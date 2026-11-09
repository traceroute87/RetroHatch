# RetroHatch for RG Rotate (Android)

Kotlin Android app for the RG Rotate (Android 12 / API 31, 720x720 touchscreen, D-pad and buttons). Separate from the Nano code
(`platforms/nano`, `ui/`, `core/`); it shares only the **catalog format, the signing key and the trust rules** (`catalog/`, `tools/trust.py`).

**M1 status: browse only.** Home, Discover, App Details, Installed/Updates (empty states), Settings (Device Information, Catalog Status, About).
No network, no install. Until a signed Android catalog exists, the bundled offline sample is shown and labelled **PREVIEW ONLY** everywhere.

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

## Not done (M2)
Android `PackageInstaller`, catalog download, and the APK fields of the signed index (package name, versionCode, signer-certificate SHA-256).
`tools/trust.py` still requires `.opk` destination names, so no signed Android catalog can be built yet; the Kotlin verifier already accepts the
generalised shape (dest rules apply to `opk` artifacts only). Nothing here publishes a catalog or touches the signing key.
