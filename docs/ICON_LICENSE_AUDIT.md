# Icon licence audit (37 extracted icons)

First pass 2026-11-02 (offline), then a targeted investigation of the eight GitHub-hosted icons the same day with read-only web access to their upstream repositories (GitHub API and raw files: LICENSE, README, credits files, release metadata). Nothing else was fetched; no package was downloaded.

## Verdict

| Class | Icons | Meaning |
|---|---|---|
| Redistributable | **2** | Znax and Rubido: the author states the graphics are his own and the repository is MIT. |
| Unclear | **34** | No icon-specific licence or credit found, or the evidence leaves a gap. |
| Restricted | **1** | Blips: its icon contains a sprite the author bought and marked "do not reuse". |

**2 of 37 icons are cleared and shipped: Znax and Rubido.** Both are recorded as `redistributable` in `discovery/opk-metadata-evidence.json` with their sources, are tracked under `candidates/icons/` with the MIT notices in `candidates/icons/NOTICE.md`, and are the only icons the snapshots name and the production OPK carries. Blips is recorded `restricted`; the other 34 stay `unclear` and show the package glyph. A project licence is never assumed to cover artwork: the two cleared icons rest on explicit statements about who made the graphics.

## Targeted investigation: the eight GitHub-hosted icons

Each icon was matched to its upstream file by SHA-256 (seven are byte-identical to a file in the repository; the SuDokuL icon is not in the repository and is a resized derivative of the author's logo). Links point at the commit read. All eight repositories are MIT; the licence text names the copyright holder shown. Every release asset was uploaded by the repository owner, so each author published the icon inside the OPK themselves.

| Icon | Upstream file | Who made the artwork | Evidence for this icon | Notice / attribution if shipped | Verdict |
|---|---|---|---|---|---|
| Znax | [`graphics/znax.png`](https://github.com/joyrider3774/znax_funkey/blob/d196189936e5/graphics/znax.png) | Willems Davy (joyrider3774) | README Credits: "All Graphics were made by Willems Davy initially for the gp2x version ... adapted ... using gimp". The icon is four coloured blocks like the game's own `blocks.png`. [README](https://github.com/joyrider3774/znax_funkey/blob/d196189936e5/README.md), [LICENSE](https://github.com/joyrider3774/znax_funkey/blob/d196189936e5/LICENSE) | MIT: keep "Copyright (c) 2025 Willems Davy" and the permission text | **Redistributable** |
| Rubido | [`rubidofs/icon.png`](https://github.com/joyrider3774/rubido_funkey/blob/8ca470ce87b6/rubidofs/icon.png) | Willems Davy | README Credits: "Graphcis are made by me willems davy aka joyrider3774 using gimp". The bought assets it lists (and warns not to reuse) are sounds only. The icon sits beside `graphics/`, not inside it, so this rests on the blanket graphics statement. [README](https://github.com/joyrider3774/rubido_funkey/blob/8ca470ce87b6/README.md), [LICENSE](https://github.com/joyrider3774/rubido_funkey/blob/8ca470ce87b6/LICENSE) | MIT: keep "Copyright (c) 2024 Willems Davy" and the permission text | **Redistributable** |
| Blips | [`graphics/blips.png`](https://github.com/joyrider3774/blips_funkey/blob/903679a02b7c/graphics/blips.png) | Mixed: a 2x2 composite of dynamite, floor, player and box tiles | The dynamite tile is `graphics/bomb.png`. README Graphics: "dynamite: GUI Icons by Rexard (gamedevmarket.net) - **I Payed for this asset do not reuse !**" (also in `graphics/credits.txt`). Floor and player are Kenney CC0, box is SpriteAttack CC0, the CC BY-SA wall is not in the icon. [README](https://github.com/joyrider3774/blips_funkey/blob/903679a02b7c/README.md), [credits.txt](https://github.com/joyrider3774/blips_funkey/blob/903679a02b7c/graphics/credits.txt) | None can be given: reuse is refused for the dynamite | **Restricted** |
| Funkoban | [`graphics/sokoban.png`](https://github.com/joyrider3774/sokoban_funkey/blob/cd9fcc60dbaf/graphics/sokoban.png) | Mixed: a 2x2 composite of a target-corner tile, floor, player and box | README Graphics credits: floor and player "Kenney Sokoban tiles" CC0, box "SpriteAttack" CC0, wall "1001.com" CC BY-SA 3.0 (the wall is not in the icon). The top-left target-corner tile (`graphics/spot.png`) is credited nowhere. The README names "Kenney" for the player sprite; it was not checked against the Kenney pack (outside the eight repositories). [README](https://github.com/joyrider3774/sokoban_funkey/blob/cd9fcc60dbaf/README.md) | If cleared: CC0 needs none; the MIT notice "Copyright (c) 2025 Willems Davy" for the author's part | Unclear |
| Blockdude | [`blockdudefs/icon.png`](https://github.com/joyrider3774/blockdude_funkey/blob/de20a6c0ba54/blockdudefs/icon.png) | Chris Katiesen (default skin), per README | The icon shows the default-skin character and grass. README Credits: "The default graphics skin was created by Chris Katiesen for Klas Kroon's remake of blockdude/Blockman (oos.moxiecode.com)". No licence or permission for that skin is stated, and the repository's MIT grant is the porter's own. [README](https://github.com/joyrider3774/blockdude_funkey/blob/de20a6c0ba54/README.md) | Unknown | Unclear |
| Cglpsdl1 | [`meta/cglpsdl1.png`](https://github.com/joyrider3774/crisp-game-lib-portable-funkey/blob/5374382f1f54/meta/cglpsdl1.png) | Not stated | No credit for the icon. README credits the retrofe preview images to "Sai from funkey discord" and TommyShots. [`LICENSE.txt`](https://github.com/joyrider3774/crisp-game-lib-portable-funkey/blob/5374382f1f54/LICENSE.txt) is MIT, "Copyright (c) 2022 ABA Games", the library author's, not necessarily the icon artist's. [README](https://github.com/joyrider3774/crisp-game-lib-portable-funkey/blob/5374382f1f54/README.md) | Unknown | Unclear |
| Formula1 | [`filesystem/icon.png`](https://github.com/joyrider3774/formula1_funkey/blob/8093421fb84e/filesystem/icon.png) | Presumably the author; not stated | The "F1" lettering matches the housing art in `filesystem/graphics/background.png`. The README has no credits section and no statement about the graphics; "F1" is also a Formula One mark. [README](https://github.com/joyrider3774/formula1_funkey/blob/8093421fb84e/README.md), [LICENSE](https://github.com/joyrider3774/formula1_funkey/blob/8093421fb84e/LICENSE) | MIT "Copyright (c) 2023 Willems Davy" if cleared | Unclear |
| SuDokuL | none (OPK-only `sudokul-image.png`); closest: [`SuDokuLVS2019/3ds/logo_icon_3ds_48.png`](https://github.com/Mode8fx/SuDokuL/blob/ef32fb770c7b/SuDokuLVS2019/3ds/logo_icon_3ds_48.png) | Mode8fx (GateGuy), per README | README Credits: "Everything in this game is made by me except for the following assets": music (modarchive.org), font Commodore Pixelized v1.2 by Devin Cook, most background art (kddove85, opengameart.org), sound effects (Luke.RUSTLTD). The icon is that "S" logo with rounded corners at 32x32, published by the author in release v1.5 ([release](https://github.com/Mode8fx/SuDokuL/releases/tag/v1.5)). The exact file is not in the repository and nothing records how it was made. [README](https://github.com/Mode8fx/SuDokuL/blob/ef32fb770c7b/README.md), [LICENSE](https://github.com/Mode8fx/SuDokuL/blob/ef32fb770c7b/LICENSE) | MIT "Copyright (c) 2021 GateGuy" if cleared | Unclear (closest to clearing) |

### Software licence versus icon licence

- **Znax, Rubido:** no separate icon licence exists. The cover is the repository MIT licence plus the author's own statement that the graphics are his. That is evidence for these two files, not a general rule for his other repositories (Blips, Funkoban and Blockdude show he also uses bought and third-party art).
- **Funkoban and Blips share a tile set** (floor, player, box), credited to Kenney and SpriteAttack under CC0 and to 1001.com under CC BY-SA 3.0. The icons use only the CC0 tiles plus one extra: dynamite in Blips (bought, refused) and an uncredited target-corner tile in Funkoban. So the mixed licences of that set would not be triggered by the icons; the single uncredited tile is the gap.
- **Blockdude** is the opposite case: the repository is MIT, but the artwork in the icon belongs to someone else and carries no stated licence.
- **Cglpsdl1:** the MIT holder (ABA Games) wrote the library, not the icon.

### What would settle the open ones

| Icon | Needed |
|---|---|
| Funkoban | The author confirms the origin of `spot.png` (or it is redrawn), and the Kenney player sprite is checked against its source pack. Then CC0 plus MIT applies. |
| SuDokuL | The author confirms the OPK icon is his own derivative of the "S" logo (a repository note or the file added to the repo). |
| Formula1 | The author confirms the graphics are his own; "F1" lettering could be redrawn. |
| Cglpsdl1 | The icon author is identified and a licence is recorded, or the icon is replaced. |
| Blockdude | Permission or a licence for the default skin, or a different sprite. |
| Blips | Cannot be cleared as it is; a new icon without the dynamite would be a different file. |

## What the first pass found for the rest

- **Wiki-hosted packages (28 icons, files on the FunKey wiki file host, MPlayer among them):** no licence is cached anywhere (`license: unknown`), the wiki page text was never saved, and the package files are not kept. Nothing to rely on.
- **J2ME `pm.opk` (inspected):** the repository declares no licence; the package's only notice (`NOTICE-JavaMobileAudio.txt`, GPLv2) covers an audio library.
- **MPlayer package (inspected):** the README credits the port author and thanks others, and names no licence.
- **Visual check:** 22 icons appear to show a console, a product or project logo or brand lettering. That is not evidence of a restriction, but it points to third-party ownership, so those are the most likely to need replacing.

## Matrix

| Icon | App | Source licence | Icon-specific notice | Appears to show | Attention | Class |
|---|---|---|---|---|---|---|
| `cglpsdl1` | Cglpsdl1 | MIT | none; icon author not stated | game pad | - | Unclear |
| `funkoban` | Funkoban | MIT | README credits floor, player, box as CC0; top-left tile has no credit | game scene: crate and a character sprite | - | Unclear |
| `j2mefunkeyrgnano` | j2me-funkey-rgnano | unknown | package inspected: none for the icon | steaming cup, Java-style | brand/console | Unclear |
| `sudokul` | SuDokuL | MIT | README: all but music, font, background art, sound effects is the author's; this file is not in the repository | orange "S" | - | Unclear |
| `wiki-3doh` | 3DOh | unknown | none found (package not kept) | 3DO console with a visible brand name | brand/console | Unclear |
| `wiki-blips` | Blips | MIT | README: dynamite sprite "I Payed for this asset do not reuse !" | game scene: crate, log, character | - | Restricted |
| `wiki-blockdude` | Blockdude | MIT | README: default skin by Chris Katiesen, no licence stated | game scene: character on a platform | - | Unclear |
| `wiki-commodore64` | Commodore 64 | unknown | none found (package not kept) | "C64" lettering | brand/console | Unclear |
| `wiki-dinothawr` | Dinothawr | unknown | none found (package not kept) | green dinosaur, game art | - | Unclear |
| `wiki-dosboxpure` | DOSBox Pure | unknown | none found (package not kept) | crate labelled "DOS BOX" | brand/console | Unclear |
| `wiki-easyrpg` | EasyRPG | unknown | none found (package not kept) | green swirl, project logo | brand/console | Unclear |
| `wiki-fake08` | Fake-08 | unknown | none found (package not kept) | "FAKE 08" lettering | - | Unclear |
| `wiki-finalburnalpha2012` | FinalBurn Alpha 2012 | unknown | none found (package not kept) | orange logo | brand/console | Unclear |
| `wiki-finalburnneo` | FinalBurn Neo | unknown | none found (package not kept) | flame logo | brand/console | Unclear |
| `wiki-formula1` | Formula1 | MIT | none; the repository has no graphics credits | "F1" lettering | brand/console | Unclear |
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
| `wiki-rubido` | Rubido | MIT | README Credits: "Graphcis are made by me willems davy"; the bought assets it lists are sounds | pixel cross | - | Redistributable |
| `wiki-sdlretro` | SDL Retro | unknown | none found (package not kept) | invader-shaped logo | brand/console | Unclear |
| `wiki-smsplus` | SMS Plus | unknown | none found (package not kept) | Master System console | brand/console | Unclear |
| `wiki-st` | ST | unknown | none found (package not kept) | terminal prompt | - | Unclear |
| `wiki-swanemu` | SwanEmu | unknown | none found (package not kept) | WonderSwan handheld | brand/console | Unclear |
| `wiki-vbanext` | VBA Next | unknown | none found (package not kept) | Game Boy Advance | brand/console | Unclear |
| `wiki-vbemu` | VBEmu | unknown | none found (package not kept) | Virtual Boy headset | brand/console | Unclear |
| `wiki-znax` | Znax | MIT | README Credits: "All Graphics were made by Willems Davy" | four coloured squares | - | Redistributable |

"Attention: brand/console" marks icons that appear to depict third-party hardware or a logo (22 of 37). The other 15 show no visible third-party mark, but their author is still unknown (outside the eight investigated).

Per-icon verdicts, evidence sentences and source URLs are in `discovery/opk-metadata-evidence.json` under `icon.redistribution`.

## What was done about it

- Only `wiki-znax.png` and `wiki-rubido.png` are tracked (`.gitignore` lists them with `!` lines; every other `candidates/icons/*.png` is ignored), named by a snapshot (`icon_file`) and copied into the production OPK together with `NOTICE.md`.
- `build-opk.sh` copies only the files a snapshot names, and a snapshot names an icon only when its status is `redistributable`. The 35 other icons show the package glyph.
- The icon-loading code and its security checks are unchanged. Tests use synthetic icons for the feature and check that exactly these two real icons are named.
- Development copies of all 37 icons (plus `manifest.json` with SHA-256 values) stay in `build/opk-icons/`, git-ignored and never packaged.

## Notices that travel with the icons

MIT requires the copyright and permission notice to accompany the icon. `candidates/icons/NOTICE.md` carries the full MIT text with "Copyright (c) 2025 Willems Davy" (Znax) and "Copyright (c) 2024 Willems Davy" (Rubido), the source commit URLs and the file SHA-256 values, and `build-opk.sh` copies it into the OPK beside the icons. No other attribution is required.
