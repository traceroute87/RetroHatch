# RetroHatch for RG Rotate (Android)

Kotlin Android app for the RG Rotate (Android 12 / API 31, 720x720 touchscreen, D-pad and buttons). Separate from the Nano code
(`platforms/nano`, `ui/`, `core/`); it shares only the **catalog format, the signing key and the trust rules** (`catalog/`, `tools/trust.py`).

**M3 status: online signed catalog + download, verify, install (standard Android confirmation).** Home, Discover, App Details with Download / Install / Installed / Error states,
Installed and Updates lists, Settings. Until a signed Android catalog exists, the bundled offline sample is shown and labelled **PREVIEW ONLY** everywhere and nothing
can be installed from it. No silent installs: the last step is Android's own "Do you want to install this app?" screen (PackageInstaller session), and the user
must allow RetroHatch under "Install unknown apps".

Online catalog (`model/CatalogUpdate.kt`, `android/FileCatalogStore.kt`): at start (and from Settings > Refresh Catalog) the app fetches
`https://traceroute87.github.io/RetroHatch/catalog/index.json` and `.sig` (the same signed index the Nano uses; not published yet, so today the fetch reports a 404 and the app
stays on the PREVIEW sample). Nothing is shown or stored before the Ed25519 signature, canonical form, every publish gate and the rollback rule pass. The last valid catalog is cached
(one atomically-replaced file per trust class) and re-verified on every start, so it works offline; a rejected, invalid or failed refresh changes only the status line.
Production and DEV trust are separate classes: separate keys, cache file and rollback state; DEV keys exist only in debug builds. Only entries for `rg-rotate` / `android-12` / `apk` are listed.

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
- JVM unit tests (56): trust, policy, device filter, downloader and fetch (fake connections), identity check, the whole install flow, catalog refresh/cache/rollback/offline/DEV-vs-production with fakes.
- `python android/tools/dev_fixture.py init|build` then `python -u android/tools/e2e.py`: 11 end-to-end scenarios on the `rotate720` emulator (720x720, API 31) against a local HTTPS server that stands in for the online catalog.
  The DEV fixture (clearly labelled test APK `:fixtureapp`, DEV signing key and DEV CA, private parts in `~/.retrohatch-dev-android`) exists only in DEBUG builds
  (`src/debug`: DevHooks, network-security-config debug-overrides). The release build trusts only the production key and the system CAs.

## Not done
Uninstall, background downloads, scheduled refresh, a signed production Android catalog (nothing is published yet).

**Package visibility:** no `QUERY_ALL_PACKAGES`. Tested on API 31: an installer is not automatically allowed to see what it installed, so the manifest has a `<queries>` entry for launchable apps (catalog package names are unknown at build time). Apps without a launcher activity are not detected as installed.
Nothing here publishes a catalog or touches the production signing key.

## Real Android apps (candidates, DEV catalog)
`discovery/profiles.json` has an `rg-rotate` profile; `discovery/sources.txt` lists 10 curated GitHub repositories for it. `python tools/apk_inspect.py fetch OWNER/REPO` downloads
the latest release APK and reads its REAL identity with the SDK tools (package, versionCode, minSdk, ABIs, signing-certificate SHA-256, signature schemes, GitHub's own digest);
`apk_inspect.py inventory` writes `candidates/inventory-rg-rotate.json` (same inventory format as the Nano's; `python tools/make_inventory.py --device rg-rotate` makes the snapshot).
Everything is UNAPPROVED. `fits_from_metadata` is a reading of the manifest, not a test; `tested.emulator_x86_64_api31` is `not tested` unless an emulator run is recorded there.
`python android/tools/dev_fixture.py real IDS [tested.json]` signs a DEV-only catalog from those entries (real URLs and hashes, labelled EXPERIMENTAL / UNAPPROVED, approval record says it is not
a human approval); `python -u android/tools/e2e.py 12 NAME PACKAGE` installs one of them through the app on the emulator. No production catalog is built or signed.

## Experimental library (debug builds)
`python android/tools/dev_fixture.py real - build/android-candidates/tested.json` signs a DEV catalog of every inventory entry without a `hold` (8 apps; Pegasus and Daijishou are on hold) and bundles it into
the debug APK (`app/src/debug/assets/dev/catalog`), so Discover lists them with no server. Every artifact is level `experimental`: shown as EXPERIMENTAL / UNVERIFIED, no approval record, nothing claimed about RG Rotate.
Only a DEV-class key may carry `experimental` entries (`Trust.verify(experimentalKeyIds=...)`); `tools/trust.py` and release builds reject such an index, and `verified` entries keep every production gate even in
a DEV catalog. Downloads, size/SHA-256/package/versionCode/signer checks and the Android confirmation screen are the unchanged M2 workflow. An arm64-only APK is listed and verified for RG Rotate; the x86_64
emulator cannot install it (`e2e.py 13` stops after verification).


## UI and app management (0.4.0)
- **Look**: the existing Sunset Ember identity, laid out for 720x720 (3x the Nano's 240x240 grid): one corner radius, amber focus fill with a ring, 21-36 px type, touch back arrow in the header, A/B hint bar. Icons are **Lucide** (ISC, `LUCIDE_LICENSE.txt`): `python android/tools/lucide_to_vector.py` fetches a pinned release and writes `res/drawable/ic_*.xml` (stroke 2, 24-unit grid, tinted at run time). The Nano's pixel icons are gone from this app.
- **Launcher icon**: adaptive icon built by `python android/tools/make_launcher_icon.py` from the original `Retro_Hatch2.png` (mark) over `Header2.png` (forest), inside the safe zone, all densities, flattened legacy PNG too. Preview: `android/build/launcher-preview.png`.
- **Details page**: Overview, Features, App information, Compatibility; a section appears only when the catalog has the data. Optional catalog fields `long_description` (paragraphs split on a blank line, max 2000 chars) and `features` (max 8 x 120 chars) are validated by the Android policy and the shared JSON schema. They are **Android-only**: the RG Nano verifier (`core/rh_catalog.c`) rejects unknown app fields, so `tools/trust.py` refuses to sign a production index that carries them (a production Android catalog needs either a Nano verifier update or a separate Android index). The DEV catalog text is hand-written from each project's README: `candidates/descriptions-rg-rotate.json`.
- **Management**: Installed shows real versions and icons from PackageManager (catalog apps only; "other source" when the installed copy is not signed with the catalog's key; system apps have no Uninstall). Install is one tap (download, verify, then Android's confirmation). Update only for the same signing key and only to a newer versionCode (never a downgrade). Open uses the launch intent. Uninstall opens Android's own confirmation (`ACTION_DELETE`, normal permission `REQUEST_DELETE_PACKAGES`); the screens re-read the device when the activity resumes.
- **Tests**: `./gradlew testDebugUnitTest` (70), `python android/tools/nav_check.py` (D-pad, A/B, Back, touch on the emulator), `python -u android/tools/e2e.py 1 2 3 4 5 6 7 14` (install, cancel, bad hash/signer/package, update, no downgrade, uninstall with a harmless fixture APK; 14 needs `build/ui/fx6.apk` and `fx9.apk` built with `-PfxVersionCode=6|9`).

## Discover: categories, search, sort, filters
Discover keeps the approved look and adds a toolbar (Search, Category, Sort), one line saying what is shown ("2 of 8 - Emulators - A to Z"), and the same app rows. Pure logic in `model/Discover.kt` (unit-tested): search matches name, description, developer and tags (every word); **only categories that hold apps are listed** (Games, Emulators, Ports, Utilities, Media, Themes & Launchers, fixed order, with counts); sort A to Z / Recently updated / Newly added; show All / Installed / Not installed / Updates / Verified only. The query lives in `Ui`, so it survives opening an app. Search needs the on-screen keyboard (touch); everything else works with the D-pad (UP from the list reaches the toolbar). The data comes from Android-only catalog fields `group`, `tags`, `released`, `added` (`discovery/categories.py`; see `discovery/README.md`). `python -u android/tools/discover_check.py` drives all of it on the emulator.

## Curated DEV catalog (RG Rotate Discover)
`candidates/android-curated.json` is the tracked, reproducible selection (about 120 apps from the discovery inventory; the complete 1,2xx-candidate inventory stays separate in `build/discovery/` and `candidates/reports/`):
`python discovery/curate.py select` (offline) → `inspect` (downloads each install-eligible APK once, reads package / versionCode / signer / SHA-256, deletes it) → `check` → `python android/tools/dev_fixture.py curated` (signs the bundled DEV catalog).
- **Installable** (`mode: install`) only when every trust-policy condition holds: a GitHub release download of the app's own repository, a known licence that allows redistribution, a stable tag, an APK whose identity was read from the file, minSdk <= 31, an ABI the Rotate has. The Rotate's `ro.product.cpu.abilist` is `arm64-v8a,armeabi-v7a,armeabi` (read over adb), so 32-bit apps are accepted.
- **External listings** (`mode: external`) for everything legitimate that must not be installed here (F-Droid/IzzyOnDroid-only, official-server downloads, paid/store-only, no licence, patched closed-source builds, entries on hold). They live in the DEV-only top-level `external` list of the signed index (never accepted from a production key), carry a link and a reason and **no** URL, hash or install button; Details shows "External listing" and an "Open <store/page>" button.
- Checks: `python -u android/tools/discover_check.py` (categories, search, sort, filters, external details, D-pad), `nav_check.py`, `curated_install_check.py` (a real install/uninstall of one curated app; needs the emulator's network).
