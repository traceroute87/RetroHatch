# GitHub software coverage audit (RG Nano / FunKey OS)

Research pass 2026-11-02. Read-only GitHub API and raw README requests, **71 of the 80 allowed** (29 repository searches, 26 release lookups, 7 owner listings, 7 README fetches, 2 rate-limit probes). Unauthenticated. No package was downloaded, nothing was approved, installed, changed or committed. Compared with the 56 browser entries and every local crawl result (258 repositories, the owner lists in them, the package leads and the wiki evidence).

## Result in numbers
| Measure | Count |
|---|---|
| Distinct repositories returned by search | 298 |
| Strongly relevant (names RG Nano, FunKey S/OS, Anbernic or OPK; noise removed: U.B. Funkeys, a neuroscience lab called Funkey, hotels, and so on) | 64 repositories |
| ...already known to the browser or the local crawls | 35 |
| ...new to local data | 29 (themes, firmware forks and libraries included) |
| Distinct software projects touched (apps, ports, emulators, utilities, add-ons; a collection repo counts once) | **47** |
| ...already known | 35 |
| ...**truly new** | **12**: 9 standalone projects and 3 system add-ons |
| New standalone software suitable for the read-only browser | **8** (4 with a direct OPK, 4 source-only) |
| Also new: further downloadable builds of known projects | eDuke32 (2 OPK builds), MPlayer, ST, VBEmu, Gnash sources |
| Known to local discovery but **not in the browser** | 58 verified-OPK apps (43 32blit games, 7 SDL2 games, Temperature, 3 ADB tools, Half-Life, Counter-Strike, TyrQuake, VitaQuake II) plus 29 picoarch cores |

**Recall caveat.** Of the 88 repositories earlier crawls rated "supports" or "family", this search found 35 (about 40%). Unauthenticated GitHub search misses most of what an authenticated crawl finds, so a repository absent here is not evidence it does not exist. Treat "truly new" as a floor.

## Truly new: standalone software (12)
| Project | Form | Device evidence | Licence | Source |
|---|---|---|---|---|
| **Handheld Link** (send ROMs, saves, apps between two handhelds over USB) | direct OPK, 8.5 MB, v0.4.0 (released 2026-11-02) | README: runs on FunKey OS, tested between an RG Nano and a GBA Mini | MIT | https://github.com/DankMiimer/handheld-usb-link |
| **ScummVM** | direct OPK, 77 MB, v2.6.1 | repo and tag say FunKey S | GPL-3.0 | https://github.com/DrUm78/scummvm |
| **gnuboy** (Game Boy emulator) | direct OPK, 72 KB, v1.2.3 | tag says FunKey S | GPL-2.0 | https://github.com/DrUm78/gnuboy |
| **dingux-msx** (MSX emulator) | direct OPK, 656 KB, an asset of the rgnano_binary release | file name says rgnano | none stated | https://github.com/trngaje/rgnano_binary |
| **FK-TD** (tower defense) | source only, no release | "for the FunKey S" | none stated | https://github.com/robbi-blechdose/FK-TD |
| **Bibi** (Bomberman) | source only; a 2021 release tag has no files | "readapted for the FunKey S" | LGPL-2.1 | https://github.com/FunKey-Project/Bibi |
| **4 Gewinnt** (Connect 4) | source only | RGNano organisation, no description | none stated | https://github.com/RGNano/4gewinnt |
| **Ginger Ginny** (game) | source only; no release | description says "FunKey SDL Game" | not checked | https://github.com/nckstwrt/GingerGinny |
| System add-ons: **SimpleMenu for RG Nano**, **FunKey Add-on** (advmenu, advmame, retroarch, cores), **AdvanceMAME bundle** (1.6 GB 7z) | OPK installers (34 MB, 98 MB) and an archive | README: FunKey and Anbernic | none stated; the README forbids sharing individual files | https://github.com/trngaje/rgnano_binary |

Weaker leads, not counted: `itsmeterada/FunKey-S` ("some programs for fun", source), `WinUser-Generic/RgNano`, `robbi-blechdose/cybermetropolis`, `dvplayer`, `tsumon`, `slrmoon/motherload` (no Nano evidence or no description).

## Not standalone apps (found, kept out of the count)
Themes: PixelPerfect, Pixel-Fantasy, RGNano/Minimal. Firmware and system parts: FunKey-OS forks (3), NeoBox RG Nano buildroot, FunKey-OS-T113 (a different SoC), RetroFE and picodrive-irixxxx (release tags with no files), fkgpiod, FunKey GPIO mapping, ProdScreens, Allwinner BROM notes. Libraries and tooling: fk-engine-core, FunKeyLib, libopk, rgnano-libretro (config files), a Skraper mix, mini-scraper (PC tool). Not FunKey: Blockamok (44 assets for other consoles, none for FunKey), USB Netplay (a ZIP for ROCKNIX, KNULLI and similar), Miyoo builds, UB Funkeys projects.

## Category breakdown (the 12 new projects)
| Category | Count | Projects |
|---|---|---|
| Games | 4 | FK-TD, Bibi, 4 Gewinnt, Ginger Ginny |
| Emulators | 2 | gnuboy, dingux-msx |
| Engines & Tools | 1 | ScummVM |
| Utilities | 1 | Handheld Link |
| System add-ons (frontend, installer, bundle) | 3 | SimpleMenu, FunKey Add-on, AdvanceMAME bundle |
| Unclassified leads (not counted) | 1 | itsmeterada/FunKey-S |

## Top 30 missing applications (new or known but not displayed), by evidence and availability
Direct OPK with a named device, known licence first; source-only last. "Known" means local discovery already saw it.

| # | Application | New? | Form | Source |
|---|---|---|---|---|
| 1 | Handheld Link | new | direct OPK, MIT, RG Nano tested | https://github.com/DankMiimer/handheld-usb-link |
| 2 | Temperature | known | direct OPK, MIT (needs an ADX sensor) | https://github.com/joyrider3774/temperature_funkey |
| 3-9 | checkers, dynamate, puztrix, puzzleland, retrotime, waternet, worm (7 separate games) | known | ZIP-contained OPKs, MIT, RG Nano in topics | https://github.com/joyrider3774/funkey_sdl2_games |
| 10 | ScummVM | new | direct OPK, GPL-3.0; needs game data | https://github.com/DrUm78/scummvm/releases |
| 11 | eDuke32 (2 builds) | known project, new builds | direct OPKs, no licence stated; needs game data | https://github.com/StupidHoroscope/fks-eduke32 , https://github.com/DynaMight1124/fks-eduke32-320 |
| 12-13 | Half-Life, Counter-Strike | known | 12 KB launchers in a ZIP, GPL-3.0; need your own game files | https://github.com/DankMiimer/rg-nano-xash3d |
| 14 | gnuboy | new | direct OPK, GPL-2.0, 72 KB | https://github.com/DrUm78/gnuboy |
| 15 | dingux-msx | new | direct OPK, licence unknown | https://github.com/trngaje/rgnano_binary |
| 16-18 | USBLink, SwitchToADB, SwitchToUSB | known | direct OPKs, MIT; need ADB-capable firmware | https://github.com/DankMiimer/rg-nano-adb-tools |
| 19-20 | TyrQuake, VitaQuake II | known | direct OPKs, FunKey S builds | https://github.com/DrUm78/tyrquake , https://github.com/DrUm78/vitaquake2 |
| 21-24 | Cannonball (OutRun), VVVVVV, Commander, Gmu music player | known | DrUm78 FunKey S forks; release assets not checked this pass | https://github.com/DrUm78/Cannonball-C , /VVVVVV , /commander , /gmu |
| 25 | Super Mario 64 port | known project, new source | source; needs your own ROM | https://github.com/DrUm78/sm64-port , https://github.com/Akeruz/sm64-port-funkey-s |
| 26-29 | FK-TD, Bibi, 4 Gewinnt, Ginger Ginny | new | source only | links in the table above |
| 30 | ChooChooTracker | known | source; "ported to the RG Nano / DrUm78 CFW", MIT | https://github.com/jtmchorse/choochootracker-rgnano |

Not in the 30 because they are collections already known: 43 32blit games (https://github.com/joyrider3774/32blit_funkey) and 29 picoarch core launchers (https://github.com/sdhizumi/picoarch). New sources for apps the browser already lists: MPlayer (https://github.com/NovemberJoy/MPlayer, three OPK releases), ST terminal (a 100 KB OPK in rgnano_binary), VBEmu (https://github.com/gameblabla/vbemu), Gnash (https://github.com/gameblabla/gnash-opendingux).

## Needs a compatibility review before anything is listed as supported
| Item | Why |
|---|---|
| Handheld Link | Needs two FunKey OS handhelds with the same app version, an OTG adapter and ADB mode; loads USB network kernel modules built for kernel 4.14.14-funkey from DrUm78's source; ships its own Python runtime. Two-RG-Nano pairing is stated untested. |
| SimpleMenu for RG Nano, FunKey Add-on, AdvanceMAME bundle | Replace or extend the system frontend; the README says do not share individual files or repackage them. Redistribution terms are unclear. |
| eDuke32 FunKey-S (v1.2) | Names FunKey S only, no licence on the repository; needs Duke Nukem 3D data. |
| eDuke32-320 | The tag says 320x240; the Nano screen is 240x240. |
| ScummVM | 77 MB; needs game data; RAM and speed on the Nano are untested. |
| gnuboy | A 72 KB OPK is small for an emulator; contents not inspected. |
| dingux-msx | Licence unknown; likely needs BIOS and ROM files. |
| SM64 port | Needs your own ROM; the FunKey-S port is source-only. |
| Source-only entries (FK-TD, Bibi, 4 Gewinnt, Ginger Ginny) | No release to download: list as "source only", not installable. |
| FunKey-OS-T113, NeoBox RG Nano buildroot, FunKey-OS forks | Firmware for other hardware or unreleased forks: not apps. |

## What this pass did not do
- ZIP contents were not opened, so how many games a ZIP holds is unknown beyond earlier local data.
- OPK files were not inspected for architecture, `.desktop` data or licence notices, so "direct OPK" means a release asset with that name.
- An OPK or a FunKey claim is never proof of RG Nano compatibility; the evidence column quotes what the project itself says.
- Release assets were checked only for the new leads; the DrUm78 forks in items 21-24 are source-level leads.
- Nothing here is approved, hardware-tested or entered in any catalog.
