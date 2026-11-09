#!/usr/bin/env python3
"""Large-scale Android candidate import for retro handhelds (RG Rotate first). Structured indexes first, search engines last. Third-party catalogs are LEADS:
every candidate's file is checked independently (4-byte range read), and where a package index does not carry the manifest it is read straight from the remote APK with
Range requests (central directory + AndroidManifest.xml; nothing is downloaded whole). Nothing here approves, signs, publishes or touches catalog/.

Sources: F-Droid index-v2, IzzyOnDroid index-v2, Recompa (Android native ports), Obtainium community configurations (GitHub: ImranR98/apps.obtainium.imranr.dev),
the Retro Handhelds RG Rotate Obtainium collection, Retro Game Corps' Android guide, discovery/mainstream.json (+ its verification) and discovery/search.py results.

Status: verified (a real APK from the project's repository/official server, package + minSdk + ABIs read, licence known) | needs_verification | external_listing (store/paid).
Verification is NOT device testing. Duplicates fold by package id, then by upstream repository + name. RetroArch cores are never candidates.

  python discovery/android_import.py [--out build/discovery] [--max-resolve 400] [--deadline 2400]
"""
import argparse, csv, json, random, re, struct, sys, time, zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "tools"))
import categories as CAT, mainstream as M
from apk_inspect import pick_asset

CACHE = ROOT / "build" / "discovery" / "cache"
API_LEVEL = 31
ROTATE_ABIS = {"arm64-v8a", "armeabi-v7a", "armeabi"}      # ro.product.cpu.abilist of the RG Rotate (read over adb 2026-11-09); 32-bit apps run, so they are NOT rejected
T0 = time.time()
LABEL = CAT.LABEL
SRC_URL = {"fdroid": "https://f-droid.org/repo/index-v2.json", "izzy": "https://apt.izzysoft.de/fdroid/repo/index-v2.json", "recompa": "https://recompa.app/index.json"}

# ---- relevance --------------------------------------------------------------------------------------------------------------
CONTROLLER = re.compile(r"gamepad|game ?pad|controller|joystick|d-?pad|hardware keyboard|physical (?:buttons|keyboard)|keyboard (?:support|control)|retro ?handheld", re.I)
RETRO = re.compile(r"\bretro\b|arcade|classic|8-?bit|16-?bit|pixel|roguelike|rogue-?like|platformer|metroidvania|text adventure|tetris|sokoban|pac-?man|breakout|space invaders|snake|dungeon crawler|shoot[- ']?em|beat[- ']?em|clone of|remake of|port of|nethack|\bdoom\b|\bquake\b", re.I)
EMU = re.compile(r"emulat|libretro|retroarch|dosbox|scummvm|\bmame\b|\bsimulator of (?:the )?(?:nes|snes|gba|n64)|game ?boy|\bgba\b|\bnes\b|\bsnes\b|mega ?drive|genesis|dreamcast|playstation|\bpsx\b|\bpsp\b|nintendo (?:ds|64|3ds)|\bn64\b|atari|commodore|\bc64\b|amiga|zx ?spectrum|\bmsx\b|neo ?geo|pc engine|wonderswan|\bsaturn\b", re.I)
PORT = re.compile(r"source ?port|\bports? of\b|game engine|engine (?:for|reimplementation)|reimplementation|re-?implementation|open[- ]source engine|recomp|decomp|openttd|opentyrian|\bdevilutionx\b|scummvm", re.I)
GAME_CATS = {"Action Game", "Board Game", "Card Game", "Casual Game", "Educational Game", "Party Game", "Platformer Game", "Puzzle Game", "Role-Playing Game", "Shooter Game", "Sport Game",
             "Strategy Game", "Word Game", "Visual Novel", "Game Helper"}
GENRE_OK = {"Platformer Game", "Role-Playing Game", "Shooter Game", "Strategy Game", "Action Game", "Sport Game", "Visual Novel"}
UTIL_CATS = {"File Manager", "File Transfer", "Cloud Storage & File Sync", "App Manager", "App Store & Updater"}     # the user's list: file managers, archives, backups, syncing, app management
UTIL_KW = re.compile(r"archive|\bzip\b|\brar\b|7-?zip|backup|rsync|syncthing|\bssh\b|\bsftp\b|terminal|\badb\b|key ?mapper|gamepad mapper|controller mapper|file (?:manager|explorer|browser)|webdav|\bsmb\b|storage", re.I)
MEDIA_CATS = {"Local Media Player", "Online Media Player"}              # music and video players; game streaming is matched by STREAM
STREAM = re.compile(r"game ?stream|moonlight|steam ?link|remote play|sunshine (?:server|host)|cloud gaming|stream your (?:pc|games)|\bkodi\b|\bplex\b|jellyfin", re.I)
LAUNCH_CATS = {"Launcher", "Icon Pack", "Theming"}
LAUNCH_KW = re.compile(r"launcher|(?:game|emulat\w*|retro|rom) (?:library|front-?end|collection|manager)|home ?screen|icon pack", re.I)


def classify(name, text, cats):
    """-> (group, reasons) when the app belongs in a retro-handheld catalog, else None. Reasons are the evidence; an app without any is not a candidate."""
    cats = set(cats or [])
    hay = f"{name} . {text}"
    r = []
    head0 = name + " . " + text.split(" . ")[0]
    if ("Emulator" in cats or re.search(r"emulat|libretro|retroarch", head0, re.I)) and (EMU.search(hay) or re.search(r"games?|retro|consoles?|handhelds?", hay, re.I))             and not re.search(r"terminal|smart ?card|nfc|elm327|calculator|gps|mock location|android emulator", head0, re.I):
        return "emulators", ["category Emulator and it plays games/console software" if "Emulator" in cats else "describes itself as an emulator/libretro frontend"]
    if cats & GAME_CATS:
        if PORT.search(hay): return "ports", ["engine / source port / reimplementation of an existing game"]
        if cats & {"Game Helper"} and not CONTROLLER.search(hay): return None
        if CONTROLLER.search(hay): r.append("mentions gamepad / controller / D-pad / keyboard control")
        if RETRO.search(hay): r.append("retro / arcade / classic game style")
        if not r and cats & GENRE_OK: r.append("genre that suits a handheld (" + sorted(cats & GENRE_OK)[0] + ")")
        return ("games", r) if r else None
    if PORT.search(hay) and re.search(r"game", hay, re.I): return "ports", ["engine / source port / reimplementation of an existing game"]
    head = name + " . " + text.split(" . ")[0]                          # name + one-line summary only: long descriptions mention launchers in passing
    if (cats & LAUNCH_CATS or LAUNCH_KW.search(head)) and re.search(r"launcher|(?:game|emulat\w*|retro|rom) (?:library|front-?end|collection)|icon pack", head, re.I):
        return "themes-launchers", ["launcher / frontend / icon pack"]
    if STREAM.search(head): return "media", ["game or media streaming client"]
    if cats & MEDIA_CATS: return "media", ["media player (" + sorted(cats & MEDIA_CATS)[0] + ")"]
    if cats & UTIL_CATS: return "utilities", ["utility category " + sorted(cats & UTIL_CATS)[0]]
    if cats & {"System", "Connectivity", "Security", "Development"} and UTIL_KW.search(name + " . " + text[:300]): return "utilities", ["file / archive / backup / sync / terminal utility"]
    return None


def loc(d):
    if isinstance(d, str): return d
    d = d or {}
    return d.get("en-US") or d.get("en") or d.get("en-GB") or next(iter(d.values()), "") or ""


def ms(t):
    try: return datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat()
    except Exception: return ""


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_cached(url, name, age_h=24):
    f = CACHE / name
    if f.is_file() and time.time() - f.stat().st_mtime < age_h * 3600: return f.read_bytes()
    st, _, _, b = M.get(url, n=200_000_000)
    if st == 200: CACHE.mkdir(parents=True, exist_ok=True); f.write_bytes(b); return b
    raise RuntimeError(f"{url}: HTTP {st}")


def repo_id(url):
    """Upstream identity: github/gitlab/codeberg owner/name, lower-case, else None."""
    m = re.match(r"https?://(?:www\.)?(github\.com|gitlab\.com|codeberg\.org)/([^/\s#?]+)/([^/\s#?]+?)(?:\.git)?(?:[/#?].*)?$", url or "", re.I)
    return f"{m.group(1).lower().split('.')[0]}:{m.group(2).lower()}/{m.group(3).lower()}" if m else None


def new(**k):
    base = {"package": "", "name": "", "group": "utilities", "tags": [], "official_url": "", "download_source": "", "apk_url": "", "apk_file": "", "apk_size": None, "apk_sha256": "",
            "version": "", "released": "", "license": "", "restrictions": [], "min_sdk": None, "abis": None, "signer_sha256": [], "rotate_confidence": "unknown", "needs_game_files": "unknown",
            "status": "needs_verification", "verification": [], "flags": [], "sources": [], "reasons": [], "summary": "", "repo": "", "price": "free", "notes": "", "reports": None, "project": "", "developer": ""}
    base.update(k); return base


# ---- importers --------------------------------------------------------------------------------------------------------------

def from_fdroid_like(key, base_url, label):
    idx = json.loads(fetch_cached(SRC_URL[key], f"{key}-index-v2.json"))
    out, seen = [], 0
    for pkg, p in idx["packages"].items():
        m = p.get("metadata", {}); seen += 1
        name, summ, desc = loc(m.get("name")) or pkg, loc(m.get("summary")), loc(m.get("description"))
        g = classify(name, f"{summ} . {desc}", m.get("categories"))
        if not g or not p.get("versions"): continue
        v = max(p["versions"].values(), key=lambda x: x["manifest"].get("versionCode", 0))
        mf = v["manifest"]; sdk = (mf.get("usesSdk") or {}); mn = sdk.get("minSdkVersion", 1); nc = mf.get("nativecode") or []
        r = new(package=pkg, name=name, group=g[0], reasons=g[1], summary=summ[:160], developer=(m.get("authorName") or "").strip(), official_url=m.get("webSite") or m.get("sourceCode") or "", repo=m.get("sourceCode") or "",
                download_source=f"{label} package repository", apk_url=base_url + v["file"]["name"], apk_file=v["file"]["name"].lstrip("/"), apk_size=v["file"].get("size"), apk_sha256=v["file"].get("sha256", ""),
                version=mf.get("versionName", ""), released=ms(v.get("added") or m.get("lastUpdated")), license=m.get("license", ""), min_sdk=mn, abis=nc, signer_sha256=(mf.get("signer") or {}).get("sha256", []),
                sources=[key], verification=[f"{label} index lists the file, its SHA-256, size, manifest and signer"], tags=CAT.make_tags(m.get("categories", [])),
                restrictions=[a for a in (v.get("antiFeatures") or {}) if a in ("NonFreeNet", "NonFreeAssets", "NonFreeDep", "NonFreeAdd", "Tracking", "UpstreamNonFree", "Ads")])
        out.append(r)
    return out, seen


def from_recompa():
    d = load_json(CACHE / "recompa.json") if (CACHE / "recompa.json").is_file() else json.loads(fetch_cached(SRC_URL["recompa"], "recompa.json"))
    out = []
    for p in d["ports"]:
        for f in p.get("forks", []):
            rel = f.get("release") or {}; a = rel.get("asset")
            if not a or not f.get("package"): continue
            rep = f.get("reports") or []
            tot = {k: sum(x.get(k, 0) for x in rep) for k in ("great", "playable", "broken")}
            typ = p.get("type", "")
            r = new(package=f["package"], name=p["name"], developer=f["repo"].split("/")[0], group="ports", reasons=[f"Recompa lists a native Android {typ or 'port'} of {p.get('game') or p['name']}"],
                    official_url=f"https://github.com/{f['repo']}", repo=f"https://github.com/{f['repo']}", download_source="GitHub release of the fork repository (listed by Recompa)", apk_url=a["url"],
                    apk_file=a["name"], apk_size=a.get("size"), apk_sha256=a.get("sha256", ""), version=rel.get("tag", ""), released=(rel.get("published_at") or "")[:10], signer_sha256=[f["signer_sha256"]] if f.get("signer_sha256") else [],
                    project=f"game:{p.get('game') or p['id']}", sources=["recompa"], verification=["Recompa index (third-party lead): file, size and SHA-256 re-checked independently"], needs_game_files="yes" if typ in ("recomp", "decomp", "source-port") else "unknown",
                    tags=CAT.make_tags([typ, p.get("original_platform", "")]), reports=tot if rep else None, flags=["fork-or-community-port"], notes=f"original platform: {p.get('original_platform','')}")
            out.append(r)
    return out


def from_obtainium_community(workers=6):
    tree = json.loads(fetch_cached("https://api.github.com/repos/ImranR98/apps.obtainium.imranr.dev/git/trees/main?recursive=1", "obt-tree.json"))
    paths = [x["path"] for x in tree["tree"] if x["path"].startswith("public/data/apps/") and x["path"].endswith(".json")]
    def one(p):
        try:
            d = json.loads(fetch_cached("https://raw.githubusercontent.com/ImranR98/apps.obtainium.imranr.dev/main/" + p, "obt-" + p.rsplit("/", 1)[1], 24 * 7))
            d.setdefault("config", {}).setdefault("id", p.rsplit("/", 1)[1][:-5])      # the file name IS the package id
            return d
        except Exception: return None
    with ThreadPoolExecutor(workers) as ex: docs = list(ex.map(one, paths))
    out, seen = [], 0
    for doc in filter(None, docs):
        seen += 1
        c = doc.get("config", {}); desc = loc(doc.get("description"))
        g = classify(c.get("name", ""), desc, [x.title() for x in doc.get("categories", [])] + [x.replace("-", " ").title() for x in doc.get("categories", [])])
        if not g: g = classify(c.get("name", ""), desc, [])
        if not g: continue
        out.append(new(package=c["id"], name=c.get("name") or c["id"], group=g[0], reasons=g[1] + ["listed in the Obtainium community configurations"], summary=desc[:160], official_url=c.get("url", ""),
                       repo=c.get("url", ""), download_source="upstream release page (Obtainium community configuration)", sources=["obtainium"], verification=["Obtainium config is a third-party lead: release resolved independently"]))
    return out, seen


def from_retro_handhelds():
    d = load_json(CACHE / "obt-rotate.json")
    out = []
    for a in d["apps"]:
        url = a.get("url", "")
        m = re.search(r"\.apk", json.dumps(a.get("apkUrls", "")))
        try: apk = json.loads(a["apkUrls"])[a.get("preferredApkIndex", 0)][1]
        except Exception: apk = ""
        g = classify(a["name"], a["name"], []) or ("emulators" if re.search(r"emul|retro|retroarch|\bps2|dolphin|duck|ppsspp|flycast|azahar|drastic|yaba|pcsx|nethersx", a["name"], re.I) else "utilities", [])
        apk = apk if apk.startswith("http") and "api.github.com" not in apk else ""        # API asset URLs need a header: resolve the upstream release page instead
        out.append(new(package="", name=a["name"], group=g[0], reasons=["curated by Retro Handhelds in their RG Rotate Obtainium collection"], official_url=url, repo=url, apk_url=apk,
                       version=a.get("latestVersion") or "", download_source="upstream release page (RG Rotate collection entry)", sources=["retrohandhelds-rotate"], rotate_confidence="curated-for-rotate",
                       verification=["collection entry is a third-party lead: release resolved independently"]))
    return out


def from_rgc_guide():
    html = (CACHE / "rgc.html").read_text(encoding="utf-8", errors="replace")
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.S):
        u, t = m.group(1), re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
        pm = re.search(r"play\.google\.com/store/apps/details\?id=([\w.]+)", u)
        rid = repo_id(u)
        if pm and pm.group(1) not in seen and t and len(t) < 60:
            seen.add(pm.group(1)); out.append(new(package=pm.group(1), name=t, group="emulators",
                                                  reasons=["recommended in the Retro Game Corps Android emulation guide"], official_url=u, download_source="Google Play listing (guide link)", sources=["rgc-guide"], status="needs_verification",
                                                  flags=["store-link-only-until-verified"]))
        elif rid and rid not in seen and rid.startswith("github"):
            seen.add(rid); out.append(new(name=rid.split("/")[-1], group="emulators", reasons=["recommended in the Retro Game Corps Android emulation guide"], official_url=u, repo=u,
                                          download_source="upstream release page", sources=["rgc-guide"]))
    return out


def from_mainstream():
    seeds = {s["id"]: s for s in load_json(HERE / "mainstream.json")["apps"]}
    ver = {x["id"]: x for x in load_json(ROOT / "build" / "discovery" / "mainstream-verified.json")["apps"]}
    out = []
    for i, s in seeds.items():
        v = ver[i]
        d = next((c for c in v["channels"] if c["kind"] != "store" and c.get("ok")), None)
        stores = [c for c in v["channels"] if c["kind"] == "store" and (c.get("ok") or c.get("http") in (403, 429))]
        if not d and not stores: continue
        man = (d or {}).get("manifest") or {}
        r = new(package=man.get("package") or s["package"], name=s["name"], group=s["group"], reasons=["mainstream emulator/frontend seed (requested by name)"], official_url=s["site"] or s["source"], repo=s["source"],
                license=s["license"], price=s["price"], sources=["mainstream-seed"], needs_game_files="yes" if s["group"] == "emulators" else "unknown", notes=s.get("notes", ""), tags=CAT.make_tags(s.get("aliases", [])))
        if d:
            r.update(download_source=d["label"], apk_url=d["url"], apk_file=d.get("file", ""), apk_size=d.get("size") or man.get("size"), apk_sha256=man.get("sha256", ""), version=d.get("tag", ""), released=d.get("published", ""),
                     min_sdk=man.get("min_sdk"), abis=man.get("abis"), signer_sha256=man.get("signers_sha256", []), verification=["official channel resolved and the APK manifest read (mainstream.py)"],
                     status="verified" if man.get("package") and not d.get("zip_of_apk") else "needs_verification")
            if d.get("zip_of_apk"): r["flags"].append("official ZIP of APKs on a pre-release; APK not extracted")
            if not man.get("package"): r["flags"].append("manifest not read")
        else:
            r.update(status="external_listing", download_source=stores[0]["label"], official_url=stores[0].get("url") or r["official_url"], apk_url="", verification=["store listing exists; no direct APK from the developer"])
            r["official_url"] = next(c["url"] for c in seeds[i]["channels"] if c["kind"] == "store")
        out.append(r)
    return out


# ---- remote verification: nothing is downloaded whole ----------------------------------------------------------------

def zip_entries(url):
    """-> (size, {name: (lho, comp, csize, usize)}) from the central directory, via Range requests."""
    st, _, h, _ = M.get(url, "bytes=0-0", 1)
    cr = h.get("Content-Range", ""); size = int(cr.rsplit("/", 1)[1]) if "/" in cr and cr.rsplit("/", 1)[1].isdigit() else None
    if st not in (200, 206) or not size or size < 22: return size, {}
    st, _, _, tail = M.get(url, f"bytes={max(0, size - 66000)}-{size - 1}", 70000)
    i = tail.rfind(b"PK\x05\x06")
    if i < 0: return size, {}
    n, cdsz, cdoff = struct.unpack("<HII", tail[i + 10:i + 20])
    start = size - len(tail)
    cd = tail[cdoff - start:cdoff - start + cdsz] if cdoff >= start else M.get(url, f"bytes={cdoff}-{cdoff + cdsz - 1}", cdsz + 16)[3]
    ents, p = {}, 0
    while p + 46 <= len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        comp, = struct.unpack("<H", cd[p + 10:p + 12]); csz, usz = struct.unpack("<II", cd[p + 20:p + 28]); nl, el, cl = struct.unpack("<HHH", cd[p + 28:p + 34]); lho, = struct.unpack("<I", cd[p + 42:p + 46])
        ents[cd[p + 46:p + 46 + nl].decode("utf-8", "replace")] = (lho, comp, csz, usz); p += 46 + nl + el + cl
    return size, ents


def axml(data):
    """Minimal Android binary XML reader: -> {'package','minSdk','targetSdk'}."""
    def u16(o): return struct.unpack_from("<H", data, o)[0]
    def u32(o): return struct.unpack_from("<I", data, o)[0]
    pos, strings = 8, []
    out = {}
    while pos + 8 <= len(data):
        t, hs, sz = u16(pos), u16(pos + 2), u32(pos + 4)
        if sz <= 0: break
        if t == 0x0001:
            cnt, flags, sstart = u32(pos + 8), u32(pos + 16), u32(pos + 20); utf8 = bool(flags & 0x100)
            offs = [u32(pos + 28 + 4 * i) for i in range(cnt)]
            for off in offs:
                o = pos + sstart + off
                if utf8:                       # [char length (1-2 bytes)][byte length (1-2 bytes)][bytes]
                    n = data[o]; o += 2 if n & 0x80 else 1
                    b = data[o]; o += 1
                    if b & 0x80: b = ((b & 0x7F) << 8) | data[o]; o += 1
                    strings.append(data[o:o + b].decode("utf-8", "replace"))
                else:
                    n = u16(o); strings.append(data[o + 2:o + 2 + 2 * n].decode("utf-16le", "replace"))
        elif t == 0x0102:
            ns, nm, ast, asz, ac = u32(pos + 16), u32(pos + 20), u16(pos + 24), u16(pos + 26), u16(pos + 28)
            el = strings[nm] if nm < len(strings) else ""
            for k in range(ac):
                a = pos + 16 + ast + k * 20
                an = strings[u32(a + 4)] if u32(a + 4) < len(strings) else ""
                rv, dtype, dv = u32(a + 8), data[a + 15], u32(a + 16)
                val = (strings[rv] if rv != 0xFFFFFFFF and rv < len(strings) else dv) if dtype in (0x03, 0x00) else dv
                if el == "manifest" and an == "package": out["package"] = val
                if el == "uses-sdk" and an == "minSdkVersion": out["minSdk"] = dv
                if el == "uses-sdk" and an == "targetSdkVersion": out["targetSdk"] = dv
            if el == "uses-sdk" or (el == "application" and "minSdk" in out): break
        pos += sz
    return out


def remote_manifest(url):
    """minSdk, package, ABIs of a remote APK from ~3 Range requests."""
    size, ents = zip_entries(url)
    e = ents.get("AndroidManifest.xml")
    if not e: return None
    lho, comp, csz, usz = e
    st, _, _, b = M.get(url, f"bytes={lho}-{lho + 30 + 300 + csz}", csz + 400)
    if len(b) < 30 or b[:4] != b"PK\x03\x04": return None
    nl, el = struct.unpack("<HH", b[26:30]); data = b[30 + nl + el:30 + nl + el + csz]
    raw = data if comp == 0 else zlib.decompress(data, -15)
    info = axml(raw)
    abis = sorted({n.split("/")[1] for n in ents if n.startswith("lib/") and n.count("/") >= 2})
    return {"package": info.get("package", ""), "min_sdk": info.get("minSdk", 1), "target_sdk": info.get("targetSdk"), "abis": abis, "size": size}


def github_release(repo):
    """Latest release APK of a GitHub repo, via the release pages (no API quota). -> dict | None."""
    st, final, _ = M.text(f"https://github.com/{repo}/releases/latest", 10)
    tag = final.rsplit("/tag/", 1)[1] if "/tag/" in final else None
    if not tag: return None
    st, _, html = M.text(f"https://github.com/{repo}/releases/expanded_assets/{tag}", 300000)
    names = [__import__("urllib.parse").parse.unquote(n) for n in re.findall(r'href="/[^"]+/releases/download/[^"/]+/([^"]+)"', html)]
    apks = [{"name": n} for n in names if n.lower().endswith(".apk")]
    if not apks: return {"tag": tag, "apk": None}
    a = pick_asset(apks)
    st2, _, pg = M.text(f"https://github.com/{repo}/releases/tag/{tag}", 120000)
    return {"tag": tag, "apk": a["name"], "url": f"https://github.com/{repo}/releases/download/{tag}/{__import__('urllib.parse').parse.quote(a['name'])}", "published": (re.search(r'datetime="(\d{4}-\d{2}-\d{2})', pg) or [None, ""])[1]}


def gitlab_release(proj):
    st, _, _, b = M.get(f"https://gitlab.com/api/v4/projects/{__import__('urllib.parse').parse.quote(proj, safe='')}/releases?per_page=1")
    if st != 200: return None
    rs = json.loads(b)
    if not rs: return None
    links = [l for l in rs[0]["assets"]["links"] if l["name"].lower().endswith(".apk")]
    if not links: return {"tag": rs[0]["tag_name"], "apk": None}
    return {"tag": rs[0]["tag_name"], "apk": links[0]["name"], "url": links[0]["url"], "published": rs[0]["released_at"][:10]}


def codeberg_release(proj):
    st, _, _, b = M.get(f"https://codeberg.org/api/v1/repos/{proj}/releases?limit=1")
    if st != 200: return None
    rs = json.loads(b)
    if not rs: return None
    links = [a for a in rs[0].get("assets", []) if a["name"].lower().endswith(".apk")]
    if not links: return {"tag": rs[0]["tag_name"], "apk": None}
    return {"tag": rs[0]["tag_name"], "apk": links[0]["name"], "url": links[0]["browser_download_url"], "published": (rs[0].get("published_at") or "")[:10]}


def repo_page(repo):
    st, _, h = M.text(f"https://github.com/{repo}", 600000)
    if st != 200: return {"status": st}
    lic = re.findall(r">\s*([A-Za-z0-9.+-]{2,40}) license\s*<", h)
    return {"status": 200, "license": lic[0] if lic else "", "archived": "This repository has been archived" in h or "archived by the owner" in h.lower(), "fork": bool(re.search(r"forked from\s*<", h))}


def resolve(r):
    """Fill a lead's file, version, licence and manifest from its upstream (GitHub / GitLab / Codeberg), then check the file. Mutates r."""
    rid = repo_id(r["repo"] or r["official_url"])
    if not r["apk_url"] and rid:
        host, path = rid.split(":", 1)
        try:
            rel = {"github": github_release, "gitlab": gitlab_release, "codeberg": codeberg_release}[host](path)
        except Exception as e: rel = None; r["flags"].append("release lookup failed")
        if rel and rel.get("apk"):
            r.update(apk_url=rel["url"], apk_file=rel["apk"], version=rel["tag"], released=rel.get("published", ""), download_source=f"{host} release of {path}")
        else:
            r["flags"].append("no APK in the latest release" if rel else "no release found")
    if host_is_github(rid) and not r["license"]:
        pg = repo_page(rid.split(":", 1)[1])
        if pg.get("status") == 200:
            r["license"] = pg["license"]
            if pg["archived"]: r["flags"].append("archived")
            if pg["fork"]: r["flags"].append("fork")
        else: r["flags"].append(f"repo page HTTP {pg.get('status')}")
    if r["apk_url"]:
        real, size, final = M.probe(r["apk_url"])
        r["file_real"] = real
        if real is True:
            if r["apk_size"] and size and r["apk_size"] != size: r["flags"].append(f"size differs from the lead ({size} vs {r['apk_size']})")
            r["apk_size"] = r["apk_size"] or size
            if r["min_sdk"] is None:
                try: man = remote_manifest(r["apk_url"])
                except Exception: man = None
                if man and man["package"]:
                    if r["package"] and r["package"] != man["package"]: r["flags"].append(f"package differs: manifest says {man['package']}")
                    r.update(package=r["package"] or man["package"], min_sdk=man["min_sdk"], abis=man["abis"])
                    r["verification"].append("manifest read from the remote APK (Range requests)")
                else: r["flags"].append("manifest not readable")
        else: r["flags"].append("file not reachable" if real is None else "link is not an APK/ZIP")
    return r


def host_is_github(rid): return bool(rid and rid.startswith("github:"))


# ---- judgement ---------------------------------------------------------------------------------------------------------------

def installable(r):
    """Manifest facts only. -> (ok | None unknown, reason)."""
    if r["min_sdk"] is None: return None, "minSdk unknown"
    if r["min_sdk"] > API_LEVEL: return False, f"needs Android API {r['min_sdk']}+ (RG Rotate is API {API_LEVEL})"
    if r["abis"] and not (set(r["abis"]) & ROTATE_ABIS): return False, "native code for none of the device's ABIs (" + ", ".join(sorted(ROTATE_ABIS)) + ")"
    return True, ""


FOSS = re.compile(r"GPL|MIT|BSD|Apache|MPL|LGPL|AGPL|ISC|Zlib|Unlicense|CC0|CC-BY|EPL|Artistic|WTFPL|0BSD|OFL", re.I)


def judge(r):
    ok, why = installable(r)
    r["rotate_installable"] = ok
    if ok is False: r["flags"].append(why)
    if r["status"] == "external_listing": return
    lic_ok = bool(r["license"]) and r["license"].lower() not in ("none", "unknown", "noassertion", "other", "unknown license")
    real = r.get("file_real", True if "f-droid" in r["download_source"].lower() or "izzy" in r["download_source"].lower() else None)
    full = bool(r["apk_url"]) and ok is True and r["package"] and lic_ok and real is not False
    r["status"] = "verified" if full and not any(f.startswith(("file not", "link is not", "package differs")) for f in r["flags"]) else "needs_verification"
    if r["status"] == "needs_verification":
        missing = [x for x in (("no APK file", not r["apk_url"]), ("package id", not r["package"]), ("minSdk/ABIs", ok is None), ("licence", not lic_ok), ("file unreachable", real is False)) if x[1]]
        r["verification"].append("incomplete: " + ", ".join(m[0] for m in missing) if missing else "incomplete")
    if ok is True and r["rotate_confidence"] == "unknown": r["rotate_confidence"] = "manifest-installable"
    if r["group"] == "emulators" and r["needs_game_files"] == "unknown": r["needs_game_files"] = "yes"
    r["restrictions"] += ["non-commercial / no-derivatives licence: link only"] if re.search(r"-NC|NonCommercial|NC-ND", r["license"] or "", re.I) else []


def rank(r):
    s = 0.0
    for k, w in (("mainstream-seed", 5), ("retrohandhelds-rotate", 4), ("rgc-guide", 2), ("obtainium", 1), ("izzy", 0.5), ("fdroid", 0.5)):
        if k in r["sources"]: s += w
    s += 2 if r["status"] == "verified" else (0.5 if r["status"] == "needs_verification" else 0)
    s += {"emulators": 2, "ports": 0.5, "themes-launchers": 1.5, "utilities": 0.5, "media": 0.5, "games": 0.5}[r["group"]]
    if r["reasons"] and any("gamepad" in x for x in r["reasons"]): s += 1
    if r.get("reports"): s += min(2, (r["reports"]["great"] + r["reports"]["playable"]) / 3) - min(1.5, r["reports"]["broken"] / 3)
    if r["released"] and r["released"] >= str(date.today().year - 1): s += 1
    if FOSS.search(r["license"] or ""): s += 0.5
    if "fork" in r["flags"] or "archived" in r["flags"]: s -= 1
    if "sources" and len(r["sources"]) > 1: s += 0.5
    return s


def merge(a, b):
    """Fold b into a: prefer index-verified facts, union sources/flags/reasons."""
    for k in ("developer", "apk_url", "apk_file", "apk_size", "apk_sha256", "version", "released", "license", "min_sdk", "abis", "official_url", "repo", "summary", "download_source"):
        if (a[k] in ("", None, []) or (k in ("min_sdk", "abis") and a[k] is None)) and b[k] not in ("", None, []): a[k] = b[k]
    if not a["signer_sha256"]: a["signer_sha256"] = b["signer_sha256"]
    if not a["package"]: a["package"] = b["package"]
    if (a["name"] == a["package"] or a["name"].count(".") >= 2) and b["name"] and b["name"] != b["package"]: a["name"] = b["name"]
    for k in ("sources", "flags", "reasons", "verification", "tags", "restrictions"):
        a[k] = a[k] + [x for x in b[k] if x not in a[k]]
    if a["rotate_confidence"] in ("unknown", "manifest-installable") and b["rotate_confidence"] == "curated-for-rotate": a["rotate_confidence"] = "curated-for-rotate"
    if b.get("reports") and not a.get("reports"): a["reports"] = b["reports"]
    if b["status"] == "verified": a["status"] = "verified"
    return a


def norm_name(n):
    import unicodedata
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower())


def base_name(n): return norm_name(re.sub(r"\(.*?\)|\b(android|emulator|for android)\b", "", n or "", flags=re.I))


def dedupe(recs):
    byp, bynone, dups = {}, [], 0
    for r in recs:
        if r["package"]:
            if r["package"] in byp: byp[r["package"]] = merge(byp[r["package"]], r); dups += 1
            else: byp[r["package"]] = r
        else: bynone.append(r)
    out = list(byp.values())
    byrepo = {}
    for r in out:
        rid = repo_id(r["repo"] or r["official_url"])
        if rid: byrepo.setdefault((rid, norm_name(r["name"])), []).append(r)
    anyrepo = {}
    for r in out:
        rid = repo_id(r["repo"] or r["official_url"])
        if rid: anyrepo.setdefault(rid, []).append(r)
    for r in bynone:                                   # leads without a package id fold into an indexed record of the same upstream + name
        rid = repo_id(r["repo"] or r["official_url"]); hit = byrepo.get((rid, norm_name(r["name"]))) if rid else None
        if not hit and r["sources"] == ["rgc-guide"] and rid and anyrepo.get(rid): hit = anyrepo[rid][:1]    # link text is not a name: same repository is enough
        if not hit:
            same = [x for x in out if x["group"] == r["group"] and base_name(x["name"]) == base_name(r["name"]) and base_name(r["name"])]
            hit = same[:1] if len(same) == 1 else None
        if hit: merge(hit[0] if isinstance(hit, list) else hit, r); dups += 1
        else: out.append(r)
    keep, seen = [], {}
    for r in out:                                      # same upstream repository AND same name under two packages = one project (flavours), not two candidates
        rid = repo_id(r["repo"] or r["official_url"]); k = (rid, norm_name(r["name"])) if rid else None
        if k and k in seen and seen[k]["package"] != r["package"]:
            merge(seen[k], r); seen[k]["flags"].append(f"also published as {r['package']}") if r["package"] else None; dups += 1; continue
        if k: seen[k] = r
        keep.append(r)
    return keep, dups


def existing_matches():
    have = {}
    dev = ROOT / "android" / "app" / "src" / "debug" / "assets" / "dev" / "catalog" / "index.json"
    if dev.is_file():
        for ap in load_json(dev)["apps"]:
            for art in ap["artifacts"]:
                if art.get("android"): have[art["android"]["package"].lower()] = "DEV catalog"
            have[repo_id(ap["source"]) or ap["id"]] = "DEV catalog"
    for ap in load_json(ROOT / "candidates" / "inventory-rg-rotate.json")["applications"]:
        for pk in ap.get("packages", []):
            if pk.get("android"): have.setdefault(pk["android"]["package"].lower(), "inventory" + (" (on hold)" if ap.get("hold") else ""))
        for s in ap.get("sources", []): have.setdefault(repo_id(s["url"]) or "", "inventory" + (" (on hold)" if ap.get("hold") else ""))
    return have


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "build" / "discovery")); ap.add_argument("--max-resolve", type=int, default=400); ap.add_argument("--deadline", type=int, default=2400)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    stats = {"scanned": {}, "relevant": {}}
    recs = []
    fd, n = from_fdroid_like("fdroid", "https://f-droid.org/repo", "F-Droid"); stats["scanned"]["fdroid"] = n; stats["relevant"]["fdroid"] = len(fd); recs += fd
    iz, n = from_fdroid_like("izzy", "https://apt.izzysoft.de/fdroid/repo", "IzzyOnDroid"); stats["scanned"]["izzy"] = n; stats["relevant"]["izzy"] = len(iz); recs += iz
    rc = from_recompa(); stats["scanned"]["recompa"] = len(rc); stats["relevant"]["recompa"] = len(rc); recs += rc
    ob, n = from_obtainium_community(a.workers); stats["scanned"]["obtainium"] = n; stats["relevant"]["obtainium"] = len(ob); recs += ob
    rh = from_retro_handhelds(); stats["scanned"]["retrohandhelds-rotate"] = len(rh); stats["relevant"]["retrohandhelds-rotate"] = len(rh); recs += rh
    rg = from_rgc_guide(); stats["scanned"]["rgc-guide"] = len(rg); stats["relevant"]["rgc-guide"] = len(rg); recs += rg
    ms_ = from_mainstream(); stats["scanned"]["mainstream-seed"] = len(ms_); stats["relevant"]["mainstream-seed"] = len(ms_); recs += ms_
    print({k: v for k, v in stats["relevant"].items()}, "raw records", len(recs), flush=True)
    uniq, dups = dedupe(recs)
    print("after dedupe", len(uniq), "duplicates folded", dups, flush=True)
    # installable by manifest (index data) BEFORE spending requests; the not-installable are dropped, not counted
    pre = []
    dropped = {"needs Android above API 31": 0, "no usable ABI": 0}
    for r in uniq:
        ok, why = installable(r)
        if ok is False:
            dropped["needs Android above API 31" if "API" in why else "no usable ABI"] += 1; continue
        pre.append(r)
    # resolve leads (upstream release, licence, manifest) and spot-check index records with real range reads
    prio = {"retrohandhelds-rotate": 0, "mainstream-seed": 0, "rgc-guide": 1, "obtainium": 2, "recompa": 3}
    todo = sorted([r for r in pre if r["status"] != "external_listing" and (not r["apk_url"] or r["min_sdk"] is None)], key=lambda r: min(prio.get(x, 4) for x in r["sources"]))[:a.max_resolve]   # curated leads first
    print("resolving", len(todo), "leads", flush=True)
    def work(r):
        if time.time() - T0 > a.deadline: r["flags"].append("not resolved: time limit"); return r
        try: return resolve(r)
        except Exception as e: r["flags"].append("resolve error: " + str(e)[:60]); return r
    with ThreadPoolExecutor(a.workers) as ex: list(ex.map(work, todo))
    sample = random.Random(7).sample([r for r in pre if "fdroid" in r["sources"] or "izzy" in r["sources"]], 60)
    def spot(r):
        real, size, _ = M.probe(r["apk_url"]); r["file_real"] = real
        if real is not True: r["flags"].append("index file not reachable (spot check)")
        elif r["apk_size"] and size and size != r["apk_size"]: r["flags"].append("index size differs (spot check)")
        else: r["verification"].append("file reachable, size matches the index (range-read spot check)")
    with ThreadPoolExecutor(a.workers) as ex: list(ex.map(spot, sample))
    # Recompa files: probe all of them (third-party lead)
    rcs = [r for r in pre if "recompa" in r["sources"] and "file_real" not in r]
    def probe_rc(r):
        real, size, _ = M.probe(r["apk_url"]); r["file_real"] = real
        if real is not True: r["flags"].append("file not reachable" if real is None else "link is not an APK/ZIP")
        elif r["apk_size"] and size and size != r["apk_size"]: r["flags"].append("size differs from Recompa")
    with ThreadPoolExecutor(a.workers) as ex: list(ex.map(probe_rc, rcs))
    have = existing_matches()
    final = []
    for r in pre:
        if r["status"] != "external_listing" and r.get("file_real") is False and "recompa" in r["sources"] and len(r["sources"]) == 1: continue
        if r["status"] != "external_listing" and not r["apk_url"] and not r["package"]: continue   # no file and no identity: not a defensible candidate
        judge(r)
        m = have.get(r["package"].lower()) or have.get(repo_id(r["repo"]) or "")
        r["existing_match"] = m or ""
        r["rank"] = round(rank(r), 2)
        final.append(r)
    # a lead that never resolved to a file, an identity or a store listing is not a candidate
    final = [r for r in final if r["status"] == "external_listing" or r["apk_url"]]
    final.sort(key=lambda r: -r["rank"])
    write_outputs(out, final, stats, dups, dropped, have)


def write_outputs(out, final, stats, dups, dropped, have):
    cols = ["name", "package", "group", "status", "rotate_confidence", "needs_game_files", "version", "released", "license", "min_sdk", "abis", "apk_url", "apk_size", "official_url", "download_source",
            "sources", "existing_match", "tags", "price", "flags", "reasons", "verification", "rank"]
    doc = {"schema": 1, "generated": date.today().isoformat(), "note": "Leads. 'verified' = a real APK from the project's repository/official server with package, minSdk, ABIs and licence read. It is NOT device testing and NOT approval.",
           "stats": stats, "duplicates_folded": dups, "dropped_not_installable": dropped, "candidates": final}
    (out / "android-500-candidates.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    with open(out / "android-500-candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in final: w.writerow([("; ".join(map(str, r[c])) if isinstance(r[c], list) else ("" if r[c] is None else r[c])) for c in cols])
    report(out, final, doc)


def report(out, final, doc):
    import collections as C
    n = len(final); by = C.Counter(r["status"] for r in final); g = C.Counter(r["group"] for r in final)
    src = C.Counter(s for r in final for s in r["sources"]); only = C.Counter(r["sources"][0] for r in final if len(r["sources"]) == 1)
    new_ = sum(1 for r in final if not r["existing_match"]); ex = n - new_
    proj = lambda r: r["project"] or repo_id(r["repo"] or r["official_url"]) or r["package"] or r["name"]
    projects = {proj(r) for r in final}
    core = [r for r in final if r["group"] in ("emulators", "games", "ports", "themes-launchers")]
    md = [f"# Android candidate discovery (phase 2) · {doc['generated']}\n",
          "Leads, not approvals. **verified** = a real APK from the project's repository or official server, with package id, minSdk, ABIs and licence read; it is **not** device testing. Third-party catalogs (Recompa, Obtainium, Retro Handhelds, Retro Game Corps) were treated as leads and their files re-checked.\n",
          f"## Totals\n\n**{n} unique candidates (unique package ids)** · verified APK **{by['verified']}** · needs verification **{by['needs_verification']}** · external listing **{by['external_listing']}**\n",
          f"- **Distinct upstream projects: {len(projects)}** (community forks of one Recompa game, and the same repository under two package ids, count once). This is the conservative headline number.",
          f"- Core retro categories (Emulators, Games, Ports, Themes & Launchers): **{len(core)}** packages / **{len({proj(r) for r in core})}** projects. General handheld utilities and media players: **{n - len(core)}** packages (a defensible but broader selection: file managers, backup/sync, app managers, music/video players, game streaming).",
          f"- Duplicates folded: **{doc['duplicates_folded']}** (by package id, then upstream repository + name)",
          f"- Dropped as not installable on RG Rotate (manifest): needs Android above API 31 **{doc['dropped_not_installable']['needs Android above API 31']}**, no usable ABI **{doc['dropped_not_installable']['no usable ABI']}**",
          f"- New versus the current RetroHatch inventory/catalog: **{new_}** new, **{ex}** already known\n",
          "## By category\n", "| Category | Candidates | Verified | Needs verification | External |", "|---|---|---|---|---|"]
    for gid in CAT.GROUP_IDS:
        rs = [r for r in final if r["group"] == gid]
        if rs: md.append(f"| {LABEL[gid]} | {len(rs)} | {sum(r['status']=='verified' for r in rs)} | {sum(r['status']=='needs_verification' for r in rs)} | {sum(r['status']=='external_listing' for r in rs)} |")
    md += ["", "## By source (a candidate seen in several sources counts in each)\n", "| Source | Records scanned | Relevant (before dedupe) | Candidates containing it | Only from this source |", "|---|---|---|---|---|"]
    for k, v in doc["stats"]["scanned"].items(): md.append(f"| {k} | {v} | {doc['stats']['relevant'][k]} | {src[k]} | {only[k]} |")
    conf = C.Counter(r["rotate_confidence"] for r in final)
    md += ["", "## RG Rotate compatibility confidence (never a device test)\n", "| Level | Meaning | Count |", "|---|---|---|",
           f"| curated-for-rotate | listed in Retro Handhelds' RG Rotate collection | {conf['curated-for-rotate']} |", f"| manifest-installable | minSdk <= 31 and an ABI the device supports (arm64-v8a, armeabi-v7a, armeabi) or pure Java, per the APK's manifest | {conf['manifest-installable']} |", f"| unknown | manifest not read | {conf['unknown']} |", ""]
    md += ["## Top 75 recommended for RG Rotate\n", "Ranked by: named in the mainstream seed list or Retro Handhelds' Rotate collection, verified file, category value for a handheld, community reports (Recompa), recency, FOSS licence. Per-category caps keep it balanced.\n",
           "| # | App | Category | Status | Min Android | Version | Licence | Why | Source |", "|---|---|---|---|---|---|---|---|---|"]
    caps = {"emulators": 25, "games": 12, "ports": 12, "utilities": 10, "media": 8, "themes-launchers": 8}; used = C.Counter(); top = []
    for r in final:
        if r["status"] == "external_listing" and used["ext"] >= 6: continue
        if used[r["group"]] < caps[r["group"]] and r["status"] != "needs_verification" or (r["status"] == "needs_verification" and r["rank"] >= 6 and used[r["group"]] < caps[r["group"]]):
            top.append(r); used[r["group"]] += 1; used["ext"] += r["status"] == "external_listing"
        if len(top) == 75: break
    for i, r in enumerate(top, 1):
        link = f"[{r['name']}]({r['official_url']})" if r["official_url"] else r["name"]
        md.append(f"| {i} | {link} | {LABEL[r['group']]} | {r['status'].replace('_', ' ')} | {('API %s+' % r['min_sdk']) if r['min_sdk'] else '-'} | {r['version'][:18]} | {(r['license'] or '-')[:20]} | {(r['reasons'] or [''])[0][:70]} | {', '.join(r['sources'])} |")
    md += ["", "## Coverage gaps and caveats\n"]
    md += open(HERE / "android_import_notes.md", encoding="utf-8").read().splitlines() if (HERE / "android_import_notes.md").is_file() else []
    (out / "android-500-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{n} candidates: {dict(by)}  groups {dict(g)}  new {new_}")


if __name__ == "__main__":
    main()
