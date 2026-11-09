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
assert C.eligible(rec(apk_url="https://f-droid.org/repo/a.b_1.apk"))[0] is None                         # GitHub repo, but the listed file is not its release: resolved (or demoted) at inspect time
assert C.eligible(rec(apk_url="https://f-droid.org/repo/a.b_1.apk", repo="https://codeberg.org/o/tool", official_url="https://codeberg.org/o/tool"))[0] is False
ok, why = C.eligible(rec(apk_url="https://buildbot.libretro.com/stable/1.22.2/android/RetroArch_aarch64.apk")); assert ok is False and "trust policy" in why
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

# external listings link to a real page and never to a download
e = C.external_for(rec(sources=["fdroid"]), "reason"); assert e["label"] == "F-Droid" and e["url"] == "https://f-droid.org/packages/a.b/" and e["price"] is None
e = C.external_for(rec(sources=["izzy"]), "r"); assert e["label"] == "IzzyOnDroid"
e = C.external_for(rec(sources=["mainstream-seed"], official_url="https://play.google.com/store/apps/details?id=x", price="paid"), "r"); assert e["label"] == "Google Play" and e["price"] == "paid"
assert C.external_for(rec(sources=[], official_url="", repo=""), "r") is None
assert C.slug("Daijishō", set()) == "daijisho" and C.slug("Tool", {"tool"}) == "tool-2"

# the committed curated file: unique, complete, policy-shaped (written by `curate.py select` + `inspect`)
doc = json.loads((ROOT / "candidates" / "android-curated.json").read_text(encoding="utf-8"))
apps = doc["apps"]
assert 100 <= len(apps) <= 160, len(apps)
assert len({x["id"] for x in apps}) == len(apps) and len({x["package"] for x in apps if x["package"]}) == len([x for x in apps if x["package"]])
assert {x["group"] for x in apps} == {"emulators", "games", "ports", "utilities", "media", "themes-launchers"}
inst = [x for x in apps if x["mode"] == "install"]; ext = [x for x in apps if x["mode"] == "external"]
assert len(inst) >= 60 and ext
for x in inst:
    ap = x["apk"]
    assert all(ap.get(k) for k in ("url", "sha256", "size", "version_code", "signers")), x["id"]
    assert M.release_ok(x["source"], ap["url"]), x["id"]
    assert not C.NO_REDIST.search(x["license"] or "unknown") and not C.ROLLING.search(ap.get("tag") or ""), x["id"]
    assert ap["min_sdk"] <= 31 and (not ap["abis"] or set(ap["abis"]) & A.ROTATE_ABIS), x["id"]
for x in ext:
    assert "apk" not in x and x["external"]["url"].startswith("https://") and x["external"]["reason"], x["id"]
assert not any(x["name"] in C.DENY for x in apps)                                                         # reviewed false positives stay out
print("curate tests OK")
