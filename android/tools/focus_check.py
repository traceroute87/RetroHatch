#!/usr/bin/env python3
"""Update / uninstall with the physical-button path, on the rotate720 emulator: real APK update through Android's installer, the Details hero icon refreshing by
itself, the selected action coming back after Android's screens, and the first D-pad press moving the selection. Uses the harmless fixture APK only.
Needs: android/build/ui/fx6.apk and fx9.apk (gradlew :fixtureapp:assembleDebug -PfxVersionCode=6|9), `dev_fixture.py build` done, emulator up, debug APK installed.
    python -u android/tools/focus_check.py"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e as E
import nav_check as N
from PIL import Image
import io

UI = E.ANDROID / "build" / "ui"
FIX = E.FIXTURE
RES = []


def check(name, ok, detail=""):
    RES.append(bool(ok)); print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))


def vc():
    import re
    m = re.search(r"versionCode=(\d+)", E.sh(f"dumpsys package {FIX}")); return int(m.group(1)) if m else None


def hero_is_real_icon():
    """The fixture's real icon is blue; the generic package icon is grey/cream on a dark tile."""
    img = Image.open(io.BytesIO(E.adb("exec-out", "screencap", "-p", text=False))).convert("RGB")
    blue = sum(1 for x in range(30, 140, 3) for y in range(145, 255, 3) if (lambda p: p[2] > 110 and p[2] > p[0] + 40)(img.getpixel((x, y))))
    return blue > 40


def sysbutton(*labels):
    """A button of the system installer / uninstaller by its text (the dialog belongs to Android, not to RetroHatch)."""
    for l in labels:
        n = E.find(lambda n: n["text"].lower() == l.lower() and "retrohatch" not in n["pkg"] and n["pkg"] not in ("", "com.android.systemui"), 8)
        if n:
            E.sh(f"input tap {n['cx']} {n['cy']}"); time.sleep(1.5); return True
    return False


def focus():
    return N.focus_label()


def main():
    E.boot()
    E.adb("install", "-r", str(E.ANDROID / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"))
    E.server(True)
    try:
        E.fresh(); E.launch()
        E.adb("install", "-r", str(UI / "fx6.apk"))                       # version 1 of the test app, same key as the catalog's
        check("test app v1 installed", vc() == 6, str(vc()))
        E.open_entry("E2E Good APK")
        check("update is offered for v1 (catalog has v2)", E.has("Update available", 10) and E.has("Uninstall", 3))
        N.key("DOWN"); N.key("UP")                                        # leave touch mode like a first D-pad press
        check("selection is on the main action (Update)", "Update" in focus(), focus())
        N.key("A")
        check("Android's installer appears after download + verify", bool(E.find(lambda n: "retrohatch" not in n["pkg"] and n["pkg"] not in ("", "com.android.systemui") and ("update" in n["text"].lower() or "install" in n["text"].lower()), 60)))
        # confirm with the PHYSICAL buttons: the dialog's own focus, then A/Enter
        for k in ("DPAD_RIGHT", "DPAD_RIGHT", "ENTER"):
            E.sh(f"input keyevent KEYCODE_{k}"); time.sleep(0.8)
        for _ in range(30):
            if vc() == 7: break
            time.sleep(1)
        if vc() != 7:
            sysbutton("Update", "Install")
            for _ in range(30):
                if vc() == 7: break
                time.sleep(1)
        check("installed version changed 6 -> 7 through Android's installer", vc() == 7, str(vc()))
        time.sleep(3); E.shot("F1_after_update")
        check("Details shows Installed with Open + Uninstall by itself (no reopen)", E.has("Installed", 10) and E.has("Open", 3) and E.has("Uninstall", 3))
        check("hero icon is the app's real icon right away", hero_is_real_icon())
        check("selection is on a visible action after the installer closed", focus() != "", focus())
        N.key("RIGHT"); f1 = focus()
        check("first D-pad press after the installer moves the selection", "Uninstall" in f1, f1)
        N.key("LEFT"); check("D-pad LEFT returns to Open (no trap)", "Open" in focus(), focus())
        # downgrade: a newer build on the device must not be replaced
        E.adb("install", "-r", str(UI / "fx9.apk")); time.sleep(3)
        check("no Update offered for a newer installed build", not E.find(lambda n: n["text"] == "Update", 3) and E.has("Installed", 5))
        # uninstall, cancelled with the system Back key: the selected action (Uninstall) stays selected
        N.key("RIGHT"); check("selection on Uninstall", "Uninstall" in focus(), focus())
        N.key("A"); check("Android's own uninstall screen", bool(E.find(lambda n: "retrohatch" not in n["pkg"] and "uninstall" in n["text"].lower(), 20)))
        N.key("BACK"); time.sleep(2)
        check("cancelled uninstall keeps the app", E.sh(f"pm list packages {FIX}").strip() != "")
        check("selection is still on Uninstall after cancel", "Uninstall" in focus(), focus())
        N.key("LEFT"); check("first D-pad press after the cancel moves the selection", "Open" in focus(), focus())
        N.key("RIGHT"); N.key("A")
        time.sleep(2)
        for k in ("DPAD_RIGHT", "DPAD_RIGHT", "ENTER"):                    # confirm with the physical buttons, like the user on the Rotate
            E.sh(f"input keyevent KEYCODE_{k}"); time.sleep(0.8)
        if vc() is not None:
            sysbutton("OK")                                                 # touch fallback (then the first D-pad press only reveals the highlight)
        for _ in range(20):
            if vc() is None: break
            time.sleep(1)
        check("uninstalled through Android's screen", vc() is None)
        time.sleep(2); E.shot("F2_after_uninstall")
        check("Details returned to Install by itself", E.has("Ready to install", 10) and not E.find(lambda n: n["text"] == "Uninstall", 2))
        check("hero icon back to the generic package icon", not hero_is_real_icon())
        check("selection is on Install and moves with a D-pad press", "Install" in focus(), focus())
        N.key("DOWN"); N.key("UP"); check("D-pad keeps working afterwards (no trap)", "Install" in focus(), focus())
        N.key("BACK"); time.sleep(1)
        check("Android Back still goes back", E.has("Discover", 5) and E.has("E2E Good APK", 5))
    finally:
        E.server(False)
        E.sh(f"pm uninstall {FIX}", check=False)
    print(f"\n{sum(RES)}/{len(RES)} checks passed")
    sys.exit(0 if all(RES) else 1)


if __name__ == "__main__":
    main()
