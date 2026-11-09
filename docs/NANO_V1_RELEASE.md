# RG Nano V1: shortest path to shippable (2026-11-06)

Scope: finish the existing installer for ONE hardware-verified app, then freeze. No UI work, no discovery, no new apps. Everything below reuses code that already exists and passes its offline tests.

## Session 4: experimental test installs of the candidates (DEV only; see `docs/EXPERIMENTAL_INSTALL.md`)
**Update 2026-11-07:** deployed and hardware-tested (`docs/HARDWARE_TEST_10.md`). The seven GitLab-only apps (HTTP 403, no other public OPK) were then hidden from the browser through `hidden` in `candidates/inventory.json`: it now lists **123** candidates, **95** with Test Install (the 28 read-only ones are unchanged). The numbers below are the original 130 / 102.

Implemented and host-tested. 102 of the 130 candidates get a Test Install (49 direct OPK, 53 inside a ZIP); 28 stay read-only (19 source only, 5 firmware/system changes, 2 launcher stubs, 2 SDL Retro cores that are not OPKs). Nothing approves, signs or publishes anything; the production OPK has none of the code. Staged for review: `build/dev-exp/RetroHatchDev.opk` (528,384 B, sha256 `5b56f29d529d380fcb0d3d71d0ca144851eff4dd1d242ed806de2a34a4f5a3d3`, two builds identical).

**Deployment and acceptance plan (one session, needs the owner's go; DEV OPK only, the existing busy-target preflight, backups already in `build/backup/2026-11-06/`):**
1. Preflight (battery >= 25 %, no `retrohatch` process, `RetroHatchDev.opk` not mounted); replace `RetroHatchDev.opk` via hash-checked `.new` + rename. Nothing else is written.
2. Owner opens RetroHatch DEV > Discover: 130 candidates listed; open a source-only one (grey reason, A does nothing) and a firmware one (GMenu2X).
3. Pick 3 candidates: a direct OPK (e.g. Znax), a ZIP-wrapped one (e.g. one 32blit game), a wiki-hosted one (e.g. Dinothawr). For each: Test Install, read the UNVERIFIED warning, Cancel once (nothing downloaded), then Download anyway; confirm over SSH that only `.retrohatch-dev/cache/x-<id>.opk` exists and `/mnt/Applications` is unchanged; then Install; the file appears, `installed.tsv` has an `x-<id>` line; launch it and report whether it works; exit.
4. Cancel a download with B (use the largest, e.g. a 20 MB wiki OPK so there is time); confirm no `.part`/`.zip` left. Retry completes.
5. Try one that should fail (a GitLab file-page candidate such as Clock App): the failure text is shown and nothing is kept.
6. Uninstall all three from the Installed list; files gone, `installed.tsv` clean, unrelated OPKs, TaraFi, production `RetroHatch.opk` and Kishmish save data untouched; read-only SSH post-checks (processes, mounts, dmesg, hashes).
7. Report per candidate: works / fails / error text. Decide afterwards what, if anything, deserves a real catalog entry (that path is unchanged and still needs hardware evidence, a hash and approval).

## Session 2 results (2026-11-06): DEV Kishmish test prepared (outcome: see Session 3 below)

**Why Source and Compatibility showed FAIL (root cause: expected, not a defect in the app).** `tools/artifact_verify.py` computes `source` as `status == "available" AND release URL under the source repo`. The entry is `unavailable` by design until hardware evidence exists, so `source` fails on status; the URL itself IS under `https://github.com/Alialhashemi23/kishmish-nano/` (checked). `compat` fails because `level` is `untested` with 0 evidence records for the sha256. Both flip to pass only after the hardware test and a human edit. No incompatibility or security issue was found, so no STOP.

**Evidence gathered today (all passive, nothing run):**
| Check | Result |
|---|---|
| Exact file | Fresh download from `github.com/.../v0.1.0/kishmish-nano.opk`: 692,224 B, SHA-256 `3dfa9fa77242d46743611c5f281fca0e3df40a481b86e857dac13c932abae2f9` = catalog = GitHub asset digest |
| Licence | GitHub API `MIT`; `licenses/LICENSE` inside the OPK is "MIT License, Copyright (c) 2026 Alialhashemi23"; SDL 1.2 (LGPL-2.1) and musl notices ship in the OPK |
| Release | `v0.1.0` not draft, not prerelease; repo not fork, not archived |
| Package (`--inspect`, unsquashfs) | `.funkey-s.desktop` present, ARM binary + bundled musl loader + SDL + 3 WAV + licenses; `launch.sh` read in full: only `cd`, `mkdir -p $HOME/.kishmish-nano`, writes `boot.log` there, runs the bundled loader. No network, no `/etc`, no `system` |
| Real GitHub download path | The project's own HTTPS client (`build/rh_get_asan`) with the shipped `ca-bundle.crt` downloaded the real asset through the real 302 to `release-assets.githubusercontent.com`: `OK 692224`, hash matches. Current redirect `Location` is 917 B (limit 1100), path 873 B (limit 1024): fits, with about 180 B margin |
| TLS chain | `github.com` (Sectigo E46) and `release-assets.githubusercontent.com` (ISRG Root X1) both verify against the shipped bundle |

**Code changes (2 small, no installer rewrite):**
1. `ui/rh_ops.c`: one more row in the DEV-only `ALLOWED` list: `kishmish-nano` + `kishmish-nano_funkey-s.opk`. Production still has no list.
2. `tools/make_dev_catalog.py`: additive `kishmish_doc()` + `index-3`/`catalog-3.pkg` (serial 3 = RH Probe 1.1.0 + the real Kishmish entry with its real GitHub URL, signed with the DEV key). Its evidence note reads "DEV FIXTURE ... NOT production evidence." `bundled.pkg` and `index-1/2` are byte-identical to before (`9e4e6cdf...`, `8a46be94...`). `catalog/apps/kishmish-nano.json` is NOT modified.

Tests after the change: `make test` 152, `prod-test` 442, `ops-test` 441, `test_signed_flow.py` DEV 197 / PRODUCTION 205, all 0 failed. `build/dev-catalog-k/index-3.json` verifies with the DEV public key (serial 3, 2 apps).

**Staged on the PC (not deployed):**
| File | Size | SHA-256 |
|---|---|---|
| `build/dev-k/RetroHatchDev.opk` (two builds, same hash) | 499,712 | `cebab59f1e47bcfb746fb0448219c44bff616055bd8035f168ac96d7c529940c` |
| `build/dev-catalog-k/catalog-3.pkg` | | `28ff49da75da5689db699cbc0d19070cf319f4831bf0c1fd074e3dd7cebdbf25` |

**Isolation DEV vs production.** `rh_ops_init` accepts only `.retrohatch-dev` in DEV and only `.retrohatch` in production, and DEV refuses the production dir explicitly (`prod-test`). The DEV OPK embeds only the DEV public key; the production OPK only the production key. On the device the two state dirs are separate (`.retrohatch-dev`: serial-1 catalog.state, rhprobe 1.1.0 installed, cache of two probe files; `.retrohatch`: empty `cache/` and `backup/`).

**Device health (read-only SSH to 192.168.1.197, 21:31 UTC):** battery 88 % discharging; `/mnt` vfat rw, 117.5 GB free; wlan0 up; boot 2 min earlier; only the firmware's own `opkrun`/`native_launch` (connectivity app, `/opk` = `connectivity_funkey-s.opk`), no `retrohatch` process; no loop device backs RetroHatch*.opk; dmesg shows only the Wi-Fi association. `MemFree` 1.6 MB with the page cache full (normal; same as earlier sessions).

**Device baseline (unchanged so far):** `RetroHatch.opk` 520,192 B `2b0f064d2725048720c2715edd98629ee7c49810c585b1a1f2406e8a284c8d6a` (note: HARDWARE_TEST_8 recorded `6b5e997f...`; a later icon build with the same size was deployed, mtime Nov 5 21:34, so the doc is stale, the device is unchanged); `RetroHatchDev.opk` `5b5eea19...` (HARDWARE_TEST_7 build, which was deployed but its walk-through never ran: no `catalog.pkg`, `mirror.txt` etc. exist); TaraFi data in `.tarafi` is live (index and log updated at 21:29, so it may still be running/just ran; the test does not touch it). Backups on the PC in `build/backup/2026-11-06/`: `RetroHatch.opk`, `RetroHatchDev.opk`, `retrohatch-state.tar` (both state dirs), hashes verified equal to the device.

### DEV hardware test: exact plan (waiting for your approval; nothing below has run)
Writes to the Nano, all DEV scope: (a) replace `/mnt/Applications/RetroHatchDev.opk` (`5b5eea19` -> `cebab59f`, `.new` hash-checked then rename, after the busy preflight); (b) create `/mnt/FunKey/.retrohatch-dev/catalog.pkg` (= `catalog-3.pkg`; the app verifies signature, policy and rollback before showing anything); (c) the app downloads Kishmish to `.retrohatch-dev/cache/`, installs `/mnt/Applications/kishmish-nano_funkey-s.opk`, writes `installed.tsv`; Kishmish itself creates `/mnt/FunKey/.kishmish-nano/`. Not touched: `RetroHatch.opk`, TaraFi, `.retrohatch`, firmware, the other OPKs.

The catalog arrives as a file because the real Pages catalog does not exist yet. The download uses the real GitHub URL and the shipped CA bundle (no mirror, no extra CA, no catalog-url override files), so the real redirect and certificate path are exercised.

Steps (you press, I verify over SSH after each):
1. Preflight, deploy DEV OPK, copy catalog.pkg. Open RetroHatch DEV: Catalog Status shows Verified, serial 3, 2 apps.
2. Discover > Kishmish Nano: details show MIT, 0.1.0, 692,224 B. Press Download; **B once mid-download to cancel** (recovery check on a real network failure): expect "cancel" message, no `.part`/`.dl` residue in `cache/`, nothing installed.
3. Download again to the end: `cache/3dfa9fa7....opk` has the right size and hash. Bar becomes Install.
4. Install: `/mnt/Applications/kishmish-nano_funkey-s.opk` hash `3dfa9fa7...`, `installed.tsv` has the line, no `journal`, no `*.new`; the details page and Installed list show it; a second Install is refused.
5. Quit RetroHatch, launch Kishmish from the Apps drawer: icon, 240x240, D-pad/A/B/Start, sound, Start/Save/Quit returns to launcher, power button still works, save created in `/mnt/FunKey/.kishmish-nano/` and still there after relaunch.
6. Reopen RetroHatch: Installed state detected, no recovery prompt.
7. Uninstall: OPK gone, `installed.tsv` clean, save directory and other apps untouched.
8. Post-checks: no process/mount/loop left, dmesg clean, hashes of `RetroHatch.opk` (`2b0f064d`), `RetroHatchDev.opk` (`cebab59f`) and the other apps as in the baseline; battery.

Abort on: crash, new storage errors, `/mnt` read-only, battery < 25 %, reboot, or any busy target.

**Recovery coverage, stated honestly:** hardware covers the failed/cancelled download and the clean restart state. Crash-point recovery of the install/uninstall journal (power cut at every step) stays covered by the 152 + 441 host checks with fault injection, as in all earlier hardware tests; I do not propose cutting power on a FAT card. Say so if you want it anyway.

**Cleanup choices after the test (separate yes/no):** leave the DEV OPK `cebab59f` or restore `5b5eea19` from backup; restore `.retrohatch-dev` from `retrohatch-state.tar` (note: the app moves its rollback state to serial 3 and DEV catalogs below serial 3 are then refused as stale, which is correct behaviour).

**After a PASS (not before):** record the real result in `docs/HARDWARE_TEST_9.md`, then edit `catalog/apps/kishmish-nano.json` to `available` + `verified` + evidence (`tester`, date, sha256, note), add the approval, and continue with the Order / Release procedure below.

## Session 3 (2026-11-06): DEV hardware test of Kishmish: PARTIAL PASS (`docs/HARDWARE_TEST_9.md`)
Exact file `3dfa9fa7...` through the DEV installer on the Nano, real GitHub download:

| Step | Result |
|---|---|
| Signed DEV catalog verified (serial 3, 2 apps) | PASS |
| Download from real GitHub, size + SHA-256 | PASS |
| Install into `/mnt/Applications`, `installed.tsv` | PASS |
| Launch, play, save, normal exit (`Exit status: 0`) | PASS (owner-confirmed) |
| Installed-state detection | PASS (owner-reported) |
| Uninstall, cleanup, save data kept | PASS |
| Post-checks: no residue, process, mount; production OPK, TaraFi, other apps unchanged | PASS |
| Cancel a download (B) | **NOT TESTED** (download finished before B could be pressed) |
| Hardware recovery from a failed operation | **NOT TESTED** (crash recovery is offline-tested only; no power failure simulated) |
| Unexpected reboot between 22:09 and 23:51 | **cause UNKNOWN**; all files intact afterwards |

Kishmish is **not approved**: `catalog/apps/kishmish-nano.json` and `approvals.json` are unchanged. Two decisions are the owner's: (1) whether PASS-with-two-NOT-TESTED is enough hardware evidence to record `verified` for this sha256 (the evidence would have to say so honestly: DEV installer, DrUm78 firmware, date, tester), and (2) the reboot.

Still pending on the device (owner's go needed): restore the original `RetroHatchDev.opk` (`5b5eea19...`) and the DEV state (`catalog.pkg`, `catalog.state` serial 3; backup in `build/backup/2026-11-06/retrohatch-state.tar`). Kishmish's cache file (`3dfa9fa7...opk`) and save data stay.

**Remaining blockers for Nano V1 after this test**
1. Decision to record Kishmish as `verified` + approval record (human).
2. Production catalog not signed or published; Pages 404 (human, offline key).
3. Production OPK with the real key and the signed snapshot has no hardware test (the one acceptance test above; it also covers the real Pages catalog fetch, which the DEV test could not).
4. Uncommitted work: production key files, `ui/rh_ops.c` DEV row, `make_dev_catalog.py`, docs, an unrelated `discovery/web_probe.py` edit.
5. Optional: retry the cancel test (delete the cached file, press B at once) if you want that evidence.

## Already finished (verified in session 1, no code changed then)
| Piece | Evidence |
|---|---|
| Install / update / uninstall / recovery engine (`platforms/nano/rh_install.c`) | `make -C tests test` 152 checks, 0 failed (ASan/UBSan): journal, crash points, rollback, busy-mount refusal, denylist |
| Production wiring (`ui/rh_ops.c` production mode, state dir `/mnt/FunKey/.retrohatch`, no allowlist, signed catalog is the gate) | `make -C tests prod-test` 442 checks, `ops-test` 441 checks, `tests/test_signed_flow.py` DEV 197 + PRODUCTION 205 checks, `tests/test_prod_wiring.py` |
| Signed catalog: Ed25519 verify (Python and native C, 4056-case differential), canonical JSON, rollback state, approval/revocation gates | `test_trust.py`, `test_trust_native.py`, `test_trust_state.py` all OK |
| Production PUBLIC key installed | `catalog/production.pub` == bytes in `platforms/nano/ui/trusted_keys_prod.h` (checked). Private key: none in the repo (grep for PEM finds only the DEV TLS test keys under `build/dev-server/`, gitignored) |
| Publish pipeline | `docs/PUBLISHING.md`, `.github/workflows/publish-catalog.yml` (refuses unsigned, unapproved or rolled-back catalogs). Repo `traceroute87/RetroHatch` exists on GitHub, local `main` equals `origin/main` |
| Kishmish Nano catalog entry and static review | `docs/KISHMISH_REVIEW.md`. Re-checked today: release asset downloads, 692,224 B, SHA-256 `3dfa9fa7...2f9` equals the catalog entry, license MIT, squashfs magic OK (`tools/artifact_verify.py`) |

## Exact blockers (nothing else stands between this tree and V1)
1. **No approved app.** `catalog/approvals.json` is empty; Kishmish is `unavailable` / `untested`. A catalog with zero apps is signable but useless. Needs the hardware test (below) and your approval record.
2. **Catalog never signed or published.** Pages returns 404 for `/catalog/index.json`. Needs your offline signing step after blocker 1.
3. **Production build with the real key has no hardware test** (`HARDWARE_TEST_8` was built with zero keys). Covered by the acceptance test.
4. **Uncommitted work in the tree:** `catalog/production.pub`, `trusted_keys_prod.h`, `docs/HARDWARE_TEST_8.md`, and an unrelated `discovery/web_probe.py` edit. The workflow triggers on `catalog/production.pub`, so the key must be committed before CI can verify anything. Waiting for your go.
5. *(Non-blocking, state in release notes)* No compiled-in minimum serial, so deleting `/mnt/FunKey/.retrohatch/catalog.state` resets rollback protection (`docs/TRUST.md`, Limitation). Not built; do not build before V1.
6. **TLS library for the production release (decide before shipping).** Since 2026-11-09 `core/rh_net.c` links the firmware's static OpenSSL 1.1.1i (needed for TLS 1.3: `static.miraheze.org`; mbedTLS 2.16 stops at TLS 1.2). 1.1.1i is end-of-life and unpatched (known later fixes include CVE-2021-3712 and CVE-2022-0778, mostly denial of service from a malformed server certificate; none found that bypasses verification, not a full audit). Verification stays on and the client only talks to catalog/candidate https hosts, but a shipped production build should either move to a maintained library (mbedTLS 3.6 LTS or a current OpenSSL cross-built with the Buildroot toolchain, a bounded port of `rh_net.c`) or record this limit in the release notes. The production OPK shares this code, so the production acceptance test below also exercises the OpenSSL client; the production OPK is about 0.9 MB larger because of it.

Not blockers: ZIP-wrapped candidates (stay read-only), icons, licence gaps on the other 129 candidates, extra apps.

## Production catalog: minimal
Exactly one app: `kishmish-nano` (MIT, single author, exact file hashed, static review done). Nothing else is added for V1. A second app is optional and only after the same checklist (Znax or Rubido are next in the readiness audit). The other 129 candidates stay in the read-only snapshot, untouched.

## ONE hardware acceptance test (RG Nano, production build)
Build: production OPK from a clean `git archive` of the commit you approve, `PRODCAT` = the signed catalog snapshot, real `trusted_keys_prod.h`. Deploy with the `docs/DEPLOY_SAFETY.md` preflight (replaces the Test/Dev OPK only, never a mounted one). Battery >= 25 %, Wi-Fi on, FAT checked.

Run in this order, one session, owner on the device, read-only SSH for evidence:
1. Pre-state: record `/mnt/Applications` listing and hashes; `/mnt/FunKey/.retrohatch/` empty.
2. Open RetroHatch: Catalog Status shows the signed catalog from the bundled snapshot (signature OK, serial N).
3. Refresh over the REAL network: live Pages catalog verifies; real GitHub redirect and TLS chain succeed (this is the first time that path is tested for real).
4. Download Kishmish from the real GitHub URL: SHA-256 and size match, file lands in `cache/`, nothing installed yet.
5. Install: `/mnt/Applications/kishmish-nano_funkey-s.opk` has hash `3dfa9fa7...`, `installed.tsv` has the record, RetroHatch shows Installed.
6. Launch Kishmish from the launcher: 240x240 correct, D-pad/A/B/Start work, sound or silent without error, Save+Quit returns to launcher, save appears in `/mnt/FunKey/.kishmish-nano/` and survives relaunch, power button still works.
7. Persistence: close and reopen RetroHatch. Installed state is still shown, no recovery prompt. (Crash-point recovery is covered by the offline engine tests, not repeated on hardware.)
8. Uninstall: OPK removed, save directory and other apps untouched, `installed.tsv` record gone.
9. Post-state (read-only SSH): no `retrohatch`/`opkrun` process, no `/opk` mount, no loop backing file for the OPKs, no new `dmesg` storage errors, `/mnt/Applications` equals pre-state except RetroHatch.opk.

PASS = every line above. Any FAIL: stop, do not publish, report. Update/rollback of an installed version cannot be tested with one published app; it stays covered by offline tests until a second version exists.

On PASS, record in `catalog/apps/kishmish-nano.json`:
```
"status": "available",
"compatibility": {"level": "verified", "evidence": [{"sha256": "3dfa9fa77242d46743611c5f281fca0e3df40a481b86e857dac13c932abae2f9", "date": "<test date>", "tester": "<you>", "note": "RG Nano, funkeyos-drum78, docs/HARDWARE_TEST_9.md"}]}
```
(Order of evidence vs. signing: see "Order" below.)

## Order (chicken-and-egg resolved)
The test needs a signed catalog, and the catalog needs the test evidence. Break the loop with a staging signature, not a production one:
1. Hardware-test the exact Kishmish file on the DEV build (`docs/KISHMISH_REVIEW.md` checklist, steps 1 to 5). This is the compatibility evidence.
2. Fill in evidence + approval, then sign and publish the real catalog (you, offline).
3. Run the ONE acceptance test above against the real catalog and real URLs.
4. If it fails, revoke or unpublish (`revoked` in `approvals.json`, bump serial, re-sign).

## Release procedure (minimum, repeatable)
Per release, from a clean checkout of `main`:
1. `python tools/validate.py && python tests/test_validate.py && python tests/test_trust.py`
2. WSL: `make -C tests test prod-test ops-test native-test state-test`; then `python tests/test_signed_flow.py`, `test_trust_state.py`, `test_trust_native.py`
3. `python tools/artifact_verify.py <id> --file <downloaded.opk> --inspect` for every published app (file downloaded into its own empty directory)
4. Evidence + approval records committed (`docs/PUBLISHING.md` steps 1 to 4)
5. Offline machine with the key: `trust.py build`, `trust.py sign`, `trust.py verify` (`docs/PUBLISHING.md` step 5). Passphrase only in the environment of that terminal.
6. `python tools/make_pkg.py site/catalog/index.json build/catalog.pkg`; `PRODCAT=build/catalog.pkg sh platforms/nano/ui/build-opk.sh` twice, compare hashes
7. Commit `catalog/` and `site/catalog/`, push; workflow verifies and deploys Pages
8. Deploy OPK with the DEPLOY_SAFETY preflight; run the acceptance test (first release) or steps 2 to 5 and 8 to 9 (later releases)

## Key handling: can it be completed safely? Yes, with these checks
- Ceremony is documented (`docs/KEY_CEREMONY.md`) and the public half is already in the tree, so it has apparently been done. I cannot see where the private key lives and do not want to. **You should confirm** it is outside the repo, backed up on a second stick, and the passphrase is in a password manager. Confirm the 16-hex key id printed at keygen matches the first 16 hex of sha256 of `98ed5db6...ca18120` (`tools/trust.py verify` prints it for any signed index).
- Signing needs only: key file, passphrase env var, `trust.py sign`. CI never sees either. `.gitignore` blocks `*.pem`, `*.key`, `rh-signing*`.
- Before the first real signature, rehearse once on a throwaway key (`trust.py keygen` to a temp dir, `--pubkey` override on verify). `test_signed_flow.py` already does this on every run, so no extra work is needed.

## RG Rotate: reuse vs. separate Android adapter
**Reuse as-is:** catalog schema (`app.schema.json` already has `format: apk`, `device.schema.json` already has `android-packageinstaller` and `package_format: apk`), approvals/revocation model, `trust.py` build/sign/verify, key and signing procedure, Pages publishing + workflow, discovery and inventory tooling, `artifact_verify.py` (hash, source, license), release procedure above, the Ed25519 trust model and rollback serial.

**Needs small generalisation (host side):** `trust.py check_index` and `core/rh_catalog.c` currently require `.opk` destination names, the protected-destination denylist and the device/firmware pair `rg-nano / funkeyos-drum78`. An APK entry needs package name + minimum version code + signing-certificate SHA-256 instead of a destination file name.

**Separate Android adapter (new code, Kotlin/Java, not shared with Nano):**
- UI: native Android, not the SDL 1.2 UI.
- Verify catalog: reimplement the canonical-JSON strict parse + Ed25519 check (JDK/BouncyCastle/libsodium). Keep the same test vectors (`tests/trust_fixture`, RFC 8032) so both verifiers agree.
- Install: `PackageInstaller` session with user confirmation; Android enforces package signature continuity, so there is no custom engine, journal or mount logic. Uninstall via the system dialog.
- Download: platform HTTPS, then check size + SHA-256 + APK signing-cert fingerprint pinned in the signed entry before handing to the installer.
- Rollback state: app-private storage; the "state deleted" limitation is the same.

**Before starting Rotate:** Nano V1 acceptance test passed, catalog signed and live, key procedure confirmed, the tree committed, and a decision on whether Rotate shares the same signing key (recommended: yes, one trust root) and the same Pages catalog (recommended: yes, `devices` section already separates them).
