#!/usr/bin/env python3
"""Multi-device candidate search: RG Nano / FunKeyOS (OPK) and RG Rotate / Android (APK), from the SAME profiles (discovery/profiles.json) and the SAME evidence
analysis (discovery/discover.py) as discovery/crawl.py. It reuses crawl.py's guarded fetch, request budget and User-Agent; it is not a second crawler.

  GitHub repository search (profile queries + the device's repos in sources.txt)  ->  latest release  ->  real downloadable file (a 4-byte range read, never a
  full download)  ->  README evidence  ->  category + tags (categories.py)  ->  one candidate record with flags  ->  build/discovery/candidates-<device>.json

Metadata only. Nothing is downloaded whole, installed, approved, signed or written to catalog/. A filename that mentions a device proves nothing: compatibility
is `claimed` only when a sentence in the description / topics / release notes / README says the device is supported, and is never `tested` here. APK identity
(package, minSdk, ABIs, signer) is read later, from the file, by tools/apk_inspect.py for the candidates a human picks.

  python discovery/search.py --device all [--max-req 120] [--out build/discovery]
  python discovery/review.py                      -> the human-readable report from these files (offline)
"""
import argparse, json, math, re, sys, time, urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "tools"))
import discover as D, categories as CAT, crawl as C
from apk_inspect import pick_asset

PROFILES = json.loads((HERE / "profiles.json").read_text(encoding="utf-8"))
EXT = {"rg-nano": ".opk", "rg-rotate": ".apk"}
ABANDONED_DAYS = 548          # no push for ~18 months
ERRORS = []


def today():
    return date.today().isoformat()


def age_days(iso):
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - (t if t.tzinfo else t.replace(tzinfo=timezone.utc))).days
    except (ValueError, AttributeError):
        return 10 ** 6


# ---- GitHub ---------------------------------------------------------------------------------------------------------------

def search(query, per_page=30, wait=6.5):
    """One repository search. Unauthenticated search is limited to 10 requests a minute, so this waits; a rate-limit answer ends the search phase (reported)."""
    time.sleep(wait)
    st, js = C.api("/search/repositories?q=" + urllib.parse.quote(query) + f"&sort=updated&order=desc&per_page={per_page}")
    if st in (403, 429):
        ERRORS.append(f"search rate limit hit at {query!r}"); return None
    if st != 200 or not js:
        ERRORS.append(f"search failed ({st}) for {query!r}"); return []
    return js.get("items", [])


def latest_release(full):
    """Newest non-draft release (a stable one when there is one) -> (release dict | None, stable bool)."""
    st, js = C.api(f"/repos/{full}/releases?per_page=6")
    if st != 200 or not isinstance(js, list):
        if st not in (404,):
            ERRORS.append(f"releases {full}: {st}")
        return None, True
    rels = [r for r in js if not r.get("draft")]
    stable = [r for r in rels if not r.get("prerelease")]
    return (stable[0], True) if stable else ((rels[0], False) if rels else (None, True))


def readme_of(full, branch):
    for name in ("README.md", "readme.md", "README.rst", "README"):
        st, _, b, _ = C.fetch(f"https://raw.githubusercontent.com/{full}/{branch or 'HEAD'}/{name}", limit=300_000)
        if st == 200 and b:
            return b.decode("utf-8", "replace"), f"https://github.com/{full}#readme"
    return None


def real_file(device, url):
    """The first bytes say what the file is: an OPK is a squashfs image ('hsqs'), an APK is a ZIP ('PK\\x03\\x04'). None = could not tell (unreachable)."""
    if device == "rg-nano":
        ok, size, st = C.probe_opk(url)
        return ok, size
    st, h, b, _ = C.fetch(url, "bytes=0-3", 4)
    return ((b == b"PK\x03\x04") if st in (200, 206) else None), C.total_size(h, st, 4)


def choose_artifact(device, rel):
    """-> {asset, member, real} for the release's best downloadable file, or None. RG Nano: an .opk asset, else a .zip whose central directory lists an .opk (read with Range
    requests, as crawl.py does). RG Rotate: the APK pick_asset() prefers (arm64 first). `real` is a 4-byte magic check, never a download."""
    if not rel:
        return None
    assets = rel.get("assets", [])
    direct = [x for x in assets if x["name"].lower().endswith(EXT[device])]
    if direct:
        a = pick_asset(direct) if device == "rg-rotate" else direct[0]
        return {"asset": a, "member": None, "real": real_file(device, a["browser_download_url"])[0], "others": len(direct) - 1}
    if device == "rg-nano":
        zips = sorted([x for x in assets if x["name"].lower().endswith(".zip")], key=lambda x: (not re.search(r"funkey|opk|nano", x["name"].lower()), x["name"]))
        for z in zips[:1]:
            _, members, _ = C.list_zip(z["browser_download_url"])
            opk = next((m for m in members if m["name"].lower().endswith(".opk")), None)
            if opk:
                return {"asset": z, "member": opk["name"], "real": C.zip_member_is_opk(z["browser_download_url"], opk), "others": 0}
    return None


def abi_hint(names):
    n = " ".join(names).lower()
    if re.search(r"arm64|aarch64|android64|v8a", n): return "arm64"
    if re.search(r"universal", n): return "universal"
    if re.search(r"x86|i386|armeabi|arm32|v7a", n): return "other-abi"
    return "unmarked"


# ---- candidate record ----------------------------------------------------------------------------------------------------

def flags_for(device, repo, rel, stable, asset, real, hint, verdict):
    f = []
    if repo.get("archived"): f.append("archived")
    if age_days(repo.get("pushed_at")) > ABANDONED_DAYS: f.append("abandoned")
    if not (repo.get("license") or {}).get("spdx_id") or repo["license"]["spdx_id"] == "NOASSERTION": f.append("missing-license")
    if not (repo.get("description") or "").strip(): f.append("missing-description")
    if repo.get("fork"): f.append("fork")
    if rel is None: f.append("no-release")
    elif not asset: f.append("no-" + EXT[device][1:] + "-in-release")
    elif real is False: f.append("not-a-real-" + EXT[device][1:])
    elif real is None: f.append("file-unreachable")
    if rel is not None and not stable: f.append("pre-release-only")
    if asset and re.search(r"debug|nightly|snapshot", asset["name"].lower()): f.append("debug-or-nightly-build")
    if device == "rg-rotate" and asset and hint == "other-abi": f.append("not-arm64")
    # Android is one platform: an APK that names another handheld is not incompatible with RG Rotate. An OPK built for another handheld may well be.
    if verdict in ("incompatible", "conflicting") or (verdict == "other_device" and device == "rg-nano"): f.append("compat-" + verdict)
    return f


def build(device, repo, rel, stable, readme, hits=1, art=None):
    full = repo["full_name"]
    prof = PROFILES[device]
    asset, member, real = (art["asset"], art["member"], art["real"]) if art else (None, None, None)
    verdict, ex = D.analyze(repo, rel, readme, prof)
    hint = abi_hint([a["name"] for a in (rel or {}).get("assets", [])]) if device == "rg-rotate" else ""
    flags = flags_for(device, repo, rel, stable, asset, real, hint, verdict)
    if member: flags.append("opk-inside-zip")
    text = (readme[0][:1500] if readme else "")
    group, conf = CAT.classify(repo.get("name"), repo.get("description"), repo.get("topics"), text=text)
    c = {"device": device, "repo": full, "url": repo.get("html_url") or f"https://github.com/{full}", "name": repo.get("name"), "owner": repo["owner"]["login"] if repo.get("owner") else full.split("/")[0],
         "description": (repo.get("description") or "").strip(), "topics": repo.get("topics") or [], "stars": repo.get("stargazers_count", 0),
         "license": (repo.get("license") or {}).get("spdx_id") or "unknown", "pushed": (repo.get("pushed_at") or "")[:10], "created": (repo.get("created_at") or "")[:10],
         "group": group, "group_confidence": conf, "tags": CAT.make_tags(repo.get("topics")), "hits": hits, "flags": flags,
         "compat": {"verdict": verdict, "level": "claimed" if verdict == "supports" else "none", "evidence": ex[:3]},   # never "tested": only a human with the device sets that
         "release": None, "artifact": None}
    if repo.get("fork"): c["fork"] = {"parent": (repo.get("parent") or {}).get("full_name")}
    if rel:
        c["release"] = {"tag": rel.get("tag_name"), "published": (rel.get("published_at") or "")[:10], "url": rel.get("html_url"), "stable": stable}
    if asset:
        c["artifact"] = {"name": asset["name"], "url": asset["browser_download_url"], "size": asset.get("size"), "format": "zip" if member else EXT[device][1:], "member": member,
                         "real_file": real, "abi_hint": hint, "other_assets": art["others"]}
    c["flags"] += [x for x in D.suspicious_flags(c) if x not in c["flags"]]
    c["score"] = score(c)
    return c


def score(c):
    """A ranking for the reader, not a verdict. Explicit support and a real, licensed, maintained download lead; every flag costs points."""
    s = math.log10(1 + c["stars"]) * 2 + min(c["hits"], 4) * 0.5
    s += {"supports": 4, "family": 1, "ambiguous": 0.5, "none": 0, "other_device": 0 if c["device"] == "rg-rotate" else -6}.get(c["compat"]["verdict"], -6)
    if c["artifact"] and c["artifact"]["real_file"]: s += 3
    if c["license"] != "unknown": s += 1
    if age_days(c["pushed"]) < 365: s += 1
    s -= 1.5 * sum(f in ("abandoned", "archived", "fork", "pre-release-only", "debug-or-nightly-build", "missing-license", "no-release", "not-arm64", "list-not-an-app", "release-name-mismatch") for f in c["flags"])
    return round(s, 2)


# ---- run -------------------------------------------------------------------------------------------------------------------

def source_repos(device):
    """Repositories the maintainers listed for this device in discovery/sources.txt (community / upstream sources)."""
    out = []
    ok, _ = C.read_sources((HERE / "sources.txt").read_text(encoding="utf-8-sig"))
    for kind, key, url, devs, _n in ok:
        if kind == "repo" and device in devs and "github.com" in url:
            out.append(key if "/" in key else urllib.parse.urlsplit(url).path.strip("/"))
    return out


def collect(device, max_queries, max_repos, wait, known=frozenset(), check_known=False):
    prof = PROFILES[device]
    seen, hits = {}, {}
    for q in prof["queries"][:max_queries]:
        items = search(q, wait=wait)
        if items is None: break
        for r in items:
            k = r["full_name"].lower()
            seen.setdefault(k, r); hits[k] = hits.get(k, 0) + 1
    for full in source_repos(device):            # the maintainers' own list: looked at when it is new, or when known entries are re-checked (needs API budget)
        k = full.lower()
        if k not in seen and (check_known or k not in known):
            st, js = C.api(f"/repos/{full}")
            if st == 200 and js: seen[k] = js; hits[k] = 1
    pool = [r for r in seen.values() if check_known or r["full_name"].lower() not in known]   # known entries cost API budget and only matter for update checks
    ranked = sorted(pool, key=lambda r: (-hits[r["full_name"].lower()], -(r.get("stargazers_count") or 0)))
    return ranked[:max_repos], hits


def run_device(device, a):
    known = known_repos(device)
    repos, hits = collect(device, a.max_queries, a.max_repos, a.wait, known, a.check_known)
    out, forks = [], []
    for r in repos:
        full = r["full_name"]
        if C.NREQ >= C.MAX_REQ or C.STOP: break
        rel, stable = latest_release(full)
        out.append(build(device, r, rel, stable, readme_of(full, r.get("default_branch")), hits[full.lower()], choose_artifact(device, rel)))
        if r.get("fork"): forks.append(out[-1])
    for c in forks[:a.max_forks]:                 # original vs fork: one request each for the parent
        st, js = C.api(f"/repos/{c['repo']}")
        if st == 200 and js and js.get("parent"): c["fork"] = {"parent": js["parent"]["full_name"]}
    out = dedupe(out)
    for c in out:
        c["known"] = c["repo"].lower() in known
    return out


def known_repos(device):
    """Lower-case owner/name of every repository already in this device's inventory or in the catalogs."""
    inv = HERE.parent / "candidates" / ("inventory.json" if device == "rg-nano" else "inventory-rg-rotate.json")
    k = set()
    if inv.is_file():
        for app in json.loads(inv.read_text(encoding="utf-8"))["applications"]:
            for s in app.get("sources", []):
                m = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)", s.get("url", ""))
                if m: k.add(m.group(1).lower())
    return k


def dedupe(cands):
    """One candidate per project. A fork whose parent is in the set folds into the parent (alias); a look-alike (same normalised name, same description, other owner) folds into the one with more stars."""
    by = {c["repo"].lower(): c for c in cands}
    keep = {}
    for c in sorted(cands, key=lambda c: -c["stars"]):
        parent = ((c.get("fork") or {}).get("parent") or "").lower()
        if parent in by and parent != c["repo"].lower():
            by[parent].setdefault("aliases", []).append(c["repo"]); continue
        key = re.sub(r"[^a-z0-9]", "", (c["name"] or "").lower())
        twin = next((k for k in keep.values() if re.sub(r"[^a-z0-9]", "", (k["name"] or "").lower()) == key and k["description"].lower() == c["description"].lower() and k["description"]), None)
        if twin:
            twin.setdefault("aliases", []).append(c["repo"]); continue
        keep[c["repo"].lower()] = c
    return sorted(keep.values(), key=lambda c: -c["score"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default="all", choices=["all", "rg-nano", "rg-rotate"])
    ap.add_argument("--out", default=str(HERE.parent / "build" / "discovery"))
    ap.add_argument("--max-req", type=int, default=120, help="request budget for the whole run (GitHub API + raw + range reads)")
    ap.add_argument("--max-queries", type=int, default=12, help="repository searches per device")
    ap.add_argument("--max-repos", type=int, default=30, help="repositories examined per device (best-ranked first)")
    ap.add_argument("--max-forks", type=int, default=6)
    ap.add_argument("--check-known", action="store_true", help="also re-check repositories already in the inventory for new releases (default with GITHUB_TOKEN)")
    ap.add_argument("--wait", type=float, default=None, help="seconds between searches (default 6.5 without GITHUB_TOKEN, 2.5 with)")
    a = ap.parse_args()
    import os
    a.wait = a.wait if a.wait is not None else (2.5 if os.environ.get("GITHUB_TOKEN") else 6.5)
    a.check_known = a.check_known or bool(os.environ.get("GITHUB_TOKEN"))
    C.MAX_REQ, C.DELAY = a.max_req, 0.2
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for device in (["rg-nano", "rg-rotate"] if a.device == "all" else [a.device]):
        cands = run_device(device, a)
        doc = {"schema": 1, "device": device, "generated": today(), "requests": C.NREQ, "stopped": C.STOP[:1], "errors": ERRORS[:], "candidates": cands,
               "note": "UNAPPROVED leads. compat.level 'claimed' = a sentence says so; nothing here is tested, approved or installable."}
        (out / f"candidates-{device}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{device}: {len(cands)} candidates ({sum(1 for c in cands if not c['known'])} not in the inventory), {C.NREQ} requests so far, errors: {len(ERRORS)}")
    print("next: python discovery/review.py --in", out)


if __name__ == "__main__":
    main()
