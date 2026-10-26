# RetroHatch

Discover. Install. Enjoy. Free, open-source app installer for retro handhelds.
Working title; name, domain and trademark are not secured.

**Status: Phase 1 (catalog schema + validator) + Phase 3A/3C (Nano local install + uninstall module; install hardware-verified in 3B, uninstall host-tested only).** No UI, network, discovery or Android code yet.

## Layout

```
catalog/schema/   JSON Schemas (app, device), schema version 1
catalog/devices/  device profiles (hardware + firmware ids + install adapter)
catalog/apps/     one file per app; <id>.json, id == filename
tools/validate.py schema + cross-file rules
core/sha256.*     dependency-free SHA-256
platforms/nano/   rh_install.{c,h}: local OPK install/update/recover into /mnt/Applications
tests/            python tests/test_validate.py ; make -C tests test  (gcc, Linux/WSL)
docs/DESIGN.md    architecture, trust model, risks, next milestone
```

## Validate

```
pip install jsonschema
python tools/validate.py
python tests/test_validate.py
```

## Rules baked into the validator

- Only `status: available` artifacts may ever be offered. Unknown facts stay absent; the artifact stays `unavailable` with a reason.
- `available` needs version, https url, sha256, size, a known license, and a level other than `untested`/`unsupported`.
- `verified` needs evidence whose sha256 equals the artifact sha256 (exact artifact tested).
- Device profile (hardware) and adapter (install method) are separate; many profiles can share one adapter.
- Unknown fields are rejected.

## Nano install module (platforms/nano)

`rh_install()` stages `<name>.opk.new` (invisible to the Apps scanner), checks size/SHA-256/space,
refuses if the target OPK is mounted (loop backing file via /sys/block; unknown = refuse), only replaces
OPKs RetroHatch installed itself, backs up the old file to `/mnt/FunKey/.retrohatch/backup/`, journals,
renames, syncs, re-verifies, and gives the new file an even-second mtime >= old+4 s so the scanner's
path|size|mtime fingerprint changes. `rh_recover()` finishes or rolls back an interrupted install.
Record: `/mnt/FunKey/.retrohatch/installed.tsv` (app_id, version, sha256, dest).

`rh_uninstall(cfg, app_id, dest)` (3C) removes only an OPK the record lists for that app_id whose bytes still match the recorded hash; protected names, mounted or unknown-mount-state targets are refused. It parks a hash-verified copy in the state dir, journals, unlinks, drops the record line, then deletes the parked copy (one backup per app, none after uninstall). `rh_recover()` completes or rolls back an interrupted uninstall. App saves/settings are never touched.

## Local catalog -> engine (Phase 4A, host only)

`tools/plan.py` validates the whole local catalog, selects the artifact for one device + firmware, and refuses anything not `available` + `verified` with an `install.dest_name`. It never downloads: the OPK comes from `--file` and must match the catalog size and SHA-256, then `build/rh_host_cli` (the unchanged install engine) does the work. `rh_host_cli` requires explicit `--apps`/`--state` dirs. TaraFi stays `unavailable`, and `TaraFi.opk` is on the engine denylist regardless. Test: `python3 tests/test_plan.py` (WSL/Linux).

## Nano UI (Phase 4B, host only)

`ui/` = native 240x240 SDL 1.2 UI (Sunset Ember palette), separate from the install engine: `rh_model` (real catalog + `installed.tsv` + device facts), `rh_ui` (screens/navigation), `rh_gfx` (rects, RB12 bitmap fonts, tinted icons), `rh_json`. Assets are baked by `tools/make_ui_assets.py` (WSL: Pillow + resvg). Fonts: GNU Unifont + Kode Mono (OFL); icons: Lucide (ISC). The UI never installs, downloads or touches the network; the details CTA (shown only for `available` artifacts) is read-only.

Test + screenshots (WSL): `make -C tests ui-test SHOTS=../build/shots` then `python3 tools/shots_png.py build/shots build/shots_png`. Viewer: `build/rh_ui_host <repo_root> [state_dir]`. Test fixtures in `tests/ui_fixture/` are fake apps for tests only.

**Phase 4C (staged, not deployed):** `sh platforms/nano/ui/build-opk.sh` (WSL) -> `build/RetroHatch.opk` + `.sha256` (reproducible). Program: `ui/rh_ui_main.c`; launcher files in `platforms/nano/ui/`. Buttons arrive from fkgpiod as the letters u/d/l/r/a/b (q = MENU), as in TaraFi.

## Trusted catalog (Phase 6C-1, host only)

`tools/trust.py` (build/sign/verify, Ed25519 via `cryptography`), `tools/artifact_verify.py`, `catalog/approvals.json`. Only human-approved, hardware-verified artifacts reach the signed index. Verifier fails closed until a production public key is set. See `docs/TRUST.md`. Test: `python tests/test_trust.py`.

**Phase 6C-2:** native verifier `core/rh_catalog.c` + vendored Monocypher 4.0.3 (`vendor/monocypher/`). Tests: `make -C tests native-test`, `python tests/test_trust_native.py` (WSL). Not connected to the UI. See `docs/TRUST.md`.
