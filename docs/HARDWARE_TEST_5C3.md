# Phase 5C-3 hardware test: uninstall RH Probe v1.1.0 (DEV build only). NOTHING here has been run.

Artifacts (staged): `build/RetroHatchDev.opk` sha256 `f6cfff4dc69b7b748edadf2ed3fce3378fa771403daca1f268816ebfac148cb3` (131072 B).
Current Nano state to preserve until the uninstall: `rhprobe_funkey-s.opk` = `abad12c3cfb11db70928b9061cf9034ecc4c0ee60450f85ceb8631f3c9a7d205` (v1.1.0, mtime 1792980598),
`.retrohatch-dev/installed.tsv` = `dde95ddb40278160786b898dbaeb8ff138946d67d54c0172500ed4f1a18074e3`, `backup/rhprobe_funkey-s.opk.bak` = `2cb430f65e63d2105bd7a407f40a145352a0fece44d6b18937985eb53d9b2963` (v1.0.0),
cache: `2cb430f6...` + `abad12c3...`, DEV OPK on the Nano `98579363...`, production `RetroHatch.opk` `b75332e6...`, TaraFi 11567104 B. `/mnt/FunKey/.retrohatch` absent.

N="sh $HOME/.ssh/rgnano_ssh.sh"; D=/mnt/FunKey/.retrohatch-dev

## H0 stability preflight (read-only). STOP the whole test if any item fails.
1. `uptime`, `cat /proc/sys/kernel/random/boot_id`: record both. The Nano rebooted unexpectedly once after 5C-2; any later change of boot_id or an uptime that went backwards = another unexplained reboot -> stop and report.
2. `grep ' /mnt ' /proc/mounts` must still say `rw` (it is mounted `errors=remount-ro`; `ro` = storage fault -> stop).
3. `dmesg`: scan for `mmc|vfat|FAT-fs|EXT4|I/O error|blk_update_request|remount|reset|watchdog|Under-voltage|thermal`. Only the known boot-time `loop0` (Bluetooth image) line at ~15 s is accepted; anything new -> stop.
4. Battery: `cat /tmp/current_battery_percentage` (stop if under ~25 % or not charging while low), `df -h /mnt /tmp` (plenty free).
5. Read-only evidence for the earlier reboot, if present: `dmesg | head -40`, any power log under `/mnt/FunKey` (list only), `ls /tmp` for crash files.
6. No squashfs mounts, no `opkrun`/`retrohatch` process, no `$D/journal`, no `*.new`.
7. Baseline: `sha256sum` every file listed above; `find $D | sort`; `ls -l /mnt/Applications`.

## H1 evidence copies to the PC (read-only `cat`, no Nano writes)
`$N "cat $D/backup/rhprobe_funkey-s.opk.bak" > build/backup/rhprobe-v1.0.0.bak.copy` and verify `2cb430f6...`; also keep the current v1.1.0 OPK and `installed.tsv`.
The same v1.0.0 bytes already exist in `build/probe/rhprobe_1.0.0.opk` and the Nano cache. Note: the engine overwrites the single per-app `.bak` with a copy of v1.1.0 at the START of any
uninstall attempt and deletes it on success, so the v1.0.0 backup does not survive the test (it is never restored).

## H2 deploy (needs your approval; RetroHatch DEV must be closed)
Save the current DEV OPK `98579363...` to `build/backup/`, then hash-checked `.opk.new` -> rename of `build/RetroHatchDev.opk`. Re-run H0 items 1-3 afterwards.

## H3 user-controlled uninstall (RetroHatch DEV)
1. Settings > About: "DEV (install/update/uninstall)". Discover > RH Probe (test): version 1.1.0; the amber bar reads **Uninstall** (trash icon).
2. A: Uninstall screen. Orange "This removes the app", "Version 1.1.0", file name, "Saves and settings are kept", **Cancel** focused. Press B (no change), re-open, A on Cancel (no change).
3. A, Down, A on Uninstall -> "Removing..." (no input) -> "Uninstalled". A returns to details: bar now **Install** (local file available). Installed: "No installed applications".
4. Quit with MENU. Re-enter the Apps drawer.

## H4 agent verification
`rhprobe_funkey-s.opk` absent; `installed.tsv` has no rhprobe line (empty file is fine); `$D/backup` empty; no `$D/journal`, no `*.new`, no `*.tmp`; both cache files intact;
drawer fingerprint/manifest no longer list RH Probe; `RetroHatch.opk` `b75332e6...`, TaraFi + other OPKs unchanged; `/mnt/FunKey/.retrohatch` absent; boot_id/uptime consistent; dmesg and `/mnt` still clean.

## Not done on hardware (host-only)
Mounted / modified / unmanaged refusals and interrupted uninstall (all covered by 441 host checks): reproducing them on the Nano needs hand-altering a managed OPK, which is excluded.

## Cleanup (separate approval)
Remove only test-created, non-managed leftovers: `RetroHatchDev.opk`, `$D` (cache, empty state). RH Probe is already gone through the engine.
