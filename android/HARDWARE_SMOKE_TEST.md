# RG Rotate hardware smoke test (debug build, experimental catalog)

Build: `android/app/build/outputs/apk/debug/app-debug.apk` (debug-signed, package `app.retrohatch.rotate`, minSdk 31).
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
5. **Discover + details** - Discover lists 8 apps, each tagged `EXPERIMENTAL`. Open Lemuroid: Status `EXPERIMENTAL / UNVERIFIED`, package, version, size 11.4 MB.
6. **Settings > Catalog** - Source `DEV fixture catalog (bundled)`, Refresh `off: debug build on hardware...`, no network error shown.
7. **Install Unknown Apps flow** - on Lemuroid press Install / Download. Expect "Allow installs" state, Android settings opens (or follow the text), turn on "Allow from this source" for RetroHatch, come back, press Install again.
8. **Download + install Lemuroid** - progress shows, then `Verifying` then `Ready to install`, then Android's installer confirm screen. Confirm. Expect success.
9. **Launch + return** - open Lemuroid (from the app's Open button or launcher), then return to RetroHatch (Back / Home / recents). RetroHatch still responsive, no restart loop.
10. **Installed detection** - Lemuroid now shows `installed` in Discover and Details. Other 7 apps do not (unless already on the device - note which).

Optional: `adb logcat -d | grep -i retrohatch` after a failure; `adb shell pm list packages | grep -i lemuroid`.

Report: pass/fail per item plus any screen that looks wrong.
