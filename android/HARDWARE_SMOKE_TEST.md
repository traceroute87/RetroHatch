# RG Rotate hardware smoke test (debug build, experimental catalog)

Build: `android/app/build/outputs/apk/debug/app-debug.apk` (debug-signed, package `app.retrohatch.rotate`, version 0.4.0-ui, minSdk 31).
The 8 apps (Aegis, Droid-ify, Gallery, Lemuroid, Material Files, melonDS, NewPipe, Obtainium) come from a bundled catalog signed with a throw-away DEV key.
All are EXPERIMENTAL / UNVERIFIED. No production catalog exists. On real hardware the debug build never contacts 10.0.2.2 and does no online refresh.

## Install
```
adb devices
adb install -r app-debug.apk
adb shell am start -n app.retrohatch.rotate/.ui.MainActivity
```
(`-r` keeps data on re-install. Uninstall: `adb uninstall app.retrohatch.rotate`.)

## Checks (pass / fail / note each)
1. **Install + open** - app installs, icon-less launch works, Home appears, no crash.
2. **720x720 layout** - nothing clipped or overlapping; orange strip reads `EXPERIMENTAL DEV CATALOG - bundled, offline - test key`; hint bar (A / B) visible; text readable.
3. **Touch** - tap rows, tap A / B in the hint bar, scroll the lists.
4. **Buttons** - D-pad moves highlight, A selects, B / Back goes back (on Home leaves app), L1 / R1 jump four rows. Note any key that does nothing.
5. **Discover + details** - Discover lists 8 apps under the orange EXPERIMENTAL strip. Open Lemuroid: an EXPERIMENTAL chip, Overview, Features, App information (package, version, 11.4 MB), Compatibility "Experimental".
6. **Settings > Catalog** - Source `DEV fixture catalog (bundled)`, Refresh `off: debug build on hardware...`, no network error shown.
7. **Install Unknown Apps flow** - on Lemuroid press Install. One tap: expect "Allow installs" and Android's settings (turn on "Allow from this source" for RetroHatch), come back, press Install again.
8. **Download + install Lemuroid** - progress shows, then `Verifying`, then Android's installer confirm screen. Confirm. Expect success and the page switching to Open / Uninstall.
9. **Launch + return** - press Open, then return to RetroHatch (Back / Home / recents). RetroHatch is still responsive and shows the same state.
10. **Installed detection** - Lemuroid shows `Installed` in Discover, appears in Installed with its real icon and version, and is not listed under Updates. The other 7 apps are not listed unless already on the device.
11. **Launcher icon** - the RetroHatch icon fills its launcher tile with no white border and nothing important cropped.
12. **Uninstall** - on Lemuroid press Uninstall. Android's own "Do you want to uninstall this app?" appears; Cancel keeps it, OK removes it and the page returns to Install by itself.

Optional: `adb logcat -d | grep -i retrohatch` after a failure; `adb shell pm list packages | grep -i lemuroid`.

Report: pass/fail per item plus any screen that looks wrong.
