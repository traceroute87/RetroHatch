# Candidate review: kishmish-nano (first real app). Status: NOT verified, NOT published

Catalog entry: `catalog/apps/kishmish-nano.json` (status `unavailable`, level `untested`, so the signed index cannot contain it).

| Check | Finding |
|---|---|
| Source | https://github.com/Alialhashemi23/kishmish-nano, owner Alialhashemi23, created 2026-10-09, not a fork, not archived, 0 stars (brand new, single author) |
| Release | `v0.1.0`, a normal release (published 2026-10-09 12:14 UTC), tag commit `84653f90…`. `v0.2.0-rc.1` is a prerelease and says it still needs a Nano playtest: not used |
| Artifact | `kishmish-nano.opk`, **692,224 B, SHA-256 `3dfa9fa77242d46743611c5f281fca0e3df40a481b86e857dac13c932abae2f9`**. Downloaded here and re-hashed: equals GitHub's asset digest and the author's `SHA256SUMS.txt` |
| License | MIT (`LICENSE`, "Copyright (c) 2026 Alialhashemi23"), matches GitHub's detection. The OPK also carries unmodified FunKey SDK runtime: SDL 1.2.15 (LGPL-2.1+, dynamically linked and replaceable) and musl 1.2.1 (MIT), with notices in `licenses/`; corresponding sources are in the release asset `kishmish-runtime-sources.zip` (SHA-256 `a1d0299f…`). We only link to the author's release, we do not redistribute it |
| Package (static inspection, nothing run) | squashfs, 19 entries, no symlinks/special files/odd paths; `kishmish.funkey-s.desktop` (+ `.anbernic.desktop`), `launch.sh`, one ARM binary, bundled musl loader + SDL, 3 WAVs, licenses |
| Binary | ARM ELF32, ARMv7-A, hard-float VFPv4 + NEON: matches the Nano's CPU (`neon vfpv4`); uses its own musl loader and SDL, so it does not depend on the device libc. Strings show no network, `system`/`exec` or `/etc` access; it writes only `<HOME>/.kishmish-nano/` |
| Saves | `launch.sh` uses `$HOME/.kishmish-nano`. On our firmware apps started by the launcher get `HOME=/mnt/FunKey` (read from the running launcher): writable FAT, so saves go to `/mnt/FunKey/.kishmish-nano/`. Root is read-only, which is why this was worth checking |
| Compatibility evidence | The author reports basic boot and play on a **stock Anbernic RG Nano firmware**; our device runs FunKey OS (DrUm78 build, `funkeyos-drum78`). Different firmware: **no evidence for ours** |
| Dest name | `kishmish-nano_funkey-s.opk` (not on the engine denylist) |

## What needs the Nano (cannot be done from the PC)
Install this exact file (hash `3dfa9fa7…`) on the DEV Nano, then:
1. It appears in the Apps drawer with its icon and launches (the bundled loader works on this firmware).
2. Display is 240x240 and correct; D-pad, A, B, Start work; sound plays (or the game continues silently without error).
3. Start, Save and Quit returns to the launcher; the power button still shuts down normally; the app exits cleanly.
4. Save file is created under `/mnt/FunKey/.kishmish-nano/`, survives a relaunch.
5. RetroHatch uninstall leaves the save and the other apps alone; no new `dmesg` errors; no leftover processes or mounts.

Only after those pass: record the tester/date/hash as `evidence`, set `available` + `verified`, add the approval, build, sign, publish (`docs/PUBLISHING.md`). Open question for you: the author's own later release `v0.2.0-rc.1` will replace `v0.1.0` eventually; each new file needs its own hardware test.
