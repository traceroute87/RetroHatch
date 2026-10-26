# Production signing key: do this yourself, offline

I never generate, see or store this key. You make it once; the app only ever gets the PUBLIC half.

**What you need:** one computer that you can take offline (disconnect Wi-Fi/Ethernet), Python 3 with `pip install cryptography` done beforehand, a copy of this repository's `tools/` and `catalog/schema` folders (or the whole repo), and two USB sticks.

1. **Disconnect the computer from the network.**
2. **Make a folder on USB stick #1**, e.g. `E:\retrohatch-keys\`. It must not be inside the repository, a cloud-synced folder (OneDrive, Dropbox, Google Drive) or your Desktop.
3. **Choose a long passphrase** (5+ random words). Put it in your password manager.
4. **Generate the key** (PowerShell, from the repository folder):
   ```
   $env:RH_KEY_PASSPHRASE = "your long passphrase"
   python tools\trust.py keygen --out E:\retrohatch-keys\rh-signing.pem
   ```
   It prints the **public key (64 hex characters)** and a **key id**. The command refuses to write inside the repository and refuses to overwrite an existing key.
5. **Write down / photograph the public key hex and key id** (they are not secret).
6. **Back up:** copy `rh-signing.pem` to USB stick #2; keep the sticks in two different places. Without the key and passphrase you cannot publish updates (recovery would mean shipping a new RetroHatch with a new key).
7. **Close the terminal** (`$env:RH_KEY_PASSPHRASE` disappears with it), then reconnect the network if you like.
8. **Send me only the 64-character public key.** I run `python tools/set_prod_key.py <hex>`, which writes `catalog/production.pub` and `platforms/nano/ui/trusted_keys_prod.h`.

**Never:** commit, email, chat, upload or screenshot `rh-signing.pem` or the passphrase. The Pages workflow and I only ever see public data.

**Later, to publish a catalog** you plug in USB stick #1 and follow `docs/PUBLISHING.md` (signing takes one command with the same passphrase).

**If the key is ever lost or leaked:** stop publishing; ship a RetroHatch update that trusts a new public key (the overlap procedure is in `docs/TRUST.md`, "Keys"). Devices that never update keep trusting the old key, which is why the key must stay offline.
