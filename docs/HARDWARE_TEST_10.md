# Hardware test 10: experimental test-install DEV build (RG Nano), 2026-11-07

**Result: PASS. The experimental DEV installer is deployed and left in place for ongoing testing. Nothing was approved, signed or published.**

| Item | Value |
|---|---|
| Build | `RetroHatchDev.opk`, 528,384 B, sha256 `5b56f29d529d380fcb0d3d71d0ca144851eff4dd1d242ed806de2a34a4f5a3d3` (two builds identical), `-DRH_DEV -DRH_EXPERIMENTAL`; production OPK has none of it (`tests/test_prod_wiring.py`) |
| Deployment | busy preflight (no `retrohatch`/`opkrun` of ours, target not mounted or loop-backed), hash-checked `.new`, rename. Previous DEV OPK `cebab59f...` = `build/dev-k/RetroHatchDev.opk`; original `5b5eea19...` and production `RetroHatch.opk` (`2b0f064d...`) backed up in `build/backup/2026-11-06/`. Battery 56 % at start |

| Step | Result |
|---|---|
| 130 candidates listed | PASS (owner) |
| 102 show Test Install, 28 greyed | PASS (owner) |
| Znax (direct OPK): confirm, download, install | PASS; installed file `774c2a33...` = upstream release asset, `installed.tsv` `x-znax`, no temp files |
| Znax launch, play, clean exit | PASS (owner) |
| Rubido (direct OPK): download, install | PASS; `bbd02cca...` = upstream |
| 2048 (OPK inside an 18.7 MB ZIP): download, extract, install | PASS; ZIP holds one `2048.opk`, installed `33e13cf1...` = member of the upstream ZIP, byte for byte |
| 2048 and Rubido launch, clean exit | PASS (owner) |
| Production and unrelated files | PASS: `RetroHatch.opk` `2b0f064d...`, `rhprobe`, commander, gmu, st-sdl, unarchiver unchanged (names, sizes, dates, hashes); `README` unchanged; `.retrohatch` (production state) empty and untouched; Kishmish save `pet.sav` unchanged; TaraFi not modified by this test |
| Post-checks | no retrohatch/opkrun process, only `loop0` (bluetooth) mounted, no residue (`.new`, `.part`, `.zip`, journal, `.tmp`), boot ID unchanged since 23:46 (no reboot), no new dmesg lines (only the known boot lines), battery 35 % at the end |

Left installed on purpose: Znax, Rubido, 2048 (apps and `x-` records), the cache copies in `.retrohatch-dev/cache/`, and their saves. `installed.tsv` also still lists the DEV fixture `rhprobe`.

Not checked by me: the on-screen UNVERIFIED warnings (owner saw them), the confirmation screens (owner pressed them), and the launches (owner-reported; the saves each app wrote are on the card). Not tested: the cancel and broken-link cases (skipped by request).
