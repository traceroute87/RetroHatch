"""Run: python tests/test_discover.py  (no framework, no network)."""
import base64, json, sys, tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "discovery"))
import discover as D

PROF = json.loads((Path(D.__file__).parent / "profiles.json").read_text())["rg-nano"]
AS_OF = date(2026, 10, 26)
CAT = ({"github.com/traceroute87/tarafi"}, {"tarafi", "rhprobe"})


def repo(name, desc="", lic="MIT", **kw):
    r = {"full_name": name, "name": name.split("/")[1], "html_url": f"https://github.com/{name}", "description": desc, "topics": [],
         "license": {"spdx_id": lic} if lic else None, "pushed_at": "2026-09-01T00:00:00Z"}
    r.update(kw)
    return r


def asset(name, url="auto", **kw):
    return {"name": name, "browser_download_url": f"https://github.com/dl/{name}" if url == "auto" else url, **kw}


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

# ---- pipeline ----
REPOS = [
    repo("a/good", "Game for RG Nano"),
    repo("b/nolic", "tool", lic=None),
    repo("c/misleading", "Cool app"),
    repo("d/contra", "Port. Not compatible with RG Nano."),
    repo("traceroute87/TaraFi", "Music player for RG Nano"),
    repo("e/rhprobe", "other"),
    repo("f/malformed", "funkeyos thing"),
    repo("g/old", "RG Nano old", archived=True, pushed_at="2020-01-01T00:00:00Z"),
    repo("h/pre", "funkeyos", fork=True),
    repo("i/ign", "RG Nano theme"),
    repo("j/rej", "RG Nano tool"),
    repo("k/noreadme", "For RG Nano"),
    repo("l/fail", "For RG Nano"),
]
RELS = {
    "a/good": [rel(assets=[asset("good_funkey-s.opk", size=10, digest="sha256:ab")])],
    "b/nolic": [rel(assets=[asset("x.opk")])],
    "c/misleading": [rel(assets=[asset("app_funkey-s.opk")])],
    "d/contra": [rel(assets=[asset("p.opk")])],
    "f/malformed": [rel(assets=[asset("m.opk", url="http://insecure/m.opk"), {"size": 3}, "junk", asset("readme.txt")]), None, "junk"],
    "g/old": [],
    "h/pre": [rel("v0", assets=[asset("p.opk")], prerelease=True), rel("draft", draft=True, assets=[asset("d.opk")])],
}
READMES = {"c/misleading": "Runs on Miyoo. Nothing else.", "a/good": "Supports RG Nano."}
CALLS = []


def fake(url):
    CALLS.append(url)
    if "/search/" in url:
        return 200, {}, {"items": REPOS + [REPOS[0], {"bad": 1}]}
    parts = url.split("/repos/")[1].split("/")
    name = parts[0] + "/" + parts[1].split("?")[0]
    if name == "l/fail":
        return 500, {}, None
    if url.endswith("/readme"):
        if name not in READMES:
            return 404, {}, None
        return 200, {}, {"content": base64.b64encode(READMES[name].encode()).decode(), "html_url": f"https://github.com/{name}#readme"}
    return 200, {}, RELS.get(name, [])


def tri(**kw):
    t = {"ignored": {}, "rejected": {}, "reviewed": {}}
    t.update({k: {r.lower(): v for r, v in d.items()} for k, d in kw.items()})
    return t


def run(triage, get=fake, **kw):
    return D.discover({**PROF, "queries": ["q"]}, get, as_of=AS_OF, catalog=CAT, triage=triage, **kw)


TRI = tri(ignored={"I/Ign": "theme, not an app"}, rejected={"j/rej": "bundles GPL code"})
cands, known, notes = run(TRI)
by = {c["repo"]: c for c in cands}

assert known == ["e/rhprobe", "traceroute87/TaraFi"], known                      # catalog duplicates
assert len(cands) == len(by) == 11                                             # search duplicate collapsed
assert by["a/good"]["level"] == "claimed" and by["a/good"]["assets"][0]["reported_digest"] == "sha256:ab"
assert by["b/nolic"]["license"] == "unknown" and "license unknown" in by["b/nolic"]["flags"]
m = by["c/misleading"]                                                         # filename alone proves nothing
assert m["level"] == "discovered" and m["verdict"] == "filename"
assert by["d/contra"]["verdict"] == "incompatible" and by["d/contra"]["level"] == "discovered"
f = by["f/malformed"]
assert [a for a in f["assets"] if "url" in a] == [] and "malformed asset" in f["flags"] and "no package asset" in f["flags"]
assert {"no release", "archived", "inactive >2y"} <= set(by["g/old"]["flags"])
h = by["h/pre"]
assert h["release"]["tag"] == "v0" and "prerelease only" in h["flags"] and "fork" in h["flags"]
assert by["i/ign"]["status"] == "ignored" and by["j/rej"]["status"] == "rejected" and by["j/rej"]["detail"]
assert not any("i/ign" in u or "j/rej" in u for u in CALLS if "/repos/" in u)   # nothing fetched for triaged repos
assert "no readme" in by["k/noreadme"]["flags"] and by["k/noreadme"]["level"] == "claimed"   # missing README tolerated
assert by["l/fail"]["level"] == "claimed" and any("l/fail: releases HTTP 500" in n for n in notes)   # API failure noted
assert all(c["level"] in ("discovered", "claimed") for c in cands if "level" in c)   # never tested/verified
assert all(c["status"] == "new" for c in cands if "verdict" in c)

# ---- triage: unchanged suppressed, changed surfaced ----
tri2 = tri(ignored=TRI["ignored"], rejected=TRI["rejected"],
           reviewed={"a/good": {"fp": by["a/good"]["fp"], "release": "v1", "verdict": "supports"},
                     "k/noreadme": {"fp": "stale", "release": "v0", "verdict": "none"}})
c2, _, _ = run(tri2)
b2 = {c["repo"]: c for c in c2}
assert b2["a/good"]["status"] == "unchanged" and b2["k/noreadme"]["status"] == "changed"
assert "release v0 -> None" in b2["k/noreadme"]["detail"] and "verdict none -> supports" in b2["k/noreadme"]["detail"]
act, low, unch, trg = D.split(c2)
assert "a/good" not in [c["repo"] for c in act] and "k/noreadme" in [c["repo"] for c in act]
assert len(trg) == 2 and len(unch) == 1
txt = D.report(c2, known, notes, "rg-nano", "2026-10-26")
assert "### a/good" not in txt and "### k/noreadme" in txt and "theme, not an app" in txt
assert "changed" in txt and "Nothing here is installable" in txt
assert "Ignored / rejected" not in D.report(c2, known, notes, "rg-nano", "2026-10-26", issue=True)
# a new release flips an unchanged repo to changed
RELS["a/good"] = [rel("v2", assets=[asset("good_funkey-s.opk", size=11)])]
c3, _, _ = run(tri2)
b3 = {c["repo"]: c for c in c3}["a/good"]
assert b3["status"] == "changed" and "release v1 -> v2" in b3["detail"]
RELS["a/good"] = [rel(assets=[asset("good_funkey-s.opk", size=10, digest="sha256:ab")])]
assert D.digest(D.split(c2)[0]) != D.digest(D.split(c3)[0])                     # issue digest tracks the actionable set

# mark-reviewed writes fingerprints, then nothing is actionable
with tempfile.TemporaryDirectory() as t:
    p = Path(t) / "triage.json"
    D.mark_reviewed(p, cands)
    t3 = D.load_triage(p)
    c4, _, _ = run(t3)
    assert D.split(c4)[0] == [] and len(D.split(c4)[2]) > 0
    assert t3["reviewed"]["a/good"]["fp"] == by["a/good"]["fp"]
    (Path(t) / "bad.json").write_text("{nope")
    assert D.load_triage(Path(t) / "bad.json")["ignored"] == {}                   # corrupt triage tolerated

# deterministic regardless of API order
r1 = D.report(cands, known, notes, "rg-nano", "2026-10-26")
REPOS.reverse()
c5, k5, n5 = run(TRI)
assert r1 == D.report(c5, k5, n5, "rg-nano", "2026-10-26")

# rate limits and failures are reported; a half-fetched candidate is dropped
c6, _, n6 = D.discover({**PROF, "queries": ["q1", "q2"]}, lambda u: (403, {}, None), catalog=CAT)
assert c6 == [] and any("rate limited" in n for n in n6)


def lim(u):
    if "/search/" in u: return 200, {}, {"items": [REPOS[0], REPOS[1]]}
    if u.endswith("/readme"): return 403, {"X-RateLimit-Remaining": "0"}, None
    return 200, {}, []


c7, _, n7 = D.discover({**PROF, "queries": ["q"]}, lim, catalog=CAT)
assert c7 == [] and any("rate limit hit" in n for n in n7)
c8, _, n8 = D.discover({**PROF, "queries": ["q"]}, lambda u: (200, {}, "garbage"), catalog=CAT)
assert c8 == [] and n8
_, _, n9 = D.discover({**PROF, "queries": ["q"]}, fake, max_repos=2, catalog=CAT)
assert any("only first 2" in n and n.startswith(D.INFO) for n in n9)             # informational: run still complete
assert D.fetch_readme(lambda u: (200, {}, {"content": "!!!notb64"}), "a/b")[1] is None
assert D.fetch_readme(lambda u: (200, {}, {"content": 5}), "a/b")[1] is None
assert D.known_catalog()[1] >= {"tarafi"}
print("discover tests OK")
