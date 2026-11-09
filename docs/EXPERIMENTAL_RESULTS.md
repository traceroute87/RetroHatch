# Experimental test-install results (owner-reported, RG Nano, FunKey OS DrUm78, via RetroHatch DEV)

Not approvals. A "works" here means the owner installed it with the experimental DEV installer, launched it and played it. Nothing in this file enters `catalog/`, `approvals.json` or any signed index; a real catalog entry still needs a hash, hardware evidence for that exact file, and a human approval.

## How to report
Send one line per app, any time, in this form (the name as shown in RetroHatch):

`<name>: works | issues | fails - <short note>`

Examples: `Snake: works`, `DOSBox Pure: issues - no sound`, `Dune2: fails - black screen, exits to menu`, `Clock App: download failed - HTTP 403`.
"fails" covers install errors (copy the on-screen message), crashes and apps that never start. I append each line below with the date and the file's SHA-256 (from `installed.tsv`). To see what is currently installed: RetroHatch > Installed (rows tagged UNVERIFIED), or ask me to read `/mnt/FunKey/.retrohatch-dev/installed.tsv`.

## Results
| Date | App | Package | SHA-256 (installed file) | Result | Note |
|---|---|---|---|---|---|
| 2026-11-07 | Znax | direct OPK (github.com/joyrider3774/znax_funkey v1.0) | `774c2a33...b6705` | works | launched, played, exited cleanly; wrote its own saves |
| 2026-11-07 | Rubido | direct OPK (github.com/joyrider3774/rubido_funkey v1.0) | `bbd02cca...a9eef6` | works | launched and exited cleanly |
| 2026-11-07 | 2048 | OPK inside ZIP (github.com/joyrider3774/32blit_funkey v1.0) | `33e13cf1...97664` | works | ZIP member matched upstream byte for byte; launched and exited cleanly |
| 2026-11-07 | 2048 (2nd launch) | same file as above | `33e13cf1...97664` | unconfirmed incident (not a proven defect) | the Nano stopped responding to its buttons while 2048 was open (screen frozen on its menu); a reboot fixed it. Not reproduced, cause not investigated further. Logged only so a repeat can be recognised |
| 2026-11-07 | NanoCraft | OPK inside ZIP (github.com/DankMiimer/nanocraft v1.0.13) | see `installed.tsv` | fails: opens and closes | not a crash. The OPK is only a launcher; its own log (`/mnt/FunKey/nanocraft/run.log`) says: "NanoCraft's runtime is missing. Extract the release payload into /mnt/FunKey/nanocraft/ - it should contain: ninecraft runtime/ gl/ mesa/ egl-wrap/ lib/". RetroHatch extracts only the OPK from a ZIP, so the rest of the ZIP (and your own Minecraft PE APK) must be copied by hand. Same limit as the launcher-stub apps already greyed out |
