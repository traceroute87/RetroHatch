#!/usr/bin/env python3
"""Regenerate tests/trust_fixture_android/ : a SYNTHETIC catalog with one Nano OPK app and one Android APK app, built by tools/trust.py and signed
with a throwaway key whose private half is discarded. Nothing here is a real app or a real signature of the project. Only the public key is kept
(signed/PUBKEY.hex). Used by tests/test_android_catalog.py, tests/test_trust_native.py and the Kotlin unit tests (android/app/src/test)."""
import hashlib, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import trust as T
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FX = HERE / "trust_fixture_android"
SRC = HERE / "trust_fixture" / "catalog"
sha = lambda s: hashlib.sha256(s.encode()).hexdigest()
APK_SHA, SIGNER = sha("fixture-apk-file"), sha("fixture-signing-certificate")

apk_app = {
    "schema": 1, "id": "fixtureapk", "name": "Fixture APK (synthetic)", "description": "FIXTURE ONLY - not a real app.", "developer": "retrohatch-fixture",
    "source": "https://github.com/retrohatch-fixture/fixtureapk", "license": "MIT", "category": "utility",
    "artifacts": [{
        "device": "rg-rotate", "firmware": "android-12", "format": "apk", "status": "available", "version": "1.0.0",
        "url": "https://github.com/retrohatch-fixture/fixtureapk/releases/download/v1.0.0/fixtureapk.apk", "sha256": APK_SHA, "size": 4096,
        "android": {"package": "app.retrohatch.fixture", "version_code": 7, "signer_sha256": [SIGNER]},
        "compatibility": {"level": "verified", "evidence": [{"sha256": APK_SHA, "date": "2026-11-09", "tester": "fixture", "note": "synthetic"}]}}]}
approval = {"app": "fixtureapk", "device": "rg-rotate", "firmware": "android-12", "sha256": APK_SHA, "size": 4096,
            "release": "https://github.com/retrohatch-fixture/fixtureapk/releases/tag/v1.0.0", "approved_by": "fixture", "date": "2026-11-09"}

if FX.exists():
    shutil.rmtree(FX)
cat = FX / "catalog"
for d in ("apps", "devices"):
    (cat / d).mkdir(parents=True)
shutil.copy(SRC / "apps" / "examplepad.json", cat / "apps")
shutil.copy(SRC / "devices" / "rg-nano.json", cat / "devices")
shutil.copy(HERE.parent / "catalog" / "devices" / "rg-rotate.json", cat / "devices")
(cat / "apps" / "fixtureapk.json").write_text(json.dumps(apk_app, indent=2) + "\n")
ap = json.loads((SRC / "approvals.json").read_text())
ap["approvals"].append(approval)
(cat / "approvals.json").write_text(json.dumps(ap, indent=2) + "\n")

doc = T.build(cat, 1, "2026-11-09")
idx = T.canonical(doc)
key = Ed25519PrivateKey.generate()
(FX / "signed").mkdir()
(FX / "signed" / "index.json").write_bytes(idx)
(FX / "signed" / "index.json.sig").write_bytes(T.sign(idx, key))
(FX / "signed" / "PUBKEY.hex").write_text(T.raw_pub(key).hex() + "\n")
print("fixture written:", FX, "key id", T.key_id(T.raw_pub(key)))
