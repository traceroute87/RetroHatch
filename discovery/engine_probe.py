#!/usr/bin/env python3
"""TEMPORARY compatibility probe for four free web-search APIs, using only their documented endpoints:
  mwmbl      GET  https://api.mwmbl.org/api/v2/search/?q=...                 (anonymous tier: 1 req/s, 1000/month per IP)
  marginalia GET  https://api2.marginalia-search.com/search?query=...        (header API-Key: public)
  freeserp   GET  https://freeserp.ai/api.php?index=web&q=...&size=10        (keyless)
  truegle    POST https://api.truegle.info/api/search  {"query": ...}        (header X-Truegle-Client; 30/min per IP)
The same 10 queries go to each provider (one thread per provider, each paced to its own documented limit). No retries, no
proxies. Whole test capped at 90 s. Metadata only: nothing is downloaded or installed.

  python discovery/engine_probe.py --out out
"""
import argparse, json, re, sys, threading, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover as D

UA = "retrohatch-discovery/1 (+https://github.com/traceroute87/RetroHatch)"
CAP_S = 90
PROF = json.loads((D.HERE / "profiles.json").read_text(encoding="utf-8"))["rg-nano"]
RELEVANT = D.term_re(PROF["direct"] + PROF["family"] + ["opk"])
QUERIES = ["rg nano opk", "funkey s opk", "rg nano homebrew games download", "funkey os third party applications", "anbernic rg nano apps",
           "rg nano emulators opk", "funkey s games", "rg nano custom firmware", "rockbox rg nano", "funkey opk download"]
T0 = time.time()
Q = urllib.parse.quote_plus


def req(provider, q):
    if provider == "mwmbl":
        return urllib.request.Request(f"https://api.mwmbl.org/api/v2/search/?q={Q(q)}", headers={"User-Agent": UA}), 1.2
    if provider == "marginalia":
        return urllib.request.Request(f"https://api2.marginalia-search.com/search?query={Q(q)}&count=20", headers={"User-Agent": UA, "API-Key": "public"}), 1.5
    if provider == "freeserp":
        return urllib.request.Request(f"https://freeserp.ai/api.php?index=web&q={Q(q)}&size=10", headers={"User-Agent": UA}), 0.5
    return urllib.request.Request("https://api.truegle.info/api/search", data=json.dumps({"query": q, "mode": "blue-pill"}).encode(),
                                  headers={"User-Agent": UA, "Content-Type": "application/json", "X-Truegle-Client": "retrohatch-discovery"}), 2.2


def walk(x, out):
    """Collect every dict that carries an http(s) url, whatever the provider's envelope looks like."""
    if isinstance(x, dict):
        if isinstance(x.get("url"), str) and x["url"].startswith("http"): out.append(x)
        for v in x.values(): walk(v, out)
    elif isinstance(x, list):
        for v in x: walk(v, out)
    return out


def run(provider, log, results):
    for q in QUERIES:
        if time.time() - T0 > CAP_S - 8:
            log.append({"provider": provider, "query": q, "status": "skipped", "error": "90 s cap"}); continue
        rq, pause = req(provider, q)
        t = time.time(); st, body, hd, err = 0, b"", {}, None
        try:
            with urllib.request.urlopen(rq, timeout=12) as r: st, body, hd = r.status, r.read(2_000_000), dict(r.headers)
        except urllib.error.HTTPError as e: st, hd, body, err = e.code, dict(e.headers), e.read(400), f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, ValueError) as e: err = f"{type(e).__name__}: {e}"[:140]
        js = None
        try: js = json.loads(body) if body else None
        except ValueError: pass
        hits = walk(js, []) if js is not None else []
        rec = {"provider": provider, "query": q, "status": st, "seconds": round(time.time() - t, 2), "bytes": len(body), "valid_json": js is not None, "n_results": len(hits),
               "rate_limit": {k: v for k, v in hd.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}}
        if err or st != 200: rec["error"] = err or f"HTTP {st}"; rec["body_start"] = body[:160].decode("utf-8", "replace")
        log.append(rec)
        for h in hits:
            results.append({"provider": provider, "query": q, "url": h["url"], "title": str(h.get("title") or "")[:100],
                            "snippet": str(h.get("snippet") or h.get("description") or h.get("extract") or "")[:160]})
        time.sleep(pause)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="out"); a = ap.parse_args()
    log, res, th = [], [], []
    for p in ("mwmbl", "marginalia", "freeserp", "truegle"):
        t = threading.Thread(target=run, args=(p, log, res)); t.start(); th.append(t)
    for t in th: t.join(timeout=max(1, CAP_S + 5 - (time.time() - T0)))
    host = lambda u: urllib.parse.urlsplit(u).netloc.lower().removeprefix("www.")
    summ = {}
    for p in ("mwmbl", "marginalia", "freeserp", "truegle"):
        L, R = [l for l in log if l["provider"] == p], [r for r in res if r["provider"] == p]
        rel = [r for r in R if RELEVANT.search(D.norm(" ".join([r["url"], r["title"], r["snippet"]])))]
        lead = [r for r in rel if re.search(r"\.(opk|zip)(\?|$)", r["url"], re.I) or re.search(r"\.opk\b", r["snippet"] + r["title"], re.I)
                or re.search(r"/(releases?|downloads?)\b", r["url"], re.I)]
        summ[p] = {"requests": len([l for l in L if l["status"] != "skipped"]), "http_200": sum(l["status"] == 200 for l in L), "valid_json": sum(l["valid_json"] for l in L if "valid_json" in l),
                   "statuses": sorted({str(l.get("error") or l["status"]) for l in L}), "avg_seconds": round(sum(l.get("seconds", 0) for l in L) / max(1, len(L)), 2),
                   "results": len(R), "unique_domains": len({host(r["url"]) for r in R}), "relevant_domains": sorted({host(r["url"]) for r in rel}),
                   "download_leads": sorted({r["url"] for r in lead})[:40], "rgnano_com": any(host(r["url"]).endswith("rgnano.com") for r in R),
                   "funkey_wiki": any("funkey-project.com" in host(r["url"]) or "funkey" in host(r["url"]) and "wiki" in r["url"] for r in R),
                   "rate_limit_headers": sorted({json.dumps(l["rate_limit"], sort_keys=True) for l in L if l.get("rate_limit")})}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "engine-probe.json").write_text(json.dumps({"purpose": "documented-API compatibility probe", "seconds": round(time.time() - T0, 1), "cap_s": CAP_S,
                                                       "queries": QUERIES, "summary": summ, "requests": log, "results": res}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"## engine probe ({round(time.time() - T0)} s of {CAP_S} s cap); optional channels, not production")
    for p, s in summ.items():
        print(f"- {p}: {s['http_200']}/{s['requests']} HTTP 200, json {s['valid_json']}, {s['results']} results, {s['unique_domains']} domains, {len(s['relevant_domains'])} relevant, "
              f"{len(s['download_leads'])} download leads, rgnano.com={s['rgnano_com']}, funkey wiki={s['funkey_wiki']}, avg {s['avg_seconds']} s, statuses {s['statuses']}")


if __name__ == "__main__":
    main()
