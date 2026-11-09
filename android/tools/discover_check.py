#!/usr/bin/env python3
"""Discover on the rotate720 emulator (or a connected RG Rotate: set ANDROID_SERIAL) against the bundled curated DEV catalog: categories, search, sort, filters, external listings,
details, D-pad and touch. Expected values are computed from the bundled catalog itself, so the check follows whatever is curated. Reads the screen with uiautomator, sends real taps / key
events / typed text. Needs the debug APK installed. Screenshots: android/build/discover/.
    python -u android/tools/discover_check.py"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nav_check as N

OUT = N.ANDROID / "build" / "discover"; N.OUT = OUT
APP = N.APP
RES = []
CAT = json.loads((N.ANDROID / "app" / "src" / "debug" / "assets" / "dev" / "catalog" / "index.json").read_text(encoding="utf-8"))
ENTRIES = [{"name": a["name"], "group": a["group"], "released": a.get("released", ""), "ext": False, "tags": a.get("tags", []), "dev": a["developer"]} for a in CAT["apps"]] + \
          [{"name": a["name"], "group": a["group"], "released": a.get("released", ""), "ext": True, "label": a["label"], "tags": a.get("tags", []), "dev": a["developer"]} for a in CAT["external"]]
LABEL = {"games": "Games", "emulators": "Emulators", "ports": "Ports", "utilities": "Utilities", "media": "Media", "themes-launchers": "Themes & Launchers"}
ORDER = list(LABEL)


def check(name, ok, detail=""):
    RES.append(bool(ok)); print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail[:160]}]" if detail and not ok else ""))


def tap(text, exact=True):
    for n in N.dump():
        if (n["text"] == text if exact else text.lower() in n["text"].lower()) and n["cy"] > 90:
            N.sh("input", "tap", str(n["cx"]), str(n["cy"])); time.sleep(1.2); return True
    return False


def texts(): return N.texts()


def main():
    total = len(ENTRIES); ext = [e for e in ENTRIES if e["ext"]]; inst = [e for e in ENTRIES if not e["ext"]]
    N.sh("pm", "clear", APP)
    N.start(); time.sleep(1)
    check("Home -> Discover by touch", tap("Discover") and all(x in texts() for x in ("Search", "Category", "Sort")), texts())
    check(f"summary line counts every entry ({total}: {len(inst)} installable + {len(ext)} external)", f"{total} apps" in texts(), texts()[:160]); N.shot("01_browse")

    tap("Category"); N.shot("02_categories"); t = texts()
    N.sh("input", "swipe", "360", "560", "360", "160", "300"); time.sleep(1); t += " | " + texts()           # the last categories sit below the fold
    have = [g for g in ORDER if any(e["group"] == g for e in ENTRIES)]
    check("Category screen: only non-empty categories with counts", all(f"{LABEL[g]} | {sum(e['group']==g for e in ENTRIES)}" in t for g in have) and all(LABEL[g] not in t for g in ORDER if g not in have), t[:300])
    g = "emulators"; k = sum(e["group"] == g for e in ENTRIES)
    tap("Emulators"); N.shot("03_emulators"); t = texts()
    check(f"choosing Emulators shows {k} of {total}", f"{k} of {total}" in t and "Emulators" in t, t[:200])

    tap("Sort"); tap("Newly added"); tap("Recently updated"); N.key("B"); time.sleep(1.2)
    em = sorted([e for e in ENTRIES if e["group"] == g], key=lambda e: (e["released"] == "", "".join(chr(255 - ord(c)) for c in e["released"]), e["name"].lower()))
    check(f"Recently updated puts '{em[0]['name']}' first among emulators", em[0]["name"] in texts() and "Recently updated" in texts(), texts()[:200]); N.shot("04_updated")

    tap("Sort"); N.sh("input", "swipe", "360", "560", "360", "160", "300"); time.sleep(1); tap("External listings"); N.key("B"); time.sleep(1.2); N.shot("05_external_filter")
    t = texts(); ee = [e for e in ENTRIES if e["group"] == g and e["ext"]]
    check("External listings filter shows only external entries, each marked External", "External listings" in t and (not ee or ("External" in t and any(x["name"] in t for x in ee))) and f"{len(ee)} of {total}" in t, t[:220])
    if not tap("Clear search and filters"): tap("", exact=True)
    N.start(); N.key("A"); time.sleep(1)

    if ext:                                           # an external listing: link and reason, no install button
        e = sorted(ext, key=lambda x: (len(x["name"].split()) < 2, x["name"].lower()))[0]       # a multi-word name: the typed search word never equals the result row's text
        tap("Search"); time.sleep(0.8); N.sh("input", "text", e["name"].split()[0]); time.sleep(1.2)
        check(f"search finds the external entry '{e['name']}'", e["name"] in texts(), texts()[:160])
        tap(e["name"]); time.sleep(1.5); N.shot("06_external_details"); t = texts()
        check("external details: 'External listing', its reason and an Open <label> button; no Install / Update", "External listing" in t and f"Open {e['label']}"[:26] in t and "Install" not in t.replace("Installed", "") and "Update" not in t, t[:300])
        N.key("B"); time.sleep(1); N.key("B"); time.sleep(1)

    pick = next(e for e in inst if e["tags"])         # search by name, tag and a word that matches nothing
    N.start(); N.key("A"); time.sleep(1)               # fresh start: the previous query is kept while the app runs
    tap("Search"); time.sleep(0.8)
    for word, want in ((pick["name"].split()[0], pick["name"]), (pick["tags"][0], pick["name"]), ("zzzzqq", None)):
        N.sh("input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(30): N.sh("input", "keyevent", "KEYCODE_DEL")
        N.sh("input", "text", word.replace(" ", "")); time.sleep(1.0)
        if want: check(f"search '{word}' finds '{want}'", want in texts(), texts()[:160])
        else: check("search with no hit says so", "No apps match" in texts(), texts()[:120])
    N.shot("07_search"); N.key("B"); time.sleep(1)

    N.start(); N.key("A"); time.sleep(1)               # D-pad
    n = 0
    while not any(x in N.focus_label() for x in ("Search", "Category", "Sort")) and n < 6: N.key("UP"); n += 1
    check("D-pad: UP from the list reaches the toolbar", any(x in N.focus_label() for x in ("Search", "Category", "Sort")), N.focus_label())
    N.key("LEFT", "LEFT"); check("D-pad: LEFT reaches Search", "Search" in N.focus_label(), N.focus_label())
    N.key("RIGHT"); check("D-pad: RIGHT moves Search -> Category", "Category" in N.focus_label(), N.focus_label())
    N.key("DOWN"); check("D-pad: DOWN returns to the list", N.focus_label() != "" and "Category" not in N.focus_label(), N.focus_label())
    for _ in range(12): N.key("DOWN")
    check("D-pad: DOWN x12 keeps moving down the list (no trap)", N.focus_label() != "", N.focus_label()); N.shot("08_dpad_list")
    N.key("A"); time.sleep(1.2)
    check("D-pad: A opens App Details", "App Details" in texts(), texts()[:100])
    N.key("B"); time.sleep(1); check("B returns to Discover", "Discover" in texts(), texts()[:100])
    print(f"\n{sum(RES)}/{len(RES)} Discover checks passed")
    sys.exit(0 if all(RES) else 1)


if __name__ == "__main__":
    main()
