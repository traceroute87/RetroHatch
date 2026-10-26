# Phase 5C-2 hardware test: update RH Probe 1.0.0 -> 1.1.0 (DEV build only)

Artifacts (staged, not deployed): `build/RetroHatchDev.opk` (sha256 `985793636422f3849d152f733dc043f520d52c4cdbcce941607b0447126dcf6b`)
and `build/probe/rhprobe_1.1.0.opk` (4096 B, `abad12c3cfb11db70928b9061cf9034ecc4c0ee60450f85ceb8631f3c9a7d205`; differs from 1.0.0 only in the
desktop Comment). Baseline to preserve: `.retrohatch-dev/installed.tsv` `98f1763d...1544`, cache `2cb430f6...2963`,
`rhprobe_funkey-s.opk` = `2cb430f6...` (4096 B, 01:49), production `RetroHatch.opk` `b75332e6...`.

N="sh $HOME/.ssh/rgnano_ssh.sh"; D=/mnt/FunKey/.retrohatch-dev; V2=abad12c3cfb11db70928b9061cf9034ecc4c0ee60450f85ceb8631f3c9a7d205

## H0 preflight (read-only)  No squashfs mount, no RetroHatch process, baseline hashes above, no `$D/journal`, no `*.new`.
## H1 deploy (agent)  Replace `RetroHatchDev.opk` via hash-checked `.opk.new` -> rename (keep a PC copy of the current DEV OPK `b4c82e4c...` first);
put `rhprobe_1.1.0.opk` into `$D/cache/$V2.opk` and verify its hash. Nothing else is written; v1.0.0 cache + record untouched.
## H2 user checks (RetroHatch DEV)
1. Discover/Installed/Updates: Updates lists "RH Probe (test) 1.0.0 > 1.1.0"; its Details bar is an amber "Update".
2. A -> Update screen: "Old version is backed up", "1.0.0 > 1.1.0", **Cancel** focused. B and Cancel return with no change.
3. A, Down, A on Update -> "Updating..." (no input) -> "Updated". Back to details: bar "Installed", version 1.1.0; Updates = "No updates available".
4. MENU, re-enter the Apps drawer.
## H3 agent verification (after you quit)
`sha256sum /mnt/Applications/rhprobe_funkey-s.opk` = `$V2`; `installed.tsv` = one line `rhprobe 1.1.0 $V2 /mnt/Applications/rhprobe_funkey-s.opk`;
`$D/backup/rhprobe_funkey-s.opk.bak` = `2cb430f6...` (v1.0.0); file mtime even and >= old+4 s; no journal / `*.new`; manifest shows "RH Probe (test)" and
the opkinfo Comment reads "... v1.1.0"; `/mnt/FunKey/.retrohatch` still absent; production + TaraFi + other OPKs unchanged.
## H4 optional negatives (need a state that is still 1.0.0, so run BEFORE H2, or after restoring 1.0.0 is not possible without Uninstall)
Run first, then the real update: (a) temporarily rename the cache file -> bar "Update file missing", A does nothing; (b) wrong-size cache -> "Update file wrong size".
(Wrong-hash / unmanaged / mounted / interrupted updates are covered by 263 host checks; no on-device kill hook.)
## Cleanup  None this phase: RH Probe 1.1.0 + backup stay for Uninstall (5C-3). Note: the engine's uninstall parks and then deletes the single per-app backup,
so the v1.0.0 backup does not survive an uninstall (it is never restored).
