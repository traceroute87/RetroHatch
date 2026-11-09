#!/usr/bin/env python3
"""Android counterpart of tools/opk_inspect.py: read the REAL identity of an APK, never guess it. Offline for `inspect`; `fetch` downloads one release asset of
a GitHub repository first (public API, honest User-Agent, size cap). Never installs or runs anything and never writes catalog/.

  python tools/apk_inspect.py inspect FILE.apk
  python tools/apk_inspect.py fetch OWNER/REPO [--asset NAME] [--out DIR]     latest release -> pick the APK for RG Rotate -> download -> inspect -> JSON
  python tools/apk_inspect.py inventory INSPECTED.json [--tested TESTED.json]  -> candidates/inventory-rg-rotate.json (same inventory format as the Nano's;
                                                                              then: python tools/make_inventory.py --device rg-rotate)

Facts come from the Android SDK tools (build-tools: aapt2 dump badging, apksigner verify --print-certs): package, versionCode/versionName, minSdk, targetSdk,
native ABIs, the SHA-256 of each signing certificate (what the catalog's android.signer_sha256 must hold) and the signature schemes. `fits` says whether the
file can run on RG Rotate (Android 12 = API 31, arm64) and on the x86_64 emulator, judged only from those facts: it is NOT a test.

Asset choice for RG Rotate (arm64): an APK named for arm64-v8a, else the only APK, else a universal one (name says universal or has no ABI/flavour marker).
"""
import argparse, hashlib, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDK = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or Path.home() / "AppData/Local/Android/Sdk")
UA = "retrohatch-discovery/1 (+https://github.com/traceroute87/RetroHatch)"
MAX_BYTES = 200 * 1024 * 1024
API_LEVEL = 31


def tool(name):
    ext = "*.exe" if os.name == "nt" else ""
    bat = "*.bat" if os.name == "nt" else ""
    c = sorted((SDK / "build-tools").glob(f"*/{name}{bat if name == 'apksigner' else ext}"), reverse=True)
    if not c:
        raise SystemExit(f"{name} not found under {SDK}/build-tools (set ANDROID_HOME)")
    return str(c[0])


def run(*a):
    r = subprocess.run(a, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def inspect(path):
    path = Path(path)
    rc, out, err = run(tool("aapt2"), "dump", "badging", str(path))
    if rc:
        raise SystemExit(f"aapt2 failed: {err.strip()[:200]}")
    m = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", out)
    if not m:
        raise SystemExit("no package line in aapt2 output")
    min_sdk = re.search(r"sdkVersion:'(\d+)'", out)
    tgt = re.search(r"targetSdkVersion:'(\d+)'", out)
    abis = re.findall(r"native-code: ([^\n]*)", out)
    abis = sorted(set(re.findall(r"'([^']+)'", abis[0]))) if abis else []
    rc, so, se = run(tool("apksigner"), "verify", "--verbose", "--print-certs", str(path))
    schemes = [k for k in ("v1", "v2", "v3", "v3.1", "v4") if re.search(rf"Verified using {re.escape(k)} scheme.*: true", so)]
    # ONLY "Signer #N" lines: apksigner also prints a "Source Stamp Signer" (Play's stamp key, shared by unrelated apps), which is not the app's signing identity
    signers = sorted(set(re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})", so, re.M)))
    dns = sorted(set(re.findall(r"^Signer #\d+ certificate DN: (.*)$", so, re.M)))
    debuggable = "application-debuggable" in out
    launcher = bool(re.search(r"launchable-activity: name='", out))
    label = re.search(r"application-label:'([^']*)'", out)
    info = {"file": path.name, "size": path.stat().st_size, "sha256": sha256(path), "package": m.group(1), "version_code": int(m.group(2)), "version_name": m.group(3),
            "label": label.group(1) if label else "", "min_sdk": int(min_sdk.group(1)) if min_sdk else 1, "target_sdk": int(tgt.group(1)) if tgt else None,
            "abis": abis, "signers_sha256": signers, "signer_dn": dns, "signature_schemes": schemes, "signature_ok": rc == 0 and bool(signers), "debuggable": debuggable, "launchable": launcher}
    sdk_ok = info["min_sdk"] <= API_LEVEL
    info["fits"] = {"rg_rotate_android12_arm64": bool(sdk_ok and (not abis or "arm64-v8a" in abis) and info["signature_ok"]),
                    "emulator_x86_64": bool(sdk_ok and (not abis or "x86_64" in abis) and info["signature_ok"])}
    return info


def pick_asset(assets):
    apks = [a for a in assets if a["name"].lower().endswith(".apk")]
    if not apks:
        return None
    arm = [a for a in apks if "arm64" in a["name"].lower() or "aarch64" in a["name"].lower() or "android64" in a["name"].lower()]
    if arm:
        return sorted(arm, key=lambda a: (bool(re.search(r"fdroid|foss", a["name"].lower())), a["name"]))[0]   # the project's own flavour before a store flavour
    if len(apks) == 1:
        return apks[0]
    uni = [a for a in apks if "universal" in a["name"].lower()]
    if uni:
        return uni[0]
    plain = [a for a in apks if not re.search(r"armeabi|arm32|x86|fdroid|foss|debug", a["name"].lower())]
    return (plain or apks)[0]


def get(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Accept": accept} if accept else {})})
    return urllib.request.urlopen(req, timeout=60)


def fetch(repo, asset=None, out="build/android-candidates"):
    rel = json.load(get(f"https://api.github.com/repos/{repo}/releases/latest", "application/vnd.github+json"))
    meta = json.load(get(f"https://api.github.com/repos/{repo}", "application/vnd.github+json"))
    a = next((x for x in rel["assets"] if x["name"] == asset), None) if asset else pick_asset(rel["assets"])
    if not a:
        raise SystemExit(f"{repo}: no APK asset in {rel['tag_name']}")
    if a["size"] > MAX_BYTES:
        raise SystemExit(f"{repo}: {a['name']} is {a['size']} bytes (cap {MAX_BYTES})")
    dest = ROOT / out / repo.replace("/", "__")
    dest.mkdir(parents=True, exist_ok=True)
    f = dest / a["name"]
    if not f.is_file() or f.stat().st_size != a["size"]:
        with get(a["browser_download_url"]) as r, open(f.with_suffix(".part"), "wb") as o:
            n = 0
            while b := r.read(1 << 20):
                n += len(b)
                if n > MAX_BYTES:
                    raise SystemExit("download over the size cap")
                o.write(b)
        f.with_suffix(".part").replace(f)
    info = inspect(f)
    gh_digest = (a.get("digest") or "").removeprefix("sha256:")
    info.update({"repo": repo, "repo_url": f"https://github.com/{repo}", "tag": rel["tag_name"], "published": rel["published_at"][:10],
                 "url": a["browser_download_url"], "asset": a["name"], "release_url": rel["html_url"],
                 "github_digest": gh_digest, "github_digest_matches": (gh_digest == info["sha256"]) if gh_digest else None,
                 "license": ((meta.get("license") or {}).get("spdx_id") or "unknown"), "description": (meta.get("description") or "").strip(), "topics": meta.get("topics", []),
                 "archived": meta.get("archived", False), "pushed_at": (meta.get("pushed_at") or "")[:10]})
    if info["license"] == "NOASSERTION":
        info["license"] = "unknown"
    if info["size"] != a["size"]:
        raise SystemExit("downloaded size differs from the release asset size")
    return info


def entry(i, tested=None):
    """One inventory entry (same keys as candidates/inventory.json) from a fetched+inspected APK. Nothing is guessed: every field is read from the APK,
    the GitHub release/repository, or is the literal 'not tested'."""
    name = i["repo"].split("/")[1]
    notes = []
    if i["license"] == "unknown":
        notes.append("No licence detected by GitHub for this repository: it cannot enter a catalog until the licence is confirmed by hand.")
    if any("Google Inc" in d and "CN=Android" in d for d in i["signer_dn"]):
        notes.append("Signed with a certificate whose subject is CN=Android, O=Google Inc. (looks like an AOSP key, not a developer key). Check who holds that key before any approval.")
    if i["published"] < "2025-01-01":
        notes.append(f"Latest release is old ({i['published']}).")
    if not i["fits"]["emulator_x86_64"]:
        notes.append("arm64-only native code: cannot run on the x86_64 emulator, needs a real arm64 device.")
    t = (tested or {}).get(i["repo"])
    hold = ("licence not detected: resolve it first" if i["license"] == "unknown" else
            "signing certificate looks like an AOSP key: investigate who holds it first" if any("Google Inc" in d and "CN=Android" in d for d in i["signer_dn"]) else "")
    e = {"id": (re.sub(r"[^a-z0-9]", "", (i["label"] or name).lower()) or re.sub(r"[^a-z0-9]", "", name.lower()))[:48], "name": i["label"] or name, "kind": "app", "status": "apk-verified",
            "description": i["description"] or f"Android app {i['package']}", "topics": i["topics"], "version": i["version_name"], "license": i["license"],
            "last_activity": i["pushed_at"], "claim": {"kind": "android", "text": f"Android APK: minSdk {i['min_sdk']}, " + (", ".join(i["abis"]) or "no native code"), "where": "apk manifest"},
            "sources": [{"type": "repo", "url": i["repo_url"]}],
            "packages": [{"name": i["asset"], "url": i["url"], "size": i["size"], "format": "apk", "signature": "apk", "container": "", "from": "release", "sha256": i["sha256"],
                          "android": {"package": i["package"], "version_code": i["version_code"], "signer_sha256": i["signers_sha256"]}}],
            "evidence": {"apk": {k: i[k] for k in ("package", "version_code", "version_name", "min_sdk", "target_sdk", "abis", "signers_sha256", "signer_dn", "signature_schemes", "debuggable", "launchable")},
                         "release": {"tag": i["tag"], "published": i["published"], "page": i["release_url"], "github_digest_matches": i["github_digest_matches"]},
                         "fits_from_metadata": i["fits"],
                         "tested": {"emulator_x86_64_api31": t or "not tested", "rg_rotate_hardware": "not tested"}, "notes": notes}}
    if hold:
        e["hold"] = hold   # kept out of every DEV catalog (android/tools/dev_fixture.py real) until a human resolves it
    return e


def inventory(src, tested):
    items = json.loads(Path(src).read_text(encoding="utf-8"))
    tmap = json.loads(Path(tested).read_text(encoding="utf-8")) if tested else {}
    inv = {"schema": 2, "device": "rg-rotate",
           "status": "UNAPPROVED candidate inventory, read-only. Not part of the signed catalog: nothing here is approved, hardware-tested or installable.",
           "known_limits": [
               {"id": "not-a-crawl", "note": "These entries come from curated repository sources (discovery/sources.txt, device rg-rotate) read with tools/apk_inspect.py (GitHub releases API plus the Android SDK's aapt2 and apksigner). discovery/crawl.py still runs the rg-nano profile only; it was not extended to find Android apps on its own."},
               {"id": "metadata-only", "note": "'fits_from_metadata' is judged from the APK's minSdk and native ABIs. It is not a test. Nothing was run on RG Rotate hardware."},
               {"id": "release-hosts", "note": "Only GitHub release downloads can enter a signed catalog (tools/trust.py: url must be a release download of the entry's own source repository). F-Droid and vendor sites are not used."}],
           "package_evidence": {"note": "Raw APK identities are in each entry's packages[].android and evidence.apk, read from the downloaded files on " + __import__("time").strftime("%Y-%m-%d") + "."},
           "applications": sorted((entry(i, tmap) for i in items), key=lambda e: e["id"])}
    out = ROOT / "candidates" / "inventory-rg-rotate.json"
    out.write_text(json.dumps(inv, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(inv['applications'])} entries -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("inspect"); i.add_argument("file")
    f = sp.add_parser("fetch"); f.add_argument("repo"); f.add_argument("--asset"); f.add_argument("--out", default="build/android-candidates")
    v = sp.add_parser("inventory"); v.add_argument("inspected"); v.add_argument("--tested")
    a = ap.parse_args()
    if a.cmd == "inventory":
        return inventory(a.inspected, a.tested)
    print(json.dumps(inspect(a.file) if a.cmd == "inspect" else fetch(a.repo, a.asset, a.out), indent=1))


if __name__ == "__main__":
    main()
