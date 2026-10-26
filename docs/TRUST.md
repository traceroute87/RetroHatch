# Trusted catalog (Phase 6C-1, host side only)

Not connected to the Nano UI. Nothing here downloads, installs or runs an app.

## Pipeline

```
discovery/discover.py      candidate report            level: discovered | claimed   (author's words)
  -> human review          write catalog/apps/<id>.json by hand, unavailable/untested
  -> tools/artifact_verify.py  local file vs entry      integrity, source URL, license, compat, destination, package
  -> hardware test         on the exact sha256         level: verified + evidence[sha256] in the entry
  -> human approval        add a record to catalog/approvals.json (the only way into the index)
  -> tools/trust.py build  index.json                  ONLY approved + verified + available artifacts
  -> tools/trust.py sign   index.json.sig              offline machine, key outside the repo
  -> publish index.json + index.json.sig (GitHub Pages / release asset)
```

Discovery never writes `catalog/`, and `build` ignores anything not in `approvals.json`.

| Stage | Meaning | Where recorded |
|---|---|---|
| Discovered | found on GitHub | `build/discovery/*` only |
| Claimed compatible | repo text says it supports the device | discovery report only |
| Hardware tested | ran on a real Nano; evidence tied to the artifact sha256 | `compatibility.level: verified` + `evidence` |
| Verified and approved | a human accepted this exact sha256 | `catalog/approvals.json` |

Only the last row, with the three before it satisfied, reaches the signed index. `community`/`experimental` entries are never published (`PUBLISH_LEVELS`).

## Separate trust decisions (do not conflate)

1. **Integrity**: bytes equal catalog size + sha256. A file matching its own hash proves nothing about the publisher.
2. **Source identity**: the artifact URL must be `https://github.com/<owner>/<repo>/releases/download/<tag>/<file>` of the entry's own `source`, and the approval's `release` must be the matching tag URL. This checks URL shape only. The reviewer still confirms the repo/release is the real author's. GitHub accounts can be taken over.
3. **Compatibility**: `verified` plus evidence for exactly these bytes. A new binary needs new evidence.
4. **Catalog approval**: the approval record. The signature then says only "the key holder published this index".

`check_index` re-runs every gate (no approval, wrong URL, unverified level, unavailable status, revoked hash, duplicate or protected destination, orphan approval). `build`, `sign` and `verify` all call it, so a buggy builder or a valid signature cannot bypass them.

## Approval record (`catalog/approvals.json`)

```json
{"schema": 1, "revoked": [],
 "approvals": [{"app": "id", "device": "rg-nano", "firmware": "funkeyos-drum78", "sha256": "<64 hex>", "size": 123,
                "release": "https://github.com/o/r/releases/tag/v1.0.0", "approved_by": "name", "date": "YYYY-MM-DD"}]}
```
Revoke by adding `{"app", "sha256", "reason"}` to `revoked`; the approval is dropped and the hash stays in the index.

## Index and signature

- `index.json`: canonical JSON (sorted keys, no whitespace, ASCII, no floats), keys `format, serial, generated, devices, apps, approvals, revoked` (+ optional `expires`). No key material inside; a catalog can never introduce keys.
- `index.json.sig`: `{"alg":"ed25519","key_id":<first 16 hex of sha256(pubkey)>,"sig":<base64 64 bytes>,"v":1}` over the exact bytes of `index.json`. Ed25519 is deterministic (RFC 8032): same input, same signature.
- Verify order, fail closed on any error: key configured -> signature document -> key id known -> Ed25519 verify over raw bytes -> strict parse (duplicate keys, NaN, floats rejected) -> bytes must equal canonical form -> policy gates -> rollback check.
- Crypto: Python `cryptography` (OpenSSL). No custom Ed25519 code. Host tools need `pip install cryptography jsonschema`.

## Clock, offline, rollback

- The Nano clock is never trusted for a decision. `serial` (integer, must increase) plus the stored `{serial, sha256}` of the newest accepted index defeat rollback. Same serial with different content is rejected.
- `expires` is optional and only yields a warning when the clock looks sane (year >= 2026). A wrong clock cannot reject or accept anything.
- An offline device keeps using the last accepted index and cannot learn of revocations until it refreshes (inherent; an index may be arbitrarily stale and still valid). First run has no stored serial and accepts any validly signed index (embedded snapshot); keep the shipped snapshot current.

## Keys

- `TRUSTED_KEYS` in `tools/trust.py` is empty on purpose: **verify fails closed ("no trusted key configured") until the production public key is added.** Generate it on an offline machine:
  `RH_KEY_PASSPHRASE=... python tools/trust.py keygen --out /secure/offline/rh-signing.pem` (refuses paths inside the repo; refuses to overwrite). Commit only the printed public key hex.
- Keep the private key off the repo, off CI, encrypted (passphrase env var), with an offline backup. `.gitignore` also blocks `*.pem`, `*.key`, `rh-signing*`.
- Single key holder is a single point of failure: keep the backup in a second place.
- **Rotation**: (1) generate the new key; (2) ship a client/verifier release trusting `[old, new]`; (3) after clients updated, sign with new; (4) release trusting `[new]` only. Keys change only through a client update, never through the catalog. Compromise: same flow, but revoke the old key at step 2 and accept that devices that never update remain exposed.
- `tests/trust_fixture/signed/` is an example signed with a throwaway key whose private half was deleted; its public key is in `PUBKEY.hex`. It is not a production key.

## Commands

```
python tools/artifact_verify.py ID --file X.opk [--inspect]       # --inspect lists the squashfs via unsquashfs -ll; never mounts or runs it
python tools/trust.py build [--serial N] [--expires YYYY-MM-DD]   # serial defaults to previous + 1
python tools/trust.py sign build/index.json --key /secure/rh-signing.pem
python tools/trust.py verify build/index.json --pubkey <hex> [--state state.json]
python tests/test_trust.py
```

## Phase 6C-2: native verifier (done, not connected to the UI or deployed)

- `core/rh_catalog.{h,c}`: `rh_catalog_verify()`, a pure function (no files, network or clock). Crypto is **Monocypher 4.0.3** `crypto_ed25519_check()` (standard Ed25519/SHA-512, RFC 8032), vendored unmodified in `vendor/monocypher/` (`PROVENANCE.md`: URL, SHA-512/256, licence, per-file hashes; the test fails if any file changes). The BLAKE2b `crypto_eddsa_check` is never used.
- Order: nkeys>0 -> size bounds (index <= 256 KiB, signature <= 1 KiB) -> signature document (strict, 64-byte signature, 16-hex key id) -> key id must be in the embedded list -> Ed25519 over the exact bytes -> only then the strict canonical-JSON parse -> publish gates -> rollback. Any failure returns a code and a static message; nothing is partially trusted.
- Strict parser: byte-exact canonical form (sorted keys therefore no duplicates, no whitespace, escapes exactly as `json.dumps(ensure_ascii=True)` emits them, integers only, <= 2^31-1), 8192 tokens, depth 12. Python `trust.py` enforces the same limits so a catalog the signer accepts always fits the device.
- Policy gates are a small C re-implementation of `check_index` (fields and types, release URL, approvals, `verified` + evidence, device/firmware/format, protected and duplicate destinations, revocation). It is intentionally a re-check, not a substitute: the signer already ran the full jsonschema validation. The destination denylist is a lower-case copy of `rh_install.c`; `tests/test_trust_native.py` fails if they drift.
- `TRUSTED_KEYS` stays empty: callers pass the key list, and an empty list fails closed. No production key exists.
- Rollback state `{serial, sha256}` is returned in `*next`; persisting it is the caller's job (Phase 6C-3). `expires` is returned for display only.

Tests (`make -C tests native-test`; `python tests/test_trust_native.py` needs WSL Ubuntu): RFC 8032 section 7.1 vectors (5, extracted from the RFC text and cross-checked against `cryptography`), bit-flip/truncation/S+L rejection, size and argument guards, Python-signed catalogs, modified catalog/signature, missing signature, wrong/unknown/rotated keys, device and firmware mismatch, limits, canonical-form edge cases, rollback/fork, 22 signed-but-policy-violating indexes, and a differential run of 4056 cases (2556 structural mutations of two signed indexes, 1200 re-signed byte mutations, 300 stale-signature cases) under ASan/UBSan: native never accepts what Python rejects, and they agree on every accepted index.

ARM (existing FunKey Buildroot toolchain, `sh platforms/nano/cli/build-verify-arm.sh`): CLI `build/rh_verify_arm` static, 117,640 B (91,244 B stripped, including printf/scanf for the CLI). Verifier alone (rh_catalog + sha256 + Monocypher, `-Os`, gc-sections): about 44 KB text in a minimal static binary. Memory while verifying: 160 KiB heap (8192 tokens x 20 B) plus about 12 KiB stack. Host -O2 time: about 2 ms per full verification including file IO. **Not measured on the Nano** (no deployment this phase): the F1C100s core is much slower than the host, so measure there before relying on it.

### Remaining before the UI may trust a catalog (6C-3)
1. Persist `{serial, sha256}` atomically under `/mnt/FunKey/.retrohatch/` and load it on start; decide the first-run policy.
2. Generate the production key offline, put its public half into the embedded list, and rotate by client update only.
3. Run the ARM verifier read-only on the Nano against the fixtures (tamper cases included), record real timing/RAM.
4. Wire `rh_model` to the verified index and gate the install CTA on it; keep the local DEV catalog path clearly separate.
5. Revocation of already-installed apps and index freshness UX are still open.

## Phase 6C-4: persistent rollback state (host-tested, not connected to anything)

`core/rh_catalog_state.{h,c}`, independent of the UI and of the install engine (does not include `rh_install.h`, never touches `installed.tsv`, journals, backups or OPKs). One file in a caller-supplied directory (planned: `/mnt/FunKey/.retrohatch/catalog.state`, not used yet):

```
RHCS1 <serial> <sha256 hex> <check>\n      check = first 16 hex of sha256("RHCS1 <serial> <sha256 hex>")   (99 bytes max)
```

- `rh_catalog_verify_persist()` = load state -> `rh_catalog_verify()` (prev = stored state) -> save new state. State only advances **after the catalog verified completely**; any failure writes nothing. Same index again is a no-op. A catalog that verifies but whose state cannot be saved is **not trusted** (`RH_CAT_E_STATE`).
- Absent state is a first run. Present-but-unreadable or corrupt state (wrong magic/shape/check, extra bytes, wrong type, I/O error) is **refused**, never treated as first run, and never overwritten. There is no fallback to older data: a corrupt `catalog.state` is refused even if `catalog.state.bak` is valid.
- `rh_cstate_save` also refuses to lower the serial or fork it (same serial, different hash), as defence in depth.
- Crash safety, same pattern as `rh_install.c` (tmp file, `fsync`, `rename`, `fsync` directory) plus a parked copy because FAT rename atomicity is not assumed: write `catalog.state.tmp`; park the old record as `catalog.state.bak`; rename tmp to `catalog.state`; delete `.bak`. A power cut leaves the old record, the new record, or only the parked old record (a lone valid `.bak` is recovered by `load`). A stale `.tmp` is ignored. Tested by injecting a crash or an error at every step.
- Tests: `make -C tests state-test` (every single-bit corruption of a stored record is refused; interrupted and failed writes; real failing `open`/`rename`; monotonic rule) and `python tests/test_trust_state.py` (through the CLI: repeated catalogs, rollbacks, same-serial forks, bad catalogs never advancing the state, corrupt state, crashes, engine files untouched).

### Limitation: local state is not a trust anchor

If an attacker (or a bug, a reformat, a "clean up" tool, a restored SD image) deletes the state file and its `.bak`, or the whole directory, the verifier sees a first run and accepts any validly signed catalog again, including an old one with known vulnerable or revoked entries. Rollback protection therefore only holds while the local state survives and only against attackers who cannot delete it; it does not defend against anyone with write access to the SD card. Closing this needs something outside this storage: a minimum serial compiled into each RetroHatch release (raised on every release), or a trusted clock/server. Not built; the test `limit_s3_accepted_after_delete` documents the behaviour. Also unchanged: a freshly installed device has no baseline, so its first accepted catalog is whatever validly signed index it is shown first.
