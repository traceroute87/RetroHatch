# Publishing the signed catalog (GitHub Pages + GitHub Releases)

Nothing is published unless a human approved it **and** you signed it offline. Pages only hosts what you commit; the workflow `.github/workflows/publish-catalog.yml` refuses to deploy a catalog that does not verify.

```
site/                       static site served at https://traceroute87.github.io/RetroHatch/
  catalog/index.json        canonical signed index (built by trust.py; only approved + hardware-verified artifacts)
  catalog/index.json.sig    Ed25519 signature (made offline)
```
App files are **not** hosted by us: the signed index points at the upstream project's GitHub Release asset
(`https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`); the device checks the size and SHA-256 recorded in the signed entry.

## One-time setup
1. Create the repository `traceroute87/RetroHatch` (if you name it differently, change `RH_CATALOG_BASE_URL` in `ui/rh_source.h`) and push this project (you do this; I do not push).
2. Settings, Pages, **Source = GitHub Actions**.
3. Do the key ceremony (`docs/KEY_CEREMONY.md`), send me the public key, I install it with `tools/set_prod_key.py` and you commit `catalog/production.pub`.

## Adding or updating an app (every time)
1. `catalog/apps/<id>.json` entry written by hand (discovery only finds candidates). Source repo, license, exact release asset URL, size, SHA-256.
2. `python tools/artifact_verify.py <id> --file <downloaded.opk> --inspect` (integrity, URL under the source repo, license, package).
3. **Hardware test of that exact file** on the RG Nano. Then set `status: available`, `compatibility.level: verified` with `evidence` (sha256 of the tested file, date, tester). Anything less is never published.
4. Add the approval record to `catalog/approvals.json` (`app, device, firmware, sha256, size, release tag URL, approved_by, date`).
5. On the offline machine with the key (serial increases automatically):
   ```
   python tools\trust.py build --out site\catalog\index.json --expires 2027-12-31
   python tools\trust.py sign site\catalog\index.json --key E:\retrohatch-keys\rh-signing.pem
   python tools\trust.py verify site\catalog\index.json
   ```
6. Commit `catalog/` and `site/catalog/`, push. The workflow validates, verifies the signature and approvals, checks the serial did not go back compared with the live catalog, then deploys.
7. Revoking: add the app and sha256 to `revoked` in `catalog/approvals.json`, rebuild, sign, push.

## Bundling a snapshot in the OPK (beta build)
`python tools\make_pkg.py site\catalog\index.json build\catalog.pkg` (verifies first), then build with that file as the bundled catalog.
