# Deployment safety rule (RG Nano)

Incident 2026-10-26 (resolved): an OPK was replaced while RetroHatch DEV was running from it (opkrun loop-mounts the OPK as squashfs). The app froze, the buttons stopped responding, and the button daemon had to be restarted. No data was lost; both OPKs were restored and verified.

**Rule: never replace, rename or delete an OPK whose process or squashfs mount is active. Check before EVERY deployment and EVERY rollback. If the target is busy, abort and ask the user to close the app. Never bypass the check.**

Preflight, read-only, run immediately before the swap:
```
grep -E 'loop[0-9]+ /opk|/opk ' /proc/mounts                      # any squashfs mount of /opk
for l in /sys/block/loop*/loop/backing_file; do cat $l; done      # which file backs each loop device
for p in /proc/[0-9]*; do cat $p/comm; done | grep -E 'retrohatch|opkrun|native_launch'
```
Abort if the OPK being replaced is a loop backing file, or any `retrohatch`/`opkrun` process exists. The install engine (`rh_install.c`) already refuses such targets (`RH_E_BUSY`); manual deployments must meet the same bar.

Also, as before: hash-check a `.opk.new` before the rename; back up the current file to the PC first; check battery (>= 25 %), `/mnt` rw, no new `dmesg` storage errors; verify hashes after.

Do not restart `fkgpiod` or kill processes except to diagnose a real problem the user reported.

The original orange Home header stays (the blue-forest experiment was rejected).
