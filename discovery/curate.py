#!/usr/bin/env python3
"""Curate the Android DEV catalog from the discovery inventory. Reproducible: the tracked output is candidates/android-curated.json (every fact needed to rebuild the signed DEV
catalog, no network), the complete discovery inventory stays separate (build/discovery/android-500-candidates.json, candidates/reports/).

  python discovery/curate.py select [--inventory build/discovery/android-500-candidates.json]   pick ~130 apps, decide install vs external listing (offline)
  python discovery/curate.py inspect [--workers 4]                                               download each install-eligible APK once, read package/versionCode/signer/SHA-256
  python discovery/curate.py check                                                               validate the curated file against the catalog policy rules (offline)
  python android/tools/dev_fixture.py curated                                                    sign candidates/android-curated.json into the bundled DEV catalog

Direct install is offered ONLY when every trust-policy condition holds (a GitHub release download of the entry's own repository, a known licence that allows redistribution, a
stable tag, an APK whose package, versionCode, signer and SHA-256 were read from the file, minSdk <= 31 and an ABI the RG Rotate has). Everything else that is legitimate is an
EXTERNAL LISTING: a link and the reason, no download, no hash, no install button. Nothing here approves, signs for production, or publishes.
"""
import argparse, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "tools"))
import categories as CAT, mainstream as M, android_import as A

OUT = ROOT / "candidates" / "android-curated.json"
INV = ROOT / "build" / "discovery" / "android-500-candidates.json"
QUOTA = {"emulators": 45, "ports": 40, "games": 40, "themes-launchers": 25, "utilities": 45, "media": 25}
RECENT = "2024-11-01"                    # non-seed apps must have a release in the last ~two years
RECENT_EMU = "2019-01-01"                # standalone emulators change slowly; an older one is listed with a "not updated since" flag
ROLLING = C_ROLLING = re.compile(r"continuous|nightly|latest|snapshot|pre-?release|beta|dev", re.I)
NO_REDIST = re.compile(r"-NC|NonCommercial|NC-ND|proprietary|unlicensed|unverified|none|unknown|noassertion", re.I)
NO_INSTALL_PKG = {"xyz.aethersx2.android": "A patched build of the closed-source, abandoned AetherSX2: the right to redistribute the APK is unclear, so RetroHatch only links to the project."}
SEED_REPO_LICENSE = {v["id"]: (v.get("repo_meta") or {}).get("license") for v in json.loads((ROOT / "build" / "discovery" / "mainstream-verified.json").read_text(encoding="utf-8"))["apps"]} if (ROOT / "build" / "discovery" / "mainstream-verified.json").is_file() else {}
MAX_APK = 160 * 1024 * 1024
LIGHT_PLATFORMS = {"n64", "snes", "nes", "gba", "gbc", "gb", "ps1", "genesis", "ds", "psp", "dos", "amiga", "32x"}      # original platforms a T618-class handheld is most likely to cope with
HEAVY_PLATFORMS = {"xbox360", "xbox", "switch", "ps4", "wiiu", "ps2", "gamecube", "wii", "3ds"}
RECOMPA_CAP = 12                       # community ports are many and heavy: cap them so the catalog is not a port list
# reviewed false positives of the keyword rules (an "emulates gestures" app, a weather app that mentions moonlight, a root-only SMB server, ...)
DENY = {"Timed Shutdown [No Root]", "GeoJoystick", "Suntimes", "DebForge", "SeekPrivacy", "SimbaDroid", "LetterBox", "SuperShopaholic", "AeroPayout", "Janken (Rock Paper Scissors)", "Burger Party", "Bim!",
        "Authorizer", "Accordion", "Melodeon", "Android Virtual Pen", "Holey Light", "Android USB Script", "Astro Loop", "AuraOrbit", "ConnectFour Studio", "Tennis Score Manager", "RootlessJamesDSP", "werewolves_game", "Orion Master", "Live Wallpaper Dino Game", "Dino Game"}
OFFICIAL_HOSTS = {"buildbot.libretro.com": "libretro buildbot", "www.ppsspp.org": "ppsspp.org", "downloads.duckstation.org": "downloads.duckstation.org", "dl.dolphin-emu.org": "dolphin-emu.org"}
HAND = {"com.beemdevelopment.aegis": "aegis", "com.looker.droidify": "droidify", "org.fossify.gallery": "gallery", "com.swordfish.lemuroid": "lemuroid", "me.zhanghai.android.files": "materialfiles",
        "me.magnum.melonds": "melonds", "org.schabi.newpipe": "newpipe", "dev.imranr.obtainium": "obtainium"}


# ---- trusted sources (mirror of android/.../model/TrustedSources.kt; tests/test_curate.py keeps the two in step) ----------------------------------------------------------
PINS = json.loads((HERE / "trusted_sources.json").read_text(encoding="utf-8"))
OFFICIAL = PINS["official_servers"]


def source_kind(source, url, pkg, vc):
    """-> github | gitlab | codeberg | fdroid | izzy | official | None. The same rules the app's catalog policy applies to a signed entry."""
    if not url or not url.startswith("https://") or any(c <= " " or c == "\\" or ord(c) >= 0x7F for c in url) or "@" in url.split("://", 1)[1].split("/", 1)[0]: return None
    src = (source or "").rstrip("/")
    src = src[:-4] if src.endswith(".git") else src
    low = url.lower()
    if re.fullmatch(r"https://github\.com/[^/\s]+/[^/\s]+", src or "") and M.release_ok(src, url): return "github"
    m = re.fullmatch(r"https://gitlab\.com/([^\s]+/[^\s/]+)", src)
    if m:
        base = f"https://gitlab.com/{m.group(1)}".lower()
        if (low.startswith(base + "/-/releases/") and "/downloads/" in low) or low.startswith(base + "/uploads/"): return "gitlab"
    m = re.fullmatch(r"https://codeberg\.org/([^/\s]+)/([^/\s]+)", src)
    if m and re.fullmatch(re.escape(f"https://codeberg.org/{m.group(1)}/{m.group(2)}".lower()) + r"/releases/download/[^/\s]+/[^/\s]+", low): return "codeberg"
    if pkg and vc is not None:
        if url == f"https://f-droid.org/repo/{pkg}_{vc}.apk": return "fdroid"
        if url == f"https://apt.izzysoft.de/fdroid/repo/{pkg}_{vc}.apk": return "izzy"
        pre = OFFICIAL.get(pkg)
        if pre and url.startswith(pre) and len(url) > len(pre) and ".." not in url and "?" not in url and "#" not in url: return "official"
    return None


def _tool(name):
    import shutil, os
    t = shutil.which(name) or (str(Path(os.environ.get("JAVA_HOME", "")) / "bin" / (name + (".exe" if os.name == "nt" else ""))) if os.environ.get("JAVA_HOME") else None)
    if not t or not Path(t).exists(): raise SystemExit(f"{name} (JDK) is required to verify repository metadata")
    return t


_INDEX = {}


def verified_index(kind):
    """Repository metadata ONLY after its authenticity is established: the signed entry.jar must verify (jarsigner) with the pinned certificate fingerprint (keytool), and the index file
    must hash to the SHA-256 in the signed entry.json. -> {package: latest version facts}. Raises SystemExit when anything differs."""
    import subprocess, tempfile, hashlib
    if kind in _INDEX: return _INDEX[kind]
    pin = PINS["repos"][kind]
    with tempfile.TemporaryDirectory() as t:
        jar = Path(t) / "entry.jar"
        st, _, _, b = M.get(pin["repo"] + "/entry.jar", n=5_000_000)
        if st != 200: raise SystemExit(f"{kind}: entry.jar HTTP {st}")
        jar.write_bytes(b)
        v = subprocess.run([_tool("jarsigner"), "-verify", str(jar)], capture_output=True, text=True)
        if "jar verified" not in v.stdout + v.stderr: raise SystemExit(f"{kind}: entry.jar signature does not verify")
        fp = re.search(r"SHA256:\s*([0-9A-F:]{95})", subprocess.run([_tool("keytool"), "-printcert", "-jarfile", str(jar)], capture_output=True, text=True).stdout)
        if not fp or fp.group(1).upper() != pin["fingerprint_sha256"].upper(): raise SystemExit(f"{kind}: entry.jar is signed by {fp and fp.group(1)}, not the pinned certificate")
        import zipfile
        entry = json.loads(zipfile.ZipFile(jar).read("entry.json"))
    st, _, _, idx = M.get(pin["repo"] + entry["index"]["name"], n=200_000_000)
    if st != 200 or hashlib.sha256(idx).hexdigest() != entry["index"]["sha256"]: raise SystemExit(f"{kind}: the index does not match the SHA-256 in the signed entry.json")
    pk = json.loads(idx)["packages"]
    out = {}
    for name, p in pk.items():
        if not p.get("versions"): continue
        v = max(p["versions"].values(), key=lambda x: x["manifest"].get("versionCode", 0)); mf = v["manifest"]
        out[name] = {"url": f"{pin['repo']}/{name}_{mf['versionCode']}.apk", "file": v["file"]["name"].lstrip("/"), "sha256": v["file"]["sha256"], "size": v["file"]["size"], "version_code": mf["versionCode"],
                     "version_name": mf.get("versionName", ""), "min_sdk": (mf.get("usesSdk") or {}).get("minSdkVersion", 1), "abis": mf.get("nativecode") or [], "signers": (mf.get("signer") or {}).get("sha256", []),
                     "anti": sorted((v.get("antiFeatures") or {}))}
    _INDEX[kind] = out
    print(f"  {kind}: entry.jar verified against the pinned certificate; index hash matches ({len(out)} packages)", flush=True)
    return out


def slug(name, taken):
    import unicodedata
    base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("-")[:48] or "app"
    i, cand = 2, base
    while cand in taken: cand = f"{base}-{i}"; i += 1
    return cand


def recent(r): return (r["released"] or "") >= RECENT


SEEDS = {s["name"]: s for s in json.loads((HERE / "mainstream.json").read_text(encoding="utf-8"))["apps"]}


_DESC = {}
_DESC_FILE = ROOT / "build" / "discovery" / "cache" / "repodesc.json"
if _DESC_FILE.is_file(): _DESC.update(json.loads(_DESC_FILE.read_text(encoding="utf-8")))


def repo_description(rid):
    """The project's own one-line GitHub description (the page's og:description). Used only when no index carries a summary."""
    if rid in _DESC: return _DESC[rid]
    t = _repo_description(rid)
    _DESC[rid] = t
    return t


def _repo_description(rid):
    st, _, h = M.text(f"https://github.com/{rid.split(':', 1)[1]}", 200_000)
    m = re.search(r'<meta property="og:description" content="([^"]+)"', h) or re.search(r'<meta name="description" content="([^"]+)"', h)
    if not m: return None
    t = re.sub(r"\s*(?:-|·)\s*GitHub.*$", "", m.group(1).replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")).strip()
    t = re.sub(r"\s*Contribute to .*$", "", t)
    return t[:200] if len(t) >= 15 else None


def describe(r):
    """A short description from what a source says. Never written by hand and never invented: no source text, no entry."""
    seed0 = SEEDS.get(r["name"]) or next((x for x in SEEDS.values() if x["package"] and x["package"] == r["package"]), None)
    if seed0 and seed0["systems"] and seed0["group"] == "emulators" and "mainstream-seed" in r["sources"]: return f"Emulator for {', '.join(seed0['systems'])}."[:200]
    t = (r.get("summary") or "").strip()
    if len(t) >= 15: return t[:200]
    if "recompa" in r["sources"]:
        g = re.search(r"native Android (.+?) of (.+)", (r["reasons"] or [""])[0])
        if g: return f"Native Android {g.group(1)} of {g.group(2)}. You supply your own original game files."[:200]
    seed = SEEDS.get(r["name"]) or next((x for x in SEEDS.values() if x["package"] and x["package"] == r["package"]), None)
    if seed and seed["systems"] and seed["group"] == "emulators": return f"Emulator for {', '.join(seed['systems'])}."[:200]
    if seed and seed["group"] == "themes-launchers": return "Frontend and launcher for your game library."
    rid = A.repo_id(r["repo"] or r["official_url"])
    if rid and rid.startswith("github:"): return repo_description(rid)
    return None


def score(r):
    s = r["rank"]
    if "rgc-guide" in r["sources"] or "retrohandhelds-rotate" in r["sources"] or "mainstream-seed" in r["sources"]: s += 3
    if r.get("reports"): s += min(2, (r["reports"]["great"] + r["reports"]["playable"]) / 2)
    plat = (r.get("notes") or "").replace("original platform: ", "")
    if "recompa" in r["sources"]: s += 2 if plat in LIGHT_PLATFORMS else (-1.5 if plat in HEAVY_PLATFORMS else 0)
    if recent(r): s += 1
    if r["license"] and not NO_REDIST.search(r["license"]): s += 1
    if r["status"] == "needs_verification": s -= 2
    if "fork" in r["flags"] or "archived" in r["flags"]: s -= 1.5
    return s


def eligible(r):
    """-> (install candidate?, reason if external). Final decision happens after the APK was inspected."""
    rid = A.repo_id(r["repo"] or r["official_url"])
    if r["status"] == "external_listing": return False, r.get("notes") or "Paid or store-only software: no direct APK from the developer."
    if not r["apk_url"]: return False, "No direct APK found."
    if r["package"] in NO_INSTALL_PKG: return False, NO_INSTALL_PKG[r["package"]]
    host = re.match(r"https?://([^/]+)", r["apk_url"]).group(1)
    if host in OFFICIAL_HOSTS and r["package"] not in OFFICIAL: return False, f"The official download is hosted on {OFFICIAL_HOSTS[host]}, which is not a pinned source for this app (pinned official servers: " + ", ".join(sorted({u.split('/')[2] for u in OFFICIAL.values()})) + ")."
    if not r["license"] or NO_REDIST.search(r["license"]):
        return False, ("The licence forbids redistribution or is not free; use the official download." if r["license"] and re.search(r"-NC|NonCommercial|proprietary", r["license"], re.I)
                       else "No licence was found; RetroHatch does not install unlicensed software.")
    if r["status"] != "verified": return False, "Download or compatibility details are incomplete."
    if ROLLING.search(r["version"] or ""): return False, "Rolling or pre-release build: not pinned to a stable release."
    if (r["apk_size"] or 0) > MAX_APK: return False, "The APK is larger than RetroHatch downloads (200 MB)."
    src = "https://github.com/" + rid.split(":", 1)[1] if rid and rid.startswith("github:") else (r["official_url"] or r["repo"])
    if rid and rid.startswith("github:") and M.release_ok(src, r["apk_url"]): return True, ""
    kind = host_kind(r)
    if kind in ("fdroid", "izzy"): return True, ""                      # facts come from the verified repository index (see select)
    if kind in ("gitlab", "codeberg", "official"): return None, ""      # inspected like a GitHub release
    if rid and rid.startswith("github:"): return None, "GitHub repo but the listed APK is not a release of it (resolved at inspect time)"
    return False, f"No trusted source for this download ({host}): RetroHatch installs from GitHub, GitLab or Codeberg releases of the app's own repository, the F-Droid and IzzyOnDroid repositories, and pinned official servers."


def host_kind(r):
    """Which trusted source (if any) serves this record's APK."""
    pkg = r["package"]
    rid = A.repo_id(r["repo"] or r["official_url"])
    src = ("https://" + {"github": "github.com", "gitlab": "gitlab.com", "codeberg": "codeberg.org"}[rid.split(":", 1)[0]] + "/" + rid.split(":", 1)[1]) if rid else (r["official_url"] or "")
    for kind, base in (("fdroid", "https://f-droid.org/repo/"), ("izzy", "https://apt.izzysoft.de/fdroid/repo/")):
        if r["apk_url"].startswith(base) and kind in r["sources"] and pkg: return kind
    return source_kind(src, r["apk_url"], pkg, None) or (source_kind(src, r["apk_url"], pkg, 0) if r["apk_url"].startswith(tuple(OFFICIAL.values())) else None)


def external_for(r, why):
    pkg = r["package"]
    if "fdroid" in r["sources"] and pkg: label, url = "F-Droid", f"https://f-droid.org/packages/{pkg}/"
    elif "izzy" in r["sources"] and pkg: label, url = "IzzyOnDroid", f"https://apt.izzysoft.de/fdroid/index/apk/{pkg}"
    elif r["official_url"].startswith("https://"): label, url = ("Google Play" if "play.google.com" in r["official_url"] else "Official page"), r["official_url"]
    elif r["repo"].startswith("https://"): label, url = "Project page", r["repo"]
    else: return None
    return {"label": label, "url": url, "reason": why[:236], "price": (r["price"] if r["price"] and r["price"] != "free" else None)}


def select(a):
    inv = json.loads(Path(a.inventory).read_text(encoding="utf-8"))["candidates"]
    old = {x["package"]: x for x in (json.loads(OUT.read_text(encoding="utf-8"))["apps"] if OUT.is_file() else [])}
    hand = json.loads((ROOT / "candidates" / "descriptions-rg-rotate.json").read_text(encoding="utf-8"))["apps"]
    by_pkg = {}
    for r in inv:
        if r["package"] or r["status"] == "external_listing": by_pkg.setdefault(r["package"] or r["name"], r)
    chosen, used_repo, per = [], set(), {g: 0 for g in QUOTA}
    pool = sorted([r for r in inv if (r["package"] or r["status"] == "external_listing") and (r["status"] != "needs_verification" or "mainstream-seed" in r["sources"] or "retrohandhelds-rotate" in r["sources"])],
                  key=lambda r: -score(r))
    for r in pool:                                                        # seed licences: what GitHub reports for the project (the seed file only says "unverified")
        if (r["license"] or "").lower() == "unverified":
            seed = SEEDS.get(r["name"]); lic = SEED_REPO_LICENSE.get(seed["id"]) if seed else None
            if lic and lic not in ("NOASSERTION", "none"): r["license"] = lic
    need = [A.repo_id(r["repo"] or r["official_url"]) for r in pool if not (r.get("summary") or "").strip() and A.repo_id(r["repo"] or r["official_url"])]
    with ThreadPoolExecutor(8) as ex: list(ex.map(repo_description, [n for n in need if n and n.startswith("github:") and n not in _DESC]))
    _DESC_FILE.write_text(json.dumps(_DESC), encoding="utf-8")
    seeds = [r for r in pool if r["package"] in HAND or "mainstream-seed" in r["sources"] or "retrohandhelds-rotate" in r["sources"]]
    for r in seeds + pool:
        g = r["group"]
        if r["name"] in DENY or r["name"].replace("\ufeff", "") in DENY: continue
        if g == "games" and not any(("gamepad" in x or "retro" in x) for x in r["reasons"]): continue          # explicit handheld/retro evidence only
        if "recompa" in r["sources"] and sum(1 for c, _ in chosen if "recompa" in c["sources"]) >= RECOMPA_CAP: continue
        if g not in QUOTA or per[g] >= QUOTA[g] and r not in seeds: continue
        if r in [c for c in chosen]: continue
        key = r["project"] or A.repo_id(r["repo"] or r["official_url"]) or r["package"] or r["name"]
        if key in used_repo: continue                                                         # one entry per upstream project (icon-pack variants, flavours)
        if not recent(r) and not ({"mainstream-seed", "retrohandhelds-rotate"} & set(r["sources"])) and r["package"] not in HAND and not (g == "emulators" and (r["released"] or "") >= RECENT_EMU): continue
        desc = describe(r)
        if desc is None and r["package"] in HAND: desc = hand[HAND[r["package"]]]["description"]
        if not desc: continue
        used_repo.add(key); per[g] = per.get(g, 0) + 1; chosen.append((r, desc))
    taken, apps = set(HAND.values()), []
    for r, desc in chosen:
        ok, why = eligible(r)
        pkg = r["package"]
        e = old.get(pkg) or {}
        aid = e.get("id") or HAND.get(pkg) or slug(r["name"], taken); taken.add(aid)
        rid = A.repo_id(r["repo"] or r["official_url"])
        source = "https://github.com/" + rid.split(":", 1)[1] if rid and rid.startswith("github:") else (r["official_url"] if r["official_url"].startswith("https://") else r["repo"])
        entry = {"id": aid, "name": r["name"].replace("﻿", "").strip()[:60], "group": r["group"], "tags": r["tags"][:8], "description": desc, "developer": (r["developer"] or (rid.split(":", 1)[1].split("/")[0] if rid else "unknown"))[:60],
                 "source": source, "license": r["license"] or "unknown", "package": pkg, "released": r["released"][:10] if r["released"] else "", "version": r["version"],
                 "recommended_by": [x for x in ("rgc-guide", "retrohandhelds-rotate", "mainstream-seed") if x in r["sources"]], "sources": r["sources"], "reasons": r["reasons"][:2],
                 "min_sdk": r["min_sdk"], "abis": r["abis"], "needs_game_files": r["needs_game_files"], "flags": ([f"not updated since {r['released'][:7]}"] if r["released"] and r["released"] < RECENT and g == "emulators" else []) + [f for f in r["flags"] if not f.startswith("also published")][:4], "added": e.get("added") or "2026-11-09"}
        kind = host_kind(r) if ok is not False else None
        if ok is True and kind in ("fdroid", "izzy"):                      # facts from the authenticated repository index: no download needed, the app re-checks the file on the device
            facts = verified_index(kind).get(pkg)
            if facts and facts["min_sdk"] <= 31 and (not facts["abis"] or set(facts["abis"]) & A.ROTATE_ABIS) and facts["signers"] and not ROLLING.search(facts["version_name"] or ""):
                entry["mode"] = "install"; entry["apk"] = {**{k: facts[k] for k in ("url", "file", "sha256", "size", "version_code", "version_name", "min_sdk", "abis", "signers")}, "tag": facts["version_name"],
                                                          "source_kind": kind, "sha256_inspected": f"{kind} index (entry.jar signature verified against the pinned certificate)"}
                entry["needs"] = ["device testing"]; entry["version"] = facts["version_name"]
                if facts["anti"]: entry["flags"] = (entry.get("flags", []) + ["anti-features: " + ", ".join(facts["anti"])])[:5]
                apps.append(entry); continue
            ok, why = False, f"{kind} index does not carry a compatible, stable build of this package."
        if ok is True or ok is None:
            entry["mode"] = "install"; entry["apk"] = e.get("apk") or {"url": r["apk_url"], "file": r["apk_file"], "tag": r["version"], "size": r["apk_size"], "sha256": r["apk_sha256"]}
            entry["fallback_external"] = external_for(r, why or "Could not be verified for direct install.")
            entry["needs"] = ["device testing"]
        else:
            ext = external_for(r, why)
            if not ext: continue
            entry["mode"] = "external"; entry["external"] = ext
            entry["needs"] = ["source approval" if "trust policy" in why or "package repository" in why else "legal/licence review" if "licence" in why else "direct APK source", "device testing"]
        apps.append(entry)
    apps = finalize(add_hand(apps))
    doc = {"schema": 1, "generated": date.today().isoformat(), "device": "rg-rotate", "device_abis": sorted(A.ROTATE_ABIS),
           "note": "Curated from build/discovery/android-500-candidates.json (reproducible with discovery/curate.py). mode=install entries carry the APK facts read from the file; mode=external entries are listings only. Leads, never approvals.",
           "apps": sorted(apps, key=lambda x: (x["group"], x["name"].lower()))}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    c = {m: sum(1 for x in apps if x["mode"] == m) for m in ("install", "external")}
    print(f"{len(apps)} apps selected -> {OUT}: {c}; per group {dict((g, sum(1 for x in apps if x['group']==g)) for g in QUOTA)}")


def inspect(a):
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    if a.retry:                                                    # entries demoted for a reason that has since been fixed go back through the inspection
        for x in doc["apps"]:
            r = (x.get("external") or {}).get("reason", "")
            if x["mode"] == "external" and re.match(r"Not installable here: (package differs|inspect failed)", r):
                x["fallback_external"] = {**x["external"], "reason": r.split(". ", 1)[-1] if ". " in r else r}
                x["mode"] = "install"; x.pop("external"); x["apk"] = {"url": "", "file": "", "tag": "", "size": None, "sha256": ""}
    todo = [x for x in doc["apps"] if x["mode"] == "install" and not x["apk"].get("sha256_inspected")]
    print("inspecting", len(todo), "APKs (downloaded one at a time per worker, deleted after reading)", flush=True)
    def work(x):
        ap = x["apk"]
        url = ap["url"]
        rid = A.repo_id(x["source"])
        if source_kind(x["source"], url, x["package"], None) or source_kind(x["source"], url, x["package"], 0): pass                  # a trusted source already
        elif not (rid and rid.startswith("github:") and M.release_ok(x["source"], url)):     # a package-repository URL: look for the same build in the project's own GitHub release
            rel = A.github_release(rid.split(":", 1)[1]) if rid and rid.startswith("github:") else None
            if not rel or not rel.get("apk"): return x, "no APK in the project's own latest GitHub release"
            url = rel["url"]; ap.update(file=rel["apk"], tag=rel["tag"], url=url)
        try: info = M.inspect_apk(x["id"], url, ROOT / "build" / "discovery")
        except Exception as e: return x, "inspect failed: " + str(e)[:80]
        if "error" in info: return x, "inspect failed: " + info["error"]
        if x["package"] and info["package"] != x["package"]: x["flags"] = x.get("flags", []) + [f"index lists {x['package']}; the project's own release is {info['package']}"][:1]     # the file decides
        if not info["fits"]["rg_rotate_android12_arm64"] or not info["signers_sha256"]: return x, "does not fit RG Rotate or has no valid signer"
        if C_ROLLING.search(ap.get("tag") or "") or C_ROLLING.search(info["version_name"] or ""): return x, "the latest release is a beta / rolling build, not a pinned stable release"
        if info["abis"] and not (set(info["abis"]) & A.ROTATE_ABIS): return x, "native code for none of the device's ABIs"
        ap.update(sha256=info["sha256"], size=info["size"], version_code=info["version_code"], version_name=info["version_name"], min_sdk=info["min_sdk"], abis=info["abis"],
                  signers=info["signers_sha256"], sha256_inspected=date.today().isoformat())
        x["package"] = info["package"]; x["version"] = info["version_name"] or x["version"]
        return x, None
    with ThreadPoolExecutor(a.workers) as ex: results = list(ex.map(work, todo))
    demoted = 0
    for x, err in results:
        if err:
            demoted += 1
            ext = x.pop("fallback_external", None)
            if ext: x["mode"] = "external"; x["external"] = {**ext, "reason": f"Not installable here: {err}. " + ext["reason"]}; x.pop("apk", None); x["needs"] = ["source approval", "device testing"]
            else: x["flags"] = x.get("flags", []) + [err]
            print("  demoted to external:", x["name"], "-", err)
    seen = {}
    for x in doc["apps"]:
        if x["mode"] == "install" and x["package"]:
            if x["package"] in seen:                                # two entries resolved to one package id: keep the first, the other becomes a flag-only duplicate and is dropped
                x["mode"] = "drop"; print("  duplicate package dropped:", x["name"], "=", seen[x["package"]])
            else: seen[x["package"]] = x["name"]
    doc["apps"] = finalize(add_hand([x for x in doc["apps"] if x["mode"] != "drop"]))
    for x in doc["apps"]: x.pop("fallback_external", None) if x["mode"] == "external" or x["apk"].get("sha256_inspected") else None
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    c = {m: sum(1 for x in doc["apps"] if x["mode"] == m) for m in ("install", "external")}
    print("inspected", len(todo), "demoted", demoted, c)


def add_hand(apps):
    """The eight apps with hand-written descriptions (candidates/descriptions-rg-rotate.json) are always present. Their APK facts come from candidates/inventory-rg-rotate.json
    (identity read from the files with tools/apk_inspect.py); a selection run that did not pick one of them gets it from there."""
    hand = json.loads((ROOT / "candidates" / "descriptions-rg-rotate.json").read_text(encoding="utf-8"))["apps"]
    inv = {a["packages"][0]["android"]["package"]: a for a in json.loads((ROOT / "candidates" / "inventory-rg-rotate.json").read_text(encoding="utf-8"))["applications"] if a.get("packages")}
    have = {x["package"] for x in apps}
    for pkg, hid in HAND.items():
        if pkg in have or pkg not in inv: continue
        a = inv[pkg]; pk = a["packages"][0]; ev = a["evidence"]["apk"]
        repo = a["sources"][0]["url"]
        apps.append({"id": hid, "name": a["name"], "group": a.get("group") or "utilities", "tags": a.get("tags", [])[:8], "description": hand[hid]["description"], "developer": repo.split("/")[3], "source": repo,
                     "license": a["license"], "package": pkg, "released": ev and a["evidence"]["release"]["published"][:10], "version": a["version"], "recommended_by": [], "sources": ["inventory"],
                     "reasons": ["one of the eight apps with hand-written descriptions"], "min_sdk": ev["min_sdk"], "abis": ev["abis"], "needs_game_files": "unknown", "flags": [], "added": "2026-11-09", "mode": "install",
                     "apk": {"url": pk["url"], "file": pk["name"], "tag": a["evidence"]["release"]["tag"], "size": pk["size"], "sha256": pk["sha256"], "version_code": pk["android"]["version_code"], "version_name": a["version"],
                             "min_sdk": ev["min_sdk"], "abis": ev["abis"], "signers": pk["android"]["signer_sha256"], "sha256_inspected": "2026-11-09 (candidates/inventory-rg-rotate.json)"}, "needs": ["device testing"]})
    return apps


def apply_holds(apps):
    """An inventory entry that a person put ON HOLD (licence not detected, suspicious signing certificate, ...) is never offered for install: it becomes an external listing with the hold as the reason."""
    holds = {}
    for a in json.loads((ROOT / "candidates" / "inventory-rg-rotate.json").read_text(encoding="utf-8"))["applications"]:
        if a.get("hold") and a.get("packages"): holds[a["packages"][0]["android"]["package"]] = a["hold"]
    for x in apps:
        if x["package"] in holds and x["mode"] == "install":
            url = x["source"]
            x["mode"] = "external"; x.pop("apk", None); x.pop("fallback_external", None)
            x["external"] = {"label": "Project page", "url": url, "reason": "On hold for review: " + holds[x["package"]] + ". RetroHatch does not install it until that is resolved.", "price": None}
            x["needs"] = ["source approval", "device testing"]
    return apps


def finalize(apps):
    """One entry per package id (installable beats external, then the more recommended) and unique ids. A package id names ONE installed app on the device."""
    apps = apply_holds(apps)
    best = {}
    for x in apps:
        if x["package"] in HAND: x["id"] = HAND[x["package"]]
        k = x["package"] or x["id"]
        score = (x["mode"] == "install", len(x.get("recommended_by", [])))
        if k not in best or score > best[k][0]: best[k] = (score, x)
    keep = [v[1] for v in best.values()]
    ids = {}
    for x in keep:
        base = x["id"]; i = 2
        while x["id"] in ids: x["id"] = f"{base}-{i}"; i += 1
        ids[x["id"]] = x
    return sorted(keep, key=lambda x: (x["group"], x["name"].lower()))


def check(a):
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    errs, ids, pkgs = [], set(), set()
    for x in doc["apps"]:
        w = x["id"]
        if w in ids: errs.append(f"{w}: duplicate id")
        ids.add(w)
        if x["package"] and x["package"] in pkgs: errs.append(f"{w}: duplicate package {x['package']}")
        pkgs.add(x["package"])
        if x["group"] not in CAT.GROUP_IDS: errs.append(f"{w}: group")
        if x["mode"] == "install":
            ap = x["apk"]
            if not all(ap.get(k) for k in ("url", "sha256", "size", "version_code", "signers")): errs.append(f"{w}: install entry without full APK identity")
            elif not source_kind(x["source"], ap["url"], x["package"], ap["version_code"]): errs.append(f"{w}: url is not from a trusted source for this entry")
            if NO_REDIST.search(x["license"] or "unknown"): errs.append(f"{w}: licence '{x['license']}' cannot be installed")
            if ROLLING.search(ap.get("tag") or ""): errs.append(f"{w}: rolling tag")
            if ap.get("min_sdk", 99) > 31: errs.append(f"{w}: minSdk")
            if ap.get("abis") and not set(ap["abis"]) & A.ROTATE_ABIS: errs.append(f"{w}: ABI")
        else:
            e = x.get("external") or {}
            if "apk" in x or not e.get("url", "").startswith("https://") or not e.get("reason"): errs.append(f"{w}: external listing needs a url + reason and no apk")
    print(f"{len(doc['apps'])} entries checked, {len(errs)} problems")
    for e in errs[:20]: print("  ", e)
    sys.exit(1 if errs else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("select"); s.add_argument("--inventory", default=str(INV))
    i = sp.add_parser("inspect"); i.add_argument("--workers", type=int, default=4); i.add_argument("--retry", action="store_true")
    sp.add_parser("check"); sp.add_parser("finalize")
    a = ap.parse_args()
    if a.cmd == "finalize":
        doc = json.loads(OUT.read_text(encoding="utf-8")); doc["apps"] = finalize(add_hand(doc["apps"])); OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"); print(len(doc["apps"]), "entries"); return
    {"select": select, "inspect": inspect, "check": check}[a.cmd](a)


if __name__ == "__main__":
    main()
