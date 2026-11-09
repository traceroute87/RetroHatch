# Hardware test 9: Kishmish Nano through the RetroHatch DEV installer (RG Nano), 2026-11-06

**Result: PARTIAL PASS. Download, install, launch, exit, uninstall and installed-state handling are HARDWARE-TESTED for the exact file `kishmish-nano.opk` sha256 `3dfa9fa77242d46743611c5f281fca0e3df40a481b86e857dac13c932abae2f9` on RG Nano / FunKey OS (DrUm78). The cancel-download test is NOT TESTED. The reboot cause is UNKNOWN. This is NOT a production approval: `catalog/apps/kishmish-nano.json` and `catalog/approvals.json` are unchanged.**

This tests the RetroHatch DEV installer and one application, not the production build, not the production catalog and not the real Pages catalog (which does not exist yet).

## What was tested
| Item | Value |
|---|---|
| Build | `RetroHatchDev.opk`, 499,712 B, sha256 `cebab59f1e47bcfb746fb0448219c44bff616055bd8035f168ac96d7c529940c` (two builds, same hash). Source: tree at `8e68b62` plus the DEV allowlist row for `kishmish-nano` in `ui/rh_ops.c` and the serial-3 fixture in `tools/make_dev_catalog.py` (both uncommitted) |
| Catalog | `catalog-3.pkg` (sha256 `28ff49da...`), serial 3, DEV-signed fixture with the real Kishmish entry and real GitHub URL; copied to `/mnt/FunKey/.retrohatch-dev/catalog.pkg` |
| Device | RG Nano, FunKey OS, 192.168.1.197, battery 88 % at start (74 % at deploy, 83 % at the end), `/mnt` 117.5 GB free |
| Deployment | `RetroHatchDev.opk.new` hash-checked, busy preflight (no `retrohatch` process, no loop device backed by RetroHatch OPKs, not mounted), then rename. Previous file `5b5eea19...` backed up in `build/backup/2026-11-06/`, with `RetroHatch.opk` and both state directories (`retrohatch-state.tar`) |
| Download | real `github.com` URL through the real 302 to `release-assets.githubusercontent.com`, shipped CA bundle, no mirror, no extra CA |

## Acceptance steps
| # | Step | Result | Evidence |
|---|---|---|---|
| 1 | Catalog Status: Verified, serial 3, 2 apps | PASS | owner on screen; `catalog.state` `RHCS1 3 e0c0df55...` |
| 2 | Kishmish details page (MIT, 0.1.0, 692,224 B) | PASS (owner-reported) | owner: "everything else seems fine" |
| 3 | Cancel a download with B | **NOT TESTED** | the owner could not press B in time (692 KB downloads in about a second) |
| 4 | Download from real GitHub, size and SHA-256 verified | PASS | cache file `3dfa9fa7...opk`, 692,224 B, hash re-computed on the device equals the catalog |
| 5 | Install | PASS | `/mnt/Applications/kishmish-nano_funkey-s.opk` hash `3dfa9fa7...`; `installed.tsv` line `kishmish-nano 0.1.0 3dfa9fa7... /mnt/Applications/kishmish-nano_funkey-s.opk`; no journal, `.new`, `.part`, `.dl`, `.tmp` |
| 6 | Launch and play | PASS (owner-confirmed) | `boot.log`: `Video: 240x240 16 bpp`, `Meow audio ready`; the game was playable |
| 7 | Save created and kept | PASS | `/mnt/FunKey/.kishmish-nano/pet.sav` written during play; after the reboot and a relaunch the save was read and updated (`KISHMISH1 98 99 99 0 0 3 ...`) |
| 8 | Normal exit | PASS | owner-confirmed; the 23:57 relaunch `boot.log` ends `Exit status: 0` |
| 9 | Installed-state detected | PASS (owner-reported) | owner confirmed the install and uninstall through the app; the app's own state matches `installed.tsv` before and after |
| 10 | Uninstall | PASS | OPK gone, `installed.tsv` back to the single `rhprobe` line (118 B, same as the baseline), `backup/` empty, no journal |
| 11 | Post-checks | PASS | below |
| - | Recovery on a failed operation | **NOT TESTED on hardware** (see step 3). Crash-point recovery stays covered by the offline fault-injection suites; no power failure was simulated |

## Read-only SSH verification after the test (23:58 UTC)
| Check | Result |
|---|---|
| Kishmish OPK removed from `/mnt/Applications` | PASS |
| `installed.tsv` has no Kishmish line | PASS |
| Leftover journal / `.new` / `.part` / `.dl` / `.tmp` / `.bak` in `/mnt/Applications`, `.retrohatch-dev`, `.retrohatch` | none |
| Processes and mounts | no `retrohatch`, `opkrun`, `native_launch` or kishmish process; only `loop0` (bluetooth `storage.img`); no `/opk` mount |
| Production `RetroHatch.opk` | unchanged, `2b0f064d...` |
| Other apps | `rhprobe` (`abad12c3...`), commander, gmu, st-sdl, unarchiver: names, sizes, dates unchanged; `README` unchanged |
| `.retrohatch` (production state) | untouched, empty `cache/` and `backup/` |
| TaraFi (`.tarafi`) | not touched by this test (latest changes 21:29, before the deployment) |
| Kishmish save data | preserved in `/mnt/FunKey/.kishmish-nano/` (`pet.sav`, `boot.log`) |
| Kishmish cache file | still in `.retrohatch-dev/cache/` (by design the cache is kept) |
| dmesg | nothing new except two `usb 1-1.2: current rate 48000 is different from the runtime rate 8000` lines (audio during play). The boot lines (`FAT-fs ... not properly unmounted`, `loop0 I/O error`, Wi-Fi beacon) match earlier tests |
| Filesystem | `/mnt` vfat rw; the dirty-FAT flag was already set before this test |

## Unexpected event: reboot, cause UNKNOWN
Between the 22:09 save and 23:51 the boot ID changed (`4d6cc141...` to `e0bd3398...`; uptime 5 min at 23:51). Possibly a depleted battery or a manual power-off, but the owner did not confirm either; the battery read 87 % at 22:08 and 83 % afterwards, which does not by itself rule it out (readings were taken before and after, not at the moment of the reboot). dmesg shows the dirty-FAT line from the following boot. All files and hashes were intact after it, including `installed.tsv`, the cache and the save. Not attributed to RetroHatch or Kishmish; not investigated further.

## Notes
- `ALSA lib ... Unknown PCM /dev/dsp1` appears in Kishmish's own log; sound was reported working.
- Kishmish writes `boot.log` on every launch (about 0.5 KB) and `pet.sav` under `/mnt/FunKey/.kishmish-nano/`.
- The DEV OPK on the Nano is still `cebab59f...` and `.retrohatch-dev` still holds `catalog.pkg` and `catalog.state` at serial 3. Restoring the original DEV OPK and state is pending the owner's go.
