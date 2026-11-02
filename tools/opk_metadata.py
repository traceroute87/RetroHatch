"""Offline helper shared by tools/make_wiki_inventory.py and tools/make_candidate_snapshot.py: apply the package .desktop evidence
(discovery/opk-metadata-evidence.json) to candidate entries. No network, no file writes of its own.

Rules, in order of trust:
  * An existing description is never replaced. An empty one is filled only from a package Comment that really describes the app
    (not a BIOS note, "Modified", or the app's own name with "for Libretro"); the source is recorded in `description_source`.
  * `category` is never changed. The package's Categories are recorded and compared with the row's category (reviewed, or derived by
    the same word lists the Nano UI uses); a disagreement goes to `metadata_review`, and the Basis text gets a short verdict.
  * `name` is never changed. A different package Name is listed under `metadata_review.name` as a proposal only.
  * Icons are recorded (format, size, SHA-256, availability inside the package). `icon_file` is set, and the file may sit under candidates/icons/,
    ONLY when the icon's redistribution status is "redistributable". A project licence is not assumed to cover its artwork; "unclear" and
    "restricted" icons keep the package glyph, stay out of Git and out of the production OPK, and live only in a local development folder.
enrich() is idempotent: it removes its own earlier additions first, so it can be re-run on an already enriched snapshot.
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "discovery" / "opk-metadata-evidence.json"
SOURCE = "package .desktop Comment"
SOURCE_EDITED = SOURCE + ", edited"   # the shown text differs from the Comment; evidence keeps the original (desktop.comment) and the reason
# shown instead of the Comment, by maintainer decision (the original stays in the evidence file)
DISPLAY = {"wiki-lameds": ("NDS emulator", "maintainer edit: leading word \"Horrible\" dropped")}
VERDICT_SEP = "; package "          # appended to a category basis: "; package agrees"
BASIS_MAX = 95                      # the Nano UI keeps 95 characters of a row value
CAT_NAME = {"games": "Games", "emulators": "Emulators", "media": "Media", "utilities": "Utilities", "engines": "Engines & Tools", "other": "Other"}
SECTION = {"games": "games", "emulators": "emulators"}   # launcher sections that name a RetroHatch category; "applications" is too generic

# the Nano UI's word lists (ui/rh_model.c KW); tests/test_opk_metadata.py checks this copy against the C source
KW = {"games": "game games minigame minigames puzzle puzzles arcade platformer roguelike rpg shooter sokoban sudoku".split(),
      "emulators": "emulator emulators emulation libretro retroarch".split(),
      "media": "music audio video movie movies mp3 podcast radio photo photos media ebook".split(),
      "utilities": "utility utilities viewer editor manager calculator clock terminal launcher backup converter".split(),
      "engines": "engine engines runtime library lib libs framework sdk toolkit toolchain tool tools compiler interpreter devkit".split()}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def derive_category(name, desc, topics):
    """what rh_categorize() in the Nano UI answers: exactly one category with a whole-word match, else Other"""
    hit = set()
    for text in (name or "", desc or "", " ".join(topics or [])):
        for tok in re.findall(r"[A-Za-z0-9]+", text):
            if len(tok) < 24:
                for cat, words in KW.items():
                    if tok.lower() in words: hit.add(cat)
    return hit.pop() if len(hit) == 1 else "other"


NOTE_START = ("needs ", "requires ", "modified")
# decided by reading each Comment once: product name plus a word that adds nothing
NAME_ONLY = {"wiki-easyrpg": "product name plus \"Player\""}


def classify_comment(comment, rid, names):
    """('description'|'note'|'name-only', reason). Only 'description' may fill an empty description."""
    c = (comment or "").strip()
    if not c: return "note", "empty"
    low = c.lower()
    if low.startswith(NOTE_START) or "$home" in low or re.search(r"\b\w+\.(bin|rom)\b", low): return "note", "setup or status note"
    if rid in NAME_ONLY: return "name-only", NAME_ONLY[rid]
    keep = []
    for w in c.split():                                   # drop version strings, (0.37b5) and the like, whole
        if re.match(r"^\(?v?\d", w, re.I): continue
        keep += [t for t in re.findall(r"[a-z0-9]+", w.lower()) if t not in ("for", "libretro", "a", "an", "the", "of")]
    rest = "".join(keep)
    if not rest or any(rest in norm(n) for n in names if n): return "name-only", "the app's own name (and \"for Libretro\" or a version)"
    return "description", ""


def load(path=EVIDENCE):
    p = Path(path)
    if not p.is_file(): return {}
    return {r["id"]: r for r in json.loads(p.read_text(encoding="utf-8"))["records"]}


def strip(c):
    """remove what enrich() added earlier, so a second run starts from the original entry"""
    if str(c.get("description_source", "")).startswith(SOURCE): c["description"] = ""
    for k in ("description_source", "package_metadata", "metadata_review", "icon_file"): c.pop(k, None)
    if c.get("category_basis") and VERDICT_SEP in c["category_basis"]: c["category_basis"] = c["category_basis"].split(VERDICT_SEP)[0]


def enrich(c, rec):
    strip(c)
    if not rec: return None
    d, review = rec["desktop"], {}
    cls = rec["comment_class"]
    if d["comment"] and cls == "description":
        shown = rec.get("display_comment") or d["comment"]
        if not c["description"]: c["description"] = shown; c["description_source"] = SOURCE_EDITED if shown != d["comment"] else SOURCE
        elif norm(d["comment"]) != norm(c["description"]) and not norm(c["description"]).startswith(norm(d["comment"])):
            review["description"] = {"package_comment": d["comment"], "kept": "existing description"}
    if d["name"] and norm(d["name"]) != norm(c["name"]): review["name"] = {"package_name": d["name"], "listed": c["name"], "applied": False}
    first = (d["categories"] or "").split(";")[0].lower()
    sec = SECTION.get(first)
    reviewed = bool(c.get("category") and c.get("category_basis"))
    row = c["category"] if reviewed else derive_category(c["name"], c["description"], c.get("topics"))
    verdict = ("agrees" if sec == row else "differs") if sec else ("generic" if first == "applications" else "unmapped" if first else "none")
    if verdict in ("differs", "unmapped"): review["category"] = {"package": d["categories"], "row": CAT_NAME[row], "applied": False}
    if reviewed and verdict != "none":
        b = c["category_basis"] + VERDICT_SEP + verdict
        if len(b) <= BASIS_MAX: c["category_basis"] = b
    c["package_metadata"] = {"source": "package .desktop", "package": rec["package"], "name": d["name"], "comment": d["comment"], "comment_class": cls,
                             **({"display_comment": rec["display_comment"], "display_comment_reason": rec["display_comment_reason"]} if rec.get("display_comment") else {}),
                             **({"comment_reason": rec["comment_reason"]} if rec.get("comment_reason") else {}), "categories": d["categories"],
                             "category_evidence": {"maps_to": CAT_NAME[sec] if sec else None, "row_category": CAT_NAME[row], "row_category_reviewed": reviewed, "verdict": verdict},
                             "icon": rec["icon"], **({"multiple_desktop_files": True} if rec.get("multiple_desktop_files") else {})}
    if rec["icon"].get("available") and rec["icon"].get("sha256") and rec["icon"].get("redistribution", {}).get("status") == "redistributable":   # recorded hash AND a clear right to ship it; the Nano UI shows it
        c["icon_file"] = "icons/%s.%s" % (rec["id"], rec["icon"]["format"].lower())
    if review: c["metadata_review"] = review
    return {"description": "description_source" in c, "verdict": verdict, "name": "name" in review}


# ---- icon redistribution rights ---------------------------------------------------------------------------------------
STATUSES = ("redistributable", "unclear", "restricted")
# Only an entry here can make an icon "redistributable"/"restricted": it needs evidence naming the icon (or its asset folder) and the licence
# that covers it. Nothing qualifies today: no audited icon carries an icon-specific licence or credit.
RIGHTS_OVERRIDE = {}
_DEFAULT = "No licence, credit or notice for the icon was found, and the package contents were not kept for a second look. The package's own licence is unknown and is not assumed to cover its artwork."
_MIT_REPO = "Repository is MIT (GitHub licence field). No notice names the icon's author or source, so the MIT grant is not assumed to cover this artwork."
_NOTES = {
    "funkoban": _MIT_REPO + " The package ships licence notices for its fonts (Roboto, Space Mono) only, none for graphics.",
    "cglpsdl1": _MIT_REPO, "wiki-blips": _MIT_REPO + " The game is a remake of another author's DOS game.", "wiki-blockdude": _MIT_REPO + " The game is a remake of another author's game.",
    "wiki-formula1": _MIT_REPO, "wiki-rubido": _MIT_REPO, "wiki-znax": _MIT_REPO + " The game is a remake of another author's Flash game.",
    "sudokul": "Repository is MIT (GitHub licence field). The package's strings point to opengameart.org for art and sound; the licence of this picture was not identified.",
    "j2mefunkeyrgnano": "Repository declares no licence. The package's only notice (NOTICE-JavaMobileAudio.txt, GPLv2) covers a Java audio library, not this icon.",
    "wiki-mplayer": "The package README credits the port author and thanks others; it states no licence for the artwork.",
}
_INSPECTED = {"funkoban", "sudokul", "j2mefunkeyrgnano", "wiki-mplayer"}   # package files still on hand when this was written; the rest were deleted after probing


def icon_rights(rid, repo_license):
    if rid in RIGHTS_OVERRIDE: return RIGHTS_OVERRIDE[rid]
    return {"status": "unclear", "evidence": _NOTES.get(rid, _DEFAULT), "source_license": repo_license or "unknown",
            "package_files_inspected": rid in _INSPECTED}
