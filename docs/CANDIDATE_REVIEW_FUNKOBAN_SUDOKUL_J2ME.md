# Offline compatibility review: Funkoban, SuDokuL, j2me-funkey-rgnano (pm.opk)

Date: 2026-10-31. Status of all three: **UNAPPROVED, not hardware-tested.** This review changes no catalog, approval, key or candidate permission. It is a static review only: nothing from the packages was executed, no device was contacted, and nothing was installed.

## How this was done
- The three records come from `candidates/rg-nano.json` (built from the 2026-10-26 crawl). Source, release tag, license, description, topics and README excerpts are that cached discovery data. No GitHub API or README request was made (downloads were limited to the three packages), so release authorship, GitHub's asset digest and the READMEs were **not** re-checked.
- Exactly three downloads, each the existing release-asset URL from the record. Size equals the size the crawler recorded, first bytes are `hsqs` (squashfs).
- Each OPK was listed with `unsquashfs -ll` and extracted into its own new directory (not under the repo). Binaries were read with the FunKey toolchain's `arm-linux-readelf` and `strings`. Nothing was run, mounted or loaded.
- Device facts used: `docs/KISHMISH_REVIEW.md` (device CPU `neon vfpv4`; apps started by the launcher get `HOME=/mnt/FunKey`; OPKs are loop-mounted squashfs read-only), `platforms/nano/rh_install.[ch]`, `catalog/schema/app.schema.json`, `docs/PUBLISHING.md`. Library availability comes from two local DrUm78 FunKey-OS Buildroot trees and the stock defconfig (see "Library check"); the device's real library list is not recorded anywhere in the repo.

## Compatibility matrix

| | Funkoban | SuDokuL | j2me-funkey-rgnano (`pm.opk`) |
|---|---|---|---|
| Source / release | github.com/joyrider3774/sokoban_funkey, tag `v1.1` | github.com/Mode8fx/SuDokuL, tag `v1.5` | github.com/slrmoon/j2me-funkey-rgnano, tag `1.3.0` |
| License (documented) | MIT (GitHub-detected). Package has no project LICENSE; fonts carry Roboto (Apache) and Space Mono (OFL) notices; the four music files have no license text | MIT (GitHub-detected). No LICENSE in package; strings point to opengameart.org for art/sound | **Unknown** (GitHub detected none). Package files carry Sun phoneME GPL-2.0 headers and a GPLv2 notice for Java Mobile Audio |
| Package validity | Valid squashfs, gzip, 51 inodes, no symlinks/devices, no `..` paths. 8,531,968 B, SHA-256 `ef28ed14…b843` | Valid squashfs, 5 inodes, no symlinks/devices. 913,408 B, SHA-256 `dfd5837d…7ecd`. Stray `OpenPackageCreator.lnk` (Windows shortcut, harmless) | Valid squashfs, 194 inodes, no symlinks/devices. 3,645,440 B, SHA-256 `568e6b9b…a5aa`. Contains an **i386** static ELF (`bin/preverify`) that cannot run on the Nano |
| Desktop metadata | `Funkoban.funkey-s.desktop`: `Exec=funkoban`, `Icon=graphics/sokoban` (file exists), `Categories=games` | `sudokul.funkey-s.desktop`: `Exec=sudokul`, `Icon=sudokul-image` (file exists), `Type=Game`, `Categories=games;` | `pm.funkey-s.desktop`: `Exec=pm`, `Icon=pm` (file exists), `Categories=emulators` |
| CPU architecture | ELF32 ARM EABI5, ARMv7-A, hard-float, VFPv4 + NEON, Thumb-2; interpreter `/lib/ld-musl-armhf.so.1` | same | `pm`, `runMidlet`, `cldc_vm`: same ARM profile; `preverify` is x86 (not runnable) |
| Matches device CPU | Yes (device reports `neon vfpv4`) | Yes | Yes for the ARM binaries |
| Dependencies (not bundled) | `libSDL-1.2`, `libSDL_image-1.2`, `libSDL_ttf-2.0`, `libSDL_mixer-1.2`, `libmikmod.so.3`, `libSDL_gfx.so.13`, `libstdc++`, `libgcc_s`, musl | `libSDL-1.2`, `libSDL_image-1.2`, `libSDL_ttf-2.0`, `libSDL_mixer-1.2`, `libmikmod.so.3`, `libstdc++`, `libgcc_s`, musl | `pm`: `libSDL-1.2`, `libSDL_gfx.so.13`. `runMidlet`: `libz`, SDL, SDL_image, SDL_gfx, `libstdc++`, `libgcc_s`. `cldc_vm`: `libz`, `libstdc++`, `libgcc_s`. `pm` also shells out (`system`/`popen`) using `unzip`, `awk`, `sed`, `grep`, `tr` |
| Firmware requirements | Built by CI with FunKey SDK 2.3.0 (musl armhf). Needs the five SDL-family libraries above on the device. No firmware claim for DrUm78 FunKeyOS in the cached data | Same SDK build. Cached evidence only names the FunKey family (topic `funkey-s`), not RG Nano | Description names "FunKey S / RG Nano". README (cached excerpt) says to put `pm.opk` in the `emulators` folder, not an apps folder. Runtime-only: no MIDlet is bundled, the user must add `.jar` files |
| Runtime side effects | `$HOME/.sokoban_*` (settings, level packs) via `getenv("HOME")`; `mkdir`/`remove`/`rename`/`rmdir`; no network, no `system`/`exec` | `$HOME/.local/share/.sudokul` and `settings.bin`; one `mkdir` (nested parent dirs may be missing, so saves might not persist); no network, no `system`/`exec` | Writes `/mnt/FunKey/.pm/` (runtime copy ~6.5 MB of `lib` + `bin`, logs, favorites, keybinds, RMS). `runMidlet`/`cldc_vm` import `socket`/`connect`/`gethostbyname` (Java networking). Uninstalling the OPK leaves `/mnt/FunKey/.pm` behind |
| Installer compatibility | Passes the installer's name checks as `funkoban_funkey-s.opk` (also as `Funkoban.opk`): plan target `/mnt/Applications/funkoban_funkey-s.opk`. OPK is treated as opaque (size and SHA-256 only) | Passes as `sudokul_funkey-s.opk`: `/mnt/Applications/sudokul_funkey-s.opk` | Passes as `j2me_funkey-s.opk` (or `pm.opk`) but the file is meant for an `emulators` folder; whether the launcher lists it from `/mnt/Applications` with `Categories=emulators` is unknown |
| Missing information | Exact libraries on the device; README not read; music/asset licenses; hardware evidence; `install.dest_name` and `sha256` are not yet in any catalog entry | Exact libraries on the device; RG Nano claim is family-level only; README not read; save-dir creation behavior; hardware evidence | License; exact libraries on the device; README not read; which folder the launcher scans for `emulators`; MIDlet source for any real test; hardware evidence |
| **Verdict** | **Ready for future hardware testing** (after the library preflight below) | **Ready for future hardware testing** (after the library preflight; lower claim confidence) | **Blocked** (license unknown: the catalog schema allows no available artifact with an unknown license; also runtime-only, writes outside RetroHatch's state, x86 `preverify`) |

## Library check (what could and could not be established)
Re-checked 2026-11-02, read-only, against the two local DrUm78 FunKey-OS trees in WSL `~/nanofi-build/` (both `origin` = `github.com/DrUm78/FunKey-OS`, HEAD `6739391b2` / `384286a`, 2026-03-04) and the NEEDED entries of the extracted ARM binaries (`readelf -d`). Neither tree is the image on the Nano; they are build outputs.
- **Tree A `FunKey-OS`** (stock config): `output/target` is an **incomplete build**. It has no `/bin/busybox` at all, `output/build` holds only `sdl`, `sdl_image`, `sdl_ttf`, and `output/images` holds only `TaraFi.opk`. Its "missing" SDL_mixer/mikmod/SDL_gfx therefore says nothing about the firmware.
- **Tree B `FunKey-OS-rgnano-wifi`**: complete rootfs. Its only `funkey_defconfig` change is a Wi-Fi block (linux-firmware, iw, wpa_supplicant); it adds no libraries.
- **Stock `funkey_defconfig`** (tree A, unmodified in `FunKey/configs`) enables `BR2_PACKAGE_SDL`, `SDL_IMAGE`, `SDL_TTF`, `SDL_MIXER`, `SDL_GFX`, `LIBMIKMOD`. Stock `busybox.config` enables `UNZIP`, `AWK`, `SED`, `GREP`, `TR`.

| Library / tool | Needed by | Tree A (incomplete) | Tree B (complete) | Status |
|---|---|---|---|---|
| `libSDL-1.2.so.0` | all three | present | present | **Confirmed** |
| `libSDL_image-1.2.so.0` | all three | present | present | **Confirmed** |
| `libSDL_ttf-2.0.so.0` | Funkoban, SuDokuL | present | present | **Confirmed** |
| `libSDL_mixer-1.2.so.0` | Funkoban, SuDokuL | absent (build incomplete) | present | **Confirmed in a complete build + stock defconfig**; not seen on device |
| `libmikmod.so.3` | Funkoban, SuDokuL | absent (build incomplete) | present | same |
| `libSDL_gfx.so.13` | Funkoban, pm, runMidlet | absent (build incomplete) | present | same |
| `libstdc++.so.6`, `libgcc_s.so.1`, `libz.so.1` | all / runMidlet, cldc_vm | present | present | **Confirmed** |
| `ld-musl-armhf.so.1` | all | present | present | **Confirmed** |
| `unzip`, `awk`, `sed`, `grep`, `tr` (pm) | pm only | no busybox in tree | busybox applets (symlinks) | **Confirmed in stock busybox config** |

Missing libraries: **none** against a complete DrUm78 build. Correction to the earlier draft: SDL_mixer, mikmod and SDL_gfx are **not** extras that only the wifi variant adds; they come from the stock defconfig and tree A simply never finished building.

Unknowns (cannot be closed offline):
- The firmware actually flashed on the Nano (version, config, any trimmed rootfs). No device library list is stored in the repo.
- Exact SONAME/ABI of the on-device SDL_mixer/SDL_gfx (the OPKs were built with FunKey SDK 2.3.0; tree B is DrUm78 HEAD from 2026-03).
- pm's behavior in the launcher's `emulators` folder, and Java networking use by `runMidlet`/`cldc_vm`.

Net effect on verdicts: library risk for Funkoban and SuDokuL drops from "possible load failure" to "low, still verify". Verdicts are unchanged (Funkoban and SuDokuL ready for future hardware testing after the read-only preflight; pm.opk blocked on license).

## Comparison with RetroHatch's installer requirements
- **Destination and names:** `rh_plan_target` (the installer's own name checks) accepts all proposed dest names and puts them in `/mnt/Applications/`. None is on the deny list. The files are root-level `*.opk`, which the Apps drawer scan reads.
- **Opaque handling:** the installer verifies size and SHA-256 only. Everything above (architecture, libraries, save locations) is outside what it checks, which is why this manual review matters.
- **Space:** all three are far below the free-space margin on a normal card.
- **Uninstall:** `rh_uninstall` removes only the OPK. App data under `/mnt/FunKey` (`.sokoban_*`, `.local/share/.sudokul`, `.pm/`) remains. That is the same behavior as for the Kishmish candidate.
- **DEV flow:** `ui/rh_ops.c` allows only `rhprobe`. These apps are not in the allowlist, and no signed DEV catalog entry exists. A supervised test needs a deliberate, reviewed allowlist entry and a DEV catalog entry, or manual placement under the existing deploy-safety rules. Neither was done here.
- **Production catalog rules** (`app.schema.json`, `docs/PUBLISHING.md`): needs a known license, `install.dest_name`, exact `size` and `sha256`, a hardware test of that exact file with evidence, and a human approval record. None of that exists for any of the three. Funkoban and SuDokuL would need only the hardware test and records; pm.opk is stopped at the license.

## Preflight for a future supervised test (read-only on the device)
1. Confirm on the device: `libSDL_mixer-1.2.so.0`, `libmikmod.so.3`, `libSDL_gfx.so.13`, `libSDL_ttf-2.0.so.0`, and `/lib/ld-musl-armhf.so.1`.
2. Confirm `HOME` seen by launched apps is `/mnt/FunKey` and `/mnt/FunKey/.local/share` can be created (SuDokuL).
3. Then follow `docs/DEPLOY_SAFETY.md` and the Kishmish checklist (appears in drawer, launches, display and input, exits cleanly, saves persist, uninstall leaves other apps alone, no new `dmesg` errors).

## Hashes of the reviewed files
```
ef28ed1445742ee7793108d55b30dc97a480787f7c659e826be01d769d38b843  Funkoban.opk       (v1.1)
dfd5837d4d57f067f855e21ce04974b0a1580a105241541d6f0cba1f7fa67ecd  SuDokuL-v1.5-funkey.opk  (v1.5)
568e6b9b665b16efcb463c1d43dfbcbaf6ea624d27ccb23231c0bb4d840aa5ca  pm.opk             (1.3.0)
```
The downloaded files and extractions are in WSL `~/opkreview/` (outside the repository). Each new release file would need its own review and hardware test.
