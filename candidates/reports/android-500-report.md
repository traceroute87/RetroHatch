# Android candidate discovery (phase 2) · 2026-11-09

Leads, not approvals. **verified** = a real APK from the project's repository or official server, with package id, minSdk, ABIs and licence read; it is **not** device testing. Third-party catalogs (Recompa, Obtainium, Retro Handhelds, Retro Game Corps) were treated as leads and their files re-checked.

## Totals

**1238 unique candidates (unique package ids)** · verified APK **984** · needs verification **252** · external listing **2**

- **Distinct upstream projects: 1178** (community forks of one Recompa game, and the same repository under two package ids, count once). This is the conservative headline number.
- Core retro categories (Emulators, Games, Ports, Themes & Launchers): **781** packages / **732** projects. General handheld utilities and media players: **457** packages (a defensible but broader selection: file managers, backup/sync, app managers, music/video players, game streaming).
- Duplicates folded: **111** (by package id, then upstream repository + name)
- Dropped as not installable on RG Rotate (manifest): needs Android above API 31 **7**, no arm64 library **61**
- New versus the current RetroHatch inventory/catalog: **1229** new, **9** already known

## By category

| Category | Candidates | Verified | Needs verification | External |
|---|---|---|---|---|
| Games | 151 | 151 | 0 | 0 |
| Emulators | 39 | 32 | 6 | 1 |
| Ports | 472 | 232 | 240 | 0 |
| Utilities | 304 | 299 | 5 | 0 |
| Media | 153 | 153 | 0 | 0 |
| Themes & Launchers | 119 | 117 | 1 | 1 |

## By source (a candidate seen in several sources counts in each)

| Source | Records scanned | Relevant (before dedupe) | Candidates containing it | Only from this source |
|---|---|---|---|---|
| fdroid | 4988 | 754 | 689 | 636 |
| izzy | 1405 | 110 | 106 | 70 |
| recompa | 461 | 461 | 443 | 433 |
| obtainium | 480 | 40 | 24 | 4 |
| retrohandhelds-rotate | 23 | 23 | 23 | 13 |
| rgc-guide | 49 | 49 | 20 | 6 |
| mainstream-seed | 21 | 21 | 18 | 5 |

## RG Rotate compatibility confidence (never a device test)

| Level | Meaning | Count |
|---|---|---|
| curated-for-rotate | listed in Retro Handhelds' RG Rotate collection | 23 |
| manifest-installable | minSdk <= 31 and arm64 (or pure Java) per the APK's manifest | 1173 |
| unknown | manifest not read | 42 |

## Top 75 recommended for RG Rotate

Ranked by: named in the mainstream seed list or Retro Handhelds' Rotate collection, verified file, category value for a handheld, community reports (Recompa), recency, FOSS licence. Per-category caps keep it balanced.

| # | App | Category | Status | Min Android | Version | Licence | Why | Source |
|---|---|---|---|---|---|---|---|---|
| 1 | [Dolphin Emulator](https://dolphin-emu.org/) | Emulators | verified | API 21+ | 2603a | GPL-2.0-or-later | category Emulator and it plays games/console software | fdroid, obtainium, rgc-guide, mainstream-seed, retrohandhelds-rotate |
| 2 | [PPSSPP](https://www.ppsspp.org/) | Emulators | verified | API 9+ | 1.19.3 | GPL-2.0-or-later | category Emulator and it plays games/console software | fdroid, obtainium, rgc-guide, mainstream-seed, retrohandhelds-rotate |
| 3 | [melonDS](https://github.com/rafaelvcaetano/melonDS-android) | Emulators | verified | API 24+ | 2.0.1 | GPL-3.0 | category Emulator and it plays games/console software | obtainium, mainstream-seed, retrohandhelds-rotate, rgc-guide |
| 4 | [Duckstation](https://play.google.com/store/apps/details?id=com.github.stenzek.duckstation&amp;hl=en_US&amp;gl=US) | Emulators | verified | API 24+ | 12126 | CC-BY-NC-ND-4.0 | recommended in the Retro Game Corps Android emulation guide | rgc-guide, mainstream-seed, retrohandhelds-rotate |
| 5 | [ARMSX2](https://github.com/ARMSX2/ARMSX2) | Emulators | verified | API 30+ | 2.9.2 | unverified | mainstream emulator/frontend seed (requested by name) | mainstream-seed, retrohandhelds-rotate |
| 6 | [Vita3K](https://vita3k.org/) | Emulators | verified | API 28+ | continuous | GPL-2.0 | category Emulator and it plays games/console software | obtainium, mainstream-seed, rgc-guide |
| 7 | [Azahar](https://azahar-emu.org/) | Emulators | verified | API 29+ | 2126.2 | GPL-2.0 | mainstream emulator/frontend seed (requested by name) | mainstream-seed, rgc-guide |
| 8 | [Flycast](https://flycast.github.io/) | Emulators | verified | API 21+ | v2.7 | GPL-2.0 | mainstream emulator/frontend seed (requested by name) | mainstream-seed, rgc-guide |
| 9 | [RetroArch](http://www.libretro.com) | Emulators | verified | API 16+ | 1.22.2 | GPL-3.0-only | category Emulator and it plays games/console software | fdroid, obtainium, mainstream-seed |
| 10 | [NetherSX2 (patched AetherSX2)](https://github.com/Trixarian/NetherSX2-patch) | Emulators | verified | API 26+ | 2.2n | unverified | mainstream emulator/frontend seed (requested by name) | mainstream-seed, rgc-guide |
| 11 | [Winlator](https://github.com/brunodev85/winlator) | Emulators | verified | API 26+ | v11.2.0 | unverified | mainstream emulator/frontend seed (requested by name) | mainstream-seed, rgc-guide |
| 12 | [Daijishō](https://github.com/TapiocaFox/Daijishou) | Themes & Launchers | verified | API 26+ | v1.5.0 | MIT | mainstream emulator/frontend seed (requested by name) | mainstream-seed, rgc-guide |
| 13 | [Lemuroid](https://github.com/Swordfish90/Lemuroid) | Emulators | verified | API 23+ | 1.17.0 | GPL-3.0-or-later | category Emulator and it plays games/console software | fdroid, mainstream-seed |
| 14 | [Obtainium](https://github.com/ImranR98/Obtainium) | Utilities | verified | API 26+ | 1.7.4 | GPL-3.0-only | utility category App Store & Updater | fdroid, retrohandhelds-rotate, rgc-guide |
| 15 | [NetherSX2 Classic](https://github.com/Trixarian/NetherSX2-classic) | Emulators | verified | API 26+ | 2.2n | Unlicense | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate, rgc-guide |
| 16 | [MAME4droid](https://github.com/Seleuco/MAME4droid-2024) | Emulators | verified | API 29+ | v1.41.2 | unverified | mainstream emulator/frontend seed (requested by name) | mainstream-seed |
| 17 | [Syncthing-Fork](https://github.com/researchxxl/syncthing-android/wiki) | Utilities | verified | API 23+ | 2.1.7.0 | MPL-2.0 | utility category Cloud Storage & File Sync | fdroid, retrohandhelds-rotate |
| 18 | [Spotube](https://github.com/KRTirtho/spotube) | Media | verified | API 24+ | 5.1.2 | BSD-4-Clause | media player (Online Media Player) | fdroid, retrohandhelds-rotate |
| 19 | [Console Launcher](https://play.google.com/store/apps/details?id=com.k2.consolelauncher&amp;hl=en_US) | Emulators | needs verification | API 27+ | v2.0.0-beta.6.12 | - | recommended in the Retro Game Corps Android emulation guide | rgc-guide, retrohandhelds-rotate |
| 20 | [Pegasus Frontend](https://pegasus-frontend.org/) | Themes & Launchers | verified | API 21+ | weekly_2024w38 | GPL-3.0 | mainstream emulator/frontend seed (requested by name) | mainstream-seed |
| 21 | [Snes9x EX+](https://www.explusalpha.com/) | Emulators | needs verification | - | Pre-release | GPL-3.0 | mainstream emulator/frontend seed (requested by name) | mainstream-seed |
| 22 | [Argosy Launcher](https://github.com/rommapp/argosy-launcher) | Themes & Launchers | verified | API 26+ | v2.29.2 | GPL-3.0 | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate |
| 23 | [Arcticons](https://arcticons.com/) | Themes & Launchers | verified | API 21+ | 15.3.2 | GPL-3.0-only | launcher / frontend / icon pack | fdroid, obtainium |
| 24 | [Arcticons Day & Night](https://arcticons.com/) | Themes & Launchers | verified | API 29+ | 15.3.2 | GPL-3.0-only | launcher / frontend / icon pack | fdroid, obtainium |
| 25 | [Arcticons Black](https://arcticons.com/) | Themes & Launchers | verified | API 21+ | 15.3.2 | GPL-3.0-only | launcher / frontend / icon pack | fdroid, obtainium |
| 26 | [Arcticons Material You](https://arcticons.com/) | Themes & Launchers | verified | API 26+ | 15.3.2 | GPL-3.0-only | launcher / frontend / icon pack | fdroid, obtainium |
| 27 | [Moonlight Game Streaming](https://moonlight-stream.org) | Media | verified | API 16+ | 12.1 | GPL-3.0-or-later | game or media streaming client | fdroid, obtainium, rgc-guide |
| 28 | [Lawnicons](https://github.com/LawnchairLauncher/lawnicons) | Themes & Launchers | verified | API 26+ | 2.19.0 | Apache-2.0 | launcher / frontend / icon pack | izzy, obtainium |
| 29 | [Pizza Boy GBA / GBC](https://play.google.com/store/apps/details?id=it.dbtecno.pizzaboypro) | Emulators | external listing | - |  | proprietary | mainstream emulator/frontend seed (requested by name) | mainstream-seed |
| 30 | [Daijishou](https://github.com/TapiocaFox/Daijishou) | Utilities | verified | API 26+ | v1.5.0 | MIT | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate |
| 31 | [MAME4droid-Current](https://github.com/seleuco/MAME4droid-Current) | Utilities | verified | API 29+ | v1.41.2 | GPL-2.0 | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate |
| 32 | [UniPatcher](https://github.com/btimofeev/UniPatcher) | Utilities | verified | API 24+ | v0.19 | GPL-3.0 | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate |
| 33 | [cannoli](https://github.com/CannoliHQ/cannoli) | Utilities | verified | API 28+ | v1.9.1 | GPL-3.0 | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate |
| 34 | [ES-DE Android Apps](https://github.com/BinaryQuantumSoul/esde_android_apps) | Utilities | verified | API 21+ | v1.3.3 | AGPL-3.0 | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate |
| 35 | [Jellyfin](https://jellyfin.org/) | Media | verified | API 21+ | 2.7.3 | GPL-2.0-or-later | game or media streaming client | fdroid, izzy, obtainium |
| 36 | [RetroArch (AArch64)](https://buildbot.libretro.com/stable) | Emulators | needs verification | - | 1.22.2 | - | curated by Retro Handhelds in their RG Rotate Obtainium collection | retrohandhelds-rotate |
| 37 | [﻿USP - ZX Spectrum Emulator](https://bitbucket.org/djdron/unrealspeccyp) | Emulators | verified | API 23+ | 0.0.86.29 | GPL-3.0-or-later | category Emulator and it plays games/console software | fdroid |
| 38 | [Suntimes](https://github.com/forrestguice/SuntimesWidget) | Media | verified | API 14+ | 0.17.6 | GPL-3.0-or-later | game or media streaming client | fdroid, obtainium |
| 39 | [GeoJoystick](https://github.com/Kamui2040/K2040-GeoJoystick) | Emulators | verified | API 27+ | 0.1.5 | GPL-3.0-only | describes itself as an emulator/libretro frontend | fdroid |
| 40 | [Timed Shutdown [No Root]](https://github.com/maforn/TimedShutdownAndroid) | Emulators | verified | API 27+ | v3.0 | GPL-3.0-only | describes itself as an emulator/libretro frontend | fdroid |
| 41 | [8-Bit Wonders](https://eightbitwonders.gitlab.io/app/) | Emulators | verified | API 19+ | 0.8.11 | GPL-2.0-or-later | category Emulator and it plays games/console software | fdroid |
| 42 | [Jellyfin for Android TV](https://jellyfin.org/) | Media | verified | API 21+ | 0.19.10 | GPL-2.0-or-later | game or media streaming client | fdroid, obtainium |
| 43 | [Shizuku](https://shizuku.rikka.app/) | Utilities | verified | API 24+ | 13.6.0.r1086.26508 | Apache-2.0 | file / archive / backup / sync / terminal utility | izzy, obtainium |
| 44 | [BkEmu](https://github.com/3cky/bkemu-android) | Emulators | verified | API 23+ | 1.2.3 | GPL-3.0-only | describes itself as an emulator/libretro frontend | izzy |
| 45 | [Black para Android](https://github.com/RanggaCasper/Black-Android) | Ports | verified | API 29+ | v1.8.1 | MIT | Recompa lists a native Android recomp of Black | recompa |
| 46 | [Doom](https://github.com/Desm0nt/doom-port) | Ports | verified | API 29+ | v0.4.22 | MIT | Recompa lists a native Android recomp of Doom (2016) | recompa |
| 47 | [Downhill Revived](https://github.com/skuza-oss/downhill-revived) | Ports | verified | API 30+ | v0.7.13 | GPL-3.0 | Recompa lists a native Android recomp of Downhill Domination | recompa |
| 48 | [Dusklight](https://github.com/TwilitRealm/dusklight) | Ports | verified | API 28+ | v2.0.3 | CC0-1.0 | Recompa lists a native Android decomp of The Legend of Zelda: Twilight | recompa |
| 49 | [GT3 Revisites](https://github.com/matt-pulsipher/GT3-revisited) | Ports | verified | API 24+ | v0.6.3 | MIT | Recompa lists a native Android source-port of Gran Turismo 3 | recompa |
| 50 | [Need for Speed: Most Wanted](https://github.com/RanggaCasper/MostWanted-Android) | Ports | verified | API 29+ | v1.4.0 | GPL-3.0 | Recompa lists a native Android recomp of Need for speed most wanted bl | recompa |
| 51 | [Unleashed Recompiled](https://github.com/SansNope/UnleashedRecomp-Android) | Ports | verified | API 29+ | v0.6.1 | GPL-3.0 | Recompa lists a native Android recomp of Sonic Unleashed | recompa |
| 52 | [Cinderbox](https://github.com/Ekyso/Cinderbox) | Ports | verified | API 26+ | 0.8.1 | MIT | Recompa lists a native Android source-port of Stardew Valley | recompa, obtainium |
| 53 | [RimDroid](https://github.com/udarmolota/RimDroid) | Ports | verified | API 30+ | 0.3.0 | GPL-3.0 | Recompa lists a native Android source-port of RimWorld | recompa, obtainium |
| 54 | [FableDroid](https://github.com/hardsilinder/FableDroid) | Ports | verified | API 31+ | v0.6.3-beta | MIT | Recompa lists a native Android recomp of Fable II | recompa |
| 55 | [Zandatsu](https://github.com/dfdx047/Zandatsu) | Ports | verified | API 30+ | v1.2 | GPL-3.0 | Recompa lists a native Android recomp of Metal Gear Rising Revengeance | recompa |
| 56 | [Fluffy](https://github.com/mlm-games/fluffy) | Utilities | verified | API 24+ | 4.6.0 | GPL-3.0-or-later | utility category File Manager | fdroid, izzy |
| 57 | [Universal Installer](https://universal-installer.pwhs.app/) | Utilities | verified | API 24+ | 1.21.0 | GPL-3.0-only | utility category App Manager | fdroid, izzy |
| 58 | [LetterBox](https://gitlab.com/muelli/letterbox) | Games | verified | API 23+ | 1.8.0 | GPL-3.0-only | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 59 | [BlocksTV](https://github.com/22pumba22/BlocksTV) | Games | verified | API 23+ | 0.9.2 | MIT | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 60 | [Square Chess](https://dataespresso.com/) | Games | verified | API 26+ | 1.5.0 | GPL-3.0-or-later | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 61 | [Alex vs Bus: The Race](https://github.com/M374LX/alexvsbus) | Games | verified | API 16+ | 2025.06.16.0 | GPL-3.0-or-later | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 62 | [King Pong](https://kingalexgilbert.github.io/king-pong/) | Games | verified | API 24+ | 2.0.0 | GPL-3.0-only | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 63 | [SuperShopaholic](https://gitlab.com/jave/supershopaholic) | Games | verified | API 21+ | 1.1 | AGPL-3.0-or-later | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 64 | [Bluke](https://github.com/arnav-kr/Bluke) | Games | verified | API 28+ | 1.1.0 | AGPL-3.0-or-later | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 65 | [Findroid](https://github.com/jarnedemeulemeester/findroid) | Media | verified | API 28+ | 1.1.0 | GPL-3.0-only | game or media streaming client | fdroid, izzy |
| 66 | [Fabularium](https://github.com/davidar/fabularium) | Games | verified | API 16+ | 1.5.1 | GPL-2.0-or-later | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 67 | [FinalRozGameNew](https://rozworld.itch.io) | Games | verified | API 21+ | 1.0.0 | MIT | mentions gamepad / controller / D-pad / keyboard control | fdroid |
| 68 | [StS2 Mobile Launcher](https://github.com/Ekyso/StS2-Launcher) | Ports | verified | API 24+ | 0.2.0 | MIT | Recompa lists a native Android source-port of Slay the Spire 2 | recompa, obtainium |
| 69 | [citra](https://github.com/weihuoya/citra/releases) | Emulators | verified | API 24+ | 20251112 | GPL-2.0 | recommended in the Retro Game Corps Android emulation guide | rgc-guide |
| 70 | [cemu](https://github.com/SSimco/Cemu/releases) | Emulators | verified | API 30+ | 0.5 | MPL-2.0 | recommended in the Retro Game Corps Android emulation guide | rgc-guide |
| 71 | [idTech4A++](https://github.com/glKarin/com.n0n3m4.diii4a) | Games | verified | API 24+ | 1.1.0harmattan72li | GPL-3.0-only | retro / arcade / classic game style | fdroid, recompa |
| 72 | [DOOM & Wolfenstein RPG](https://github.com/Erick194) | Games | verified | API 24+ | 1.0.4.8 | GPL-3.0-only | retro / arcade / classic game style | fdroid, recompa |
| 73 | [Katawa Shoujo: Re-Engineered](https://fhs.sh) | Games | verified | API 21+ | 2.0.5 | MPL-2.0 | retro / arcade / classic game style | fdroid, recompa |
| 74 | [PipePipe](https://github.com/InfinityLoop1308/PipePipe) | Media | verified | API 23+ | 5.5.0 | GPL-3.0-or-later | media player (Online Media Player) | fdroid |
| 75 | [Polaris](https://github.com/agersant/polaris-android) | Media | verified | API 24+ | 0.10.4 | MIT | media player (Online Media Player) | fdroid |

## Coverage gaps and caveats

**What "verified" means here.** A real APK served by the project's own repository, an official developer server, or an official package repository (F-Droid / IzzyOnDroid), whose package id, minSdk, ABIs and licence were read, and whose file answered a range read as a ZIP. It is **not** a device test and **not** an approval. Index-sourced rows (F-Droid, IzzyOnDroid) carry their manifest in the index; 60 of them were spot-checked by range read. Recompa / Obtainium / Retro Handhelds / Retro Game Corps rows are third-party leads: their files were re-resolved from the upstream release and their manifests read from the remote APK (central directory + `AndroidManifest.xml` by Range requests, nothing downloaded whole; the reader was cross-checked against `aapt2` on two APKs).

**Trust-policy changes needed before any external-source candidate could enter the signed catalog (NOT applied; production rules are unchanged).**
1. `CatalogPolicy.releaseOk` / `tools/trust.py` accept only a GitHub release download of the entry's own repository. To admit APKs from F-Droid / IzzyOnDroid, add a per-entry `download_host` that the signed index pins (https://f-droid.org/repo/, https://apt.izzysoft.de/fdroid/repo/) while the artifact's `sha256` and `signer_sha256` stay mandatory; the hash pin keeps integrity independent of the host.
2. Official developer servers (buildbot.libretro.com, ppsspp.org, downloads.duckstation.org) need the same per-entry pinned host plus an approval that records the official page it came from (today an approval's `release` must be a GitHub tag URL).
3. GitLab and Codeberg need their own release-download URL patterns in `releaseOk`.
4. Rolling tags (Vita3K `continuous`, nightlies) must be pinned by SHA-256 and re-signed per build, or stay external.
5. A ZIP that contains APKs (Snes9x EX+ pre-release) cannot be installed by the PackageInstaller flow: external listing only.
6. Paid, store-only or licence-restricted software (DuckStation CC-BY-NC-ND, ES-DE, DraStic, Redream, Pizza Boy) needs an `external listing` entry kind that carries a store URL and **no** download URL, hash or install button.
7. Android-only display fields (`group`, `tags`, `released`, `added`, `long_description`, `features`) still cannot go into a production index while the Nano verifier rejects unknown app fields.

**Coverage gaps and limits.**
- Only structured, public indexes were imported. Closed-source, paid and Google-Play-only apps appear only through the named seed list and the guides, so they are under-represented; third-party APK mirrors (APKPure, Uptodown, ...) were deliberately not used.
- Relevance is keyword- and category-based over the indexes (reasons are recorded per candidate). F-Droid's own categories are coarse, so games/utilities/media are a precision-over-recall selection, not an exhaustive list.
- Obtainium's community directory holds about 480 configurations; most are general-purpose apps outside this scope.
- Licences for GitHub-hosted leads are read from the repository page (SPDX label as shown by GitHub); a repository with none shown is `needs verification`, not assumed free.
- Recompa lists community forks. Each fork is a separate package id and is flagged `fork-or-community-port`; they need the user's own original game files. Its device reports come from other phones and are shown only as signal, never as RG Rotate evidence.
- Compatibility: nothing was run on an RG Rotate. `curated-for-rotate` means Retro Handhelds list the app in their Rotate collection; `manifest-installable` means minSdk <= 31 and arm64 (or pure Java).
- GitHub and CDN requests were unauthenticated and rate-limited; leads that did not resolve before the time limit are flagged and not counted.
