# Discovery

One set of profiles (`profiles.json`), one evidence analysis (`discover.py`), three small tools. Everything is read-only metadata: nothing here downloads a whole package, installs, approves, signs or publishes.

| Tool | What it does |
|---|---|
| `crawl.py` | The RG Nano / FunKeyOS (OPK) link-following crawl: GitHub search, README links, community sources, 4-byte `hsqs` probes. Unchanged by the Android work. |
| `search.py` | Both devices, same profile queries plus the device's repos in `sources.txt`: GitHub repository search, latest release, the real file (OPK: `hsqs`, APK: ZIP magic, an OPK inside a release ZIP: central directory), README evidence, category and tags. Reuses `crawl.py`'s guarded fetch, budget and User-Agent. Writes `build/discovery/candidates-<device>.json`. |
| `review.py` | The maintainer's report (`review.md`, `review.json`, `review.digest`) from those files, the two inventories and the review state. Offline. |
| `categories.py` | The one category vocabulary: `games`, `emulators`, `ports`, `utilities`, `media`, `themes-launchers` (one primary group per app, optional tags). `--apply` fills missing `group`/`tags` in `candidates/inventory*.json`. |

```
python discovery/search.py --device all --max-req 120      # unauthenticated: ~60 API calls an hour, 10 searches a minute; set GITHUB_TOKEN for more
python discovery/review.py                                 # build/discovery/review.md
python discovery/review.py --update-state                  # also record first/last seen, so reported leads stop being "new"
```

## What a candidate is
A repository with a latest release, judged on what it says and what is really there. **A file name that mentions a device proves nothing**: compatibility is `claimed` only when a sentence in the project's own description, topics, release notes or README says the device is supported, and is never `tested` here. APK identity (package, minSdk, ABIs, signer) is read later from the file by `tools/apk_inspect.py` for the leads a person picks.

Flags: `abandoned` (no push for 18 months), `archived`, `missing-license`, `missing-description`, `fork` (folded into its parent when the parent is also found), `no-release`, `no-apk-in-release` / `no-opk-in-release`, `not-a-real-apk`, `file-unreachable`, `pre-release-only`, `debug-or-nightly-build`, `not-arm64`, `release-name-mismatch`, `list-not-an-app`, `compat-incompatible` / `compat-conflicting` / `compat-other_device`. The last group (and lists) are set aside, not shown again as candidates. For Android an APK that names another handheld is not incompatible with RG Rotate; an OPK built for another handheld may be.

## The report
Each candidate lands in exactly one group: **Updated** (a release newer than the one on record; a rejected project only returns for a real change), **New**, **Needs compatibility testing**, **Missing information**, **Previously reviewed or rejected**. Strongest first, with the source link, the download link and the reason. A person records a decision in `candidates/review-state.json`:

```json
{"schema": 1, "repos": {"owner/name": {"status": "rejected", "reason": "closed source", "reviewed": "2026-11-09"}}}
```
`status`: `reviewed` or `rejected` (both stay quiet until a new release), `testing`, `approved` (informational). The weekly workflow keeps first/last seen in its cache and edits ONE issue ("Candidate review"), and only when the set of new/updated leads changed.

## Suggesting an app
Open an issue with the **Suggest an app** form. It is a lead for a person: nothing is approved or published automatically. A maintainer can run the `discovery` workflow with `submitted_only` and the URL to inspect it.

## Catalog metadata kept apart from the signed catalog
`group`, `tags`, `released`, `added`, `long_description` and `features` are **Android-only** catalog fields (schema, Kotlin policy). The RG Nano's C verifier (`core/rh_catalog.c`) rejects unknown app fields, so `tools/trust.py` refuses to sign a production index that carries them. The Nano keeps its own `category` ids; `categories.LEGACY` maps them onto the same groups so both devices are organised identically.
