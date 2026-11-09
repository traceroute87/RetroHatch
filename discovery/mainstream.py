#!/usr/bin/env python3
"""Mainstream-software discovery: a curated seed list (discovery/mainstream.json) of well-known Android emulators, frontends and ports, CHECKED against their official
channels, then compared with what the catalog and the candidate inventory already hold (the gap report). Leads only: nothing is approved, signed or published, and
catalog/ is never written.

  python discovery/mainstream.py verify [--inspect] [--out build/discovery]   network: resolve each channel, check the real file, optionally read its manifest
  python discovery/mainstream.py gap [--out build/discovery] [--device-packages FILE]   offline: build/discovery/gap-report.md from the verification + the catalogs

Channel kinds: github (latest release or a named tag, assets from the release page), listing (an official download directory), page (an official page that links the APK),
gitlab (releases API), store (an EXTERNAL LISTING: a store page is never presented as a direct APK; only its existence is checked). A direct file is confirmed by a 4-byte
range read (ZIP magic). --inspect downloads each confirmed APK (cap 230 MB, deleted afterwards) and reads package, minSdk, ABIs and signer with tools/apk_inspect.py.
"""
import argparse, hashlib, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
UA = "Mozilla/5.0 (compatible; retrohatch-discovery/1; +https://github.com/traceroute87/RetroHatch)"
CAP = 230 * 1024 * 1024
WEIGHT = {"light": "light system: expected to run comfortably on a mid-range SoC like the Unisoc T618",
          "medium": "medium system: playable for many titles on a T618-class SoC; demanding games may struggle",
          "heavy": "heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device)",
          "varies": "depends on the system/core run inside it"}


def get(url, rng=None, n=900_000, accept_json=False):
    h = {"User-Agent": UA}
    if rng: h["Range"] = rng
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30)
        return r.status, r.geturl(), dict(r.headers), r.read(n)
    except urllib.error.HTTPError as e:
        return e.code, url, dict(e.headers or {}), b""
    except Exception as e:
        return 0, url, {}, str(e)[:80].encode()


def text(url, n=900_000):
    st, final, _, b = get(url, n=n)
    return st, final, b.decode("utf-8", "replace")


def vkey(s):
    return tuple(int(x) for x in re.findall(r"\d+", s)) or (0,)


def probe(url):
    """-> (real ZIP/APK magic | None unreachable, size, final url)."""
    st, final, h, b = get(url, "bytes=0-3", 4)
    cr = h.get("Content-Range", "")
    size = int(cr.rsplit("/", 1)[1]) if "/" in cr and cr.rsplit("/", 1)[1].isdigit() else (int(h["Content-Length"]) if st == 200 and str(h.get("Content-Length", "")).isdigit() else None)
    return ((b == b"PK\x03\x04") if st in (200, 206) else None), size, final


def github_meta(repo):
    st, _, _, b = get(f"https://api.github.com/repos/{repo}")
    if st != 200: return {"status": st}
    j = json.loads(b)
    return {"status": 200, "license": (j.get("license") or {}).get("spdx_id") or "none", "archived": j["archived"], "pushed": j["pushed_at"][:10], "stars": j["stargazers_count"],
            "fork": j["fork"], "description": j.get("description")}


def do_github(ch):
    repo = ch["repo"]
    tag = ch.get("tag")
    if not tag:
        st, final, _ = text(f"https://github.com/{repo}/releases/latest", 10)
        tag = final.rsplit("/tag/", 1)[1] if "/tag/" in final else None
    if not tag:
        return {"ok": False, "why": "no release published on GitHub"}
    st, _, html = text(f"https://github.com/{repo}/releases/expanded_assets/{tag}")
    names = re.findall(r'href="/[^"]+/releases/download/[^"/]+/([^"]+)"', html)
    names = [urllib.parse.unquote(x) for x in names]
    hit = [n for n in names if re.search(ch["pick"], n, re.I)]
    st2, _, page = text(f"https://github.com/{repo}/releases/tag/{tag}", 200_000)
    published = (re.search(r'datetime="(\d{4}-\d{2}-\d{2})', page) or [None, ""])[1]
    if not hit:
        return {"ok": False, "tag": tag, "published": published, "assets": names[:8], "why": "latest release has no matching APK" + (" (assets: " + ", ".join(names[:5]) + ")" if names else " (no assets)")}
    return {"ok": True, "tag": tag, "published": published, "file": hit[0], "url": f"https://github.com/{repo}/releases/download/{tag}/{urllib.parse.quote(hit[0])}", "assets": names[:8]}


def do_listing(ch):
    st, base, html = text(ch["base"])
    if st != 200: return {"ok": False, "why": f"directory listing HTTP {st}"}
    root = ch["base"]
    if ch.get("dirs", True):
        vers = sorted({m for m in re.findall(r'href="[^"]*?/(\d+(?:\.\d+)+)/"', html)}, key=vkey)
        if not vers: return {"ok": False, "why": "no version directories found"}
        root = f"{ch['base']}{vers[-1]}/"
        tag = vers[-1]
    else:
        tag = ""
    st, sub, html = text(root + ch.get("subdir", ""))
    if st != 200: return {"ok": False, "why": f"HTTP {st} for {root + ch.get('subdir', '')}"}
    files = [f for f in re.findall(r'href="([^"]+\.apk)"', html) if re.search(ch["pick"], f)]
    if not files: return {"ok": False, "why": "no matching APK in the directory"}
    f = sorted(files, key=vkey)[-1]
    url = urllib.parse.urljoin(sub, f)
    return {"ok": True, "tag": tag or (re.search(r"(\d+)\.apk", f) or [None, ""])[1], "file": f.rsplit("/", 1)[-1], "url": url, "published": ""}


def do_page(ch):
    st, final, html = text(ch["url"])
    if st != 200: return {"ok": False, "why": f"official page HTTP {st}" + (" (the site blocks automated requests)" if st in (403, 429) else "")}
    found = re.findall(ch["pick"], html)
    links = [m.group(0) for m in re.finditer(ch["pick"], html)]
    if not links: return {"ok": False, "why": "the page links no APK"}
    pairs = sorted(zip(re.findall(r"(?:" + ch["pick"] + r")", html), links), key=lambda x: vkey(x[0] if isinstance(x[0], str) else x[0][0]))
    url = urllib.parse.urljoin(final, sorted(set(links), key=vkey)[-1] if ch.get("newest") else links[0])
    return {"ok": True, "tag": ".".join(re.findall(r"\d+", url.split("/files/")[1].split("/")[0])) if "/files/" in url else "", "file": url.rsplit("/", 1)[-1], "url": url, "published": ""}


def do_gitlab(ch):
    st, _, _, b = get(f"https://gitlab.com/api/v4/projects/{urllib.parse.quote(ch['project'], safe='')}/releases?per_page=3")
    if st != 200: return {"ok": False, "why": f"GitLab releases API HTTP {st}"}
    rels = json.loads(b)
    for r in rels:
        names = [l["name"] for l in r["assets"]["links"]]
        hit = [l for l in r["assets"]["links"] if re.search(ch["pick"], l["name"], re.I)]
        if hit: return {"ok": True, "tag": r["tag_name"], "published": r["released_at"][:10], "file": hit[0]["name"], "url": hit[0]["url"]}
    return {"ok": False, "tag": rels[0]["tag_name"] if rels else "", "published": rels[0]["released_at"][:10] if rels else "", "why": "the three latest releases attach no APK (assets: " + ", ".join(names[:4]) + ")"}


def do_store(ch):
    st, final, html = text(ch["url"], 120_000)
    title = (re.search(r"<title[^>]*>([^<]*)</title>", html) or [None, ""])[1].strip()
    return {"ok": st == 200, "http": st, "title": re.sub(r"\s+", " ", title)[:90], "why": "" if st == 200 else f"listing returned HTTP {st}"}


RESOLVE = {"github": do_github, "listing": do_listing, "page": do_page, "gitlab": do_gitlab, "store": do_store}


def inspect_apk(app_id, url, outdir):
    import apk_inspect as AI
    f = outdir / "apk" / f"{app_id}.apk"
    f.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r, open(f, "wb") as o:
            while b := r.read(1 << 20):
                n += len(b)
                if n > CAP: raise RuntimeError("over the size cap")
                o.write(b); h.update(b)
        info = AI.inspect(f)
        return {k: info[k] for k in ("package", "version_code", "version_name", "min_sdk", "target_sdk", "abis", "signers_sha256", "fits", "debuggable")} | {"sha256": h.hexdigest(), "size": n}
    except (Exception, SystemExit) as e:
        return {"error": str(e)[:120]}
    finally:
        for _ in range(8):                      # Windows may still hold the file for a moment after aapt2/apksigner exit
            try: f.unlink(missing_ok=True); break
            except PermissionError: __import__("time").sleep(0.7)


def verify(a):
    seeds = json.loads((HERE / "mainstream.json").read_text(encoding="utf-8"))["apps"]
    out = []
    for app in seeds:
        rec = {"id": app["id"], "name": app["name"], "channels": [], "repo_meta": None}
        if app["source"].startswith("https://github.com/"):
            rec["repo_meta"] = github_meta(app["source"].removeprefix("https://github.com/"))
        for ch in app["channels"]:
            r = RESOLVE[ch["kind"]](ch) | {"kind": ch["kind"], "label": ch.get("label") or ch.get("repo") or ch.get("project")}
            if ch["kind"] != "store" and r.get("ok"):
                real, size, final = probe(r["url"])
                r.update({"real_file": real, "size": size, "final_url": final, "zip_of_apk": bool(ch.get("zip"))})
                if real is not True: r["ok"] = False; r["why"] = "the link did not answer with a ZIP/APK file" if real is False else "the file could not be reached"
                elif a.inspect and not ch.get("zip"): r["manifest"] = inspect_apk(app["id"], r["url"], Path(a.out))
            rec["channels"].append(r)
            print(f"{app['id']:14} {r['kind']:8} {'OK ' if r.get('ok') else '-- '} {r.get('tag', r.get('http', '')) or ''} {r.get('file') or r.get('title') or r.get('why', '')}"[:150])
        out.append(rec)
    res = {"schema": 1, "checked": date.today().isoformat(), "apps": out}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "mainstream-verified.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("->", Path(a.out) / "mainstream-verified.json")


# ---- gap report ------------------------------------------------------------------------------------------------------------------

def catalog_index():
    """What the catalog / inventory already holds, by package and by source repository."""
    have = {}
    def add(key, where): have.setdefault(key.lower(), []).append(where)
    dev = ROOT / "android" / "app" / "src" / "debug" / "assets" / "dev" / "catalog" / "index.json"
    if dev.is_file():
        for ap in json.loads(dev.read_text(encoding="utf-8"))["apps"]:
            for art in ap["artifacts"]:
                if art.get("android"): add(art["android"]["package"], "DEV catalog (bundled, experimental)")
            add(ap["source"].removeprefix("https://github.com/"), "DEV catalog (bundled, experimental)")
    for d in (ROOT / "catalog" / "apps",):
        for p in d.glob("*.json"):
            ap = json.loads(p.read_text(encoding="utf-8"))
            for art in ap.get("artifacts", []):
                if art.get("android"): add(art["android"]["package"], "production catalog")
    inv = ROOT / "candidates" / "inventory-rg-rotate.json"
    for ap in json.loads(inv.read_text(encoding="utf-8"))["applications"]:
        for pk in ap.get("packages", []):
            if pk.get("android"): add(pk["android"]["package"], "candidate inventory" + (" (ON HOLD: " + ap["hold"] + ")" if ap.get("hold") else ""))
        for s in ap.get("sources", []):
            add(s["url"].removeprefix("https://github.com/"), "candidate inventory" + (" (ON HOLD: " + ap["hold"] + ")" if ap.get("hold") else ""))
    return have


def release_ok(source, url):
    """tools/trust.py + the device verifier: a catalog APK URL must be a release download of the entry's OWN GitHub source repository."""
    m = re.fullmatch(r"https://github\.com/([^/\s]+)/([^/\s]+?)/?", source or "")
    return bool(m and url and re.match(re.escape(f"https://github.com/{m.group(1)}/{m.group(2)}/releases/download/") + r"[^/]+/[^/]+$", url, re.I))


def gap(a):
    seeds = {x["id"]: x for x in json.loads((HERE / "mainstream.json").read_text(encoding="utf-8"))["apps"]}
    ver = {x["id"]: x for x in json.loads((Path(a.out) / "mainstream-verified.json").read_text(encoding="utf-8"))["apps"]}
    checked = json.loads((Path(a.out) / "mainstream-verified.json").read_text(encoding="utf-8"))["checked"]
    have = catalog_index()
    onpkg = set(Path(a.device_packages).read_text().split()) if a.device_packages and Path(a.device_packages).is_file() else set()
    rows, buckets = [], {"direct": [], "store": [], "unresolved": []}
    for i, s in seeds.items():
        v = ver[i]
        where = sorted({w for k in ([s["package"]] if s["package"] else []) + [s["source"].removeprefix("https://github.com/")] for w in have.get(k.lower(), []) if k})
        direct = next((c for c in v["channels"] if c["kind"] != "store" and c.get("ok")), None)
        stores = [c for c in v["channels"] if c["kind"] == "store" and c.get("ok")]
        man = (direct or {}).get("manifest") or {}
        if direct: buckets["direct"].append(i)
        elif stores or any(c["kind"] == "store" and c.get("http") in (403, 429) for c in v["channels"]): buckets["store"].append(i)
        else: buckets["unresolved"].append(i)
        rows.append((s, v, where, direct, stores, man))
    md = [f"# Mainstream Android retro software: gap report · checked {checked}\n",
          "Leads, not approvals. Every claim below was read from an official page, a release page or the APK's own manifest on the date above; where something could not be confirmed it says so. "
          "\"Expected RG Rotate compatibility\" is an expectation from the file's manifest and the SoC class (Unisoc T618, Android 12 / API 31, arm64, about 2.5 GB RAM): **none of it was tested**.\n",
          f"**{len(seeds)} seeds** · in the catalog or inventory already: **{sum(1 for r in rows if r[2])}** · missing: **{sum(1 for r in rows if not r[2])}** · verified official direct APK: **{len(buckets['direct'])}** · "
          f"store-only (external listing): **{len(buckets['store'])}** · unresolved: **{len(buckets['unresolved'])}**\n"]
    md += ["## Summary\n", "| App | Systems | In our catalog? | Official direct APK (verified) | Licence · price | Min Android · ABIs (from the APK) | Expected on RG Rotate |", "|---|---|---|---|---|---|---|"]
    for s, v, where, direct, stores, man in rows:
        cat = "; ".join(where) if where else "**missing**"
        if direct:
            size = direct.get("size") or man.get("size")
            sz = f"{size / 1048576:.0f} MB" if size else ""
            dl = f"yes: [{direct['file'][:38]}]({direct['url']}) · {direct.get('tag', '')} · {sz}" + (" · official ZIP of APKs, pre-release" if direct.get("zip_of_apk") else "")
        elif stores or any(c["kind"] == "store" for c in v["channels"]):
            blocked = [c["label"] for c in v["channels"] if c["kind"] == "store" and c.get("http") in (403, 429)]
            dl = "no: store listing only (" + ", ".join([c["label"] for c in stores] + [b + ", page blocks automated checks" for b in blocked]) + ")"
        else: dl = "**not confirmed**: " + ("; ".join(c.get("why", "") for c in v["channels"] if c.get("why")) or "no official channel identified")
        lic = (v["repo_meta"] or {}).get("license") if v.get("repo_meta") and v["repo_meta"].get("status") == 200 else None
        if lic in (None, "NOASSERTION", "none"):
            licence = f"{s['license']} (curated; GitHub shows no SPDX id)" + f" · {s['price']}" if lic else f"{s['license']} (curated) · {s['price']}"
        else:
            licence = f"{lic} (GitHub) · {s['price']}"
        if man.get("package"):
            api = f"API {man['min_sdk']}+ · {', '.join(man['abis']) or 'no native code'}"
            fit = ("installable on API 31 / arm64 (manifest, not a test)" if man["fits"]["rg_rotate_android12_arm64"] else "**manifest says it cannot install on RG Rotate** (minSdk or ABI)")
        elif man.get("error"): api, fit = "APK not inspected (" + man["error"][:40] + ")", "unknown"
        else: api, fit = "not inspected (no direct APK)" if not direct else "not inspected", "unknown until a file is inspected"
        exp = f"{fit}; {WEIGHT[s['weight']]}"
        if s["package"] in onpkg: exp += f"; `{s['package']}` is installed on the test device (not a compatibility test)"
        md.append(f"| **{s['name']}** | {', '.join(s['systems'])[:48]} | {cat} | {dl} | {licence} | {api} | {exp} |")
    md += ["", "## What can enter the signed catalog as a direct download", "",
           "The catalog policy (`tools/trust.py`, the device verifier) accepts an APK only when its URL is a **GitHub release download of the entry's own source repository**. Of the verified direct APKs:", ""]
    for s, v, where, direct, stores, man in rows:
        if direct:
            ok = release_ok(s["source"], direct["url"])
            md.append(f"- **{s['name']}**: {'**eligible**' if ok and not direct.get('zip_of_apk') else 'external listing / manual only'} - " + ("GitHub release of its own repository." if ok and not direct.get("zip_of_apk") else
                      ("the official file is a ZIP of APKs on a pre-release." if direct.get("zip_of_apk") else f"the official download is on `{urllib.parse.urlsplit(direct['url']).netloc}`, not a GitHub release of `{s['source'].removeprefix('https://github.com/') or 'its repository'}`.")) +
                      (f" Licence note: {s['notes']}" if s["id"] in ("duckstation", "nethersx2") else ""))
    md += ["", "## Store-only software: external listings", "",
           "These have no APK we may link directly. They can appear in RetroHatch only as clearly labelled **external listings** (a link to the store page, no download, no install button).", ""]
    for s, v, where, direct, stores, man in rows:
        if not direct:
            md.append(f"- **{s['name']}** ({', '.join(s['systems'])}): " + (", ".join(f"[{c['label']}]({next(x['url'] for x in seeds[s['id']]['channels'] if x['kind'] == 'store' and (x.get('label') == c['label']))})" for c in stores) or "no live listing found") +
                      f" · {s['price']}" + (f" · {s['notes']}" if s.get("notes") else ""))
    md += ["", "## Findings that change the plan", ""]
    dead = [r for r in rows if r[0]["id"] == "yabasanshiro2" and r[1]["repo_meta"] and r[1]["repo_meta"].get("status") != 200]
    if dead: md.append("- **Yaba Sanshiro 2**: the source repository its own website links (`github.com/devmiyax/yabause`) returns 404; only Google Play listings exist.")
    md.append("- **Beacon**: no official project could be identified with the name alone. Please say which Beacon is meant (launcher, URL or package) before it is added.")
    md.append("- **RetroArch cores are not counted** as separate apps; RetroArch, Lemuroid and similar frontends are one entry each.")
    md += ["", "## Directory seeds for the 500+ goal (next step, not run yet)", "",
           "Machine-readable or list-style directories that cover emulators and handheld software by console and category, to be read into `discovery/search.py` as seeds, then filtered to real, licensed, installable, non-duplicate APKs:", "",
           "- Obtainium crowdsourced configurations: `apps.obtainium.imranr.dev` (JSON of apps with their release sources)", "- F-Droid category index: Games, Multimedia, System (`f-droid.org/packages/`) and IzzyOnDroid", "- Emulation wikis and guides that list Android emulators per console (emulation.gametechwiki.com, the r/EmulationOnAndroid wiki, retro-handheld guides)",
           "- GitHub topics by console (`topic:gameboy`, `topic:psp`, `topic:n64`, ...) combined with `topic:android`, and `topic:retro-handheld` repositories", ""]
    out = Path(a.out) / "gap-report.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    (Path(a.out) / "gap-report.json").write_text(json.dumps({"checked": checked, "missing": [r[0]["id"] for r in rows if not r[2]], "direct": buckets["direct"], "store_only": buckets["store"], "unresolved": buckets["unresolved"]}, indent=1) + "\n")
    print(out, {k: len(v) for k, v in buckets.items()})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    v = sp.add_parser("verify"); v.add_argument("--inspect", action="store_true"); v.add_argument("--out", default=str(ROOT / "build" / "discovery"))
    g = sp.add_parser("gap"); g.add_argument("--out", default=str(ROOT / "build" / "discovery")); g.add_argument("--device-packages")
    a = ap.parse_args()
    (verify if a.cmd == "verify" else gap)(a)


if __name__ == "__main__":
    main()
