"""Run: python tests/test_android_import.py  (no framework, no network). Relevance rules, deduplication, installability and verification judgement of discovery/android_import.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "discovery")); sys.path.insert(0, str(ROOT / "tools"))
import android_import as A

# relevance: evidence or nothing
assert A.classify("Lemuroid", "All in one emulator", ["Emulator"])[0] == "emulators"
assert A.classify("Termux", "Terminal emulator for Android", ["Emulator"]) is None                       # a terminal "emulator" is not a console emulator
assert A.classify("Graph 89", "TI-89 calculator emulator", ["Emulator"]) is None
assert A.classify("Blips", "A retro arcade puzzle game", ["Puzzle Game"])[0] == "games"
assert A.classify("Calm", "A relaxing coloring game", ["Casual Game"]) is None                          # no handheld evidence: not a candidate
assert A.classify("Pad Quest", "Platformer with gamepad support", ["Casual Game"])[0] == "games"
assert A.classify("OpenTTD", "Open source engine reimplementation of Transport Tycoon", ["Strategy Game"])[0] == "ports"
assert A.classify("Material Files", "File manager", ["File Manager"])[0] == "utilities"
assert A.classify("Clock", "A clock", ["Clock"]) is None
assert A.classify("LibreTube", "An alternative frontend for YouTube", ["Online Media Player"])[0] == "media"   # a "YouTube frontend" is a media client, not a game launcher
assert A.classify("Olauncher", "Minimal launcher", ["Launcher"])[0] == "themes-launchers"
assert A.classify("Suntimes", "Sunrise and sunshine times", ["Weather"]) is None
assert A.classify("Moonlight", "Open source game streaming client", ["Multimedia"])[0] == "media"

# installability comes from the manifest only
r = A.new(min_sdk=23, abis=["arm64-v8a", "x86"]); assert A.installable(r)[0] is True
assert A.installable(A.new(min_sdk=33, abis=[]))[0] is False                                              # Android 12 is API 31
assert A.installable(A.new(min_sdk=21, abis=["armeabi-v7a"]))[0] is True                                  # the Rotate lists armeabi-v7a (32-bit) in its abilist
assert A.installable(A.new(min_sdk=21, abis=["x86", "x86_64"]))[0] is False                               # x86 only: no usable ABI
assert A.installable(A.new(min_sdk=21, abis=[]))[0] is True                                                # pure Java
assert A.installable(A.new())[0] is None                                                                   # unknown stays unknown

# verification: a file, a package, a manifest and a licence, or it is only a lead
ok = A.new(package="a.b", apk_url="https://x/a.apk", min_sdk=24, abis=[], license="GPL-3.0", file_real=True, download_source="x"); A.judge(ok); assert ok["status"] == "verified" and ok["rotate_confidence"] == "manifest-installable"
nolic = A.new(package="a.b", apk_url="https://x/a.apk", min_sdk=24, abis=[], license="", file_real=True, download_source="x"); A.judge(nolic); assert nolic["status"] == "needs_verification" and "licence" in nolic["verification"][-1]
nomf = A.new(package="a.b", apk_url="https://x/a.apk", license="MIT", file_real=True, download_source="x"); A.judge(nomf); assert nomf["status"] == "needs_verification"
dead = A.new(package="a.b", apk_url="https://x/a.apk", min_sdk=24, abis=[], license="MIT", file_real=False, download_source="x"); A.judge(dead); assert dead["status"] == "needs_verification"
store = A.new(status="external_listing", name="Paid"); A.judge(store); assert store["status"] == "external_listing"      # never promoted to a download
nc = A.new(package="a.b", apk_url="https://x/a.apk", min_sdk=24, abis=[], license="CC-BY-NC-ND-4.0", file_real=True, download_source="x"); A.judge(nc); assert any("link only" in x for x in nc["restrictions"])

# deduplication: package id first, then upstream repository + name; distinct packages of different projects stay distinct
a = A.new(package="p.one", name="Dolphin Emulator", repo="https://github.com/dolphin-emu/dolphin", sources=["fdroid"], group="emulators")
b = A.new(package="p.one", name="Dolphin", sources=["izzy"], group="emulators")                               # same package id: folded
c = A.new(package="", name="Dolphin Emulator", repo="https://github.com/dolphin-emu/dolphin", sources=["obtainium"], group="emulators")   # a lead with the same upstream and name: folded
d = A.new(package="p.two", name="Dolphin MMJR", repo="https://github.com/other/mmjr", sources=["retrohandhelds-rotate"], group="emulators")   # a distinct fork: kept
keep, dups = A.dedupe([a, b, c, d])
assert sorted(x["package"] for x in keep) == ["p.one", "p.two"] and dups == 2, (keep, dups)
assert sorted(next(x for x in keep if x["package"] == "p.one")["sources"]) == ["fdroid", "izzy", "obtainium"]
g = A.new(package="", name="Flycast app", repo="https://github.com/flyinghead/flycast", sources=["rgc-guide"])          # a guide link is corroboration, not a candidate of its own
f = A.new(package="com.flycast.emulator", name="Flycast", repo="https://github.com/flyinghead/flycast", sources=["mainstream-seed"])
keep, dups = A.dedupe([f, g]); assert len(keep) == 1 and "rgc-guide" in keep[0]["sources"]
assert A.norm_name("Daijishō") == A.norm_name("Daijisho")
assert A.repo_id("https://github.com/Owner/Name.git") == "github:owner/name" and A.repo_id("https://f-droid.org/x") is None

print("android import tests OK")  # the remote manifest reader was cross-checked against aapt2 on real APKs (Lemuroid: minSdk 23; ARMSX2: minSdk 30), not with a synthetic file
