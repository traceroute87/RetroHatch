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
r3 = C.seed_freeserp(C.Crawl(), None); assert r3["status"] == "degraded" and r3["requests"] == 1, r3
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
