#!/usr/bin/env python3
"""Build SIGNED DEV catalogs for the RH Probe test app (never for production).

  python tools/make_dev_catalog.py --out build/dev-catalog [--key PEM]

Without --key a throwaway key is generated in memory (used by the host tests; its public half is written to pubkey.hex).
With --key (the DEV signing key kept outside the repo) the same files are what the DEV OPK bundles and what the LAN test
server hands out. Source/URLs use a clearly fake GitHub repo (retrohatch-fixture/rhprobe) so the publish policy
(`release download of the source repo`) is satisfied without touching a real repository.

Files in OUT:
  bundled.pkg          serial 1: RH Probe 1.0.0                       (sig document + "\\n" + index, the on-device cache format)
  index-2.json/.sig    serial 2: RH Probe 1.1.0 (+ an extra app)       (what a refresh downloads)
  index-2.tampered.json  serial 2 index with one changed byte          (same .sig must now fail)
  index-1.json/.sig    serial 1 again                                  (rollback after serial 2)
  index-2b.json/.sig   serial 2, different content                     (same-serial fork)
  gh/retrohatch-fixture/rhprobe/releases/download/v1.0.0|v1.1.0/rhprobe_funkey-s.opk   the packages (from build/probe)
  wrong/...            same names, other bytes                         (hash mismatch)
  pubkey.hex"""
import argparse, base64, copy, hashlib, json, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import trust as T
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SRC = "https://github.com/retrohatch-fixture/rhprobe"


def app_doc(version, sha, size):
    return {"schema": 1, "id": "rhprobe", "name": "RH Probe (test)", "description": "TEST APP - signed DEV catalog only. Not a real app.",
            "developer": "traceroute87", "source": SRC, "license": "MIT", "category": "application",
            "artifacts": [{"device": "rg-nano", "firmware": "funkeyos-drum78", "format": "opk", "status": "available", "version": version,
                           "url": f"{SRC}/releases/download/v{version}/rhprobe_funkey-s.opk", "sha256": sha, "size": size,
                           "install": {"dest_name": "rhprobe_funkey-s.opk"},
                           "compatibility": {"level": "verified", "evidence": [{"sha256": sha, "date": "2026-10-25", "tester": "traceroute87",
                                                                              "note": "RG Nano hardware test (Phase 5C)"}]}}]}


def other_doc():
    sha = "e" * 64
    src = "https://github.com/retrohatch-fixture/otherpad"
    d = app_doc("1.0", sha, 1234)
    d.update(id="otherpad", name="Other Pad (test)", source=src)
    a = d["artifacts"][0]
    a.update(url=f"{src}/releases/download/v1.0/otherpad_funkey-s.opk")
    a["install"] = {"dest_name": "otherpad_funkey-s.opk"}
    return d


def catalog(td, apps, serial, date="2026-10-26"):
    c = Path(td) / f"c{serial}{len(apps)}{date}"
    (c / "apps").mkdir(parents=True); (c / "devices").mkdir()
    shutil.copy(ROOT / "catalog" / "devices" / "rg-nano.json", c / "devices")
    approvals = []
    for a in apps:
        (c / "apps" / f"{a['id']}.json").write_text(json.dumps(a))
        x = a["artifacts"][0]
        approvals.append({"app": a["id"], "device": "rg-nano", "firmware": "funkeyos-drum78", "sha256": x["sha256"], "size": x["size"],
                          "release": x["url"].rsplit("/releases/download/", 1)[0] + "/releases/tag/" + x["url"].split("/download/")[1].split("/")[0],
                          "approved_by": "dev-fixture", "date": "2026-10-26"})
    (c / "approvals.json").write_text(json.dumps({"schema": 1, "approvals": approvals, "revoked": []}))
    return T.canonical(T.build(c, serial, date))


def sign(idx, key):
    return T.canonical({"v": 1, "alg": "ed25519", "key_id": T.key_id(T.raw_pub(key)), "sig": base64.b64encode(key.sign(idx)).decode()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--key", type=Path)
    ap.add_argument("--probe-dir", type=Path, default=ROOT / "build" / "probe")
    a = ap.parse_args()
    key = serialization.load_pem_private_key(a.key.read_bytes(), None) if a.key else Ed25519PrivateKey.generate()
    out = a.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    pk = {v: (a.probe_dir / f"rhprobe_{v}.opk").read_bytes() for v in ("1.0.0", "1.1.0")}
    sha = {v: hashlib.sha256(b).hexdigest() for v, b in pk.items()}
    with tempfile.TemporaryDirectory() as td:
        d1 = app_doc("1.0.0", sha["1.0.0"], len(pk["1.0.0"]))
        d2 = app_doc("1.1.0", sha["1.1.0"], len(pk["1.1.0"]))
        i1 = catalog(td, [d1], 1)
        i2 = catalog(td, [d2, other_doc()], 2)
        i2b = catalog(td, [d2], 2, "2026-11-01")
        (out / "bundled.pkg").write_bytes(sign(i1, key) + b"\n" + i1)
        for name, idx in (("index-1", i1), ("index-2", i2), ("index-2b", i2b)):
            (out / f"{name}.json").write_bytes(idx)
            (out / f"{name}.json.sig").write_bytes(sign(idx, key))
        t = bytearray(i2); t[t.index(b"RH Probe")] ^= 0x20
        (out / "index-2.tampered.json").write_bytes(bytes(t))
    for v, b in pk.items():
        d = out / "gh" / "retrohatch-fixture" / "rhprobe" / "releases" / "download" / f"v{v}"
        d.mkdir(parents=True); (d / "rhprobe_funkey-s.opk").write_bytes(b)
        w = out / "wrong" / "retrohatch-fixture" / "rhprobe" / "releases" / "download" / f"v{v}"
        w.mkdir(parents=True); (w / "rhprobe_funkey-s.opk").write_bytes(bytes(reversed(b)))
    (out / "pubkey.hex").write_text(T.raw_pub(key).hex() + "\n")
    (out / "sha.txt").write_text("".join(f"{v} {sha[v]} {len(pk[v])}\n" for v in pk))
    print(f"dev catalogs -> {out} (key id {T.key_id(T.raw_pub(key))}, probe sha {sha['1.0.0'][:8]} / {sha['1.1.0'][:8]})")


if __name__ == "__main__":
    main()
