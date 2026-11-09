**What "verified" means here.** A real APK served by the project's own repository, an official developer server, or an official package repository (F-Droid / IzzyOnDroid), whose package id, minSdk, ABIs and licence were read, and whose file answered a range read as a ZIP. It is **not** a device test and **not** an approval. Index-sourced rows (F-Droid, IzzyOnDroid) carry their manifest in the index; 60 of them were spot-checked by range read. Recompa / Obtainium / Retro Handhelds / Retro Game Corps rows are third-party leads: their files were re-resolved from the upstream release and their manifests read from the remote APK (central directory + `AndroidManifest.xml` by Range requests, nothing downloaded whole; the reader was cross-checked against `aapt2` on two APKs).

**Trust-policy changes needed before any external-source candidate could enter the signed catalog (NOT applied; production rules are unchanged).**
1. `CatalogPolicy.releaseOk` / `tools/trust.py` accept only a GitHub release download of the entry's own repository. To admit APKs from F-Droid / IzzyOnDroid, add a per-entry `download_host` that the signed index pins (https://f-droid.org/repo/, https://apt.izzysoft.de/fdroid/repo/) while the artifact's `sha256` and `signer_sha256` stay mandatory; the hash pin keeps integrity independent of the host.
2. Official developer servers (buildbot.libretro.com, ppsspp.org, downloads.duckstation.org) need the same per-entry pinned host plus an approval that records the official page it came from (today an approval's `release` must be a GitHub tag URL).
3. GitLab and Codeberg need their own release-download URL patterns in `releaseOk`.
4. Rolling tags (Vita3K `continuous`, nightlies) must be pinned by SHA-256 and re-signed per build, or stay external.
5. A ZIP that contains APKs (Snes9x EX+ pre-release) cannot be installed by the PackageInstaller flow: external listing only.
6. Paid, store-only or licence-restricted software (DuckStation CC-BY-NC-ND, ES-DE, DraStic, Redream, Pizza Boy) needs an `external listing` entry kind that carries a store URL and **no** download URL, hash or install button.
7. Android-only display fields (`group`, `tags`, `released`, `added`, `long_description`, `features`) still cannot go into a production index while the Nano verifier rejects unknown app fields.

**Coverage gaps and limits.**
- Only structured, public indexes were imported. Closed-source, paid and Google-Play-only apps appear only through the named seed list and the guides, so they are under-represented; third-party APK mirrors (APKPure, Uptodown, ...) were deliberately not used.
- Relevance is keyword- and category-based over the indexes (reasons are recorded per candidate). F-Droid's own categories are coarse, so games/utilities/media are a precision-over-recall selection, not an exhaustive list.
- Obtainium's community directory holds about 480 configurations; most are general-purpose apps outside this scope.
- Licences for GitHub-hosted leads are read from the repository page (SPDX label as shown by GitHub); a repository with none shown is `needs verification`, not assumed free.
- Recompa lists community forks. Each fork is a separate package id and is flagged `fork-or-community-port`; they need the user's own original game files. Its device reports come from other phones and are shown only as signal, never as RG Rotate evidence.
- Compatibility: nothing was run on an RG Rotate. `curated-for-rotate` means Retro Handhelds list the app in their Rotate collection; `manifest-installable` means minSdk <= 31 and arm64 (or pure Java).
- GitHub and CDN requests were unauthenticated and rate-limited; leads that did not resolve before the time limit are flagged and not counted.
