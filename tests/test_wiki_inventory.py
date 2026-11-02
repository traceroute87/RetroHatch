"""Run: python tests/test_wiki_inventory.py  (no framework, no network)."""
import json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_wiki_inventory as W

PAGE = W.PAGE
VIA = [{"anchor": "Download", "from": PAGE}]
LINK = [{"anchor": "Link", "from": PAGE}]


def pkg(url, name, via, **kw):
    return dict({"url": url, "name": name, "via": via, "kind": "direct", "repo": None, "size": 1000, "status": 206}, **kw)


# ---- synthetic crawl: every shape the real data has ----------------------------------------------------------------
res = {"packages": [
    pkg("https://static.miraheze.org/funkeywiki/a/Gambatte-V4.opk", "Gambatte-V4.opk", VIA, judgement="installable"),
    pkg("https://gitlab.com/g/-/raw/m/gambatte_funkey-s.opk", "gambatte_funkey-s.opk", LINK, judgement="false-positive", size=None, status=403),
    pkg("https://gitlab.com/g/-/raw/m/gambatte_funkey-s.opk?x", "gambatte_funkey-s.opk", LINK, judgement="false-positive", size=None, status=403),   # a second URL for one mirror
    pkg("https://static.miraheze.org/funkeywiki/b/Gambatte_%28SDL_Retro_Core%29.zip", "Gambatte_%28SDL_Retro_Core%29.zip", VIA, kind="zip-container", opks=0, entries=1),
    pkg("https://gitlab.com/g/-/raw/m/clock_app_funkey-s.opk", "clock_app_funkey-s.opk", LINK, judgement="false-positive", size=None, status=403),    # only link: unavailable
    pkg("https://static.miraheze.org/funkeywiki/c/Databases.zip", "Databases.zip", [{"anchor": "Databases folder", "from": PAGE}], kind="zip-container", opks=0),   # support file
    pkg("https://static.miraheze.org/funkeywiki/d/Dinothawr-V2.opk", "Dinothawr-V2.opk", VIA, judgement="installable"),
    pkg("https://static.miraheze.org/funkeywiki/d/Dinothawr.zip", "Dinothawr.zip", [{"anchor": "Game files", "from": PAGE}], kind="zip-container", opks=0),   # data of the listing above
    pkg("https://github.com/o/Znax/releases/latest/download/Znax.opk", "Znax.opk", LINK, judgement="installable", repo="o/Znax"),
    pkg("https://static.miraheze.org/funkeywiki/e/Other.opk", "Other.opk", [{"anchor": "x", "from": "https://example.org/not-the-wiki"}], judgement="installable"),   # not linked from the page
], "repos": [
    {"repo": "o/Znax", "meta": {"license": "MIT", "pushed_at": "2025-01-02T00:00:00Z"}, "release": "v1.0", "via": []},
    {"repo": "o/KeyKalc", "meta": {}, "via": [{"anchor": "Link", "from": PAGE}]},                                       # repo link, no package
], "unique_installable_apps": [{"url": "https://github.com/o/Znax/releases/download/v1.0/Znax.opk", "name": "Znax.opk", "repo": "o/Znax", "size": 4242}]}
existing = {"candidates": [{"id": "znax", "package": {"name": "Znax.opk"}}]}
with tempfile.TemporaryDirectory() as t:
    rf, ef = Path(t) / "r.json", Path(t) / "e.json"
    rf.write_text(json.dumps(res)); ef.write_text(json.dumps(existing))
    cands, support, unnamed = W.build([str(rf)], [], str(ef))
by = {c["name"]: c for c in cands}
assert unnamed == []
assert sorted(by) == ["Clock App", "Dinothawr", "Gambatte", "Gambatte (SDL Retro core)", "KeyKalc", "Znax"], sorted(by)   # support, data and unlinked files are not listings
assert [s["name"] for s in support] == ["Databases.zip"]
g = by["Gambatte"]                                                      # wiki OPK + gitlab mirror: one listing, mirror reported once
assert g["package"]["signature"] == "squashfs" and g["version"] == "V4" and g["listing"]["mirror"] == "gitlab.com: HTTP 403", g["listing"]["mirror"]
assert len(g["listing"]["urls"]) == 3   # the three URLs the page links to for this application
assert by["Clock App"]["package"]["signature"] == "" and by["Clock App"]["listing"]["download"] == "Unavailable (HTTP 403)"
assert by["Gambatte (SDL Retro core)"]["listing"]["download"].startswith("ZIP, not opened") and by["Gambatte (SDL Retro core)"]["package"]["signature"] == ""
assert by["KeyKalc"]["listing"]["download"] == "No file link crawled" and by["KeyKalc"]["repo"] == "o/KeyKalc"
z = by["Znax"]                                                          # `latest` alias pinned to the tag, license from repo metadata, matched to the existing candidate
assert z["package"]["url"].endswith("/releases/download/v1.0/Znax.opk") and z["package"]["size"] == 4242 and z["license"] == "MIT" and z["same_as"] == "znax"
for c in cands:                                                         # nothing here can look approved, tested or installable
    assert c["approval"] == "unapproved" and c["hardware_test"] == "none" and c["listing"]["wiki_category"] == "" and c["category_basis"]
    assert not ({"sha256", "install", "approved"} & set(c)) and c["category"] in W.CATS
assert W.ident("Mednafen_(NES_only).opk") == W.ident("Mednafen_%28NES_only%29.opk") and W.ident("pcsx_rearmed_ultimate.opk") == W.ident("PCSX_ReARMed_V2.opk")
assert W.ident("sdlretro_funkey-s.opk") == W.ident("SDL_Retro-V9.zip") == "sdlretro"

# ---- the committed inventory ---------------------------------------------------------------------------------------
d = json.loads((ROOT / "candidates" / "wiki-listings.json").read_text(encoding="utf-8"))
C = d["candidates"]
ids = [c["id"] for c in C]
assert len(ids) == len(set(ids)) == 46, len(ids)
assert sum("same_as" in c for c in C) == 2 and {c["same_as"] for c in C if "same_as" in c} == {"funkoban", "cglpsdl1"}
assert sum(bool(c["package"]["signature"]) for c in C) == 35 and sum(not c["package"]["signature"] for c in C) == 11
assert sum(c["listing"]["download"].startswith("Unavailable") for c in C) == 7 and sum(c["listing"]["download"] == "No file link crawled" for c in C) == 2
assert sorted(c["category"] for c in C).count("emulators") == 20 and all(c["category"] in W.CATS for c in C)
assert all(c["approval"] == "unapproved" and c["hardware_test"] == "none" and c["listing"]["source"] == "wiki" and c["listing"]["wiki_category"] == "" for c in C)
assert all(not ({"sha256", "install", "approved", "dest_name"} & set(c)) for c in C)
assert all(u.startswith("https://") for c in C for u in c["listing"]["urls"])
assert [s["name"] for s in d["support_files"]] == ["Databases.zip", "Machines.zip", "SquashFS.zip"]
# every candidate already shown still exists in the other source: nothing unique to either was removed
old = json.loads((ROOT / "candidates" / "rg-nano.json").read_text(encoding="utf-8"))["candidates"]
assert len(old) == 10 and all(c["id"] not in ids for c in old)
# the signed catalog side is untouched by this work
assert json.loads((ROOT / "catalog" / "approvals.json").read_text())["approvals"] == []
print("test_wiki_inventory: ok")
