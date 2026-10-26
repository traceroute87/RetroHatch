# Phase 5A hardware procedure (Installed / Updates with isolated test data)

Test build: `build/RetroHatchTest.opk` (`TEST=1 sh platforms/nano/ui/build-opk.sh`). Same binary as production; its
launcher reads ONLY `/mnt/FunKey/.retrohatch-test` and shows in the drawer as "RetroHatch TEST". The production
`RetroHatch.opk` and `/mnt/FunKey/.retrohatch` are never touched. Test names end in "(test)".

Data source: `tests/ui_test_data/` (catalog/ + scenarios/{populated,noupdates,empty}/installed.tsv).

## Deploy (needs approval; Nano writes only under `.retrohatch-test` and one new OPK name)
N="sh $HOME/.ssh/rgnano_ssh.sh"; D=tests/ui_test_data; T=/mnt/FunKey/.retrohatch-test
1. Preflight: no `/mnt/Applications/RetroHatchTest.opk*`, `$T` absent, no squashfs mount.
2. Data (tar over ssh, then verify):
   `tar -C $D -cf - catalog scenarios | $N "mkdir -p $T && tar -C $T -xf - && mv $T/scenarios/* $T/ && rmdir $T/scenarios && echo populated > $T/mode && sync"`
   Check: `find $T -type f | sort` = catalog/apps/{rhprobe,rhprobe-b..e,tarafi}.json, catalog/devices/rg-nano.json,
   {populated,noupdates,empty}/installed.tsv, mode.
3. OPK: stage to /tmp, verify sha256, copy to `/mnt/Applications/RetroHatchTest.opk.new`, verify, rename, sync (same as production procedure).

## Run on the Nano (user), one scenario at a time
Switch scenario (quit the app first): `$N "echo <populated|noupdates|empty> > $T/mode"`.
populated: Installed = 6 rows (RH Probe, B, C, D, E "(test)" at 1.0.0, then `rhprobe-gone` 0.9.0); scroll to last row;
  A on `rhprobe-gone` does nothing (Select hint greyed); A on RH Probe opens details (version 1.1.0, test note).
  Updates = 1 row "RH Probe (test) 1.0.0 > 1.1.0"; A opens details; B returns.
noupdates: Installed = B, C; Updates = "No updates available".
empty: Installed = "No installed applications"; Updates = same empty state.
All: D-pad scroll keeps selection visible, A selects, B backs out, MENU quits. TaraFi (Discover) unavailable.

## Cleanup
Quit app; `rm -f /mnt/Applications/RetroHatchTest.opk; rm -rf /mnt/FunKey/.retrohatch-test; sync`; re-enter drawer.
