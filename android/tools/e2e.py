#!/usr/bin/env python3
"""End-to-end test of the RG Rotate installer on the Android 12 (API 31) 720x720 emulator `rotate720`.

Needs: python android/tools/dev_fixture.py init && build   (DEV keys, labelled test APK, signed DEV catalogs)
Run:   python android/tools/e2e.py            (starts the emulator and the HTTPS test server if they are not running)

Drives the real app through its UI (uiautomator dump + taps) and Android's own package installer screen, and checks the result with pm/dumpsys:
  1 success       download over HTTPS (DEV CA), verify, install after the user taps Install in Android's installer
  2 user cancel   the user taps Cancel in Android's installer: nothing is installed, the app says so
  3 bad hash      tampered file: rejected before install, nothing kept
  4 wrong signer  right hash, other signing certificate: rejected before install
  5 wrong package catalog names another package than the APK: rejected before install
  6 cancel download   cancel while downloading: partial file removed
  7 invalid catalogs  bad signature / tampered index / unknown key / rollback: catalog rejected, only the PREVIEW sample is shown
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


def fresh(catalog="good"):
    """Clean slate: fixture removed, app data cleared, the chosen signed catalog placed in the app's private files, install permission granted (as the user would)."""
    sh(f"pm uninstall {FIXTURE}", check=False)
    sh(f"am force-stop {APP}", check=False)
    sh(f"pm clear {APP}")
    if catalog:
        put_catalog(catalog)
    sh(f"appops set {APP} REQUEST_INSTALL_PACKAGES allow")
    sh("settings put secure immersive_mode_confirmations confirmed")


def put_catalog(name):
    d = FX / "catalogs" / name
    for f in ("index.json", "index.json.sig"):
        adb("push", str(d / f), f"/data/local/tmp/{f}")
    sh(f"run-as {APP} sh -c 'mkdir -p files/catalog && cp /data/local/tmp/index.json files/catalog/index.json && cp /data/local/tmp/index.json.sig files/catalog/index.json.sig'")


def launch():
    sh(f"am force-stop {APP}", check=False)
    sh(f"am start -n {APP}/.ui.MainActivity")
    time.sleep(3)


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


@scenario("1 success: download, verify, install after the user confirms")
def s1():
    fresh(); launch()
    assert has("DEV FIXTURE CATALOG", 10), "DEV banner"
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
    assert has("installed", 60, pkg=None)
    for _ in range(30):
        if fixture_installed():
            break
        time.sleep(1)
    assert fixture_installed(), "package not installed"
    dump = sh(f"dumpsys package {FIXTURE}")
    assert "versionCode=7" in dump, dump[:300]
    # back to the app: Done / Open in the installer, then the app must say Installed
    n = find(lambda n: n["text"].lower() in ("done", "open") and "retrohatch" not in n["pkg"], 10)
    if n:
        sh(f"input tap {n['cx']} {n['cy']}")
    sh(f"am start -n {APP}/.ui.MainActivity")
    time.sleep(3)
    assert has("Installed", 20) and has("Open", 5), "app state Installed"
    shot("1e_installed")
    assert downloads() == [], f"downloaded APK should be removed after install: {downloads()}"


@scenario("2 user cancel in Android's installer")
def s2():
    fresh(); launch(); open_entry("E2E Good APK")
    tap("Download", exact=True); assert has("Ready to install", 40)
    tap("Install", exact=True)
    time.sleep(2)
    installer_button("Cancel")
    sh(f"am start -n {APP}/.ui.MainActivity"); time.sleep(3)
    assert has("Install cancelled", 20), "app must report the cancel"; shot("2_install_cancelled")
    assert not fixture_installed(), "cancelled install must not install"


def failing(title, expect, shotname):
    fresh(); launch(); open_entry(title)
    tap("Download", exact=True)
    assert has(expect, 40), f"expected error '{expect}'"
    shot(shotname)
    assert has("Error", 5)
    assert not fixture_installed()
    assert [d for d in downloads() if d.endswith(".apk") or d.endswith(".part")] == [], f"nothing may be kept: {downloads()}"


@scenario("3 invalid hash is rejected, nothing kept")
def s3(): failing("E2E Bad Hash", "SHA-256 mismatch", "3_bad_hash")


@scenario("4 wrong signing certificate is rejected before install")
def s4(): failing("E2E Wrong Signer", "Signing certificate does not match", "4_wrong_signer")


@scenario("5 wrong package name is rejected before install")
def s5(): failing("E2E Wrong Package", "Wrong package", "5_wrong_package")


@scenario("6 cancel a download in progress (physical B button)")
def s6():
    fresh(); launch(); open_entry("E2E Slow Download")
    tap("Download", exact=True)
    for _ in range(20):                                   # wait for the partial file instead of a UI dump: the UI never idles while the progress bar moves
        if any(d.endswith(".part") for d in downloads()):
            break
        time.sleep(0.5)
    assert any(d.endswith(".part") for d in downloads()), "download did not start"
    shot("6a_downloading")
    sh("input keyevent KEYCODE_BUTTON_B")                 # B = cancel while downloading (the hint bar says Cancel)
    assert has("Download cancelled", 20); shot("6b_cancelled")
    time.sleep(1)
    assert [d for d in downloads() if d.endswith(".apk") or d.endswith(".part")] == [], downloads()
    assert not fixture_installed()


def catalog_status():
    tap("Back", 10) if has("App Details", 1) else None
    tap("Settings", exact=True); tap("Catalog Status")


@scenario("7 invalid catalogs: bad signature, tampered index, unknown key, rollback")
def s7():
    for name, why in (("badsig", "bad signature"), ("tampered", "bad signature"), ("unknownkey", "unknown signing key")):
        fresh(name); launch()
        assert has("PREVIEW ONLY", 10), f"{name}: preview strip"
        tap("Settings", exact=True); tap("Catalog Status")
        assert has("Signed catalog rejected: " + why, 10), f"{name}: reason '{why}'"
        shot("7_" + name)
        sh("input keyevent KEYCODE_BACK"); sh("input keyevent KEYCODE_BACK")
        tap("Discover", exact=True)
        assert not has("E2E", 3), f"{name}: no entry of the rejected catalog may be shown"
    fresh("good"); launch()
    assert has("DEV FIXTURE CATALOG", 10)           # accepts serial 2, remembers it
    put_catalog("rollback"); launch()               # serial 1: older
    assert has("PREVIEW ONLY", 10)
    tap("Settings", exact=True); tap("Catalog Status")
    assert has("rollback", 10); shot("7_rollback")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not (FX / "meta.json").exists():
        raise SystemExit("run: python android/tools/dev_fixture.py build")
    boot()
    adb("install", "-r", str(ANDROID / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"))
    srv = subprocess.Popen([sys.executable, str(HERE / "dev_fixture.py"), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    try:
        every = {"1": s1, "2": s2, "3": s3, "4": s4, "5": s5, "6": s6, "7": s7}
        for k in (sys.argv[1:] or every):                  # e2e.py 4 6  runs only those scenarios
            every[k]()
    finally:
        srv.terminate()
        sh(f"pm uninstall {FIXTURE}", check=False)
    (OUT / ("results.json" if not sys.argv[1:] else "results-partial.json")).write_text(json.dumps({"device": sh("getprop ro.product.model").strip(), "api": 31, "results": RESULTS}, indent=1))
    bad = [r for r in RESULTS if r["result"] != "PASS"]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} scenarios passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
