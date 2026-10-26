#!/usr/bin/env python3
"""Local catalog -> Nano install engine. Host only: no network, no download.

  plan.py --catalog DIR --device rg-nano --firmware ID --apps DIR --state DIR \
          install|uninstall APP_ID [--file LOCAL_OPK]

The whole catalog must validate first. Install needs a `verified`, `available`
artifact for exactly this device + firmware; the local file must match the
catalog size and SHA-256 (the engine re-checks). The catalog URL is never used.
"""
import argparse, subprocess, sys
from pathlib import Path

import validate

CLI = Path(__file__).resolve().parent.parent / "build" / "rh_host_cli"
ADAPTER = "opk-funkeyos"
ENGINE_EXTRA = []  # tests: ["--mounts", f, "--sysblock", d] for a hermetic mount view


class Refused(Exception):
    pass


def select(catalog, app_id, device_id, firmware, installing):
    errs = validate.check(catalog)
    if errs:
        raise Refused("catalog invalid: " + errs[0])
    app = validate.load(catalog / "apps" / f"{app_id}.json") if (catalog / "apps" / f"{app_id}.json").is_file() else None
    dev = validate.load(catalog / "devices" / f"{device_id}.json") if (catalog / "devices" / f"{device_id}.json").is_file() else None
    if not app:
        raise Refused(f"unknown app '{app_id}'")
    if not dev:
        raise Refused(f"unknown device '{device_id}'")
    if dev["adapter"] != ADAPTER:
        raise Refused(f"no installer for adapter '{dev['adapter']}'")
    if firmware not in dev["firmware"]:
        raise Refused(f"firmware '{firmware}' not on device '{device_id}'")
    arts = [a for a in app["artifacts"] if a["device"] == device_id and a["firmware"] == firmware
            and a["format"] == dev["package_format"]]
    if not arts:
        raise Refused("no artifact for this device/firmware")
    art = arts[0]
    if installing:
        if art["status"] != "available":
            raise Refused("artifact unavailable: " + art.get("unavailable_reason", ""))
        if art["compatibility"]["level"] != "verified":
            raise Refused(f"compatibility is '{art['compatibility']['level']}', need 'verified'")
    dest = art.get("install", {}).get("dest_name")
    if not dest:
        raise Refused("artifact has no install.dest_name")
    return app, art, dest


def run_engine(args, apps, state):
    if not CLI.is_file():
        raise Refused(f"build {CLI} first (see tests/test_plan.py)")
    r = subprocess.run([str(CLI), "--apps", str(apps), "--state", str(state), *ENGINE_EXTRA, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def install(catalog, app_id, device, firmware, apps, state, file):
    app, art, dest = select(catalog, app_id, device, firmware, True)
    f = Path(file)
    if not f.is_file() or f.stat().st_size != art["size"]:
        raise Refused("local file missing or size differs from catalog")
    return run_engine(["install", app_id, art["version"], dest, str(f), str(art["size"]), art["sha256"]], apps, state)


def uninstall(catalog, app_id, device, firmware, apps, state):
    _, _, dest = select(catalog, app_id, device, firmware, False)
    return run_engine(["uninstall", app_id, dest], apps, state)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, default=validate.ROOT)
    ap.add_argument("--device", required=True)
    ap.add_argument("--firmware", required=True)
    ap.add_argument("--apps", required=True, type=Path)
    ap.add_argument("--state", required=True, type=Path)
    ap.add_argument("action", choices=["install", "uninstall"])
    ap.add_argument("app_id")
    ap.add_argument("--file")
    a = ap.parse_args()
    try:
        if a.action == "install":
            if not a.file:
                raise Refused("--file required (no downloading)")
            rc, out = install(a.catalog, a.app_id, a.device, a.firmware, a.apps, a.state, a.file)
        else:
            rc, out = uninstall(a.catalog, a.app_id, a.device, a.firmware, a.apps, a.state)
    except Refused as e:
        print(f"refused: {e}")
        sys.exit(2)
    print(out)
    sys.exit(rc)
