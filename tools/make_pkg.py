#!/usr/bin/env python3
"""Pack a signed catalog into the on-device single-file format (signature document + newline + index), used for the
snapshot bundled inside an OPK (catalog/catalog.pkg) and the downloaded cache. Verifies it first; refuses otherwise.

  python tools/make_pkg.py site/catalog/index.json out/catalog.pkg [--pubkey HEX]   (default key: catalog/production.pub)"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust as T

ap = argparse.ArgumentParser()
ap.add_argument("index", type=Path); ap.add_argument("out", type=Path); ap.add_argument("--pubkey", action="append")
a = ap.parse_args()
idx = a.index.read_bytes()
sig = a.index.with_name(a.index.name + ".sig").read_bytes()
try:
    T.verify(idx, sig, a.pubkey)
except T.TrustError as e:
    sys.exit(f"FAIL: {e}")
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_bytes(sig + b"\n" + idx)
print(f"{a.out}: {len(sig) + 1 + len(idx)} bytes (verified)")
