#!/usr/bin/env python3
"""One category vocabulary for every device. Each application has ONE primary `group` and optional searchable `tags`.

  games | emulators | ports | utilities | media | themes-launchers

The signed catalog's own `category` enum (application utility launcher theme port other) is read by the RG Nano's C verifier and stays as it is; `group`
and `tags` are display metadata (candidate inventories, Android-only catalog fields). LEGACY maps the Nano inventory's category ids onto the same groups, so
a Nano OPK and an Android APK of the same kind land in the same group. A human can always override a group in the inventory: classify() only fills gaps.

  python discovery/categories.py --apply     fill missing `group` / `tags` in candidates/inventory*.json (never overwrites a value already there)
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS = [("games", "Games"), ("emulators", "Emulators"), ("ports", "Ports"), ("utilities", "Utilities"), ("media", "Media"), ("themes-launchers", "Themes & Launchers")]
GROUP_IDS = [g for g, _ in GROUPS]
LABEL = dict(GROUPS)
LEGACY = {"games": "games", "emulators": "emulators", "media": "media", "utilities": "utilities", "engines": "ports"}   # Nano inventory categories; "other" is classified from text

# (group, regex over name + description + topics). Order = priority: the first group whose score is highest wins; ties go to the earlier group in PRIORITY.
RULES = {
    "emulators": r"emulat|libretro|retroarch|\bmame\b|\bnes\b|\bsnes\b|game ?boy|\bgba\b|\bnds\b|nintendo ds|playstation|\bpsx\b|\bpsp\b|genesis|mega ?drive|dreamcast|\bn64\b|scummvm|dosbox|\bcore\b|\bmsx\b|atari|neo ?geo|pc engine|saturn|\bj2me\b",
    "themes-launchers": r"launcher|front-?end|\btheme|\bskin\b|wallpaper|icon pack|home screen|\bpegasus\b|daijish|\bes-de\b|emulationstation",
    "ports": r"\bports?\b|ported|engine|openbor|sdl ?port|reimplement|source port|\bopen source clone of|\bremake\b|\bsdl2?\b",
    "media": r"music|audio|video|player|podcast|radio|streaming|youtube|gallery|photo|image viewer|\bebook|e-reader|reader|movie|\bmp3\b|\bvlc\b|\bkodi\b|soundcloud|\bsubtitle",
    "utilities": r"file manager|files?\b.*manager|\btool|utility|2fa|authenticator|\botp\b|app store|updater|terminal|ssh|settings|calculator|clock|monitor|backup|sync|keyboard|launcher shortcut|\bsystem\b|installer|\bvpn\b|\bnotes?\b|browser|\bpdf\b",
    "games": r"\bgames?\b|puzzle|platformer|arcade|\brpg\b|shooter|roguelike|tetris|sokoban|snake|pong|racing|adventure|\bclone\b|sudoku|chess|solitaire|\bquiz\b|homebrew|\bplay\b|fun\b",
}
PRIORITY = ["emulators", "themes-launchers", "ports", "games", "media", "utilities"]
GENERIC_TAGS = {"android", "android-app", "android-application", "hacktoberfest", "kotlin", "kotlin-android", "java", "foss", "open-source", "opensource", "app", "apk", "mobile",
                "funkeyos", "rg-nano", "funkey-s", "opk", "rg-rotate", "gui", "github", "linux", "c", "cpp", "python", "rust", "hacktoberfest2024", "hacktoberfest2025"}
TAG_RE = re.compile(r"[a-z0-9][a-z0-9+-]{1,23}")


def classify(name="", description="", topics=(), legacy=None, text=""):
    """-> (group, confidence). confidence: 'legacy' (the Nano inventory's own category), 'high' (clear keyword lead) or 'low' (guess; a human should look)."""
    if legacy in LEGACY:
        return LEGACY[legacy], "legacy"
    hay = " ".join([name or "", description or "", " ".join(topics or []), text or ""]).lower().replace("-", " ")
    head = " ".join([name or "", description or "", " ".join(topics or [])]).lower().replace("-", " ")
    score = {g: len(re.findall(rx, head)) * 2 + len(re.findall(rx, hay)) for g, rx in RULES.items()}
    best = max(PRIORITY, key=lambda g: (score[g], -PRIORITY.index(g)))
    if score[best] == 0:
        return "utilities", "low"
    ranked = sorted(score.values(), reverse=True)
    return best, ("high" if ranked[0] > ranked[1] else "low")


def make_tags(topics=(), extra=(), limit=6):
    """Searchable tags: the project's own topics minus the generic ones, then a few vocabulary words. Lower-case, short, unique."""
    out = []
    for t in list(topics or []) + list(extra or []):
        t = str(t).strip().lower()
        if TAG_RE.fullmatch(t) and t not in GENERIC_TAGS and t not in out:
            out.append(t)
    return out[:limit]


def present(groups):
    """Only groups that hold entries, in the fixed display order."""
    have = set(groups)
    return [g for g in GROUP_IDS if g in have]


def apply_inventories():
    n = 0
    for name in ("inventory.json", "inventory-rg-rotate.json"):
        p = ROOT / "candidates" / name
        inv = json.loads(p.read_text(encoding="utf-8"))
        for a in inv["applications"]:
            if a.get("kind") == "support":
                continue
            if "group" not in a:
                a["group"], conf = classify(a.get("name"), a.get("description"), a.get("topics"), a.get("category"))
                if conf == "low":
                    a["group_confidence"] = "low"
                n += 1
            if "tags" not in a:
                a["tags"] = make_tags(a.get("topics"))
        p.write_text(json.dumps(inv, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{n} entries classified")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        apply_inventories()
    else:
        print(__doc__)
