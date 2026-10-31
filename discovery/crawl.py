#!/usr/bin/env python3
"""Link-following candidate discovery. Seeds = GitHub repo search (profiles.json queries); everything else is found by
following links from READMEs and pages. No hardcoded source URLs. Bounded (requests, pages, repos, time), SSRF-guarded,
never downloads a whole package: OPKs are probed with a 4-byte Range read (squashfs magic), ZIPs by reading the central
directory with Range requests. Metadata only; never writes catalog/, never installs or approves anything.

  python discovery/crawl.py [--out build/discovery]
"""
import argparse, collections, heapq, hashlib, http.client, ipaddress, json, os, re, socket, struct, sys, time, urllib.error, urllib.parse, urllib.request, zlib
from collections import deque
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover as D

UA = "retrohatch-discovery/1 (+https://github.com/traceroute87/RetroHatch)"
MAX_REQ, MAX_PAGES, MAX_REPOS, MAX_OWNERS, MAXD, DEADLINE_S, DELAY = 1500, 80, 160, 12, 4, 1500, 0.1
PER_HOST, LOW_PAGE_SHARE, VERIFY_RESERVE, GOOD, TREE_MAX, TREE_RUN_MAX = 8, 0.6, 0.85, 3, 40, 120   # TREE_RUN_MAX: tree package probes per run, all repos   # pages per host; share of page budget open to low-score pages; request share after which only package checks run; "promising" score
README_QUERY_MAX, README_PER_PAGE, README_PAGES, README_SEED_MAX = 16, 50, 2, 30   # README-mention search: requests, results per page, pages per query, new repos queued per run (own repo slots on top of MAX_REPOS)
RESERVED = {"topics", "orgs", "features", "sponsors", "about", "pricing", "marketplace", "login", "join", "settings",
            "collections", "explore", "enterprise", "search", "apps", "site", "customer-stories", "readme", "security", "trending"}
FORGE_RESERVED = {"explore", "users", "user", "groups", "dashboard", "help", "api", "search", "projects", "admin", "snippets", "topics",
                  "org", "repo", "assets", "-", "login", "sign_in", "users_sign_in", "notifications"}   # gitlab.com / codeberg.org non-project paths
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
    if host in ("gitlab.com", "codeberg.org") and len(seg) >= 2 and seg[0].lower() not in FORGE_RESERVED:
        proj = seg[:seg.index("-")] if "-" in seg else seg          # GitLab: "/-/" ends the (sub)group/project path
        if host == "codeberg.org": proj = proj[:2]                  # Codeberg: owner/repo, the rest is a file view
        full = "/".join(urllib.parse.unquote(x) for x in proj).removesuffix(".git")
        if len(proj) < 2 or not all(re.fullmatch(r"[\w.-]+", x) for x in full.split("/")): return None, u
        return "forge", (f"codeberg.org/{full}" if host == "codeberg.org" else f"gitlab.com/{urllib.parse.quote(full, safe='')}|{full}")
    if JUNK_HOST.search(host) or JUNK_PATH.search(low) or JUNK_SHARE.search(host + low): return None, u   # social sharing, login/account, retail/marketing: never queued
    return "page", u


def link_template(u):
    """URL pattern for harvest diversity: host + path with digit runs collapsed + query keys (values dropped).
    download.php?themeid=3860 and ?themeid=3861 share one pattern; /wiki/Apps and /wiki/Ports do not."""
    p = urllib.parse.urlsplit(u)
    return p.netloc.lower() + re.sub(r"\d+", "#", p.path) + "?" + "&".join(sorted(k for k, _ in urllib.parse.parse_qsl(p.query, keep_blank_values=True)))


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
        self.tree_known = {}   # (repo lower, path) -> {"blob", "url"} of files already in the package store (set by main())
        self.tree_left, self.tree_salt = TREE_RUN_MAX, str(T0)
        self.tree_scans = {}   # repo lower -> {"repo", "commit", "complete", "scanned", "packages"}, kept between runs (set by main())
        self.scope, self.out_of_scope = None, 0   # submitted-only mode: the only repos/forge projects that may be queued (set by submitted_only())
        self.stored_repos, self.readme_seeds = set(), set()   # repos with packages in the store (set by main()); lower-case repos queued by README search
        self.releases, self.deferred = {}, set()   # repo lower -> {"tag", "assets": {file name: tagged URL}} resolved THIS run; latest URLs requeued once

    def drop(self, why): self.dropped[why] = self.dropped.get(why, 0) + 1

    def repo_capped(self, key):
        """README-search repos have their own README_SEED_MAX slots on top of MAX_REPOS: they take none from other discovery and are not starved by it."""
        return key.lower() not in self.readme_seeds and len(self.repos) - sum(k in self.repos for k in self.readme_seeds) >= MAX_REPOS

    def push(self, kind, key, via, depth):
        if self.scope is not None and kind not in ("opk", "zip") and (kind, key.lower()) not in self.scope:
            self.out_of_scope += 1; return   # submitted-only: no pages, owners or other repos; deliberate, so not counted as budget exhaustion
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
            elif kind in ("repo", "forge") and relevant is True: self.push(kind, key, v, depth + 1)
            elif kind == "page" and relevant and depth < MAXD:
                if "shields.io" in u: continue   # badge images are not pages
                s = pscore(anchor, u)
                if s and (relevant is True or s >= GOOD): scored.append((-s, u, {**v, "score": s}))
        per, picked = {}, 0
        for _, u, v in sorted(scored):   # best first, at most 2 links per URL pattern, so 6 near-identical links cannot take every slot
            t = link_template(u)
            if per.get(t, 0) >= 2: continue
            per[t] = per.get(t, 0) + 1; picked += 1
            self.push("page", u, v, depth + 1)
            if picked == 6: break

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
        if self.repo_capped(full): return self.drop("repo cap")
        r = self.repos[full.lower()] = {"repo": full, "url": f"https://github.com/{full}", "via": [via], "meta": self.pending_meta.get(full.lower(), {}), "packages": [],
                                        "in_catalog": D.norm_url(f"https://github.com/{full}") in self.known_src or full.split("/")[1].lower() in self.known_ids}
        if r["in_catalog"]: return
        st, _, b, _ = fetch(f"https://raw.githubusercontent.com/{full}/HEAD/README.md")
        r["readme_status"] = st
        text = b.decode("utf-8", "replace")[:60000] if st == 200 else ""
        m = {"full_name": full, "name": full.split("/")[1], "html_url": r["url"], "description": r["meta"].get("description"), "topics": r["meta"].get("topics") or []}
        r["verdict"], r["evidence"] = D.analyze(m, None, (text, r["url"] + "#readme") if text else None, PROF)
        if text: self.harvest(text, r["url"] + "/blob/HEAD/README.md", via, depth, r["verdict"] in ("supports", "ambiguous", "family", "conflicting"))
        st, _, _, final = fetch(f"https://github.com/{full}/releases/latest")
        tm = re.search(r"/releases/tag/([^/?#]+)", final) if st == 200 else None
        if tm:
            r["release"] = urllib.parse.unquote(tm.group(1))
            st, _, b, _ = fetch(f"https://github.com/{full}/releases/expanded_assets/{tm.group(1)}")
            rel = self.releases[full.lower()] = {"tag": r["release"], "assets": {}}
            for href in dict.fromkeys(re.findall(r'href="(/[^"]+/releases/download/[^"]+)"', b.decode("utf-8", "replace"))):
                u = "https://github.com" + href
                if href.lower().startswith(f"/{full}/releases/download/{tm.group(1)}/".lower()):   # this repo's latest tag only
                    rel["assets"][urllib.parse.unquote(href.rsplit("/", 1)[1])] = u
                if href.lower().endswith(".opk"): self.push("opk", u, {"from": r["url"] + "/releases/tag/" + tm.group(1), "anchor": "release asset", "repo": full}, depth + 1)
                elif href.lower().endswith(".zip"): self.push("zip", u, {"from": r["url"] + "/releases/tag/" + tm.group(1), "anchor": "release asset", "repo": full}, depth + 1)
            if r["verdict"] in ("supports", "family") and "/" in full:   # a device-relevant author: look at their other repos too
                self.push("owner", full.split("/")[0], {"from": r["url"], "anchor": "owner of relevant repo"}, depth + 1)
        if r["verdict"] in ("supports", "family", "ambiguous"): self.do_tree(full, r, depth)

    def do_tree(self, full, r, depth):
        """Packages stored in the repository's files, not only release assets. 2 API requests (commit, recursive tree). Only the
        profile's package extensions (.opk for the Nano: tree ZIPs were 0/50 useful). Files already in the package store are skipped
        unless their git blob changed (then re-queued, flagged with the previous URL); unseen files are taken in a per-run shuffled
        order, so successive runs cover a large tree instead of the same first entries. At most TREE_MAX per repo and TREE_RUN_MAX
        per run. URLs pin the commit SHA (immutable); identity is repo + path; every package keeps the repo for judge()."""
        if self.tree_left <= 0: return self.drop("tree budget")
        st, js = api(f"/repos/{full}/commits/HEAD")
        sha = (js or {}).get("sha") if isinstance(js, dict) else None
        if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
            r["tree"] = {"status": st}; return
        prev = self.tree_scans.get(full.lower()) or {}
        if prev.get("commit") == sha and prev.get("complete"):   # same commit, every package path already stored or rejected: nothing new
            r["tree"] = {"status": st, "commit": sha, "skipped": "unchanged commit, fully enumerated"}; return
        st, js = api(f"/repos/{full}/git/trees/{sha}?recursive=1")
        items = (js or {}).get("tree") if isinstance(js, dict) else None
        if not isinstance(items, list):
            r["tree"] = {"status": st, "commit": sha}; return
        ext = tuple(e.lower() for e in PROF.get("package_ext") or [".opk"])
        pk = [x for x in items if x.get("type") == "blob" and isinstance(x.get("path"), str) and x["path"].lower().endswith(ext)]
        changed, unseen = [], []
        for x in pk:
            k = self.tree_known.get((full.lower(), x["path"]))
            if k is None: unseen.append(x)
            elif x.get("sha") and k["blobs"] and x["sha"] not in k["blobs"]: changed.append(x)
        tie = lambda x: hashlib.sha256((self.tree_salt + full + x["path"]).encode()).hexdigest()
        take = (changed + sorted(unseen, key=tie))[:min(TREE_MAX, self.tree_left)]
        self.tree_left -= len(take)
        # complete only when nothing is left to look at: an unfinished, changed or transiently failing path keeps the repo scanned
        self.tree_scans[full.lower()] = {"repo": full, "commit": sha, "complete": not (changed or unseen or js.get("truncated")),
                                         "scanned": date.today().isoformat(), "packages": len(pk)}
        r["tree"] = {"status": st, "commit": sha, "packages": len(pk), "known": len(pk) - len(unseen) - len(changed), "changed": len(changed),
                     "unseen": len(unseen), "queued": len(take), "truncated": bool(js.get("truncated")) or len(changed) + len(unseen) > len(take)}
        for x in take:
            u = f"https://raw.githubusercontent.com/{full}/{sha}/" + urllib.parse.quote(x["path"])
            v = {"from": f"https://github.com/{full}/tree/{sha}", "anchor": "repository file", "path": x["path"], "repo": full, "commit": sha, "blob": x.get("sha")}
            if x in changed: v["previous_url"] = self.tree_known[(full.lower(), x["path"])]["url"]
            self.push("opk" if x["path"].lower().endswith(".opk") else "zip", u, v, depth + 1)

    def do_forge(self, key, via, depth):
        """key = 'codeberg.org/owner/repo' or 'gitlab.com/<url-encoded path>|group/sub/project'. README and release assets via the
        forge's own API. A README device claim is candidate evidence for following its links, never proof of compatibility."""
        if self.repo_capped(key): return self.drop("repo cap")
        host, rest = key.split("/", 1)
        pid, full = (rest.split("|", 1) if host == "gitlab.com" else (None, rest))
        url = f"https://{host}/{full}"
        r = self.repos[key.lower()] = {"repo": key, "url": url, "via": [via], "meta": self.pending_meta.get(key.lower(), {}), "packages": [], "in_catalog": False}
        m = {"full_name": full, "name": full.split("/")[-1], "html_url": url, "description": r["meta"].get("description"), "topics": r["meta"].get("topics") or []}
        text = ""
        st, _, b, _ = fetch(f"https://codeberg.org/api/v1/repos/{full}/raw/README.md" if host == "codeberg.org" else
                            f"https://gitlab.com/api/v4/projects/{pid}/repository/files/README.md/raw?ref=HEAD")
        text = b.decode("utf-8", "replace")[:60000] if st == 200 else ""
        r["readme_status"] = st
        r["verdict"], r["evidence"] = D.analyze(m, None, (text, url) if text else None, PROF)
        r["verdict_basis"] = "readme claim (candidate evidence)" if text else "metadata"
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

    def alias(self, kind, url, via, depth):
        """A github.com/<repo>/releases/latest/download/<file> link is the asset of the repo's latest release. When this run resolved
        that tag, listed <file> among its assets and verified the tagged URL, the latest URL inherits that probe instead of downloading
        the same file again; the record says so (alias_of, alias_tag). Anything less (repo not visited, file not in the tag, tagged
        probe failed or not run yet) -> False: probed normally. Name and size never establish an alias."""
        m = LATEST.match(url)
        rel = self.releases.get(m[1].lower()) if m else None
        t = rel and rel["assets"].get(urllib.parse.unquote(m[2]))
        if not t: return False
        tp = self.pkgs.get(t)
        if tp is None and url not in self.deferred:   # the tagged asset is still queued (pushed after the README link): look again after it
            self.deferred.add(url); self.q.append((kind, url, via, depth)); return True
        mem = [p for p in self.pkgs.values() if p.get("container") == t]
        if not tp or (tp.get("magic_squashfs") is not True if kind == "opk" else tp.get("note") or not mem or any(p.get("magic_squashfs") is not True for p in mem)):
            return False
        link = {"url": url, "via": [via], "alias_of": t, "alias_tag": rel["tag"]}
        self.pkgs[url] = {**tp, **link}
        for p in mem: self.pkgs[f"{url}!{p['path']}"] = {**p, **link, "container": url}
        return True

    def add_pkg(self, kind, url, via, depth):
        if self.alias(kind, url, via, depth): return
        gh = lambda s: (re.match(r"https://(?:github\.com|raw\.githubusercontent\.com)/([\w.-]+/[\w.-]+)/", s or "") or [None, None])[1]
        fk = classify(via.get("from") or "")   # a GitLab/Codeberg README link: its forge project key
        repo = via.get("repo") or gh(url) or gh(via.get("from")) or (fk[1] if fk[0] == "forge" else None)   # raw URLs and README links keep the repo, so judge() sees its verdict
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
    return notes + seed_readme(c)


def readme_queries(prof):
    """Search strings from the device profile: every device term, then each term with each package extension (direct terms first)."""
    terms = list(dict.fromkeys(prof["direct"] + prof["family"]))
    exts = [e.lstrip(".") for e in prof.get("package_ext") or []]
    return [f'"{t}" in:readme' for t in terms] + [f'"{t}" {x} in:readme' for x in exts for t in terms]


def seed_readme(c):
    """Repositories whose README mentions the device, whatever their names say. Bounded: README_QUERY_MAX search requests,
    README_PAGES pages per query (page 2 only when page 1 was full). Deduplicated by lower-case repo before queueing: a repo already
    queued by another seed is not queued again; catalog repos and forks are skipped. At most README_SEED_MAX new repos
    are queued (repos without stored packages first, then more matching queries, then search rank); they use their own repo slots."""
    notes, found, spent = [], {}, 0
    pause = 1 if os.environ.get("GITHUB_TOKEN") else 6.5   # unauthenticated search allows ~10 requests per minute
    for page in range(1, README_PAGES + 1):
        for q in readme_queries(PROF):
            if spent >= README_QUERY_MAX: break
            if page > 1 and len(found.get(q, ())) < README_PER_PAGE * (page - 1): continue
            st, js = api(f"/search/repositories?q={urllib.parse.quote(q)}&per_page={README_PER_PAGE}&page={page}")
            spent += 1
            if st != 200 or not js:
                notes.append(f"readme search {q!r} page {page}: HTTP {st}")
                if st in (403, 429): return notes   # rate limited: stop, do not hammer
                continue
            found.setdefault(q, []).extend(js.get("items") or [])
            time.sleep(pause)
    uniq = {}
    for q, items in found.items():
        for r in items:
            full = r.get("full_name") if isinstance(r, dict) else None
            if isinstance(full, str) and full.count("/") == 1: uniq.setdefault(full.lower(), {"r": r, "q": []})["q"].append(q)
    new = []
    for key, e in uniq.items():
        r = e["r"]
        if ("repo", key) in c.seen: continue   # already queued by another seed
        if r.get("fork") or D.norm_url(f"https://github.com/{key}") in c.known_src or key.split("/")[1] in c.known_ids: continue
        new.append((key in c.stored_repos, -len(e["q"]), len(new), key))
    for _, _, _, key in sorted(new)[:README_SEED_MAX]:
        r = uniq[key]["r"]
        c.pending_meta[key] = {**{k: r.get(k) for k in ("description", "topics", "pushed_at", "fork", "archived")}, "license": (r.get("license") or {}).get("spdx_id") or "unknown"}
        c.readme_seeds.add(key)
        c.push("repo", r["full_name"], {"from": "github-search", "anchor": uniq[key]["q"][0]}, 0)
    for _ in new[README_SEED_MAX:]: c.drop("readme search repos beyond per-run limit")
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
                key = f"{host}/{full}" if host == "codeberg.org" else f"{host}/{urllib.parse.quote(full, safe='')}|{full}"   # same key as a link to it
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


def load_leads(path, field="last_seen"):
    try: d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    if not isinstance(d, dict): return {}
    ok = lambda u, v: isinstance(u, str) and u.startswith(("http://", "https://")) and isinstance(v, dict) and isinstance(v.get(field), str) and re.fullmatch(r"\d{4}-\d\d-\d\d", v[field])
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
        if kind in ("opk", "zip", "repo", "forge"): c.push(kind, key, via, 0)
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


def fs_queries(today):
    """Device terms x profile search categories (software, applications, ports, ... not only games). When there are more queries
    than FS_MAX_REQ, a different window is used each day so every category is searched over consecutive runs."""
    terms = [t for t in PROF["direct"] + PROF["family"] if " " in t or t in PROF["family"]]   # "rg nano", "funkey os", "funkey s", "funkey"
    qs = [f"{t} {sfx}" for sfx in PROF.get("search_suffixes") or ("opk download", "opk", "homebrew games", "emulators") for t in terms]
    if len(qs) <= FS_MAX_REQ: return qs
    k = date.fromisoformat(today).toordinal() * FS_MAX_REQ % len(qs)
    return (qs[k:] + qs[:k])[:FS_MAX_REQ]


def _search(leads, st_out, feed, cache_path, today):
    retried = False
    for q in fs_queries(today):
        js = None
        while st_out["requests"] < FS_MAX_REQ:
            st_out["requests"] += 1
            st, _, b, _ = fetch(FS_URL + urllib.parse.quote_plus(q))
            js = J(b) if st == 200 and b else None
            if st != 200 or not isinstance(js, dict):
                st_out.update(status="unavailable", error=f"HTTP {st}" + (" (not JSON)" if st == 200 else "")); return st_out
            if not (js.get("engine_error") or js.get("engine_fallback") or js.get("ok") is False): break   # a real search happened
            if retried or st_out["requests"] >= FS_MAX_REQ:   # HTTP 200 but no real search happened, even after the one retry
                st_out.update(status="degraded", error=str(js.get("engine_error") or "engine_fallback")[:80]); return st_out
            retried, st_out["retried"], js = True, q, None   # one delayed retry per run, inside FS_MAX_REQ and the fetch() limits
            time.sleep(2)
        if js is None: break   # request budget spent
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


def inaccessible(pages):
    """Hosts that refused this runner (401/403/451). Recorded, never retried through another endpoint, proxy or disguise."""
    out = {}
    for pg in pages:
        if pg["status"] in (401, 403, 451): out.setdefault(urllib.parse.urlsplit(pg["url"]).netloc.lower(), []).append([pg["url"], pg["status"]])
    return out


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
    pl = res.get("package_leads")
    if pl: L += ["", "## Package lead store (candidates only, separate from catalog/)", "",
                 f"- {pl['stored_before']} stored before, {pl['stored_after']} after; {pl['verified']} verified this run ({pl['new']} new), "
                 f"{pl['changed']} CHANGED (size/contents differ; review), {pl['unreachable']} unreachable download URLs (kept), {pl.get('unverified_members', 0)} unverified ZIP members, {pl['rejected']} rejected, {pl['stale']} newly stale; "
                 f"{pl['rechecked']} stored URLs rechecked this run (max {RECHECK_MAX})"]
    sl = res.get("submitted_leads") or {}
    if sl.get("accepted") or sl.get("rejected"):
        L += ["", "## Submitted leads (maintainer-provided, NOT autonomous discoveries; candidates only, never auto-approved)", ""]
        for s in sl.get("accepted", []):
            ok_ = [p for p in s["packages"] if p["judgement"] == "installable"]
            L.append(f"- {s['url']}: {'reached' if s['reached'] else 'NOT reached'}, verdict {s['verdict']}, README HTTP {s['readme_status']}, "
                     f"release {s['release'] or 'none'}; {len(ok_)} installable of {len(s['packages'])} linked packages")
            L += [f"  - {p['name']}: {p['judgement']} ({p['reason']}) <{p['url']}>" for p in s["packages"] if p["kind"] != "zip-container"]
        L += [f"- rejected {r['url']}: {r['reason']}" for r in sl.get("rejected", [])]
    blk = res.get("inaccessible_sources") or {}
    L += ["", "## Inaccessible sources (refused this runner; content unknown, not evidence of absence)", ""] + [f"- {h}: HTTP {u[0][1]} on {len(u)} page(s), e.g. {u[0][0]}" for h, u in sorted(blk.items())] + ([] if blk else ["None."])
    L += ["", "## Relevant sites reached", ""] + [f"- {h}: {u[0]}" for h, u in sorted(res["relevant_sites"].items())]
    return "\n".join(L) + "\n"


# ---- package lead store: verified download URLs kept between runs, separate from catalog/ -----------------------------------
LATEST = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/releases/latest/download/([^/?#]+)$")
ALIAS_DAYS = 14   # a latest/download alias not re-established for this long is rechecked like any other URL
PKG_MAX, RECHECK_MAX, REJECT_MAX, SCAN_MAX = 2000, 60, 500, 2000   # stored entries (~650 B each in the Actions cache); request budget for re-probing stored URLs per run (rotating, least recently checked first)
# state: verified | unreachable (last check failed) | stale (not verified for CACHE_DAYS) | changed (size/contents differ from what
# was verified) | rejected (answered with a non-SquashFS body). Nothing is deleted on age; rejected entries stay as tombstones so a
# committed snapshot cannot resurrect them.


def recheck_order(store, today):
    """Stored URLs to re-probe, fairest first: least recently checked; within one date, hosts take turns (one URL per host per
    round), and the order inside a host is shuffled per day. Without this, equal dates fell back to URL order, so github.com
    always beat every other host and external leads were never rechecked. checked_at (seconds) separates runs on the same date."""
    tie = lambda u: hashlib.sha256((today + u).encode()).hexdigest()
    when = lambda u: (store[u].get("last_checked") or "", store[u].get("checked_at") or 0)
    live = sorted((u for u, v in store.items() if v.get("state") != "rejected"), key=lambda u: (when(u), tie(u)))
    rank, per = {}, {}
    for u in live:
        k = (when(u), urllib.parse.urlsplit(u).netloc.lower())
        rank[u] = per[k] = per.get(k, -1) + 1
    return sorted(live, key=lambda u: (when(u), rank[u], tie(u)))


def seed_packages(c, store, today=None):
    """Re-queue stored URLs at depth 0 in recheck_order(), within RECHECK_MAX requests (OPK = 1 Range read, ZIP = 3 + one per
    member, max 12). Each is fetched like any discovered link (check(), Range probe, judge()), so a source page that later
    blocks us (403) does not hide packages it once linked to. -> number of URLs queued (the list is kept in c.recheck)."""
    cost, c.recheck, today = 0, [], today or date.today().isoformat()
    for url in recheck_order(store, today):
        if alias_fresh(store[url], today): continue   # its tagged twin is the one checked; no budget spent on the same file twice
        w = 1 if store[url]["kind"] == "opk" else 3 + min(12, len(store[url].get("members") or []))
        if cost + w > RECHECK_MAX: continue   # a cheaper entry may still fit; a skipped one keeps its old date and leads next run
        cost += w; c.recheck.append(url)
    for url in c.recheck:
        v = store[url]
        c.push(v["kind"], url, {"from": "package-lead-store", "anchor": "previously verified " + v["last_verified"], "repo": v.get("repo"),
                                "first_found_via": (v.get("via") or [{}])[0].get("from")}, 0)
    return len(c.recheck)


def alias_fresh(v, today):
    """A latest/download URL whose alias to a verified tagged asset was established within ALIAS_DAYS."""
    try: return (date.fromisoformat(today) - date.fromisoformat((v.get("alias") or {})["at"])).days <= ALIAS_DAYS
    except (KeyError, TypeError, ValueError): return False   # none or malformed: rechecked normally


def load_scans(path):
    """Tree-scan progress kept between runs; malformed entries are dropped (a dropped entry only costs a rescan)."""
    try: d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    ok = lambda v: isinstance(v, dict) and isinstance(v.get("repo"), str) and isinstance(v.get("commit"), str) and re.fullmatch(r"[0-9a-f]{40}", v["commit"]) \
        and isinstance(v.get("complete"), bool) and isinstance(v.get("scanned"), str)
    return {k: v for k, v in d.items() if ok(v) and k == v["repo"].lower()} if isinstance(d, dict) else {}


def tree_known(store):
    """(repo lower, path) -> {"blobs": every git blob already stored for that file, "url": its most recent URL}, so tree scans skip
    known versions (store order is irrelevant: it is reloaded sorted by URL) and a changed file points back to its latest version."""
    out = {}
    recent = lambda u: (store[u].get("first_seen") or "", store[u].get("checked_at") or 0)
    for url in sorted(store, key=recent):
        for via in store[url].get("via") or []:
            if via.get("path") and via.get("repo"):
                k = out.setdefault((via["repo"].lower(), via["path"]), {"blobs": set(), "url": url})
                k["url"] = url
                if via.get("blob"): k["blobs"].add(via["blob"])
    return out


def recheck_stats(store, due, start):
    """This run only (not historical states): of the stored URLs queued for recheck, how many were fetched, verified, unreachable.
    "This run" = checked_at at or after the run's start time (dates alone cannot separate several runs on one day)."""
    out = {}
    for side in ("github", "external"):
        us = [u for u in due if ("github" in urllib.parse.urlsplit(u).netloc.lower()) == (side == "github")]
        done = [u for u in us if u in store and (store[u].get("checked_at") or 0) >= start]
        ok = [u for u in done if store[u].get("last_status") == "ok"]
        out[side] = {"queued": len(us), "processed": len(done), "verified": len(ok), "unreachable": len(done) - len(ok)}
    return out


def update_packages(store, pkgs, today, now=None):
    """-> per-run counts (distinct URLs). Verified packages are added/refreshed; a different size or ZIP member set marks the entry
    "changed" (previous values kept); an unreachable download URL is kept and marked; a non-SquashFS body marks "rejected";
    long-unverified ones turn "stale". A ZIP member whose header was not read is "unverified", not an unreachable URL."""
    n = {"changed": 0, "rejected": 0, "stale": 0, "unverified_members": 0, "alias_moved": 0}
    ok, new, down, aliased = set(), set(), set(), set()
    seen_zip, zsize = {}, {}
    for p in pkgs:
        if p["kind"] == "zip-container":   # the ZIP's own reachability: its directory could not be listed
            old = store.get(p["url"])
            if old and p.get("note"): down.add(p["url"]); old.update(last_checked=today, last_status=p["note"][:60])
            elif p.get("size"): zsize[p["url"]] = p["size"]
            continue
        url, kind = (p["url"], "opk") if p["kind"] == "direct" else (p["container"], "zip")
        old = store.get(url)
        if p.get("judgement") == "installable":
            ok.add(url)
            if old is None: new.add(url)
            rec = store.setdefault(url, {"kind": kind, "first_seen": today, "via": [], "members": []})
            prev = next((v["previous_url"] for v in p["via"] if v.get("previous_url")), None)
            if old is None and prev:   # same repo path, new git blob: a changed file, not silently a new or the same one
                rec["state"], rec["previous"] = "changed", {"url": prev, "last_verified": (store.get(prev) or {}).get("last_verified")}; n["changed"] += 1
            if kind == "zip":
                seen_zip.setdefault(url, set()).add(p["name"])
            elif rec.get("size") not in (None, p["size"]) or rec.get("state") == "rejected":
                rec["previous"] = {"size": rec.get("size"), "last_verified": rec.get("last_verified"), "state": rec.get("state")}
                rec["state"] = "changed"; n["changed"] += 1
            rec.update(name=p["name"] if kind == "opk" else url.rsplit("/", 1)[-1], size=p["size"] if kind == "opk" else rec.get("size"), host=p["host"],
                       repo=p.get("repo"), last_verified=today, last_checked=today, last_status="ok")
            rec["state"] = "changed" if rec.get("state") == "changed" else "verified"   # "changed" stays until a human reviews it
            if p.get("alias_of"):   # verified through the tagged asset probed this run; a different tag = latest moved (kept as history)
                a = {"of": p["alias_of"], "tag": p["alias_tag"], "at": today}
                if (rec.get("alias") or {}).get("tag") not in (None, a["tag"]): rec["previous_alias"] = rec["alias"]; n["alias_moved"] += 1
                rec["alias"], rec["verified_via"] = a, p["alias_of"]; aliased.add(url)
            else: rec.pop("verified_via", None)   # probed directly this run
            for v in p["via"]:
                if v.get("from") != "package-lead-store" and v not in rec["via"]: rec["via"] = (rec["via"] + [v])[:3]   # original provenance only
        elif old and p.get("magic_squashfs") is False and p.get("status") in (200, 206):
            old.update(state="rejected", last_checked=today, last_status=f"HTTP {p.get('status')}, not SquashFS"); n["rejected"] += 1
        elif p.get("magic_squashfs") is False and p.get("status") in (200, 206) and any(v.get("path") and v.get("repo") for v in p["via"]):
            # a repository file that answered with something that is not SquashFS (e.g. a committed HTML error page): remember it with
            # its repo/path/blob so tree scans skip the same blob; a new blob is examined again. Transient failures are not stored.
            store[url] = {"kind": kind, "state": "rejected", "never_verified": True, "first_seen": today, "last_checked": today, "name": p["name"],
                          "size": p.get("size"), "host": p["host"], "repo": p.get("repo"), "members": [],
                          "last_status": f"HTTP {p.get('status')}, not SquashFS", "via": [v for v in p["via"] if v.get("from") != "package-lead-store"][:3]}
            down.add(url); n["rejected"] += 1
        elif p.get("magic_squashfs") is None and kind == "zip":
            n["unverified_members"] += 1   # member header not read (member limit/unreadable); says nothing about the URL
        elif old and p.get("magic_squashfs") is None:
            down.add(url); old.update(last_checked=today, last_status=f"HTTP {p.get('status')}")
    for url in down - ok:
        if store[url].get("state") in (None, "verified"): store[url]["state"] = "unreachable"
    nv = sorted((u for u, v in store.items() if v.get("never_verified") and v.get("state") == "rejected"), key=lambda u: store[u]["first_seen"])
    for u in nv[:max(0, len(nv) - REJECT_MAX)]: del store[u]   # bound for never-verified rejects; tombstones of verified files stay
    for url, names in seen_zip.items():
        rec, names, size = store[url], sorted(names), zsize.get(url) or store[url].get("size")
        if rec["members"] and set(names) != set(rec["members"]) or rec.get("size") not in (None, size):   # ZIP size: unknown before, recorded now
            rec["previous"] = {"members": rec["members"], "size": rec.get("size"), "last_verified": rec.get("last_verified")}
            rec["state"] = "changed"; n["changed"] += 1
        rec["members"], rec["size"] = names[:50], size
    for v in store.values():
        if v.get("state") in (None, "verified", "unreachable") and (date.fromisoformat(today) - date.fromisoformat(v["last_verified"])).days > CACHE_DAYS:
            v["state"] = "stale"; n["stale"] += 1   # kept, never deleted for age
    if len(store) > PKG_MAX:   # storage bound only: stale, then unreachable, then oldest verified; tombstones never
        order = {"stale": 0, "unreachable": 1}
        live = sorted((u for u in store if store[u].get("state") != "rejected"), key=lambda u: (order.get(store[u].get("state"), 2), store[u]["last_verified"]))
        for u in live[:len(store) - PKG_MAX]: del store[u]
    now = int(time.time() if now is None else now)
    for url in ok | down:
        if url in store: store[url]["checked_at"] = now
    return {"verified": len(ok), "new": len(new), "unreachable": len(down - ok - {u for u in store if store[u].get("state") == "rejected"}), "aliased": len(aliased), **n}


def stats_md(res, store):
    """Key numbers for the Actions job summary, so the run can be reviewed without downloading the artifact."""
    apps, today = res["unique_installable_apps"], res["as_of"]
    gh = sum("github" in (a.get("host") or "") for a in apps)
    st = collections.Counter(v.get("state") or "verified" for v in store.values())
    pl, fs = res.get("package_leads") or {}, (res.get("optional_channels") or {}).get("freeserp") or {}
    sub = res.get("submitted_leads") or {}
    new, fresh = pl.get("new", 0), pl.get("verified", 0)   # this run's own counts, not dates (several runs can share a date)
    L = ["## Crawl statistics", "", "| | |", "|---|---|",
         f"| Verified OPKs (unique) | {len(apps)} |", f"| GitHub-hosted / other hosts | {gh} / {len(apps) - gh} |",
         f"| Package lead store (historical states) | {len(store)} entries: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())) + " |",
         f"| New this run / re-verified / retained (not verified this run) | {new} / {fresh - new} / {len(store) - fresh} |",
         f"| Stored URLs rechecked this run | {pl.get('rechecked', 0)} queued (budget {RECHECK_MAX} requests) |"] + [
         f"| Recheck this run, {side} | {r['queued']} queued, {r['processed']} fetched, {r['verified']} verified, {r['unreachable']} unreachable |"
         for side, r in (pl.get("recheck") or {}).items()] + [
         f"| This run: verified URLs / unreachable download URLs / unverified ZIP members | {pl.get('verified', 0)} / {pl.get('unreachable', 0)} / {pl.get('unverified_members', 0)} |",
         f"| This run: latest/download URLs verified via their tagged release asset / latest moved to a new tag | {pl.get('aliased', 0)} / {pl.get('alias_moved', 0)} |",
         f"| Submitted leads (separate from the counts above): accepted / rejected / installable packages | {len(sub.get('accepted', []))} / {len(sub.get('rejected', []))} / "
         f"{sum(p['judgement'] == 'installable' for s in sub.get('accepted', []) for p in s['packages'])} |",
         f"| FreeSerp | {fs.get('status', 'n/a')}: {fs.get('queries', 0)}/{fs.get('requests', 0)} queries ok, {fs.get('results', 0)} results, "
         f"{fs.get('new_leads', 0)} new leads, {fs.get('cached_leads', 0)} cached{', error ' + str(fs['error']) if fs.get('error') else ''} |",
         f"| Inaccessible sources | {', '.join(sorted(res.get('inaccessible_sources') or {})) or 'none'} |", ""]
    for state in ("changed", "unreachable", "stale", "rejected"):
        rows = sorted((u, v) for u, v in store.items() if v.get("state") == state)
        if rows:
            L += [f"**{state.capitalize()} packages ({len(rows)})**", ""] + [f"- {v.get('name') or u} ({v.get('last_status', '')}): {u}" for u, v in rows[:15]] + \
                 ([f"- ...and {len(rows) - 15} more"] if len(rows) > 15 else []) + [""]
    return "\n".join(L)


# ---- submitted leads: maintainer-provided repository URLs (workflow input), crawled like any other repo, reported apart --------
SUBMITTED, SUBMIT_MAX = "submitted-lead", 10
SUBMITTED_MAX_REQ, SUBMITTED_DEADLINE_S = 250, 300   # submitted-only budget: hard ceilings, --max-req/--deadline can only lower them
FORGE_KIND = {"github.com": "repo", "gitlab.com": "forge", "codeberg.org": "forge"}


def submitted_leads(text):
    """Whitespace/comma separated repository URLs -> ([(kind, key, url)], [(url, reason)]). Only the https root URL of a
    GitHub, GitLab or Codeberg repository is accepted; anything else is rejected and never fetched."""
    ok, bad, keys = [], [], set()
    for u in re.split(r"[\s,]+", text or ""):
        if not u: continue
        try: p = urllib.parse.urlsplit(u); host = (p.hostname or "").lower(); p.port
        except ValueError: bad.append((u[:200], "not a URL")); continue
        seg = [s for s in p.path.split("/") if s]
        why = ("too long" if len(u) > 300 else "not https" if p.scheme != "https" else "credentials not allowed" if "@" in p.netloc
               else "port not allowed" if p.port is not None else "query string not allowed" if p.query or "?" in u
               else "fragment not allowed" if p.fragment or "#" in u else "unsupported host" if host not in FORGE_KIND
               else "not a repository root" if not all(re.fullmatch(r"[\w.-]+", s) for s in seg) or len(seg) < 2 or "-" in seg or (host != "gitlab.com" and len(seg) != 2) else None)
        kind, key = classify(f"https://{host}/" + "/".join(seg)) if not why else (None, None)
        if not why and kind != FORGE_KIND[host]: why = "not a repository root"   # e.g. github.com/topics/x, gitlab.com/explore/x
        if not why and key.lower() in keys: why = "duplicate"
        if not why and len(ok) >= SUBMIT_MAX: why = f"over the limit of {SUBMIT_MAX}"
        if why: bad.append((u[:200], why)); continue
        keys.add(key.lower()); ok.append((kind, key, f"https://{host}/" + "/".join(seg)))
    return ok, bad


def mark_submitted(c, leads):
    """Packages linked directly from a submitted repository (README, release assets, repository files) get a leading
    {"from": "submitted-lead"} provenance entry: kept out of the autonomous app count, now and when the store rechecks them.
    A package also found autonomously earlier in the run keeps its autonomous provenance (first discovery wins).
    -> per lead {"url", "key", "reached", "verdict", "readme_status", "release", "packages": [package dicts]}."""
    out = []
    for kind, key, url in leads:
        r = c.repos.get(key.lower()) or {}
        base = (r.get("url") or "").lower()
        frm = lambda v: (v.get("from") or "").lower()
        pk = [p for p in c.pkgs.values() if base and any(frm(v) == base or frm(v).startswith(base + "/") for v in p["via"])]
        for p in pk:
            if p["via"][0].get("from") != SUBMITTED: p["via"].insert(0, {"from": SUBMITTED, "anchor": url})
        out.append({"url": url, "key": key, "reached": bool(r), "verdict": r.get("verdict"), "readme_status": r.get("readme_status"),
                    "release": r.get("release"), "packages": pk})
    return out


def is_submitted(p):
    return any(v.get("from") == SUBMITTED or v.get("first_found_via") == SUBMITTED for v in p["via"])


def unique_apps(c):
    """Judge every probed package (sets judgement/reason in place) -> installable apps, one per (name, size). Packages from
    submitted leads are judged the same way but reported apart, never counted as autonomous discoveries."""
    apps = {}
    for p in c.pkgs.values():
        if p["kind"] == "zip-container": continue
        verdict, why = judge(p, c)
        p["judgement"], p["reason"] = verdict, why
        if why in ("named for another device", "repo evidence: other_device"): p["other_device_evidence"] = why   # kept for future profiles, never installable here
        if verdict == "installable" and not p.get("alias_of") and not is_submitted(p):   # an alias is the same file as its tagged asset, never a second app
            key = (p["name"].lower(), p["size"])
            a_ = apps.setdefault(key, {**p, "also_via": [], "license": ((c.repos.get((p["repo"] or "").lower()) or {}).get("meta") or {}).get("license")})
            if a_ is not p: a_["also_via"] += p["via"]
    return sorted(apps.values(), key=lambda x: (x["repo"] or x["host"], x["name"].lower()))


def submitted_report(res):
    ok = res["complete"]
    L = [f"# Submitted-only discovery: {'COMPLETE' if ok else 'INCOMPLETE, NOT AUTHORITATIVE'}", ""]
    L += [f"- incomplete because: {w}" for w in res["incomplete_reasons"]]
    L += [f"As of {res['as_of']}; {'authenticated' if res['authenticated'] else 'UNAUTHENTICATED'}; {res['requests']} requests in {res['seconds']} s "
          f"(limits {res['limits']['max_requests']} requests, {res['limits']['deadline_s']} s); {res['out_of_scope']} out-of-scope links not followed.",
          "**Candidates only: nothing here is approved, tested, installed or written to catalog/. Package lead stores and caches were not read or changed.**", ""]
    for s in res["leads"]:
        L += [f"## {s['url']}", f"- {'reached' if s['reached'] else 'NOT reached'}; verdict {s['verdict']}; README HTTP {s['readme_status']}; "
              f"release {s['release'] or 'none'}" + ("; already in catalog" if s["in_catalog"] else "")]
        pk = s["packages"]
        L += [f"- {len([p for p in pk if p['kind'] != 'zip-container'])} package(s) found, "
              f"{len([p for p in pk if p.get('judgement') == 'installable'])} installable (squashfs magic verified)"]
        for p in pk:
            if p["kind"] == "direct": L.append(f"  - OPK {p['name']}: {p['judgement']} ({p['reason']}) <{p['url']}>")
            elif p["kind"] == "zip-container":
                L.append(f"  - ZIP <{p['url']}>: {p.get('entries', 0)} entries, {p.get('opks', 0)} OPK(s) inside" + (f"; {p['note']}" if p.get("note") else ""))
                L += [f"    - {m['path']}: {m['judgement']} ({m['reason']})" for m in pk if m["kind"] == "zip" and m.get("container") == p["url"]]
        L.append("")
    L += ["## Rejected inputs", ""] + [f"- {r['url']}: {r['reason']}" for r in res["rejected"]] + ([] if res["rejected"] else ["None."])
    L += ["", "## Failed requests", ""] + [f"- {u}: {st}" for u, st in res["failures"]] + ([] if res["failures"] else ["None."])
    return "\n".join(L) + "\n"


def submitted_only(a):
    """Targeted run for --submitted: only the supplied repositories, their README, releases, repository files and the package links
    they contain. No seed searches, FreeSerp, owner or page crawling, no other repositories, no stored-URL rechecks, and no read or
    write of any persistent cache (package leads, tree scans, lead cache): history and provenance stay exactly as they were."""
    global MAX_REQ, DEADLINE_S
    MAX_REQ, DEADLINE_S = min(a.max_req or SUBMITTED_MAX_REQ, SUBMITTED_MAX_REQ), min(a.deadline or SUBMITTED_DEADLINE_S, SUBMITTED_DEADLINE_S)
    leads, rejected = submitted_leads(a.submitted)
    for u, why in rejected: print(f"rejected {u}: {why}", file=sys.stderr)
    if not leads: sys.exit("submitted-only: no valid GitHub, GitLab or Codeberg repository URL supplied")
    c, notes = Crawl(), []
    c.scope = {(kind, key.lower()) for kind, key, _ in leads}
    for kind, key, url in leads: c.push(kind, key, {"from": SUBMITTED, "anchor": url}, 0)
    try: c.run()
    except Exception as e:   # a crash must still leave a report that says INCOMPLETE
        notes.append(f"crawl error: {type(e).__name__}: {e}"[:200])
    sub = mark_submitted(c, leads)
    unique_apps(c)   # judges every package in place; its autonomous app list is deliberately unused
    fields = ("url", "name", "kind", "size", "judgement", "reason", "container", "path", "magic_squashfs", "status", "note", "entries", "opks")
    for s in sub:
        s["in_catalog"] = bool((c.repos.get(s["key"].lower()) or {}).get("in_catalog"))
        s["packages"] = [{k: p.get(k) for k in fields} for p in s["packages"]]
    res = {"as_of": date.today().isoformat(), "authenticated": bool(os.environ.get("GITHUB_TOKEN")), "requests": NREQ, "seconds": round(time.time() - T0),
           "limits": {"max_requests": MAX_REQ, "deadline_s": DEADLINE_S}, "out_of_scope": c.out_of_scope, "leads": sub,
           "rejected": [{"url": u, "reason": r} for u, r in rejected], "failures": FAILS[:60]}
    res["incomplete_reasons"] = assess(notes, len(c.q) + len(c.pq), STOP, FAILS, c.dropped)
    res["complete"] = not res["incomplete_reasons"]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "submitted-results.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    md = submitted_report(res)
    (out / "submitted-results.md").write_text(md, encoding="utf-8")
    print(md)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(D.ROOT / "build" / "discovery"))
    ap.add_argument("--no-github-seed", action="store_true", help="seed only from non-GitHub search APIs")
    ap.add_argument("--max-req", type=int); ap.add_argument("--deadline", type=int)
    ap.add_argument("--no-freeserp", action="store_true", help="skip the optional FreeSerp web-search seeds")
    ap.add_argument("--lead-cache", default=None, help="JSON file of FreeSerp leads kept between runs")
    ap.add_argument("--package-leads", default=None, help="JSON store of verified download URLs, revalidated and updated each run")
    ap.add_argument("--package-seed", default=None, help="read-only JSON store merged in first (e.g. a committed snapshot)")
    ap.add_argument("--submitted", default="", help=f"up to {SUBMIT_MAX} GitHub/GitLab/Codeberg repository URLs (unapproved leads, reported separately)")
    ap.add_argument("--submitted-only", action="store_true", help="inspect only the --submitted repositories (small budget, no general discovery, caches untouched)")
    a = ap.parse_args()
    if a.submitted_only: return submitted_only(a)
    global MAX_REQ, DEADLINE_S
    MAX_REQ, DEADLINE_S = a.max_req or MAX_REQ, a.deadline or DEADLINE_S
    c = Crawl()
    notes, optional = [], {}
    store, rechecked = {}, 0
    c.recheck = []
    for f in (a.package_seed, a.package_leads):
        if f: store.update({u: v for u, v in load_leads(f, "last_checked").items() if v.get("kind") in ("opk", "zip")})   # load_leads drops malformed entries
    scans_path = Path(a.package_leads).with_name("tree-scans.json") if a.package_leads else None
    c.tree_scans = load_scans(scans_path) if scans_path else {}
    leads, rejected = submitted_leads(a.submitted)
    for kind, key, url in leads: c.push(kind, key, {"from": SUBMITTED, "anchor": url}, 0)   # queued first; same handlers, checks and budget
    try:
        c.tree_known = tree_known(store)
        c.stored_repos = {v["repo"].lower() for v in store.values() if isinstance(v.get("repo"), str)}
        rechecked = seed_packages(c, store)
        notes = ([] if a.no_github_seed else seed(c)) + seed_multi(c)
        optional["freeserp"] = {"status": "disabled"} if a.no_freeserp else seed_freeserp(c, a.lead_cache)
        c.run()
    except Exception as e:   # a crash must still leave a report that says INCOMPLETE
        notes.append(f"crawl error: {type(e).__name__}: {e}"[:200])
    sub = mark_submitted(c, leads)
    uniq = unique_apps(c)
    for s in sub: s["packages"] = [{k: p.get(k) for k in ("url", "name", "kind", "size", "judgement", "reason")} for p in s["packages"]]
    why = assess(notes, len(c.q) + len(c.pq), STOP, FAILS, c.dropped)
    caps = [n for n, hit in (("repos", len(c.repos) - sum(k in c.repos for k in c.readme_seeds) >= MAX_REPOS), ("pages", len(c.pages) >= MAX_PAGES), ("owners", len(c.owners) >= MAX_OWNERS)) if hit]
    sites = {}
    for pg in c.pages.values():
        if pg["status"] == 200 and pg.get("relevant"): sites.setdefault(pg.get("host"), []).append(pg["url"])
    res = {"as_of": date.today().isoformat(), "authenticated": bool(os.environ.get("GITHUB_TOKEN")), "requests": NREQ, "seconds": round(time.time() - T0),
           "limits": {"max_requests": MAX_REQ, "max_pages": MAX_PAGES, "max_repos": MAX_REPOS, "max_depth": MAXD}, "seed_notes": notes,
           "unique_installable_apps": uniq,
           "packages": [p for p in c.pkgs.values()],
           "repos": list(c.repos.values()), "pages": list(c.pages.values()), "owners": list(c.owners.values()),
           "relevant_sites": sites, "inaccessible_sources": inaccessible(c.pages.values()), "skipped": c.dropped, "failures": FAILS[:60], "optional_channels": optional}
    res.update(complete=not why, incomplete_reasons=why, caps_hit=caps)
    res["submitted_leads"] = {"accepted": sub, "rejected": [{"url": u, "reason": r} for u, r in rejected]}
    res["package_leads"] = {"stored_before": len(store), "rechecked": rechecked, **update_packages(store, c.pkgs.values(), res["as_of"]), "stored_after": len(store)}
    res["package_leads"]["recheck"] = recheck_stats(store, c.recheck, int(T0))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.package_leads:
        Path(a.package_leads).parent.mkdir(parents=True, exist_ok=True)
        Path(a.package_leads).write_text(json.dumps(store, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "package-leads.json").write_text(json.dumps(store, indent=1, sort_keys=True) + "\n", encoding="utf-8")   # candidates only, never catalog/
    scans = dict(sorted(c.tree_scans.items(), key=lambda kv: kv[1]["scanned"], reverse=True)[:SCAN_MAX])
    for f in [scans_path, out / "tree-scans.json"] if scans_path else [out / "tree-scans.json"]:
        f.write_text(json.dumps(scans, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "discovery-results.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if a.lead_cache and Path(a.lead_cache).is_file(): (out / "freeserp-leads.json").write_bytes(Path(a.lead_cache).read_bytes())   # artifact carries the cache the next run will restore
    md = report(res, c)
    (out / "discovery-results.md").write_text(md, encoding="utf-8")
    digest = hashlib.sha256("\n".join(sorted(f"{x['name'].lower()}:{x['size']}" for x in uniq)).encode()).hexdigest()[:12]
    (out / "summary.json").write_text(json.dumps({"complete": not why, "reasons": why, "caps_hit": caps, "skipped": c.dropped, "apps": len(uniq), "digest": digest, "authenticated": res["authenticated"],
                                                  "requests": NREQ, "seconds": res["seconds"]}) + "\n")
    print(md.split("## Unique")[0])   # the status header goes to the step summary
    print(stats_md(res, store))


if __name__ == "__main__":
    main()
