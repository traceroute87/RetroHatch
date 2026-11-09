# Mainstream Android retro software: gap report · checked 2026-11-09

Leads, not approvals. Every claim below was read from an official page, a release page or the APK's own manifest on the date above; where something could not be confirmed it says so. "Expected RG Rotate compatibility" is an expectation from the file's manifest and the SoC class (Unisoc T618, Android 12 / API 31, arm64, about 2.5 GB RAM): **none of it was tested**.

**23 seeds** · in the catalog or inventory already: **4** · missing: **19** · verified official direct APK: **15** · store-only (external listing): **6** · unresolved: **2**

## Summary

| App | Systems | In our catalog? | Official direct APK (verified) | Licence · price | Min Android · ABIs (from the APK) | Expected on RG Rotate |
|---|---|---|---|---|---|---|
| **RetroArch** | multi-system (libretro cores) | **missing** | yes: [RetroArch_aarch64.apk](https://buildbot.libretro.com/stable/1.22.2/android/RetroArch_aarch64.apk) · 1.22.2 · 175 MB | GPL-3.0 (GitHub) · free | API 16+ · arm64-v8a, x86_64 | installable on API 31 / arm64 (manifest, not a test); depends on the system/core run inside it |
| **Lemuroid** | multi-system (libretro cores) | DEV catalog (bundled, experimental); candidate inventory | yes: [lemuroid-app-free-dynamic-release.apk](https://github.com/Swordfish90/Lemuroid/releases/download/1.17.0/lemuroid-app-free-dynamic-release.apk) · 1.17.0 · 11 MB | GPL-3.0 (GitHub) · free | API 23+ · arm64-v8a, armeabi-v7a, x86, x86_64 | installable on API 31 / arm64 (manifest, not a test); depends on the system/core run inside it |
| **DuckStation** | PlayStation | **missing** | yes: [duckstation-12126.apk](https://downloads.duckstation.org/android-testing/downloads/duckstation-12126.apk) · 12126 · 107 MB | CC-BY-NC-ND-4.0 (curated; GitHub shows no SPDX id) · free | API 24+ · arm64-v8a, armeabi-v7a, x86, x86_64 | installable on API 31 / arm64 (manifest, not a test); medium system: playable for many titles on a T618-class SoC; demanding games may struggle |
| **NetherSX2 (patched AetherSX2)** | PlayStation 2 | **missing** | yes: [NetherSX2-v2.2n-4248.apk](https://github.com/Trixarian/NetherSX2-patch/releases/download/2.2n/NetherSX2-v2.2n-4248.apk) · 2.2n · 21 MB | Unlicense (GitHub) · free | API 26+ · arm64-v8a | installable on API 31 / arm64 (manifest, not a test); heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **ARMSX2** | PlayStation 2 | **missing** | yes: [ARMSX2-2.9.2-a11-armv8.2-sdk30.apk](https://github.com/ARMSX2/ARMSX2/releases/download/2.9.2/ARMSX2-2.9.2-a11-armv8.2-sdk30.apk) · 2.9.2 · 75 MB | GPL-3.0 (GitHub) · free | API 30+ · arm64-v8a | installable on API 31 / arm64 (manifest, not a test); heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **PPSSPP** | PlayStation Portable | **missing** | yes: [ppsspp.apk](https://www.ppsspp.org/files/1_20_4/ppsspp.apk) · 1.20.4 · 43 MB | GPL-2.0 (curated; GitHub shows no SPDX id) · free (Gold is a paid Play Store supporter edition) | API 21+ · arm64-v8a, armeabi-v7a, x86_64 | installable on API 31 / arm64 (manifest, not a test); medium system: playable for many titles on a T618-class SoC; demanding games may struggle |
| **Vita3K** | PlayStation Vita | **missing** | yes: [android-latest.apk](https://github.com/Vita3K/Vita3K/releases/download/continuous/android-latest.apk) · continuous · 28 MB | GPL-2.0 (GitHub) · free | API 28+ · arm64-v8a, x86_64 | installable on API 31 / arm64 (manifest, not a test); heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **Mupen64Plus FZ** | Nintendo 64 | **missing** | no: store listing only (Google Play) | GPL-3.0 (GitHub) · free (Pro is a paid Play Store edition) | not inspected (no direct APK) | unknown until a file is inspected; medium system: playable for many titles on a T618-class SoC; demanding games may struggle |
| **melonDS** | Nintendo DS, DSi | DEV catalog (bundled, experimental); candidate inventory | yes: [app-gitHub-prod-release.apk](https://github.com/rafaelvcaetano/melonDS-android/releases/download/2.0.1/app-gitHub-prod-release.apk) · 2.0.1 · 20 MB | GPL-3.0 (GitHub) · free | API 24+ · arm64-v8a, armeabi-v7a, x86_64 | installable on API 31 / arm64 (manifest, not a test); medium system: playable for many titles on a T618-class SoC; demanding games may struggle |
| **DraStic DS Emulator** | Nintendo DS | **missing** | no: store listing only () | proprietary (curated) · paid | not inspected (no direct APK) | unknown until a file is inspected; medium system: playable for many titles on a T618-class SoC; demanding games may struggle |
| **Azahar** | Nintendo 3DS | **missing** | yes: [azahar-android-vanilla-2126.2.apk](https://github.com/azahar-emu/azahar/releases/download/2126.2/azahar-android-vanilla-2126.2.apk) · 2126.2 · 48 MB | GPL-3.0 (GitHub) · free | API 29+ · arm64-v8a, x86_64 | installable on API 31 / arm64 (manifest, not a test); heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **Dolphin** | GameCube, Wii | **missing** | no: store listing only (Google Play) | GPL-2.0 (curated; GitHub shows no SPDX id) · free | not inspected (no direct APK) | unknown until a file is inspected; heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **Flycast** | Dreamcast, NAOMI, Atomiswave | **missing** | yes: [flycast-2.7.apk](https://github.com/flyinghead/flycast/releases/download/v2.7/flycast-2.7.apk) · v2.7 · 35 MB | GPL-2.0 (GitHub) · free | API 21+ · arm64-v8a, armeabi-v7a, x86, x86_64 | installable on API 31 / arm64 (manifest, not a test); heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **Redream** | Dreamcast | **missing** | no: store listing only (Google Play) | proprietary (curated) · free; optional $6 Premium | not inspected (no direct APK) | unknown until a file is inspected; heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **Yaba Sanshiro 2** | Sega Saturn | **missing** | no: store listing only (Google Play) | GPL-2.0 (curated) · free; Pro is a paid Play Store edition | not inspected (no direct APK) | unknown until a file is inspected; medium system: playable for many titles on a T618-class SoC; demanding games may struggle |
| **Snes9x EX+** | Super Nintendo | **missing** | yes: [Snes9xEXPlus.zip](https://github.com/Rakashazi/emu-ex-plus-alpha/releases/download/Pre-release/Snes9xEXPlus.zip) · Pre-release · 6 MB · official ZIP of APKs, pre-release | GPL-3.0 (GitHub) · free (EmuEx apps are also sold on Google Play) | not inspected | unknown until a file is inspected; light system: expected to run comfortably on a mid-range SoC like the Unisoc T618 |
| **Pizza Boy GBA / GBC** | Game Boy Advance, Game Boy Color | **missing** | no: store listing only (Google Play) | proprietary (curated) · free (ads) / Pro paid | not inspected (no direct APK) | unknown until a file is inspected; light system: expected to run comfortably on a mid-range SoC like the Unisoc T618 |
| **MAME4droid** | Arcade (MAME) | **missing** | yes: [MAME4droid.2026-1.41.2-release.apk](https://github.com/Seleuco/MAME4droid-2024/releases/download/v1.41.2/MAME4droid.2026-1.41.2-release.apk) · v1.41.2 · 162 MB | GPL-2.0 (GitHub) · free | API 29+ · arm64-v8a | installable on API 31 / arm64 (manifest, not a test); light system: expected to run comfortably on a mid-range SoC like the Unisoc T618 |
| **Winlator** | Windows x86 games (Wine + Box64) | **missing** | yes: [Winlator_11.2.apk](https://github.com/brunodev85/winlator/releases/download/v11.2.0/Winlator_11.2.apk) · v11.2.0 · 150 MB | LGPL-2.1 (GitHub) · free | API 26+ · arm64-v8a | installable on API 31 / arm64 (manifest, not a test); heavy system: expected to struggle on a T618 (Mali-G52 MP2 GPU, about 2.5 GB RAM reported by the device) |
| **Daijishō** | frontend | candidate inventory (ON HOLD: signing certificate looks like an AOSP key: investigate who holds it first) | yes: [416.apk](https://github.com/TapiocaFox/Daijishou/releases/download/v1.5.0/416.apk) · v1.5.0 · 17 MB | MIT (GitHub) · free | API 26+ · no native code | installable on API 31 / arm64 (manifest, not a test); light system: expected to run comfortably on a mid-range SoC like the Unisoc T618 |
| **ES-DE** | frontend | **missing** | no: store listing only (Samsung Galaxy Store (paid), Patreon (paid APK, official), page blocks automated checks) | MIT (desktop); Android partly closed source (curated) · Android: paid | not inspected (no direct APK) | unknown until a file is inspected; light system: expected to run comfortably on a mid-range SoC like the Unisoc T618 |
| **Pegasus Frontend** | frontend | candidate inventory (ON HOLD: licence not detected: resolve it first) | yes: [pegasus-fe_alpha16-82-gc3462e68_androi](https://github.com/mmatyas/pegasus-frontend/releases/download/weekly_2024w38/pegasus-fe_alpha16-82-gc3462e68_android64.apk) · weekly_2024w38 · 17 MB | GPL-3.0 (curated; GitHub shows no SPDX id) · free | API 21+ · arm64-v8a | installable on API 31 / arm64 (manifest, not a test); light system: expected to run comfortably on a mid-range SoC like the Unisoc T618 |
| **Beacon** | frontend | **missing** | **not confirmed**: no official channel identified | unknown (curated) · unknown | not inspected (no direct APK) | unknown until a file is inspected; light system: expected to run comfortably on a mid-range SoC like the Unisoc T618 |

## What can enter the signed catalog as a direct download

The catalog policy (`tools/trust.py`, the device verifier) accepts an APK only when its URL is a **GitHub release download of the entry's own source repository**. Of the verified direct APKs:

- **RetroArch**: external listing / manual only - the official download is on `buildbot.libretro.com`, not a GitHub release of `libretro/RetroArch`.
- **Lemuroid**: **eligible** - GitHub release of its own repository.
- **DuckStation**: external listing / manual only - the official download is on `downloads.duckstation.org`, not a GitHub release of `stenzek/duckstation`. Licence note: Non-commercial, no-derivatives licence: link to the official download, never redistribute.
- **NetherSX2 (patched AetherSX2)**: **eligible** - GitHub release of its own repository. Licence note: Community patch of the abandoned, closed-source AetherSX2; not an official upstream. Package name equals AetherSX2's, so it conflicts with the original signature.
- **ARMSX2**: **eligible** - GitHub release of its own repository.
- **PPSSPP**: external listing / manual only - the official download is on `www.ppsspp.org`, not a GitHub release of `hrydgard/ppsspp`.
- **Vita3K**: **eligible** - GitHub release of its own repository.
- **melonDS**: **eligible** - GitHub release of its own repository.
- **Azahar**: **eligible** - GitHub release of its own repository.
- **Flycast**: **eligible** - GitHub release of its own repository.
- **Snes9x EX+**: external listing / manual only - the official file is a ZIP of APKs on a pre-release.
- **MAME4droid**: **eligible** - GitHub release of its own repository.
- **Winlator**: **eligible** - GitHub release of its own repository.
- **Daijishō**: **eligible** - GitHub release of its own repository.
- **Pegasus Frontend**: **eligible** - GitHub release of its own repository.

## Store-only software: external listings

These have no APK we may link directly. They can appear in RetroHatch only as clearly labelled **external listings** (a link to the store page, no download, no install button).

- **Mupen64Plus FZ** (Nintendo 64): [Google Play](https://play.google.com/store/apps/details?id=org.mupen64plusae.v3.fzurita) · free (Pro is a paid Play Store edition)
- **DraStic DS Emulator** (Nintendo DS): no live listing found · paid · Closed source, sold on Google Play. The former project site no longer serves a page.
- **Dolphin** (GameCube, Wii): [Google Play](https://play.google.com/store/apps/details?id=org.dolphinemu.dolphinemu) · free
- **Redream** (Dreamcast): [Google Play](https://play.google.com/store/apps/details?id=io.recompiled.redream) · free; optional $6 Premium · redream.io/download lists desktop builds only; Android is linked to Google Play.
- **Yaba Sanshiro 2** (Sega Saturn): [Google Play](https://play.google.com/store/apps/details?id=org.devmiyax.yabasanshioro2) · free; Pro is a paid Play Store edition
- **Pizza Boy GBA / GBC** (Game Boy Advance, Game Boy Color): [Google Play](https://play.google.com/store/apps/details?id=it.dbtecno.pizzaboypro) · free (ads) / Pro paid · Closed source. The developer's website did not resolve when checked.
- **ES-DE** (frontend): [Samsung Galaxy Store (paid)](https://galaxystore.samsung.com/detail/org.es_de.frontend.galaxy) · Android: paid · es-de.org: "The Android release is a paid app, and it's partially closed source." ANDROID.md: sold through Patreon, the Samsung Galaxy Store and Huawei AppGallery; not on Google Play.
- **Beacon** (frontend): no live listing found · unknown · Named in the request; no official source could be identified (see the gap report). Needs the maintainer to say which project is meant.

## Findings that change the plan

- **Yaba Sanshiro 2**: the source repository its own website links (`github.com/devmiyax/yabause`) returns 404; only Google Play listings exist.
- **Beacon**: no official project could be identified with the name alone. Please say which Beacon is meant (launcher, URL or package) before it is added.
- **RetroArch cores are not counted** as separate apps; RetroArch, Lemuroid and similar frontends are one entry each.

## Directory seeds for the 500+ goal (next step, not run yet)

Machine-readable or list-style directories that cover emulators and handheld software by console and category, to be read into `discovery/search.py` as seeds, then filtered to real, licensed, installable, non-duplicate APKs:

- Obtainium crowdsourced configurations: `apps.obtainium.imranr.dev` (JSON of apps with their release sources)
- F-Droid category index: Games, Multimedia, System (`f-droid.org/packages/`) and IzzyOnDroid
- Emulation wikis and guides that list Android emulators per console (emulation.gametechwiki.com, the r/EmulationOnAndroid wiki, retro-handheld guides)
- GitHub topics by console (`topic:gameboy`, `topic:psp`, `topic:n64`, ...) combined with `topic:android`, and `topic:retro-handheld` repositories

