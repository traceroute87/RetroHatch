# RG Nano beta: what remains (everything else is built and tested)

Already done and hardware-tested in DEV: signed catalog + rollback state, verified HTTPS downloads (mbedTLS, real certificate checks), cache install/update/uninstall through the engine, offline use, tamper/hash/untrusted-TLS rejection.

## From you (nothing else blocks the beta)
1. Create the GitHub repo `traceroute87/RetroHatch`, push this project, enable Pages (Source = GitHub Actions): `docs/PUBLISHING.md`. (Different name? tell me, one constant changes.)
2. Key ceremony offline, send me the 64-hex public key: `docs/KEY_CEREMONY.md`.
3. Hardware test of kishmish-nano on the Nano: `docs/KISHMISH_REVIEW.md` (about 10 minutes; I can drive it the same way as the last test).
4. Say go for the production build and deploy (with the busy-OPK preflight, `docs/DEPLOY_SAFETY.md`).

## From me (one session, after item 2; no redesign)
1. **Production wiring** (reuse the DEV code): `ui/rh_ui_main.c` production path calls the same `refresh()` / ops setup with `trusted_keys_prod.h`; `ui/rh_ops.c` accepts the production state dir `/mnt/FunKey/.retrohatch` for this build and drops the DEV-only `ALLOWED` list (the signed, approved, hardware-verified catalog entry becomes the only gate; engine denylist, size/SHA-256 and mount checks stay). Roughly 60 changed lines.
2. **Build script:** production OPK bundles `certs/ca-bundle.crt` and the signed snapshot from `tools/make_pkg.py` (same as the DEV recipe).
3. **Tests:** re-run the existing suites; point `test_signed_flow` at the production configuration (state dir name, no allowlist, a second allowed app). No new test framework.
4. **Publish:** you sign the catalog containing kishmish-nano (after its hardware test), push, Pages deploys.
5. **One final hardware test** on the Nano against the REAL GitHub URLs (this also covers the untested GitHub redirect and certificate chain), then deploy the production OPK.

## Shortest path
key + repo (you) -> kishmish hardware test (together) -> production wiring (me, one session) -> publish signed catalog (you) -> real-URL hardware test and deploy (together). Two short working sessions plus your offline key step.

## Known limits to state in the beta notes
Deleting local state resets rollback protection (minimum-serial constant per release closes it for new installs); the CA bundle is a snapshot refreshed per release; the SD card's dirty-FAT flag is not repaired by RetroHatch (recommend `fsck` before first use); one author, one app at launch.
