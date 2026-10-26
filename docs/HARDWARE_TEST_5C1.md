# Phase 5C-1 hardware test: controlled install of RH Probe (DEV build only)

Artifacts (staged, not deployed): `build/RetroHatchDev.opk` (drawer name "RetroHatch DEV", red-DEV icon) and the probe
`build/probe/rhprobe_1.0.0.opk` (4096 B, sha256 `2cb430f65e63d2105bd7a407f40a145352a0fece44d6b18937985eb53d9b2963`, MIT).
Production `RetroHatch.opk` (`b75332e6...`) is not touched. DEV state/cache/journal/backup: `/mnt/FunKey/.retrohatch-dev/` only.
Writes on the Nano: `RetroHatchDev.opk`, `/mnt/FunKey/.retrohatch-dev/**`, and (by the install itself) `/mnt/Applications/rhprobe_funkey-s.opk`.

N="sh $HOME/.ssh/rgnano_ssh.sh"; D=/mnt/FunKey/.retrohatch-dev; SHA=2cb430f65e63d2105bd7a407f40a145352a0fece44d6b18937985eb53d9b2963

## H0 preflight (read-only)
No `RetroHatchDev.opk*`, no `rhprobe*` in /mnt/Applications, `$D` absent, no squashfs mount, production hash `b75332e6...`.

## H1 deploy DEV OPK (hash-checked .opk.new -> rename) and place the probe in the DEV cache
`cat build/probe/rhprobe_1.0.0.opk | $N "mkdir -p $D/cache && cat > $D/cache/$SHA.opk && sync"` then `sha256sum $D/cache/$SHA.opk` = `$SHA`.

## H2 user checks (RetroHatch DEV, not RetroHatch)
1. Drawer shows "RetroHatch DEV" with the red DEV icon; Settings > About says "DEV (install test)".
2. Discover: TaraFi "Not available"; RH Probe (test) with an amber focusable "Install" bar.
3. A -> Install screen: details (1.0.0, 4.0 KB, rhprobe_funkey-s.opk), focus on **Cancel**. A on Cancel returns, nothing written. B also cancels.
4. A, Down, A on Install -> "Installing..." (no input) -> "Installed". A returns to details, bar = "Installed" (non-focusable).
5. Installed lists RH Probe (test) 1.0.0. Re-enter the Apps drawer: "RH Probe (test)" is listed. (Launching it does nothing visible.)
Agent checks over SSH: `$N "sha256sum /mnt/Applications/rhprobe_funkey-s.opk"` = `$SHA`; `cat $D/installed.tsv` has one rhprobe line; no `journal`, no `*.new`; `/mnt/FunKey/.retrohatch` still absent; other OPKs + TaraFi unchanged.

## H3 negative cases (agent switches state over SSH while the app is closed; user observes)
a. Remove the cache file -> RH Probe bar reads "Local file missing", A does nothing (uninstall first or use a fresh DEV state: `rm -rf $D/installed.tsv $D/backup; rm /mnt/Applications/rhprobe_funkey-s.opk`).
b. Cache file of the right size but different bytes -> Install -> "Install failed: SHA-256 mismatch. No changes were kept." No rhprobe OPK created.
c. Unrecorded `rhprobe_funkey-s.opk` already in /mnt/Applications (copy of the probe, no installed.tsv line) -> "Install failed: Target not installed by RetroHatch"; file unchanged.
d. Production RetroHatch still shows its approved UI and no install actions.

## H4 cleanup (test-created only; app closed)
`rm -f /mnt/Applications/rhprobe_funkey-s.opk /mnt/Applications/RetroHatchDev.opk; rm -rf $D; sync`; confirm drawer = original + RetroHatch, production hash `b75332e6...`.
Crash recovery is host-tested (4 crash points) and was hardware-verified for the engine in 3B; there is no on-device kill hook.
