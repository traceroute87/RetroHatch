# Hardware test 8: read-only candidate browser (RG Nano), 2026-11-05

**Result: the read-only browser is HARDWARE-TESTED (2026-11-05). All 127 software candidates remain NOT TESTED and UNAPPROVED.** This tests the RetroHatch program, not any application it lists.

## What was tested
| Item | Value |
|---|---|
| Build | `RetroHatch.opk`, 520,192 bytes, sha256 `6b5e997f1b8c73f22ef38f327aee8bcb4ea84a85de84f96551efc9fd31e13e59` |
| Source | commit `4929e4b`, built from a `git archive` export of HEAD with `platforms/nano/ui/build-opk.sh` (two builds, same hash) |
| Configuration | production flags, `RH_N_TRUSTED_KEYS` 0 (no catalog key, so nothing signed can be verified), no bundled `catalog.pkg`. The uncommitted production key work was NOT in this build |
| Device | RG Nano, FunKey OS, kernel 4.14.14-funkey, PC at 192.168.1.48 over the existing SSH wrapper |
| Deployment | `/mnt/Applications/RetroHatch.opk` only. Previous file `b75332e6…` backed up to `build/backup/RetroHatch.opk.pre-nav-2026-11-05` (also `RetroHatch-b75332e6.opk`). Hash-checked `.new`, then rename, preflight: target not mounted, not a loop backing file, no `retrohatch` process (the only `opkrun` was the firmware's own connectivity app; the owner approved a target-only check) |

## Confirmed by the owner on the device
Home and Discover render; all 127 candidates browse; D-pad works; the physical X (`x`) and Y (`y`) buttons page up and down; category switching and the position counter work; B restores the previous selection; A opens a candidate's details; A again does nothing; B returns; no install or download was triggered.

## Read-only SSH verification
| Check | Result |
|---|---|
| While running: `retrohatch` pid 23535, 2.6 MB RSS, 1 thread, no network sockets | PASS |
| After the owner exited: no `retrohatch`, `opkrun` or `native_launch` process; no `/opk` mount; no loop device backed by `RetroHatch.opk` | PASS |
| dmesg: no lines after 21 s of uptime (device up 50 min); the only error-like lines (`FAT-fs ... not properly unmounted`, `loop1 I/O error`) are from boot, before the deployment | PASS |
| `/mnt/FunKey/.retrohatch/` holds only empty `cache/` and `backup/` directories, 0 files: no download, no `catalog.pkg`, no `installed.tsv` | PASS |
| `/mnt/Applications`: names, sizes and dates equal the baseline except the intended `RetroHatch.opk`; `RetroHatchDev.opk` still `5b5eea19…`; no `.new` left | PASS |
| `.retrohatch-dev` and `.tarafi` untouched | PASS |

## Limits and remaining concerns
- The app has no log of its own, and `/var/log` is a link to `/tmp`, so "no crash" rests on the process, mount and dmesg evidence.
- Files that changed with no content baseline, all launcher or system bookkeeping: `/mnt/last_opk`, `/mnt/FunKey/.last_mapping.key`, `connectivity/connectivity.log`, `connectivity/bluetooth/storage.img`.
- `/mnt/FunKey/.retrohatch/` did not exist before this launch; the app created it (state directories, empty).
- Not tested: Installed, Updates, Settings, approved-app details, Catalog Status (a refresh was deliberately not pressed). Installing, downloading and removing were out of scope.
- The future production build that embeds the production catalog key needs its own hardware test.
