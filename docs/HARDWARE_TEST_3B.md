# Phase 3B hardware test plan (RG Nano) — PROPOSED, NOT YET RUN

Needs explicit approval. Uses only `rhprobe*` files. Device helper: `sh ~/.ssh/rgnano_ssh.sh '<cmd>'` (password helper, Nano 192.168.1.197).
Host files (WSL-built, in `RetroHual/build/` and the session scratchpad `rhprobe/`):

| file | sha256 | size |
|---|---|---|
| rh_nano_test_cli (ARMv7 static, stripped) | `36551bc1d74d33cea78825c125c762d890639f1e53b3ca3f43126349b94b0f4c` | 74872 |
| rhprobe_v1.opk | `f0c66699b5922abc25fa8a849f4dff5cbe9dfe5a45ef7591d27bf55af194d2fe` | 4096 |
| rhprobe_v2.opk | `b5eded057af9fddb9276a05af2dca894acc490b07ff6b4f8e13c63e3ce36a297` | 4096 |

Variables: `A=/mnt/Applications/rhprobe_funkey-s.opk`, `CLI=/tmp/rh_nano_test_cli`, `V1=f0c6…d2fe`, `V2=b5ed…a297` (full hashes above).
State dir used by the CLI: `/mnt/FunKey/.retrohatch-test` (not the production dir).

## Steps (expected effect)

0. Stage tools in tmpfs only: pipe the CLI, V1, V2 to `/tmp/` (`cat f | ssh 'cat > /tmp/x'`), `chmod +x`, verify `sha256sum` equals the table. Nothing written to FAT.
1. Preflight read-only: `ls -l /mnt/Applications`, `grep squashfs /proc/mounts` (none), no tarafi/opkrun process.
2. **Install V1:** `$CLI install rhprobe 1 rhprobe_funkey-s.opk /tmp/rhprobe_v1.opk 4096 <V1>` → `result=0`; `$A` hash = V1, even mtime; `installed.tsv` has the line; no `journal`, no `*.new`.
3. **You:** open Apps drawer → expect "RH Probe V1".
4. **Update:** same with v2 → `result=0`; `$A` = V2; mtime >= old+4; backup in `.retrohatch-test/backup/` = V1.
5. **You:** re-enter drawer, no reboot → expect "RH Probe V2".
6. **Unmanaged:** `cp /tmp/rhprobe_v1.opk /mnt/Applications/rhprobe_unmanaged_funkey-s.opk` (test file), install V2 to that dest → `result=9 (target not installed by RetroHatch)`; file hash still V1.
7. **Busy:** `mkdir /tmp/rhprobe_mnt; mount -t squashfs -o loop,ro $A /tmp/rhprobe_mnt` (same read-only loop mount the scanner does; I will not open the drawer meanwhile). Check `/sys/block/loopN/loop/backing_file` shows `$A`. Install V1 over it → `result=7 (package is mounted/running)`, `$A` unchanged. Then `umount /tmp/rhprobe_mnt; rmdir /tmp/rhprobe_mnt`. Also re-run install after umount → ok (shows the block was the mount).
8. **Rollback, injected faults (no power cut):**
   a. `--fail-at synced` install of the other version → `result=13 (injected)`; `$A` hash AND mtime back to pre-test values; no journal.
   b. `--crash-at journaled` then `recover` → old version kept, journal gone.
   c. `--crash-at renamed` then `recover` → new version completed, record updated, journal gone.
9. **Final checks:** `ls -l /mnt/Applications` (only the 4 originals + rhprobe files), no `*.new`, no `journal`, `grep -c squashfs /proc/mounts` = 0, `/tmp/.sysapps_scan_mnt` absent.
10. **Cleanup (test-created only):** `rm $A /mnt/Applications/rhprobe_unmanaged_funkey-s.opk`, `rm -r /mnt/FunKey/.retrohatch-test`, `rm /tmp/rh_nano_test_cli /tmp/rhprobe_v*.opk`, `sync`. **You:** re-enter drawer → no RH Probe entries.

## Side effects
Small FAT writes in `/mnt/Applications` and `/mnt/FunKey/.retrohatch-test`; one transient read-only loop mount; tmpfs files. No reboot, no frontend restart, no root fs writes, TaraFi/other apps untouched (CLI refuses any dest not named `rhprobe*.opk`).

## Stop conditions
Any unexpected mount, `result` other than expected, hash mismatch, FAT error in `dmesg`, or an `.opk` I did not create appearing/changing in `/mnt/Applications`.

## Open until run
`utimensat` on vfat via musl; rename-over-existing on vfat; `backing_file` sysfs for a *squashfs* loop (confirmed only for loop0/ext4: `/sys/block/loop0/loop/backing_file` exists; unbound loop1 has none).
