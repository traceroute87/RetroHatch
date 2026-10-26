"""Run: python tests/test_trust.py  (no framework, no network, keys are generated in memory)."""
import base64, copy, json, shutil, sys, tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import artifact_verify as AV
import trust as T
import validate
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FX = HERE / "trust_fixture"
OPK = FX / "examplepad_funkey-s.opk"
KEY, KEY2 = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
PUB, PUB2 = T.raw_pub(KEY).hex(), T.raw_pub(KEY2).hex()


def fails(fn, *frag):
    try:
        fn()
    except T.TrustError as e:
        assert all(f in str(e) for f in frag), (frag, str(e))
        return
    raise AssertionError(f"expected TrustError {frag}")


def catalog(mutate=None, approvals=None):
    """Temp copy of the fixture catalog; mutate(app_dict) / approvals(dict) edit it in place."""
    t = Path(tempfile.mkdtemp())
    shutil.copytree(FX / "catalog", t / "c")
    for fn, mut in (("apps/examplepad.json", mutate), ("approvals.json", approvals)):
        if mut:
            p = t / "c" / fn
            d = json.loads(p.read_text())
            mut(d)
            p.write_text(json.dumps(d))
    return t / "c"


def art(app):
    return app["artifacts"][0]


def build(c=None, serial=1):
    return T.build(c or FX / "catalog", serial, "2026-10-26")


def signed(doc=None, key=KEY):
    idx = T.canonical(doc or build())
    return idx, T.sign(idx, key)


# ---- valid + the committed example ----
idx, sig = signed()
doc, st, warn = T.verify(idx, sig, [PUB])
assert doc["apps"][0]["id"] == "examplepad" and st["serial"] == 1 and warn == []
ex_idx, ex_sig, ex_pub = (FX / "signed" / n for n in ("index.json", "index.json.sig", "PUBKEY.hex"))
pub = ex_pub.read_text().strip()
assert T.verify(ex_idx.read_bytes(), ex_sig.read_bytes(), [pub])[0]["serial"] == 1
assert ex_idx.read_bytes() == idx                                       # example == deterministic build of the fixture
fails(lambda: T.verify(ex_idx.read_bytes(), ex_sig.read_bytes(), trusted=[]), "no trusted key")   # empty key list: fail closed

# ---- modified catalog / signature / missing / wrong key ----
fails(lambda: T.verify(idx.replace(b"ExamplePad", b"ExamplePwn"), sig, [PUB]), "bad signature")
fails(lambda: T.verify(idx + b" ", sig, [PUB]), "bad signature")
bad = json.loads(sig); bad["sig"] = base64.b64encode(bytes(64)).decode()
fails(lambda: T.verify(idx, T.canonical(bad), [PUB]), "bad signature")
fails(lambda: T.verify(idx, b"", [PUB]), "missing")
fails(lambda: T.verify(b"", sig, [PUB]), "missing")
fails(lambda: T.verify(idx, b"{not json", [PUB]), "malformed")
fails(lambda: T.verify(idx, T.canonical({"v": 1}), [PUB]), "unsupported signature")
fails(lambda: T.verify(idx, T.canonical({**json.loads(sig), "alg": "rsa"}), [PUB]), "unsupported signature")
fails(lambda: T.verify(idx, T.canonical({**json.loads(sig), "sig": "!!"}), [PUB]), "malformed")
fails(lambda: T.verify(idx, sig, [PUB2]), "unknown signing key")            # incorrect public key
fails(lambda: T.verify(idx, sig, ["zz"]), "malformed")
fails(lambda: T.verify(idx, sig, []), "no trusted key")
fails(lambda: T.verify(b"x" * (T.MAX_INDEX + 1), sig, [PUB]), "too large")
wrong_kid = T.canonical({**json.loads(sig), "key_id": "0" * 16})
fails(lambda: T.verify(idx, wrong_kid, [PUB]), "unknown signing key")


def raw_signed(payload, key=KEY):
    """Validly signed bytes that the builder would never produce: signature alone must not be enough."""
    return payload, T.canonical({"v": 1, "alg": "ed25519", "key_id": T.key_id(T.raw_pub(key)), "sig": base64.b64encode(key.sign(payload)).decode()})


fails(lambda: T.verify(*raw_signed(json.dumps(build(), indent=1).encode()), [PUB]), "canonical")
fails(lambda: T.verify(*raw_signed(b'{"a":1,"a":2}'), [PUB]), "duplicate key")
fails(lambda: T.verify(*raw_signed(b'{"serial":1.5}'), [PUB]), "disallowed number")
fails(lambda: T.verify(*raw_signed(b"\xff\xfe"), [PUB]), "malformed JSON")
fails(lambda: T.verify(*raw_signed(b"[]"), [PUB]), "not an object")
fails(lambda: T.verify(*raw_signed(T.canonical({**build(), "extra": 1})), [PUB]), "keys wrong")
fails(lambda: T.verify(*raw_signed(T.canonical({**build(), "format": 2})), [PUB]), "format")
fails(lambda: T.verify(*raw_signed(T.canonical({**build(), "serial": 0})), [PUB]), "serial")
fails(lambda: T.verify(*raw_signed(T.canonical({**build(), "generated": "yesterday"})), [PUB]), "YYYY-MM-DD")
fails(lambda: T.verify(*raw_signed(T.canonical({**build(), "apps": "x"})), [PUB]), "lists of objects")


# a signature does not launder a policy violation (defence in depth against a buggy builder)
def tampered(f):
    d = copy.deepcopy(build()); f(d)
    return T.canonical(d)


fails(lambda: T.verify(*raw_signed(tampered(lambda d: d["approvals"].clear())), [PUB]), "no human approval")
fails(lambda: T.verify(*raw_signed(tampered(lambda d: art(d["apps"][0]).__setitem__("url", "https://github.com/evil/x/releases/download/v1/a.opk"))), [PUB]), "release download")
fails(lambda: T.verify(*raw_signed(tampered(lambda d: d["revoked"].append({"app": "examplepad", "sha256": art(d["apps"][0])["sha256"], "reason": "x"}))), [PUB]), "revoked")
fails(lambda: T.verify(*raw_signed(tampered(lambda d: d["approvals"].append({**d["approvals"][0], "sha256": "b" * 64}))), [PUB]), "matches no published")
fails(lambda: T.verify(*raw_signed(tampered(lambda d: d["approvals"][0].__setitem__("size", 1))), [PUB]), "does not match")

# ---- sign refuses non-canonical / violating input ----
fails(lambda: T.sign(json.dumps(build(), indent=1).encode(), KEY), "canonical")
fails(lambda: T.sign(tampered(lambda d: d["approvals"].clear()), KEY), "refusing to sign")


# ---- compatibility / approval gates in the builder ----
def lvl(name):
    return lambda a: art(a)["compatibility"].update(level=name)


fails(lambda: build(catalog(lvl("community"))), "need verified")                         # approved but not hardware verified
fails(lambda: build(catalog(lvl("untested"))), "untested")
fails(lambda: build(catalog(lambda a: art(a)["compatibility"].pop("evidence"))), "evidence")   # verified without evidence
fails(lambda: build(catalog(lambda a: art(a)["compatibility"]["evidence"][0].update(sha256="c" * 64))), "evidence")
assert build(catalog(approvals=lambda d: d["approvals"].clear()))["apps"] == []        # unapproved => never published
assert build(catalog(approvals=lambda d: d["revoked"].append({"app": "examplepad", "sha256": art(json.loads((FX / "catalog/apps/examplepad.json").read_text()))["sha256"], "reason": "r"})))["apps"] == []
fails(lambda: build(catalog(approvals=lambda d: d["approvals"].append(copy.deepcopy(d["approvals"][0])))), "duplicate")
fails(lambda: build(catalog(approvals=lambda d: d["approvals"].append({**d["approvals"][0], "app": "ghost"}))), "without a publishable")
fails(lambda: build(catalog(approvals=lambda d: d.update(extra=1))), "approvals.json must be")
assert T.build(validate.ROOT, 1, "2026-10-26")["apps"] == []                              # real catalog: TaraFi etc. not published
# a second approved app: a duplicate/protected destination is rejected
fails(lambda: build(catalog(lambda a: art(a)["install"].update(dest_name="TaraFi.opk"))), "protected")
fails(lambda: build(catalog(lambda a: art(a)["install"].update(dest_name="RetroHatch.opk"))), "protected")


def two_apps():
    c = catalog()
    a = json.loads((c / "apps/examplepad.json").read_text())
    b = copy.deepcopy(a); b["id"] = "otherpad"; b["source"] = "https://github.com/retrohatch-fixture/otherpad"
    art(b)["url"] = "https://github.com/retrohatch-fixture/otherpad/releases/download/v1.0.0/examplepad_funkey-s.opk"
    art(b)["install"]["dest_name"] = "ExamplePad_funkey-s.opk"                              # same name, different case (FAT)
    (c / "apps/otherpad.json").write_text(json.dumps(b))
    ap = json.loads((c / "approvals.json").read_text())
    ap["approvals"].append({**ap["approvals"][0], "app": "otherpad", "release": "https://github.com/retrohatch-fixture/otherpad/releases/tag/v1.0.0"})
    (c / "approvals.json").write_text(json.dumps(ap))
    return c


fails(lambda: build(two_apps()), "also used by")
# wrong source / release identity
fails(lambda: build(catalog(lambda a: art(a).update(url="https://github.com/other/examplepad/releases/download/v1.0.0/examplepad_funkey-s.opk"))), "release download")
fails(lambda: build(catalog(approvals=lambda d: d["approvals"][0].update(release="https://github.com/retrohatch-fixture/examplepad/releases/tag/v9"))), "does not match")
fails(lambda: build(catalog(lambda a: a.update(source="https://gitlab.com/x/y"))), "release download")
assert T.release_ok("https://github.com/A/B.git", "https://github.com/a/b/releases/download/v1/x.opk", "https://github.com/a/b/releases/tag/v1")
assert not T.release_ok("https://github.com/a/b", "https://github.com/a/b/releases/download/v1/x.opk", "https://github.com/a/b/releases/tag/v2")
assert not T.release_ok("https://github.com/a/b", "https://github.com/a/b/raw/main/x.opk")

# ---- artifact verification (separate decisions) ----
good = AV.verify_artifact(FX / "catalog", "examplepad", OPK)
assert all(ok for ok, _ in good.values()), good
blob = OPK.read_bytes()
tmp = Path(tempfile.mkdtemp())
(tmp / "a.opk").write_bytes(blob[:-1] + b"X")                                              # modified artifact, same size
r = AV.verify_artifact(FX / "catalog", "examplepad", tmp / "a.opk")
assert not r["integrity"][0] and r["source"][0] and r["approval"][0]                         # integrity fails alone; others unaffected
(tmp / "b.opk").write_bytes(blob + b"X")
assert not AV.verify_artifact(FX / "catalog", "examplepad", tmp / "b.opk")["integrity"][0]  # wrong size
(tmp / "c.opk").write_bytes(b"MZ" + blob[2:])
assert not AV.verify_artifact(FX / "catalog", "examplepad", tmp / "c.opk")["package"][0]    # not squashfs
r = AV.verify_artifact(catalog(approvals=lambda d: d["approvals"].clear()), "examplepad", OPK)
assert r["approval"][0] is False and r["integrity"][0]                                       # integrity != approval
r = AV.verify_artifact(catalog(lvl("community")), "examplepad", OPK)
assert not r["compat"][0] and r["integrity"][0]
fails(lambda: AV.verify_artifact(FX / "catalog", "examplepad", OPK, device="other-device"), "no artifact")
fails(lambda: AV.verify_artifact(FX / "catalog", "examplepad", OPK, firmware="nope"), "no artifact")
fails(lambda: AV.verify_artifact(FX / "catalog", "nope", OPK), "no artifact")
r = AV.verify_artifact(catalog(lambda a: art(a)["install"].update(dest_name="TaraFi.opk")), "examplepad", OPK)
assert not r["destination"][0]
r = AV.verify_artifact(two_apps(), "examplepad", OPK)
assert not r["destination"][0]
# discovery output can never be installable: build() reads only hand-written catalog entries + approvals
assert "approvals" not in (HERE.parent / "discovery" / "discover.py").read_text()

# ---- determinism ----
assert T.canonical(build()) == T.canonical(build()) == idx
assert T.sign(idx, KEY) == T.sign(idx, KEY) == sig
assert T.sign(idx, KEY2) != sig
c = catalog(); p = c / "apps/examplepad.json"
p.write_text(json.dumps(json.loads(p.read_text()), indent=4, sort_keys=False))               # formatting/key order irrelevant
assert T.canonical(build(c)) == idx

# ---- key rotation ----
idx2, sig_new = signed(key=KEY2)
assert T.verify(idx2, sig_new, [PUB, PUB2])[0] and T.verify(idx, sig, [PUB2, PUB])[0]       # overlap: old and new both accepted
fails(lambda: T.verify(idx, sig, [PUB2]), "unknown signing key")                             # old key retired
fails(lambda: T.verify(idx2, sig_new, [PUB]), "unknown signing key")                         # client not yet updated
# a catalog cannot introduce its own keys
fails(lambda: T.verify(*raw_signed(T.canonical({**build(), "keys": [PUB2]})), [PUB]), "keys wrong")

# ---- rollback + unreliable clock ----
i1, s1 = signed(T.build(FX / "catalog", 5, "2026-10-26"))
_, st5, _ = T.verify(i1, s1, [PUB])
i4, s4 = signed(T.build(FX / "catalog", 4, "2026-10-26"))
fails(lambda: T.verify(i4, s4, [PUB], st5), "rollback")
i6, s6 = signed(T.build(FX / "catalog", 6, "2026-10-26"))
assert T.verify(i6, s6, [PUB], st5)[1]["serial"] == 6
assert T.verify(i1, s1, [PUB], st5)[1] == st5                                               # same index again is fine (offline re-check)
other5, os5 = signed(T.build(FX / "catalog", 5, "2026-11-01"))
fails(lambda: T.verify(other5, os5, [PUB], st5), "same serial")
ie, se = signed(T.build(FX / "catalog", 7, "2026-10-26", "2026-12-31"))
for now in (None, date(1970, 1, 1), date(2026, 11, 1), date(2999, 1, 1)):                  # wrong clock never rejects
    d, s, w = T.verify(ie, se, [PUB], None, now)
    assert s["serial"] == 7
    assert bool(w) == (now == date(2999, 1, 1)), (now, w)
fails(lambda: T.verify(i4, s4, [PUB], st5, date(1970, 1, 1)), "rollback")                    # clock cannot defeat rollback protection
fails(lambda: T.verify(*raw_signed(T.canonical({**build(), "expires": "soon"})), [PUB]), "YYYY-MM-DD")

# ---- key handling ----
fails(lambda: T.outside_repo(T.ROOT / "signing.pem"), "inside the repository")
assert T.outside_repo(tmp / "k.pem")
print("trust tests OK")
