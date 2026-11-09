"""Run: python tests/test_search.py  (no framework, no network). Category mapping, deduplication, compatibility filtering, release-change detection and the grouped
candidate report of discovery/categories.py, search.py and review.py."""
import json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "discovery")); sys.path.insert(0, str(ROOT / "tools"))
import categories as CAT, search as S, review as R

# ---- categories: one primary group, tags, legacy mapping --------------------------------------------------------------------
assert CAT.GROUP_IDS == ["games", "emulators", "ports", "utilities", "media", "themes-launchers"]
assert CAT.classify("Lemuroid", "All in one emulator on Android!", ["libretro", "emulator"])[0] == "emulators"
assert CAT.classify("Pegasus", "A graphical frontend for launching emulators", ["frontend"])[0] == "themes-launchers"
assert CAT.classify("Material Files", "Material Design file manager")[0] == "utilities"
assert CAT.classify("NewPipe", "A libre lightweight streaming front-end for Android")[0] == "media"
assert CAT.classify("Blips", "A puzzle game")[0] == "games"
assert CAT.classify("xash", "a port of xash 3d engine")[0] == "ports"
assert CAT.classify("x", "", legacy="engines") == ("ports", "legacy")              # Nano inventory ids map onto the same groups
assert CAT.classify("x", "", legacy="media") == ("media", "legacy")
assert CAT.classify("zzz", "qqq") == ("utilities", "low")                           # a guess says so
assert CAT.make_tags(["android", "Kotlin", "2fa", "retro-handheld", "2fa", "x"]) == ["2fa", "retro-handheld"]   # generic and duplicate topics drop out
assert CAT.present(["media", "games", "media"]) == ["games", "media"]               # only groups that hold entries, fixed order

# ---- the repository/release records ------------------------------------------------------------------------------------------
def repo(full, desc="", topics=(), lic="MIT", **kw):
    r = {"full_name": full, "name": full.split("/")[1], "html_url": "https://github.com/" + full, "description": desc, "topics": list(topics), "stargazers_count": 10,
         "license": {"spdx_id": lic} if lic else None, "pushed_at": "2026-10-01T00:00:00Z", "created_at": "2024-01-01T00:00:00Z", "owner": {"login": full.split("/")[0]}}
    r.update(kw); return r

def rel(tag, *names, pre=False):
    return {"tag_name": tag, "published_at": "2026-10-02T00:00:00Z", "html_url": "https://x/r", "prerelease": pre, "assets": [{"name": n, "size": 1000, "browser_download_url": "https://x/" + n} for n in names]}

def art(asset, real=True, member=None, others=0):
    return {"asset": {"name": asset, "size": 1000, "browser_download_url": "https://x/" + asset}, "member": member, "real": real, "others": others}

README = ("# App\nRuns on the Anbernic RG Rotate.", "https://r")
good = S.build("rg-rotate", repo("a/good", "An emulator", ["emulator"]), rel("v1", "good-arm64-v8a.apk"), True, README, 2, art("good-arm64-v8a.apk"))
assert good["group"] == "emulators" and good["compat"]["level"] == "claimed" and good["flags"] == [] and good["artifact"]["abi_hint"] == "arm64"
assert good["compat"]["level"] != "tested"                                           # discovery never says tested

# a filename that names a device proves nothing; no support sentence = no claim
nm = S.build("rg-rotate", repo("a/named", "tool"), rel("v1", "tool-for-rg-rotate.apk"), True, None, 1, art("tool-for-rg-rotate.apk"))
assert nm["compat"]["level"] == "none"

# real-file check: a "download" that is not an APK/OPK is flagged, not trusted
fake = S.build("rg-rotate", repo("a/fake", "x"), rel("v1", "a.apk"), True, None, 1, art("a.apk", real=False))
assert "not-a-real-apk" in fake["flags"]
assert "file-unreachable" in S.build("rg-nano", repo("a/o", "x"), rel("v1", "a.opk"), True, None, 1, art("a.opk", real=None))["flags"]
assert "no-apk-in-release" in S.build("rg-rotate", repo("a/n", "x"), rel("v1", "a.zip"), True, None, 1, None)["flags"]
assert "no-release" in S.build("rg-rotate", repo("a/r", "x"), None, True, None, 1, None)["flags"]
assert "opk-inside-zip" in S.build("rg-nano", repo("a/z", "x"), rel("v1", "pack.zip"), True, None, 1, art("pack.zip", member="g.opk"))["flags"]

# maintenance flags
f = S.build("rg-rotate", repo("a/old", "", lic=None, pushed_at="2020-01-01T00:00:00Z", archived=True, fork=True), rel("v1", "a-debug.apk", pre=True), False, None, 1, art("a-debug.apk"))["flags"]
assert {"abandoned", "archived", "missing-license", "missing-description", "fork", "pre-release-only", "debug-or-nightly-build"} <= set(f), f
assert "not-arm64" in S.build("rg-rotate", repo("a/x86", "x"), rel("v1", "a-x86_64.apk"), True, None, 1, art("a-x86_64.apk"))["flags"]
assert "list-not-an-app" in S.build("rg-rotate", repo("a/awesome-foo", "awesome list"), None, True, None, 1, None)["flags"]

# compatibility filtering: an explicit "not compatible" sets the project aside; on Android another handheld's name is NOT incompatibility, for an OPK it is
neg = S.build("rg-rotate", repo("a/neg", "x"), rel("v1", "a.apk"), True, ("This app is not compatible with the RG Rotate.", "https://r"), 1, art("a.apk"))
assert "compat-incompatible" in neg["flags"]
other_apk = S.build("rg-rotate", repo("a/oth", "Retro launcher for Miyoo and Retroid"), rel("v1", "a.apk"), True, None, 1, art("a.apk"))
assert "compat-other_device" not in other_apk["flags"]
other_opk = S.build("rg-nano", repo("a/oth2", "Port for Miyoo Mini"), rel("v1", "a.opk"), True, ("Also see RG Nano.", "https://r"), 1, art("a.opk"))
assert "compat-other_device" in other_opk["flags"]

# ranking: explicit support + a real, licensed, maintained file beats a bare repository
bare = S.build("rg-rotate", repo("a/bare", "x", lic=None), None, True, None, 1, None)
assert good["score"] > nm["score"] > bare["score"], (good["score"], nm["score"], bare["score"])

# a download whose name has nothing to do with the project, and lists that are not apps
import discover as D0
assert "release-name-mismatch" in D0.suspicious_flags({"name": "best_shizuku_apps_for_android", "owner": "krishna", "artifact": {"name": "ZYRAXON-v6.24.1.apk"}, "description": ""})
assert D0.suspicious_flags({"name": "pocketvibe", "owner": "cobanov", "artifact": {"name": "PocketVibe-0.7.4.apk"}, "description": "x"}) == []
assert "list-not-an-app" in D0.suspicious_flags({"name": "best_shizuku_apps", "owner": "k", "artifact": None, "description": ""})
assert "list-not-an-app" in D0.suspicious_flags({"name": "x", "owner": "k", "artifact": None, "description": "A curated list of apps"})

# ---- deduplication: fork -> parent, look-alike mirrors, aliases ------------------------------------------------------------
parent = S.build("rg-rotate", repo("up/tool", "Great tool", stargazers_count=500), rel("v2", "t.apk"), True, None, 3, art("t.apk"))
fork = S.build("rg-rotate", repo("me/tool", "Great tool", stargazers_count=3, fork=True), rel("v2", "t.apk"), True, None, 1, art("t.apk"))
fork["fork"] = {"parent": "up/tool"}
mirror = S.build("rg-rotate", repo("other/Tool", "Great tool", stargazers_count=1), rel("v2", "t.apk"), True, None, 1, art("t.apk"))
unrelated = S.build("rg-rotate", repo("x/different", "Something else"), rel("v1", "d.apk"), True, None, 1, art("d.apk"))
out = S.dedupe([fork, mirror, unrelated, parent])
names = [c["repo"] for c in out]
assert sorted(names) == ["up/tool", "x/different"], names
assert sorted(next(c for c in out if c["repo"] == "up/tool")["aliases"]) == ["me/tool", "other/Tool"]

# ---- the report: one group per candidate, rejected stay quiet, changed releases resurface ------------------------------------
def cand(c, known=False): c["known"] = known; return c
a_new = cand(good)
a_missing = cand(S.build("rg-rotate", repo("m/nolic", "x", lic=None), rel("v1", "m.apk"), True, None, 1, art("m.apk")))
a_aside = cand(neg)
a_rej = cand(S.build("rg-rotate", repo("r/rejected", "x"), rel("v1", "r.apk"), True, None, 1, art("r.apk")))
a_rej_changed = cand(S.build("rg-rotate", repo("r/again", "x"), rel("v9", "r.apk"), True, None, 1, art("r.apk")))
a_upd = cand(S.build("rg-rotate", repo("u/updated", "x"), rel("v3", "u.apk"), True, None, 1, art("u.apk")))
a_seen = cand(S.build("rg-rotate", repo("s/seen", "x"), rel("v1", "s.apk"), True, None, 1, art("s.apk")))
state = {"schema": 1, "repos": {"r/rejected": {"status": "rejected", "reason": "closed source", "release_tag": "v1"},
                                "r/again": {"status": "rejected", "reason": "closed source", "release_tag": "v1"},
                                "u/updated": {"status": "seen", "release_tag": "v2"}, "s/seen": {"status": "seen", "release_tag": "v1"}}}
g = R.classify_candidates("rg-rotate", [a_new, a_missing, a_aside, a_rej, a_rej_changed, a_upd, a_seen], state, {})
assert [c["repo"] for c in g["new"]] == ["a/good"]
assert [c["repo"] for c in g["missing"]] == ["m/nolic"]
assert [c["repo"] for c in g["aside"]] == ["a/neg"]
assert [c[0]["repo"] for c in g["reviewed"]] == ["r/rejected"]                    # rejected and unchanged: one quiet line, not a re-pitch
assert sorted(c["repo"] for c in g["updated"]) == ["r/again", "u/updated"]        # a real change (a new release) brings it back
assert [c["repo"] for c in g["testing"]] == ["s/seen"]                            # seen before, real file: next step is a device test
assert R.tag_norm("v1.2.0") == R.tag_norm("1.2.0")
# an inventory entry whose version changed counts as updated
inv = {"q/inv": {"version": "1.0.0", "status": "package-verified", "license": "MIT", "has_file": True, "group": "games", "name": "Inv", "url": "u", "hold": None, "hidden": None, "tags": []}}
c_inv = cand(S.build("rg-rotate", repo("q/inv", "x"), rel("v1.1.0", "i.apk"), True, None, 1, art("i.apk")), True)
assert [c["repo"] for c in R.classify_candidates("rg-rotate", [c_inv], {"repos": {}}, inv)["updated"]] == ["q/inv"]

# full report renders from files, and --update-state records first/last seen without approving anything
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    for dev in ("rg-nano", "rg-rotate"):
        (t / f"candidates-{dev}.json").write_text(json.dumps({"candidates": [a_new] if dev == "rg-rotate" else [], "errors": [], "requests": 5, "generated": "2026-11-09"}))
    md, js, dg = R.report(t, {"schema": 1, "repos": {}})
    assert "## RG Rotate (Android, APK)" in md and "[a/good](https://github.com/a/good)" in md and "New candidates (1)" in md and "| Device |" in md
    assert js["rg-rotate"]["new"] == ["a/good"] and len(dg) == 16
    st = {"schema": 1, "repos": {}}; R.update_state(t, st)
    assert st["repos"]["a/good"]["status"] == "seen" and st["repos"]["a/good"]["release_tag"] == "v1"
    assert R.classify_candidates("rg-rotate", [a_new], st, {})["new"] == []        # reported once; next time it is no longer "new"

print("search tests OK")
