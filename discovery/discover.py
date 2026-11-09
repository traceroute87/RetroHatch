#!/usr/bin/env python3
"""Shared helpers for discovery/crawl.py, the one discovery pipeline: catalog lookup, URL and text normalisation, and the sentence-level
device-evidence analysis. Metadata only: no network, no package handling, never writes catalog/."""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
API = "https://api.github.com"


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


# ---- questionable releases ------------------------------------------------------------------------------------------------

LISTY = re.compile(r"^(awesome|best|top)[-_ ]|(^|[-_ ])(awesome list|curated list|list of|alternatives?)([-_ ]|$)", re.I)


def suspicious_flags(c):
    """Flags for a candidate record (search.py output) that look at the release itself: a download whose file name has nothing to do with the project (a re-badged or unrelated
    upload), and projects that are lists rather than apps. Pure function of the record, so review.py can re-apply it to older search results. Never a verdict: a human decides."""
    f = []
    art = c.get("artifact") or {}
    words = lambda t: {w for w in re.split(r"[^a-z0-9]+", (t or "").lower()) if len(w) >= 4}
    if art.get("name") and words(c.get("name")) and not (words(c.get("name")) & words(art["name"])) and not (words(c.get("owner")) & words(art["name"])):
        f.append("release-name-mismatch")
    if LISTY.search((c.get("name") or "")) or LISTY.search(c.get("description") or ""):
        f.append("list-not-an-app")
    return f


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
