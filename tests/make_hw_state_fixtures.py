#!/usr/bin/env python3
"""Stage the Phase 6C-4 on-device rollback-state test (throwaway keys, generated fresh, private halves discarded).

  python tests/make_hw_state_fixtures.py --binary build/rh_verify_arm --out build/hw-6c4

The Nano runs it from RAM: the binary, fixtures AND the state directory (/tmp/rhv-state) are all on tmpfs. Nothing
touches /mnt, installed.tsv, the Apps drawer or any OPK. See docs/HARDWARE_TEST_6C4.md."""
import argparse, base64, copy, hashlib, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import trust as T
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FX = HERE / "trust_fixture"

RUN_SH = r"""#!/bin/sh
# On-device rollback-state test. Writes ONLY under /tmp (tmpfs). Run from RAM: sh run.sh
cd "$(dirname "$0")" || exit 1
ST=/tmp/rhv-state
PUB=@PUB@
pass=0; fail=0
V() { ./rh_verify --index fixtures/$1.idx --sig fixtures/$1.sig --pubkey $PUB --device ${2:-rg-nano} --firmware ${3:-funkeyos-drum78} --state-dir $ST $4 2>&1; }
chk() { # name expected-prefix actual
  case "$3" in "$2"*) pass=$((pass+1)); echo "PASS $1";; *) fail=$((fail+1)); echo "FAIL $1: expected '$2' got '$3'";; esac
}
same() { [ "$(cat $ST/catalog.state 2>/dev/null)" = "$1" ]; }
ok() { if [ "$2" ]; then pass=$((pass+1)); echo "PASS $1"; else fail=$((fail+1)); echo "FAIL $1"; fi; }
echo "== environment"; uname -a; grep -E 'MemFree' /proc/meminfo; grep ' /tmp ' /proc/mounts; sha256sum rh_verify
rm -rf $ST
echo "== first run, repeats, advance"
chk first_run_s3 "OK serial=3" "$(V s3)"
S3=$(cat $ST/catalog.state); ok state_file_written "$(echo "$S3" | grep -q '^RHCS1 3 ' && echo y)"
ok only_state_file "$([ "$(ls -A $ST)" = catalog.state ] && echo y)"
chk repeat_s3 "OK serial=3" "$(V s3)"; ok repeat_state_unchanged "$(same "$S3" && echo y)"
chk advance_s5 "OK serial=5" "$(V s5)"; S5=$(cat $ST/catalog.state); ok state_is_5 "$(echo "$S5" | grep -q '^RHCS1 5 ' && echo y)"
echo "== rollback, fork, failed catalogs never move the state"
chk rollback_s4 "FAIL 10" "$(V s4)"; chk rollback_s3 "FAIL 10" "$(V s3)"; chk fork_s5 "FAIL 11" "$(V s5fork)"
chk bad_signature "FAIL 6" "$(V s6bad)"; chk policy_unapproved "FAIL 8" "$(V s8noappr)"
chk device_mismatch "FAIL 9" "$(V s6 some-other-handheld)"; chk firmware_mismatch "FAIL 9" "$(V s6 rg-nano funkeyos-future)"
chk unknown_key "FAIL 5" "$(V s9otherkey)"; chk malformed "FAIL 7" "$(V junk)"
ok state_unmoved "$(same "$S5" && echo y)"
ok no_stray_files "$([ "$(ls -A $ST)" = catalog.state ] && echo y)"
chk advance_s6 "OK serial=6" "$(V s6)"; S6=$(cat $ST/catalog.state); ok state_is_6 "$(echo "$S6" | grep -q '^RHCS1 6 ' && echo y)"
echo "== corrupt or odd existing state is refused, never reset"
for name in edit trunc empty garbage; do
  case $name in
    edit) sed 's/^RHCS1 6/RHCS1 7/' $ST/catalog.state > $ST/x; cat $ST/x > $ST/catalog.state; rm $ST/x;;
    trunc) head -c 30 $ST/catalog.state > $ST/x; cat $ST/x > $ST/catalog.state; rm $ST/x;;
    empty) : > $ST/catalog.state;;
    garbage) echo garbage > $ST/catalog.state;;
  esac
  chk corrupt_${name}_valid_new "FAIL 14" "$(V s7)"; chk corrupt_${name}_old_catalog "FAIL 14" "$(V s3)"
  printf '%s\n' "$S6" > $ST/catalog.state
done
rm $ST/catalog.state; mkdir $ST/catalog.state; chk state_is_directory "FAIL 14" "$(V s7)"; rmdir $ST/catalog.state
printf '%s\n' "$S6" > $ST/catalog.state
echo "== interrupted writes (power loss at each step while advancing 3 -> 6)"
for step in tmp_open tmp_written bak_made renamed synced; do
  rm -rf $ST; V s3 >/dev/null
  chk crash_$step "FAIL 14" "$(V s6 rg-nano funkeyos-drum78 "--inject $step:crash")"
  cur=$(cat $ST/catalog.state 2>/dev/null)
  case $step in
    renamed|synced) r=$(V s3); chk crash_${step}_new_record_kept "FAIL 10" "$r";;
    *) r=$(V s3); chk crash_${step}_old_record_kept "OK serial=3" "$r";;
  esac
  chk crash_${step}_retry "OK serial=6" "$(V s6)"
  ok crash_${step}_clean "$(same "$S6" && [ "$(ls -A $ST)" = catalog.state ] && echo y)"
done
echo "== failed writes: catalog not trusted, old state kept"
for step in tmp_open tmp_written bak_made; do
  rm -rf $ST; V s3 >/dev/null
  chk err_$step "FAIL 14" "$(V s5 rg-nano funkeyos-drum78 "--inject $step:err")"
  ok err_${step}_state_kept "$(same "$S3" && [ "$(ls -A $ST)" = catalog.state ] && echo y)"
  chk err_${step}_retry "OK serial=5" "$(V s5)"
done
rm -rf $ST; V s3 >/dev/null; mkdir $ST/catalog.state.bak; touch $ST/catalog.state.bak/x
chk real_failed_rename "FAIL 14" "$(V s5)"; ok real_failed_rename_kept "$(same "$S3" && echo y)"
rm -rf $ST/catalog.state.bak; mkdir $ST/catalog.state.tmp
chk real_failed_open "FAIL 14" "$(V s5)"; ok real_failed_open_kept "$(same "$S3" && echo y)"
rmdir $ST/catalog.state.tmp; chk retry_after_real_failures "OK serial=5" "$(V s5)"
echo "== independence from the install engine files"
rm -rf $ST; mkdir -p $ST; echo keep > $ST/installed.tsv; echo j > $ST/journal
V s3 >/dev/null; V s5 >/dev/null
ok engine_files_untouched "$([ "$(cat $ST/installed.tsv $ST/journal | tr '\n' ' ')" = 'keep j ' ] && echo y)"
echo "== documented limitation: deleting the state resets rollback protection"
rm -rf $ST; chk limit_s5 "OK serial=5" "$(V s5)"; chk limit_s3_refused "FAIL 10" "$(V s3)"
rm -f $ST/catalog.state; chk limit_s3_accepted_after_delete "OK serial=3" "$(V s3)"
echo "== timing (verify + state check/save on tmpfs, 20 runs of the same catalog after a first save)"
rm -rf $ST; V s3 >/dev/null
./rh_verify --index fixtures/s5.idx --sig fixtures/s5.sig --pubkey $PUB --device rg-nano --firmware funkeyos-drum78 --state-dir $ST --repeat 20 --stats
echo "== after"; grep MemFree /proc/meminfo
echo "cases: pass=$pass fail=$fail"
[ "$fail" = 0 ]
"""


def signed(payload, key):
    return T.canonical({"v": 1, "alg": "ed25519", "key_id": T.key_id(T.raw_pub(key)), "sig": base64.b64encode(key.sign(payload)).decode()})


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
    PA = T.raw_pub(A).hex()

    def put(name, idx, sig):
        (out / "fixtures" / f"{name}.idx").write_bytes(idx)
        (out / "fixtures" / f"{name}.sig").write_bytes(sig)

    def cat(serial, mutate=None, date="2026-10-26", key=A):
        d = T.build(FX / "catalog", serial, date)
        if mutate:
            mutate(d)
        raw = T.canonical(d)
        return raw, signed(raw, key)

    for n in (3, 4, 5, 6, 7):
        put(f"s{n}", *cat(n))
    put("s5fork", *cat(5, date="2026-11-01"))
    raw, sg = cat(6)
    put("s6bad", raw.replace(b"ExamplePad", b"ExamplePwn"), sg)
    put("s8noappr", *cat(8, lambda d: d["approvals"].clear()))
    put("s9otherkey", *cat(9, key=B))
    put("junk", b'{"a":[1,2,', signed(b'{"a":[1,2,', A))
    (out / "run.sh").write_bytes(RUN_SH.replace("@PUB@", PA).encode())
    shutil.copy(a.binary, out / "rh_verify")
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}" for p in sorted(out.rglob("*")) if p.is_file()]
    (out / "SHA256SUMS").write_bytes(("\n".join(sums) + "\n").encode())
    print(f"staged -> {out} ({len(sums)} files)")


if __name__ == "__main__":
    main()
