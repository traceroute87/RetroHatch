# Icon licence audit (37 extracted icons)

Offline audit, 2026-11-02. Inputs: the cached GitHub licence field for each source repository, the notices inside the four packages still on hand (MPlayer, Funkoban, SuDokuL, J2ME), the cached README excerpts, and the icons themselves. No download, crawl or request was made. The other 33 packages were deleted after probing and could not be re-inspected.

## Verdict

| Class | Icons | Meaning |
|---|---|---|
| Redistributable | **0** | No icon has evidence that a licence covers the artwork itself. |
| Unclear | **37** | No icon-specific licence, credit or notice was found. |
| Restricted | **0** | Nothing found says redistribution is forbidden. |

**0 of 37 icons are ready for distribution.** A project licence (MIT here, GPL there) is not assumed to cover its artwork, so the repository-level MIT grants do not clear the 8 icons that have one.

## What the evidence was

- **Wiki-hosted packages (28 icons, files on the FunKey wiki file host, MPlayer among them):** no licence is cached anywhere (`license: unknown`), the wiki page text was never saved, and the package files are not kept. Nothing to rely on.
- **GitHub MIT repositories (joyrider3774: Funkoban, Cglpsdl1, Blips, Blockdude, Formula1, Rubido, Znax; Mode8fx: SuDokuL):** the licence field says MIT. Cached README excerpts say nothing about artwork credits. Blips, Blockdude and Znax are remakes of other authors' games.
- **Funkoban package (inspected):** licence files only for its two fonts (Roboto, Space Mono); none for graphics.
- **SuDokuL package (inspected):** no licence file; its strings point to opengameart.org for art and sound, so third-party art is acknowledged but this picture's licence is not identified.
- **J2ME `pm.opk` (inspected):** the repository declares no licence; the package's only notice (`NOTICE-JavaMobileAudio.txt`, GPLv2) covers an audio library.
- **MPlayer package (inspected):** the README credits the port author and thanks others, and names no licence.
- **Visual check:** 22 icons appear to show a console, a product or project logo or brand lettering. That is not evidence of a restriction, but it points to third-party ownership, so those are the most likely to need replacing.

## Matrix

| Icon | App | Source licence | Icon-specific notice | Appears to show | Attention | Class |
|---|---|---|---|---|---|---|
| `cglpsdl1` | Cglpsdl1 | MIT | none found (package not kept) | game pad | - | Unclear |
| `funkoban` | Funkoban | MIT | package inspected: none for the icon | game scene: crate and a character sprite | - | Unclear |
| `j2mefunkeyrgnano` | j2me-funkey-rgnano | unknown | package inspected: none for the icon | steaming cup, Java-style | brand/console | Unclear |
| `sudokul` | SuDokuL | MIT | package inspected: none for the icon | orange "S" | - | Unclear |
| `wiki-3doh` | 3DOh | unknown | none found (package not kept) | 3DO console with a visible brand name | brand/console | Unclear |
| `wiki-blips` | Blips | MIT | none found (package not kept) | game scene: crate, log, character | - | Unclear |
| `wiki-blockdude` | Blockdude | MIT | none found (package not kept) | game scene: character on a platform | - | Unclear |
| `wiki-commodore64` | Commodore 64 | unknown | none found (package not kept) | "C64" lettering | brand/console | Unclear |
| `wiki-dinothawr` | Dinothawr | unknown | none found (package not kept) | green dinosaur, game art | - | Unclear |
| `wiki-dosboxpure` | DOSBox Pure | unknown | none found (package not kept) | crate labelled "DOS BOX" | brand/console | Unclear |
| `wiki-easyrpg` | EasyRPG | unknown | none found (package not kept) | green swirl, project logo | brand/console | Unclear |
| `wiki-fake08` | Fake-08 | unknown | none found (package not kept) | "FAKE 08" lettering | - | Unclear |
| `wiki-finalburnalpha2012` | FinalBurn Alpha 2012 | unknown | none found (package not kept) | orange logo | brand/console | Unclear |
| `wiki-finalburnneo` | FinalBurn Neo | unknown | none found (package not kept) | flame logo | brand/console | Unclear |
| `wiki-formula1` | Formula1 | MIT | none found (package not kept) | "F1" lettering | brand/console | Unclear |
| `wiki-gambatte` | Gambatte | unknown | none found (package not kept) | Game Boy and Game Boy Color | brand/console | Unclear |
| `wiki-gamemusicemu` | Game Music Emu | unknown | none found (package not kept) | speaker with a music note (stock-icon style) | - | Unclear |
| `wiki-ganbarenatuskian` | Ganbare Natuskian | unknown | none found (package not kept) | anime-style character, game art | - | Unclear |
| `wiki-gnash` | Gnash | unknown | none found (package not kept) | "G" logo | brand/console | Unclear |
| `wiki-lameds` | LameDS | unknown | none found (package not kept) | stacked lettering logo | brand/console | Unclear |
| `wiki-mame2000` | MAME 2000 | unknown | none found (package not kept) | "M" logo | brand/console | Unclear |
| `wiki-mednafennesonly` | Mednafen (NES only) | unknown | none found (package not kept) | NES console | brand/console | Unclear |
| `wiki-mplayer` | MPlayer | unknown | package inspected: none for the icon | yellow arrow with "m" | - | Unclear |
| `wiki-pcfxemu` | PC-FX Emu | unknown | none found (package not kept) | PC-FX console | brand/console | Unclear |
| `wiki-pcsxrearmed` | PCSX ReARMed | unknown | none found (package not kept) | "PCSXR" logo with a game controller | brand/console | Unclear |
| `wiki-picodrive` | PicoDrive | unknown | none found (package not kept) | Mega Drive/Genesis console | brand/console | Unclear |
| `wiki-piemu` | Piemu | unknown | none found (package not kept) | abstract black-and-white figure | - | Unclear |
| `wiki-pocketcdg` | Pocket CDG | unknown | none found (package not kept) | same speaker icon as Game Music Emu | - | Unclear |
| `wiki-pokemini` | PokeMini | unknown | none found (package not kept) | Pokemon Mini handheld with logo | brand/console | Unclear |
| `wiki-rubido` | Rubido | MIT | none found (package not kept) | pixel cross | - | Unclear |
| `wiki-sdlretro` | SDL Retro | unknown | none found (package not kept) | invader-shaped logo | brand/console | Unclear |
| `wiki-smsplus` | SMS Plus | unknown | none found (package not kept) | Master System console | brand/console | Unclear |
| `wiki-st` | ST | unknown | none found (package not kept) | terminal prompt | - | Unclear |
| `wiki-swanemu` | SwanEmu | unknown | none found (package not kept) | WonderSwan handheld | brand/console | Unclear |
| `wiki-vbanext` | VBA Next | unknown | none found (package not kept) | Game Boy Advance | brand/console | Unclear |
| `wiki-vbemu` | VBEmu | unknown | none found (package not kept) | Virtual Boy headset | brand/console | Unclear |
| `wiki-znax` | Znax | MIT | none found (package not kept) | four coloured squares | - | Unclear |

"Attention: brand/console" marks icons that appear to depict third-party hardware or a logo (22 of 37). The other 15 show no visible third-party mark, but their author is still unknown.

Notes per icon are in `discovery/opk-metadata-evidence.json` under `icon.redistribution` (status, evidence sentence, source licence, whether package files were inspected).

## What was done about it

- No icon file is tracked in Git, named by a snapshot (`icon_file`), or copied into the production OPK. Every candidate shows the package glyph.
- `candidates/icons/*.png` is git-ignored; a cleared icon can only be added on purpose (`git add -f`). `build-opk.sh` copies only the files a snapshot names, and a snapshot names an icon only when its status is `redistributable`.
- The icon-loading code and its tests are unchanged in behaviour. The tests now use two synthetic icons drawn for them (`tests/ui_fixture/icons/`).
- Development copies of all 37 icons (plus `manifest.json` with SHA-256 values) stay in `build/opk-icons/`, git-ignored and never packaged.

## What would clear an icon

1. **Own-project artwork with a stated licence:** a README, CREDITS or asset-folder licence naming the icon or its folder (for example the joyrider3774 repositories, if their assets are declared the author's own and MIT).
2. **Third-party art with a recorded licence:** the SuDokuL picture, if its opengameart.org source and licence are identified and the attribution it requires is added.
3. **Replacement:** original artwork for the console, logo and brand icons. This is the realistic route for the flagged icons.
Checking 1 and 2 needs the repositories' files, which means network access that this audit did not use.
