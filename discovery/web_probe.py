#!/usr/bin/env python3
"""TEMPORARY probe: do PullPush (Reddit archive search) and Wayback CDX work from a GitHub runner, and do they find
relevant domains/pages/OPK URLs without any hardcoded source? Capped at 30 requests / 60 s. Metadata only: never
downloads anything (one 4-byte Range read of one archived OPK). Archived URLs are historical leads, never approved.

  python discovery/web_probe.py --out out
"""
import argparse, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path

MAX_REQ, MAX_S = 30, 60
UA = "retrohatch-discovery/1 (+https://github.com/traceroute87/RetroHatch)"
PROFILE = json.loads((Path(__file__).resolve().parent / "profiles.json").read_text(encoding="utf-8"))["rg-nano"]
DIRECT = {re.sub(r"\s+", "", t) for t in PROFILE["direct"]}
TERMS = sorted({re.sub(r"\s+", "", t) for t in PROFILE["direct"] + PROFILE["family"]})  # device terms only
SKIP = ("reddit.com", "redd.it", "imgur.com", "youtu", "github.com", "gitlab.com", "google.com", "dropbox.com", "we.tl", "mega.nz")
T0, LOG = time.time(), []


def get(url, rng=None, limit=3_000_000):
    """-> (status, headers, body). Records every request (status, seconds, rate-limit headers)."""
    if len(LOG) >= MAX_REQ or time.time() - T0 > MAX_S:
        return -1, {}, b""
    t = time.time()
    st, hd, body = 0, {}, b""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": rng} if rng else {})}), timeout=15) as r:
            st, hd, body = r.status, dict(r.headers), r.read(limit)
    except urllib.error.HTTPError as e:
        st, hd = e.code, dict(e.headers)
    except (urllib.error.URLError, OSError, ValueError) as e:
        hd = {"error": str(e)[:100]}
    LOG.append({"url": url, "status": st, "seconds": round(time.time() - t, 2), "bytes": len(body),
                "rate_limit": {k: v for k, v in hd.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}, **({"error": hd["error"]} if "error" in hd else {})})
    time.sleep(0.5)
    return st, hd, body


def jget(url):
    st, hd, b = get(url)
    try:
        return st, json.loads(b)
    except ValueError:
        return st, None


def host(u):
    return urllib.parse.urlsplit(u if "//" in u else "//" + u).netloc.lower().removeprefix("www.").split(":")[0]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="out"); a = ap.parse_args()
    q = urllib.parse.quote
    seen = {}      # domain -> {"urls": set, "from": [queries]}
    for kind, qq in (("submission", "rgnano"), ("submission", "rg nano"), ("comment", "funkey opk"), ("submission", "funkey s")):
        st, js = jget(f"https://api.pullpush.io/reddit/search/{kind}/?size=100&q={q(qq)}")
        for p in (js or {}).get("data", []) if isinstance(js, dict) else []:
            for u in re.findall(r"https?://[^\s)\]>\"]+", " ".join([p.get("url") or "", p.get("selftext") or "", p.get("body") or ""])):
                h = host(u.rstrip(".,;"))
                if h and "." in h and not any(h.endswith(s) for s in SKIP):
                    d = seen.setdefault(h, {"urls": set(), "from": set()}); d["urls"].add(u.rstrip(".,;")[:200]); d["from"].add(f"pullpush:{kind}:{qq}")
    # domains whose own name carries a device term -> enumerate their archived pages (lookup, not discovery)
    named = [h for h in seen if any(t in h.replace("-", "") for t in TERMS)]
    cands = sorted(named, key=lambda h: (not any(t in h.replace("-", "") for t in DIRECT), -len(seen[h]["urls"]), h))[:3]   # direct device terms first
    way = {}
    for h in cands:
        st, hd, b = get(f"https://web.archive.org/cdx/search/cdx?url={q(h)}&matchType=domain&collapse=urlkey&fl=timestamp,original,statuscode&filter=statuscode:200&limit=500")
        rows = [l.split(" ", 2) for l in b.decode("utf-8", "replace").splitlines() if l.count(" ") >= 2]
        pk = [r for r in rows if re.search(r"\.(opk|zip)(\?|$)", r[1], re.I)]
        way[h] = {"http": st, "pages": len(rows), "package_leads": [{"original": r[1], "archived_replay": f"https://web.archive.org/web/{r[0]}id_/{r[1]}", "approved": False, "source": "wayback-cdx"} for r in pk[:60]],
                  "sample_pages": [r[1] for r in rows[:25]]}
    # one archived OPK: does the replay serve real bytes? (4-byte Range read only)
    magic = None
    for w in way.values():
        for lead in w["package_leads"][:1]:
            st, hd, b = get(lead["archived_replay"], "bytes=0-3", 4); magic = {"url": lead["archived_replay"], "http": st, "squashfs_magic": b[:4] == b"hsqs"}
            break
        if magic: break
    ok = lambda s: 200 <= s < 300
    checks = {"pullpush_http_ok": any(l["status"] == 200 and "pullpush" in l["url"] for l in LOG),
              "pullpush_valid_json_with_data": len(seen) > 0,
              "domains_found": len(seen), "device_named_domains": cands,
              "wayback_http_ok": any(ok(w["http"]) for w in way.values()),
              "wayback_enumerated_pages": sum(w["pages"] for w in way.values()),
              "wayback_package_leads": sum(len(w["package_leads"]) for w in way.values()),
              "recall_rgnano_domain_found": any(h.endswith("rgnano.com") for h in seen),
              "recall_rockbox_page_enumerated": any("rockbox" in p.lower() for w in way.values() for p in w["sample_pages"] + [x["original"] for x in w["package_leads"]]),
              "requests": len(LOG), "seconds": round(time.time() - T0, 1), "within_caps": len(LOG) <= MAX_REQ and time.time() - T0 <= MAX_S + 5}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    doc = {"purpose": "temporary PullPush + Wayback reachability probe", "checks": checks, "requests": LOG, "magic_probe": magic,
           "domains": {h: {"urls": sorted(d["urls"])[:5], "from": sorted(d["from"])} for h, d in sorted(seen.items(), key=lambda kv: -len(kv[1]["urls"]))[:60]}, "wayback": way,
           "notice": "Archived downloads are historical leads only: approved=false, never installed."}
    (out / "web-discovery-evidence.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(checks, indent=1))
    sys.exit(0)


if __name__ == "__main__":
    main()
