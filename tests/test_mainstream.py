"""Run: python tests/test_mainstream.py  (no framework, no network). The mainstream seed list and the pure parts of discovery/mainstream.py."""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "discovery")); sys.path.insert(0, str(ROOT / "tools"))
import mainstream as M, categories as CAT

seeds = json.loads((ROOT / "discovery" / "mainstream.json").read_text(encoding="utf-8"))["apps"]
ids = [s["id"] for s in seeds]
assert len(ids) == len(set(ids)) and len(ids) >= 23
for s in seeds:
    assert s["group"] in CAT.GROUP_IDS and s["weight"] in M.WEIGHT, s["id"]
    for c in s["channels"]:
        assert c["kind"] in M.RESOLVE, (s["id"], c["kind"])
        if c["kind"] == "store": assert c["url"].startswith("https://"), s["id"]
        if c["kind"] == "github": assert re.fullmatch(r"[\w.-]+/[\w.-]+", c["repo"]) and c["pick"], s["id"]
        if c["kind"] != "store": re.compile(c["pick"])                      # every pattern compiles
# every app the request names is present (Beacon only as an unresolved seed)
for want in ("retroarch", "lemuroid", "duckstation", "nethersx2", "armsx2", "ppsspp", "vita3k", "mupen64plusfz", "melonds", "drastic", "azahar", "dolphin", "flycast", "redream",
             "yabasanshiro2", "snes9xexplus", "pizzaboy", "mame4droid", "winlator", "daijishou", "esde", "beacon", "pegasus"):
    assert want in ids, want
assert next(s for s in seeds if s["id"] == "beacon")["channels"] == []

# the catalog's own rule for a direct APK: a release download of the entry's OWN GitHub repository (never a store page, a mirror or another host)
assert M.release_ok("https://github.com/Swordfish90/Lemuroid", "https://github.com/Swordfish90/Lemuroid/releases/download/1.17.0/a.apk")
assert not M.release_ok("https://github.com/libretro/RetroArch", "https://buildbot.libretro.com/stable/1.22.2/android/RetroArch_aarch64.apk")
assert not M.release_ok("https://github.com/a/b", "https://github.com/c/d/releases/download/v1/x.apk")
assert not M.release_ok("", "https://github.com/a/b/releases/download/v1/x.apk")
assert not M.release_ok("https://github.com/a/b", "https://play.google.com/store/apps/details?id=x")

# version ordering picks the newest, numerically
assert sorted(["1.9.0", "1.22.2", "1.10.1"], key=M.vkey)[-1] == "1.22.2"
assert sorted(["downloads/duckstation-9999.apk", "downloads/duckstation-12126.apk"], key=M.vkey)[-1].endswith("12126.apk")
print("mainstream tests OK")
