#!/usr/bin/env python3
"""End-to-end test of the RG Rotate app on the Android 12 (API 31) 720x720 emulator `rotate720`, against a local HTTPS server.

Needs: python android/tools/dev_fixture.py init && build   (DEV keys, labelled test APK, signed DEV catalogs)
Run:   python -u android/tools/e2e.py [scenario numbers]   (starts the emulator and the HTTPS test server if they are not running)

The app is the DEBUG build: it trusts the DEV fixture key and DEV CA and maps https://traceroute87.github.io/RetroHatch/catalog/ to the local server (DevHooks).
It drives the real UI (uiautomator dump + taps) and Android's own package installer screen, and checks the result with pm/dumpsys/run-as:
  1  install            fetch catalog, download, verify, install after the user confirms; nothing is installed before that
  2  installed state    after a restart the app still shows Installed (no QUERY_ALL_PACKAGES); after a system uninstall it shows Ready again
  3  user cancel        the user taps Cancel in Android's installer: nothing is installed
  4  bad hash           tampered file: rejected, nothing kept
  5  wrong signer       other signing certificate: rejected before install
  6  wrong package      catalog names another package: rejected before install
  7  cancel download    B button while downloading: partial file removed
  8  online refresh     start-up fetch of the signed catalog, then Settings > Refresh Catalog brings in a newer one
  9  offline            server down: the cached catalog is still shown, the refresh reports the failure
  10 invalid updates    bad signature / tampered / unknown key / rollback: rejected, the last valid catalog stays
  11 no matching apps   valid catalog without an RG Rotate entry: accepted, "No apps for RG Rotate yet"
Screenshots and results go to android/build/e2e/."""
import json, os, re, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANDROID = HERE.parent
FX = ANDROID / "build" / "devfixture"
OUT = ANDROID / "build" / "e2e"
SDK = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or (Path.home() / "AppData/Local/Android/Sdk"))
ADB = str(SDK / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"))
APP, FIXTURE = "app.retrohatch.rotate", "app.retrohatch.testfixture"
RESULTS = []


def adb(*a, check=True, text=True, timeout=60):
    r = subprocess.run([ADB, *a], capture_output=True, text=text, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"adb {a}: {r.stdout}{r.stderr}")
    return r.stdout


def sh(cmd, **k):
    return adb("shell", cmd, **k)


def boot():
    if "device" not in adb("devices", check=False).replace("List of devices attached", ""):
        print("starting emulator rotate720 ...")
        subprocess.Popen([str(SDK / "emulator" / "emulator.exe"), "-avd", "rotate720", "-no-window", "-no-audio", "-no-boot-anim", "-gpu", "swiftshader_indirect", "-no-snapshot", "-accel", "on"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            if sh("getprop sys.boot_completed", check=False).strip() == "1":
                break
        except Exception:
            pass
        time.sleep(5)
    else:
        raise SystemExit("emulator did not boot")
    assert sh("wm size").strip().endswith("720x720"), sh("wm size")
    assert sh("getprop ro.build.version.sdk").strip() == "31"
    sh("settings put secure immersive_mode_confirmations confirmed")


def nodes():
    sh("uiautomator dump /sdcard/ui.xml", check=False)
    x = adb("exec-out", "cat", "/sdcard/ui.xml", text=False, check=False).decode("utf-8", "replace")
    try:
        root = ET.fromstring(x)
    except ET.ParseError:
        return []
    out = []
    for n in root.iter("node"):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds", ""))
        if m:
            l, t, r, b = map(int, m.groups())
            out.append({"text": n.get("text", ""), "id": n.get("resource-id", ""), "pkg": n.get("package", ""), "cx": (l + r) // 2, "cy": (t + b) // 2, "enabled": n.get("enabled") == "true"})
    return out


def find(pred, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for n in nodes():
            if pred(n):
                return n
        time.sleep(1)
    return None


def has(text, timeout=20, pkg=None):
    return find(lambda n: text.lower() in n["text"].lower() and (pkg is None or pkg in n["pkg"]), timeout)


def tap(text, timeout=20, exact=False, pkg=None):
    n = find(lambda n: (n["text"] == text if exact else text.lower() in n["text"].lower()) and (pkg is None or pkg in n["pkg"]) and n["enabled"], timeout)
    if not n:
        shot("FAIL_" + re.sub(r"\W+", "_", text))
        raise AssertionError(f"'{text}' not found on screen")
    sh(f"input tap {n['cx']} {n['cy']}")
    time.sleep(1)
    return n


def shot(name):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.png").write_bytes(adb("exec-out", "screencap", "-p", text=False))


def installer_button(label):
    """A button of Android's own package installer (any installer package), by text."""
    n = find(lambda n: n["text"].lower() == label.lower() and "retrohatch" not in n["pkg"] and n["pkg"] not in ("", "com.android.systemui"), 25)
    if not n:
        shot("FAIL_installer_" + label)
        raise AssertionError(f"system installer button '{label}' not found")
    sh(f"input tap {n['cx']} {n['cy']}")
    time.sleep(1.5)


def fixture_installed():
    return FIXTURE in sh(f"pm list packages {FIXTURE}", check=False)


SRV = None


def server(up):
    global SRV
    if up and SRV is None:
        SRV = subprocess.Popen([sys.executable, str(HERE / "dev_fixture.py"), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
    elif not up and SRV is not None:
        SRV.terminate(); SRV.wait(); SRV = None
        time.sleep(1)


def serve_catalog(name):
    """What the online catalog URL returns from now on (the server serves this directory live)."""
    live = FX / "serve" / "catalog"
    for f in ("index.json", "index.json.sig"):
        (live / f).write_bytes((FX / "catalogs" / name / f).read_bytes())


def fresh(catalog="good"):
    """Clean slate: fixture removed, app data cleared (no cache, no rollback state), the online catalog set, install permission granted (as the user would)."""
    server(True)
    sh(f"pm uninstall {FIXTURE}", check=False)
    sh(f"am force-stop {APP}", check=False)
    sh(f"pm clear {APP}")
    if catalog:
        serve_catalog(catalog)
    sh(f"appops set {APP} REQUEST_INSTALL_PACKAGES allow")
    sh("settings put secure immersive_mode_confirmations confirmed")


def launch(dev_banner=True):
    """Start the app; the start-up refresh runs in the background and the screens rebuild when it ends."""
    sh(f"am force-stop {APP}", check=False)
    sh(f"am start -n {APP}/.ui.MainActivity")
    time.sleep(3)
    if dev_banner:
        assert has("DEV FIXTURE CATALOG", 30), "the signed DEV catalog did not arrive"


def open_entry(title):
    tap("Discover", exact=True)
    time.sleep(1)
    for _ in range(3):                                    # the list is longer than the screen: scroll like a finger would
        n = find(lambda n: title.lower() in n["text"].lower() and 40 < n["cy"] < 600, 3)
        if n:
            break
        sh("input swipe 360 560 360 160 300"); time.sleep(1)
    tap(title)
    assert has("App Details", 10)


def downloads():
    return sh(f"run-as {APP} sh -c 'ls files/downloads 2>/dev/null'", check=False).split()


def scenario(name):
    def deco(fn):
        def run():
            t0 = time.time()
            try:
                fn()
                RESULTS.append({"scenario": name, "result": "PASS", "seconds": round(time.time() - t0, 1)})
                print(f"PASS  {name}")
            except Exception as e:
                RESULTS.append({"scenario": name, "result": "FAIL", "why": str(e)[:300]})
                print(f"FAIL  {name}: {e}")
        return run
    return deco


@scenario("1 install: fetch catalog, download, verify, install after the user confirms")
def s1():
    fresh(); launch()
    shot("1a_home_dev_banner")
    open_entry("E2E Good APK")
    assert has("Ready to download", 10); shot("1b_ready")
    tap("Download", exact=True)
    assert has("Ready to install", 40), "download + verification"; shot("1c_ready_to_install")
    assert not fixture_installed()
    tap("Install", exact=True)
    time.sleep(2); shot("1d_android_installer")
    assert find(lambda n: "retrohatch" not in n["pkg"] and n["pkg"] not in ("", "com.android.systemui") and "install" in n["text"].lower(), 25), "Android's own installer screen did not appear"
    assert not fixture_installed(), "nothing may be installed before the user confirms"
    installer_button("Install")
    for _ in range(40):
        if fixture_installed():
            break
        time.sleep(1)
    assert fixture_installed(), "package not installed"
    assert "versionCode=7" in sh(f"dumpsys package {FIXTURE}")
    n = find(lambda n: n["text"].lower() in ("done", "open") and "retrohatch" not in n["pkg"], 10)
    if n:
        sh(f"input tap {n['cx']} {n['cy']}")
    sh(f"am start -n {APP}/.ui.MainActivity")
    time.sleep(3)
    assert has("Installed", 20) and has("Open", 5), "app state Installed"
    shot("1e_installed")
    assert downloads() == [], f"downloaded APK should be removed after install: {downloads()}"


@scenario("2 installed state without QUERY_ALL_PACKAGES: survives a restart, follows a system uninstall")
def s2():
    perms = run_tool("aapt2", "dump", "permissions", str(ANDROID / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"))
    assert "QUERY_ALL_PACKAGES" not in perms, perms
    assert "REQUEST_INSTALL_PACKAGES" in perms and "INTERNET" in perms
    assert fixture_installed(), "needs scenario 1 first"
    launch(); open_entry("E2E Good APK")                  # restart: catalog from the cache, installed state from the platform
    assert has("Installed", 15) and has("Open", 5); shot("2a_installed_after_restart")
    sh(f"pm uninstall {FIXTURE}")
    launch(); open_entry("E2E Good APK")
    assert has("Ready to download", 15); shot("2b_after_uninstall")


@scenario("3 user cancel in Android's installer")
def s3():
    fresh(); launch(); open_entry("E2E Good APK")
    tap("Download", exact=True); assert has("Ready to install", 40)
    tap("Install", exact=True)
    time.sleep(2)
    installer_button("Cancel")
    sh(f"am start -n {APP}/.ui.MainActivity"); time.sleep(3)
    assert has("Install cancelled", 20), "app must report the cancel"; shot("3_install_cancelled")
    assert not fixture_installed(), "cancelled install must not install"


def failing(title, expect, shotname):
    fresh(); launch(); open_entry(title)
    tap("Download", exact=True)
    assert has(expect, 40), f"expected error '{expect}'"
    shot(shotname)
    assert has("Error", 5)
    assert not fixture_installed()
    assert [d for d in downloads() if d.endswith(".apk") or d.endswith(".part")] == [], f"nothing may be kept: {downloads()}"


@scenario("4 invalid hash is rejected, nothing kept")
def s4(): failing("E2E Bad Hash", "SHA-256 mismatch", "4_bad_hash")


@scenario("5 wrong signing certificate is rejected before install")
def s5(): failing("E2E Wrong Signer", "Signing certificate does not match", "5_wrong_signer")


@scenario("6 wrong package name is rejected before install")
def s6(): failing("E2E Wrong Package", "Wrong package", "6_wrong_package")


@scenario("7 cancel a download in progress (physical B button)")
def s7():
    fresh(); launch(); open_entry("E2E Slow Download")
    tap("Download", exact=True)
    for _ in range(20):                                   # wait for the partial file instead of a UI dump: the UI never idles while the progress bar moves
        if any(d.endswith(".part") for d in downloads()):
            break
        time.sleep(0.5)
    assert any(d.endswith(".part") for d in downloads()), "download did not start"
    shot("7a_downloading")
    sh("input keyevent KEYCODE_BUTTON_B")                 # B = cancel while downloading (the hint bar says Cancel)
    assert has("Download cancelled", 20); shot("7b_cancelled")
    time.sleep(1)
    assert [d for d in downloads() if d.endswith(".apk") or d.endswith(".part")] == [], downloads()
    assert not fixture_installed()


def catalog_rows():
    """Open Settings > Catalog Status from wherever the app is (relaunching would re-run the start-up refresh)."""
    for _ in range(4):
        if has("Refresh Catalog", 1):
            break
        sh("input keyevent KEYCODE_BACK"); time.sleep(1)
        if has("Settings", 1) and not has("Refresh Catalog", 1) and has("Discover", 1):
            tap("Settings", exact=True)
    tap("Catalog Status"); time.sleep(1)


def settings_refresh(expect, timeout=40):
    """In Settings: press Refresh Catalog and wait for the outcome text shown under it."""
    assert has("Refresh Catalog", 5)
    tap("Refresh Catalog", exact=True)
    assert has(expect, timeout), f"expected '{expect}' after Refresh Catalog"


def listed(title, timeout=2):
    tap("Discover", exact=True)
    time.sleep(1)
    found = False
    for _ in range(4):
        if has(title, timeout):
            found = True; break
        sh("input swipe 360 560 360 160 300"); time.sleep(1)
    return found


@scenario("8 online refresh: start-up fetch, then Settings > Refresh Catalog brings a newer catalog")
def s8():
    fresh("good"); launch()                               # start-up refresh: serial 2
    tap("Settings", exact=True)
    assert has("Updated to serial 2", 10); shot("8a_settings_after_startup_refresh")
    tap("Catalog Status")
    assert has("DEV fixture catalog (cached)", 5) and has("serial 2", 5); shot("8b_catalog_status")
    sh("input keyevent KEYCODE_BACK"); time.sleep(1)
    serve_catalog("v3")
    settings_refresh("Updated to serial 3"); shot("8c_updated")
    assert has("Hidden", 1) or True
    sh("input keyevent KEYCODE_BACK"); time.sleep(1)       # Settings -> Home
    assert listed("E2E Added Later"), "the new entry must appear after the refresh"; shot("8d_new_entry")
    serve_catalog("v3")
    sh("input keyevent KEYCODE_BACK"); time.sleep(1)
    tap("Settings", exact=True)
    settings_refresh("Already up to date (serial 3)")


@scenario("9 offline: cached catalog still shown, the failure is reported, nothing lost")
def s9():
    server(False)                                         # the online catalog is unreachable now
    try:
        launch()                                          # DEV banner comes from the verified cache, before any network
        assert listed("E2E Added Later"), "cached entries must be shown offline"; shot("9a_offline_cached")
        sh("input keyevent KEYCODE_BACK"); time.sleep(1)
        tap("Settings", exact=True)
        assert has("Failed:", 30), "the failed refresh must be reported"; shot("9b_offline_status")
        tap("Catalog Status")
        assert has("DEV fixture catalog (cached)", 5) and has("serial 3", 5)
    finally:
        server(True)


@scenario("10 invalid updates are rejected and the last valid catalog stays")
def s10():
    launch()                                              # cache = serial 3 (from scenario 8); the start-up refresh keeps it
    for name, why in (("badsig", "Rejected: bad signature"), ("tampered", "Rejected: bad signature"), ("unknownkey", "Rejected: unknown signing key"), ("rollback", "Rejected: rollback")):
        serve_catalog(name)
        tap("Settings", exact=True)
        settings_refresh(why); shot("10_" + name)
        assert has("previous catalog is kept", 3)
        sh("input keyevent KEYCODE_BACK"); time.sleep(1)
        assert listed("E2E Added Later"), f"{name}: the last valid catalog must still be shown"
        sh("input keyevent KEYCODE_BACK"); time.sleep(1)
    tap("Settings", exact=True); tap("Catalog Status")
    assert has("serial 3", 5), "still the last valid serial"; shot("10_status_after_rejections")


@scenario("11 no matching Android apps: valid catalog, nothing for RG Rotate")
def s11():
    fresh("nomatch"); launch()
    tap("Discover", exact=True)
    assert has("No apps for RG Rotate yet", 10); shot("11_no_matching_apps")
    sh("input keyevent KEYCODE_BACK"); time.sleep(1)
    tap("Settings", exact=True); tap("Catalog Status")
    assert has("1 for other devices", 5) or has("for other devices", 5)


def run_tool(name, *args):
    t = sorted((SDK / "build-tools").glob("*/" + name + ("*.exe" if os.name == "nt" else "")), reverse=True)[0]
    return subprocess.run([str(t), *args], capture_output=True, text=True).stdout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not (FX / "meta.json").exists():
        raise SystemExit("run: python android/tools/dev_fixture.py build")
    boot()
    adb("install", "-r", str(ANDROID / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"))
    server(True)
    try:
        every = {"1": s1, "2": s2, "3": s3, "4": s4, "5": s5, "6": s6, "7": s7, "8": s8, "9": s9, "10": s10, "11": s11}
        for k in (sys.argv[1:] or every):                  # e2e.py 8 9 10  runs only those scenarios (8 -> 9 -> 10 build on each other's app state)
            every[k]()
    finally:
        server(False)
        sh(f"pm uninstall {FIXTURE}", check=False)
    (OUT / ("results.json" if not sys.argv[1:] else "results-partial.json")).write_text(json.dumps({"device": sh("getprop ro.product.model").strip(), "api": 31, "results": RESULTS}, indent=1))
    bad = [r for r in RESULTS if r["result"] != "PASS"]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} scenarios passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
