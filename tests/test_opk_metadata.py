"""Run: python tests/test_opk_metadata.py  (no framework, no network, no OPK files)."""
import copy, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import opk_metadata as OM

# ---- Comment classes: only a real description may fill an empty description -----------------------------------------
cc = OM.classify_comment
assert cc("Native video player", "x", ["MPlayer"])[0] == "description"
assert cc("Needs bios.bin in $HOME/.3doh", "x", ["3DO!h"])[0] == "note" and cc("Needs pcfx.rom in $HOME/.pcfxemu", "x", [])[0] == "note"
assert cc("Modified", "x", ["PCSX Rearmed"])[0] == "note" and cc("", "x", [])[0] == "note"
for c, names in (("DOSBox Pure for Libretro", ["DOSBox Pure"]), ("Dinothawr v1.0 for Libretro", ["Dinothawr"]), ("Gambatte v0.5.0-netlink for Libretro", ["Gambatte"]),
                 ("MAME (0.37b5) for Libretro", ["MAME 2000"]), ("Final Burn Alpha (0.2.97.29) for Libretro", ["FBA 2012", "FinalBurn Alpha 2012"]),
                 ("Game Music Emu for Libretro", ["GME", "Game Music Emu"]), ("PocketCDG for Libretro", ["PocketCDG"])):
    assert cc(c, "x", names)[0] == "name-only", c                          # the app's own name is not a description
assert cc("EasyRPG Player", "wiki-easyrpg", ["EasyRPG"])[0] == "name-only"
for c, names in (("Commodore 64 emulator for Libretro", ["C64", "Commodore 64"]), ("PICO-8 Emulator (port gameblabla)", ["FAKE08"]), ("ST Terminal", ["ST-SDL", "ST"]),
                 ("SMS/GG/SG emulator", ["SMS Plus GX"]), ("Essential core pack for Libretro", ["SDLRetro"]), ("A remake of the dos Bips game", ["Blips"])):
    assert cc(c, "x", names)[0] == "description", c

# ---- enrich(): what it may and may not change ----------------------------------------------------------------------
rec = {"id": "t", "package": {"name": "T.opk", "size": 9, "sha256": "0" * 64, "identity": "medium: squashfs signature + recorded size"},
       "desktop": {"file": "t.desktop", "name": "Tee", "comment": "A tiny puzzle game", "categories": "games"},
       "icon": {"file": "t.png", "bytes": 100, "format": "PNG", "width": 32, "height": 32, "available": True}, "comment_class": "description"}
base = {"id": "t", "name": "T", "description": "", "topics": [], "category": "emulators", "category_basis": "Wiki heading not cached; by file name only: emulator by name",
        "approval": "unapproved", "hardware_test": "none"}
c = copy.deepcopy(base); OM.enrich(c, rec)
assert c["description"] == "A tiny puzzle game" and c["description_source"] == OM.SOURCE      # empty + descriptive: filled, with its source
assert c["category"] == "emulators" and c["name"] == "T" and c["approval"] == "unapproved"      # nothing else changes
assert c["category_basis"].endswith("; package differs") and len(c["category_basis"]) <= OM.BASIS_MAX
assert c["metadata_review"]["category"] == {"package": "games", "row": "Emulators", "applied": False}
assert c["metadata_review"]["name"] == {"package_name": "Tee", "listed": "T", "applied": False}   # a proposal, never applied
assert c["package_metadata"]["icon"]["available"] and c["package_metadata"]["category_evidence"]["verdict"] == "differs"
once = copy.deepcopy(c); OM.enrich(c, rec); assert c == once                                  # idempotent
OM.enrich(c, None); assert c == base                                                          # and fully removable
b2 = copy.deepcopy(base); b2["description"] = "Existing words"; OM.enrich(b2, rec)
assert b2["description"] == "Existing words" and "description_source" not in b2               # an existing description is never replaced
assert b2["metadata_review"]["description"]["package_comment"] == "A tiny puzzle game"        # a real difference is reported
b3 = copy.deepcopy(base); b3["description"] = "A tiny puzzle game, with extra words"; OM.enrich(b3, rec)
assert "description" not in b3.get("metadata_review", {})                                     # a richer version of the same sentence is no conflict
for cls in ("note", "name-only"):                                                              # a non-description never fills anything
    b4 = copy.deepcopy(base); r4 = dict(rec, comment_class=cls); OM.enrich(b4, r4)
    assert b4["description"] == "" and "description_source" not in b4
b5 = copy.deepcopy(base); b5.pop("category"); b5.pop("category_basis"); b5["name"] = "Game Box"; OM.enrich(b5, dict(rec, desktop=dict(rec["desktop"], categories="applications")))
assert "category" not in b5 and b5["package_metadata"]["category_evidence"]["verdict"] == "generic"   # derived row: evidence kept, no basis text invented
b6 = copy.deepcopy(base); b6["category"] = "games"; OM.enrich(b6, rec); assert b6["category_basis"].endswith("; package agrees")
long = copy.deepcopy(base); long["category_basis"] = "x" * 90; OM.enrich(long, rec); assert long["category_basis"] == "x" * 90   # never overflow the 95 characters the UI keeps

# ---- the word lists are the Nano UI's own ---------------------------------------------------------------------------
src = (ROOT / "ui" / "rh_model.c").read_text(encoding="utf-8")
for cat, tag in (("games", "RH_CAT_GAMES"), ("emulators", "RH_CAT_EMU"), ("media", "RH_CAT_MEDIA"), ("utilities", "RH_CAT_UTIL"), ("engines", "RH_CAT_ENGINE")):
    m = re.search(r"\[%s\] = \{([^}]*)\}" % tag, src)
    assert m and re.findall(r'"([a-z0-9]+)"', m.group(1)) == OM.KW[cat], cat
assert OM.derive_category("SuDokuL", "Multiplatform Sudoku game, made with C++/SDL2", ["game"]) == "games"
assert OM.derive_category("X", "A Sokoban engine", ["2d-game"]) == "other" and OM.derive_category("j2me", "phoneME-based J2ME runtime", []) == "engines"

# ---- the committed evidence and what it did to the committed snapshots ---------------------------------------------
E = json.loads((ROOT / "discovery" / "opk-metadata-evidence.json").read_text(encoding="utf-8"))["records"]
txt = (ROOT / "discovery" / "opk-metadata-evidence.json").read_text(encoding="utf-8").lower()
assert not any(x in txt for x in ("c:" + chr(92), "c:/", "/mnt/", "/home/", "downloads", "appdata", "opkreview", "scratchpad"))   # no local paths
O = json.loads((ROOT / "candidates" / "rg-nano.json").read_text(encoding="utf-8"))["candidates"]
W = json.loads((ROOT / "candidates" / "wiki-listings.json").read_text(encoding="utf-8"))["candidates"]
rows = {c["id"]: c for c in O + [w for w in W if "same_as" not in w]}                         # the browser's candidate rows
assert len(rows) == 54 and len(E) == 37 and len({r["id"] for r in E}) == 37 and {r["id"] for r in E} <= set(rows)
assert sorted(r["comment_class"] for r in E).count("description") == 25 and sorted(r["comment_class"] for r in E).count("note") == 3
for r in E:
    assert re.fullmatch(r"[0-9a-f]{64}", r["package"]["sha256"]) and r["package"]["identity"].split(":")[0] in ("high", "medium")
    assert r["icon"]["available"] and (r["icon"]["format"], r["icon"]["width"], r["icon"]["height"]) == ("PNG", 32, 32)
    assert set(r) <= {"id", "listed_as", "package", "desktop", "icon", "comment_class", "comment_reason", "display_comment", "display_comment_reason", "multiple_desktop_files"}   # no raw bytes, no paths
filled = [c for c in rows.values() if "description_source" in c]
assert len(filled) == 21 and all(c["description"] == c["package_metadata"].get("display_comment", c["package_metadata"]["comment"]) and c["package_metadata"]["comment_class"] == "description" for c in filled)
lame = rows["wiki-lameds"]                                                                    # the one maintainer edit: shown "NDS emulator", original Comment kept
assert lame["description"] == "NDS emulator" and lame["description_source"] == OM.SOURCE_EDITED and lame["package_metadata"]["comment"] == "Horrible NDS emulator"
assert [c["id"] for c in filled if c["description_source"] == OM.SOURCE_EDITED] == ["wiki-lameds"]
assert [r for r in E if r["id"] == "wiki-lameds"][0]["desktop"]["comment"] == "Horrible NDS emulator" and OM.DISPLAY["wiki-lameds"][0] == "NDS emulator"
assert sum("display_comment" in r for r in E) == 1
assert all(c["package_metadata"]["comment_class"] != "description" for c in rows.values() if "package_metadata" in c and c["description"] == "")   # no non-description was used
for c in rows.values():                                                                         # names, approvals, compatibility labels, categories stay as they were
    assert c["approval"] == "unapproved" and c["hardware_test"] == "none" and c["claim"]["kind"] in ("rg-nano", "family")
    if "name" in c.get("metadata_review", {}): assert c["metadata_review"]["name"]["listed"] == c["name"] and c["metadata_review"]["name"]["applied"] is False
    if "category" in c.get("metadata_review", {}): assert c["metadata_review"]["category"]["applied"] is False
    if "package_metadata" in c and c.get("category_basis"): assert len(c["category_basis"]) <= OM.BASIS_MAX
assert {c["id"]: c["category"] for c in O if "category" in c} == {"nanocraft": "games", "funkoban": "games", "picoarch": "emulators"}   # reviewed categories untouched
assert [c["name"] for c in O][:3] == ["j2me-funkey-rgnano", "NanoCraft", "Funkoban"]                                  # existing names kept

# ---- clean checkout: tracked files only, no build/ dir, no OPKs ----------------------------------------------------
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    for rel in ("tools/opk_metadata.py", "tools/make_candidate_snapshot.py", "discovery/opk-metadata-evidence.json", "candidates/rg-nano.json"):
        (t / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / rel, t / rel)
    r = subprocess.run([sys.executable, "-I", str(t / "tools" / "make_candidate_snapshot.py"), "--enrich-only"], capture_output=True, text=True, cwd=t)
    assert r.returncode == 0, r.stdout + r.stderr
    norm = lambda p: p.read_bytes().replace(b"\r\n", b"\n")
    assert norm(t / "candidates" / "rg-nano.json") == norm(ROOT / "candidates" / "rg-nano.json"), "rg-nano.json is not what the tracked evidence produces"
print("test_opk_metadata: ok")
