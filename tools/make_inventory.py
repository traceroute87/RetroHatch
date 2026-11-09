#!/usr/bin/env python3
"""The one candidate inventory: candidates/inventory.json (hand-readable, audit-grade, never shipped) -> candidates/rg-nano.json (the small
read-only snapshot the Nano browser loads). Offline: no request, no download, never touches catalog/, approvals or keys.

  python tools/make_inventory.py            write the snapshot
  python tools/make_inventory.py --check    validate the inventory and fail if the committed snapshot differs from what it generates

One entry = one application (or emulator core, support file, system add-on: `kind`), with a stable `id` (lower-case name, no punctuation) that never
depends on a download URL or version. `sources` (repositories, wiki) and `packages` (files, with ZIP member, hash, mirrors) can each hold several.
Every entry is UNAPPROVED and untested; `status` says how far the package was looked at:
  package-verified  a squashfs OPK was seen by a crawl (says nothing about safety or compatibility)
  listed            named by the FunKey wiki, file not verified (see listing.download)
  unverified        an audit note says a release package exists; it was not inspected
  source-only       no release package
Detailed evidence (opk metadata ids, reviews, audit references) stays in the inventory; the snapshot carries only what the browser shows.
An entry with a non-empty `hidden` (the reason, with the date) stays here in full but is left out of the snapshot, so the browser never offers it:
used for an app whose only published download is known not to work. Remove the field when a working link exists.
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INV, OUT = ROOT / "candidates" / "inventory.json", ROOT / "candidates" / "rg-nano.json"
KINDS = {"app": "", "core": "Emulator core, not a stand-alone app. ", "system": "System add-on, changes the menu or firmware. ", "support": None}   # support: inventory only
STATUS = {"package-verified": "", "listed": "", "unverified": "Package not inspected (audit note). ", "source-only": "Source only, no release package. "}
CATS = {"games", "emulators", "media", "utilities", "engines", "other"}   # ids the UI reads
ID = re.compile(r"[a-z0-9]{2,48}")
HTTPS = re.compile(r"https://[^\s]+")


def problems(inv):
    errs, seen = [], set()
    for a in inv.get("applications", []):
        w = a.get("id", "?")
        if not ID.fullmatch(w) or w in seen: errs.append(f"{w}: id must be unique lower-case letters and digits")
        seen.add(w)
        if a.get("kind") not in KINDS: errs.append(f"{w}: unknown kind {a.get('kind')!r}")
        if a.get("status") not in STATUS: errs.append(f"{w}: unknown status {a.get('status')!r}")
        if not a.get("name"): errs.append(f"{w}: no name")
        if a.get("claim", {}).get("kind", "") not in ("rg-nano", "family", ""): errs.append(f"{w}: claim kind")
        if "category" in a and (a["category"] not in CATS or not a.get("category_basis")): errs.append(f"{w}: category needs a known id and its basis")
        for s in a.get("sources", []):
            if s.get("type") not in ("repo", "wiki") or not HTTPS.fullmatch(s.get("url", "")): errs.append(f"{w}: bad source {s}")
        for p in a.get("packages", []):
            if p.get("url") and not HTTPS.fullmatch(p["url"]): errs.append(f"{w}: package URL is not https")
            if p.get("signature", "") not in ("", "squashfs") or p.get("container", "") not in ("", "zip") or not isinstance(p.get("size", 0), int): errs.append(f"{w}: bad package fields")
            if "sha256" in p and not re.fullmatch(r"[0-9a-f]{64}", p["sha256"]): errs.append(f"{w}: bad sha256")
        seen_sig = any(p.get("signature") == "squashfs" for p in a.get("packages", []))
        if (a.get("status") == "package-verified") != seen_sig: errs.append(f"{w}: status package-verified needs (and only needs) a squashfs-verified package")
        if "hidden" in a and not (isinstance(a["hidden"], str) and a["hidden"].strip()): errs.append(f"{w}: hidden needs a reason")
        if a.get("status") == "source-only" and a.get("packages"): errs.append(f"{w}: source-only entries have no package")
        if a.get("icon_file") and not (OUT.parent / a["icon_file"]).is_file(): errs.append(f"{w}: icon file {a['icon_file']} is missing")
        for bad in ("approval", "hardware_test"):
            if bad in a: errs.append(f"{w}: {bad} is not stored here: every entry is UNAPPROVED and untested")
    return errs


def slug(url):
    m = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)", url or "")
    return m.group(1) if m else ""


def entry(a):
    repos = [s["url"] for s in a.get("sources", []) if s["type"] == "repo" and s.get("primary", True)]   # further sources are inventory detail
    wiki = next((s["url"] for s in a.get("sources", []) if s["type"] == "wiki"), "")
    pk = next((p for p in a.get("packages", []) if p.get("signature")), (a.get("packages") or [None])[0])
    e = {"id": a["id"], "name": a["name"], "description": KINDS[a["kind"]] + STATUS[a["status"]] + a["description"], "topics": a.get("topics", []),
         "version": a.get("version", ""), "repo": slug(repos[0]) if repos else "", "source": repos[0] if repos else wiki, "license": a.get("license", "unknown"),
         "last_activity": a.get("last_activity", ""),
         "package": {"name": pk["name"] if pk else "", "url": pk["url"] if pk else "", "size": pk.get("size", 0) if pk else 0, "format": pk.get("format", "") if pk else "",
                     "signature": pk.get("signature", "") if pk else "", "container": pk.get("container", "") if pk else "", "more_packages": a.get("also_in_repo", 0)},
         "claim": a["claim"]}
    if "category" in a: e["category"], e["category_basis"] = a["category"], a["category_basis"]
    e["hardware_test"], e["approval"] = "none", "unapproved"
    if "listing" in a:
        l = a["listing"]; e["listing"] = {"source": "wiki", "wiki_category": l.get("wiki_category", ""), "download": l.get("download", ""), "mirror": l.get("mirror", "")}
    if a.get("icon_file"): e["icon_file"] = a["icon_file"]
    return e


def shown(a):   # in the browser snapshot?
    return KINDS[a["kind"]] is not None and not a.get("hidden")


def snapshot(inv):
    return {"schema": 1, "device": inv["device"], "status": "UNAPPROVED candidates, read-only; not part of the signed catalog. Generated from candidates/inventory.json by tools/make_inventory.py: edit that file.",
            "candidates": [entry(a) for a in inv["applications"] if shown(a)]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate only; exit 1 on a problem or when the snapshot is out of date")
    a = ap.parse_args()
    inv = json.loads(INV.read_text(encoding="utf-8"))
    errs = problems(inv)
    text = json.dumps(snapshot(inv), ensure_ascii=False, separators=(",", ":")).replace('},{"id"', '},\n{"id"') + "\n"
    if a.check and not errs and (not OUT.is_file() or OUT.read_text(encoding="utf-8") != text): errs.append(f"{OUT.name} is out of date: run python tools/make_inventory.py")
    for e in errs: print("inventory:", e, file=sys.stderr)
    if errs: sys.exit(1)
    if not a.check: OUT.write_text(text, encoding="utf-8")
    print(f"{len(inv['applications'])} inventory entries -> {sum(shown(x) for x in inv['applications'])} browser entries ({sum(bool(x.get('hidden')) for x in inv['applications'])} hidden)" + (" (checked)" if a.check else f", {len(text)} bytes written"))


if __name__ == "__main__":
    main()
