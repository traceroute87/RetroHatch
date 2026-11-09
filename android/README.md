# RetroHatch for RG Rotate (Android)

Kotlin Android app for the RG Rotate (Android 12 / API 31, 720x720 touchscreen, D-pad and buttons). Separate from the Nano code
(`platforms/nano`, `ui/`, `core/`); it shares only the **catalog format, the signing key and the trust rules** (`catalog/`, `tools/trust.py`).

**M2 status: download, verify, install (standard Android confirmation).** Home, Discover, App Details with Download / Install / Installed / Error states,
Installed and Updates lists, Settings. Until a signed Android catalog exists, the bundled offline sample is shown and labelled **PREVIEW ONLY** everywhere and nothing
can be installed from it. No silent installs: the last step is Android's own "Do you want to install this app?" screen (PackageInstaller session), and the user
must allow RetroHatch under "Install unknown apps".

Install pipeline (`model/Download.kt`, `model/Install.kt`, `android/AndroidDeps.kt`): signed catalog entry -> HTTPS download (https only, also across redirects, size
and SHA-256 from the signed entry, `.part` file, progress, cancel) -> the platform reads package name, versionCode and signing certificate(s) from the APK and they must
equal the signed `android` object (`package`, `version_code`, `signer_sha256`) -> size/hash/identity checked again right before the PackageInstaller session -> user confirms.

## Build and test (Windows or Linux; JDK 17+, Android SDK with platform 34 + build-tools 34)
```
cd android
echo sdk.dir=<path to Android SDK> > local.properties      # not committed
./gradlew :app:testDebugUnitTest :app:assembleDebug
```
APK: `app/build/outputs/apk/debug/app-debug.apk`. Tests run on the JVM (no device) and read the SAME fixtures the Nano verifiers use:
`tests/trust_fixture/signed` (signed index) and `tests/rfc8032_vectors.h` (RFC 8032 vectors).

## Layout
- `model/` pure Kotlin, no Android: `StrictJson` (strict parse + canonical form = `trust.py`), `Trust` (Ed25519 via BouncyCastle, fail closed, rollback state),
  `CatalogPolicy` (publish gates ported from `trust.py check_index`), `Catalog` (model, **device filter**, preview/signed loader).
- `ui/` native Android views built in code. Layout is the Nano's, in "Nano pixels" x 3 (240 -> 720).
- `res/drawable-nodpi/` byte-identical copies of the project artwork: `Retro_Hatch.png` (logo), `Header2.png` (home forest), `Header.png` (title band),
  `ui/assets/ic_*.png` (icons). Only the launcher icon is a resized derivative of `Retro_Hatch.png`. The originals are untouched.
- `assets/preview/index.json` offline sample (unsigned): two real Nano entries (must be hidden here) and four placeholder Rotate entries with no package.

## Input
Touch: tap rows, A / B in the hint bar. D-pad: move, A / Enter / centre = select. B / Esc / Back = back (Home: leave). L1 / R1 = jump four rows.

## Catalog format (shared with the Nano)
APK artifacts carry `android: {package, version_code, signer_sha256[1..8]}`; the artifact `sha256`/`size` are the APK file's. `install.dest_name` is for OPK artifacts only
(and forbidden on APKs); `android` is forbidden on OPKs. Enforced identically by `tools/validate.py`, `tools/trust.py`, `core/rh_catalog.c` (the Nano verifier still
accepts a shared index) and `model/CatalogPolicy.kt`. `tests/trust_fixture_android/` is a synthetic mixed index signed by the Python tools; Python, C and Kotlin all verify it.

## Testing
- JVM unit tests (44): trust, policy, device filter, downloader (fake connections), identity check, the whole install flow with fakes.
- `python android/tools/dev_fixture.py init|build` then `python android/tools/e2e.py`: end-to-end on the `rotate720` emulator (720x720, API 31) against a local HTTPS server.
  The DEV fixture (clearly labelled test APK `:fixtureapp`, DEV signing key and DEV CA, private parts in `~/.retrohatch-dev-android`) exists only in DEBUG builds
  (`src/debug`: DevHooks, network-security-config debug-overrides). The release build trusts only the production key and the system CAs.

## Not done
Catalog download/refresh (the app reads `files/catalog/index.json[.sig]` or the bundled one), uninstall, background downloads, a signed production Android catalog.
Nothing here publishes a catalog or touches the production signing key.
