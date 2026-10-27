#!/usr/bin/env python3
"""Link-following candidate discovery. Seeds = GitHub repo search (profiles.json queries); everything else is found by
following links from READMEs and pages. No hardcoded source URLs. Bounded (requests, pages, repos, time), SSRF-guarded,
never downloads a whole package: OPKs are probed with a 4-byte Range read (squashfs magic), ZIPs by reading the central
directory with Range requests. Metadata only; never writes catalog/, never installs or approves anything.

  python discovery/crawl.py [--out build/discovery]
"""
import argparse, heapq, hashlib, http.client, ipaddress, json, os, re, socket, struct, sys, time, urllib.error, urllib.parse, urllib.request, zlib
from collections import deque
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover as D

UA = "retrohatch-discovery/1 (+https://github.com/traceroute87/RetroHatch)"
MAX_REQ, MAX_PAGES, MAX_REPOS, MAX_OWNERS, MAXD, DEADLINE_S, DELAY = 1500, 80, 160, 12, 4, 1500, 0.1
PER_HOST, LOW_PAGE_SHARE, VERIFY_RESERVE, GOOD = 8, 0.6, 0.85, 3   # pages per host; share of page budget open to low-score pages; request share after which only package checks run; "promising" score
RESERVED = {"topics", "orgs", "features", "sponsors", "about", "pricing", "marketplace", "login", "join", "settings",
            "collections", "explore", "enterprise", "search", "apps", "site", "customer-stories", "readme", "security", "trending"}
EXCLUDE = re.compile(r"theme|firmware|bootloader|kernel|skin|wallpaper|bios|toolchain", re.I)
HINT = re.compile(r"opk|funkey|rg[ -_]?nano|third[ -_]party|applications?|apps\b|games?|homebrew|collection|download|release|wiki|ports?", re.I)
NOISE = re.compile(r"[?&](action=(history|edit|info|submit|raw|purge)|oldid=|diff=|veaction=|printable=|curid=)|/Special:|/Talk:|/User:", re.I)   # wiki history/edit/special pages
STRONG = re.compile(r"opk|third[ -_]?party|homebrew|applications?|software|emulators?|downloads?|releases?|collections?|catalog", re.I)   # software-index / download vocabulary
JUNK_HOST = re.compile(r"(^|\.)(facebook|twitter|x|linkedin|pinterest|instagram|tiktok|youtube|youtu|whatsapp|wa|telegram|t|tumblr|amazon|ebay|aliexpress|alibaba|walmart|etsy|temu|banggood|paypal|patreon|ko-fi)\.(com|be|co|me|org|net|co\.uk|de)$", re.I)
JUNK_PATH = re.compile(r"/(share|sharer|intent|login|log-in|signin|sign-in|signup|sign-up|register|account|my-account|cart|checkout|basket|wishlist|privacy|terms|cookies?|contact|about-us|careers|newsletter|subscribe|shop|store|products?|buy)(/|$|\.php)|[?&](share|replytocom|add-to-cart)=|^mailto:", re.I)
JUNK_SHARE = re.compile(r"^((old\.)?reddit\.com/submit|share\.flipboard\.com/bookmarklet|getpocket\.com/save)(/|$|\?)", re.I)   # host-qualified share endpoints only
IMG = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|css|js|mp4|webm|pdf)(\?|$)", re.I)
LINK = re.compile(r'<a\s[^>]*?href=(?:["\']([^"\']+)["\']|([^\s"\'>]+))[^>]*>(.*?)</a>|\[([^\]]*)\]\(\s*<?(\S+?)>?\s*\)|(https?://[^\s<>"\')\]]+)', re.S | re.I)

PROF = json.loads((D.HERE / "profiles.json").read_text(encoding="utf-8"))["rg-nano"]
DRE, FRE = D.term_re(PROF["direct"]), D.term_re(PROF["family"])
ORE = D.term_re(PROF["other"])   # other devices: a package named for one of them is not for ours
T0, NREQ, FAILS, HOSTOK, STOP = time.time(), 0, [], {}, []


class Guard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(Guard)


def check(u):
    """Only public http(s) hosts (the crawl follows arbitrary links; never let it reach private or metadata addresses)."""
    p = urllib.parse.urlsplit(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("scheme")
    if p.hostname not in HOSTOK:
        try:
            HOSTOK[p.hostname] = all(ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(p.hostname, None))
        except (OSError, ValueError):
            HOSTOK[p.hostname] = False
    if not HOSTOK[p.hostname]:
        raise ValueError("non-public host")


def fetch(url, rng=None, limit=2_000_000):
    """-> (status, headers, body, final_url). status 0 = network error, -1 = refused (budget/time/unsafe)."""
    global NREQ
    if NREQ >= MAX_REQ or time.time() - T0 > DEADLINE_S:
        if not STOP: STOP.append("request cap" if NREQ >= MAX_REQ else "time limit")
        return -1, {}, b"", url
    try:
        check(url)
    except ValueError:
        return -1, {}, b"", url
    NREQ += 1
    time.sleep(DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": rng} if rng else {})})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok and urllib.parse.urlsplit(url).hostname == "api.github.com":
        req.add_unredirected_header("Authorization", f"Bearer {tok}")   # api.github.com only; never forwarded on a redirect
    try:
        with OPENER.open(req, timeout=20) as r:
            return r.status, r.headers, r.read(limit), r.geturl()
    except urllib.error.HTTPError as e:
        FAILS.append([url, e.code]); return e.code, e.headers, b"", url
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:   # e.g. InvalidURL for a link containing spaces
        FAILS.append([url, str(e)[:80]]); return 0, {}, b"", url


def J(b):
    try: return json.loads(b)
    except ValueError: return None


def api(path):
    st, h, b, _ = fetch(D.API + path)
    return st, (J(b) if st == 200 and b else None)


def total_size(h, st, n):
    cr = h.get("Content-Range") if h else None
    if cr and "/" in cr and cr.rsplit("/", 1)[1].isdigit():
        return int(cr.rsplit("/", 1)[1])
    cl = h.get("Content-Length") if h else None
    return int(cl) if st == 200 and cl and cl.isdigit() else None


# ---- packages ------------------------------------------------------------------------------------------------

def probe_opk(url):
    st, h, b, _ = fetch(url, "bytes=0-3", 4)
    return (b == b"hsqs") if st in (200, 206) else None, total_size(h, st, 4), st   # unreachable (403/404/login wall) = unknown, not "not an OPK"


def list_zip(url):
    """-> (zip_size, [{name, usize, comp, lho}], note). Central directory only, via Range."""
    st, h, _, _ = fetch(url, "bytes=0-0", 1)
    size = total_size(h, st, 1)
    if st not in (200, 206) or not size or size < 22:
        return size, [], f"zip size probe HTTP {st}"
    st, h, tail, _ = fetch(url, f"bytes={max(0, size - 66000)}-{size - 1}", 70000)
    if st not in (200, 206) or len(tail) < 22:
        return size, [], f"zip tail HTTP {st}"
    i = tail.rfind(b"PK\x05\x06")
    if i < 0:
        return size, [], "no end-of-central-directory"
    n, cdsz, cdoff = struct.unpack("<HII", tail[i + 10:i + 20])
    if cdoff == 0xFFFFFFFF or cdsz > 2_000_000:
        return size, [], "zip64 or oversized directory: not listed"
    start = size - len(tail) if st == 206 else 0
    if cdoff >= start:
        cd = tail[cdoff - start:cdoff - start + cdsz]
    else:
        _, _, cd, _ = fetch(url, f"bytes={cdoff}-{cdoff + cdsz - 1}", cdsz + 16)
    out, p = [], 0
    while p + 46 <= len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        comp, = struct.unpack("<H", cd[p + 10:p + 12])
        usz, = struct.unpack("<I", cd[p + 24:p + 28])
        nl, el, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
        lho, = struct.unpack("<I", cd[p + 42:p + 46])
        out.append({"name": cd[p + 46:p + 46 + nl].decode("utf-8", "replace"), "usize": usz, "comp": comp, "lho": lho})
        p += 46 + nl + el + cl
    return size, out, ""


def zip_member_is_opk(url, e):
    """Read the member's first bytes (Range) and check for squashfs magic. -> True | False | None (could not tell)."""
    st, _, b, _ = fetch(url, f"bytes={e['lho']}-{e['lho'] + 700}", 800)
    if st not in (200, 206) or len(b) < 30 or b[:4] != b"PK\x03\x04":
        return None
    nl, el = struct.unpack("<HH", b[26:30])
    data = b[30 + nl + el:]
    try:
        head = data[:4] if e["comp"] == 0 else zlib.decompressobj(-15).decompress(data, 8)[:4] if e["comp"] == 8 else None
    except zlib.error:
        return None
    return None if head is None else head == b"hsqs"


# ---- crawl ---------------------------------------------------------------------------------------------------

def links_of(text, base):
    out = {}
    for m in LINK.finditer(text or ""):
        if m.group(1) or m.group(2): href, anchor = m.group(1) or m.group(2), re.sub(r"<[^>]+>", "", m.group(3))
        elif m.group(5): href, anchor = m.group(5), m.group(4)
        else: href, anchor = m.group(6), ""
        u = urllib.parse.urljoin(base, re.sub(r"&amp;", "&", href.strip())).split("#")[0].rstrip(".,;")
        if u.startswith(("http://", "https://")) and not IMG.search(u) and not NOISE.search(u):
            out.setdefault(u, " ".join(anchor.split())[:80])
    return out


def classify(u):
    p = urllib.parse.urlsplit(u)
    host, path = p.netloc.lower().removeprefix("www."), p.path
    low = (path + ("?" + p.query if p.query else "")).lower()   # also catches download.php?file=X.opk
    raw = u.replace("/blob/", "/raw/") if host == "github.com" else u.replace("/-/blob/", "/-/raw/") if host == "gitlab.com" else u   # file view page -> the file itself
    if re.search(r"\.opk($|&)", low): return "opk", raw
    if re.search(r"\.zip($|&)", low): return "zip", raw
    seg = [s for s in path.split("/") if s]
    if host == "github.com" and seg and seg[0].lower() not in RESERVED:
        if len(seg) == 1: return "owner", seg[0]
        if not re.fullmatch(r"[\w.-]+", seg[1]): return None, u
        return "repo", f"{seg[0]}/{re.sub(r'[.]git$', '', seg[1])}"
    if host.endswith(("githubusercontent.com", "github.com")): return None, u
    if JUNK_HOST.search(host) or JUNK_PATH.search(low) or JUNK_SHARE.search(host + low): return None, u   # social sharing, login/account, retail/marketing: never queued
    return "page", u


def pscore(anchor, u):
    """How promising a link is as a software index / download page (0 = not worth a request)."""
    p = urllib.parse.urlsplit(u)
    t = anchor + " " + urllib.parse.unquote(p.path + " " + p.query)
    return 2 * len(STRONG.findall(t)) + len(HINT.findall(t)) + 2 * len(DRE.findall(D.norm(t)))


class PQ:
    """Page queue: seed leads (depth 0, independently found by a search) first, then best score first (FIFO among equals).
    Seeds are bounded (FS_MAX_PAGES), so derived links cannot starve them and they cannot starve derived links."""
    def __init__(self): self.h, self.n = [], 0
    def append(self, item): heapq.heappush(self.h, (item[3] > 0, -(item[2].get("score") or 0), self.n, item)); self.n += 1
    def popleft(self): return heapq.heappop(self.h)[-1]
    def __iter__(self): return (x[-1] for x in sorted(self.h))
    def __len__(self): return len(self.h)


class Crawl:
    def __init__(self):
        self.q, self.pq, self.seen = deque(), PQ(), set()   # pq: pages first (cheap, link-rich) so packages cannot starve them
        self.repos, self.pages, self.owners, self.pkgs, self.sites = {}, {}, {}, {}, {}
        self.known_src, self.known_ids = D.known_catalog()
        self.pending_meta, self.hosts, self.dropped = {}, {}, {}

    def drop(self, why): self.dropped[why] = self.dropped.get(why, 0) + 1

    def push(self, kind, key, via, depth):
        k = (kind, key.lower() if kind != "page" else key)
        if k in self.seen: 
            self._via(kind, key, via)
            return
        self.seen.add(k)
        (self.pq if kind == "page" else self.q).append((kind, key, via, depth))

    def _via(self, kind, key, via):
        d = {"repo": self.repos, "page": self.pages, "owner": self.owners}.get(kind, {}).get(key.lower() if kind != "page" else key)
        if d is not None and len(d["via"]) < 5 and via not in d["via"]: d["via"].append(via)

    def harvest(self, text, base, via, depth, relevant):
        """Queue what the page links to. Packages always; repos/owners/pages only from device-relevant text.
        relevant == "family" (page names only the device family, e.g. FunKey): follow promising page links only (score >= GOOD)."""
        scored = []
        for u, anchor in links_of(text, base).items():
            kind, key = classify(u)
            v = {"from": base, "anchor": anchor}
            if kind in ("opk", "zip"): self.push(kind, key, v, depth + 1)
            elif kind == "repo" and relevant is True: self.push(kind, key, v, depth + 1)
            elif kind == "page" and relevant and depth < MAXD:
                if "shields.io" in u: continue   # badge images are not pages
                s = pscore(anchor, u)
                if s and (relevant is True or s >= GOOD): scored.append((-s, u, {**v, "score": s}))
        for _, u, v in sorted(scored)[:6]:
            self.push("page", u, v, depth + 1)

    def do_page(self, url, via, depth):
        host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
        if len(self.pages) >= MAX_PAGES: return self.drop("page cap")
        if via.get("score", 0) < GOOD and len(self.pages) >= MAX_PAGES * LOW_PAGE_SHARE: return self.drop("page budget reserved for promising pages")
        if self.hosts.get(host, 0) >= PER_HOST: return self.drop("per-host limit")
        self.hosts[host] = self.hosts.get(host, 0) + 1
        st, h, b, final = fetch(url)
        rec = self.pages[url] = {"url": url, "status": st, "via": [via], "depth": depth, "relevant": False}
        if st != 200 or "html" not in (h.get("Content-Type") or "text/html").lower() and "text" not in (h.get("Content-Type") or "text"):
            return
        text = b.decode("utf-8", "replace")
        plain = D.norm(re.sub(r"<[^>]+>", " ", text))
        rec["relevant"] = bool(DRE.search(plain))
        rec["family"] = not rec["relevant"] and bool(FRE.search(plain))
        rec["host"] = urllib.parse.urlsplit(final).netloc.lower()
        self.harvest(text, final, via, depth, True if rec["relevant"] else "family" if rec["family"] else False)

    def do_owner(self, name, via, depth):
        if len(self.owners) >= MAX_OWNERS: return self.drop("owner cap")
        rec = self.owners[name.lower()] = {"owner": name, "via": [via], "repos": []}
        st, _, b, _ = fetch(f"https://github.com/{name}?tab=repositories")
        if st != 200: rec["status"] = st; return
        for m in re.finditer(r'href="/' + re.escape(name) + r'/([\w.-]+)" itemprop="name codeRepository"', b.decode("utf-8", "replace"), re.I):
            rec["repos"].append(f"{name}/{m.group(1)}")
        for full in rec["repos"][:30]:
            self.push("repo", full, {"from": f"https://github.com/{name}?tab=repositories", "anchor": "owner listing"}, depth + 1)

    def do_repo(self, full, via, depth):
        if len(self.repos) >= MAX_REPOS: return self.drop("repo cap")
        r = self.repos[full.lower()] = {"repo": full, "url": f"https://github.com/{full}", "via": [via], "meta": self.pending_meta.get(full.lower(), {}), "packages": [],
                                        "in_catalog": D.norm_url(f"https://github.com/{full}") in self.known_src or full.split("/")[1].lower() in self.known_ids}
        if r["in_catalog"]: return
        st, _, b, _ = fetch(f"https://raw.githubusercontent.com/{full}/HEAD/README.md")
        text = b.decode("utf-8", "replace")[:60000] if st == 200 else ""
        m = {"full_name": full, "name": full.split("/")[1], "html_url": r["url"], "description": r["meta"].get("description"), "topics": r["meta"].get("topics") or []}
        r["verdict"], r["evidence"] = D.analyze(m, None, (text, r["url"] + "#readme") if text else None, PROF)
        if text: self.harvest(text, r["url"] + "/blob/HEAD/README.md", via, depth, r["verdict"] in ("supports", "ambiguous", "family", "conflicting"))
        st, _, _, final = fetch(f"https://github.com/{full}/releases/latest")
        tm = re.search(r"/releases/tag/([^/?#]+)", final) if st == 200 else None
        if tm:
            r["release"] = urllib.parse.unquote(tm.group(1))
            st, _, b, _ = fetch(f"https://github.com/{full}/releases/expanded_assets/{tm.group(1)}")
            for href in dict.fromkeys(re.findall(r'href="(/[^"]+/releases/download/[^"]+)"', b.decode("utf-8", "replace"))):
                u = "https://github.com" + href
                if href.lower().endswith(".opk"): self.push("opk", u, {"from": r["url"] + "/releases/tag/" + tm.group(1), "anchor": "release asset", "repo": full}, depth + 1)
                elif href.lower().endswith(".zip"): self.push("zip", u, {"from": r["url"] + "/releases/tag/" + tm.group(1), "anchor": "release asset", "repo": full}, depth + 1)
            if r["verdict"] in ("supports", "family") and "/" in full:   # a device-relevant author: look at their other repos too
                self.push("owner", full.split("/")[0], {"from": r["url"], "anchor": "owner of relevant repo"}, depth + 1)

    def do_forge(self, key, via, depth):
        """key = 'codeberg.org/owner/repo' or 'gitlab.com/<id>|owner/repo'. Release assets via the forge's own API."""
        host, rest = key.split("/", 1)
        pid, full = (rest.split("|", 1) if host == "gitlab.com" else (None, rest))
        url = f"https://{host}/{full}"
        r = self.repos[key.lower()] = {"repo": key, "url": url, "via": [via], "meta": self.pending_meta.get(key.lower(), {}), "packages": [], "in_catalog": False}
        m = {"full_name": full, "name": full.split("/")[-1], "html_url": url, "description": r["meta"].get("description"), "topics": r["meta"].get("topics") or []}
        text = ""
        if host == "codeberg.org":
            st, _, b, _ = fetch(f"https://codeberg.org/api/v1/repos/{full}/raw/README.md")
            text = b.decode("utf-8", "replace")[:60000] if st == 200 else ""
        r["verdict"], r["evidence"] = D.analyze(m, None, (text, url) if text else None, PROF)
        if text: self.harvest(text, url, via, depth, r["verdict"] in ("supports", "ambiguous", "family", "conflicting"))
        if r["verdict"] in ("none", "other_device", "incompatible"): return
        if host == "codeberg.org":
            st, _, b, _ = fetch(f"https://codeberg.org/api/v1/repos/{full}/releases?limit=3")
            rels = (J(b) if st == 200 and b else None) or []
            rel = next((x for x in rels if not x.get("draft") and not x.get("prerelease")), None)
            urls = [a.get("browser_download_url") for a in (rel or {}).get("assets") or []]
            r["release"] = (rel or {}).get("tag_name")
        else:
            st, _, b, _ = fetch(f"https://gitlab.com/api/v4/projects/{pid}/releases?per_page=3")
            rels = (J(b) if st == 200 and b else None) or []
            urls =[l.get("direct_asset_url") or l.get("url") for l in ((rels[0].get("assets") or {}).get("links") or [])] if rels else []
            r["release"] = rels[0].get("tag_name") if rels else None
        for u in urls:
            if isinstance(u, str) and u.lower().endswith((".opk", ".zip")):
                self.push("opk" if u.lower().endswith(".opk") else "zip", u, {"from": url, "anchor": "release asset", "repo": key}, depth + 1)

    def do_ia(self, ident, via, depth):
        """Internet Archive item: list its files (metadata API), queue .opk/.zip."""
        st, _, b, _ = fetch(f"https://archive.org/metadata/{ident}")
        rec = self.repos[f"archive.org/{ident}".lower()] = {"repo": f"archive.org/{ident}", "url": f"https://archive.org/details/{ident}", "via": [via], "meta": {}, "packages": [], "in_catalog": False, "verdict": "supports"}
        files = ((J(b) or {}).get("files") if st == 200 and b else None) or []
        rec["files"] = [f.get("name") for f in files if str(f.get("name", "")).lower().endswith((".opk", ".zip", ".7z", ".img", ".rar", ".tar.gz"))][:40]
        for f in files:
            n = str(f.get("name", ""))
            if n.lower().endswith((".opk", ".zip")) and int(f.get("size") or 0) < 3_000_000_000:
                u = f"https://archive.org/download/{ident}/{urllib.parse.quote(n)}"
                self.push("opk" if n.lower().endswith(".opk") else "zip", u, {"from": rec["url"], "anchor": "archive.org file", "repo": rec["repo"]}, depth + 1)

    def add_pkg(self, kind, url, via, depth):
        repo = via.get("repo") or (re.match(r"https://github\.com/([\w.-]+/[\w.-]+)/", url) or [None, None])[1]
        host = urllib.parse.urlsplit(url).netloc.lower()
        if kind == "opk":
            ok, size, st = probe_opk(url)
            self.pkgs[url] = {"kind": "direct", "name": (re.findall(r"[^/&=?#]+\.opk", urllib.parse.unquote(url), re.I) or [url])[-1], "url": url, "container": None, "size": size,
                              "magic_squashfs": ok, "status": st, "repo": repo, "host": host, "via": [via]}
        else:
            zsize, ents, note = list_zip(url)
            opks = [e for e in ents if e["name"].lower().endswith(".opk") and not e["name"].endswith("/")]
            self.pkgs[url] = {"kind": "zip-container", "name": url.rsplit("/", 1)[1], "url": url, "size": zsize, "entries": len(ents), "opks": len(opks),
                              "note": note, "repo": repo, "host": host, "via": [via]}
            for k, e in enumerate(opks):
                ok = zip_member_is_opk(url, e) if k < 12 else None
                self.pkgs[f"{url}!{e['name']}"] = {"kind": "zip", "name": e["name"].rsplit("/", 1)[-1], "path": e["name"], "url": url, "container": url,
                                                   "size": e["usize"], "magic_squashfs": ok, "repo": repo, "host": host, "via": [via]}

    def run(self):
        n = 0
        while self.q or self.pq:
            n += 1   # pages (cheap, link-rich) go 2:1 ahead of packages/repos, but neither queue can starve the other
            kind, key, via, depth = (self.pq if self.pq and (n % 3 or not self.q) else self.q).popleft()
            if kind not in ("opk", "zip") and NREQ >= MAX_REQ * VERIFY_RESERVE: self.drop("requests reserved for package verification"); continue
            if kind == "page": self.do_page(key, via, depth)
            elif kind == "owner": self.do_owner(key, via, depth)
            elif kind == "forge": self.do_forge(key, via, depth)
            elif kind == "ia": self.do_ia(key, via, depth)
            elif kind == "repo": self.do_repo(key, via, depth)
            else: self.add_pkg(kind, key, via, depth)
            if NREQ >= MAX_REQ or time.time() - T0 > DEADLINE_S: break


# ---- results -------------------------------------------------------------------------------------------------

def seed(c):
    notes = []
    for q in PROF["queries"]:
        st, js = api(f"/search/repositories?q={urllib.parse.quote(q)}&per_page=30&sort=updated")
        if st != 200 or not js:
            notes.append(f"seed query {q!r}: HTTP {st}"); continue
        for r in js.get("items") or []:
            meta = {k: r.get(k) for k in ("description", "topics", "pushed_at", "fork", "archived")}
            meta["license"] = (r.get("license") or {}).get("spdx_id") or "unknown"
            c.push("repo", r["full_name"], {"from": "github-search", "anchor": q}, 0)
            c.pending_meta[r["full_name"].lower()] = meta
        time.sleep(1)
    return notes


def seed_multi(c):
    """Non-GitHub seeds from public search APIs: Codeberg (Gitea), GitLab, Internet Archive. Terms come from profiles.json."""
    notes = []
    terms = sorted({re.sub(r"\s+", "-", t) for t in PROF["direct"] + PROF["family"]} | {t.replace(" ", "") for t in PROF["direct"]})
    for t in terms:
        for host, u in (("codeberg.org", f"https://codeberg.org/api/v1/repos/search?q={urllib.parse.quote(t)}&limit=30"),
                        ("gitlab.com", f"https://gitlab.com/api/v4/projects?search={urllib.parse.quote(t)}&per_page=30&order_by=last_activity_at")):
            st, _, b, _ = fetch(u)
            if st != 200:
                notes.append(f"{host} search {t!r}: HTTP {st}"); continue
            js = J(b)
            for x in (js.get("data") if isinstance(js, dict) else js) or []:
                full = x.get("full_name") or x.get("path_with_namespace")
                key = f"{host}/{full}" if host == "codeberg.org" else f"{host}/{x['id']}|{full}"
                c.pending_meta[key.lower()] = {"description": x.get("description"), "topics": x.get("topics") or x.get("tag_list") or []}
                c.push("forge", key, {"from": f"{host}-search", "anchor": t}, 0)
    for qq in ('"rg nano"', "funkey", "rgnano", '"funkey s" opk'):
        st, _, b, _ = fetch(f"https://archive.org/advancedsearch.php?q={urllib.parse.quote(qq)}&fl[]=identifier&fl[]=title&rows=30&output=json")
        if st != 200:
            notes.append(f"archive.org search {qq!r}: HTTP {st}"); continue
        for d in ((J(b) or {}).get("response") or {}).get("docs") or []:
            if DRE.search(D.norm(d.get("title", ""))) or FRE.search(D.norm(d.get("title", ""))):
                c.push("ia", d["identifier"], {"from": "archive.org-search", "anchor": qq}, 0)
    return notes


# ---- optional channel: FreeSerp (documented keyless JSON search API) -----------------------------------------------
FS_URL, FS_MAX_REQ, FS_MAX_PAGES, CACHE_DAYS, CACHE_MAX = "https://freeserp.ai/api.php?index=web&size=10&q=", 16, 25, 90, 500


def walk(x, out):
    """Every dict carrying an http(s) url, whatever the envelope looks like."""
    if isinstance(x, dict):
        if isinstance(x.get("url"), str) and x["url"].startswith("http"): out.append(x)
        for v in x.values(): walk(v, out)
    elif isinstance(x, list):
        for v in x: walk(v, out)
    return out


def load_leads(path):
    try: d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    if not isinstance(d, dict): return {}
    ok = lambda u, v: isinstance(u, str) and u.startswith(("http://", "https://")) and isinstance(v, dict) and isinstance(v.get("last_seen"), str) and re.fullmatch(r"\d{4}-\d\d-\d\d", v["last_seen"])
    return {u: v for u, v in d.items() if ok(u, v)}   # a corrupt cache entry is dropped, never trusted; survivors still go through classify/check()/fetch like fresh results


def save_leads(path, leads, today):
    keep = {u: v for u, v in leads.items() if (date.fromisoformat(today) - date.fromisoformat(v["last_seen"])).days <= CACHE_DAYS}
    keep = dict(sorted(keep.items(), key=lambda kv: kv[1]["last_seen"], reverse=True)[:CACHE_MAX])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(keep, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def seed_freeserp(c, cache_path=None, today=None):
    """Optional web-search seeds. Queries are built from profile terms, results feed the normal queue (relevance gate, SSRF guard,
    link-following, dedup). Never raises and never marks the run incomplete: -> status dict reported as an optional channel."""
    today = today or date.today().isoformat()
    st_out = {"status": "ok", "requests": 0, "queries": 0, "results": 0, "new_leads": 0, "cached_leads": 0, "error": None}
    leads = load_leads(cache_path) if cache_path else {}
    cand = {}   # page url -> [score, hits, first-seen order, via]; admitted after all queries, best first (not first-come)

    def feed(url, title, snippet, query, cached, hits=1):
        text = D.norm(" ".join([url, title, snippet]))
        kind, key = classify(url)
        via = {"from": "freeserp-search", "anchor": query + (" [cached lead]" if cached else ""), "title": title[:80]}
        if kind in ("opk", "zip", "repo"): c.push(kind, key, via, 0)
        elif kind == "page" and (DRE.search(text) or FRE.search(text)):
            cand.setdefault(key, [max(GOOD + 1, pscore(title, url)), 0, len(cand), {**via, "score": max(GOOD + 1, pscore(title, url))}])[1] += hits

    def admit():
        """FS_MAX_PAGES distinct pages, ranked by score then by how many queries found them. A URL hit by several queries
        takes one slot, and leads from late queries compete with early ones on equal terms."""
        for _, _, _, key, via in sorted((-sc, -n, i, k, v) for k, (sc, n, i, v) in cand.items())[:FS_MAX_PAGES]:
            c.push("page", key, via, 0)
        st_out["pages_admitted"], st_out["pages_not_admitted"] = min(len(cand), FS_MAX_PAGES), max(0, len(cand) - FS_MAX_PAGES)

    for url, v in leads.items():
        feed(url, v.get("title", ""), "", (v.get("queries") or ["cache"])[0], True, len(v.get("queries") or []) or 1); st_out["cached_leads"] += 1
    try:
        return _search(leads, st_out, feed, cache_path, today)
    finally:
        admit()   # every exit path, including FreeSerp down: cached leads still get admitted


def _search(leads, st_out, feed, cache_path, today):
    terms = [t for t in PROF["direct"] + PROF["family"] if " " in t or t in PROF["family"]]   # "rg nano", "funkey os", "funkey s", "funkey"
    for suffix in ("opk download", "opk", "homebrew games", "emulators"):
        for t in terms:
            if st_out["requests"] >= FS_MAX_REQ: break
            q = f"{t} {suffix}"
            st_out["requests"] += 1
            st, _, b, _ = fetch(FS_URL + urllib.parse.quote_plus(q))
            js = J(b) if st == 200 and b else None
            if st != 200 or not isinstance(js, dict):
                st_out.update(status="unavailable", error=f"HTTP {st}" + ("" if st == 200 else "") + (" (not JSON)" if st == 200 else "")); return st_out
            if js.get("engine_error") or js.get("engine_fallback") or js.get("ok") is False:
                st_out.update(status="degraded", error=str(js.get("engine_error") or "engine_fallback")[:80]); return st_out   # HTTP 200 but no real search happened
            st_out["queries"] += 1
            for h in walk(js.get("results"), []):
                u, title = h["url"].split("#")[0], str(h.get("title") or "")
                st_out["results"] += 1
                new = u not in leads
                rec = leads.setdefault(u, {"first_seen": today, "queries": [], "title": title[:100]})
                rec["last_seen"] = today
                if q not in rec["queries"]: rec["queries"] = (rec["queries"] + [q])[:5]
                st_out["new_leads"] += new
                feed(u, title, str(h.get("snippet") or h.get("description") or ""), q, False)
            time.sleep(0.4)
    if cache_path and st_out["results"]: save_leads(cache_path, leads, today)
    return st_out


def judge(p, c):
    """-> ('installable' | 'false-positive', reason)."""
    if EXCLUDE.search(p["name"]): return "false-positive", "name looks like theme/firmware/bootloader/kernel/toolchain"
    if p["magic_squashfs"] is False: return "false-positive", "not a squashfs OPK (magic mismatch)"
    if ORE.search(D.norm(p["name"] + " " + (p["repo"] or ""))) and not DRE.search(D.norm(p["name"] + " " + (p["repo"] or ""))):
        return "false-positive", "named for another device"
    r = c.repos.get((p["repo"] or "").lower())
    if r and r.get("verdict") in ("incompatible", "other_device"): return "false-positive", f"repo evidence: {r['verdict']}"
    if r and r.get("in_catalog"): return "false-positive", "already in catalog"
    if p["magic_squashfs"] is None:
        return "unverified", f"download not reachable (HTTP {p['status']})" if p["kind"] == "direct" else "OPK inside ZIP; magic not read (member limit/unreadable)"
    return "installable", "squashfs magic verified" + (" inside ZIP" if p["kind"] == "zip" else "")


def assess(notes, queue_left, stop, fails, dropped=None):
    """Reasons this run must NOT be treated as authoritative (empty list = complete)."""
    why = list(notes)
    if stop: why.append(f"stopped early: {stop[0]}")
    if queue_left: why.append(f"{queue_left} queued items not processed")
    lim = {k: v for k, v in (dropped or {}).items() if k != "per-host limit"}   # per-host is deliberate noise control, the rest is budget exhaustion
    if lim: why.append("coverage-limited, results are NOT exhaustive: " + ", ".join(f"{k} ({v} skipped)" for k, v in sorted(lim.items())))
    rl = [u for u, s in fails if s == 429 or (s == 403 and "api.github.com" in str(u))]
    if rl: why.append(f"rate limited ({len(rl)} responses, e.g. {rl[0][:80]})")
    return why


def report(res, c):
    ok = res["complete"]
    L = [f"# Crawl discovery: {'COMPLETE' if ok else 'INCOMPLETE, NOT AUTHORITATIVE'}", ""]
    R = res["incomplete_reasons"]
    L += [f"- incomplete because: {w}" for w in R[:6]] + ([f"- ...and {len(R) - 6} more (see discovery-results.json)"] if len(R) > 6 else [])
    L += [f"As of {res['as_of']}; {'authenticated' if res['authenticated'] else 'UNAUTHENTICATED'}; {res['requests']} requests in {res['seconds']} s "
          f"(limits {res['limits']['max_requests']} requests); caps hit: {', '.join(res['caps_hit']) or 'none'}.",
          f"{len(res['unique_installable_apps'])} unique OPKs (squashfs magic verified), {len(res['repos'])} repos, {len(res['pages'])} pages.",
          "**Candidates only: nothing here is approved, tested or installed.**" + ("" if ok else " Do not use this run to conclude something is absent."), "",
          "## Unique OPKs", "", "| App | Size B | License | Download | Found via |", "|---|---|---|---|---|"]
    for a in res["unique_installable_apps"]:
        v = a["via"][0]
        L.append(f"| {a['name']}{' (in ZIP)' if a['kind'] == 'zip' else ''} | {a['size']} | {a.get('license') or '?'} | {a['url']} | {v['from'][:80]} |")
    bad = [p for p in res["packages"] if p.get("judgement") == "false-positive"]
    L += ["", "## Excluded", ""] + [f"- {p['name']}: {p['reason']} <{p['url']}>" for p in bad] + ([] if bad else ["None."])
    L += ["", "## Optional channels (a failure here never makes the run incomplete)", ""] + [f"- {k}: {v}" for k, v in res.get("optional_channels", {}).items()]
    L += ["", "## Relevant sites reached", ""] + [f"- {h}: {u[0]}" for h, u in sorted(res["relevant_sites"].items())]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(D.ROOT / "build" / "discovery"))
    ap.add_argument("--no-github-seed", action="store_true", help="seed only from non-GitHub search APIs")
    ap.add_argument("--max-req", type=int); ap.add_argument("--deadline", type=int)
    ap.add_argument("--no-freeserp", action="store_true", help="skip the optional FreeSerp web-search seeds")
    ap.add_argument("--lead-cache", default=None, help="JSON file of FreeSerp leads kept between runs")
    a = ap.parse_args()
    global MAX_REQ, DEADLINE_S
    MAX_REQ, DEADLINE_S = a.max_req or MAX_REQ, a.deadline or DEADLINE_S
    c = Crawl()
    notes, optional = [], {}
    try:
        notes = ([] if a.no_github_seed else seed(c)) + seed_multi(c)
        optional["freeserp"] = {"status": "disabled"} if a.no_freeserp else seed_freeserp(c, a.lead_cache)
        c.run()
    except Exception as e:   # a crash must still leave a report that says INCOMPLETE
        notes.append(f"crawl error: {type(e).__name__}: {e}"[:200])
    apps = {}
    for p in c.pkgs.values():
        if p["kind"] == "zip-container": continue
        verdict, why = judge(p, c)
        p["judgement"], p["reason"] = verdict, why
        if verdict == "installable":
            key = (p["name"].lower(), p["size"])
            a_ = apps.setdefault(key, {**p, "also_via": [], "license": ((c.repos.get((p["repo"] or "").lower()) or {}).get("meta") or {}).get("license")})
            if a_ is not p: a_["also_via"] += p["via"]
    uniq = sorted(apps.values(), key=lambda x: (x["repo"] or x["host"], x["name"].lower()))
    why = assess(notes, len(c.q) + len(c.pq), STOP, FAILS, c.dropped)
    caps = [n for n, hit in (("repos", len(c.repos) >= MAX_REPOS), ("pages", len(c.pages) >= MAX_PAGES), ("owners", len(c.owners) >= MAX_OWNERS)) if hit]
    sites = {}
    for pg in c.pages.values():
        if pg["status"] == 200 and pg.get("relevant"): sites.setdefault(pg.get("host"), []).append(pg["url"])
    res = {"as_of": date.today().isoformat(), "authenticated": bool(os.environ.get("GITHUB_TOKEN")), "requests": NREQ, "seconds": round(time.time() - T0),
           "limits": {"max_requests": MAX_REQ, "max_pages": MAX_PAGES, "max_repos": MAX_REPOS, "max_depth": MAXD}, "seed_notes": notes,
           "unique_installable_apps": uniq,
           "packages": [p for p in c.pkgs.values()],
           "repos": list(c.repos.values()), "pages": list(c.pages.values()), "owners": list(c.owners.values()),
           "relevant_sites": sites, "skipped": c.dropped, "failures": FAILS[:60], "optional_channels": optional}
    res.update(complete=not why, incomplete_reasons=why, caps_hit=caps)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "discovery-results.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if a.lead_cache and Path(a.lead_cache).is_file(): (out / "freeserp-leads.json").write_bytes(Path(a.lead_cache).read_bytes())   # artifact carries the cache the next run will restore
    md = report(res, c)
    (out / "discovery-results.md").write_text(md, encoding="utf-8")
    digest = hashlib.sha256("\n".join(sorted(f"{x['name'].lower()}:{x['size']}" for x in uniq)).encode()).hexdigest()[:12]
    (out / "summary.json").write_text(json.dumps({"complete": not why, "reasons": why, "caps_hit": caps, "skipped": c.dropped, "apps": len(uniq), "digest": digest, "authenticated": res["authenticated"],
                                                  "requests": NREQ, "seconds": res["seconds"]}) + "\n")
    print(md.split("## Unique")[0])   # the status header goes to the step summary


if __name__ == "__main__":
    main()
