# Monocypher (vendored, unmodified)

- Version: **4.0.3** (release tag `4.0.3`)
- Source: https://monocypher.org/download/monocypher-4.0.3.tar.gz (also https://github.com/LoupVaillant/Monocypher/releases/tag/4.0.3)
- Tarball SHA-512 (matches the `.sha512` published next to it):
  `40904ada5c7ee4f7741733e38b69a30a4b0561cbffba5ffe7c2dce16136d540251ec0d9056ff606510d3b5b708fb8a40db7e0870d4a0b2dc17ba2bfb880f8965`
- Tarball SHA-256 (computed here, for convenience): `8cc9bc341a66249016db9bd70e9142d8d0aef9945973744b1ac05dbc55d8ee66`
- Cross-check: the four source files below are byte-identical to `raw.githubusercontent.com/LoupVaillant/Monocypher/4.0.3/src/...`
  except line 1 (`__git__` in git, `4.0.3` in the release tarball).
- Licence: dual 2-clause BSD / CC-0 (`LICENCE.md`). Authors: `AUTHORS.md`.
- Files are copied verbatim; do not edit. RetroHatch uses only `crypto_ed25519_check()` (standard Ed25519 with SHA-512, RFC 8032).
  The default BLAKE2b EdDSA verifier (`crypto_eddsa_check`) is never called by RetroHatch code.

| File | SHA-256 |
|---|---|
| monocypher.c | 57eb914fc88136119bd41655cccb8c250048bf54d470540625186f8ab16f64be |
| monocypher.h | c494da712122da7ff679fdcf318a5317e84972b6c950fe9d896212947797facd |
| monocypher-ed25519.c | 60fce3578fb00b00da96490653d993c4cb427b1e1be38183285c66e04d22cc18 |
| monocypher-ed25519.h | abc4fad381879f5c29176ebe014b9189956b3dfe0a3e36459b6990bc57212380 |
| LICENCE.md | 5f8360e4c06ddcc584bdb4b210c6af824c4bb301e6a9a521869b6d90795ca4b3 |
| AUTHORS.md | 75a4d04559754a1016006f2c0e194cc7b459583cf9b1e2ce4ec10c74cb3de578 |

`tests/test_trust_native.py` re-checks these hashes, so any edit fails the test suite.
To upgrade: download the new tarball, verify its published checksum, copy the same files, update this page.
