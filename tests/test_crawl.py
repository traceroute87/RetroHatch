"""Run: python tests/test_crawl.py  (no framework, no network)."""
import io, os, sys, zipfile, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "discovery"))
import crawl as C

# ---- classify / links ----------------------------------------------------------------------------------------
assert C.classify("https://github.com/a/b/releases/download/v1/x.opk")[0] == "opk"
assert C.classify("https://github.com/a/b/blob/main/x.zip") == ("zip", "https://github.com/a/b/raw/main/x.zip")
assert C.classify("https://github.com/a/b") == ("repo", "a/b")
assert C.classify("https://github.com/a/b.git") == ("repo", "a/b")
assert C.classify("https://github.com/a") == ("owner", "a")
assert C.classify("https://github.com/topics/funkey")[0] != "repo"
assert C.classify("https://wiki.example.org/wiki/Apps") == ("page", "https://wiki.example.org/wiki/Apps")
L = C.links_of('<a href="/wiki/List">Third-party</a> [dl](https://x.org/a.opk) https://x.org/p.png https://w.org/wiki/F?action=history',
               "https://w.org/wiki/Main")
assert L == {"https://w.org/wiki/List": "Third-party", "https://x.org/a.opk": "dl"}, L   # image and wiki-history URLs dropped

# ---- judge: wrong device / bad magic / theme names are false positives, real OPK is installable ------------------
class FakeCrawl: repos = {}
pk = lambda name, repo="o/app", magic=True, kind="direct": {"name": name, "repo": repo, "magic_squashfs": magic, "kind": kind}
assert C.judge(pk("game.opk"), FakeCrawl)[0] == "installable"
assert C.judge(pk("rg350-update-1.7.opk", "Ninoh-FOX/RG350-ROGUE-CFW"), FakeCrawl)[0] == "false-positive"
assert C.judge(pk("PocketSNES_gcw0.opk", "DrUm78/PocketSNES"), FakeCrawl)[0] == "false-positive"
assert C.judge(pk("x.opk", magic=False), FakeCrawl)[0] == "false-positive"
assert C.judge(pk("dark_theme.opk"), FakeCrawl)[0] == "false-positive"
assert C.judge(pk("a.opk", magic=None, kind="zip"), FakeCrawl)[0] == "unverified"

# ---- completeness is never claimed when the run was cut short ---------------------------------------------------
assert C.assess([], 0, [], []) == []
assert any("request cap" in w for w in C.assess([], 0, ["request cap"], []))
assert any("not processed" in w for w in C.assess([], 3, [], []))
assert any("rate limited" in w for w in C.assess([], 0, [], [["https://x/y", 429]]))
assert any("rate limited" in w for w in C.assess([], 0, [], [["https://api.github.com/s", 403]]))
assert C.assess([], 0, [], [["https://wiki.example.org/x", 403]]) == []   # an ordinary 403 is not a rate limit
assert C.assess(["seed query 'x': HTTP 403"], 0, [], []) == ["seed query 'x': HTTP 403"]

# ---- ZIP listing + member magic via Range reads on a synthetic archive -------------------------------------------
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr(zipfile.ZipInfo("stored.opk"), b"hsqs" + b"x" * 100, zipfile.ZIP_STORED)
    z.writestr(zipfile.ZipInfo("packed.opk"), b"hsqs" + b"y" * 5000, zipfile.ZIP_DEFLATED)
    z.writestr(zipfile.ZipInfo("fake.opk"), b"NOPE" + b"z" * 100, zipfile.ZIP_DEFLATED)
    z.writestr("readme.txt", b"hello")
DATA = buf.getvalue()


def fake_fetch(url, rng=None, limit=0):
    a, b = rng.removeprefix("bytes=").split("-")
    a, b = int(a), int(b)
    return 206, {"Content-Range": f"bytes {a}-{min(b, len(DATA) - 1)}/{len(DATA)}"}, DATA[a:b + 1], url


real_fetch, C.fetch = C.fetch, fake_fetch
size, ents, note = C.list_zip("https://x/z.zip")
assert size == len(DATA) and note == "" and len(ents) == 4, (size, ents, note)
opks = {e["name"]: C.zip_member_is_opk("https://x/z.zip", e) for e in ents if e["name"].endswith(".opk")}
assert opks == {"stored.opk": True, "packed.opk": True, "fake.opk": False}, opks
C.fetch = real_fetch

# ---- request cap and time limit are enforced; token goes to api.github.com only, never forwarded -----------------
sent = []
class FakeOpener:
    def open(self, req, timeout=0):
        sent.append((req.full_url, req.get_header("Authorization")))
        raise OSError("offline")
C.OPENER, C.DELAY, C.HOSTOK = FakeOpener(), 0, {"api.github.com": True, "example.org": True}
os.environ["GITHUB_TOKEN"] = "tok"
C.fetch("https://api.github.com/x"); C.fetch("https://example.org/x")
assert sent == [("https://api.github.com/x", "Bearer tok"), ("https://example.org/x", None)], sent
C.MAX_REQ = C.NREQ
assert C.fetch("https://example.org/y")[0] == -1 and len(sent) == 2 and C.STOP == ["request cap"]
print("crawl tests OK")

# ---- FreeSerp optional channel (offline: fetch is faked) ---------------------------------------------------------------
import json, tempfile
assert C.classify("https://www.willemssoft.be/index.php?main=59&sub=60&action=download&file=Funkoban.opk")[0] == "opk"   # query-style download link
assert C.links_of("[d](https://w.be/i.php?action=download&file=X.opk)", "https://w.be/")   # real downloads are not wiki noise

SHOT = {"ok": True, "results": [
    {"url": "https://www.willemssoft.be/index.php?main=59&action=download&file=Funkoban.opk", "title": "Funkoban", "snippet": "Funkey Nano"},
    {"url": "https://rgnano.com/applications/", "title": "RG Nano Applications", "snippet": ""},
    {"url": "https://github.com/someone/funkey-game", "title": "game", "snippet": ""},
    {"url": "https://hotels.example.com/funky", "title": "Cheap hotels", "snippet": "book now"},
]}
calls = []
def fs_fetch(url, rng=None, limit=0):
    calls.append(url); return 200, {}, json.dumps(SHOT).encode(), url
C.fetch = fs_fetch
c = C.Crawl()
cache = os.path.join(tempfile.mkdtemp(), "leads.json")
r = C.seed_freeserp(c, cache, "2026-10-27")
assert r["status"] == "ok" and r["requests"] == C.FS_MAX_REQ == len(calls), r                       # bounded
assert any(u.endswith("q=funkey+opk+download") for u in calls), calls                             # queries come from profile terms
queued = {(k, key) for k, key, via, d in list(c.q) + list(c.pq)}
assert ("opk", "https://www.willemssoft.be/index.php?main=59&action=download&file=Funkoban.opk") in queued
assert ("page", "https://rgnano.com/applications/") in queued and ("repo", "someone/funkey-game") in queued
assert not any("hotels" in key for _, key in queued)                                                   # irrelevant page never queued
v = [via for k, key, via, d in c.pq if "rgnano.com" in key][0]
assert v["from"] == "freeserp-search" and v["anchor"].startswith("rg nano") and v["title"], v          # provenance kept
leads = json.load(open(cache)); assert len(leads) == 4 and leads["https://rgnano.com/applications/"]["queries"], leads
# a later run with FreeSerp down still replays the cached leads and reports the outage as an optional-channel status
C.fetch = lambda url, rng=None, limit=0: (429, {}, b"", url)
c2 = C.Crawl(); r2 = C.seed_freeserp(c2, cache, "2026-10-28")
assert r2["status"] == "unavailable" and r2["error"] == "HTTP 429" and r2["cached_leads"] == 4 and r2["requests"] == 1, r2   # one request, no retry
assert any(k == "opk" for k, *_ in list(c2.q))
# HTTP 200 with a fallback engine is NOT a successful search
C.fetch = lambda url, rng=None, limit=0: (200, {}, b'{"ok":true,"results":[],"engine_fallback":true,"engine_error":"engine_unavailable"}', url)
r3 = C.seed_freeserp(C.Crawl(), None); assert r3["status"] == "degraded" and r3["requests"] == 2 and r3["retried"], r3   # one retry, then stop
# network error / bad JSON: still no exception
C.fetch = lambda url, rng=None, limit=0: (0, {}, b"", url); assert C.seed_freeserp(C.Crawl(), None)["status"] == "unavailable"
C.fetch = lambda url, rng=None, limit=0: (200, {}, b"<html>", url); assert C.seed_freeserp(C.Crawl(), None)["status"] == "unavailable"
# cache pruning: entries older than CACHE_DAYS drop
C.save_leads(cache, {"https://old.example/x": {"first_seen": "2026-01-01", "last_seen": "2026-01-01", "queries": [], "title": ""},
                     "https://new.example/x": {"first_seen": "2026-10-27", "last_seen": "2026-10-27", "queries": [], "title": ""}}, "2026-10-27")
assert list(json.load(open(cache))) == ["https://new.example/x"]
# corrupt / hostile cache entries are dropped on load; a valid file:// or private-IP lead can never be fetched
bad = os.path.join(tempfile.mkdtemp(), "bad.json")
open(bad, "w").write(json.dumps({"file:///etc/passwd": {"last_seen": "2026-10-27"}, "https://ok.example/x": {"last_seen": "2026-10-27"}, "https://nodate.example/": {}, "https://str.example/": "x"}))
assert list(C.load_leads(bad)) == ["https://ok.example/x"]
C.HOSTOK["169.254.169.254"] = False; C.STOP.clear(); C.MAX_REQ = 10**6
assert real_fetch("http://169.254.169.254/latest/meta-data")[0] == -1 and real_fetch("file:///etc/passwd")[0] == -1   # revalidated at fetch time
# an optional-channel failure never makes the run incomplete (it is not in `notes`)
assert C.assess([], 0, [], []) == []
print("freeserp tests OK")

# ---- a link that makes http.client raise (e.g. a space in the URL) is a failed fetch, not a crash --------------------
import http.client
class BadOpener:
    def open(self, req, timeout=0): raise http.client.InvalidURL("URL can't contain control characters")
C.fetch, C.OPENER, C.MAX_REQ = real_fetch, BadOpener(), 10**6
C.STOP.clear(); C.HOSTOK["example.org"] = True
assert C.fetch("https://example.org/a b")[0] == 0
print("fetch robustness OK")

# ---- queue fairness: with both queues full, packages are not starved behind pages -------------------------------------------
c = C.Crawl(); order = []
c.do_page = lambda key, via, d: order.append("page"); c.add_pkg = lambda kind, key, via, d: order.append("pkg")
for i in range(30): c.push("page", f"https://p{i}.example/", {}, 0)
for i in range(5): c.push("opk", f"https://d.example/{i}.opk", {}, 0)
c.run()
assert order[:3] == ["page", "page", "pkg"] and order.count("pkg") == 5 and order.index("pkg") < 4, order
print("queue fairness OK")

# ---- prioritization: junk never queued, software indexes first, per-host + budget limits, coverage-limited is visible ----------
for u in ("https://www.facebook.com/sharer/sharer.php?u=x", "https://twitter.com/intent/tweet?text=x", "https://shop.example.com/cart",
          "https://www.amazon.com/dp/B0", "https://wa.me/?text=x", "https://store.example.com/products/funkey-s", "https://example.com/login", "https://example.com/account/settings"):
    assert C.classify(u)[0] is None, u
assert C.classify("https://wiki.example.org/wiki/Third-party_apps")[0] == "page" and C.classify("https://rgnano.com/applications/")[0] == "page"
assert C.pscore("Third-party OPK list", "https://w.org/wiki/Third-party_apps") > C.pscore("Home", "https://w.org/") == 0
c = C.Crawl()
for u, a in (("https://a.org/about", ""), ("https://a.org/games", "Games"), ("https://a.org/opk-downloads", "OPK downloads")):
    c.push("page", u, {"score": C.pscore(a, u)}, 0)
assert [k for _, k, _, _ in c.pq][0] == "https://a.org/opk-downloads"                      # best score served first
c = C.Crawl(); C.fetch = lambda url, rng=None, limit=0: (404, {}, b"", url)
for i in range(C.PER_HOST + 3): c.do_page(f"https://same.org/p{i}", {"score": 9}, 1)
assert len(c.pages) == C.PER_HOST and c.dropped["per-host limit"] == 3                       # repeated pages from one domain are capped
c = C.Crawl()
for i in range(int(C.MAX_PAGES * C.LOW_PAGE_SHARE)): c.do_page(f"https://h{i}.org/", {"score": 1}, 1)
n = len(c.pages); c.do_page("https://low.org/", {"score": 1}, 1); c.do_page("https://good.org/opk", {"score": 5}, 1)
assert len(c.pages) == n + 1 and "https://good.org/opk" in c.pages and "https://low.org/" not in c.pages   # reserve for promising pages
assert any("coverage-limited" in w and "NOT exhaustive" in w for w in C.assess([], 0, [], [], {"repo cap": 4}))
assert C.assess([], 0, [], [], {"per-host limit": 4}) == []
C.fetch = real_fetch
print("prioritization tests OK")

# ---- reach fixes: unquoted hrefs, GitLab blob -> raw, family-only pages follow promising links only ------------------------------
L = C.links_of('<a href=../add_roms/ class=md-nav__link>Add ROMs</a> <a href="/q">Q</a> <a href=https://x.org/a.opk>dl</a>',
               "https://doc.example.org/manual/software/add_opk/")
assert L == {"https://doc.example.org/manual/software/add_roms/": "Add ROMs", "https://doc.example.org/q": "Q", "https://x.org/a.opk": "dl"}, L
assert C.classify("https://gitlab.com/u/rel/-/blob/master/opk/x.opk") == ("opk", "https://gitlab.com/u/rel/-/raw/master/opk/x.opk")
assert C.classify("https://gitlab.com/u/rel/-/blob/master/x.zip") == ("zip", "https://gitlab.com/u/rel/-/raw/master/x.zip")
assert C.classify("https://example.org/-/blob/x.opk")[1] == "https://example.org/-/blob/x.opk"   # only gitlab.com is rewritten
FAM = ('<p>FunKey S docs</p><a href="https://w.example.org/wiki/List_of_third-party_OPK_applications">third-party OPK applications</a>'
       '<a href="https://w.example.org/wiki/Teardown">teardown</a><a href="https://github.com/o/r">r</a><a href="https://d.example.org/g.opk">g</a>')
C.fetch = lambda url, rng=None, limit=0: (200, {"Content-Type": "text/html"}, FAM.encode(), url)
c = C.Crawl(); c.do_page("https://doc.example.org/x", {"score": 5}, 0)
q = {(k, key) for k, key, _, _ in list(c.q) + list(c.pq)}
assert c.pages["https://doc.example.org/x"]["family"] and not c.pages["https://doc.example.org/x"]["relevant"]
assert ("page", "https://w.example.org/wiki/List_of_third-party_OPK_applications") in q                  # promising link followed
assert not any("Teardown" in key for _, key in q) and ("repo", "o/r") not in q                            # weak links / repos not followed
assert ("opk", "https://d.example.org/g.opk") in q                                                       # packages always
C.fetch = lambda url, rng=None, limit=0: (200, {"Content-Type": "text/html"}, b'<p>cooking</p><a href="https://w.example.org/opk-downloads">OPK downloads</a>', url)
c = C.Crawl(); c.do_page("https://doc.example.org/y", {"score": 5}, 0); assert not len(c.pq)            # unrelated page still follows nothing
C.fetch = real_fetch
C.fetch = lambda url, rng=None, limit=0: (403, {}, b"", url)
assert C.probe_opk("https://gitlab.com/u/r/-/raw/master/x.opk")[0] is None                              # login wall is not a magic mismatch
assert C.judge({**pk("x.opk", magic=None), "status": 403}, FakeCrawl) == ("unverified", "download not reachable (HTTP 403)")
C.fetch = real_fetch
print("reach fix tests OK")

# ---- cached/search lead starvation: late-query leads get admitted, duplicates take one slot, seeds beat derived links -----------
def fs_many(url, rng=None, limit=0):
    q = urllib.parse.unquote_plus(url.split("q=")[1])
    late = q.endswith("emulators")
    res = [{"url": "https://dup.example/funkey", "title": "FunKey"}]                                    # same lead in every query
    res += [{"url": f"https://p-{q.replace(' ', '-')}-{i}.example/funkey", "title": "FunKey"} for i in range(2)]
    if late: res.append({"url": "https://docs.example/manual/software/add_roms/", "title": "Add New ROMs - FunKey docs"})
    return 200, {}, json.dumps({"ok": True, "results": res}).encode(), url
import urllib.parse
C.fetch, sleep = fs_many, C.time.sleep; C.time.sleep = lambda s: None
c = C.Crawl(); r = C.seed_freeserp(c, None, "2026-10-27")
admitted = [key for _, key, _, _ in c.pq]
assert len(admitted) == C.FS_MAX_PAGES and admitted.count("https://dup.example/funkey") == 1, admitted   # one slot per distinct URL
assert "https://docs.example/manual/software/add_roms/" in admitted, admitted                       # late-query lead not starved
assert r["pages_not_admitted"] == 1 + 2 * C.FS_MAX_REQ + 1 - C.FS_MAX_PAGES, r                          # what was left out is reported
C.time.sleep, C.fetch = sleep, real_fetch
q = C.PQ()
q.append(("page", "https://derived.example/share?t=rg+nano", {"score": 12}, 3)); q.append(("page", "https://seed.example/docs", {"score": 4}, 0))
assert q.popleft()[1] == "https://seed.example/docs"                                                     # independent seed before derived link
for u in ("https://www.reddit.com/submit?url=https%3A%2F%2Fx.example%2Frg-nano", "https://old.reddit.com/submit?url=x",
          "https://share.flipboard.com/bookmarklet/popout?v=2&title=RG+Nano", "https://getpocket.com/save?url=https%3A%2F%2Fx.example"):
    assert C.classify(u)[0] is None, u                                                                   # share endpoints never queued
for u in ("https://www.reddit.com/r/RGNano/comments/abc/opk_list/", "https://www.reddit.com/r/FunKey/", "https://flipboard.com/@x/funkey-apps",
          "https://getpocket.com/explore/item/homebrew", "https://example.org/submit-your-opk/", "https://example.org/save-states/"):
    assert C.classify(u)[0] == "page", u                                                                 # discussions and software pages kept
print("lead starvation tests OK")

# ---- sources that refuse the runner are reported as inaccessible, not silently dropped -----------------------------------------
B = C.inaccessible([{"url": "https://wiki.example.org/wiki/Apps", "status": 403}, {"url": "https://wiki.example.org/wiki/Main", "status": 403},
                    {"url": "https://ok.example/", "status": 200}, {"url": "https://gone.example/", "status": 404}])
assert B == {"wiki.example.org": [["https://wiki.example.org/wiki/Apps", 403], ["https://wiki.example.org/wiki/Main", 403]]}, B
print("inaccessible source tests OK")

# ---- package lead store: verified URLs persist, blocked != gone, provenance kept, separate from catalog ------------------------
src = {"from": "https://wiki.example.org/wiki/List", "anchor": "Pico"}
U = "https://files.example/Pico.opk"
P = lambda **k: {"kind": "direct", "name": "Pico.opk", "url": U, "container": None, "size": 458752,
                 "host": "files.example", "repo": None, "via": [src], "judgement": "installable", "magic_squashfs": True, "status": 206, **k}
store = {}
assert C.update_packages(store, [P()], "2026-10-27")["new"] == 1
assert store[U]["kind"] == "opk" and store[U]["size"] == 458752 and store[U]["via"] == [src] and store[U]["state"] == "verified"
c = C.Crawl(); C.seed_packages(c, store)                                                            # next run: re-queued directly
k, key, via, d = c.q[0]; assert (k, key, d) == ("opk", U, 0) and via["first_found_via"] == src["from"]
assert C.update_packages(store, [P(judgement="unverified", magic_squashfs=None, status=403, via=[via])], "2026-11-03")["unreachable"] == 1
assert store[U]["state"] == "unreachable" and store[U]["last_status"] == "HTTP 403" and store[U]["via"] == [src]   # blocked: kept
C.update_packages(store, [P(via=[via])], "2026-11-10"); assert store[U]["via"] == [src] and store[U]["state"] == "verified"   # store hop is not provenance
# 1. never deleted for age: turns stale, keeps everything
C.update_packages(store, [], "2027-03-01"); assert store[U]["state"] == "stale" and store[U]["size"] == 458752 and store[U]["via"] == [src]
# 3. size change is flagged, previous values kept, and the flag sticks after later verifications
r = C.update_packages(store, [P(size=999424)], "2027-03-02"); assert r["changed"] == 1 and store[U]["state"] == "changed"
assert store[U]["previous"]["size"] == 458752 and store[U]["size"] == 999424
C.update_packages(store, [P(size=999424)], "2027-03-03"); assert store[U]["state"] == "changed"
zipm = lambda n: P(kind="zip", name=n, url="https://files.example/g.zip", container="https://files.example/g.zip")
zs = {}; C.update_packages(zs, [zipm("A.opk"), zipm("B.opk")], "2026-10-27"); assert zs["https://files.example/g.zip"]["members"] == ["A.opk", "B.opk"]
C.update_packages(zs, [zipm("A.opk"), zipm("B.opk")], "2026-10-28"); assert zs["https://files.example/g.zip"]["state"] == "verified"
C.update_packages(zs, [zipm("C.opk")], "2026-10-29"); z = zs["https://files.example/g.zip"]
assert z["state"] == "changed" and z["previous"]["members"] == ["A.opk", "B.opk"] and z["members"] == ["C.opk"]      # ZIP contents changed
# rejected = tombstone: kept, never rechecked, and a snapshot (seed) cannot resurrect it because the cache entry wins the merge
rs = {U: dict(store[U])}
assert C.update_packages(rs, [P(judgement="false-positive", magic_squashfs=False, status=200)], "2027-03-04")["rejected"] == 1
assert rs[U]["state"] == "rejected" and rs[U]["via"] == [src]
c = C.Crawl(); assert C.seed_packages(c, rs) == 0 and not len(c.q)
d_ = tempfile.mkdtemp(); seedf, cachef = os.path.join(d_, "seed.json"), os.path.join(d_, "cache.json")
json.dump({U: {**store[U], "state": "verified"}, "https://files.example/New.opk": {"kind": "opk", "last_verified": "2026-10-27", "via": []}}, open(seedf, "w"))
json.dump(rs, open(cachef, "w"))
merged = {}
for f in (seedf, cachef): merged.update(C.load_leads(f, "last_verified"))                          # same order as main(): seed, then cache
assert merged[U]["state"] == "rejected" and "https://files.example/New.opk" in merged
# 2. rechecks are bounded and rotate: least recently checked first, every entry gets its turn
big = {f"https://f.example/{i}.opk": {"kind": "opk", "last_verified": "2026-10-01", "last_checked": f"2026-10-{1 + i % 28:02d}"} for i in range(100)}
c = C.Crawl(); assert C.seed_packages(c, big) == C.RECHECK_MAX and len(c.q) == C.RECHECK_MAX
first = {key for _, key, _, _ in c.q}
assert max(big[u]["last_checked"] for u in first) <= min(big[u]["last_checked"] for u in set(big) - first)   # stalest first
for u in first: big[u]["last_checked"] = "2026-11-01"
c = C.Crawl(); C.seed_packages(c, big); assert set(big) - first <= {key for _, key, _, _ in c.q}               # next run: the rest first
zips = {f"https://z.example/{i}.zip": {"kind": "zip", "last_verified": "2026-10-01", "members": ["a.opk"] * 5} for i in range(30)}
assert C.seed_packages(C.Crawl(), zips) == C.RECHECK_MAX // 8                                              # ZIPs cost 3 + members requests
bad = os.path.join(tempfile.mkdtemp(), "pk.json"); open(bad, "w").write(json.dumps({"file:///x.opk": {"kind": "opk", "last_verified": "2026-10-27"}, "https://ok.example/a.opk": {"kind": "opk", "last_verified": "2026-10-27"}}))
assert list(C.load_leads(bad, "last_verified")) == ["https://ok.example/a.opk"]                       # malformed / non-http entries dropped
print("package lead store tests OK")

# ---- job summary statistics (reviewable without downloading the artifact) ---------------------------------------------------
res = {"as_of": "2026-10-27", "unique_installable_apps": [{"host": "github.com"}, {"host": "static.miraheze.org"}, {"host": "static.miraheze.org"}],
       "package_leads": {"rechecked": 7, "new": 1, "verified": 2}, "inaccessible_sources": {"wiki.example.org": []},
       "optional_channels": {"freeserp": {"status": "ok", "queries": 16, "requests": 16, "results": 160, "new_leads": 3, "cached_leads": 92, "error": None}}}
store = {"https://a/x.opk": {"name": "x.opk", "first_seen": "2026-10-27", "last_verified": "2026-10-27", "state": "verified"},
         "https://a/y.opk": {"name": "y.opk", "first_seen": "2026-10-01", "last_verified": "2026-10-27", "state": "changed", "last_status": "ok"},
         "https://a/z.opk": {"name": "z.opk", "first_seen": "2026-10-01", "last_verified": "2026-10-01", "state": "unreachable", "last_status": "HTTP 403"}}
md = C.stats_md(res, store)
for want in ("| Verified OPKs (unique) | 3 |", "| GitHub-hosted / other hosts | 1 / 2 |", "changed 1, unreachable 1, verified 1",
             "| 1 / 1 / 1 |", "ok: 16/16 queries ok", "wiki.example.org", "**Changed packages (1)**", "z.opk (HTTP 403): https://a/z.opk"):
    assert want in md, (want, md)
print("job summary tests OK")


# ---- recheck coverage: equal dates must not starve external hosts; per-run counts; ZIP members vs unreachable URLs ---------------
GH = {f"https://github.com/o{i}/r/releases/download/v1/a{i}.opk": {"kind": "opk", "last_verified": "2026-10-27", "last_checked": "2026-10-27"} for i in range(120)}
EXT = {f"https://static.miraheze.org/funkeywiki/{i}/x{i}.opk": {"kind": "opk", "last_verified": "2026-10-27", "last_checked": "2026-10-27"} for i in range(28)}
ZIPS = {f"https://github.com/z{i}/r/releases/download/v1/p.zip": {"kind": "zip", "last_verified": "2026-10-27", "last_checked": "2026-10-27", "members": ["m.opk"] * 18} for i in range(4)}
st = {**GH, **EXT, **ZIPS}
cost = lambda us: sum(1 if st[u]["kind"] == "opk" else 3 + min(12, len(st[u]["members"])) for u in us)
c = C.Crawl(); C.seed_packages(c, st, "2026-10-28")
ext = [u for u in c.recheck if "miraheze" in u]
assert cost(c.recheck) <= C.RECHECK_MAX and len(ext) >= 20, (cost(c.recheck), len(ext))        # same date: hosts take turns, budget kept
covered, day = set(), 28
while EXT.keys() - covered and day < 40:                                                           # every external lead gets rechecked
    c = C.Crawl(); C.seed_packages(c, st, f"2026-10-{day}")
    for u in c.recheck: st[u]["last_checked"] = f"2026-10-{day}"
    covered |= set(c.recheck); day += 1
assert not EXT.keys() - covered and day <= 30, day
assert not GH.keys() - covered or day > 29                                                         # ...and GitHub ones keep rotating
# per-run stats are separate from history: 1 external verified, 1 external unreachable, 1 GitHub queued but never fetched
due = list(EXT)[:2] + list(GH)[:1]
s2 = {u: {**v, "last_checked": "2026-10-27"} for u, v in st.items()}
s2[due[0]].update(last_checked="2026-11-01", last_verified="2026-11-01", last_status="ok", checked_at=5000)
s2[due[1]].update(last_checked="2026-11-01", last_status="HTTP 403", checked_at=5001)
s2[due[2]].update(last_checked="2026-11-01", last_status="ok", checked_at=4000)          # checked by an EARLIER run the same day
assert C.recheck_stats(s2, due, 4500) == {"github": {"queued": 1, "processed": 0, "verified": 0, "unreachable": 0},
                                                  "external": {"queued": 2, "processed": 2, "verified": 1, "unreachable": 1}}
# a reachable ZIP with 18 members, 6 beyond the header limit: verified, 0 unreachable URLs, 6 unverified members, state untouched
Z = "https://github.com/p/picoarch/releases/download/v1/picoarch.zip"
zs = {Z: {"kind": "zip", "first_seen": "2026-10-01", "last_verified": "2026-10-01", "via": [], "members": [f"m{i}.opk" for i in range(12)], "state": "verified"}}
mem = lambda i, magic: {"kind": "zip", "name": f"m{i}.opk", "url": Z, "container": Z, "size": 1, "host": "github.com", "repo": "p/picoarch", "via": [src],
                        "judgement": "installable" if magic else "unverified", "magic_squashfs": magic}
cont = {"kind": "zip-container", "url": Z, "note": "", "host": "github.com"}
r = C.update_packages(zs, [cont] + [mem(i, True) for i in range(12)] + [mem(i, None) for i in range(12, 18)], "2026-11-01")
assert (r["verified"], r["unreachable"], r["unverified_members"]) == (1, 0, 6) and zs[Z]["state"] == "verified", (r, zs[Z]["state"])
# the same ZIP when its directory cannot be read: one unreachable URL, members not counted
r = C.update_packages(zs, [{**cont, "note": "zip size probe HTTP 403"}], "2026-11-02")
assert (r["verified"], r["unreachable"], r["unverified_members"]) == (0, 1, 0) and zs[Z]["state"] == "unreachable" and zs[Z]["last_status"] == "zip size probe HTTP 403"
print("recheck coverage tests OK")

# ---- same-date runs: state persisted between runs must move the rotation on (checked_at), not repeat the same 60 requests -------
def fixture():
    mk = lambda kind, **k: {"kind": kind, "first_seen": "2026-10-27", "last_verified": "2026-10-27", "last_checked": "2026-10-27", "via": [], **k}
    return {**{f"https://github.com/o{i}/r/releases/download/v1/a{i}.opk": mk("opk", size=1) for i in range(120)},
            **{f"https://static.miraheze.org/funkeywiki/{i}/x{i}.opk": mk("opk", size=1) for i in range(28)},
            **{f"https://github.com/z{i}/r/releases/download/v1/p.zip": mk("zip", members=[f"m{j}.opk" for j in range(18)]) for i in range(4)}}
def results(st, urls):   # what the crawl reports for each re-probed URL: every one reachable and verified
    out = []
    for u in urls:
        h = urllib.parse.urlsplit(u).netloc
        if st[u]["kind"] == "opk":
            out.append({"kind": "direct", "name": u.rsplit("/", 1)[1], "url": u, "container": None, "size": 1, "host": h, "repo": None, "via": [], "judgement": "installable", "magic_squashfs": True})
        else:
            out.append({"kind": "zip-container", "url": u, "note": "", "host": h})
            out += [{"kind": "zip", "name": m, "url": u, "container": u, "size": 1, "host": h, "repo": None, "via": [], "judgement": "installable" if k < 12 else "unverified",
                     "magic_squashfs": True if k < 12 else None} for k, m in enumerate(st[u]["members"])]
    return out
st, done, order = fixture(), set(), []
for run in range(6):                                                                                 # six runs, all on 2026-10-27
    c = C.Crawl(); C.seed_packages(c, st, "2026-10-27")
    assert cost(c.recheck) <= C.RECHECK_MAX, run                                                     # budget every run
    order.append(set(c.recheck))
    C.update_packages(st, results(st, c.recheck), "2026-10-27", now=1000 + run)                     # persisted state between runs
    done |= set(c.recheck)
assert not order[0] & order[1], len(order[0] & order[1])                                            # run 2 does not repeat run 1
assert not EXT.keys() - order[0] and any("github.com/o" in u for u in order[1])                     # external done in run 1; skipped GitHub next
for i in range(1, 6):                                                                                 # a run repeats URLs only once it
    before = set().union(*order[:i])                                                                  # has taken every unchecked one
    assert not order[i] & before or len(before | order[i]) == len(st), i
assert all(u in done for u in ZIPS) and len(done) == len(st), (len(done), len(st))                  # ZIPs and cheap OPKs all covered
print("same-date rotation tests OK")

# ---- forge projects found by link: GitLab/Codeberg URLs go through the forge API, GitLab README is read, its build link verified ----
assert C.classify("https://gitlab.com/someone/player") == ("forge", "gitlab.com/someone%2Fplayer|someone/player")
assert C.classify("https://gitlab.com/grp/sub/player/-/tree/main") == ("forge", "gitlab.com/grp%2Fsub%2Fplayer|grp/sub/player")   # subgroups
assert C.classify("https://gitlab.com/a/b.git")[1] == "gitlab.com/a%2Fb|a/b" and C.classify("https://gitlab.com/explore/projects")[0] == "page"
assert C.classify("https://codeberg.org/o/r/src/branch/main/README.md") == ("forge", "codeberg.org/o/r")
assert C.classify("https://gitlab.com/a/b/-/raw/main/x.opk")[0] == "opk" and C.classify("https://github.com/a/b") == ("repo", "a/b")   # unchanged
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w") as z:
    z.writestr(zipfile.ZipInfo("player/player.opk"), b"hsqs" + b"p" * 300, zipfile.ZIP_DEFLATED)
    z.writestr("player/readme.txt", b"x")
ZD, ZURL = zbuf.getvalue(), "https://builds.example.org/data/player-rgnano.zip"
README = ("# Player\nBuilds for the Anbernic RG Nano, requires the community FunKey OS fork.\n"
          f"- To install [download the dev build]({ZURL}) and copy the .opk to Applications.\n")
def forge_fetch(readme):
    def f(url, rng=None, limit=0):
        if url == "https://forum.example.org/t/1": return 200, {"Content-Type": "text/html"}, b'<p>RG Nano port</p><a href="https://gitlab.com/someone/player">source</a>', url
        if url == "https://gitlab.com/api/v4/projects/someone%2Fplayer/repository/files/README.md/raw?ref=HEAD": return 200, {}, readme.encode(), url
        if url.startswith("https://gitlab.com/api/v4/projects/someone%2Fplayer/releases"): return 200, {}, b"[]", url
        if url == ZURL and rng:
            a, b = map(int, rng.removeprefix("bytes=").split("-"))
            return 206, {"Content-Range": f"bytes {a}-{min(b, len(ZD) - 1)}/{len(ZD)}"}, ZD[a:b + 1], url
        return 404, {}, b"", url
    return f
C.fetch, C.MAX_REQ = forge_fetch(README), 10**6
c = C.Crawl(); c.push("page", "https://forum.example.org/t/1", {"from": "test", "score": 5}, 0); c.run()
r = c.repos["gitlab.com/someone%2fplayer|someone/player"]
assert r["readme_status"] == 200 and r["verdict"] != "none" and r["verdict_basis"].startswith("readme claim"), r       # metadata was empty
opk = [p for p in c.pkgs.values() if p["kind"] == "zip"][0]
assert opk["name"] == "player.opk" and opk["magic_squashfs"] is True and C.judge(opk, c)[0] == "installable"           # verified, not approved
assert opk["via"][0]["from"] == "https://gitlab.com/someone/player"                                                      # provenance: the README
C.fetch = forge_fetch("# Player\nA music player.\n")                                                                     # control
c2 = C.Crawl(); c2.do_forge("gitlab.com/someone%2Fplayer|someone/player", {"from": "test"}, 0)
assert c2.repos["gitlab.com/someone%2fplayer|someone/player"]["verdict"] == "none" and not len(c2.pq)                    # no device claim: nothing followed
C.fetch = real_fetch
print("forge reach tests OK")

# ---- search categories from the profile, rotated within FS_MAX_REQ; one FreeSerp retry; diverse harvest slots ------------------
qa, qb = C.fs_queries("2026-10-27"), C.fs_queries("2026-10-28")
allq = {f"{t} {s}" for s in C.PROF["search_suffixes"] for t in ("rg nano", "funkey os", "funkey s", "funkey")}
assert len(qa) == len(qb) == C.FS_MAX_REQ and set(qa) | set(qb) == allq, (len(allq), sorted(allq - set(qa) - set(qb)))   # 2 days cover all
assert {"software", "applications", "ports"} <= set(C.PROF["search_suffixes"])
saved = C.PROF.pop("search_suffixes"); assert C.fs_queries("2026-10-27")[0] == "rg nano opk download" and len(C.fs_queries("2026-10-27")) == 16
C.PROF["search_suffixes"] = saved                                                                       # profile without categories: old queries
sleep_, C.time.sleep = C.time.sleep, (lambda s: None)
OKJ = json.dumps({"ok": True, "results": [{"url": "https://w.example/rg-nano-apps", "title": "RG Nano apps"}]}).encode()
BAD = b'{"ok":true,"results":[],"engine_fallback":true,"engine_error":"engine_unavailable"}'
def seq(*bodies):
    it = iter(bodies)
    def f(url, rng=None, limit=0): return 200, {}, next(it, OKJ), url
    return f
C.fetch = seq(BAD, OKJ)                                                                                 # degraded once, then fine
r = C.seed_freeserp(C.Crawl(), None, "2026-10-27")
assert r["status"] == "ok" and r["retried"] and r["requests"] == C.FS_MAX_REQ and r["queries"] == C.FS_MAX_REQ - 1, r   # retry costs a query slot
C.fetch = seq(BAD, OKJ, BAD)                                                                            # only one retry per run
r = C.seed_freeserp(C.Crawl(), None, "2026-10-27"); assert r["status"] == "degraded" and r["requests"] == 3 and r["queries"] == 1, r
C.time.sleep = sleep_
# harvest: six near-identical high-scoring links take at most 2 slots; distinct links keep theirs
assert C.link_template("https://t.example/download.php?themeid=3860") == C.link_template("https://t.example/download.php?themeid=3861")
assert C.link_template("https://w.example/wiki/Apps") != C.link_template("https://w.example/wiki/Ports")
H = "<p>RG Nano</p>" + "".join(f'<a href="https://themes.example.org/download.php?themeid={3860 + i}">download RG Nano theme</a>' for i in range(6)) + \
    '<a href="https://www.example.org/download/rg-nano">RG Nano download builds</a><a href="https://www.example.org/manual/rg-nano">RG Nano manual</a>'
c = C.Crawl(); c.harvest(H, "https://themes.example.org/index.php?target=rgnano", {}, 0, True)
pushed = [key for _, key, _, _ in c.pq]
assert sum("themeid" in u for u in pushed) == 2 and "https://www.example.org/download/rg-nano" in pushed and "https://www.example.org/manual/rg-nano" in pushed, pushed
C.fetch = real_fetch
print("search category / retry / diversity tests OK")

# ---- repository tree discovery: pinned commit URLs, repo provenance, wrong-device exclusion, bounded ---------------------------
SHA = "a" * 40
def tree_fetch(desc_readme, paths, calls):
    def f(url, rng=None, limit=0):
        calls.append(url)
        if url.endswith("/README.md"): return 200, {}, desc_readme.encode(), url
        if url.endswith("/releases/latest"): return 404, {}, b"", url
        if url.endswith("/commits/HEAD"): return 200, {}, json.dumps({"sha": SHA}).encode(), url
        if "/git/trees/" in url: return 200, {}, json.dumps({"sha": "t", "truncated": False, "tree": [{"path": p_, "type": "blob"} for p_ in paths] + [{"path": "Apps", "type": "tree"}]}).encode(), url
        if "raw.githubusercontent.com" in url and rng: return 206, {"Content-Range": "bytes 0-3/8192"}, b"hsqs", url
        return 404, {}, b"", url
    return f
calls = []
C.fetch = tree_fetch("# Pack\nApps for the RG Nano running FunKey OS.\n", ["Apps/Game One.opk", "Apps/b.zip", "docs/x.md"] + [f"More/m{i}.opk" for i in range(60)], calls)
c = C.Crawl(); c.tree_salt = "2"; c.do_repo("someone/pack", {"from": "test"}, 0)   # fixed shuffle (salt "2" queues Game One); T0 made this flaky
r = c.repos["someone/pack"]
q = [(k, key, via) for k, key, via, _ in c.q if via.get("anchor") == "repository file"]
assert r["tree"]["commit"] == SHA and r["tree"]["packages"] == 61 and r["tree"]["queued"] == C.TREE_MAX == len(q) and r["tree"]["truncated"]   # bounded
assert sum("/git/trees/" in u for u in calls) == 1 and sum(u.endswith("/commits/HEAD") for u in calls) == 1                         # 2 API requests
k, u, via = next(x for x in q if "Game%20One.opk" in x[1])
assert k == "opk" and u == f"https://raw.githubusercontent.com/someone/pack/{SHA}/Apps/Game%20One.opk" and C.classify(u) == ("opk", u)   # immutable URL
assert via["repo"] == "someone/pack" and via["commit"] == SHA and via["path"] == "Apps/Game One.opk"                                # provenance
assert not any("docs/x.md" in x[1] or ".zip" in x[1] for x in q) and all(x[0] == "opk" for x in q)                            # profile extensions only: no tree ZIPs
c.add_pkg(k, u, via, 1); p = c.pkgs[u]
assert p["repo"] == "someone/pack" and p["magic_squashfs"] is True and C.judge(p, c)[0] == "installable"                          # Nano repo: candidate
# other-device repo: no tree request at all, and its OPK is never Nano-installable even with a valid SquashFS header
calls.clear()
C.fetch = tree_fetch("# Pack\nRepository of RG350 and GCW0 compatible software for OpenDingux.\n", ["Apps/x.opk"], calls)
c = C.Crawl(); c.do_repo("other/rg350pack", {"from": "test"}, 0)
assert c.repos["other/rg350pack"]["verdict"] in ("other_device", "none") and not any("/git/trees/" in u for u in calls) and "tree" not in c.repos["other/rg350pack"]
c.repos["other/rg350pack"]["verdict"] = "other_device"
raw = f"https://raw.githubusercontent.com/other/rg350pack/{SHA}/Apps/x.opk"
c.add_pkg("opk", raw, {"from": "https://example.org/list"}, 1); p = c.pkgs[raw]                                                  # no repo in via:
assert p["repo"] == "other/rg350pack" and p["magic_squashfs"] is True and C.judge(p, c) == ("false-positive", "repo evidence: other_device")   # inferred from raw URL
c.add_pkg("opk", "https://files.example/y.opk", {"from": "https://github.com/other/rg350pack/blob/HEAD/README.md"}, 1)          # README link: repo from via
assert c.pkgs["https://files.example/y.opk"]["repo"] == "other/rg350pack" and C.judge(c.pkgs["https://files.example/y.opk"], c)[0] == "false-positive"
for desc in ("Repository of RG-350 and PocketGo 2 compatible Software", "Apps for the GCW Zero"):                          # spelling variants
    assert C.D.analyze({"full_name": "o/r", "name": "r", "html_url": "https://github.com/o/r", "description": desc, "topics": []}, None, None, C.PROF)[0] == "other_device", desc
assert C.D.analyze({"full_name": "o/r", "name": "r", "html_url": "https://github.com/o/r", "description": "Game for the RG Nano", "topics": []}, None, None, C.PROF)[0] == "supports"
C.fetch = real_fetch
print("repository tree tests OK")

# ---- large repository trees: progressive coverage across runs, changed files flagged, budgets, store limit, same-day stats ------
FULL, N = "someone/wiki-mirror", 454
blobs = {f"wiki/files/app{i:03d}.opk": f"{i:040x}" for i in range(N)}
def mirror_fetch(sha):
    def f(url, rng=None, limit=0):
        if url.endswith("/commits/HEAD"): return 200, {}, json.dumps({"sha": sha}).encode(), url
        if "/git/trees/" in url:
            tree = [{"path": p_, "type": "blob", "sha": b_} for p_, b_ in blobs.items()] + [{"path": "wiki/files/pack.zip", "type": "blob", "sha": "f" * 40}]
            return 200, {}, json.dumps({"truncated": False, "tree": tree}).encode(), url
        return 404, {}, b"", url
    return f
def run_tree(store, salt, sha=SHA, budget=None):
    C.fetch = mirror_fetch(sha)
    c = C.Crawl(); c.tree_known, c.tree_salt = C.tree_known(store), salt
    if budget is not None: c.tree_left = budget
    r = {}; c.do_tree(FULL, r, 0)
    q = [(key, via) for _, key, via, _ in c.q]
    pk = [{"kind": "direct", "name": via["path"].rsplit("/", 1)[1], "url": key, "container": None, "size": 8192, "host": "raw.githubusercontent.com",
           "repo": FULL, "via": [via], "judgement": "installable", "magic_squashfs": True, "status": 206} for key, via in q]
    return r["tree"], q, pk
store, covered, runs = {}, set(), 0
while len(covered) < N and runs < 20:
    t, q, pk = run_tree(store, f"run{runs}")
    paths = {via["path"] for _, via in q}
    assert len(q) == C.TREE_MAX or len(q) == N - len(covered), (runs, len(q))                       # 40 per run, last run the rest
    assert not paths & covered, runs                                                                  # never the same files again
    assert all(key.startswith(f"https://raw.githubusercontent.com/{FULL}/{SHA}/") and not key.endswith(".zip") for key, _ in q)   # pinned, OPK only
    C.update_packages(store, pk, "2026-10-28", now=6000 + runs)
    covered |= paths; runs += 1
assert covered == set(blobs) and runs == -(-N // C.TREE_MAX) == 12 and len(store) == N, (runs, len(store))   # every path in 12 runs
t, q, _ = run_tree(store, "run-x"); assert t["known"] == N and t["unseen"] == 0 and not q                   # nothing left: no wasted probes
# a file changes in a later commit: re-queued first at the new commit URL, stored as "changed" with the previous URL
SHA2, changed_path = "b" * 40, "wiki/files/app007.opk"
old_url = next(u for u, v in store.items() if v["via"][0]["path"] == changed_path)
blobs[changed_path] = "c" * 40
t, q, pk = run_tree(store, "run-y", SHA2)
assert t["changed"] == 1 and len(q) == 1 and q[0][1]["previous_url"] == old_url and q[0][0].startswith(f"https://raw.githubusercontent.com/{FULL}/{SHA2}/")
r = C.update_packages(store, pk, "2026-10-29", now=7000); new_url = q[0][0]
assert r["changed"] == 1 and store[new_url]["state"] == "changed" and store[new_url]["previous"]["url"] == old_url and old_url in store   # old kept for recheck
c = C.Crawl(); C.seed_packages(c, store, "2026-10-30"); assert c.recheck                              # verified files still rotate through rechecks
# run budget across repos: tree probes stop at TREE_RUN_MAX, then whole trees are skipped (counted)
t, q, _ = run_tree({}, "b1", budget=25); assert len(q) == 25
C.fetch = mirror_fetch(SHA); c = C.Crawl(); c.tree_left = 0; c.do_tree(FULL, {}, 0); assert c.dropped.get("tree budget") == 1 and not len(c.q)
# store limit: room for large trees; over the limit, stale/unreachable go first, recently verified and tombstones stay
assert C.PKG_MAX >= 2000
lim = {f"https://x/{i}.opk": {"kind": "opk", "last_verified": "2026-10-01", "state": "verified"} for i in range(C.PKG_MAX - 1)}
lim["https://x/stale.opk"] = {"kind": "opk", "last_verified": "2026-01-01", "state": "stale"}
lim["https://x/gone.opk"] = {"kind": "opk", "last_verified": "2026-10-01", "state": "unreachable"}
lim["https://x/rej.opk"] = {"kind": "opk", "last_verified": "2025-01-01", "state": "rejected"}
C.update_packages(lim, [], "2026-10-02"); assert len(lim) == C.PKG_MAX and "https://x/stale.opk" not in lim and "https://x/gone.opk" not in lim and "https://x/rej.opk" in lim
# same-day reporting: earlier runs that day are not "new"; this run's counts come from update_packages
same = {f"https://h/{i}.opk": {"first_seen": "2026-10-27", "last_verified": "2026-10-27", "state": "verified"} for i in range(197)}
md = C.stats_md({"as_of": "2026-10-27", "unique_installable_apps": [], "package_leads": {"new": 45, "verified": 193, "rechecked": 36}, "optional_channels": {}}, same)
assert "| 45 / 148 / 4 |" in md, md
C.fetch = real_fetch
print("large tree coverage tests OK")

# ---- changed file, then rediscovered at the same new blob: known, not re-queued; a third blob is a new change -------------------
RP, PATH = "dev/one", "apps/app.opk"
def one_file(sha, blob):
    def f(url, rng=None, limit=0):
        if url.endswith("/commits/HEAD"): return 200, {}, json.dumps({"sha": sha}).encode(), url
        if "/git/trees/" in url: return 200, {}, json.dumps({"tree": [{"path": PATH, "type": "blob", "sha": blob}]}).encode(), url
        return 404, {}, b"", url
    return f
def scan(store, sha, blob, now, budget=None):
    store = json.loads(json.dumps(store, sort_keys=True))                                            # reloaded like the Actions cache
    C.fetch = one_file(sha, blob); c = C.Crawl(); c.tree_known = C.tree_known(store)
    if budget is not None: c.tree_left = budget
    r = {}; c.do_tree(RP, r, 0)
    pk = [{"kind": "direct", "name": "app.opk", "url": key, "container": None, "size": 4096, "host": "raw.githubusercontent.com", "repo": RP,
           "via": [via], "judgement": "installable", "magic_squashfs": True, "status": 206} for _, key, via, _ in c.q]
    n = C.update_packages(store, pk, "2026-10-28", now=now)
    return store, r.get("tree", {}), [key for _, key, _, _ in c.q], n
S1, S2, S3 = "f" * 40, "0" * 40, "8" * 40                                                              # newer commits sort FIRST
st_, t, q, n = scan({}, S1, "1" * 40, 100); u1 = q[0]                                                   # 1. original verified
assert t["unseen"] == 1 and n["new"] == 1 and st_[u1]["state"] == "verified"
st_, t, q, n = scan(st_, S2, "2" * 40, 200); u2 = q[0]                                                  # 2-3. blob changes
assert t["changed"] == 1 and n["changed"] == 1 and st_[u2]["state"] == "changed" and st_[u2]["previous"]["url"] == u1
for i in range(3):                                                                                      # 4. same new blob, repeated runs
    st_, t, q, n = scan(st_, S2, "2" * 40, 300 + i)
    assert (t["known"], t["changed"], t["unseen"], q, n["changed"]) == (1, 0, 0, [], 0), (i, t, q)      # already discovered, not re-queued
assert set(st_) == {u1, u2} and st_[u1]["via"][0]["blob"] == "1" * 40 and st_[u1]["via"][0]["commit"] == S1   # history + provenance intact
assert st_[u2]["previous"]["url"] == u1 and st_[u2]["via"][0]["blob"] == "2" * 40
st_, t, q, n = scan(st_, S3, "3" * 40, 400)                                                             # third, different blob
assert t["changed"] == 1 and len(q) == 1 and st_[q[0]]["state"] == "changed" and st_[q[0]]["previous"]["url"] == u2   # points at the latest
_, t, q, _ = scan(st_, S3, "4" * 40, 500, budget=0); assert q == [] and t == {}                         # budget still respected
C.fetch = real_fetch
print("changed-file rediscovery tests OK")

# ---- tree-scan progress and persisted rejects: no redundant tree requests, no re-probing an unchanged bad file ------------------
RS = "dev/pack"
def repo_fetch(sha, files, calls):
    def f(url, rng=None, limit=0):
        calls.append(url)
        if url.endswith("/commits/HEAD"): return 200, {}, json.dumps({"sha": sha}).encode(), url
        if "/git/trees/" in url: return 200, {}, json.dumps({"tree": [{"path": p_, "type": "blob", "sha": b_} for p_, (b_, _) in files.items()]}).encode(), url
        return 404, {}, b"", url
    return f
def outcome(files, path, rng_status):   # what probing a queued file returns: (status, first bytes)
    return rng_status.get(path, (206, files[path][1]))
def scan_run(state, sha, files, calls, rng_status={}, per_repo=None):
    store, scans = state
    store, scans = json.loads(json.dumps(store, sort_keys=True)), json.loads(json.dumps(scans))      # persisted between runs
    C.fetch = repo_fetch(sha, files, calls)
    c = C.Crawl(); c.tree_known, c.tree_scans = C.tree_known(store), scans
    r = {}; c.do_tree(RS, r, 0)
    pk = []
    for _, key, via, _ in c.q:
        st_, body = outcome(files, via["path"], rng_status)
        pk.append({"kind": "direct", "name": via["path"].rsplit("/", 1)[1], "url": key, "container": None, "size": 4096, "host": "raw.githubusercontent.com",
                   "repo": RS, "via": [via], "status": st_, "magic_squashfs": (body == b"hsqs") if st_ in (200, 206) else None})
    for p_ in pk: p_["judgement"] = C.judge(p_, c)[0]
    C.update_packages(store, pk, "2026-10-29", now=int(time.time()))
    return (store, c.tree_scans), r.get("tree", {}), [via["path"] for _, _, via, _ in c.q]
import time
A1, A2, A3 = "1" * 40, "2" * 40, "3" * 40
files = {f"apps/a{i}.opk": (f"{i + 1:040x}", b"hsqs") for i in range(50)}                            # 50 files: needs 2 runs at 40/run
files["apps/broken.opk"] = ("e" * 40, b"<htm")                                                       # committed HTML error page
state, calls = ({}, {}), []
state, t, q = scan_run(state, A1, files, calls)                                                      # run 1: 40 of 51
assert len(q) == 40 and not state[1][RS.lower()]["complete"]
calls.clear(); state, t, q = scan_run(state, A1, files, calls)                                       # run 2: unfinished repo continues
assert len(q) == 11 and sum("/git/trees/" in u for u in calls) == 1
assert any(v.get("state") == "rejected" and v["via"][0]["path"] == "apps/broken.opk" and v["via"][0]["blob"] == "e" * 40 for v in state[0].values())   # rejected, with identity
assert not state[1][RS.lower()]["complete"]                                                          # this run still queued paths
calls.clear(); state, t, q = scan_run(state, A1, files, calls)                                       # run 3: everything known -> complete
assert q == [] and t["known"] == 51 and state[1][RS.lower()]["complete"]                             # broken.opk NOT probed again
calls.clear(); state, t, q = scan_run(state, A1, files, calls)                                       # run 4: unchanged + complete
assert t.get("skipped") and q == [] and not any("/git/trees/" in u for u in calls) and sum(u.endswith("/commits/HEAD") for u in calls) == 1   # 1 request, no tree
files["apps/broken.opk"] = ("f" * 40, b"hsqs")                                                       # corrected replacement, new commit
calls.clear(); state, t, q = scan_run(state, A2, files, calls)
assert sum("/git/trees/" in u for u in calls) == 1 and q == ["apps/broken.opk"] and t["changed"] == 1   # changed commit inspected, fix examined
fixed = [v for v in state[0].values() if v["via"][0]["path"] == "apps/broken.opk" and v["via"][0]["blob"] == "f" * 40]
assert fixed and fixed[0]["state"] == "changed" and fixed[0]["previous"]["url"]                      # verified, flagged for review, history kept
# transient failures stay retryable: a 403 / timeout is not stored and the repo is not marked complete
files["apps/flaky.opk"] = ("9" * 40, b"hsqs")
for st_ in (403, 0):
    calls.clear(); state, t, q = scan_run(state, A3, files, calls, {"apps/flaky.opk": (st_, b"")})
    assert q == ["apps/flaky.opk"] and not state[1][RS.lower()]["complete"], (st_, q)                 # queued again every run
    assert not any(v["via"][0]["path"] == "apps/flaky.opk" for v in state[0].values())
calls.clear(); state, t, q = scan_run(state, A3, files, calls)                                       # recovers -> stored
assert q == ["apps/flaky.opk"] and any(v["via"][0]["path"] == "apps/flaky.opk" and v["state"] == "verified" for v in state[0].values())
# bounds and loading
many = {f"https://raw.githubusercontent.com/{RS}/{A1}/x{i}.opk": {"kind": "opk", "state": "rejected", "never_verified": True, "first_seen": f"2026-10-{1 + i % 28:02d}",
        "last_checked": "2026-10-29", "via": []} for i in range(C.REJECT_MAX + 7)}
many["https://x/tomb.opk"] = {"kind": "opk", "state": "rejected", "first_seen": "2025-01-01", "last_checked": "2025-01-01", "last_verified": "2025-01-01", "via": []}
C.update_packages(many, [], "2026-10-29"); assert sum(v.get("never_verified", False) for v in many.values()) == C.REJECT_MAX and "https://x/tomb.opk" in many
sp = os.path.join(tempfile.mkdtemp(), "tree-scans.json")
json.dump({"dev/pack": {"repo": "dev/pack", "commit": A1, "complete": True, "scanned": "2026-10-29"}, "bad": {"repo": "x"}, "other/r": {"repo": "Other/R", "commit": "zz", "complete": True, "scanned": "x"}}, open(sp, "w"))
assert list(C.load_scans(sp)) == ["dev/pack"]                                                        # malformed scan records dropped
C.fetch = real_fetch
print("tree scan efficiency tests OK")

# ---- GitHub release aliases: latest/download/<file> inherits this run's verified probe of the tagged asset, never name + size --
import re as _re
def zbytes(member, body):
    b = io.BytesIO(); z = zipfile.ZipFile(b, "w", zipfile.ZIP_STORED); z.writestr(member, body); z.close(); return b.getvalue()
def ranged(data, rng):
    a, b_ = map(int, _re.match(r"bytes=(\d+)-(\d+)", rng).groups()); b_ = min(b_, len(data) - 1)
    return 206, {"Content-Range": f"bytes {a}-{b_}/{len(data)}"}, data[a:b_ + 1]
def rel_fetch(repo, tag, assets, calls, broken=()):
    """assets: file -> bytes of the repo's latest release; latest/download serves the same bytes (as GitHub's redirect would)."""
    def f(url, rng=None, limit=0):
        calls.append(url)
        if url.endswith("/README.md"):
            return 200, {}, ("# Games for the RG Nano\n" + "".join(f"[{n}](https://github.com/{repo}/releases/latest/download/{n})\n" for n in ("Game.opk", "Pack.zip"))).encode(), url
        if url == f"https://github.com/{repo}/releases/latest": return 200, {}, b"", f"https://github.com/{repo}/releases/tag/{tag}"
        if "/expanded_assets/" in url: return 200, {}, "".join(f'<a href="/{repo}/releases/download/{tag}/{n}">' for n in assets).encode(), url
        m = _re.match(rf"https://github\.com/{repo}/releases/(?:download/{_re.escape(tag)}|latest/download)/(.+)$", url)
        if m and m[1] in assets and rng and url not in broken: return (*ranged(assets[m[1]], rng), url)
        return 404, {}, b"", url
    return f
RA, GAME, PACK = "dev/games", b"hsqs" + b"\0" * 60, zbytes("Pack/a.opk", b"hsqs" + b"\0" * 40)
LG, LP = f"https://github.com/{RA}/releases/latest/download/Game.opk", f"https://github.com/{RA}/releases/latest/download/Pack.zip"
T = lambda tag, n: f"https://github.com/{RA}/releases/download/{tag}/{n}"
def rel_run(tag, assets, broken=()):
    calls = []; C.fetch = rel_fetch(RA, tag, assets, calls, broken)
    c = C.Crawl(); c.do_repo(RA, {"from": "test"}, 0); c.run(); C.unique_apps(c); return c, calls   # judged, as in main()
c, calls = rel_run("v1", {"Game.opk": GAME, "Pack.zip": PACK})
assert LG not in calls and LP not in calls and T("v1", "Game.opk") in calls and T("v1", "Pack.zip") in calls      # latest URLs: no download at all
assert c.pkgs[LG]["alias_of"] == T("v1", "Game.opk") and c.pkgs[LG]["alias_tag"] == "v1" and c.pkgs[LG]["via"][0]["from"].endswith("README.md")
assert c.pkgs[f"{LP}!Pack/a.opk"]["container"] == LP and c.pkgs[f"{LP}!Pack/a.opk"]["magic_squashfs"] is True
apps = C.unique_apps(c); assert sorted(a["url"] for a in apps) == sorted([T("v1", "Game.opk"), T("v1", "Pack.zip")]) and all(not a.get("alias_of") for a in apps)   # no extra apps
st = {}; r = C.update_packages(st, c.pkgs.values(), "2026-10-28")
assert r["aliased"] == 2 and r["new"] == 4 and set(st) == {LG, LP, T("v1", "Game.opk"), T("v1", "Pack.zip")}       # both URLs kept
assert st[LG]["alias"] == {"of": T("v1", "Game.opk"), "tag": "v1", "at": "2026-10-28"} and st[LG]["verified_via"] == T("v1", "Game.opk") and st[LG]["via"][0]["from"].endswith("README.md")
assert st[LP]["size"] == st[T("v1", "Pack.zip")]["size"] == len(PACK) and st[LP]["members"] == ["a.opk"]           # ZIP size recorded
assert "alias" not in st[T("v1", "Game.opk")] and "verified_via" not in st[T("v1", "Game.opk")]
# recheck: a fresh alias costs nothing; its tagged twin still rotates; an expired alias is checked again
c = C.Crawl(); C.seed_packages(c, st, "2026-11-01"); assert set(c.recheck) == {T("v1", "Game.opk"), T("v1", "Pack.zip")}
c = C.Crawl(); C.seed_packages(c, st, "2026-11-12"); assert {LG, LP} <= set(c.recheck)                               # > ALIAS_DAYS
assert not C.alias_fresh({"alias": {"at": "garbage"}}, "2026-11-01") and not C.alias_fresh({"alias": "x"}, "2026-11-01")
# latest moves to v2 with a new Game.opk: alias follows the new tag, old tag kept as history, size change flagged
GAME2 = b"hsqs" + b"\1" * 90
c, calls = rel_run("v2", {"Game.opk": GAME2, "Pack.zip": PACK}); assert LG not in calls
r = C.update_packages(st, c.pkgs.values(), "2026-10-29")
assert r["alias_moved"] == 2 and st[LG]["alias"]["tag"] == "v2" and st[LG]["previous_alias"]["tag"] == "v1" and st[LG]["state"] == "changed"
assert st[LG]["previous"]["size"] == len(GAME) and T("v1", "Game.opk") in st and st[T("v1", "Game.opk")]["state"] == "verified"
# the file is missing from the latest tag: no alias, latest probed directly (and found missing)
c, calls = rel_run("v3", {"Pack.zip": PACK}); assert LG in calls and "alias_of" not in c.pkgs[LG] and c.pkgs[LG]["magic_squashfs"] is None
# the tagged probe fails: never inherited, latest probed normally and recorded as directly checked
c, calls = rel_run("v1", {"Game.opk": GAME, "Pack.zip": PACK}, broken={T("v1", "Game.opk")})
assert LG in calls and "alias_of" not in c.pkgs[LG] and c.pkgs[LG]["magic_squashfs"] is True and "alias_of" in c.pkgs[LP]
C.update_packages(st, c.pkgs.values(), "2026-10-30"); assert "verified_via" not in st[LG] and st[LG]["alias"]["at"] == "2026-10-29"   # history kept, ages out
# repo not visited this run, another repo's tag, and same name + size on other hosts: always probed, never aliased
C.fetch = rel_fetch(RA, "v1", {"Game.opk": GAME}, calls := [])
c = C.Crawl(); c.add_pkg("opk", LG, {"from": "x"}, 1); assert LG in calls and "alias_of" not in c.pkgs[LG]
c = C.Crawl(); c.releases["dev/other"] = {"tag": "v1", "assets": {"Game.opk": T("v1", "Game.opk")}}; c.add_pkg("opk", LG, {"from": "x"}, 1); assert "alias_of" not in c.pkgs[LG]
for u in ("https://static.miraheze.org/funkeywiki/1/1d/Game.opk", f"https://raw.githubusercontent.com/m/w/{'a' * 40}/files/Game.opk"):
    c.pkgs[u] = {"kind": "direct", "name": "Game.opk", "url": u, "size": len(GAME), "magic_squashfs": True, "via": []}
assert not c.alias("opk", "https://static.miraheze.org/funkeywiki/1/1d/Game.opk", {}, 1) and not any(p.get("alias_of") for p in c.pkgs.values())
# ZIP size: unknown -> recorded silently; a later different size is a change with the old size kept
zs = {}; zc = lambda size: {"kind": "zip-container", "url": "https://z.example/g.zip", "size": size, "note": ""}
zm = {"kind": "zip", "name": "a.opk", "url": "https://z.example/g.zip", "container": "https://z.example/g.zip", "size": 9, "host": "z.example", "repo": None, "via": [], "judgement": "installable", "magic_squashfs": True}
C.update_packages(zs, [zm], "2026-10-27"); assert zs["https://z.example/g.zip"]["size"] is None                         # old records: no size
C.update_packages(zs, [zc(500), zm], "2026-10-28"); assert zs["https://z.example/g.zip"]["size"] == 500 and zs["https://z.example/g.zip"]["state"] == "verified"
r = C.update_packages(zs, [zc(700), zm], "2026-10-29"); z = zs["https://z.example/g.zip"]
assert r["changed"] == 1 and z["state"] == "changed" and z["previous"]["size"] == 500 and z["size"] == 700
C.fetch = real_fetch
print("release alias tests OK")

# ---- submitted leads: maintainer-provided repository URLs, validated, crawled normally, reported apart, never auto-approved ----
ok_, bad_ = C.submitted_leads("https://github.com/Dev/Game.git, https://gitlab.com/grp/sub/player/ https://codeberg.org/o/r "
                              "https://GITHUB.com/dev/game http://github.com/a/b https://user:pw@github.com/a/b https://github.com:8443/a/b "
                              "https://github.com/a/b?tab=readme https://github.com/a/b#readme https://example.org/a/b https://www.github.com/a/b "
                              "https://raw.githubusercontent.com/a/b https://github.com/a https://github.com/a/b/blob/main/x.opk "
                              "https://gitlab.com/a/b/-/tree/main https://github.com/topics/funkey https://gitlab.com/explore/projects https://[x")
assert ok_ == [("repo", "Dev/Game", "https://github.com/Dev/Game.git"), ("forge", "gitlab.com/grp%2Fsub%2Fplayer|grp/sub/player", "https://gitlab.com/grp/sub/player"),
               ("forge", "codeberg.org/o/r", "https://codeberg.org/o/r")], ok_
assert [r for _, r in bad_] == ["duplicate", "not https", "credentials not allowed", "port not allowed", "query string not allowed", "fragment not allowed",
                                "unsupported host", "unsupported host", "unsupported host", "not a repository root", "not a repository root",
                                "not a repository root", "not a repository root", "not a repository root", "not a URL"], bad_
many_ = C.submitted_leads(" ".join(f"https://github.com/o/r{i}" for i in range(12)))
assert len(many_[0]) == C.SUBMIT_MAX and [r for _, r in many_[1]] == ["over the limit of 10"] * 2 and C.submitted_leads("") == ([], [])
# a GitLab repo whose name has no device keyword: README read, its external build link verified, kept apart from autonomous apps
def sub_run(readme, text):
    C.fetch = forge_fetch(readme); leads, _ = C.submitted_leads(text)
    c = C.Crawl()
    for kind, key, url in leads: c.push(kind, key, {"from": C.SUBMITTED, "anchor": url}, 0)
    c.run(); sub = C.mark_submitted(c, leads); return c, sub, C.unique_apps(c)
c, sub, apps = sub_run(README, "https://gitlab.com/someone/player")
s = sub[0]; inst = [p for p in s["packages"] if p.get("judgement") == "installable"]
assert s["reached"] and s["readme_status"] == 200 and [p["name"] for p in inst] == ["player.opk"] and inst[0]["magic_squashfs"] is True
assert apps == [] and all(p["via"][0] == {"from": C.SUBMITTED, "anchor": "https://gitlab.com/someone/player"} for p in s["packages"])   # not autonomous
st = {}; C.update_packages(st, c.pkgs.values(), "2026-10-28"); assert st[ZURL]["via"][0]["from"] == C.SUBMITTED and st[ZURL]["state"] == "verified"
c = C.Crawl(); C.seed_packages(c, st, "2026-11-20"); k_, key_, via_, _ = c.q[0]
assert key_ == ZURL and via_["first_found_via"] == C.SUBMITTED and C.is_submitted({"via": [via_]})                         # rechecks stay apart too
assert "Submitted leads (separate from the counts above): accepted / rejected / installable packages | 1 / 0 / 1" in C.stats_md(
    {"unique_installable_apps": [], "as_of": "2026-10-28", "submitted_leads": {"accepted": [{**s, "packages": [{"judgement": p.get("judgement")} for p in s["packages"]]}], "rejected": []}}, {})
# same repo found by autonomous discovery (forum link): counted as an autonomous app as before
C.fetch = forge_fetch(README); c = C.Crawl(); c.push("page", "https://forum.example.org/t/1", {"from": "test", "score": 5}, 0); c.run()
assert [a["name"] for a in C.unique_apps(c)] == ["player.opk"]
# a submitted repo for another device: inspected, its package still judged by the normal rules (not installable)
c, sub, apps = sub_run(README, "https://gitlab.com/someone/player")
c.repos["gitlab.com/someone%2fplayer|someone/player"]["verdict"] = "other_device"; C.unique_apps(c)
assert all(p["judgement"] == "false-positive" for p in sub[0]["packages"] if p["kind"] == "zip")                    # same exclusion rules as discovery
# rejected URLs are never queued, so never fetched
n0 = C.NREQ
c, sub, apps = sub_run("", "https://user:pw@gitlab.com/someone/player http://github.com/a/b https://gitlab.com/someone/player/-/raw/main/x.opk")
assert sub == [] and not c.pkgs and not c.repos and not c.pages and C.NREQ == n0   # nothing queued, no request made
C.fetch = real_fetch
print("submitted lead tests OK")

# ---- submitted-only mode: only the supplied repositories, never general discovery or historical rechecks, caches untouched ----------
import contextlib, json, tempfile, time, urllib.parse
SO_README = (f"# Game\nPorted for the Anbernic RG Nano.\n- [zip build]({ZURL})\n- [other repo](https://github.com/other/repo)\n"
             "- [author](https://github.com/otherowner)\n- [apps wiki](https://wiki.example.org/wiki/OPK_Applications)\n")
so_calls = []
def so_fetch(url, rng=None, limit=0):
    if C.NREQ >= C.MAX_REQ:   # same budget accounting as the real fetch()
        if not C.STOP: C.STOP.append("request cap")
        return -1, {}, b"", url
    C.NREQ += 1; so_calls.append(url)
    if url == "https://raw.githubusercontent.com/sub/game/HEAD/README.md": return 200, {}, SO_README.encode(), url
    if url == "https://github.com/sub/game/releases/latest": return 200, {}, b"", "https://github.com/sub/game/releases/tag/v1"
    if url == "https://github.com/sub/game/releases/expanded_assets/v1": return 200, {}, b'<a href="/sub/game/releases/download/v1/game.opk">x</a>', url
    if url == "https://github.com/sub/game/releases/download/v1/game.opk": return 206, {"Content-Range": "bytes 0-3/999"}, b"hsqs", url
    if url == "https://gitlab.com/api/v4/projects/someone%2Fplayer/repository/files/README.md/raw?ref=HEAD": return 200, {}, b"# Player\nBuilt for the RG Nano.\n", url
    if url == ZURL and rng:
        a, b = map(int, rng.removeprefix("bytes=").split("-"))
        return 206, {"Content-Range": f"bytes {a}-{min(b, len(ZD) - 1)}/{len(ZD)}"}, ZD[a:b + 1], url
    return 404, {}, b"", url
def so_main(*args):
    so_calls.clear(); C.NREQ, C.T0 = 0, time.time(); C.FAILS.clear(); C.STOP.clear()
    buf = io.StringIO(); old = sys.argv; sys.argv = ["crawl.py", "--submitted-only", *args]
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()): C.main()
    finally: sys.argv = old
    return buf.getvalue()
saved = C.fetch, C.MAX_REQ, C.DEADLINE_S, C.DELAY, C.seed, C.seed_multi, C.seed_freeserp, C.seed_packages
def forbidden(*a, **k): raise AssertionError("general discovery or historical recheck started in submitted-only mode")
C.fetch, C.DELAY = so_fetch, 0
C.seed = C.seed_multi = C.seed_freeserp = C.seed_packages = forbidden
with tempfile.TemporaryDirectory() as td:
    td = Path(td); (td / "cache").mkdir()
    keep = {"packages.json": json.dumps({"https://old.example.org/old.opk": {"kind": "opk", "state": "verified", "first_seen": "2026-01-01", "last_verified": "2026-01-01",
                                                                            "last_checked": "2026-01-01", "via": [{"from": "https://old.example.org/"}], "members": []}}),
            "freeserp.json": json.dumps({"https://x.example.org/p": {"last_seen": "2026-01-01", "queries": ["q"]}}), "seed.json": "{}"}
    for n, t in keep.items(): (td / "cache" / n).write_text(t, encoding="utf-8")
    def untouched(): return all((td / "cache" / n).read_text(encoding="utf-8") == t for n, t in keep.items()) and sorted(p.name for p in (td / "cache").iterdir()) == sorted(keep)
    caches = ["--package-leads", str(td / "cache/packages.json"), "--package-seed", str(td / "cache/seed.json"), "--lead-cache", str(td / "cache/freeserp.json")]
    md = so_main("--out", str(td / "o"), "--max-req", "99999", "--deadline", "99999", *caches,
                 "--submitted=https://github.com/sub/game https://gitlab.com/someone/player https://example.org/x")
    res = json.loads((td / "o/submitted-results.json").read_text(encoding="utf-8"))
    # budget: ceilings, not defaults; never the 1200-request crawl
    assert C.MAX_REQ == C.SUBMITTED_MAX_REQ < 1200 and C.DEADLINE_S == C.SUBMITTED_DEADLINE_S and res["limits"]["max_requests"] == C.SUBMITTED_MAX_REQ
    # nothing but the submitted repos and the package links they carry was requested
    hosts = {urllib.parse.urlsplit(u).netloc for u in so_calls}
    assert hosts <= {"raw.githubusercontent.com", "github.com", "api.github.com", "gitlab.com", "builds.example.org"}, hosts
    assert not [u for u in so_calls if any(x in u for x in ("freeserp", "/search", "advancedsearch", "tab=repositories", "other/repo", "otherowner", "wiki.example.org", "old.example.org", "codeberg.org"))], so_calls
    assert 0 < res["requests"] <= C.SUBMITTED_MAX_REQ and res["requests"] == len(so_calls)
    assert res["out_of_scope"] >= 3 and res["complete"], (res["out_of_scope"], res["incomplete_reasons"])   # skipped on purpose: not "incomplete"
    # per-lead report: README status, packages, OPK inside the ZIP, verification
    gh, gl = res["leads"]
    assert gh["reached"] and gh["readme_status"] == 200 and gh["release"] == "v1" and gl["reached"] and gl["readme_status"] == 200
    byk = {p["kind"]: p for p in gh["packages"]}
    assert byk["direct"]["name"] == "game.opk" and byk["direct"]["judgement"] == "installable"
    assert byk["zip-container"]["opks"] == 1 and byk["zip"]["path"] == "player/player.opk" and byk["zip"]["magic_squashfs"] is True and byk["zip"]["judgement"] == "installable"
    assert res["rejected"] == [{"url": "https://example.org/x", "reason": "unsupported host"}]
    for s in (f"{res['requests']} requests in", "README HTTP 200", "player/player.opk: installable", "OPK game.opk: installable", "Rejected inputs", "not read or changed", "nothing here is approved"):
        assert s in md or s in (td / "o/submitted-results.md").read_text(encoding="utf-8"), s
    # separate from autonomous statistics; no catalog/, no persistent store or cache written or changed (history and provenance kept)
    assert sorted(p.name for p in (td / "o").iterdir()) == ["submitted-results.json", "submitted-results.md"] and untouched()
    # a cut-short run says so
    so_main("--out", str(td / "o2"), "--max-req", "3", *caches, "--submitted=https://github.com/sub/game")
    r2 = json.loads((td / "o2/submitted-results.json").read_text(encoding="utf-8"))
    assert not r2["complete"] and any("not processed" in w or "request cap" in w for w in r2["incomplete_reasons"]) and r2["requests"] == 3 and untouched()
    # no valid URL: fails before any request, writes nothing
    for bad in ("", "https://example.org/x http://github.com/a/b"):
        try: so_main("--out", str(td / "o3"), *caches, f"--submitted={bad}"); raise AssertionError("must exit")
        except SystemExit as e: assert "no valid" in str(e)
        assert not so_calls and C.NREQ == 0 and not (td / "o3").exists() and untouched()
C.fetch, C.MAX_REQ, C.DEADLINE_S, C.DELAY, C.seed, C.seed_multi, C.seed_freeserp, C.seed_packages = saved
# the scope exists only in submitted-only mode: a normal crawl still queues pages, owners and other repos
assert C.Crawl().scope is None
c = C.Crawl(); c.push("page", "https://wiki.example.org/wiki/Apps", {"from": "t"}, 0); c.push("owner", "someone", {"from": "t"}, 0); c.push("repo", "a/b", {"from": "t"}, 0)
assert len(c.pq) == 1 and len(c.q) == 2 and c.out_of_scope == 0
c = C.Crawl(); c.scope = {("repo", "sub/game")}
for k_, v_ in (("page", "https://w.org/p"), ("owner", "o"), ("repo", "a/b"), ("forge", "codeberg.org/a/b"), ("ia", "ident"), ("repo", "sub/game"), ("opk", "https://x.org/a.opk"), ("zip", "https://x.org/a.zip")):
    c.push(k_, v_, {"from": "t"}, 0)
assert c.out_of_scope == 5 and [(k_, v_) for k_, v_, _, _ in c.q] == [("repo", "sub/game"), ("opk", "https://x.org/a.opk"), ("zip", "https://x.org/a.zip")] and not len(c.pq)
print("submitted-only tests OK")

# ---- README-mention search: bounded, paginated, deduplicated, fair (offline: C.api and sleep are stubs) -----------------
import urllib.parse
Q = C.readme_queries(C.PROF)
assert len(Q) == len(set(Q)) and all(x in Q for x in ('"rg nano" in:readme', '"funkeyos" in:readme', '"funkey s" in:readme', '"rg nano" opk in:readme', '"funkey" opk in:readme')), Q
assert Q[0] == '"rg nano" in:readme' and all("in:readme" in x for x in Q)   # direct device terms first; README mentions only
saved_api, saved_sleep = C.api, C.time.sleep
C.time.sleep = lambda s: None
calls = []
repo_ = lambda name, **kw: {"full_name": name, "description": "d", "topics": [], "pushed_at": "2024-01-01T00:00:00Z", "license": None, **kw}


def readme_crawl(table, stored=(), pre=()):
    """A Crawl whose search API serves table[(query, page)] -> items, or an HTTP status int."""
    c = C.Crawl(); c.stored_repos = set(stored); c.known_ids.add("known-app")
    for x in pre: c.push("repo", x, {"from": "t"}, 0)
    del calls[:]

    def fake(path):
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        key = (qs["q"][0], int(qs["page"][0])); calls.append(key)
        r = table.get(key, [])
        return (r, None) if isinstance(r, int) else (200, {"items": r})
    C.api = fake
    return c


# admission: repos named without any device term, buried at the end of page 1 and on page 2, behind many already-stored repos, are queued
fill = [repo_(f"old{i}/tool{i}") for i in range(46)]
buried = [repo_("dev1/zeta"), repo_("Dev2/Viewer"), repo_("dev3/bin")]
table = {(Q[0], 1): fill + buried + [repo_("dev4/late")], (Q[0], 2): [repo_("dev5/page-two")], (Q[1], 1): buried[:1] + [repo_("dev1/ZETA")]}
c = readme_crawl(table, stored=[f"old{i}/tool{i}" for i in range(46)])
notes = C.seed_readme(c)
assert notes == [] and {"dev1/zeta", "dev2/viewer", "dev3/bin", "dev4/late", "dev5/page-two"} <= c.readme_seeds
assert len(c.readme_seeds) == C.README_SEED_MAX and [k for _, k, _, _ in c.q][:5] == ["dev1/zeta", "Dev2/Viewer", "dev3/bin", "dev4/late", "dev5/page-two"]   # unstored repos first, then search rank
assert not any(r[0].startswith("dev1/zeta") and r[0] != "dev1/zeta" for r in [(k,) for _, k, _, _ in c.q]) and sum(k.lower() == "dev1/zeta" for _, k, _, _ in c.q) == 1   # case variants are one repo
assert c.dropped == {"readme search repos beyond per-run limit": 51 - C.README_SEED_MAX} and all(v["from"] == "github-search" and v["anchor"] in Q for _, _, v, _ in c.q)
# bounded pagination: page 2 only for the query whose page 1 was full, never more than README_QUERY_MAX requests
assert calls.count((Q[0], 2)) == 1 and sum(p == 2 for _, p in calls) == 1 and len(calls) == len(Q) + 1 <= C.README_QUERY_MAX
c = readme_crawl({(q, p): [repo_(f"o{p}/{n}") for n in range(C.README_PER_PAGE)] for q in Q for p in (1, 2)})
C.seed_readme(c)
assert len(calls) == C.README_QUERY_MAX and len(set(calls)) == len(calls) and len(c.readme_seeds) <= C.README_SEED_MAX
# dedup against other seeds, the catalog, and forks; a stored repo still queues when there is room
c = readme_crawl({(Q[0], 1): [repo_("pre/seeded"), repo_("x/known-app"), repo_("f/fork", fork=True), repo_("keep/stored"), repo_("bad"), repo_("a/b/c")]}, stored=["keep/stored"], pre=["pre/seeded"])
C.seed_readme(c)
assert c.readme_seeds == {"keep/stored"} and [k for _, k, _, _ in c.q] == ["pre/seeded", "keep/stored"]
# rate limit: stop at once, say so, queue nothing
c = readme_crawl({(Q[0], 1): 403, (Q[1], 1): [repo_("a/b")]})
notes = C.seed_readme(c)
assert len(calls) == 1 and len(notes) == 1 and "HTTP 403" in notes[0] and not c.readme_seeds and not c.q
# another failure is noted, the remaining queries still run
c = readme_crawl({(Q[0], 1): 500, (Q[1], 1): [repo_("a/b")]})
assert len(C.seed_readme(c)) == 1 and c.readme_seeds == {"a/b"}
# fairness: README-search repos take no slot from other discovery and are not starved by it
saved_max = C.MAX_REPOS
C.MAX_REPOS = 2
c = C.Crawl(); c.readme_seeds = {"s/one"}
C.fetch = lambda url, rng=None, limit=0: (404, {}, b"", url)
for name in ("a/one", "a/two", "s/one"): c.do_repo(name, {"from": "t"}, 0)
assert sorted(c.repos) == ["a/one", "a/two", "s/one"] and not c.dropped   # the seed fit beside two others
c.do_repo("a/three", {"from": "t"}, 0)
assert "a/three" not in c.repos and c.dropped == {"repo cap": 1}          # others stay capped at MAX_REPOS, seeds excluded from the count
c.readme_seeds.add("s/two"); c.do_repo("s/two", {"from": "t"}, 0)
assert "s/two" in c.repos
C.MAX_REPOS, C.fetch, C.api, C.time.sleep = saved_max, real_fetch, saved_api, saved_sleep
print("readme search tests OK")
