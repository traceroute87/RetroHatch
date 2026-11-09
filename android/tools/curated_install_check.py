#!/usr/bin/env python3
"""One real install and uninstall of a curated catalog app on the rotate720 emulator, through RetroHatch's own UI and Android's installer: the smallest pure-Java entry of
candidates/android-curated.json (no native libraries, so the x86_64 emulator can run it). Proves the curated, signed DEV catalog entry downloads from its GitHub release, passes the
SHA-256 / package / signer checks and installs only after the user confirms. Also confirms an external listing shows no Install button.
    python -u android/tools/curated_install_check.py [fdroid|izzy]"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e as E
import nav_check as N

cur = json.loads((E.ANDROID.parent / "candidates" / "android-curated.json").read_text(encoding="utf-8"))["apps"]
KIND = sys.argv[1] if len(sys.argv) > 1 else None          # e.g. "fdroid": use the smallest entry of that source instead of the smallest overall
cands = sorted([x for x in cur if x["mode"] == "install" and (KIND is None or x["apk"].get("source_kind") == KIND) and x["apk"].get("abis") == [] and x["apk"]["min_sdk"] <= 31 and x["apk"]["size"] < 15_000_000], key=lambda x: x["apk"]["size"])
app = cands[0]; pkg = app["package"]
RES = []
def check(name, ok, detail=""):
    RES.append(bool(ok)); print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail[:140]}]" if detail and not ok else ""))

E.sh(f"pm uninstall {pkg}", check=False); E.sh(f"pm clear {E.APP}"); E.sh(f"appops set {E.APP} REQUEST_INSTALL_PACKAGES allow")
N.start(); E.tap("Discover", exact=True); time.sleep(1)
E.tap("Search"); time.sleep(0.8); E.sh("input text " + app["name"].split()[0].replace("'", "")); time.sleep(1.2)
check(f"search finds '{app['name']}' ({app['apk']['size']//1024} KB, {pkg})", E.has(app["name"], 5))
E.tap(app["name"]); time.sleep(1.5)
check("details: Install button, EXPERIMENTAL chip, no external listing", E.has("Install", 5) and E.has("EXPERIMENTAL", 3) and not E.has("External listing", 1)); E.shot("C1_details")
E.tap("Install", exact=True)
check("Android's own installer appears after download + verify (nothing installed before the user confirms)",
      bool(E.find(lambda n: "retrohatch" not in n["pkg"] and n["pkg"] not in ("", "com.android.systemui") and "install" in n["text"].lower(), 90)) and pkg not in E.sh(f"pm list packages {pkg}")); E.shot("C2_installer")
E.installer_button("Install")
for _ in range(40):
    if pkg in E.sh(f"pm list packages {pkg}", check=False): break
    time.sleep(1)
check("package installed", pkg in E.sh(f"pm list packages {pkg}", check=False))
import re
check("installed versionCode equals the signed catalog's", int(re.search(r"versionCode=(\d+)", E.sh(f"dumpsys package {pkg}")).group(1)) == app["apk"]["version_code"])
E.sh(f"am start -n {E.APP}/.ui.MainActivity"); time.sleep(3)
check("Details now shows Installed with Open + Uninstall", E.has("Installed", 15) and E.has("Uninstall", 3)); E.shot("C3_installed")
E.tap("Uninstall", exact=True); time.sleep(2); E.installer_button("OK")
for _ in range(20):
    if pkg not in E.sh(f"pm list packages {pkg}", check=False): break
    time.sleep(1)
check("uninstalled through Android's own screen", pkg not in E.sh(f"pm list packages {pkg}", check=False))
E.sh(f"am start -n {E.APP}/.ui.MainActivity"); time.sleep(3)
check("Details returns to Install by itself", E.has("Install", 10) and not E.find(lambda n: n["text"] == "Uninstall", 2))
# an external listing never has an install button
ext = next(x for x in cur if x["mode"] == "external")
N.start(); E.tap("Discover", exact=True); time.sleep(1); E.tap("Search"); time.sleep(0.8); E.sh("input text " + ext["name"].split()[0].replace("'", "")); time.sleep(1.2); E.tap(ext["name"]); time.sleep(1.5)
check(f"external listing '{ext['name']}': Open {ext['external']['label']}, no Install button", E.has("External listing", 5) and not E.find(lambda n: n["text"] == "Install", 2)); E.shot("C4_external")
print(f"\n{sum(RES)}/{len(RES)} checks passed")
sys.exit(0 if all(RES) else 1)
