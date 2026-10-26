# Final DEV hardware test: signed catalog + HTTPS download + install lifecycle on the RG Nano. NOTHING here has been run on the Nano.

One approval, one session. Everything stays in the DEV world: DEV OPK, `.retrohatch-dev` state, DEV signing key, test CA. Production `RetroHatch.opk`, TaraFi, firmware and `/mnt/FunKey/.retrohatch` are not touched.

## What was built (host tests all pass)

| Piece | Where |
|---|---|
| HTTPS client, mbedTLS 2.16.9 (the version TaraFi uses), cert + host name always verified, TLS 1.2+, https-only incl. redirects, size/time limits, `.part` -> SHA-256 check -> atomic rename | `core/rh_net.{h,c}` |
| Signed catalog source: bundled snapshot + downloaded copy (one atomic file), verified by `rh_catalog_verify_persist` (signature, policy, rollback state) before anything is shown | `ui/rh_source.{h,c}` |
| Model from a verified index; Catalog Status page (A = refresh); Details gets **Download**; Network Status page | `ui/rh_model.c`, `ui/rh_ui.c` |
| Ops: download (allowlist, size+SHA-256 from the signed entry, free-space check, B cancels), refresh | `ui/rh_ops.c` |
| DEV signing key (public half in the OPK, private half in `~/.retrohatch-dev/`), signed DEV catalogs, LAN HTTPS test server | `platforms/nano/ui/trusted_keys_dev.h`, `tools/make_dev_catalog.py`, `tools/dev_server.py` |

Tests: `ui-test` 100, `ops-test` 441, `state-test`, `test_net.py` (real TLS: good/IP/wrong-host/untrusted/expired/not-yet-valid certs, redirects incl. loop/6 hops/downgrade, chunked, truncated, oversize, gzip, malformed headers, timeouts, cancel, offline/DNS), `test_signed_flow.py` (195 checks: bundled -> download -> install -> refresh -> download -> update; tampered/stale/forked/junk/reset/404 catalogs leave cache and rollback state unchanged; wrong-hash/truncated/cancelled/offline downloads leave nothing; offline restart; damaged cache; wrong key; corrupt rollback state), plus all earlier trust/native suites.

## Staged artifacts (host, none deployed)

| File | Size | SHA-256 |
|---|---|---|
| `build/dev7/RetroHatchDev.opk` (reproducible: two builds, same hash) | 487,424 | `5b5eea19cd1cd0b585ab857f3ae2af81bba480608f0dda5fbd4d2848d13b2b0c` |
| `build/rh_get_arm` (static HTTPS test tool) | 603,628 | `34b9b78ccd442f00f883e360a1d7ceebd50c05f0447bfc0a39ad6e42b860888e` |
| `platforms/nano/ui/ca-bundle.crt` (121 Mozilla roots from Ubuntu `ca-certificates`, Sep 2026; shipped in the OPK as `certs/ca-bundle.crt`) | 182,140 | `7975117e54f05f0ed1e1e767efd1f6827d662d720282ad4a360eecc636958de8` |
| `build/dev-catalog/bundled.pkg` (serial 1: RH Probe 1.0.0; inside the OPK) | 1,499 | `9e4e6cdf70fd659bd6fefb66cea780e1677e9c163e22342994abd977dbe429ed` |
| served by the PC: `index-2.json(.sig)` serial 2 (RH Probe 1.1.0 + a non-allowlisted app), `gh/…/rhprobe_funkey-s.opk` v1.0.0 (`2cb430f6…`) and v1.1.0 (`abad12c3…`) | | |
| Production candidate (scratch, NOT for deployment): `build/dev7/RetroHatch.opk` has zero network/crypto symbols | 126,976 | `bb9836e6…` |

## Writes this test makes on the Nano (all DEV scope, FAT is still flagged dirty and accepted)

1. Back up the current DEV OPK (`f6cfff4d…`, already saved under `build/backup/`), then replace `/mnt/Applications/RetroHatchDev.opk` (hash-checked `.new` -> rename, as in 5C-3).
2. Create in `/mnt/FunKey/.retrohatch-dev/`: `extra-ca.crt` (the PC test CA), `mirror.txt`, `catalog-url.txt`. Move the old `cache/` aside (`cache.pre7/`) so the download is a real one.
3. The app itself creates `catalog.state`, `catalog.pkg`, `cache/<sha>.opk`, and installs/updates/uninstalls RH Probe through the existing engine.
4. Cleanup at the end (separate yes/no): remove the three files, `catalog.*`, restore `cache.pre7`.

## Procedure

**A. Preflight (read-only)**: IP, battery >= 40 %, boot_id, `/mnt` rw, dmesg known lines, no retrohatch process, `/etc/ssl/certs` empty (expected), device date correct (TLS needs it; a wrong date shows "Certificate date invalid").

**B. Tool test from RAM (before touching the DEV app)**: PC runs `python3 tools/dev_server.py --host <PC IP>` (WSL or Windows with `openssl`); copy `rh_get_arm`, `ca-bundle.crt`, the server's `ca.pem` to `/tmp/rhv`; on the Nano:
`./rh_get_arm --ca ca-bundle.crt --extra-ca ca.pem --max 300000 https://<PC IP>:8443/catalog/index.json /tmp/rhv/i.json` -> `OK 2445`; the same against `https://github.com/` is NOT run (no real downloads here). Also with `--ca ca-bundle.crt` only (no extra CA) -> `FAIL 3 Certificate not trusted` (proves verification is on). Record time (parsing 121 roots + handshake) and `MemFree`.

**C. Deploy the DEV OPK + the three config files** (writes above).

**D. UI walk-through (you press the buttons, I verify over SSH after each step)**:
1. Settings > Catalog Status: "Signed, bundled / Verified / Serial 1 / 1 app".
2. Discover > RH Probe: bar **Download** -> A, Download: progress, "Downloaded". Check `cache/2cb430f6….opk` hash. Bar becomes **Install** -> install -> Apps drawer has RH Probe 1.0.0.
3. Settings > Catalog Status > A: "Catalog updated: serial 2, 2 apps". Updates shows RH Probe 1.1.0; Download, then Update; check `abad12c3…` and `installed.tsv`.
4. Discover shows "Other Pad (test)": the bar says "Not allowed in DEV" (signed but not on the DEV allowlist).
5. Uninstall RH Probe.
6. Tamper round (I switch `variant.txt` on the PC; you press refresh/download each time): `tampered` -> "Catalog signature check failed"; `stale`/`fork` -> "older than one already accepted"; `junk`/`404`/`reset` -> clean error; `wrong` bytes -> "SHA-256 mismatch: file rejected", `trunc` -> "cut short"; B during a download cancels. After each: cache and `catalog.state` unchanged, no `.part/.dl/.new`.
7. Offline: stop the server (or Wi-Fi off): Catalog Status still shows the cached serial 2; refresh/download say "No internet connection"; Install from the existing cache still works.

**E. Post-checks**: boot_id/uptime, dmesg, `/mnt` rw, production OPK `b75332e6…` unchanged, `RetroHatch.opk`/TaraFi untouched, battery. Then ask about cleanup.

Abort on: crash/SIGSEGV, new storage errors, `/mnt` read-only, battery < 25 %, reboot.

Expected numbers: CA bundle parse + handshake on the Cortex-A7 well under 2 s; download of 4 KB trivial; the catalog 2.4 KB. Peak RAM: token buffer 160 KiB + TLS ~60 KiB + roots ~0.5 MiB.

## Remaining blockers before a public beta

1. **Catalog address**: `RH_CATALOG_BASE_URL` is a placeholder (`https://retrohatch.github.io/catalog/`). Needs the real GitHub Pages repo and a deploy workflow (static `index.json` + `index.json.sig` from `trust.py build/sign`).
2. **Production key ceremony** (you): generate offline, put the public half in `trusted_keys_prod.h`, back it up. Until then the production build verifies nothing (by design).
3. **First real app (kishmish-nano)**: exact-artifact download, SHA-256/size, license note (MIT in repo metadata; check the file), OPK inspection (`artifact_verify.py --inspect`), Nano hardware test of that exact file, then a hand-written catalog entry + approval.
4. **Production build wiring**: production `rh_ui_main.c` still reads the local catalog directory and has no network. Making production use the signed catalog is a small change (same `refresh()` + prod key) but it must wait for 1 to 3. The DEV allowlist (`rhprobe` only) must become "any approved signed entry" by removing `ALLOWED` in `rh_ops.c`; the signed catalog's approval gate then is the only gate.
5. **Real GitHub test**: download from `github.com/.../releases/download/...` (redirect to `release-assets.githubusercontent.com`): verify the chain against the shipped bundle on the device and the redirect handling once, before release.
6. Deleting all local state resets rollback protection (documented). A minimum-serial constant per release closes it for fresh installs.
7. The CA bundle is a snapshot; roots rotate. Ship a fresh bundle with each release.
8. Wi-Fi setup stays in the Connectivity app; RetroHatch shows "No internet connection" when it cannot connect.
9. Real RG Nano SD: the dirty-FAT flag stays unrepaired on this card; recommend `fsck` for beta testers' cards.
