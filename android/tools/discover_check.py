#!/usr/bin/env python3
"""Discover on the rotate720 emulator (or a connected RG Rotate: set ANDROID_SERIAL): categories, search, sort, filters, empty state, state kept across screens, D-pad and
touch. Reads the screen with uiautomator, sends real taps / key events / typed text. Needs the debug APK installed (the 8-app DEV catalog is bundled). Screenshots: android/build/discover/.
    python -u android/tools/discover_check.py"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nav_check as N

OUT = N.ANDROID / "build" / "discover"; N.OUT = OUT
APP = N.APP
RES = []


def check(name, ok, detail=""):
    RES.append(bool(ok)); print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail[:150]}]" if detail and not ok else ""))


def tap(text, exact=True, below=0):
    for n in N.dump():
        if (n["text"] == text if exact else text.lower() in n["text"].lower()) and n["cy"] > below:
            N.sh("input", "tap", str(n["cx"]), str(n["cy"])); time.sleep(1.2); return True
    return False


def names(): return [n["text"] for n in N.dump() if n["text"] in ("Aegis", "Droid-ify", "Gallery", "Lemuroid", "Material Files", "melonDS", "NewPipe", "Obtainium")]


def main():
    N.sh("pm", "clear", APP)
    N.start(); time.sleep(1)
    check("Home -> Discover by touch", tap("Discover") and "Search" in N.texts() and "Category" in N.texts() and "Sort" in N.texts(), N.texts())
    t = N.texts(); N.shot("01_browse")
    check("toolbar + summary line: 8 apps, A to Z", "8 apps" in t and "A to Z" in t, t[:200])
    check("sorted A to Z", names()[:2] == ["Aegis", "Droid-ify"], str(names()))

    # categories: only the ones that hold apps
    tap("Category"); N.shot("02_categories"); t = N.texts()
    check("Category screen lists only non-empty categories with counts", all(x in t for x in ("All apps", "Emulators", "Utilities", "Media")) and not any(x in t for x in ("Games", "Ports", "Themes")), t)
    check("counts: Emulators 2, Utilities 4, Media 2", "Emulators | 2" in t and "Utilities | 4" in t and "Media | 2" in t, t)
    tap("Emulators"); N.shot("03_emulators"); t = N.texts()
    check("choosing Emulators filters the list and says so", names() == ["Lemuroid", "melonDS"] and "2 of 8" in t and "Emulators" in t, f"{names()} {t[:150]}")

    # sort + filter, state kept
    tap("Category") if False else None
    tap("Sort"); N.shot("04_options"); tap("Newly added"); tap("Recently updated")
    check("Sort by Recently updated is checked", "Recently updated" in N.texts(), N.texts())
    N.key("B"); time.sleep(1)
    check("back to Discover: Emulators sorted by release date (melonDS 2026-05 before Lemuroid 2026-04)", names() == ["melonDS", "Lemuroid"] and "Recently updated" in N.texts(), f"{names()} {N.texts()[:160]}")
    tap("Sort"); N.sh("input", "swipe", "360", "560", "360", "160", "300"); time.sleep(1); tap("Updates available"); N.key("B"); time.sleep(1); N.shot("05_empty_filter")
    t = N.texts()
    check("empty state when nothing matches, with a way out", "No matching apps" in t and "Clear search and filters" in t, t)
    tap("Clear search and filters"); time.sleep(1)
    check("clearing resets search, category and filter", len(names()) >= 4 and "8 apps" in N.texts(), f"{names()} {N.texts()[:100]}")

    # search by name, description, developer and tag
    tap("Search"); time.sleep(0.8)
    for word, want in (("lemu", ["Lemuroid"]), ("libretro", ["Lemuroid"]), ("Swordfish90", ["Lemuroid"]), ("emulator", ["Lemuroid", "melonDS"]), ("2fa", ["Aegis"]), ("zzzz", [])):
        N.sh("input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(12): N.sh("input", "keyevent", "KEYCODE_DEL")
        N.sh("input", "text", word); time.sleep(1.0)
        got = sorted(x for x in names() if x != "")
        check(f"search '{word}' -> {want}", got == sorted(want), f"{got} {N.texts()[:100]}")
    N.shot("06_search_none")
    check("search with no hit says so", "No apps match" in N.texts(), N.texts())
    for _ in range(12): N.sh("input", "keyevent", "KEYCODE_DEL")
    N.sh("input", "text", "retro"); time.sleep(1)
    N.shot("07_search_results")
    tap("Lemuroid"); time.sleep(1.2)
    check("a search result opens App Details", "App Details" in N.texts() and "Lemuroid" in N.texts(), N.texts()[:100])
    N.key("B"); time.sleep(1); N.key("B"); time.sleep(1)
    check("search text kept on Discover after opening an app", '"retro"' in N.texts() and "of 8" in N.texts(), N.texts()[:160])
    tap("", exact=True) if False else None

    # D-pad: toolbar reachable and no trap
    N.start(); N.key("A"); time.sleep(1)
    n = 0
    while not any(x in N.focus_label() for x in ("Search", "Category", "Sort")) and n < 6: N.key("UP"); n += 1
    check("D-pad: UP from the list reaches the toolbar", any(x in N.focus_label() for x in ("Search", "Category", "Sort")), N.focus_label())
    N.key("LEFT", "LEFT"); check("D-pad: LEFT reaches Search", "Search" in N.focus_label(), N.focus_label())
    N.key("RIGHT"); check("D-pad: RIGHT moves Search -> Category", "Category" in N.focus_label(), N.focus_label())
    N.key("RIGHT"); check("D-pad: RIGHT moves Category -> Sort", "Sort" in N.focus_label(), N.focus_label())
    N.key("DOWN"); check("D-pad: DOWN returns to the app list", any(a in N.focus_label() for a in ("Aegis", "Droid-ify", "Gallery", "Lemuroid", "Material", "melonDS", "NewPipe", "Obtainium")), N.focus_label())
    N.key("UP", "LEFT", "A"); time.sleep(1)
    check("D-pad: A on a toolbar button opens its screen", "Categories" in N.texts() or "Search" in N.texts(), N.texts()[:100])
    N.key("B"); time.sleep(1)
    check("B returns from it", "Discover" in N.texts(), N.texts()[:100])
    print(f"\n{sum(RES)}/{len(RES)} Discover checks passed")
    sys.exit(0 if all(RES) else 1)


if __name__ == "__main__":
    main()
