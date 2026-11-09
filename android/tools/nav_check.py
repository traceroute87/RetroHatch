#!/usr/bin/env python3
"""Focused navigation check on the rotate720 emulator (720x720, Android 12), for the physical-button and touch paths of the UI.
Sends real key events / taps / swipes with adb and reads the resulting focus and text with uiautomator. Needs the emulator running and the debug APK installed
(the DEV catalog is bundled, so no server is needed). Screenshots go to android/build/nav/.
    python android/tools/nav_check.py"""
import os, re, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path

ANDROID = Path(__file__).resolve().parents[1]
OUT = ANDROID / "build" / "nav"
ADB = str(Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe") if os.name == "nt" else "adb"
APP = "app.retrohatch.rotate"
KEY = {"UP": 19, "DOWN": 20, "LEFT": 21, "RIGHT": 22, "A": 96, "B": 97, "L1": 102, "R1": 103, "BACK": 4, "ENTER": 66}
RES = []


def sh(*a):
    return subprocess.run([ADB, "shell", *a], capture_output=True, text=True).stdout


def key(*names):
    for n in names:
        sh("input", "keyevent", str(KEY[n])); time.sleep(0.8)


def dump():
    sh("uiautomator dump /sdcard/n.xml")
    x = subprocess.run([ADB, "exec-out", "cat", "/sdcard/n.xml"], capture_output=True).stdout.decode("utf-8", "replace")
    out = []
    for n in ET.fromstring(x).iter("node"):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds", ""))
        l, t, r, b = map(int, m.groups())
        out.append(dict(text=n.get("text", ""), focused=n.get("focused") == "true", clickable=n.get("clickable") == "true", cx=(l + r) // 2, cy=(t + b) // 2, l=l, t=t, r=r, b=b, pkg=n.get("package", "")))
    return out


def texts():
    return " | ".join(n["text"] for n in dump() if n["text"])


def focus_label():
    """The text inside the focused container (a row or a button), '' if nothing is focused."""
    nodes = dump()
    f = [n for n in nodes if n["focused"]]
    if not f:
        return ""
    box = f[0]
    return " ".join(n["text"] for n in nodes if n["text"] and n["l"] >= box["l"] and n["r"] <= box["r"] and n["t"] >= box["t"] and n["b"] <= box["b"])


def shot(name):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.png").write_bytes(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)


def check(name, ok, detail=""):
    RES.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))


def start():
    sh("am", "force-stop", APP); sh("am", "start", "-n", f"{APP}/.ui.MainActivity"); time.sleep(4)
    sh("input", "keyevent", str(KEY["DOWN"])); time.sleep(0.5); sh("input", "keyevent", str(KEY["UP"])); time.sleep(0.8)   # leave touch mode like a first D-pad press does


def main():
    assert "720x720" in sh("wm", "size"), "needs the 720x720 emulator"
    start(); shot("01_home")
    check("home: D-pad focus starts on Discover", focus_label().startswith("Discover"), focus_label())
    key("DOWN"); check("home: DOWN moves to Installed", focus_label().startswith("Installed"), focus_label())
    key("DOWN", "DOWN", "DOWN"); check("home: DOWN stops on the last row (Settings), no wrap, not lost", focus_label().startswith("Settings"), focus_label())
    key("UP", "UP", "UP"); check("home: UP back to Discover", focus_label().startswith("Discover"), focus_label())
    key("A"); time.sleep(1); shot("02_discover")
    check("A opens Discover", "Discover" in texts() and "Search" in texts() and "Category" in texts(), texts()[:120])
    first = focus_label(); check("discover: the first app row is focused on entry (not a toolbar button)", first != "" and not first.startswith(("Search", "Category", "Sort")), first)
    key("R1"); n1 = focus_label(); check("R1 jumps four rows", n1 != "" and n1 != first, n1)
    key("L1"); check("L1 jumps back", focus_label() == first, focus_label())
    key("DOWN", "DOWN"); key("A"); time.sleep(1); shot("03_details")
    check("A opens App Details", "App Details" in texts(), texts()[:120])
    check("details: the main action button is focused", any(x in focus_label() for x in ("Install", "Open", "Update")), focus_label())
    key("R1"); shot("04_details_scrolled"); check("R1 scrolls the page", "OVERVIEW" in texts().upper() or "Features" in texts(), texts()[:100])
    key("R1", "R1", "R1", "R1", "R1"); shot("05_details_end")
    check("details: page end reachable (Compatibility)", "COMPATIBILITY" in texts().upper(), texts()[:100])
    key("L1", "L1", "L1", "L1", "L1", "L1", "L1", "L1")
    check("details: L1 scrolls back to the top", "Install" in texts() or "Update" in texts() or "Open" in texts(), texts()[:100])
    n = 0
    while "Source" not in focus_label() and n < 25:          # DOWN scrolls the page (the description) until the next control comes into view, then focus moves to it
        key("DOWN"); n += 1
    f = focus_label(); check(f"details: repeated DOWN reaches the Source row after scrolling ({n} presses): focus is not trapped", "Source" in f, f); shot("05b_details_source_focused")
    n = 0
    while not ("Install" in focus_label() or "Open" in focus_label()) and n < 25:
        key("UP"); n += 1
    check(f"details: repeated UP returns to the action button ({n} presses)", "Install" in focus_label() or "Open" in focus_label(), focus_label())
    key("B"); time.sleep(1)
    check("B goes back to Discover", "Discover" in texts() and "Search" in texts(), texts()[:100])
    key("A"); time.sleep(1); key("BACK"); time.sleep(1)
    check("system Back goes back to Discover", "Discover" in texts() and "Search" in texts(), texts()[:100])
    key("B"); time.sleep(1)
    check("B on a sub-screen returns Home", "Discover" in texts() and "Settings" in texts() and "Exit" in texts(), texts()[:100])
    key("DOWN", "DOWN", "DOWN"); key("A"); time.sleep(1); shot("06_settings")
    check("settings reachable by D-pad", "Settings" in texts() and "Catalog Status" in texts(), texts()[:100])
    key("DOWN"); key("A"); time.sleep(1); shot("07_catalog_status")
    check("Catalog Status shows the bundled experimental source", "DEV fixture catalog" in texts(), texts()[:200])
    key("B", "B", "B"); time.sleep(1)
    # touch
    start()
    n = [x for x in dump() if x["text"] == "Discover"][0]; sh("input", "tap", str(n["cx"]), str(n["cy"])); time.sleep(1)
    check("touch: tapping a row opens it", "Search" in texts() and "Category" in texts(), texts()[:100])
    sh("input", "swipe", "360", "560", "360", "160", "300"); time.sleep(1); shot("08_touch_scrolled")
    check("touch: swipe scrolls the list", "8-Bit Wonders" not in texts(), texts()[:200])
    sh("input", "tap", "40", "40"); time.sleep(1)                       # the header's back arrow
    check("touch: header back arrow goes back", "Settings" in texts() and "Exit" in texts(), texts()[:100])
    n = [x for x in dump() if x["text"] == "Discover"][0]; sh("input", "tap", str(n["cx"]), str(n["cy"])); time.sleep(1)
    h = [x for x in dump() if x["text"] == "Back"][0]; sh("input", "tap", str(h["cx"]), str(h["cy"])); time.sleep(1)   # the hint bar's B
    check("touch: hint-bar B goes back", "Exit" in texts(), texts()[:100])
    bad = [n for n, ok in RES if not ok]
    print(f"\n{len(RES) - len(bad)}/{len(RES)} navigation checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
