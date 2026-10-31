#!/usr/bin/env python3
"""Local, UNAPPROVED RG Nano candidate snapshot from an existing discovery result. Offline: reads a discovery-results.json, makes no request.
Never touches catalog/ or approvals.json. Each entry also carries the repository topics: the UI derives the category from name, description and topics. One entry per repository (a repo's other packages are only counted), chosen by fixed rules:
installable package with verified squashfs signature, repo not a fork or archived, package >= MIN_SIZE (skips helper stubs), device claim
'supports' (RG Nano named) before 'family' (FunKey only), newest activity first, at most PER_OWNER per owner, at most MAX entries.

  python tools/make_candidate_snapshot.py [--results build/crawl-full/discovery-results.json] [--out candidates/rg-nano.json]
"""
import argparse, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATS = {"games", "emulators", "media", "utilities", "engines", "other"}   # ids the UI reads; anything else is ignored there
MAX, PER_OWNER, MIN_SIZE = 10, 2, 64 * 1024
DIRECT = re.compile(r"rg[ -_]?nano|funkey[ -_]?os", re.I)
FAMILY = re.compile(r"funkey", re.I)


def alnum(s): return re.sub(r"[^a-z0-9]", "", s.lower())


def app_name(pkg, repo):
    """Package file name without extension, device suffix and version: Znax.opk -> Znax, SuDokuL-v1.5-funkey.opk -> SuDokuL."""
    s = re.sub(r"\.opk$", "", pkg["name"], flags=re.I)
    s = re.sub(r"[-_ ]*funkey([-_ ]*s)?$", "", s, flags=re.I)
    s = re.sub(r"[-_ ]*v?\d+(\.\d+)+$", "", s, flags=re.I)
    s = re.sub(r"[-_ ]*v\d+$", "", s, flags=re.I)
    return s if len(s) > 2 else repo.split("/")[1]   # "pm.opk" says nothing: fall back to the repository name


def claim_of(r):
    """(kind, text, where): the best statement tying the software to the device, or ('', 'Unknown', '')."""
    ev = [e for e in r.get("evidence") or [] if e["kind"] == "supports"]
    if ev:
        e = ev[0]; return "rg-nano" if DIRECT.search(e["text"]) else "family", e["text"].strip(" .!"), e["source"]
    m = r.get("meta") or {}
    for where, text in (("description", m.get("description") or ""), ("topics", " ".join(m.get("topics") or [])), ("name", r["repo"].split("/")[1])):
        if DIRECT.search(text): return "rg-nano", text.strip(), where
        if FAMILY.search(text): return "family", text.strip(), where
    return "", "Unknown", ""


def reviewed_category(repo, r, pkgs, reviewed):
    """(id, basis) from candidates/categories.json, or (None, None). Every quote must occur in the cached data for this repository."""
    e = (reviewed or {}).get(repo)
    if not e: return None, None
    hay = json.dumps({"meta": r.get("meta"), "evidence": r.get("evidence"), "packages": [p["name"] for p in pkgs]}, ensure_ascii=False).lower()
    quotes = e.get("evidence") or []
    if e.get("category") not in CATS or not quotes: raise SystemExit(f"{repo}: reviewed category needs a known id and evidence quotes")
    for q in quotes:
        if q.lower() not in hay: raise SystemExit(f"{repo}: evidence {q!r} not found in the discovery data")
    return e["category"], "; ".join(quotes)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default=str(ROOT / "build" / "crawl-full" / "discovery-results.json"))
    ap.add_argument("--out", default=str(ROOT / "candidates" / "rg-nano.json"))
    ap.add_argument("--categories", default=str(ROOT / "candidates" / "categories.json"))
    a = ap.parse_args()
    res = json.loads(Path(a.results).read_text(encoding="utf-8"))
    repos = {r["repo"].lower(): r for r in res["repos"]}
    cf = Path(a.categories)
    reviewed = json.loads(cf.read_text(encoding="utf-8")).get("reviewed") if cf.is_file() else {}
    by = {}
    for p in res["unique_installable_apps"]:
        r = repos.get((p.get("repo") or "").lower())
        if r and p["judgement"] == "installable" and p.get("magic_squashfs") is True and not p.get("alias_of"): by.setdefault(r["repo"], []).append(p)
    picks = []
    for repo, pk in by.items():
        r = repos[repo.lower()]; m = r.get("meta") or {}
        pk = [p for p in pk if (p.get("size") or 0) >= MIN_SIZE]
        kind, text, where = claim_of(r)
        if not pk or m.get("fork") or m.get("archived") or not kind: continue
        best = sorted(pk, key=lambda p: (alnum(app_name(p, repo)) != alnum(repo.split("/")[1]), len(p["name"]), p["name"]))[0]
        picks.append((kind != "rg-nano", "".join(chr(255 - ord(c)) for c in (m.get("pushed_at") or "")), repo, r, m, best, len(pk) - 1, (kind, text, where)))
    picks.sort(key=lambda t: t[:3])
    out, owners = [], {}
    for _, _, repo, r, m, p, more, (kind, text, where) in picks:
        o = repo.split("/")[0].lower()
        if owners.get(o, 0) >= PER_OWNER or len(out) >= MAX: continue
        owners[o] = owners.get(o, 0) + 1
        via = next((v["from"] for v in r.get("via") or [] if v.get("from") and "github-search" not in v["from"]), "github-search")
        cat, basis = reviewed_category(repo, r, by[repo], reviewed)
        out.append({
            "id": alnum(app_name(p, repo)) or alnum(repo), "name": app_name(p, repo), "description": m.get("description") or "", "topics": list(m.get("topics") or [])[:12],
            "version": r.get("release") or "", "repo": repo, "source": r["url"], "license": m.get("license") or "", "last_activity": (m.get("pushed_at") or "")[:10],
            "package": {"name": p["name"], "url": p["url"], "size": p.get("size") or 0, "format": "opk", "signature": "squashfs",
                        "container": "zip" if p["kind"] == "zip" else "", "more_packages": more},
            "claim": {"kind": kind, "text": text, "where": where},
            **({"category": cat, "category_basis": basis} if cat else {}),
            "hardware_test": "none", "approval": "unapproved"})
    doc = {"schema": 1, "device": "rg-nano", "status": "UNAPPROVED local candidates, not part of the signed catalog",
           "from": {"results": Path(a.results).name, "as_of": res["as_of"]}, "candidates": out}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in out: print(f"{c['name']:22} {c['version']:14} {c['claim']['kind']:8} {c['package']['size']:>9} +{c['package']['more_packages']} {c['repo']}")


if __name__ == "__main__":
    main()
