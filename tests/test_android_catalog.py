"""Run: python tests/test_android_catalog.py
Android APK entries in the shared catalog format: the Python trust tools accept a mixed Nano-OPK + Android-APK index, enforce the APK fields
(package, version_code, signer_sha256), and keep every OPK rule for OPK artifacts. Nano OPK-only behaviour is covered by test_trust.py."""
import copy, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import trust as T

FX = HERE / "trust_fixture_android" / "signed"
idx, sig, pub = (FX / "index.json").read_bytes(), (FX / "index.json.sig").read_bytes(), (FX / "PUBKEY.hex").read_text().strip()

doc, state, _ = T.verify(idx, sig, [pub])
assert doc["serial"] == 1 and {a["id"] for a in doc["apps"]} == {"examplepad", "fixtureapk"}
assert {d["id"] for d in doc["devices"]} == {"rg-nano", "rg-rotate"}
apk = next(a for a in doc["apps"] if a["id"] == "fixtureapk")["artifacts"][0]
assert apk["format"] == "apk" and "install" not in apk and apk["android"]["package"] == "app.retrohatch.fixture" and apk["android"]["version_code"] == 7
assert T.check_index(doc) == []


def mut(fn):
    d = copy.deepcopy(doc)
    fn(next(a for a in d["apps"] if a["id"] == "fixtureapk")["artifacts"][0], d)
    return T.check_index(d)


def bad(fn, what):
    e = mut(fn)
    assert e and any(what in x for x in e), (what, e)


bad(lambda a, d: a.pop("android"), "android")
bad(lambda a, d: a["android"].pop("package"), "package")
bad(lambda a, d: a["android"].pop("signer_sha256"), "signer_sha256")
bad(lambda a, d: a["android"].update(package="nodots"), "package")
bad(lambda a, d: a["android"].update(package="app.1bad"), "package")
bad(lambda a, d: a["android"].update(package="a" * 254 + ".bb"), "package")
bad(lambda a, d: a["android"].update(version_code=0), "version_code")
bad(lambda a, d: a["android"].update(version_code=2**31), "version_code")
bad(lambda a, d: a["android"].update(version_code="7"), "version_code")
bad(lambda a, d: a["android"].update(signer_sha256=[]), "signer_sha256")
bad(lambda a, d: a["android"].update(signer_sha256=["AB" * 32]), "signer_sha256")
bad(lambda a, d: a["android"].update(signer_sha256=[a["android"]["signer_sha256"][0]] * 2), "signer_sha256")
bad(lambda a, d: a["android"].update(extra=1), "extra")
bad(lambda a, d: a.update(install={"dest_name": "x.opk"}), "install")
bad(lambda a, d: a.update(url="https://example.com/fixtureapk.apk"), "release")
bad(lambda a, d: a.update(sha256="0" * 64), "evidence")
bad(lambda a, d: a.update(format="opk"), "format")
bad(lambda a, d: a.update(status="unavailable"), "available")

# the OPK artifact keeps all its rules, and must not carry android fields
opk = lambda d: next(a for a in d["apps"] if a["id"] == "examplepad")["artifacts"][0]
d = copy.deepcopy(doc); opk(d)["android"] = {"package": "a.b", "version_code": 1, "signer_sha256": ["0" * 64]}
assert any("android" in x for x in T.check_index(d))
d = copy.deepcopy(doc); opk(d)["install"]["dest_name"] = "examplepad.bin"
assert any("protected or not .opk" in x for x in T.check_index(d))
d = copy.deepcopy(doc); del opk(d)["install"]
assert T.check_index(d)

# tampering the signed index or signature fails
t = bytearray(idx); t[40] ^= 1
for args in ((bytes(t), sig), (idx, sig.replace(b"ed25519", b"ed448"))):
    try:
        T.verify(*args, [pub]); raise SystemExit("tampered input accepted")
    except T.TrustError:
        pass
print("android catalog tests OK")
