#!/usr/bin/env python3
"""Find CANDIDATE apps on GitHub. Metadata only: never downloads or runs a package, never writes catalog/.
Levels here: discovered | claimed. 'tested'/'verified' exist only in catalog/ and are never set by this tool."""
import argparse, base64, binascii, hashlib, json, os, re, sys, urllib.parse, urllib.request, urllib.error
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
API = "https://api.github.com"
INFO = "info: "  # notes with this prefix do not make a run incomplete


def http_get(url, token=None):
    """-> (status, headers, parsed json | None). Network errors become status 0."""
    h = {"Accept": "application/vnd.github+json", "User-Agent": "retrohatch-discovery"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
            return r.status, dict(r.headers), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), None
    except (urllib.error.URLError, OSError, ValueError):
        return 0, {}, None


def norm_url(u):
    u = (u or "").strip().lower().rstrip("/")
    return re.sub(r"\.git$", "", re.sub(r"^https?://(www\.)?", "", u))


def known_catalog():
    """Source URLs and ids already in catalog/ and dev/catalog/."""
    src, ids = set(), set()
    for d in (ROOT / "catalog" / "apps", ROOT / "dev" / "catalog" / "apps"):
        for p in sorted(d.glob("*.json")):
            doc = json.loads(p.read_text(encoding="utf-8"))
            ids.add(doc.get("id"))
            if doc.get("source"):
                src.add(norm_url(doc["source"]))
    return src, ids


# ---- evidence analysis -------------------------------------------------------------------------

def norm(s):
    return re.sub(r"[-_]+", " ", (s or "").lower())


def term_re(terms):
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(norm(t)) for t in sorted(terms, key=len, reverse=True)) + r")(?![a-z0-9])")


NEG = r"(?<![a-z0-9])(?:not|no|never|without|cannot|unsupported|incompatible|doesn't|does not|isn't|won't|can't)(?![a-z0-9])"
NEG_AFTER = r"\W+(?:\w+\W+){0,3}?(?:not supported|unsupported|incompatible|not compatible|not work|n't work)"
NOT_TESTED = re.compile(r"not (?:yet )?(?:been )?(?:tested|verified)|untested")
POS_CUE = re.compile(r"\b(?:support\w*|compatible|works? on|runs? on|running on|tested on|port(?:ed)?|for|builds? for|targets?|designed for|made for|installs? on)\b")


def lines_of(text):
    text = re.sub(r"```.*?```", "\n", text or "", flags=re.S)   # code blocks are commands, not claims
    return [l.strip() for l in re.split(r"(?<=[.!?])\s+|\n+", text) if l.strip()]


def excerpt(line):
    line = re.sub(r"\s+", " ", line)
    return line if len(line) <= 160 else line[:157] + "..."


def analyze(repo, rel, readme, prof):
    """Sentence-level evidence. readme = (text, url) or None. -> (verdict, excerpts[{kind,source,text,url}]).
    verdict: supports | incompatible | conflicting | other_device | ambiguous | family | none.
    Heuristic: a sentence naming the device is 'supports' only with a support cue (for/supports/runs on/...),
    'incompatible' on a nearby negation, else 'ambiguous'. Only 'supports' can become level 'claimed'."""
    dre, fre, ore = term_re(prof["direct"]), term_re(prof["family"]), term_re(prof.get("other") or ["zzznomatch"])
    base = repo.get("html_url") or f"https://github.com/{repo['full_name']}"
    rtext, rurl = readme if readme else ("", base)
    srcs = [("description", repo.get("description"), base),
            ("topics", " . ".join(repo.get("topics") or []), base),
            ("release", (rel or {}).get("body"), (rel or {}).get("html_url") or base + "/releases"),
            ("readme", rtext, rurl)]
    head = norm(" . ".join([repo.get("name") or "", repo.get("description") or "", " ".join(repo.get("topics") or [])]))
    ex = []
    for label, text, url in srcs:
        for ln in lines_of(text):
            n = norm(ln)
            m = dre.search(n)
            if not m:
                continue
            t = re.escape(m.group(0))
            if label == "topics":
                kind = "supports"
            elif NOT_TESTED.search(n):
                kind = "ambiguous"
            elif re.search(NEG + r"\W+(?:\w+\W+){0,4}?" + t, n) or re.search(t + NEG_AFTER, n):
                kind = "incompatible"
            elif POS_CUE.search(n):
                kind = "supports"
            else:
                kind = "ambiguous"
            ex.append({"kind": kind, "source": label, "text": excerpt(ln), "url": url})
    k = {x: [e for e in ex if e["kind"] == x] for x in ("incompatible", "supports", "ambiguous")}
    other_head = bool(ore.search(head)) and not dre.search(head)
    if k["supports"] and k["incompatible"]:
        v = "conflicting"
    elif k["incompatible"]:
        v = "incompatible"
    elif other_head and len(k["supports"]) < 2:
        v = "other_device"
    elif k["supports"]:
        v = "supports"
    elif k["ambiguous"]:
        v = "ambiguous"
    elif fre.search(norm(" ".join([head, (rel or {}).get("body") or "", rtext]))):
        v = "family"
    else:
        v = "none"
    return v, k["incompatible"][:3] + k["supports"][:3] + k["ambiguous"][:3]


# ---- candidates --------------------------------------------------------------------------------

def pick_release(rels):
    ok = [r for r in rels if isinstance(r, dict) and not r.get("draft")]
    ok.sort(key=lambda r: (not r.get("prerelease"), r.get("published_at") or ""), reverse=True)
    return ok[0] if ok else None


def assets_of(rel, prof):
    out = []
    for a in (rel or {}).get("assets") or []:
        if not isinstance(a, dict):
            continue
        name, url = a.get("name"), a.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str) or not url.startswith("https://"):
            out.append({"name": name if isinstance(name, str) else None, "problem": "malformed asset (missing name or https url)"})
        elif name.lower().endswith(tuple(prof["package_ext"])):
            out.append({"name": name, "url": url, "size": a.get("size") if isinstance(a.get("size"), int) else None,
                        "reported_digest": a.get("digest") or None})
    return sorted(out, key=lambda a: a["name"] or "")


def fingerprint(c):
    core = {"level": c["level"], "verdict": c["verdict"], "license": c["license"], "tag": (c["release"] or {}).get("tag"),
            "assets": [[a.get("name"), a.get("size"), a.get("reported_digest")] for a in c["assets"]],
            "ex": [[e["kind"], e["text"]] for e in c["evidence"]]}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:12]


def candidate(repo, rels, prof, as_of, readme=None):
    rel = pick_release(rels)
    lic = (repo.get("license") or {}).get("spdx_id") or "unknown"
    lic = "unknown" if lic == "NOASSERTION" else lic
    assets = assets_of(rel, prof)
    verdict, ev = analyze(repo, rel, readme, prof)
    fnames = [a["name"] for a in assets if a.get("name")]
    if verdict == "none" and any(norm(t) in norm(f) for f in fnames for t in prof["direct"] + prof["family"]):
        verdict = "filename"   # a package filename alone proves nothing
    flags = []
    if lic == "unknown": flags.append("license unknown")
    if repo.get("archived"): flags.append("archived")
    if repo.get("fork"): flags.append("fork")
    if not rel: flags.append("no release")
    elif not any("url" in a for a in assets): flags.append("no package asset")
    if rel and rel.get("prerelease"): flags.append("prerelease only")
    if any("problem" in a for a in assets): flags.append("malformed asset")
    if not readme: flags.append("no readme")
    if as_of and repo.get("pushed_at") and (as_of - date.fromisoformat(repo["pushed_at"][:10])).days > 730:
        flags.append("inactive >2y")
    c = {"repo": repo["full_name"], "url": repo.get("html_url") or f"https://github.com/{repo['full_name']}",
         "description": repo.get("description") or "", "license": lic, "last_activity": (repo.get("pushed_at") or "")[:10],
         "release": {"tag": rel.get("tag_name"), "date": (rel.get("published_at") or "")[:10]} if rel else None,
         "assets": assets, "level": "claimed" if verdict == "supports" else "discovered", "verdict": verdict,
         "evidence": ev, "flags": sorted(flags)}
    c["fp"] = fingerprint(c)
    return c


def fetch_readme(get, full):
    """-> (status, (text, url) | None, headers)."""
    st, hd, js = get(f"{API}/repos/{full}/readme")
    if st != 200 or not isinstance(js, dict) or not isinstance(js.get("content"), str):
        return st, None, hd
    try:
        text = base64.b64decode(js["content"]).decode("utf-8", "replace")[:30000]
    except (binascii.Error, ValueError):
        return 200, None, hd
    return 200, (text, js.get("html_url") or f"https://github.com/{full}#readme"), hd


# ---- triage ------------------------------------------------------------------------------------

def load_triage(path):
    """{"ignored": {repo: reason}, "rejected": {repo: reason}, "reviewed": {repo: {fp, release, verdict}}}; keys lowercased."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return {k: {r.lower(): v for r, v in (raw.get(k) or {}).items()} for k in ("ignored", "rejected", "reviewed")}


def triage_status(c, tri):
    """-> (status, detail). status: ignored | rejected | new | changed | unchanged."""
    key = c["repo"].lower()
    for s in ("ignored", "rejected"):
        if key in tri[s]:
            return s, str(tri[s][key])
    rv = tri["reviewed"].get(key)
    if not isinstance(rv, dict):
        return "new", ""
    if rv.get("fp") == c.get("fp"):
        return "unchanged", ""
    ch = []
    if rv.get("release") != (c["release"] or {}).get("tag"):
        ch.append(f"release {rv.get('release')} -> {(c['release'] or {}).get('tag')}")
    if rv.get("verdict") != c["verdict"]:
        ch.append(f"verdict {rv.get('verdict')} -> {c['verdict']}")
    return "changed", "; ".join(ch) or "evidence or assets changed"


# ---- discovery run -----------------------------------------------------------------------------

def discover(profile, get, max_repos=30, as_of=None, catalog=None, triage=None):
    """get(url) -> (status, headers, json). Returns (candidates, in_catalog, notes).
    Candidates carry status/detail. Ignored/rejected repos are stubs: no release/README requests are spent on them."""
    src, ids = catalog if catalog is not None else known_catalog()
    tri = triage or load_triage("/nonexistent")
    notes, repos = [], {}
    for q in profile["queries"]:
        st, hd, js = get(f"{API}/search/repositories?q={urllib.parse.quote(q)}&per_page=30&sort=updated")
        if st != 200 or not isinstance(js, dict):
            notes.append(f"query {q!r}: HTTP {st}" + (" (rate limited)" if st in (403, 429) else ""))
            if st in (403, 429): break
            continue
        for r in js.get("items") or []:
            if isinstance(r, dict) and r.get("full_name"):
                repos.setdefault(r["full_name"].lower(), r)
    names = sorted(repos)
    if len(names) > max_repos:
        notes.append(f"{INFO}{len(names)} repos found, only first {max_repos} (alphabetical) inspected")
        names = names[:max_repos]
    cands, known = [], []
    for n in names:
        r = repos[n]
        if norm_url(r.get("html_url") or "") in src or r["full_name"].split("/")[-1].lower() in ids:
            known.append(r["full_name"]); continue
        stub = {"repo": r["full_name"], "url": r.get("html_url") or f"https://github.com/{r['full_name']}"}
        for s in ("ignored", "rejected"):
            if n in tri[s]:
                cands.append({**stub, "status": s, "detail": str(tri[s][n])}); break
        else:
            st, hd, rels = get(f"{API}/repos/{r['full_name']}/releases?per_page=5")
            if st in (403, 429) or hd.get("X-RateLimit-Remaining") == "0":
                notes.append(f"rate limit hit at {r['full_name']}; this and remaining repos skipped"); break
            if st != 200 or not isinstance(rels, list):
                notes.append(f"{r['full_name']}: releases HTTP {st}"); rels = []
            st, readme, hd = fetch_readme(get, r["full_name"])
            if st in (403, 429) or hd.get("X-RateLimit-Remaining") == "0":
                notes.append(f"rate limit hit at {r['full_name']}; this and remaining repos skipped"); break
            if st not in (200, 404):
                notes.append(f"{r['full_name']}: readme HTTP {st}")
            c = candidate(r, rels, profile, as_of, readme)
            c["status"], c["detail"] = triage_status(c, tri)
            cands.append(c)
    cands.sort(key=lambda c: (c.get("level") != "claimed", c["repo"].lower()))
    return cands, sorted(known), sorted(set(notes))


def split(cands):
    full = [c for c in cands if "verdict" in c]
    act = [c for c in full if c["status"] in ("new", "changed") and c["level"] == "claimed"]
    low = [c for c in full if c["status"] in ("new", "changed") and c["level"] != "claimed"]
    return act, low, [c for c in full if c["status"] == "unchanged"], [c for c in cands if c["status"] in ("ignored", "rejected")]


def digest(act):
    return hashlib.sha256("\n".join(sorted(f"{c['repo'].lower()}:{c['fp']}" for c in act)).encode()).hexdigest()[:12]


# ---- output ------------------------------------------------------------------------------------

def block(c):
    rel = c["release"]
    tag = f"{c['status']}" + (f": {c['detail']}" if c["detail"] else "")
    L = [f"### {c['repo']}  [{c['level']}; {tag}]", c["description"] or "(no description)", "",
         f"- source: {c['url']}", f"- license: {c['license']}", f"- last activity: {c['last_activity'] or 'unknown'}",
         f"- latest release: {rel['tag']} ({rel['date']})" if rel else "- latest release: none",
         f"- evidence verdict: {c['verdict']} (author's text only; not tested)"]
    L += [f"  - {e['kind']} ({e['source']}): \"{e['text']}\" <{e['url']}>" for e in c["evidence"]]
    L += [f"- asset: {a['name']} {a.get('size') or '?'} B {a.get('url', '')}" + (f" [{a['problem']}]" if "problem" in a else "") for a in c["assets"]]
    if c["flags"]: L.append("- flags: " + ", ".join(c["flags"]))
    L += [f"- fingerprint: {c['fp']}", ""]
    return L


def report(cands, known, notes, device, as_of, issue=False):
    act, low, unch, triaged = split(cands)
    L = [f"# Discovery: {device}", "",
         f"As of {as_of}. **{len(act)} actionable** ({sum(c['status'] == 'new' for c in act)} new, {sum(c['status'] == 'changed' for c in act)} changed); "
         f"{len(low)} low-signal; {len(unch)} unchanged (suppressed); {len(triaged)} ignored/rejected; {len(known)} already in catalog.", "",
         "**Nothing here is installable, tested or verified.** `claimed` = the repo's own text says it supports the device. `discovered` = found, no usable claim. "
         "Filenames prove nothing. Promotion needs a hand-written catalog entry + hardware test. After review run `python discovery/discover.py --mark-reviewed`.", ""]
    L += ["## Actionable", ""] + ([x for c in act for x in block(c)] or ["None.", ""])
    if not issue:
        if low: L += ["## Low-signal (new or changed)", *[f"- {c['repo']}: {c['verdict']}, {c['status']} <{c['url']}>" for c in low], ""]
        if triaged: L += ["## Ignored / rejected", *[f"- {c['repo']}: {c['status']}: {c['detail']}" for c in triaged], ""]
        if known: L += ["## Already in catalog", *[f"- {k}" for k in known], ""]
    if notes: L += ["## Limitations this run", *[f"- {n.removeprefix(INFO)}" for n in notes], ""]
    return "\n".join(L)


def mark_reviewed(path, cands, only=()):
    tri = load_triage(path)
    only = {o.lower() for o in only}
    for c in split(cands)[0]:
        if not only or c["repo"].lower() in only:
            tri["reviewed"][c["repo"].lower()] = {"fp": c["fp"], "release": (c["release"] or {}).get("tag"), "verdict": c["verdict"]}
    Path(path).write_text(json.dumps({k: dict(sorted(v.items())) for k, v in tri.items()}, indent=1) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--device", default="rg-nano")
    ap.add_argument("--max-repos", type=int, default=30)
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--out", default=str(ROOT / "build" / "discovery"))
    ap.add_argument("--triage", default=str(HERE / "triage.json"))
    ap.add_argument("--mark-reviewed", nargs="*", metavar="REPO", help="record current actionable candidates (or named ones) as reviewed")
    a = ap.parse_args()
    prof = json.loads((HERE / "profiles.json").read_text(encoding="utf-8"))[a.device]
    tok = os.environ.get("GITHUB_TOKEN")
    cands, known, notes = discover(prof, lambda u: http_get(u, tok), a.max_repos, date.fromisoformat(a.as_of), triage=load_triage(a.triage))
    if not tok: notes.append(f"{INFO}no GITHUB_TOKEN: unauthenticated limits (10 search/min, 60 core/h)")
    complete = not [n for n in notes if not n.startswith(INFO)]
    s = split(cands)
    d = digest(s[0])
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / f"candidates-{a.device}.json").write_text(json.dumps({"device": a.device, "as_of": a.as_of, "candidates": cands, "in_catalog": known, "notes": notes}, indent=1, sort_keys=True) + "\n")
    (out / f"candidates-{a.device}.md").write_text(report(cands, known, notes, a.device, a.as_of) + "\n", encoding="utf-8")
    (out / f"issue-{a.device}.md").write_text(report(cands, known, notes, a.device, a.as_of, issue=True) + f"\n<!-- rh-discovery:{a.device}:{d} -->\n", encoding="utf-8")
    (out / f"summary-{a.device}.json").write_text(json.dumps({"complete": complete, "actionable": len(s[0]), "digest": d, "marker": f"rh-discovery:{a.device}:{d}"}) + "\n")
    print(f"{len(s[0])} actionable, {len(s[1])} low-signal, {len(s[2])} unchanged, {len(s[3])} ignored/rejected, {len(known)} in catalog; complete={complete} -> {out}")
    for n in notes: print("note:", n.removeprefix(INFO), file=sys.stderr)
    if a.mark_reviewed is not None:
        if not complete:
            sys.exit("incomplete run: not marking anything reviewed")
        mark_reviewed(a.triage, cands, a.mark_reviewed)
        print(f"triage updated: {a.triage}")


if __name__ == "__main__":
    main()
