# Phase 6C-4 hardware test: persistent rollback state on the RG Nano. NOTHING here has been run on the Nano.

Goal: show on the device that the new state module (`core/rh_catalog_state.c`) advances `{serial, sha256}` only after a catalog verified completely, refuses rollbacks, forks and corrupt state, and survives interrupted and failed writes. Host results: `make -C tests state-test` (in-process, ASan/UBSan) and `python tests/test_trust_state.py` (through the real CLI).

## Staged (host, `build/hw-6c4/`, 145,141 B, 22 files)

| Item | Value |
|---|---|
| `rh_verify` ARM (static, reproducible: two builds, same hash) | 125,144 B (95,340 B stripped), sha256 `77a4d22575f40974a874240e7083b361b266535ddb9f1c2a30a81acd7251b89e` |
| `run.sh` | sha256 `88bc55e1a3baf7008b4267a9c9e94028533452693f89624724ac8e11828547e4` |
| `SHA256SUMS` (every other file) | sha256 `9ebc7530f88c42f1fe5d3a22d17c16ce5d379613ee36b707d506a5fd5ee85593` |

Same crypto as 6C-3 (`rh_catalog.c` and Monocypher unchanged); new code is `rh_catalog_state.c` and the CLI's `--state-dir` / `--inject` test options. Keys are throwaway, generated in memory, private halves discarded. Do not regenerate after approval.

## RAM only

Binary, fixtures **and the state directory** (`/tmp/rhv-state`) are on tmpfs. Nothing is written to `/mnt` (FAT, still flagged dirty), nothing near `installed.tsv`, the journal, backups, the Apps drawer or any OPK. The production state path `/mnt/FunKey/.retrohatch` is never used. A reboot erases everything. On tmpfs rename is atomic, so this test proves the logic, not FAT power-loss behaviour (see limitations).

## Procedure (needs your approval; Nano must be reachable)

Preflight (read-only): current IP, battery >= 30 %, `/mnt` still `rw`, boot_id and uptime, `dmesg` only the known lines, `/tmp` not `noexec`, `MemFree`, no `retrohatch`/`opkrun`.
1. `cd build && tar cf - hw-6c4 | ssh … "mkdir -p /tmp/rhv && tar xf - -C /tmp/rhv --strip-components=1"`
2. `cd /tmp/rhv && sha256sum -c SHA256SUMS` (all OK), `sha256sum rh_verify` = `77a4d225…`.
3. `chmod +x rh_verify && sh run.sh` -> expect `cases: pass=67 fail=0` and exit 0.
4. Re-check boot_id, uptime, `dmesg`, `/mnt` still `rw`, `/mnt/Applications` hashes unchanged.
5. Cleanup (tmpfs only): `rm -rf /tmp/rhv /tmp/rhv-state`.
Abort on any FAIL, signal, new storage error, `/mnt` read-only, reboot or low battery.

## What the 67 checks cover

First run creates exactly one file with a valid record; the same catalog again leaves it byte-identical; advance 3 -> 5 -> 6; rollback (4, 3) and same-serial fork refused with the state unchanged; bad signature, unapproved, wrong device/firmware, unknown key and malformed catalogs never move the state and leave no stray files; edited / truncated / empty / garbage / directory-in-place state is refused (even for a valid newer catalog and for an old one); power loss injected at each of `tmp_open`, `tmp_written`, `bak_made`, `renamed`, `synced` leaves the old or the new record (never none, never corrupt) and a retry completes; injected I/O errors at three steps and real failing `open`/`rename` (directories squatting on `.tmp`/`.bak`) refuse trust, keep the old record and recover on retry; engine files in the same directory are untouched; the documented reset-by-deletion limitation is demonstrated; timing of verify + state check.

## Expected numbers

Previous Nano figures (3.95 ms small catalog, 58 ms for a 100-app catalog, < 1 MiB RSS) plus a few ms for the state file read, which on tmpfs is negligible; a *save* adds one small write, an fsync and two renames (on FAT/SD this will cost noticeably more; not measured here).

## Not covered by this hardware test

- Behaviour of FAT/SD under real power loss or a full card: FAT rename atomicity is not assumed, which is why the previous record is parked as `.bak` and a lone `.bak` is recovered; that logic is exercised on the host and in RAM, not on the SD card. A later, separately approved test would use a throwaway directory on `/mnt` with the same script.
- UI, installs, downloads, production state path, production keys.
