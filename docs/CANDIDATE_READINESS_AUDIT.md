# Candidate readiness audit (130 candidates)

Date: 2026-11-05. Offline review of `candidates/inventory.json` (133 entries, 130 shown in the browser). Nothing was downloaded, installed, approved or deployed. Three single-page reads were made for descriptions (listed under Part 1); no crawl was run. Every candidate stays **UNAPPROVED** and **not hardware-tested**.

## Summary
| Item | Result |
|---|---|
| Candidates in the browser | 130 (unchanged, no duplicates; ids unique) |
| Descriptions replaced or recovered | 71 |
| Still generic | 7 (the `funkey_sdl2_games` builds) |
| Icons found / cleared / rendered | 37 found (every inspected package has a 32x32 PNG) / 2 cleared / 2 rendered in the desktop UI tests (Znax, Rubido); not yet seen on the device |
| Readiness | A 91 / B 19 / C 9 / D 11 |

## Part 1: descriptions
**Before:** 24 entries had no description (the screen showed "No description: the wiki text was not saved."), 43 32blit games shared one generic sentence, and three more (Rockbox, Bibi, 4 Gewinnt) showed crawler wording ("no description", "release tag has no files").

**After:** 71 descriptions were rewritten from a named source. Each such entry carries a `description_source` field in the inventory. Sources:
- **FunKey wiki, raw page read once on 2026-11-05 (`List_of_third-party_OPK_applications`):** 24 entries. Applications table descriptions for Clock, EasyRPG, Game Music Emu, KeyKalc, Pocket CDG, GMenu2X (audio fix) and ST; the Emulators table (system, BIOS file) for 3DOh, DOSBox Pure, FinalBurn Alpha 2012, FinalBurn Neo, Gambatte, MAME 2000, PC-FX Emu, PCSX ReARMed, the two SDL Retro cores; the Games table (genre) for Dinothawr, Divi-Dead, Heboris, NCrafti (the wiki's Crafti, its link is `ncrafti_funkey-s.opk`), SRB2, STK, Worship Vector. For the emulators the OPK `.desktop` Comment in `discovery/opk-metadata-evidence.json` agrees. The wiki's own text is the maintainers' description, so it is the best available "developer" source for these builds.
- **Original README:** Meleelight (the repository README's first paragraph, one read) and the 43 32blit games (the collection README, one read: "32blit game by <author>, ported for FunKey / RG Nano"). The same README names each game's original repository, now stored as a second, non-primary source on every one of those 43 entries.
- **Existing evidence, only reworded:** Rockbox, 4 Gewinnt, Bibi (their old text exposed internal limits).
- **Category side effect:** six of those wiki games (Divi-Dead, Heboris, NCrafti, SRB2, STK, Worship Vector) had the reviewed category "Other" (taken from the file name); the wiki genre column now sets "Games" with that column as the basis. In the snapshot's reviewed categories, Games went from 64 to 70 and Other from 9 to 3. Dinothawr was already Games.

**Still generic (7):** Checkers, Dynamate, Puztrix, Puzzleland, Retrotime, Waternet, Worm ("SDL2 game build for FunKey / RG Nano, one of seven in the funkey_sdl2_games collection"). No per-game text exists in tracked evidence, and recovering it would need seven more page reads. The sentence is neutral and states nothing untrue.

**No placeholder text reaches the screen:** a test now fails if any browser entry has an empty description or one that says "no description", "not saved", "wiki text" or "was not recorded". The short status labels the generator adds in front of some descriptions ("Source only", "Package not inspected (audit note)", "Emulator core", "System add-on") are unchanged: they state package status, and the UI tests assert them.

## Part 2: icons
**Pipeline, traced end to end**
1. OPK icon extraction: 37 packages were inspected earlier (`discovery/opk-metadata-evidence.json`); all 37 contain a 32x32 PNG. 93 other candidates' packages were never opened, so their icons are unknown.
2. Redistribution review (`docs/ICON_LICENSE_AUDIT.md`). **Icon rights are separate from application licences:** an app's MIT or GPL licence is never assumed to cover its artwork, so most MIT apps still have an "unclear" icon here. **2 redistributable** (Znax, Rubido: explicit statements about who made the graphics, MIT notices in `candidates/icons/NOTICE.md`), **1 restricted** (Blips), **34 unclear**. A project's licence is never assumed to cover its artwork, so unclear icons are not copied.
3. `candidates/icons/` holds exactly the two cleared PNGs, `wiki-znax.png` and `wiki-rubido.png`, unchanged, each with its own allow line in `.gitignore` and its attribution in `candidates/icons/NOTICE.md` (shipped in the OPK next to them). No icon was added or changed in this work.
4. `candidates/inventory.json` names them with `icon_file` (2 entries); the generator copies that into `rg-nano.json` (2 entries).
5. `platforms/nano/ui/build-opk.sh` copies only the files the snapshot names. The OPK I deployed (built from the committed tree) contains `candidates/icons/wiki-znax.png`, `wiki-rubido.png` and `NOTICE.md` (checked in its squashfs listing).
6. On the device the UI resolves `candidates/icons/<file>` relative to the candidates file, decodes it once, accepts only 32x32 images, and draws it in the row tile; otherwise it draws the package glyph.

**Exact reason no icons were seen on the Nano:** only 2 of the 130 candidates have a licensed icon, and they sit at rows **46 (Rubido) and 57 (Znax)** of the 130-row Discover list. Every other row, including everything on the first screens, correctly shows the plain package glyph. I found no fault in the pipeline: the two files are in the shipped OPK, the snapshot names them, the path and 32x32 checks pass, and the desktop UI tests render both (`ui_nav_test` "icons" section; screenshots below). I did not see the device screen for those two rows, so on-device rendering of them is **not verified**; scroll to Rubido (position 46 of 130, `All 46/130`) to confirm.

**Placeholder:** all other candidates use the one existing package glyph (green box), consistently. Category-specific glyphs were **not** added: they need new artwork, and only a 20 px general icon set exists. This is reported as a possible follow-up, not built.

**Not done on purpose:** no icon was copied without a recorded right, no icon downloads, no 130 new icons. Two likely cheap follow-ups: TaraFi (the owner's own app) and Kishmish Nano (MIT, single author) could be cleared if the owner confirms the artwork is covered; that needs the files, which means a download.

## Part 3: readiness (all 130)
**What the classes mean.** These classes only sort candidates for further evaluation. **Class A means "eligible for further hardware-test evaluation". It does NOT mean approved, safe, redistributable or installable.** Every one of the 130 candidates, A included, is UNAPPROVED, hardware test "none", and cannot be installed or downloaded by RetroHatch. Approval still needs an exact-file hardware test, a licence check, a signed catalog entry and a human decision.

- **A, eligible for evaluation:** source or project identity and a package URL are recorded, the OPK format was seen by a crawl (a squashfs signature only), and no documented blocker exists. Missing evidence is not a blocker by itself.
- **B, needs investigation:** package not inspected or only listed, or an open question about the package.
- **C, blocked by a documented issue.**
- **D, source only:** no release package.

| Class | Count | What it is |
|---|---|---|
| A | 91 | 40 direct OPKs, 51 ZIP-wrapped (the 43 32blit games, 7 SDL2 games, picoarch); Kishmish Nano included |
| B | 19 | package not inspected (Rockbox, Temperature, ScummVM, eDuke32, gnuboy, DINGUX MSX, tyrquake, vitaquake2), wiki GitLab-only builds not verified (Clock, Divi-Dead, Heboris, KeyKalc, NCrafti, SRB2, STK, Worship Vector), plus j2me, NanoCraft, Meleelight |
| C | 9 | firmware or USB-mode changes, cores that are not applications, 12 KB launcher stubs |
| D | 11 | TaraFi and ten source-only repositories |

**Caveats that apply to the candidates (A included)**

1. **Application licences are unknown for 98 of 130.** Only 32 state one (MIT 22, GPL-3.0 4, AGPL-3.0 2, NOASSERTION 2, GPL-2.0 1, LGPL-2.1 1). The unknown ones are mostly the 28 wiki-hosted builds (no source repository), the 43 32blit ports (the port repository is MIT, each game's upstream licence is not checked) and several source-only repos. Unknown means "not established", not "unlicensed". It does not stop a hardware test but it does stop publishing or redistributing any of these files. The Licence column below is the **software** licence only.
2. **ZIP packages are not supported by the current installer.** The installer treats an OPK as one opaque file and cannot open ZIPs. 55 candidates ship inside ZIPs (including 51 of class A: the 43 32blit games, the 7 SDL2 games and picoarch). They can be tested by copying the files by hand, but RetroHatch cannot install them, and most use the unpinned `releases/latest` URL, which can change under us.
3. **Package contents are unverified.** "OPK format seen" means a crawl read a squashfs signature, nothing more: no file was fully inspected, hashed (except Kishmish's recorded SHA-256), run or checked for safety. Rockbox, Temperature, ScummVM, eDuke32, gnuboy, DINGUX MSX, tyrquake, vitaquake2 and the wiki GitLab-only builds were not inspected at all. **Rockbox stays `unverified`: its ZIP was reported as changed and no current evidence exists for its contents.** Kishmish Nano had a static review (`docs/KISHMISH_REVIEW.md`) but is still unapproved and untested on this firmware.
4. **Some apps need extra game data, files or permissions:**
   - BIOS or ROM files: 3DOh (`bios.bin`), PC-FX Emu (`pcfx.rom`), PCSX ReARMed (`SCPH1001.BIN`), DINGUX MSX (BIOS and ROM files, likely). Every emulator also needs the user's own ROMs.
   - Game data: Dinothawr (separate game files), ScummVM, eDuke32, Half-Life and Counter-Strike (own game files), Super Mario 64 port (own ROM, source only), NanoCraft (own Minecraft PE APK), Pocket CDG (matching MP3 and CDG files).
   - Hardware or firmware: Temperature (an ADX sensor), USBLink, SwitchToADB, SwitchToUSB and Handheld Link (ADB-capable firmware, USB mode changes, kernel modules; Handheld Link also needs a second handheld and an OTG adapter), GMenu2X (replaces the firmware menu). ST is a terminal program, so it gives shell access on the device.
5. **Compatibility is claimed, not tested.** 67 name the RG Nano, 62 name FunKey only, 1 is unknown, all from project text. Kishmish's author tested stock Anbernic firmware, not this one.

### Top 10 to test first
1. **Kishmish Nano** (A): MIT, exact 692,224-byte file and SHA-256 `3dfa9fa7...` recorded, static review already done (`docs/KISHMISH_REVIEW.md`), reports RG Nano boot on stock firmware. Only the Nano test is missing.
2. **Znax** (A): MIT software licence, direct 1.4 MB OPK; it also has a cleared icon (a separate right, see Part 2), so it shows the icon path.
3. **Rubido** (A): MIT software licence, direct 3.5 MB OPK; cleared icon as well.
4. **Blips** (A): MIT, direct 0.8 MB OPK, repository topics name the RG Nano.
5. **Blockdude** (A): MIT, direct 3.4 MB OPK, topics name the RG Nano.
6. **Formula1** (A): MIT, direct 0.2 MB OPK, the smallest file; topics name the RG Nano.
7. **Funkoban** (A): MIT, direct 8.5 MB OPK, repository text names the RG Nano.
8. **SuDokuL** (A): MIT, direct 0.9 MB OPK; a self-contained Sudoku game.
9. **Cglpsdl1** (A): MIT, direct 0.3 MB OPK, repository text names the RG Nano.
10. **TriSpace** (A): AGPL-3.0, direct 3.7 MB OPK, an Elite-like space game (source and licence obligations apply when publishing).

All ten are direct OPK downloads (no ZIP step) under an MIT or AGPL software licence, and no BIOS, ROM or game-file dependency is recorded for any of them. Being listed here is a testing order only, not an approval.

### Every candidate
| Name | Class | Source | Package | Licence | Reason / dependency |
|---|---|---|---|---|---|
| 2048 | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| 32blox | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| 3DOh | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded Needs bios. |
| 4inrow | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Alienattack | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Amaze | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Armadillo | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Asteroids | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Blips | A | github.com/joyrider3774/blips_funkey | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Blit Kart | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Blit Racers | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Blockdude | A | github.com/joyrider3774/blockdude_funkey | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Bounce | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Cannonhead | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Carsprint | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Castle | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Cglpsdl1 | A | github.com/joyrider3774/crisp-game-lib-portable-funkey | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Checkers | A | github.com/joyrider3774/funkey_sdl2_games | ZIP > OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Commodore 64 | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Dino | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Dinothawr | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded Needs the separate game files. |
| Dodgeem | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| DOSBox Pure | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Dots | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Dune2 | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Dynamate | A | github.com/joyrider3774/funkey_sdl2_games | ZIP > OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| EasyRPG | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Fake-08 | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| FinalBurn Alpha 2012 | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| FinalBurn Neo | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Formula1 | A | github.com/joyrider3774/formula1_funkey | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Fourblock Descent | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Funkoban | A | github.com/joyrider3774/sokoban_funkey | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Gambatte | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Game Music Emu | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Ganbare Natuskian | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Geometry | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Gnash | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Gol | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Harry | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Indy | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Invader | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Jetpac | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Jumpy Squirrel | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| KeyCraft | A | github.com/robbi-blechdose/KeyCraft | OPK, format seen | AGPL-3.0 | squashfs OPK seen by a crawl; source and package URL recorded |
| Kishmish Nano | A | github.com/Alialhashemi23/kishmish-nano | OPK, not verified | MIT | exact file, SHA-256 and MIT licence recorded in its catalog entry; static review in docs/KISHMISH_REVIEW.md; only the Nano test is missing |
| Knightlore | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| LameDS | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| MAME 2000 | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Match3 | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Mednafen (NES only) | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Minesweeper | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Missile | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| MPlayer | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| PC-FX Emu | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded Needs pcfx. |
| PCSX ReARMed | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded Needs the BIOS file SCPH1001. |
| picoarch | A | github.com/sdhizumi/picoarch | ZIP > OPK, format seen | NOASSERTION | squashfs OPK seen by a crawl; source and package URL recorded |
| PicoDrive | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Piemu | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Ping | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Pocket CDG | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded Needs a matching MP3 and CDG file for each song. |
| PokeMini | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Puztrix | A | github.com/joyrider3774/funkey_sdl2_games | ZIP > OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Puzzleland | A | github.com/joyrider3774/funkey_sdl2_games | ZIP > OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Raycaster | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Retrotime | A | github.com/joyrider3774/funkey_sdl2_games | ZIP > OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Rocks And Diamonds | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Rubido | A | github.com/joyrider3774/rubido_funkey | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Scrolly Tile | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| SDL Retro | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Simon | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| SMS Plus | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Snake | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Snake2 | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Sokoblit | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Solitaire | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| ST | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| SuDokuL | A | github.com/Mode8fx/SuDokuL | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Super Square Bros | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| SwanEmu | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Tower | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| TowerDefense | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| TriSpace | A | github.com/robbi-blechdose/TriSpace | OPK, format seen | AGPL-3.0 | squashfs OPK seen by a crawl; source and package URL recorded |
| VBA Next | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| VBEmu | A | FunKey wiki (hosted OPK, no source repo) | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Wakkawakka | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Waternet | A | github.com/joyrider3774/funkey_sdl2_games | ZIP > OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Willy | A | github.com/joyrider3774/32blit_funkey | ZIP > OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Worm | A | github.com/joyrider3774/funkey_sdl2_games | ZIP > OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| XASH3DFS | A | github.com/Sn3zee-cmds/XASH3DFS | OPK, format seen | unknown | squashfs OPK seen by a crawl; source and package URL recorded |
| Znax | A | github.com/joyrider3774/znax_funkey | OPK, format seen | MIT | squashfs OPK seen by a crawl; source and package URL recorded |
| Clock App | B | FunKey wiki (hosted OPK, no source repo) | OPK, not verified | unknown | named by the FunKey wiki, file not verified |
| dingux-msx | B | github.com/trngaje/rgnano_binary | none | unknown | package named by an audit note or report, file not inspected needs BIOS and ROM files. |
| Dividead | B | FunKey wiki (hosted OPK, no source repo) | OPK, not verified | unknown | named by the FunKey wiki, file not verified |
| eDuke32 | B | github.com/StupidHoroscope/fks-eduke32 | none | unknown | package named by an audit note or report, file not inspected Needs game data. |
| gnuboy | B | github.com/DrUm78/gnuboy | none | GPL-2.0 | package named by an audit note or report, file not inspected |
| Heboris | B | FunKey wiki (hosted OPK, no source repo) | OPK, not verified | unknown | named by the FunKey wiki, file not verified |
| j2me-funkey-rgnano | B | github.com/slrmoon/j2me-funkey-rgnano | OPK, format seen | unknown | pm.opk J2ME runtime: licence unknown, identity of the build not confirmed |
| KeyKalc | B | github.com/Robbi-Blechdose/KeyKalc | none | unknown | named by the FunKey wiki, file not verified |
| meleelight | B | github.com/chasemcdizzle/meleelight-funkey-s | OPK, format seen | NOASSERTION | large port of a Nintendo-game remake; licence NOASSERTION/unstated; check provenance of assets (README 'Assets and provenance') |
| NanoCraft | B | github.com/DankMiimer/nanocraft | ZIP > OPK, format seen | GPL-3.0 | runtime that needs the user's own Minecraft PE APK; check what the package bundles |
| NCrafti | B | FunKey wiki (hosted OPK, no source repo) | OPK, not verified | unknown | named by the FunKey wiki, file not verified |
| Rockbox | B | gitlab.com/hairo/rockbox | ZIP > OPK, not inspected | unknown | package named by an audit note or report, file not inspected |
| ScummVM | B | github.com/DrUm78/scummvm | none | GPL-3.0 | package named by an audit note or report, file not inspected Needs game data. |
| SRB2 | B | FunKey wiki (hosted OPK, no source repo) | OPK, not verified | unknown | named by the FunKey wiki, file not verified |
| STK | B | FunKey wiki (hosted OPK, no source repo) | OPK, not verified | unknown | named by the FunKey wiki, file not verified |
| Temperature | B | github.com/joyrider3774/temperature_funkey | none | MIT | package named by an audit note or report, file not inspected |
| TyrQuake | B | github.com/DrUm78/tyrquake | none | unknown | package named by an audit note or report, file not inspected |
| VitaQuake II | B | github.com/DrUm78/vitaquake2 | none | unknown | package named by an audit note or report, file not inspected |
| Worship Vector | B | FunKey wiki (hosted OPK, no source repo) | OPK, not verified | unknown | named by the FunKey wiki, file not verified |
| Counter-Strike | C | github.com/DankMiimer/rg-nano-xash3d | none | GPL-3.0 | 12 KB launcher stub; needs the rest of a 70-entry ZIP plus the user's game files Needs your own game files. |
| Gambatte (SDL Retro core) | C | FunKey wiki (hosted OPK, no source repo) | ZIP > OPK, not verified | unknown | core, not an application: needs the SDL Retro frontend |
| GMenu2X | C | github.com/DrUm78/gmenu2x | none | unknown | system add-on: replaces the firmware menu (modifies system behaviour) |
| Half-Life | C | github.com/DankMiimer/rg-nano-xash3d | none | GPL-3.0 | 12 KB launcher stub; needs the rest of a 70-entry ZIP plus the user's game files Needs your own game files. |
| Handheld Link | C | github.com/DankMiimer/handheld-usb-link | none | MIT | loads USB kernel modules and ships its own Python runtime; compatibility review needed (audit note) Needs two FunKey OS handhelds, an OTG adapter and ADB mode. |
| SwitchToADB | C | github.com/DankMiimer/rg-nano-adb-tools | none | MIT | changes the USB mode; README says many firmware builds do not support ADB Needs ADB-capable firmware. |
| SwitchToUSB | C | github.com/DankMiimer/rg-nano-adb-tools | none | MIT | changes the USB mode; same ADB firmware caveat Needs ADB-capable firmware. |
| USBLink | C | github.com/DankMiimer/rg-nano-adb-tools | none | MIT | USB link tool; needs ADB-capable firmware Needs ADB-capable firmware. |
| VICE (SDL Retro core) | C | FunKey wiki (hosted OPK, no source repo) | ZIP > OPK, not verified | unknown | core, not an application: needs the SDL Retro frontend |
| 4 Gewinnt | D | github.com/RGNano/4gewinnt | none | unknown | no release package |
| Bibi | D | github.com/FunKey-Project/Bibi | none | LGPL-2.1 | no release package |
| Cannonball | D | github.com/DrUm78/Cannonball-C | none | unknown | no release package |
| ChooChooTracker | D | github.com/jtmchorse/choochootracker-rgnano | none | MIT | no release package |
| Commander | D | github.com/DrUm78/commander | none | unknown | no release package |
| FK-TD | D | github.com/robbi-blechdose/FK-TD | none | unknown | no release package |
| Ginger Ginny | D | github.com/nckstwrt/GingerGinny | none | unknown | no release package |
| Gmu | D | github.com/DrUm78/gmu | none | unknown | no release package |
| Super Mario 64 port | D | github.com/DrUm78/sm64-port | none | unknown | no release package needs your own ROM. |
| TaraFi | D | github.com/traceroute87/TaraFi | none | unknown | no release package |
| VVVVVV | D | github.com/DrUm78/VVVVVV | none | unknown | no release package |

## Part 4: verification (2026-11-05)
- `python tools/make_inventory.py --check` and `python tests/test_inventory.py` pass (133 inventory entries, 130 browser entries, ids unique, snapshot byte-identical to a clean-checkout regeneration).
- C UI tests (WSL, existing build): `ui_nav_test` 17,701 checks, `ui_ops_test` 441, `ui_prod_test` 442, all 0 failed. `ui_prod_test` presses A five times on every candidate with production ops enabled: nothing installs or downloads.
- Representative 240x240 screenshots (git-ignored, `build/shots_audit/`): `audit_sheet_descriptions.png` (Gambatte row and page, DOSBox Pure, Match3, SRB2, Clock) and `audit_sheet_icons_and_more.png` (Rubido and Znax rows with their cleared icons, Znax page, Rockbox, Dinothawr, Rubido page).
- Not verified: the two icon rows on the physical Nano.

## Files changed (this task)
`candidates/inventory.json`, `candidates/rg-nano.json`, `tests/test_inventory.py`, `docs/CANDIDATE_READINESS_AUDIT.md` (new). No code, installer, signing, approval or catalog file changed. Source pages read once each (kept in the git-ignored `build/lookup_*.txt`): the FunKey wiki raw page, the 32blit_funkey README, the meleelight-funkey-s README.
