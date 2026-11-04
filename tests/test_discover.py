"""Run: python tests/test_discover.py  (no framework, no network). The shared helpers crawl.py uses: evidence analysis, catalog lookup."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "discovery"))
import discover as D

PROF = json.loads((Path(D.__file__).parent / "profiles.json").read_text())["rg-nano"]


def repo(name, desc="", lic="MIT", **kw):
    r = {"full_name": name, "name": name.split("/")[1], "html_url": f"https://github.com/{name}", "description": desc, "topics": [],
         "license": {"spdx_id": lic} if lic else None, "pushed_at": "2026-09-01T00:00:00Z"}
    r.update(kw)
    return r


def rel(tag="v1", assets=(), body="", **kw):
    return {"tag_name": tag, "published_at": "2026-08-01T00:00:00Z", "body": body, "assets": list(assets), **kw}


def analyze(desc="", readme="", body="", topics=(), name="x/app"):
    r = repo(name, desc, topics=list(topics))
    return D.analyze(r, rel(body=body) if body else None, (readme, "https://r") if readme else None, PROF)


# ---- evidence analysis ----
v, ex = analyze(readme="# App\nThis app supports the Anbernic RG Nano.")
assert v == "supports" and ex[0]["source"] == "readme" and ex[0]["url"] == "https://r" and "RG Nano" in ex[0]["text"]
assert analyze(readme="Not compatible with RG Nano.")[0] == "incompatible"
assert analyze(readme="RG Nano is not supported.")[0] == "incompatible"
assert analyze(readme="Works on FunKeyOS. It does not work on RG Nano.")[0] == "conflicting"
assert analyze(readme="Not tested on RG Nano yet.")[0] == "ambiguous"            # untested is not a claim
assert analyze(readme="Thanks to the RG Nano community.")[0] == "ambiguous"      # incidental
assert analyze(desc="Port for Miyoo Mini", readme="Also see RG Nano.")[0] == "other_device"
assert analyze(desc="Port for Miyoo Mini", readme="Runs on RG Nano. Supports FunKeyOS.")[0] == "supports"
assert analyze(topics=["rg-nano"])[0] == "supports"
assert analyze(readme="Built for FunKey S.")[0] == "family"
assert analyze(desc="nothing here")[0] == "none"
vb = analyze(body="Now runs on RG Nano.")
assert vb[0] == "supports" and vb[1][0]["source"] == "release"
assert len(analyze(readme="\n".join(f"Runs on RG Nano {i}." for i in range(10)))[1]) == 3   # bounded excerpts
assert len(analyze(readme="Runs on RG Nano " + "x " * 200)[1][0]["text"]) <= 160

assert analyze(readme="RG_NANO_PORT_HANDOFF.md documents the port for RG Nano.")[0] == "supports"   # "no" inside "nano"
assert analyze(readme="```\nexport X=1 # not on RG Nano\n```\nPlain text.")[0] == "none"   # fenced code ignored

assert D.known_catalog()[1] >= {"tarafi"}
print("discover tests OK")
