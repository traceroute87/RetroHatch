#!/usr/bin/env python3
"""Check ONE locally downloaded release asset against its hand-written catalog entry. Host only.
Never executes or mounts the file; never downloads. Each line is a SEPARATE trust decision:

  integrity     size + sha256 equal the catalog entry        (says nothing about who published the file)
  source        artifact URL is a release download of the entry's own GitHub repo + tag (URL shape only;
                you must still confirm the release/publisher by hand)
  license       a known SPDX id is recorded
  compat        level + evidence sha256 for exactly these bytes; only 'verified' is publishable
  destination   dest_name allowed, not protected, not used by another app
  package       squashfs magic; with --inspect also `unsquashfs -ll` (listing only) must show a .desktop file
  approval      a human approval record for this exact sha256 exists (informational before approval)

  artifact_verify.py APP_ID --file X.opk [--catalog DIR] [--device rg-nano] [--firmware ID] [--inspect]
Exit 0 only if every machine check passes. 'approval' never affects it: only a human adds that record.
"""
import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path

import trust, validate


def verify_artifact(catalog, app_id, file, device="rg-nano", firmware="funkeyos-drum78", inspect=False):
    cat = Path(catalog)
    errs = validate.check(cat, None if cat.resolve() == validate.ROOT.resolve() else validate.ROOT / "schema")
    if errs:
        raise trust.TrustError("catalog invalid: " + errs[0])
    apps = {p.stem: validate.load(p) for p in sorted((cat / "apps").glob("*.json"))}
    app = apps.get(app_id)
    arts = [a for a in (app or {}).get("artifacts", []) if a["device"] == device and a["firmware"] == firmware]
    if not arts:
        raise trust.TrustError(f"no artifact for {app_id} on {device}/{firmware}")
    art = arts[0]
    data = Path(file).read_bytes()
    r = {}
    got = hashlib.sha256(data).hexdigest()
    r["integrity"] = (len(data) == art.get("size") and got == art.get("sha256"),
                      f"size {len(data)} vs {art.get('size')}; sha256 {got[:12]} vs {str(art.get('sha256'))[:12]}")
    r["source"] = (art.get("status") == "available" and trust.release_ok(app["source"], art.get("url")),
                   f"{art.get('url')} under {app['source']} (publisher authenticity NOT established)")
    r["license"] = (app["license"] != "unknown", app["license"])
    comp = art["compatibility"]
    ev = [e for e in comp.get("evidence", []) if e["sha256"] == art.get("sha256")]
    r["compat"] = (comp["level"] in trust.PUBLISH_LEVELS and bool(ev), f"level {comp['level']}, {len(ev)} evidence record(s) for this sha256")
    others = [a for a in apps.values() if a["id"] != app_id]
    dp = trust.dest_problems([app] + others)
    r["destination"] = (not any(e.startswith(app_id + ":") or f"'{app_id}'" in e for e in dp), "; ".join(dp) or art.get("install", {}).get("dest_name", "none"))
    ok, why = data[:4] == b"hsqs", "squashfs magic" if data[:4] == b"hsqs" else "not a squashfs image"
    if ok and inspect:
        tool = shutil.which("unsquashfs")
        if not tool:
            ok, why = False, "--inspect: unsquashfs not found"
        else:
            out = subprocess.run([tool, "-ll", str(file)], capture_output=True, text=True, timeout=60)
            ok = out.returncode == 0 and ".desktop" in out.stdout
            why = "listing shows a .desktop entry" if ok else "listing failed or has no .desktop entry"
    r["package"] = (ok, why)
    ap = (cat / "approvals.json")
    appr = validate.load(ap)["approvals"] if ap.is_file() else []
    hit = [a for a in appr if trust.approval_key(a) == (app_id, device, firmware, art.get("sha256"))]
    r["approval"] = (bool(hit), f"approved by {hit[0]['approved_by']} on {hit[0]['date']}" if hit else "no approval record (a human adds one after review)")
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app_id"); ap.add_argument("--file", required=True)
    ap.add_argument("--catalog", type=Path, default=validate.ROOT)
    ap.add_argument("--device", default="rg-nano"); ap.add_argument("--firmware", default="funkeyos-drum78")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()
    try:
        res = verify_artifact(a.catalog, a.app_id, a.file, a.device, a.firmware, a.inspect)
    except (trust.TrustError, OSError) as e:
        print(f"FAIL: {e}", file=sys.stderr); sys.exit(1)
    for k, (ok, why) in res.items():
        print(f"{k:12} {'pass' if ok else ('PENDING' if k == 'approval' else 'FAIL'):8} {why}")
    sys.exit(0 if all(ok for k, (ok, _) in res.items() if k != "approval") else 1)
