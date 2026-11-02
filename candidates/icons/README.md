# Candidate icons: redistributable only

`icon_file` in a candidate snapshot names a 32x32 PNG here, and the Nano UI draws it. A file belongs in this folder only when
`discovery/opk-metadata-evidence.json` records its redistribution status as `redistributable` (clear evidence that a licence covers
this artwork itself, with any attribution it asks for). A project's MIT or GPL licence is not assumed to cover its artwork.

Icons that are `unclear` or `restricted` are not tracked in Git, not copied into the production OPK, and not named by the snapshots; their
candidates show the package glyph. Development copies of the extracted icons stay in `build/opk-icons/` (git-ignored), with
`manifest.json` (SHA-256 per file). See `docs/ICON_LICENSE_AUDIT.md`.

`*.png` here is git-ignored: add an approved icon with `git add -f`.
