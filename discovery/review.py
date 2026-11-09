#!/usr/bin/env python3
"""The maintainer's candidate report. Offline: reads what discovery/search.py wrote (candidates-<device>.json), the two candidate inventories and the review state
(candidates/review-state.json), and writes build/discovery/review.md (+ review.json, review.digest). Nothing here approves, signs, publishes or installs anything.

Every candidate lands in ONE group, strongest first, each line with a direct source link and the short reason it is there:
  Updated candidates                 a release newer than the one on record (a rejected project only comes back for a real change)
  New candidates                     first time seen, a real downloadable file, nothing missing
  Needs compatibility testing        known, has a real file, no test on the device yet
  Missing information                no real file in the latest release, no licence, or no description
  Previously reviewed or rejected    one line each, with the recorded reason; plus what the filters set aside (named for another device, incompatible)

State: `status` in review-state.json is set by a person (reviewed | rejected | testing | approved) with a `reason`. --update-state only records first_seen / last_seen /
release_tag and marks reported leads as `seen`, so the next report does not show them as new again.

  python discovery/review.py [--in build/discovery] [--out build/discovery] [--update-state]
"""
import argparse, hashlib, json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import categories as CAT, discover as D

STATE = ROOT / "candidates" / "review-state.json"
INV = {"rg-nano": ROOT / "candidates" / "inventory.json", "rg-rotate": ROOT / "candidates" / "inventory-rg-rotate.json"}
NAME = {"rg-nano": "RG Nano (FunKeyOS, OPK)", "rg-rotate": "RG Rotate (Android, APK)"}
SET_ASIDE = ("compat-incompatible", "compat-conflicting", "compat-other_device", "list-not-an-app")
HUMAN = {"abandoned": "no push for 18+ months", "archived": "archived", "missing-license": "no licence", "missing-description": "no description", "fork": "fork",
         "no-release": "no release", "no-apk-in-release": "no APK in the latest release", "no-opk-in-release": "no OPK in the latest release",
         "not-a-real-apk": "download is not an APK", "not-a-real-opk": "download is not an OPK", "file-unreachable": "file not reachable",
         "pre-release-only": "pre-release only", "debug-or-nightly-build": "debug/nightly build", "not-arm64": "no arm64 build marked",
         "compat-incompatible": "README says it is not compatible", "compat-conflicting": "README contradicts itself on this device", "compat-other_device": "named for another device", "list-not-an-app": "a list, not an app", "release-name-mismatch": "download name does not match the project", "opk-inside-zip": "OPK is inside a release ZIP"}


def load_state(extra=None):
    """candidates/review-state.json (what a person decided, committed) overlaid on an optional machine-written file (the Actions cache: first_seen / last_seen / release_tag).
    A person's fields always win."""
    base = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {"schema": 1, "repos": {}}
    if extra and Path(extra).is_file():
        cache = json.loads(Path(extra).read_text(encoding="utf-8")).get("repos", {})
        base["repos"] = {k: {**cache.get(k, {}), **base["repos"].get(k, {})} for k in set(cache) | set(base["repos"])}
    return base


def inventory_entries(device):
    """Inventory entries as comparable records. -> (by repo for look-ups, every entry). A collection repository holds many apps: look-ups see the first, counts see all."""
    out, every = {}, []
    for a in json.loads(INV[device].read_text(encoding="utf-8"))["applications"]:
        if a.get("kind") == "support":
            continue
        src = next((s["url"] for s in a.get("sources", []) if s["type"] == "repo"), "")
        m = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)", src)
        pk = next((p for p in a.get("packages", []) if p.get("signature")), None)
        rec = {"repo": m.group(1) if m else "", "name": a["name"], "url": src or next((s["url"] for s in a.get("sources", [])), ""),
            "group": a.get("group") or CAT.classify(a["name"], a.get("description"), a.get("topics"), a.get("category"))[0], "tags": a.get("tags", []), "license": a.get("license", "unknown"),
            "version": a.get("version", ""), "status": a["status"], "has_file": bool(pk), "description": a.get("description", ""), "hold": a.get("hold"), "hidden": a.get("hidden")}
        out.setdefault(m.group(1).lower() if m else a["id"], rec); every.append(rec)
    return out, every


def tag_norm(t):
    return re.sub(r"^v", "", (t or "").strip().lower())


def why(c):
    bits = []
    ev = (c["compat"]["evidence"] or [None])[0]
    if c["compat"]["level"] == "claimed" and ev: bits.append(f"says: \"{ev['text'][:90]}\"")
    elif c["compat"]["verdict"] in ("family", "ambiguous"): bits.append("no explicit statement for this device")
    for f in c["flags"]:
        if f in HUMAN: bits.append(HUMAN[f])
    return "; ".join(bits)


def line(c):
    rel = c.get("release") or {}
    art = c.get("artifact") or {}
    return (f"- **[{c['repo']}]({c['url']})** · {CAT.LABEL[c['group']]} · ★{c['stars']} · {c['license']} · "
            + (f"{rel['tag']} ({rel['published']})" if rel else "no release") + (f" · [download]({art['url']})" if art.get("url") else "") + f"  \n  {c['description'][:140] or '(no description)'}"
            + (f"  \n  _{why(c)}_" if why(c) else ""))


def classify_candidates(device, cands, state, inv):
    g = {"updated": [], "new": [], "testing": [], "missing": [], "reviewed": [], "aside": []}
    for c in cands:
        c["flags"] = c["flags"] + [x for x in D.suspicious_flags(c) if x not in c["flags"]]   # re-applied, so older search results get the newer checks
        k = c["repo"].lower()
        s = state["repos"].get(k)
        if any(f in SET_ASIDE for f in c["flags"]):
            g["aside"].append(c); continue
        rel_tag = (c.get("release") or {}).get("tag")
        known_tag = (s or {}).get("release_tag") or (tag_norm(inv[k]["version"]) if k in inv else None)
        changed = bool(rel_tag and known_tag and tag_norm(rel_tag) != tag_norm(known_tag))
        if s and s.get("status") in ("rejected", "reviewed") and not changed:
            g["reviewed"].append((c, s)); continue
        if changed and (s or k in inv):
            g["updated"].append(c); continue
        real = (c.get("artifact") or {}).get("real_file")
        missing = real is not True or "missing-license" in c["flags"] or "missing-description" in c["flags"]
        if missing:
            g["missing"].append(c)
        elif s or k in inv:
            g["testing"].append(c)
        else:
            g["new"].append(c)
    for v in g.values(): v.sort(key=lambda x: -(x[0] if isinstance(x, tuple) else x)["score"])
    return g


def inventory_groups(device, every, cand_keys, state):
    """Known (inventory) entries NOT re-examined this run: still needing a device test, or missing information."""
    test, miss = [], []
    for e in every:
        k = e["repo"].lower()
        if k in cand_keys or e["hold"] or e["hidden"]:
            continue
        s = state["repos"].get(k, {})
        if s.get("status") in ("rejected", "reviewed"):
            continue
        (miss if (e["license"] in ("unknown", "NOASSERTION") or not e["has_file"] or e["status"] in ("listed", "unverified", "source-only")) else test).append(e)
    return test, miss


def counts(device, every, cands):
    """Unique applications per category: the inventory plus candidates that are not in it. One application counts once."""
    seen, by = set(), {}
    for e in every:
        if e["hidden"]: continue
        seen.add(e["repo"].lower()); by[e["group"]] = by.get(e["group"], 0) + 1
    new = {}
    for c in cands:
        if c["repo"].lower() not in seen and not any(f in SET_ASIDE for f in c["flags"]) and (c.get("artifact") or {}).get("real_file"):
            new[c["group"]] = new.get(c["group"], 0) + 1
    return by, new


def report(indir, state):
    md, js, digest = [], {}, hashlib.sha256()
    md.append(f"# RetroHatch candidate review · {date.today().isoformat()}\n")
    md.append("Every entry is an UNAPPROVED lead. `claimed` compatibility is a sentence in the project's own text; nothing here was run on a device. Approval, signing and publishing stay manual.\n")
    summary = ["| Device | " + " | ".join(CAT.LABEL[g] for g in CAT.GROUP_IDS) + " | Total |", "|---|" + "---|" * (len(CAT.GROUP_IDS) + 1)]
    body = []
    for device in ("rg-nano", "rg-rotate"):
        f = indir / f"candidates-{device}.json"
        doc = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"candidates": [], "errors": ["no search run for this device"], "requests": 0, "generated": ""}
        inv, every = inventory_entries(device)
        cands = doc["candidates"]
        for c in cands: c["flags"] = c["flags"] + [x for x in D.suspicious_flags(c) if x not in c["flags"]]
        g = classify_candidates(device, cands, state, inv)
        test_inv, miss_inv = inventory_groups(device, every, {c["repo"].lower() for c in cands}, state)
        by, new = counts(device, every, cands)
        cells = [f"{by.get(x, 0)}" + (f" (+{new[x]} new)" if new.get(x) else "") for x in CAT.GROUP_IDS]
        summary.append(f"| {NAME[device]} | " + " | ".join(cells) + f" | {sum(by.values())}" + (f" (+{sum(new.values())} new)" if new else "") + " |")
        body.append(f"\n## {NAME[device]}\n")
        body.append(f"_Search {doc.get('generated') or 'not run'} · {len(cands)} repositories examined · {doc.get('requests', 0)} requests"
                    + (f" · stopped: {doc['stopped'][0]}" if doc.get("stopped") else "") + (f" · **errors:** {'; '.join(doc['errors'][:3])}" if doc.get("errors") else "") + "_\n")
        sec = [("Updated candidates", g["updated"], "release newer than the one on record"), ("New candidates", g["new"], "first seen, real downloadable file, nothing missing")]
        for title, items, hint in sec:
            body.append(f"### {title} ({len(items)})\n_{hint}_\n")
            body += [line(c) for c in items[:15]] or ["_none_", ""]
            if len(items) > 15: body.append(f"_…and {len(items) - 15} more in review.json_")
            for c in items: digest.update(f"{device}:{c['repo']}:{(c.get('release') or {}).get('tag')}".encode())
        body.append(f"\n### Needs compatibility testing ({len(g['testing'])} found this run, {len(test_inv)} on record)\n_real file, not yet run on the device; no statement is a test_\n")
        body += [line(c) for c in g["testing"][:10]]
        body += [f"- [{e['name']}]({e['url']}) · {CAT.LABEL[e['group']]} · {e['license']} · {e['version'] or 'no version'}" for e in sorted(test_inv, key=lambda e: e["name"].lower())[:10]]
        if len(test_inv) > 10: body.append(f"_…and {len(test_inv) - 10} more in candidates/{INV[device].name}_")
        body.append(f"\n### Missing information ({len(g['missing'])} found this run, {len(miss_inv)} on record)\n_no real file in the latest release, no licence, or no description_\n")
        body += [line(c) for c in g["missing"][:10]]
        body += [f"- [{e['name']}]({e['url']}) · {e['license']} · {e['status']}" for e in sorted(miss_inv, key=lambda e: e["name"].lower())[:8]]
        body.append(f"\n### Previously reviewed, rejected or set aside ({len(g['reviewed']) + len(g['aside'])})\n")
        body += [f"- [{c['repo']}]({c['url']}) · {s.get('status')}: {s.get('reason', '')}" for c, s in g["reviewed"]]
        body += [f"- [{c['repo']}]({c['url']}) · set aside: {why(c)}" for c in g["aside"][:12]]
        if not g["reviewed"] and not g["aside"]: body.append("_none_")
        js[device] = {"counts": by, "new_counts": new, **{k: [(x[0] if isinstance(x, tuple) else x)["repo"] for x in v] for k, v in g.items()}}
    md += summary + body
    return "\n".join(md) + "\n", js, digest.hexdigest()[:16]


def update_state(indir, state):
    today = date.today().isoformat()
    for device in ("rg-nano", "rg-rotate"):
        f = indir / f"candidates-{device}.json"
        if not f.is_file(): continue
        for c in json.loads(f.read_text(encoding="utf-8"))["candidates"]:
            k = c["repo"].lower()
            s = state["repos"].setdefault(k, {"device": device, "status": "seen", "first_seen": today})
            s["last_seen"] = today
            if c.get("release"): s["release_tag"] = c["release"]["tag"]
            s["license"] = c["license"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="indir", default=str(ROOT / "build" / "discovery"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--update-state", action="store_true", help="record first/last seen and release tags (into --state, else candidates/review-state.json)")
    ap.add_argument("--state", default=None, help="machine-written state file (e.g. the Actions cache); a person's candidates/review-state.json is still read and wins")
    a = ap.parse_args()
    indir = Path(a.indir); out = Path(a.out or a.indir); out.mkdir(parents=True, exist_ok=True)
    state = load_state(a.state)
    md, js, digest = report(indir, state)
    (out / "review.md").write_text(md, encoding="utf-8"); (out / "review.json").write_text(json.dumps(js, indent=1) + "\n", encoding="utf-8"); (out / "review.digest").write_text(digest + "\n")
    if a.update_state:
        update_state(indir, state)
        target = Path(a.state) if a.state else STATE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{out / 'review.md'}  digest {digest}" + ("  (state updated)" if a.update_state else ""))


if __name__ == "__main__":
    main()
