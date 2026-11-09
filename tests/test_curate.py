"""Run: python tests/test_curate.py  (no framework, no network). The install-vs-external decision of discovery/curate.py and the committed candidates/android-curated.json."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "discovery")); sys.path.insert(0, str(ROOT / "tools"))
import curate as C, android_import as A, mainstream as M

def rec(**k):
    base = dict(A.new(package="a.b", name="Tool", repo="https://github.com/o/tool", official_url="https://github.com/o/tool", license="GPL-3.0", status="verified", version="1.0",
                      apk_url="https://github.com/o/tool/releases/download/v1/t.apk", apk_size=1000, sources=["fdroid"]))
    base.update(k); return base

# direct install only when EVERY policy condition holds
assert C.eligible(rec())[0] is True
assert C.eligible(rec(apk_url="https://f-droid.org/repo/a.b_1.apk"))[0] is True                         # F-Droid repository file of a package in the verified index
assert C.eligible(rec(apk_url="https://mirror.example/a.apk", repo="https://example.org/tool", official_url="https://example.org/tool"))[0] is False   # an unknown host stays external
ok, why = C.eligible(rec(package="com.retroarch.aarch64", apk_url="https://buildbot.libretro.com/stable/1.22.2/android/RetroArch_aarch64.apk")); assert ok is None
ok, why = C.eligible(rec(license="CC-BY-NC-ND-4.0")); assert ok is False and "forbids redistribution" in why
ok, why = C.eligible(rec(license="")); assert ok is False and "No licence" in why
ok, why = C.eligible(rec(license="proprietary")); assert ok is False
ok, why = C.eligible(rec(version="continuous")); assert ok is False and "Rolling" in why
ok, why = C.eligible(rec(apk_size=300 * 1024 * 1024)); assert ok is False and "200 MB" in why or "larger" in why
ok, why = C.eligible(rec(status="needs_verification")); assert ok is False
ok, why = C.eligible(rec(apk_url="")); assert ok is False
ok, why = C.eligible(rec(status="external_listing", notes="Paid.")); assert ok is False and why == "Paid."
assert M.release_ok("https://github.com/o/tool", "https://github.com/o/tool/releases/download/v1/t.apk")
assert not M.release_ok("https://github.com/o/tool", "https://github.com/o/other/releases/download/v1/t.apk")

# the sources: same rules as the app (android/.../TrustedSources.kt), pinned official servers identical in code and data, repositories pinned by certificate
import re
kt = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "app" / "retrohatch" / "rotate" / "model" / "TrustedSources.kt").read_text(encoding="utf-8")
assert dict(re.findall(r'"([\w.]+)" to "(https://[^"]+)"', kt)) == C.OFFICIAL, "official servers differ between TrustedSources.kt and discovery/trusted_sources.json"
assert C.source_kind("https://github.com/o/r", "https://github.com/o/r/releases/download/v1/a.apk", "a.b", 7) == "github"
assert C.source_kind("https://gitlab.com/g/p", "https://gitlab.com/g/p/-/releases/v1/downloads/a.apk", "a.b", 7) == "gitlab"
assert C.source_kind("https://gitlab.com/g/p", "https://gitlab.com/other/p/-/releases/v1/downloads/a.apk", "a.b", 7) is None
assert C.source_kind("https://codeberg.org/o/r", "https://codeberg.org/o/r/releases/download/v1/a.apk", "a.b", 7) == "codeberg"
assert C.source_kind("https://x.org", "https://f-droid.org/repo/a.b_7.apk", "a.b", 7) == "fdroid" and C.source_kind("https://x.org", "https://f-droid.org/repo/a.b_8.apk", "a.b", 7) is None
assert C.source_kind("https://x.org", "https://apt.izzysoft.de/fdroid/repo/a.b_7.apk", "a.b", 7) == "izzy"
assert C.source_kind("https://x.org", "https://mirror.example/fdroid/repo/a.b_7.apk", "a.b", 7) is None and C.source_kind("https://x.org", "http://f-droid.org/repo/a.b_7.apk", "a.b", 7) is None
assert C.source_kind("https://x.org", "https://www.ppsspp.org/files/1_20_4/ppsspp.apk", "org.ppsspp.ppsspp", 1) == "official" and C.source_kind("https://x.org", "https://www.ppsspp.org/files/../x.apk", "org.ppsspp.ppsspp", 1) is None
assert set(C.PINS["repos"]) == {"fdroid", "izzy"} and all(len(v["fingerprint_sha256"].split(":")) == 32 for v in C.PINS["repos"].values())

# external listings link to a real page and never to a download
e = C.external_for(rec(sources=["fdroid"]), "reason"); assert e["label"] == "F-Droid" and e["url"] == "https://f-droid.org/packages/a.b/" and e["price"] is None
e = C.external_for(rec(sources=["izzy"]), "r"); assert e["label"] == "IzzyOnDroid"
e = C.external_for(rec(sources=["mainstream-seed"], official_url="https://play.google.com/store/apps/details?id=x", price="paid"), "r"); assert e["label"] == "Google Play" and e["price"] == "paid"
assert C.external_for(rec(sources=[], official_url="", repo=""), "r") is None
assert C.slug("Daijishō", set()) == "daijisho" and C.slug("Tool", {"tool"}) == "tool-2"

# the committed curated file: unique, complete, policy-shaped (written by `curate.py select` + `inspect`)
doc = json.loads((ROOT / "candidates" / "android-curated.json").read_text(encoding="utf-8"))
apps = doc["apps"]
assert 150 <= len(apps) <= 260, len(apps)
assert len({x["id"] for x in apps}) == len(apps) and len({x["package"] for x in apps if x["package"]}) == len([x for x in apps if x["package"]])
assert {x["group"] for x in apps} == {"emulators", "games", "ports", "utilities", "media", "themes-launchers"}
inst = [x for x in apps if x["mode"] == "install"]; ext = [x for x in apps if x["mode"] == "external"]
assert len(inst) >= 60 and ext
for x in inst:
    ap = x["apk"]
    assert all(ap.get(k) for k in ("url", "sha256", "size", "version_code", "signers")), x["id"]
    assert C.source_kind(x["source"], ap["url"], x["package"], ap["version_code"]), x["id"]
    assert not C.NO_REDIST.search(x["license"] or "unknown") and not C.ROLLING.search(ap.get("tag") or ""), x["id"]
    assert ap["min_sdk"] <= 31 and (not ap["abis"] or set(ap["abis"]) & A.ROTATE_ABIS), x["id"]
for x in ext:
    assert "apk" not in x and x["external"]["url"].startswith("https://") and x["external"]["reason"], x["id"]
assert not any(x["name"] in C.DENY for x in apps)                                                         # reviewed false positives stay out
print("curate tests OK")
