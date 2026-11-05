# Discovery inventory audit (offline, read-only)

Date: 2026-11-02, updated 2026-11-05 for the unified inventory. Point-in-time audit: the counts below are of the 2026-10-26 crawls and are not refreshed. Where the text says "the 10 displayed candidates" it describes the snapshot of that date; the snapshot is now generated from `candidates/inventory.json` (87 entries, 84 shown) by `tools/make_inventory.py`. The raw package identities of the 43 `32blit_funkey` games, the 29 picoarch cores and the older-crawl-only packages are preserved in the inventory's `package_evidence` section (names, sizes, URLs; no sha256 exists, nothing was hashed). Audit only: nothing was downloaded, no network request was made, no crawler, catalog, approval or key file was changed. Every number below is computed from local files unless it is marked **estimate**.

## Data inspected
| Source | Content |
|---|---|
| `build/crawl/`, `crawl-full/`, `crawl-multi/`, `crawl-freeserp/`, `crawl-smoke/` (all 2026-10-26) | 4 usable crawl results (383 / 422 / 158 / 43 package rows). `crawl/github-run.json` is a byte copy of `crawl/discovery-results.json`. |
| `discovery/package-leads.json` | 38 stored package URLs (30 OPK, 8 ZIP), all `verified`, last checked 2026-10-27. Every one is also in a crawl result (no lead-only package). |
| `candidates/rg-nano.json` | The 10 candidates displayed on 2026-11-02 (built from `crawl-full`); superseded by the inventory snapshot. |
| `build/discovery/candidates-rg-nano.json` | Older 9-repo candidate list (2026-10-26 12:46): Kishmish, NanoArcade, Emerald-Nano, NanoCraft, adb-tools, xash3d, rockbox-mt and two Minecraft ports. Nothing in it adds a verified OPK. |
| `build/freeserp-leads-final.json`, `engine-probe-local/` | 91 web-search result pages; no OPK download beyond those already in the crawls. |
| `catalog/` | 0 approvals, 2 entries (`kishmish-nano`, `tarafi`), both `unavailable`. Neither came from discovery. |
| `tests/ui_fixture/candidates-edge.json` | Test fixture ("not real software"); excluded. |

The four crawls are not nested: `crawl` (earlier) found 10 OPKs that the later `crawl-full` did not (DrUm78 forks, RG350 firmware, SimpleMenu), and `crawl-full` found 29 wiki-hosted OPKs that `crawl` did not. This audit uses the **union**.

## Headline numbers (confirmed from local data)
| Measure | Count |
|---|---|
| Distinct package URLs examined (crawls + leads) | **450** (82 direct OPK URLs, 368 ZIP URLs) |
| ...after collapsing `releases/latest/download` aliases onto their tag URL | 393 (57 alias URLs) |
| Distinct repositories seen | 258 (plus wiki/archive hosts) |
| Distinct OPK files (host + file name, tag/alias/path duplicates merged) | **159** |
| ...squashfs magic verified | 122 |
| ...magic not read (ZIP member limit; all `picoarch-*`) | 18 |
| ...false positive (not squashfs; GitLab `blob` HTML pages) | 19 |
| Unique software projects (mirrors, cores, helper and firmware sets merged) | **113** |
| Likely standalone applications (classes A+B+C) | **101** |
| Already displayed in RetroHatch | 10 (0 approved, 0 hardware-tested) |
| Additional standalone applications potentially available | **91** |

Reconciliation 159 OPK files to 113 projects: minus 1 SDL_Retro duplicate (OPK plus ZIP copy), minus 12 GitLab mirrors of wiki apps, minus 1 helper (`NanoCraftDiag`), minus 29 picoarch cores, minus 3 (the four RG350 firmware files are one project). The 101 standalone are the 113 projects minus 12 excluded projects.

## Deduplication rules used
- Same app = same repository (or wiki) plus same normalized file name. Different games in one repository stay separate (43 games in `32blit_funkey`).
- A `releases/latest/download/X` URL and a `releases/download/<tag>/X` URL are one file.
- The same OPK as a direct asset and inside a ZIP is one file.
- GitLab `blob/...` URLs for apps that also exist on the wiki CDN are mirrors; the other 7 GitLab-only names remain as separate (excluded) projects.
- picoarch: one project (the frontend `picoarch.opk`) plus 29 core packages. Cores are not counted as standalone apps.

## Not counted as applications
- **Emulator cores:** 29 `picoarch-<core>.opk` (11 verified, 18 magic-unread).
- **Helper:** `NanoCraftDiag_funkey-s.opk`; the 12 KB Half-Life/Counter-Strike launchers are stubs that depend on the rest of a 70-entry ZIP (see class C).
- **Firmware/recovery:** RG350 ROGUE CFW (`recovery.opk` plus three 87 MB `*-update-*.opk`).
- **Themes:** `toniremi/funkey_minui_theme`, `funkey_minui_art_theme`, `jessikarochas/PokeUI`, `RetroUI`, `berickphilip/RetroQoL-theme-Funkey-RGNano`.
- **Desktop/dev tools and non-OPK ZIPs:** igir, OpenPackageCreator, FunKey SDK ZIPs, NanoArcade (browser tool), Gerber files, 32blit desktop/STM32/web builds, openOMSI desktop builds, manuals. 112 of the 216 ZIP rows in `crawl-full` hold zero OPKs.

## Classification
Rule for A/B: A = squashfs-verified OPK, repo is not a fork/archive, and the repository text names RG Nano (`supports`). B = squashfs-verified OPK with FunKey-family-only evidence (`family` repo claim, FunKey-S file name, or the FunKey wiki third-party list). A SquashFS signature is treated as package format only. Hardware tests, license and installability are separate gates (see Blockers); no item here has passed them.

| Class | Count | Members |
|---|---|---|
| **A Strong** | **60** | 43 games in `joyrider3774/32blit_funkey`; 7 in `funkey_sdl2_games` (checkers, dynamate, puztrix, puzzleland, retrotime, waternet, worm); Blips, Blockdude, Formula1, Rubido, Znax, Funkoban, Temperature, Cglpsdl1; NanoCraft; picoarch (frontend) |
| **B Possible** | **35** | SuDokuL, KeyCraft, TriSpace, meleelight, XASH3DFS, tyrquake, vitaquake2 (the last two only in the older crawl, repo metadata missing); 28 wiki-hosted OPKs |
| **C Review** | **6** apps (+18 cores) | `pm.opk` (J2ME runtime, license unknown); SwitchToADB, SwitchToUSB, USBLink (README: "many [builds] do not" support ADB); Half-Life and Counter-Strike (12 KB stubs inside a 70-entry ZIP, bring-your-own game files); 18 magic-unread picoarch cores |
| **D Exclude** | **12 projects / 29 files** | 3 DrUm78 `*_gcw0.opk` (PocketSNES, SDLQuake2, eduke32: GCW0/RG350 platform); SimpleMenu-RFW (RG350 firmware launcher); RG350 ROGUE CFW (firmware, 4 files); 7 GitLab-only names with unusable `blob` URLs (clock_app, dividead, heboris, ncrafti, srb2, stk, worship_vector); plus 12 GitLab mirrors, 1 SDL_Retro duplicate and the NanoCraftDiag helper as duplicates/helpers |

Of class A, only **8 are direct OPK downloads** (Blips, Blockdude, Formula1, Rubido, Znax, Funkoban, Temperature, Cglpsdl1). The other **52 are inside ZIP files** (43 + 7 + NanoCraft + picoarch). The installer and `catalog/schema/app.schema.json` have no ZIP/container support (no match for "zip" or "container").

### The 10 candidates displayed on 2026-11-02, by class
A: NanoCraft, Funkoban, Cglpsdl1, picoarch. B: XASH3DFS, meleelight, SuDokuL, TriSpace, KeyCraft. C: j2me `pm.opk`.

### Category counts (standalone apps, A+B+C = 101)
| Category | Count | Basis |
|---|---|---|
| Games | 64 | 62 backed by repo description/topics/README (57 in A, 3 in B, 2 in C: Half-Life, Counter-Strike); 2 wiki games (Dinothawr, Ganbare Natuskian) by **name only (estimate)** |
| Emulators | 19 | picoarch (reviewed category) + 18 wiki OPKs by **name only (estimate)** |
| Media | 3 | wiki: Game Music Emu, MPlayer, Pocket CDG (**estimate**, name only) |
| Utilities | 4 | Temperature, SwitchToADB, SwitchToUSB, USBLink |
| Engines & Tools | 4 | `pm.opk`, XASH3DFS, wiki EasyRPG and Gnash (last two **estimate**) |
| Other | 7 | Cglpsdl1 (ambiguous: "library" and "games" topics), meleelight, tyrquake, vitaquake2 (no cached description), wiki Piemu, LameDS, ST |

The wiki has no cached descriptions, so every wiki category is an estimate. Confirmed: 101 apps, the class sizes, and the 62 metadata-backed games. The rest of the table is an estimate.

## Top 20 strongest additions (not among the current 10)
Ranked by: direct OPK before ZIP-wrapped, RG Nano named in repo text, license known (all MIT), non-stub size, newest push. All share repo-level evidence only; none is hardware-tested.

| # | App | Source repo | Evidence | Size | Form |
|---|---|---|---|---|---|
| 1 | Blips | joyrider3774/blips_funkey v1.0 | description + topics `rg-nano`, `rgnano`; MIT | 0.8 MB | direct OPK |
| 2 | Blockdude | joyrider3774/blockdude_funkey v1.0 | topics `rg-nano`, `rgnano`; MIT | 3.4 MB | direct OPK |
| 3 | Formula1 | joyrider3774/formula1_funkey v1.0 | topics `rg-nano`, `rgnano`; MIT | 0.2 MB | direct OPK |
| 4 | Rubido | joyrider3774/rubido_funkey v1.0 | topic `rg-nano`; MIT | 3.5 MB | direct OPK |
| 5 | Znax | joyrider3774/znax_funkey v1.0 | description + topics; MIT | 1.4 MB | direct OPK |
| 6 | Temperature | joyrider3774/temperature_funkey v1.1 | description "for rg nano / funkey ... from adx device" (needs an ADX sensor); MIT | 0.4 MB | direct OPK |
| 7-13 | checkers, dynamate, puztrix, puzzleland, retrotime, waternet, worm | joyrider3774/funkey_sdl2_games v1.0 | description "builds of my sdl2 playdate games for funkey / rg nano", topics `rg-nano`; MIT | 21-41 MB each | ZIP, `latest` alias URL |
| 14-20 | 2048, 4inrow, minesweeper, Ping, simon, Snake, Solitaire (7 of 43 in this repo; chosen as plain, self-contained titles) | joyrider3774/32blit_funkey v1.0 | README "32blit Games Collection for Funkey-S / RG-Nano", topics `rg-nano`; MIT (port repo; each game's upstream license not checked) | ~18.7 MB each | ZIP, `latest` alias URL |

Below the top 20: 36 more `32blit_funkey` games, then B items. B repo-hosted direct OPKs with a known license are SuDokuL (MIT), KeyCraft and TriSpace (AGPL-3.0), already displayed.

## Reasons preventing expansion
1. **The 10 was a policy cap, not the inventory (resolved).** The removed `tools/make_candidate_snapshot.py` used `MAX=10`, `PER_OWNER=2` and one entry per repository (18 without the cap; the 43-game, 7-game and 30-package repos showed as "+42 / +6 / +11 more"). `tools/make_inventory.py` has no cap and writes one entry per application. The 43 games and 29 cores are still not itemized: only their package identities are kept (`package_evidence`).
2. **ZIP-wrapped packages.** 52 of 60 class-A apps are inside ZIPs. The installer treats an OPK as an opaque file with a size and SHA-256 and has no unpack step; the schema has no container field. Alias URLs (`latest`) are not pinned to a tag or hash.
3. **No hardware evidence or approvals.** `approvals.json` is empty; production needs a hardware test of each exact file plus a human approval. 91 more apps means 91 tests (or an explicit policy for testing collections).
4. **License and provenance.** Unknown or undeclared: all 28 wiki OPKs (hosted on `static.miraheze.org`, no source repository), XASH3DFS, `pm.opk`, tyrquake/vitaquake2 (no metadata); `NOASSERTION`: meleelight, picoarch. The schema does not allow an available artifact with an unknown license.
5. **Size.** 32blit OPKs are 18.7-22.6 MB each (about 0.8 GB for the 43), the SDL2 games 21-41 MB each.
6. **Crawl coverage is bounded and uneven (estimate of the unseen part is not possible).** `crawl` and `crawl-full` each stopped at exactly `max_repos=160`; GitHub access was unauthenticated and rate-limited (21 HTTP 403 in `crawl-full`; metadata missing for DrUm78 repos; a note says "40 repos found, only first 20 inspected"); `crawl-freeserp` left 80 queued items unprocessed and the web-search engine was unavailable; all seven `rgnano.com` pages (applications, emulators, games, keykalc, blips, prboom, vitaquake-ii) failed to load, and a `willemssoft.be` Funkoban download link was never fetched. These are unexamined leads, not counted anywhere above.
7. **Source-only repositories with no verified OPK** (not counted): 66 repos with `supports`/`family` verdict have none; the app-like ones include Emerald-Nano, choochootracker-rgnano, openomsi-nano, stppc2x_funkey (Codeberg), DrUm78 VVVVVV/commander/eduke32/picodrive-funkey/sm64-port. Several are source-only or desktop builds.
8. **Broken links.** 19 GitLab `blob` URLs return 403/HTML; 7 of them are the only source for their app.

## Milestone comparison
| Target | What the audit supports | Needs |
|---|---|---|
| **25** | Yes. 10 shown + 6 new direct-OPK MIT games (items 1-6) = 16, the 6 new ones needing no packaging change, + the 7 `funkey_sdl2_games` = 23, + 2 more (e.g. two `32blit` games or tyrquake/vitaquake2 after a license look) = 25 | Raise the cap and owner limit, list one row per OPK (not per repo); decide how to present ZIP-wrapped packages |
| **50** | Data supports it (60 class A) but only with the 52 ZIP-wrapped apps, so 42 of the 50 would be ZIP-only | ZIP/container or re-hosted-OPK policy, tag-pinned URLs, a testing policy for 40+ near-identical 32blit builds |
| **100** | Not supported. 101 standalone apps exist locally; 28 have unknown license and no source, 6 are class C, and the crawl is known to be incomplete | A fresh authenticated crawl, wiki license/provenance research, and a collection model |

**Recommendation: 25.** It uses only class A, all MIT, with 16 requiring no installer change. The decision that gates anything beyond 25 is how to handle ZIP-wrapped OPKs and whether tests apply per file or per collection. Do not count class B (wiki) toward a milestone until each has a source and a license.

## Confirmed versus estimated
- **Confirmed (local data):** 450 URLs, 393 after alias collapse, 159 OPK files, 122/18/19 verification split, 113 projects, 101 standalone, class sizes 60/35/6/12, 8 direct versus 52 ZIP in class A, the 18-entry result with the cap removed, 0 approvals.
- **Estimates:** wiki-app categories (names only), the 7 GitLab-only app categories, the idea that a C-class app could move up, and anything about software not in the crawls (rgnano.com, uninspected repos, rate-limited DrUm78 repos).
