#!/usr/bin/env python3
"""PROTOTYPE, read-only: recover .desktop metadata (Name, Comment, Categories, Icon) from OPK files and compare it with what the browser
shows today. Needs `unsquashfs` (run in WSL, not as root). It changes no candidate, snapshot, catalog, approval, installer or key.

An OPK is untrusted data. Nothing in it is executed, mounted or installed. Only regular files are extracted (the .desktop file and the one
icon it names, size-bounded) into fresh temp directories that are deleted afterwards; symlinks, devices and odd names are refused.
A package is tied to a candidate by identity, never by file name alone: squashfs signature, the byte size recorded for that candidate and,
when a SHA-256 is on record (docs/CANDIDATE_REVIEW_*.md), the hash.

  python3 -I tools/opk_metadata_probe.py --local ID=PATH ...   # OPK files you already have, tied to a candidate ID by identity (no default paths)
  python3 -I tools/opk_metadata_probe.py --fetch [--report docs/OPK_METADATA_REPORT.md] [--json build/opk-metadata.json]
      also downloads the verified wiki listings that have no local file, from the URL recorded in candidates/wiki-listings.json only
      (HTTPS, allow-listed hosts, 40 MB per file, 150 MB in total, recorded size must match), and writes one report.
"""
import argparse, hashlib, json, os, re, struct, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I does not add the script directory
import opk_metadata as OM

ROOT = Path(__file__).resolve().parent.parent
SECTION = {"games": "games", "emulators": "emulators"}   # launcher sections that name a RetroHatch category; "applications" is too generic to count
CAT_ID = {"games": "Games", "emulators": "Emulators", "media": "Media", "utilities": "Utilities", "engines": "Engines & Tools", "other": "Other"}
HOSTS = ("static.miraheze.org", "static.wikitide.net", "github.com", ".githubusercontent.com")   # exact host or suffix; every redirect hop is checked too (static.wikitide.net: where the Miraheze file host redirects)
MAX_FILE, MAX_TOTAL, DESK_MAX, ICON_MAX = 40 << 20, 150 << 20, 8192, 1 << 20


CANDS = {}


def candidates():
    out = {}
    for f in ("rg-nano.json", "wiki-listings.json"):
        for c in json.loads((ROOT / "candidates" / f).read_text(encoding="utf-8"))["candidates"]: out[c["id"]] = c
    CANDS.update(out)
    return out


def recorded_hashes():
    h = {}
    for d in (ROOT / "docs").glob("CANDIDATE_REVIEW_*.md"):
        for m in re.finditer(r"^([0-9a-f]{64})\s+(\S+)", d.read_text(encoding="utf-8"), re.M): h[m.group(2).lower()] = m.group(1)
    return h


def parse_desktop(text):
    ent, on = {}, False
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("["): on = ln == "[Desktop Entry]"; continue
        if on and "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            if "[" not in k: ent.setdefault(k.strip(), v.strip())   # localised keys ignored; first value wins
    return ent


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, timeout=90)


def regular_files(pkg):
    """REGULAR files only (a symlink, device or directory is never extracted)"""
    r = sh("unsquashfs", "-ll", pkg)
    if r.returncode: raise RuntimeError("unsquashfs listing failed")
    return [l.split("squashfs-root/", 1)[1] for l in r.stdout.splitlines() if l.startswith("-") and "squashfs-root/" in l]


def extract_one(pkg, name, dest, cap):
    if re.search(r"[*?\[\\]", name) or name.startswith("/") or ".." in name.split("/"): raise ValueError("refused name")
    r = sh("unsquashfs", "-d", dest, "-f", pkg, name)
    f = Path(dest) / name
    if r.returncode or f.is_symlink() or not f.is_file(): raise RuntimeError("extract failed")
    if f.stat().st_size > cap: raise ValueError("too large")
    return f.read_bytes()


def image_info(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) >= 24: w, h = struct.unpack(">II", b[16:24]); return "PNG", w, h
    if b[:2] == b"BM" and len(b) >= 26: w, h = struct.unpack("<ii", b[18:26]); return "BMP", w, abs(h)
    if b[:4] == b"GIF8" and len(b) >= 10: w, h = struct.unpack("<HH", b[6:10]); return "GIF", w, h
    if b[:2] == b"\xff\xd8": return "JPEG", None, None
    if b.lstrip()[:5] == b"/* XP": return "XPM", None, None
    if b"<svg" in b[:512]: return "SVG", None, None
    return None, None, None


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def cands_row(c):
    """what the browser shows for this listing today: an entry matched to an existing candidate (same_as) is shown as that candidate"""
    return CANDS.get(c.get("same_as"), c)


def before_of(row):
    row = dict(row); OM.strip(row)   # the state before enrichment, so the report reads the same whether or not the snapshots were already enriched
    return {"name": row["name"], "description": row["description"], "category": CAT_ID.get(row.get("category"), "(derived)"), "category_basis": row.get("category_basis", ""), "icon": "none"}


COMPARE = ("name differs", "category conflict", "description differs", "unmapped package", "comment is")


def compare(out, row):
    """recovered vs today's metadata: contradictions are flagged, never resolved"""
    rec_ = out["recovered"]; out["before"] = b4 = before_of(row)
    out["flags"] = [f for f in out["flags"] if not f.startswith(COMPARE)]
    sec, cat = rec_["section_category"], rec_["categories"] or ""
    if rec_["name"] and norm(rec_["name"]) != norm(b4["name"]): out["flags"].append("name differs: package %r vs listed %r" % (rec_["name"], b4["name"]))
    if sec and b4["category"] != "(derived)" and CAT_ID[sec] != b4["category"]: out["flags"].append("category conflict: package section %r vs current %s" % (cat, b4["category"]))
    if cat and not sec and cat.lower() != "applications": out["flags"].append("unmapped package category %r" % cat)
    cm = rec_["comment"] or ""
    if cm and b4["description"] and norm(cm) != norm(b4["description"]) and not norm(b4["description"]).startswith(norm(cm)): out["flags"].append("description differs: package %r vs %r" % (cm, b4["description"]))
    kind, why = OM.classify_comment(cm, out["id"], [rec_["name"], b4["name"]])
    if cm and kind != "description": out["flags"].append("comment is %s, not a description: %r" % (kind, cm))


def probe(c, pkg, hashes):
    size = os.stat(pkg).st_size; sha = hashlib.sha256(Path(pkg).read_bytes()).hexdigest()
    rec = hashes.get(Path(pkg).name.lower()) or hashes.get(c["package"]["name"].lower())
    with open(pkg, "rb") as fh: magic = fh.read(4)
    ident = {"squashfs": magic == b"hsqs", "size_equal": size == c["package"]["size"], "sha256": sha, "sha256_on_record": bool(rec), "sha256_equal": (sha == rec) if rec else None}
    ident["confidence"] = ("none" if not ident["squashfs"] or not ident["size_equal"] or ident["sha256_equal"] is False
                           else "high" if ident["sha256_equal"] else "medium (signature + recorded size; no hash on record)")
    out = {"id": c["id"], "same_as": c.get("same_as"), "package": Path(pkg).name, "identity": ident, "before": before_of(cands_row(c)), "status": "failed", "flags": []}
    if ident["confidence"] == "none": out["flags"].append("identity not confirmed: metadata NOT used"); return out
    try:
        files = regular_files(pkg); desk = sorted(f for f in files if "/" not in f and f.endswith(".desktop"))
        if not desk: out["flags"].append("no .desktop file at the package root"); out["status"] = "partial"; return out
        ents = []
        with tempfile.TemporaryDirectory() as t:
            for i, d in enumerate(desk[:8]): ents.append((d, parse_desktop(extract_one(pkg, d, "%s/d%d" % (t, i), DESK_MAX).decode("utf-8", "replace"))))
            ent = next((e for d, e in ents if norm(e.get("Name")) == norm(c["name"])), ents[0][1]); dfile = next(d for d, e in ents if e is ent)
            if len(desk) > 1: out["flags"].append("%d .desktop files: used %s" % (len(desk), dfile))
            icon, info = ent.get("Icon", ""), None
            if icon and not icon.startswith("/") and ".." not in icon.split("/"):
                exts = ("",) if re.search(r"\.(png|bmp|jpe?g|gif|xpm|svg)$", icon, re.I) else (".png", ".bmp", ".xpm", ".jpg")   # a bare Icon name means NAME.<image>; a bare file of that name can be the program
                for e2 in exts:
                    if icon + e2 in files:
                        b = extract_one(pkg, icon + e2, t + "/i", ICON_MAX); fmt, w, h = image_info(b)
                        info = {"file": icon + e2, "bytes": len(b), "format": fmt, "width": w, "height": h, "valid": fmt is not None}; break
            if not info: out["flags"].append("icon %r not found as an image in the package" % icon if icon else "no Icon key")
    except Exception as e:   # bounded failure report, nothing is retried
        out["flags"].append("extraction error: %s" % e); return out
    cat = ent.get("Categories", "").strip(";"); sec = SECTION.get(cat.split(";")[0].lower())
    rec_ = {"name": ent.get("Name"), "comment": ent.get("Comment"), "categories": cat or None, "section_category": sec, "icon": info}
    out["recovered"] = rec_; out["provenance"] = {"source": "package .desktop", "file": dfile, "package_sha256": sha, "package_size": size}
    compare(out, cands_row(c))
    full = all([rec_["name"], rec_["comment"], rec_["categories"], info and info["valid"]])
    out["status"] = "success" if full else "partial"
    return out


class Hop(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        if not allowed(newurl): raise urllib.error.URLError("redirect to a host that is not allow-listed: " + str(urllib.parse.urlsplit(newurl).hostname))
        return super().redirect_request(req, fp, code, msg, hdrs, newurl)


def allowed(url):
    u = urllib.parse.urlsplit(url); h = u.hostname or ""
    return u.scheme == "https" and any(h == x or (x.startswith(".") and h.endswith(x)) for x in HOSTS)


def fetch(url, dest, expect, budget_left):
    if not allowed(url): return "URL host not allow-listed"
    if expect > MAX_FILE: return "oversized (%d MB recorded)" % (expect >> 20)
    if expect > budget_left: return "would exceed the 150 MB budget"
    req = urllib.request.Request(url, headers={"User-Agent": "RetroHatch-metadata-probe/0"})
    try:
        with urllib.request.build_opener(Hop).open(req, timeout=40) as r, open(dest, "wb") as f:
            n = int(r.headers.get("Content-Length") or -1)
            if n not in (-1, expect): return "Content-Length %d differs from recorded size %d" % (n, expect)
            got = 0
            while True:
                b = r.read(1 << 16)
                if not b: break
                got += len(b)
                if got > expect: return "more data than the recorded size"
                f.write(b)
        return None if got == expect else "short download (%d of %d bytes)" % (got, expect)
    except Exception as e:
        return "download failed: %s" % str(e)[:80]


def report_md(res, skipped, total):
    L = ["# OPK metadata recovered from package .desktop files", "",
         "Prototype run, read-only. Nothing was executed, mounted or installed; raw packages and icons were not kept or committed. No candidate, snapshot, catalog or UI file was changed.", ""]
    ok = [r for r in res if r["status"] == "success"]; pa = [r for r in res if r["status"] == "partial"]; fa = [r for r in res if r["status"] == "failed"]
    have = [r for r in res if r.get("recovered")]
    names = [r for r in have if r["recovered"]["name"]]; desc = [r for r in have if r["recovered"]["comment"]]; cats = [r for r in have if r["recovered"]["categories"]]
    icons = [r for r in have if r["recovered"]["icon"] and r["recovered"]["icon"]["valid"]]
    newdesc = [r for r in desc if not r["before"]["description"]]; seccat = [r for r in have if r["recovered"]["section_category"]]
    flagged = [r for r in res if r["flags"] and r.get("recovered")]
    dl = sum(1 for r in res if r.get("downloaded"))
    L += ["## Summary", "", "| Measure | Count |", "|---|---|", "| Packages examined | %d (%d already on this machine, %d downloaded, %d not downloaded) |" % (len(res), len(res) - dl - len(skipped), dl, len(skipped)),
          "| Bytes downloaded | %.1f MB of the 150 MB limit |" % (total / 1e6),
          "| Success (name, comment, categories and a valid icon) | %d |" % len(ok), "| Partial | %d |" % len(pa), "| Failed | %d |" % len(fa),
          "| Usable names | %d |" % len(names), "| Comments (descriptions) | %d |" % len(desc), "| Categories present | %d (%d name a RetroHatch category: games or emulators) |" % (len(cats), len(seccat)),
          "| Comments that really describe the app (not a note or the app's own name) | %d |" % sum(1 for r in desc if not any(f.startswith("comment is") for f in r["flags"])), "| Valid icons | %d |" % len(icons), "| Entries that gain a description they lack today | %d |" % len(newdesc), "| Entries with a flag to review | %d |" % len(flagged), ""]
    fm = {}
    for r in icons: fm.setdefault("%s %sx%s" % (r["recovered"]["icon"]["format"], r["recovered"]["icon"]["width"], r["recovered"]["icon"]["height"]), []).append(r["id"])
    L += ["Icon formats and sizes: " + "; ".join("%s x%d" % (k, len(v)) for k, v in sorted(fm.items())) + ". Icon facts and a redistribution verdict are recorded; an icon ships only when the verdict is redistributable.", "",
          "Identity: every package used passed the squashfs signature and recorded-size check. SHA-256 values are on record only for Funkoban, SuDokuL and J2ME; the other entries are matched by signature plus size (\"medium\") and their computed hashes are kept in the JSON.", ""]
    L += ["## Per entry", "", "| ID | Status | Package Name | Comment | Categories | Icon | Flags |", "|---|---|---|---|---|---|---|"]
    for r in res:
        v = r.get("recovered"); ic = v and v["icon"]
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (r["id"], r["status"], (v or {}).get("name") or "-", (v or {}).get("comment") or "-", (v or {}).get("categories") or "-",
                  ("%s %sx%s" % (ic["format"], ic["width"], ic["height"]) if ic and ic["valid"] else "-"), "; ".join(r["flags"]) or ""))
    if skipped: L += ["", "## Skipped or failed downloads", ""] + ["- %s: %s" % (i, w) for i, w in skipped]
    L += ["", "## Before and after (examples)", "", "| Entry | Today | Recovered |", "|---|---|---|"]
    for r in sorted(newdesc, key=lambda r: r["id"])[:8]:
        v = r["recovered"]; L.append("| %s | name %s; no description; category %s (%s) | Comment \"%s\"; Categories %s |" % (r["id"], r["before"]["name"], r["before"]["category"], "file name only" if "file name only" in r["before"]["category_basis"] else "reviewed", v["comment"], v["categories"]))
    L += ["", "## Contradictions flagged (nothing was overwritten)", ""] + (["- %s: %s" % (r["id"], f) for r in flagged for f in r["flags"] if f.startswith(COMPARE)] or ["- none"])
    L += ["", "## Maintainer edits to displayed text", ""] + ["- %s: shown as %r instead of the package Comment (%s). The original Comment stays in the evidence file." % (k, v[0], v[1]) for k, v in OM.DISPLAY.items()]
    return "\n".join(L) + "\n"


def evidence_doc(res, cands, icon_sha=None):
    """the part of the probe results worth keeping in Git: identity, extracted fields and icon facts; no paths, no package or icon bytes"""
    recs = []
    for r in res:
        v = r.get("recovered")
        if not v: continue
        c = cands[r["id"]]; rid = c.get("same_as") or r["id"]; ic = v["icon"]; pv = r["provenance"]; hi = r["identity"]["sha256_equal"] is True
        kind, why = OM.classify_comment(v["comment"], r["id"], [v["name"], r["before"]["name"], c["name"]])
        recs.append({"id": rid, **({"listed_as": r["id"]} if rid != r["id"] else {}),
                     "package": {"name": c["package"]["name"], "size": pv["package_size"], "sha256": pv["package_sha256"],
                                 "identity": "high: SHA-256 on record" if hi else "medium: squashfs signature + recorded size"},
                     "desktop": {"file": pv["file"], "name": v["name"], "comment": v["comment"], "categories": v["categories"]},
                     "icon": {"file": ic["file"], "bytes": ic["bytes"], "format": ic["format"], "width": ic["width"], "height": ic["height"], "available": ic["valid"],
                              **({"sha256": icon_sha[rid]} if icon_sha and rid in icon_sha else {}),
                              "redistribution": OM.icon_rights(rid, c.get("license") if "same_as" not in c else cands[c["same_as"]].get("license"))},
                     "comment_class": kind, **({"comment_reason": why} if why else {}),
                     **({"display_comment": OM.DISPLAY[r["id"]][0], "display_comment_reason": OM.DISPLAY[r["id"]][1]} if r["id"] in OM.DISPLAY else {}), **({"multiple_desktop_files": True} if any(".desktop files" in f for f in r["flags"]) else {})})
    return {"schema": 1, "source": "OPK package .desktop files, read with tools/opk_metadata_probe.py (squashfs signature and recorded size checked; nothing executed)",
            "note": "Original package bytes and icons are not kept. Icon facts and a redistribution verdict are recorded; an icon ships only when the verdict is redistributable. Package categories are evidence, not a category assignment.",
            "records": sorted(recs, key=lambda x: x["id"])}


def fetch_icons(a):
    """Save the icon of every evidence record into a folder, checking each package against the recorded SHA-256 and each icon against the
    recorded format, size and byte count. Local packages come from --local; the others are downloaded from the URL recorded for the listing."""
    ev = json.loads(Path(a.evidence_in).read_text(encoding="utf-8"))["records"]
    listing = {c["id"]: c for c in json.loads((ROOT / "candidates" / "wiki-listings.json").read_text(encoding="utf-8"))["candidates"]}
    local = dict(x.split("=", 1) for x in a.local); out = Path(a.icons); out.mkdir(parents=True, exist_ok=True)
    got, problems, total = [], [], 0
    with tempfile.TemporaryDirectory(prefix="rh_ico_") as t:
        for r in ev:
            rid, lid = r["id"], r.get("listed_as", r["id"]); pkg = local.get(lid) or local.get(rid); fetched = False
            if pkg is None:
                dest = os.path.join(t, "pkg.opk"); why = fetch(listing[lid]["package"]["url"], dest, r["package"]["size"], MAX_TOTAL - total)
                if why: problems.append((rid, why)); continue
                total += r["package"]["size"]; pkg = dest; fetched = True
            try:
                if hashlib.sha256(Path(pkg).read_bytes()).hexdigest() != r["package"]["sha256"]: raise ValueError("package SHA-256 differs from the recorded one")
                ic = r["icon"]
                if ic["file"] not in regular_files(pkg): raise ValueError("icon file not in the package")
                b = extract_one(pkg, ic["file"], t + "/i", ICON_MAX); info = image_info(b)
                if info != (ic["format"], ic["width"], ic["height"]) or len(b) != ic["bytes"]: raise ValueError("icon differs from the recorded format, size or byte count")
                name = rid + "." + ic["format"].lower(); (out / name).write_bytes(b)
                got.append({"id": rid, "file": name, "format": ic["format"], "width": ic["width"], "height": ic["height"], "bytes": len(b),
                            "sha256": hashlib.sha256(b).hexdigest(), "package_sha256": r["package"]["sha256"], "package_identity": "SHA-256 equals the recorded one"})
            except Exception as e:   # one bad package never stops the others
                problems.append((rid, str(e)[:100]))
            finally:
                if fetched and os.path.exists(pkg): os.remove(pkg)
            if fetched: time.sleep(0.3)
    (out / "manifest.json").write_text(json.dumps({"icons": got, "problems": problems, "downloaded_bytes": total}, indent=1) + "\n", encoding="utf-8")
    print("%d icons saved, %d problems, %.1f MB downloaded" % (len(got), len(problems), total / 1e6), file=sys.stderr)
    for p_ in problems: print("  PROBLEM %s: %s" % p_, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", action="append", default=[], metavar="ID=PATH", help="a local OPK for candidate ID; repeatable")
    ap.add_argument("--fetch", action="store_true"); ap.add_argument("--json"); ap.add_argument("--report")
    ap.add_argument("--from-json", help="regenerate --report from an earlier --json file: no download, no extraction")
    ap.add_argument("--icons", metavar="DIR", help="save each evidence record's icon into DIR (git-ignored build/ is a good place); packages are re-fetched or taken from --local")
    ap.add_argument("--icons-manifest", help="with --evidence: manifest.json written by --icons; adds each icon's SHA-256 to the evidence")
    ap.add_argument("--evidence-in", default=str(ROOT / "discovery" / "opk-metadata-evidence.json"), help="evidence file --icons reads")
    ap.add_argument("--evidence", help="with --from-json: write the compact, path-free evidence file (discovery/opk-metadata-evidence.json)")
    ap.add_argument("--resume", help="earlier --json output: entries it already downloaded and probed are kept, not fetched again")
    a = ap.parse_args()
    if os.geteuid() == 0: sys.exit("refusing to run as root")
    if a.icons: return fetch_icons(a)
    cands, hashes = candidates(), recorded_hashes(); res = []; skipped = []; total = 0
    if a.from_json:
        res = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        for r in res:
            if r.get("recovered"): compare(r, cands_row(cands[r["id"]]))
        total = sum(r["provenance"]["package_size"] for r in res if r.get("downloaded") and r.get("provenance"))
        icon_sha = {i["id"]: i["sha256"] for i in json.loads(Path(a.icons_manifest).read_text(encoding="utf-8"))["icons"]} if a.icons_manifest else None
        if a.evidence: Path(a.evidence).write_bytes((json.dumps(evidence_doc(res, cands, icon_sha), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
        if a.json: Path(a.json).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        if a.report: Path(a.report).write_bytes(report_md(res, [], total).encode("utf-8"))
        return
    probes = [tuple(x.split("=", 1)) for x in a.local]
    for cid, p in probes: res.append(probe(cands[cid], p, hashes))
    local = {cid for cid, _ in probes}
    if a.fetch:
        prev = {r["id"]: r for r in json.loads(Path(a.resume).read_text(encoding="utf-8"))} if a.resume else {}
        for r in prev.values():
            if r.get("downloaded") and r["id"] not in local: res.append(r); total += r["identity"]["size_equal"] and r["provenance"]["package_size"] if r.get("provenance") else 0
        local |= {r["id"] for r in res}
        todo = [c for c in json.loads((ROOT / "candidates" / "wiki-listings.json").read_text(encoding="utf-8"))["candidates"] if c["package"]["signature"] and c["id"] not in local]
        print("%d packages recorded as verified and not on this machine" % len(todo), file=sys.stderr)
        with tempfile.TemporaryDirectory(prefix="rh_opk_") as t:
            for c in todo:
                dest = os.path.join(t, "pkg.opk"); why = fetch(c["package"]["url"], dest, c["package"]["size"], MAX_TOTAL - total)
                if why: skipped.append((c["id"], why)); res.append({"id": c["id"], "status": "failed", "flags": ["not downloaded: " + why], "before": {"name": c["name"], "description": c["description"]}}); continue
                total += c["package"]["size"]
                r = probe(c, dest, hashes); r["downloaded"] = True; res.append(r); os.remove(dest); time.sleep(0.3)
    for r in res: print("%-26s %-8s %s" % (r["id"], r["status"], "; ".join(r["flags"])[:110]), file=sys.stderr)
    if a.json: Path(a.json).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if a.report: Path(a.report).write_bytes(report_md(res, skipped, total).encode("utf-8"))


if __name__ == "__main__":
    main()
