#!/usr/bin/env python3
"""Offline inventory of the software the FunKey wiki page "List of third-party OPK applications" links to.

Reads only files that already exist on disk (crawl results and package leads); makes no request, never touches catalog/, approvals or keys.
The crawler kept the page's LINKS (anchor + target) but not its text, so wiki category headings and descriptions are NOT in the local data:
every entry says so ("wiki_category": ""), and its RetroHatch category comes from the file name alone, with that basis written next to it.
An application that the page lists without a file link we crawled is absent from this inventory; the report says so instead of guessing.

  python tools/make_wiki_inventory.py --results A.json B.json ... --leads L.json ... [--existing candidates/rg-nano.json]
         [--out candidates/wiki-listings.json] [--md docs/WIKI_LISTINGS_INVENTORY.md]
"""
import argparse, collections, json, re, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = "https://wiki.funkey-project.com/wiki/List_of_third-party_OPK_applications"
KEY = "List_of_third-party_OPK_applications"
CATS = ("games", "emulators", "media", "utilities", "engines", "other")

# identity key -> (display name, category, why). Category rests on the name alone: the wiki heading is not cached.
NAMES = {
    "3doh": ("3DOh", "emulators", "3DO emulator by name"), "commodore64": ("Commodore 64", "emulators", "C64 machine by name"),
    "dosboxpure": ("DOSBox Pure", "emulators", "DOSBox by name"), "dinothawr": ("Dinothawr", "games", "title"),
    "easyrpg": ("EasyRPG", "engines", "RPG Maker player: runtime by name"), "fake08": ("Fake-08", "emulators", "PICO-8 player by name"),
    "finalburnalpha2012": ("FinalBurn Alpha 2012", "emulators", "arcade emulator by name"), "finalburnneo": ("FinalBurn Neo", "emulators", "arcade emulator by name"),
    "gambatte": ("Gambatte", "emulators", "Game Boy emulator by name"), "gamemusicemu": ("Game Music Emu", "media", "music player by name"),
    "ganbarenatuskian": ("Ganbare Natuskian", "games", "title"), "gnash": ("Gnash", "engines", "Flash player: runtime by name"),
    "lameds": ("LameDS", "other", "name does not say"), "mame2000": ("MAME 2000", "emulators", "arcade emulator by name"),
    "mednafennesonly": ("Mednafen (NES only)", "emulators", "Mednafen emulator by name"), "mplayer": ("MPlayer", "media", "media player by name"),
    "pcfxemu": ("PC-FX Emu", "emulators", "emulator by name"), "pcsxrearmed": ("PCSX ReARMed", "emulators", "PlayStation emulator by name"),
    "picodrive": ("PicoDrive", "emulators", "Mega Drive emulator by name"), "piemu": ("Piemu", "other", "name does not say"),
    "pocketcdg": ("Pocket CDG", "media", "CD+G karaoke player by name"), "pokemini": ("PokeMini", "emulators", "Pokemon Mini emulator by name"),
    "sdlretro": ("SDL Retro", "emulators", "libretro frontend by name"), "smsplus": ("SMS Plus", "emulators", "Master System emulator by name"),
    "st": ("ST", "other", "name does not say"), "swanemu": ("SwanEmu", "emulators", "WonderSwan emulator by name"),
    "vbanext": ("VBA Next", "emulators", "Game Boy Advance emulator by name"), "vbemu": ("VBEmu", "emulators", "Virtual Boy emulator by name"),
    "gambattesdlretrocore": ("Gambatte (SDL Retro core)", "emulators", "core for SDL Retro by name"),
    "vicesdlretrocore": ("VICE (SDL Retro core)", "emulators", "Commodore emulator core by name"),
    "blips": ("Blips", "games", "title"), "blockdude": ("Blockdude", "games", "title"), "formula1": ("Formula1", "games", "title"),
    "funkoban": ("Funkoban", "games", "title"), "rubido": ("Rubido", "games", "title"), "znax": ("Znax", "games", "title"),
    "cglpsdl1": ("Cglpsdl1", "other", "name does not say"),
    "clockapp": ("Clock App", "utilities", "clock by name"), "dividead": ("Dividead", "other", "name does not say"),
    "heboris": ("Heboris", "other", "name does not say"), "ncrafti": ("NCrafti", "other", "name does not say"),
    "srb2": ("SRB2", "other", "name does not say"), "stk": ("STK", "other", "name does not say"),
    "worshipvector": ("Worship Vector", "other", "name does not say"),
    "gmenu2x": ("GMenu2X", "utilities", "menu launcher by name"), "keykalc": ("KeyKalc", "utilities", "calculator by name"),
}
ALIAS = {"pcsxrearmedultimate": "pcsxrearmed"}   # an "ultimate" build of the same emulator: a version, not a second application
SUPPORT = {"databases": "data folder", "machines": "data folder", "squashfs": "tool (mksquashfs) archive"}   # linked from the page, not applications
# a ZIP "Game files" link is data for the game of the same name, not a listing of its own
DATA_FOR = {"dinothawr"}


def ident(fn):
    s = urllib.parse.unquote(fn).lower()
    s = re.sub(r"\.(opk|zip)$", "", s)
    s = re.sub(r"[_-]?funkey[_-]?s?$", "", s)
    s = re.sub(r"[_-]v\d+$", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return ALIAS.get(s, s)


def version_of(fn):
    m = re.search(r"[_-](v\d+)\.(?:opk|zip)$", urllib.parse.unquote(fn), re.I)
    return m.group(1).upper() if m else ""


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def collect(results, leads):
    """url -> merged package facts, for every package row whose provenance includes the wiki list page"""
    rows = {}
    def put(p, anchors):
        e = rows.setdefault(p["url"], {"url": p["url"], "name": p.get("name"), "host": p["url"].split("/")[2], "repo": p.get("repo"), "anchors": set(),
                                       "magic": False, "fp": False, "size": None, "status": set(), "opks": None, "entries": None, "kind": p.get("kind")})
        e["anchors"] |= anchors
        j = p.get("judgement") or ("installable" if p.get("state") == "verified" else None)
        e["magic"] |= j == "installable"; e["fp"] |= j == "false-positive"
        if p.get("size"): e["size"] = p["size"]
        if p.get("status") is not None: e["status"].add(p["status"])
        if p.get("opks") is not None: e["opks"] = p["opks"]; e["entries"] = p.get("entries")
        if p.get("repo") and not e["repo"]: e["repo"] = p["repo"]
    for f in results:
        for p in load(f)["packages"]:
            a = {v.get("anchor") for v in p.get("via", []) if KEY in v.get("from", "")}
            if a: put(p, a)
    for f in leads:
        for u, v in load(f).items():
            a = {x.get("anchor") for x in v.get("via", []) if KEY in x.get("from", "")}
            if a: put(dict(v, url=u), a)
    return rows


def tagged(results):
    """file name -> repo-tagged release URL (the wiki links `releases/latest/download`, which moves)"""
    t = {}
    for f in results:
        for u in load(f).get("unique_installable_apps", []):
            if "/releases/download/" in u["url"] and u.get("repo"): t.setdefault((u["repo"], u["name"].lower()), (u["url"], u.get("size")))
    return t


def repo_meta(results):
    m = {}
    for f in results:
        for r in load(f)["repos"]:
            if (r.get("meta") or {}) and r["repo"] not in m: m[r["repo"]] = r
    return m


def listed_repos(results):
    """repositories the page links to directly (no package file): repo -> anchors"""
    out = {}
    for f in results:
        for r in load(f)["repos"]:
            a = {v.get("anchor") for v in r.get("via", []) if KEY in v.get("from", "")}
            if a: out.setdefault(r["repo"], set()).update(a)
    return out


def build(results, leads, existing_path):
    rows = collect(results, leads); tag = tagged(results); meta = repo_meta(results)
    groups = collections.defaultdict(list); support = []
    for r in rows.values():
        k = ident(r["name"])
        if k in SUPPORT: support.append(r); continue
        groups[k].append(r)
    existing = {}
    if existing_path and Path(existing_path).is_file():
        for c in load(existing_path)["candidates"]: existing[ident(c["package"]["name"])] = c
    out = []; unlisted_note = []
    for k, rs in sorted(groups.items(), key=lambda kv: NAMES.get(kv[0], (kv[0],))[0].lower()):
        if k in DATA_FOR and all(r["name"].lower().endswith(".zip") for r in rs): continue   # data for another listing
        name, cat, why = NAMES.get(k, (None, "other", "name does not say"))
        if name is None: name = rs[0]["name"]; unlisted_note.append(k)
        opks = [r for r in rs if r["name"].lower().endswith(".opk") and r["magic"]]
        gl = [r for r in rs if r["host"] == "gitlab.com"]
        primary = next((r for r in opks if r["host"] != "gitlab.com"), None)
        if primary is None: primary = opks[0] if opks else None
        zips = [r for r in rs if r["name"].lower().endswith(".zip")]
        shown = primary or (gl[0] if gl else zips[0])
        repo = shown["repo"] or ""
        url, size = shown["url"], shown["size"]
        if repo and (repo, shown["name"].lower()) in tag: url, size = tag[(repo, shown["name"].lower())]
        sig = bool(primary and primary["magic"])
        if primary: dl = "Found (squashfs seen)"
        elif gl and gl[0]["fp"]: dl = "Unavailable (HTTP %s)" % ",".join(map(str, sorted(gl[0]["status"]))) if gl[0]["status"] else "Unavailable"
        elif zips: dl = "ZIP, not opened" + (" (%s entries)" % zips[0]["entries"] if zips[0]["entries"] is not None else "")
        else: dl = "No file link crawled"
        mirrors = [r for r in rs if r is not shown and r["name"].lower().endswith(".opk") and r["host"] != shown["host"]]
        mirror = "; ".join(sorted({"%s: %s" % (r["host"], "HTTP %s" % ",".join(map(str, sorted(r["status"]))) if r["fp"] and r["status"] else "found") for r in mirrors}))
        m = meta.get(repo, {}).get("meta", {}) if repo else {}
        ex = existing.get(k)
        c = {"id": "wiki-" + k, "name": name, "description": "", "topics": [], "version": version_of(shown["name"]) or (meta.get(repo, {}).get("release") or "" if repo else ""),
             "repo": repo, "source": ("https://github.com/" + repo) if repo and shown["host"] == "github.com" else PAGE,
             "license": m.get("license") or "unknown", "last_activity": (m.get("pushed_at") or "")[:10],
             "package": {"name": urllib.parse.unquote(shown["name"]), "url": url, "size": size or 0, "format": "opk" if shown["name"].lower().endswith(".opk") else "zip",
                         "signature": "squashfs" if sig else "", "container": "zip" if shown["name"].lower().endswith(".zip") else "", "more_packages": 0},
             "claim": {"kind": "family", "text": "Listed on the FunKey wiki page of third-party OPK applications", "where": "wiki"},
             "category": cat, "category_basis": "Wiki heading not cached; by file name only: " + why,
             "hardware_test": "none", "approval": "unapproved",
             "listing": {"source": "wiki", "page": PAGE, "wiki_category": "", "download": dl, "mirror": mirror,
                         "anchors": sorted({a for r in rs for a in r["anchors"] if a}), "urls": sorted({r["url"] for r in rs})}}
        if ex: c["same_as"] = ex["id"]
        out.append(c)
    for repo, anchors in sorted(listed_repos(results).items()):
        k = ident(repo.split("/")[1])
        if k in groups or repo.lower() == "drum78/drum78": continue
        name, cat, why = NAMES.get(k, (repo.split("/")[1], "other", "name does not say"))
        out.append({"id": "wiki-" + k, "name": name, "description": "", "topics": [], "version": "", "repo": repo, "source": "https://github.com/" + repo, "license": "unknown",
                    "last_activity": "", "package": {"name": "", "url": "", "size": 0, "format": "", "signature": "", "container": "", "more_packages": 0},
                    "claim": {"kind": "family", "text": "Listed on the FunKey wiki page of third-party OPK applications", "where": "wiki"},
                    "category": cat, "category_basis": "Wiki heading not cached; by file name only: " + why, "hardware_test": "none", "approval": "unapproved",
                    "listing": {"source": "wiki", "page": PAGE, "wiki_category": "", "download": "No file link crawled", "mirror": "", "anchors": sorted(a for a in anchors if a), "urls": ["https://github.com/" + repo]}})
    out.sort(key=lambda c: c["name"].lower())
    return out, support, unlisted_note


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", nargs="+", required=True); ap.add_argument("--leads", nargs="*", default=[])
    ap.add_argument("--existing", default=str(ROOT / "candidates" / "rg-nano.json"))
    ap.add_argument("--out", default=str(ROOT / "candidates" / "wiki-listings.json")); ap.add_argument("--md", default=None)
    a = ap.parse_args()
    cands, support, unnamed = build(a.results, a.leads, a.existing)
    if unnamed: sys.exit("no display name for: %s (add to NAMES)" % unnamed)
    doc = {"schema": 1, "device": "rg-nano", "status": "UNAPPROVED wiki listings, read-only; not part of the signed catalog",
           "from": {"page": PAGE, "inputs": len(a.results) + len(a.leads),
                    "note": "Link targets only. The page text (category headings, descriptions) was not cached by the crawler."},
           "support_files": [{"name": urllib.parse.unquote(r["name"]), "url": r["url"], "anchors": sorted(x for x in r["anchors"] if x), "role": SUPPORT[ident(r["name"])]} for r in sorted(support, key=lambda r: r["name"])],
           "candidates": cands}
    Path(a.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    n = len(cands); same = sum("same_as" in c for c in cands)
    ver = sum(bool(c["package"]["signature"]) for c in cands)
    cc = collections.Counter(c["category"] for c in cands)
    print(f"{n} listings, {same} already shown, {n - same} new, {ver} package-verified, {n - ver} not verified, {len(support)} support files")
    print(dict(cc))
    if a.md: Path(a.md).write_text(render_md(doc), encoding="utf-8")


def render_md(doc):
    c = doc["candidates"]; n = len(c); same = sum("same_as" in x for x in c); ver = sum(bool(x["package"]["signature"]) for x in c)
    cc = collections.Counter(x["category"] for x in c)
    L = ["# FunKey wiki listings recovered from local data", "",
         "Generated by `tools/make_wiki_inventory.py` (offline). Page: <%s>." % PAGE, "",
         "## Coverage is partial: read this first", "",
         "- The crawler kept the page's **link targets, not its text**. The wiki's original category headings and descriptions are **missing** from every local file. Every entry carries `wiki_category: \"\"`, and the Nano UI shows \"Wiki category: Not recorded\". None was invented.",
         "- The %d entries are the applications whose links the crawler followed. An application the page lists without such a link is **not here**, so %d is a floor, not the page's total. Full coverage is not claimed." % (len(doc["candidates"]), len(doc["candidates"])),
         "- The RetroHatch category column is **not** the wiki's heading. It is a filter bucket picked from the file name alone, and each entry says so in its basis line (`Wiki heading not cached; by file name only: ...`). %d entries whose names say nothing stay `Other`. Re-derive all of them from the real headings once the page text is available." % sum(x["category"] == "other" for x in doc["candidates"]),
         "- Inputs were crawl results and package leads on this machine, including an earlier session's artifacts that are not in the repository, so the generator cannot be re-run from a clean checkout. The committed `candidates/wiki-listings.json` is the record.",
         "- \"Package verified\" means a squashfs signature was seen. It says nothing about safety or compatibility. Every entry is UNAPPROVED, hardware-untested and read-only in the UI.", "",
         "| Measure | Count |", "|---|---|", "| Distinct listings recovered | %d |" % n, "| Already shown among the 10 discovered candidates | %d |" % same,
         "| Newly represented | %d |" % (n - same), "| Package verified (squashfs seen) | %d |" % ver, "| Not verified | %d |" % (n - ver),
         "| Support files linked, not counted as applications | %d |" % len(doc["support_files"]), "", "| Category (name-based) | Count |", "|---|---|"]
    names = {"games": "Games", "emulators": "Emulators", "media": "Media", "utilities": "Utilities", "engines": "Engines & Tools", "other": "Other"}
    L += ["| %s | %d |" % (names[k], cc.get(k, 0)) for k in CATS]
    L += ["", "| Application | Category | Package | Download | Source link | Also |", "|---|---|---|---|---|---|"]
    for x in c:
        p = x["package"]; l = x["listing"]
        L.append("| %s%s | %s | %s | %s | %s | %s |" % (x["name"], " (also in 10)" if "same_as" in x else "", names[x["category"]], p["name"] or "none",
                  l["download"], (x["repo"] or (p["url"] or l["urls"][0]).split("/")[2]), l["mirror"] or ""))
    L += ["", "Support files (linked from the page, not applications): " + ", ".join("%s (%s)" % (s["name"], s["role"]) for s in doc["support_files"]), ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
