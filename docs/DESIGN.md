# RetroHatch design (Phase 1)

## Smallest practical architecture

- Repo is independent of TaraFi. TaraFi is only a catalog entry (`catalog/apps/tarafi.json`).
- Catalog = static JSON files, one per app / device. Build step (later) merges them into one signed `index.json` for GitHub Pages. No backend, no DB.
- Client (later): one portable C core (catalog parse, sha256, download, install plan) + thin adapters (`opk-funkeyos`, `android-packageinstaller`). UI per platform, not shared.
- Directories `core/ platforms/ discovery/` are created when first code lands, not before.

## Catalog model

- `app` -> many `artifacts`, each pinned to (device, firmware, format). No cross-platform assumptions.
- `compatibility.level`: verified | community | experimental | unsupported | untested. `untested` is a catalog-only state (never installable).
- Evidence is keyed by artifact sha256, so a new binary needs new evidence. Updates never inherit `verified`.
- `install.dest_name` is a bare filename (regex-restricted) — adapter picks the directory; catalog cannot name paths or commands.

## Trust design (to implement; not built)

- `index.json` + detached `index.json.sig` (Ed25519). Public keys embedded in client; list of 2 keys (active + backup) to allow rotation. Private key offline.
- Index carries monotonic `serial`. Client stores highest serial seen and rejects lower (rollback). **No wall-clock expiry enforcement** (Nano clock unreliable); optional `expires` only shown as a warning when the clock looks sane.
- Index carries a `revoked` list (app id + sha256). Offline Nano learns of revocations only via refresh or OPK update.
- Install gate: size match -> sha256 match -> adapter destination check -> install. Any failure = stop, keep old version.
- Sideloaded OPK on stock Nano: offered/installed only if its sha256 matches a catalog artifact; otherwise shown as "unrecognized", not installed by RetroHatch.
- Prefer linking upstream release assets; sha256 pin defends against edited releases.

## Contradictions / risks found

1. **Ed25519 on Nano.** mbedTLS (used by TaraFi) has no Ed25519. Need a small vendored lib (monocypher or tweetnacl, public domain, ~1 file) or libsodium. Decision needed before Phase 2 signing code; check which mbedTLS version TaraFi vendors.
2. **Nano clock** wrong -> expiry unusable; replaced by serial + rollback store (above). Weakness: first run with no stored serial accepts the embedded snapshot's serial as baseline.
3. **Offline revocation gap** is inherent; document it.
4. **OPK install semantics unconfirmed**: launcher refresh, mounted-OPK overwrite, FAT rename atomicity. Engine design depends on a read-only device probe.
5. **Self-update** of RetroHatch's own (mounted) OPK needs a separate flow; out of scope until the engine works.
6. **TaraFi entry has no verified facts beyond name/source/desktop entry.** No tag/release, no LICENSE in repo, build architecture not recorded, no test evidence. Entry is `unavailable`/`untested` until a release is published and hashed. Record the license before publishing anything.
7. Brief says "verified metadata only": developer field uses the GitHub owner `traceroute87` (from git remote) — confirm preferred display name.
8. Single signing-key holder = single point of failure; document recovery in a SECURITY.md before public release.

## Next milestone

Phase 2 start: read-only probe of Nano OPK behaviour (needs explicit approval + device access), then host-side OPK inspector (squashfs listing, desktop entry, path-traversal check, sha256/size).
