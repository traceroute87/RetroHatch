#!/usr/bin/env python3
"""Stage the Phase 6C-3 on-device verifier test (throwaway keys, generated fresh, private halves discarded).

  python tests/make_hw_fixtures.py --binary build/rh_verify_arm --out build/hw-6c3

Writes OUT/{rh_verify, run.sh, expected.tsv, fixtures/*, SHA256SUMS}. Nothing is signed with a production key, nothing is
installed; the Nano runs it from RAM (/tmp) and it writes no files. See docs/HARDWARE_TEST_6C3.md."""
import argparse, base64, copy, hashlib, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import trust as T
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FX = HERE / "trust_fixture"
DEV, FW = "rg-nano", "funkeyos-drum78"

RUN_SH = r"""#!/bin/sh
# Read-only on-device check of the signed-catalog verifier. Run from RAM: sh run.sh   (writes nothing, no network)
cd "$(dirname "$0")" || exit 1
echo "== environment"; uname -a; grep -E 'model name|Hardware|Processor|BogoMIPS' /proc/cpuinfo | head -4; grep -E 'MemTotal|MemFree|MemAvailable' /proc/meminfo
echo "== binary"; sha256sum rh_verify; ls -l rh_verify
echo "== cases"
pass=0; fail=0
while IFS="$(printf '	')" read -r name expect args; do
  case "$name" in ""|"#"*) continue;; esac
  out=$(./rh_verify $args 2>&1); rc=$?
  case "$out" in "$expect"*) pass=$((pass+1)); echo "PASS $name (rc=$rc)";; *) fail=$((fail+1)); echo "FAIL $name: expected '$expect' got '$out' (rc=$rc)";; esac
done < expected.tsv
echo "cases: pass=$pass fail=$fail"
echo "== timing and memory (small catalog, 20 runs)"
./rh_verify --index fixtures/valid.idx --sig fixtures/valid.sig --pubkey @PUBA@ --device rg-nano --firmware funkeyos-drum78 --repeat 20 --stats
echo "== timing and memory (large catalog, 10 runs)"
./rh_verify --index fixtures/big.idx --sig fixtures/big.sig --pubkey @PUBA@ --device rg-nano --firmware funkeyos-drum78 --repeat 10 --stats
echo "== after"; grep -E 'MemFree' /proc/meminfo
[ "$fail" = 0 ]
"""


def signed(payload, key, **over):
    d = {"v": 1, "alg": "ed25519", "key_id": T.key_id(T.raw_pub(key)), "sig": base64.b64encode(key.sign(payload)).decode()}
    d.update(over)
    return T.canonical(d)


def big_catalog():
    base = T.build(FX / "catalog", 9, "2026-10-26")
    n = 100
    while True:
        d = copy.deepcopy(base)
        for i in range(n):
            a = copy.deepcopy(base["apps"][0]); ap = copy.deepcopy(base["approvals"][0])
            app_id, sha = f"fixture{i:03d}", hashlib.sha256(f"app{i}".encode()).hexdigest()
            src = f"https://github.com/retrohatch-fixture/{app_id}"
            a.update(id=app_id, name=f"Fixture {i}", source=src)
            x = a["artifacts"][0]
            x.update(url=f"{src}/releases/download/v1/{app_id}.opk", sha256=sha, size=1000 + i)
            x["install"] = {"dest_name": f"{app_id}.opk"}
            x["compatibility"]["evidence"][0]["sha256"] = sha
            ap.update(app=app_id, sha256=sha, size=1000 + i, release=f"{src}/releases/tag/v1")
            if i:
                d["apps"].append(a); d["approvals"].append(ap)
            else:
                d["apps"][0], d["approvals"][0] = a, ap
        if not T.check_index(d):
            return d
        n -= 10
        assert n > 0, T.check_index(d)[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    out = a.out
    if out.exists():
        shutil.rmtree(out)
    (out / "fixtures").mkdir(parents=True)
    A, B = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()   # throwaway; never written to disk
    PA, PB = T.raw_pub(A).hex(), T.raw_pub(B).hex()
    fx = out / "fixtures"
    rows = []

    def put(name, idx, sig):
        (fx / f"{name}.idx").write_bytes(idx)
        if sig is not None:
            (fx / f"{name}.sig").write_bytes(sig)

    def case(name, expect, idx, sig, keys=(PA,), dev=DEV, fw=FW, state=None):
        put(name, idx, sig)
        args = f"--index fixtures/{name}.idx --sig fixtures/{name}.sig --device {dev} --firmware {fw}"
        args += "".join(f" --pubkey {k}" for k in keys)
        if state:
            (fx / f"{name}.state").write_bytes(state.encode())
            args += f" --state fixtures/{name}.state"
        rows.append(f"{name}\t{expect}\t{args}")

    doc = T.build(FX / "catalog", 3, "2026-10-26")
    idx = T.canonical(doc)
    sig = signed(idx, A)
    h = hashlib.sha256(idx).hexdigest()
    put("valid", idx, sig)
    case("valid", "OK serial=3 apps=1 artifacts=1", idx, sig)
    case("valid_rotation_overlap", "OK serial=3", idx, sig, keys=(PB, PA))
    idx_b = T.canonical(T.build(FX / "catalog", 4, "2026-10-26"))
    case("valid_signed_by_new_key", "OK serial=4", idx_b, signed(idx_b, B), keys=(PA, PB))
    case("modified_catalog", "FAIL 6", idx.replace(b"ExamplePad", b"ExamplePwn"), sig)
    case("modified_catalog_extra_byte", "FAIL 6", idx + b"\n", sig)
    bad = bytearray(base64.b64decode(__import__("json").loads(sig)["sig"])); bad[7] ^= 1
    case("modified_signature", "FAIL 6", idx, signed(idx, A, sig=base64.b64encode(bytes(bad)).decode()))
    case("truncated_signature_doc", "FAIL 4", idx, sig[:-9])
    case("signature_wrong_length", "FAIL 4", idx, signed(idx, A, sig="AAAA"))
    case("missing_signature", "FAIL 2", idx, None)
    case("unknown_key", "FAIL 5", idx, sig, keys=(PB,))
    case("wrong_key_claiming_ours", "FAIL 6", idx, signed(idx, B, key_id=T.key_id(T.raw_pub(A))))
    case("no_trusted_key_configured", "FAIL 3", idx, sig, keys=())
    junk = b'{"a":[1,2,'
    case("malformed_catalog_signed", "FAIL 7", junk, signed(junk, A))
    import json
    pretty = json.dumps(doc, indent=1).encode()
    case("noncanonical_catalog_signed", "FAIL 7", pretty, signed(pretty, A))
    dup = b'{"a":1,"a":2}'
    case("duplicate_field_signed", "FAIL 7", dup, signed(dup, A))
    d2 = copy.deepcopy(doc); d2["approvals"].clear()
    r = T.canonical(d2)
    case("policy_unapproved_signed", "FAIL 8", r, signed(r, A))
    d3 = copy.deepcopy(doc); d3["apps"][0]["artifacts"][0]["compatibility"]["level"] = "community"
    r = T.canonical(d3)
    case("policy_unverified_signed", "FAIL 8", r, signed(r, A))
    case("device_mismatch", "FAIL 9", idx, sig, dev="some-other-handheld")
    case("firmware_mismatch", "FAIL 9", idx, sig, fw="funkeyos-future")
    case("rollback_newer_baseline", "FAIL 10", idx, sig, state=f"5 {h}\n")
    case("same_serial_different_hash", "FAIL 11", idx, sig, state=f"3 {'1' * 64}\n")
    case("same_index_again_ok", "OK serial=3", idx, sig, state=f"3 {h}\n")
    case("older_baseline_ok", "OK serial=3", idx, sig, state=f"2 {'0' * 64}\n")
    huge = b"[" + b"0," * 150000 + b"0]"
    case("oversize_index_signed", "FAIL 2", huge, signed(huge, A))
    many = T.canonical({**doc, "revoked": [{"app": "a", "sha256": "0" * 64, "reason": "r"}] * 1300})
    case("too_many_tokens_signed", "FAIL 12", many, signed(many, A))
    deep = b"[" * 40 + b"]" * 40
    case("too_deeply_nested_signed", "FAIL 12", deep, signed(deep, A))
    bigdoc = big_catalog()
    bidx = T.canonical(bigdoc)
    put("big", bidx, signed(bidx, A))
    case("big_valid_catalog", f"OK serial=9 apps={len(bigdoc['apps'])}", bidx, signed(bidx, A))
    (out / "expected.tsv").write_bytes(("# name<TAB>expected output prefix<TAB>arguments\n" + "\n".join(rows) + "\n").encode())   # LF only: the Nano shell reads it
    (out / "run.sh").write_bytes(RUN_SH.replace("@PUBA@", PA).encode())
    shutil.copy(a.binary, out / "rh_verify")
    sums = []
    for p in sorted(out.rglob("*")):
        if p.is_file():
            sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}")
    (out / "SHA256SUMS").write_bytes(("\n".join(sums) + "\n").encode())
    print(f"staged {len(rows)} cases, big catalog {len(bigdoc['apps'])} apps / {len(bidx)} bytes -> {out}")


if __name__ == "__main__":
    main()
