# Hardware test 11: TLS 1.3 downloader (OpenSSL) in the DEV build, batch-test cleanup, PokeMini UI download (RG Nano), 2026-11-09

**Result: PASS for the tested UI path (one Miraheze app). Nothing was approved, signed or published; production `RetroHatch.opk` untouched.**

## Change under test
`core/rh_net.c` uses the firmware's OpenSSL 1.1.1i (static `libssl.a`/`libcrypto.a` from the Buildroot sysroot) instead of mbedTLS 2.16, which has no TLS 1.3. `static.miraheze.org` answers a TLS 1.2 hello with alert 70 (`protocol_version`). TLS 1.2 stays the minimum, 1.3 is negotiated, certificate AND host name verification stay mandatory (`SSL_VERIFY_PEER`, `SSL_set1_host` / IP check), https-only incl. redirects, same error messages. Nothing else in the download code changed.

| Item | Value |
|---|---|
| Build | `RetroHatchDev.opk`, 1,462,272 B, sha256 `04d1ea7f57dfa84a03ad5084ffe2580d8c65dc3eaea57166c23a718c5b653257` (two builds identical), `-DRH_DEV -DRH_EXPERIMENTAL`. Previous DEV OPK `5b56f29d...` (528,384 B) |
| Deployment | busy preflight (no `/opk` mount, no `retrohatch`/`opkrun`/`native_launch`, only the Bluetooth `storage.img` loop-backed), copy to `.new`, hash check, busy re-check, rename, hash verified. Battery 82 % |
| Backups | `build/backup/2026-11-08/` (previous DEV OPK, production OPK, dev state), `build/backup/2026-11-09/` (state before cleanup, file list, save-data list, `x-pokemini.opk.cache`) |

## Tests before the deployment
`test_net.py` (real TLS: good, IP, wrong host, untrusted, expired, not-yet-valid, redirects, chunked, truncation, timeouts) OK; `test_experimental.py` 458 checks, `test_zip.py` 52, `test_prod_wiring.py`, `test_signed_flow.py` (DEV 197, PRODUCTION 205) OK; DEV and production OPKs build. On the Nano (binaries run from `/tmp`, nothing deployed): direct downloads from Miraheze (PokeMini, Dinothawr) and GitHub (Znax) with size and SHA-256 equal to the catalog; the installer's `download` for Dinothawr, PokeMini, Rubido and 2048 (ZIP member) gave hashes equal to the compatibility run; a bundle with one unrelated root fails with "Certificate not trusted"; `http://` refused.

## Steps on the device
| Step | Result |
|---|---|
| GitHub downloads after the deployment, no reinstall (Rubido, Znax, 2048, throwaway state dir, then removed) | PASS: hashes equal to the compatibility run |
| Apps drawer froze for ~2 min (found while testing, not caused by this change) | Cause: firmware `sysapps_scan.sh` fingerprints every OPK with `wc -c`, and BusyBox `wc -c` reads the whole file; with 95 OPKs (1128 MB) that is ~2 min per open. Firmware not modified |
| Cleanup: 77 batch-test apps uninstalled through the uninstall engine (`rh_exp_arm uninstall`, one at a time, busy check before each) | PASS: 18 OPKs remain in `/mnt/Applications`; `installed.tsv` holds the 12 kept records (rhprobe, Znax, Rubido, 2048, NanoCraft, Funkoban, SuDokuL, TriSpace, KeyCraft, Blips, Blockdude, Rockbox). All 857 save/settings files identical before and after (only `installed.tsv` differs); all caches kept; results and 67 screenshots untouched |
| Apps drawer after the cleanup | scan runs of 7.2, 3.9, 7.3 and 4.9 s (sampled from `/proc` while the owner opened the drawer); fingerprint of 25 OPKs 4.7 s |
| PokeMini through the DEV UI: Test Install, confirm, download over TLS 1.3 from `static.miraheze.org`, install | PASS (owner-reported on screen; I did not see the screens) |
| PokeMini launched and exited | PASS (owner-reported) |
| Evidence read over SSH | `/mnt/Applications/Pokemini_funkey.opk` sha256 `f0cb12b5882e57bfb8a6fb971e1023d2bb16cc6c6ccddb2234d2003df1141c64` = the preserved copy and the compatibility run; `installed.tsv` line `x-pokemini 0 f0cb12b5... /mnt/Applications/Pokemini_funkey.opk`; cache file written by the download (same hash); no `.part`/`.new`/journal residue; boot ID unchanged since 02:20 (no reboot); `fkgpiod` and `retrofe` running; no new dmesg storage errors |

The PokeMini cache copy was set aside before the UI test (otherwise the installer would have installed from the cache without downloading). The new download is byte-identical to it, so nothing needed restoring; the temporary copy was removed and the PC copy `build/backup/2026-11-09/x-pokemini.opk.cache` kept.

## Not tested
Other Miraheze candidates through the UI (27, not retried), the UI download of a GitHub app (covered by the headless installer driver), production build on hardware, cancel and broken-link cases.

## Open issue for the production release
OpenSSL 1.1.1i is end-of-life and linked statically from the firmware sysroot. See `docs/NANO_V1_RELEASE.md`, blocker 6: move to a maintained library or record the limit in the release notes. Verification is on and unchanged, and no verification bypass was found, but this was not a full audit.

## Also found
The firmware Apps drawer scan cost grows with the total size of the OPKs, not the count of apps. Large installs (32blit apps are ~18 MB each) will bring the freeze back; the real fix is a firmware script change, which is out of scope here.
