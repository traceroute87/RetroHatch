# Phase 6C-3 hardware test: native signed-catalog verifier on the RG Nano. NOTHING here has been run on the Nano.

Goal: show on the real device that `core/rh_catalog.c` (Monocypher 4.0.3 `crypto_ed25519_check`) accepts a legitimate signed catalog and rejects every tampered, malformed, mismatched or rolled-back one.

## What is staged (host, `build/hw-6c3/`, 804,638 B, 62 files)

| Item | Value |
|---|---|
| `rh_verify` (ARM, static, reproducible: two builds gave the same hash) | 118,924 B (91,244 B stripped), sha256 `d979350060cdb7220dd36ff6b8376645144aa9f1220b57e82a84ff7fd78b6e81` |
| ELF | ARM EABI5, v7-A, Thumb-2, VFPv4 hard-float, built with the same Buildroot toolchain as `rh_nano_test_cli` |
| `run.sh` | sha256 `615b9d2c32b5cb1a6280d7052f58334d1c4ae63caee54a3bdbe7b70d597dd803` |
| `expected.tsv` (27 cases) | sha256 `9ce210c4d68967867e6d61294754a8e912e3a5be948851fd00bd2754901469ce` |
| `SHA256SUMS` (every file) | sha256 `9872cef34e704c31aad5319680e6d0076a850edcd3a425a0a180f4a50c0c51c5` |

- Keys are throwaway: generated in memory by `tests/make_hw_fixtures.py`, public halves printed into the test files, private halves never written anywhere. The staged set must not be regenerated after approval (new random keys, new hashes).
- The set is `fixtures/*.idx|.sig|.state`: valid catalogs, tampered ones, and signed-but-invalid ones (see table below). Nothing in it can install or download anything.
- Production `RetroHatch.opk` (`b75332e6…`), the DEV OPK (`f6cfff4d…`), DEV state, TaraFi and firmware are not part of this test and are not touched.

## Design choice: RAM only, zero writes to the SD card

The binary and fixtures are copied to `/tmp/rhv` (tmpfs, 128 MB, ~0.8 MB used) and run over SSH. Nothing is written to `/mnt` (FAT, still flagged dirty), nothing is added to Apps, no OPK is installed, no launcher entry. A reboot removes everything. `run.sh` itself writes no files.

## Procedure (needs your approval; Nano must be reachable)

Preflight (read-only): battery >= 30 % (or charging); `grep ' /mnt ' /proc/mounts` still `rw`; boot_id/uptime recorded; `dmesg` shows only the known `loop0` line; `/tmp` is not mounted `noexec` (`grep ' /tmp ' /proc/mounts`); no `retrohatch`/`opkrun` DEV process; `MemFree` recorded.

1. Create the directory and copy (stdout of `tar` over SSH, no scp needed):
   `cd build && tar cf - hw-6c3 | ssh … "mkdir -p /tmp/rhv && tar xf - -C /tmp/rhv --strip-components=1"`
2. On the Nano: `cd /tmp/rhv && sha256sum -c SHA256SUMS` (all `OK`; the binary line must be `d9793500…`).
3. `chmod +x rh_verify && sh run.sh`. Expect `cases: pass=27 fail=0`, then timing/memory lines. Do not run it in parallel with anything else.
4. Record the full output, then re-check boot_id, uptime, `dmesg` (new lines), `/mnt` still `rw`.
5. Cleanup (this one is a write, to tmpfs only): `rm -rf /tmp/rhv`.
Abort conditions: any `FAIL`, any signal/`Illegal instruction`, new `dmesg` errors, `/mnt` turning read-only, boot_id change.

## Cases (27)

| Requirement | Cases (expected `rh_verify` output) |
|---|---|
| Valid accepted | `valid`, `valid_rotation_overlap` (two trusted keys), `valid_signed_by_new_key` → `OK serial=…` |
| Modified catalog | `modified_catalog` (bytes changed), `modified_catalog_extra_byte` → `FAIL 6` (bad signature) |
| Modified signature | `modified_signature` → `FAIL 6`; `truncated_signature_doc`, `signature_wrong_length` → `FAIL 4`; `missing_signature` → `FAIL 2` |
| Wrong / unknown key | `unknown_key` → `FAIL 5`; `wrong_key_claiming_ours` → `FAIL 6`; `no_trusted_key_configured` → `FAIL 3` |
| Malformed catalog (validly signed) | `malformed_catalog_signed`, `noncanonical_catalog_signed`, `duplicate_field_signed` → `FAIL 7` |
| Policy (validly signed) | `policy_unapproved_signed`, `policy_unverified_signed` → `FAIL 8` |
| Device mismatch | `device_mismatch`, `firmware_mismatch` → `FAIL 9` |
| Rollback | `rollback_newer_baseline` (stored serial 5 > 3) → `FAIL 10`; `same_serial_different_hash` → `FAIL 11`; `same_index_again_ok`, `older_baseline_ok` → `OK` |
| Limits | `oversize_index_signed` (300 KB) → `FAIL 2`; `too_many_tokens_signed`, `too_deeply_nested_signed` → `FAIL 12` |
| Large valid | `big_valid_catalog` (100 apps, 103,447 B) → `OK serial=9 apps=100` |

## Expected numbers (host estimates; the point of the test is to replace them with real ones)

- Host check of the staged set with the x86 build: 27/27 pass (dash). Host -O2 verification: about 2 ms for a small catalog including file IO (tests/test_trust_native.py).
- Memory: 160 KiB heap (8192 tokens × 20 B) + about 12 KiB stack + the 119 KB static image; the 100-app catalog uses the same token buffer. Expect `maxrss_kb` of roughly 600–900 on the Nano (static musl, no sanitizers); the host process measured 2.3–2.5 MiB with page granularity and WSL overhead.
- Time on the Nano: unknown. Cortex-A7 at the F1C-class clocks without NEON for this code path: guess 20–100 ms per Ed25519 verification, up to a few hundred ms for the 100 KB catalog (SHA-256 + parse). Anything below ~1 s is acceptable for a catalog refresh; if a verification takes longer, report it before any UI work.

## Report after the run

Pass/fail per case, actual avg/min/max ms for small and large catalogs, `maxrss_kb`, MemFree before/after, binary hash as seen on the Nano, any SIGILL/alignment/FPU problem, `dmesg` and `/mnt` status, boot_id.

## Not covered (by design)

No persistence of rollback state, no UI, no downloads or installs, no production key. A device-clock test is unnecessary: the verifier never reads a clock (`expires` is returned for display only).

## Next step after a pass: persistent rollback protection (smallest version)

Add `rh_trust_state_load/save` (in a new small file next to `rh_catalog.c`, reusing `rh_install.c`'s tmp-file + `fsync` + `rename` pattern) that stores one 72-byte record `serial sha256\n` in `/mnt/FunKey/.retrohatch/catalog.state`. Rules: load failure or missing file = first run (accept any validly signed index); corrupt file = treated as missing but reported; save only after `rh_catalog_verify` returned OK and only when the new serial is greater than or equal to the stored one; write `*.new`, sync, rename, so a power cut leaves either the old or the new record. Test it on the host with the existing temp-dir harness and a simulated crash between write and rename, then run it once on the Nano against a throw-away state dir under `/tmp` before ever pointing it at `/mnt/FunKey`.
