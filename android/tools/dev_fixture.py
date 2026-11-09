#!/usr/bin/env python3
"""DEV fixture for end-to-end testing of the Android installer. Nothing here is a real app, a real catalog or a production key.

  python android/tools/dev_fixture.py init     create the throw-away DEV CA, server certificate and DEV catalog signing key (private parts in
                                               ~/.retrohatch-dev-android, OUTSIDE the repo); write only the PUBLIC parts into the debug source set:
                                               app/src/debug/res/raw/dev_ca.pem, app/src/debug/assets/dev/{dev_keys,url_map}.txt
  python android/tools/dev_fixture.py build    build the labelled test APK (:fixtureapp), read its identity with the SDK tools, and write the signed DEV
                                               catalogs plus the files the test server hands out into android/build/devfixture/
  python android/tools/dev_fixture.py serve    HTTPS test server on 0.0.0.0:8443 (the emulator reaches the PC at 10.0.2.2)
  python android/tools/dev_fixture.py real [IDS] [TESTED.json]
                                               signed DEV catalog of REAL Android apps from candidates/inventory-rg-rotate.json (all entries without a `hold`, or the comma
                                               separated ids): real GitHub release URLs, hashes and signer certificates, every artifact level "experimental" (EXPERIMENTAL /
                                               UNVERIFIED, no approval). Written to build/devfixture/catalogs/real and, for debug builds, to app/src/debug/assets/dev/catalog.

The catalog entries name GitHub-shaped release URLs (https://github.com/retrohatch-fixture/...) so the same publish gates as the real catalog apply
(tools/trust.py check_index). The DEBUG app maps that prefix to the local server (src/debug DevHooks) and trusts the DEV CA (debug-overrides only).
The release build has neither."""
import base64, datetime, hashlib, http.server, ipaddress, json, os, re, shutil, ssl, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANDROID = HERE.parent
ROOT = ANDROID.parent
sys.path.insert(0, str(ROOT / "tools"))
KEYS = Path.home() / ".retrohatch-dev-android"
OUT = ANDROID / "build" / "devfixture"
DEBUG_SRC = ANDROID / "app" / "src" / "debug"
SDK = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or (Path.home() / "AppData/Local/Android/Sdk"))
PORT = 8443
APPS = [  # id, name, what it exercises
    ("e2e-good", "E2E Good APK", "Correct file, hash and signer: downloads, verifies and installs."),
    ("e2e-badhash", "E2E Bad Hash", "The server hands out a tampered file: the SHA-256 check must reject it."),
    ("e2e-wrongsigner", "E2E Wrong Signer", "Right hash, but signed by another key than the catalog says: the identity check must reject it."),
    ("e2e-wrongpackage", "E2E Wrong Package", "The catalog names another package than the APK contains: the identity check must reject it."),
    ("e2e-slow", "E2E Slow Download", "Throttled server: lets the test cancel a download in progress."),
    ("e2e-added", "E2E Added Later", "Only in the newer catalog (serial 3): proves a refresh brings in new entries."),
]


def need_crypto():
    global x509, hashes, serialization, ec, ed25519, NameOID
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    from cryptography.x509.oid import NameOID


def init():
    need_crypto()
    import trust as T
    KEYS.mkdir(exist_ok=True)
    if not (KEYS / "ca.pem").exists():
        now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RetroHatch DEV fixture CA (test only)")])
        ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(False, False, True, False, False, True, True, False, False), critical=True).sign(ca_key, hashes.SHA256()))
        srv_key = ec.generate_private_key(ec.SECP256R1())
        srv = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "retrohatch dev fixture server")])).issuer_name(ca_name)
               .public_key(srv_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1800))
               .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("10.0.2.2")), x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]), critical=False)
               .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
               .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False).sign(ca_key, hashes.SHA256()))
        pem = serialization.Encoding.PEM
        nopw = serialization.NoEncryption()
        (KEYS / "ca.pem").write_bytes(ca.public_bytes(pem))
        (KEYS / "ca.key").write_bytes(ca_key.private_bytes(pem, serialization.PrivateFormat.PKCS8, nopw))
        (KEYS / "server.pem").write_bytes(srv.public_bytes(pem))
        (KEYS / "server.key").write_bytes(srv_key.private_bytes(pem, serialization.PrivateFormat.PKCS8, nopw))
        dev = ed25519.Ed25519PrivateKey.generate()
        (KEYS / "catalog-dev.key").write_bytes(dev.private_bytes(pem, serialization.PrivateFormat.PKCS8, nopw))
        (KEYS / "catalog-dev.pub").write_text(T.raw_pub(dev).hex() + "\n")
        for f in KEYS.iterdir():
            os.chmod(f, 0o600)
        print("created DEV keys in", KEYS)
    (DEBUG_SRC / "res" / "raw").mkdir(parents=True, exist_ok=True)
    (DEBUG_SRC / "assets" / "dev").mkdir(parents=True, exist_ok=True)
    shutil.copy(KEYS / "ca.pem", DEBUG_SRC / "res" / "raw" / "dev_ca.pem")
    (DEBUG_SRC / "assets" / "dev" / "dev_keys.txt").write_text("# DEV fixture catalog signing key, PUBLIC half (test only, debug builds)\n" + (KEYS / "catalog-dev.pub").read_text())
    (DEBUG_SRC / "assets" / "dev" / "url_map.txt").write_text(f"# debug builds only: fixture URLs -> local HTTPS test server (10.0.2.2 = the PC, seen from the emulator)\nhttps://github.com/retrohatch-fixture/=https://10.0.2.2:{PORT}/\nhttps://traceroute87.github.io/RetroHatch/catalog/=https://10.0.2.2:{PORT}/catalog/\n")
    print("public parts written under", DEBUG_SRC)


def tool(name):
    cands = sorted((SDK / "build-tools").glob("*/" + name + "*"), reverse=True)
    if not cands:
        raise SystemExit(f"{name} not found in {SDK}/build-tools")
    return str(cands[0])


def run(*a, **k):
    r = subprocess.run(a, capture_output=True, text=True, **k)
    if r.returncode:
        raise SystemExit(f"{a[0]} failed: {r.stdout}{r.stderr}")
    return r.stdout


def apk_identity(apk):
    badging = run(tool("aapt2.exe" if os.name == "nt" else "aapt2"), "dump", "badging", str(apk))
    m = re.search(r"package: name='([^']+)' versionCode='(\d+)'", badging)
    certs = run(tool("apksigner.bat" if os.name == "nt" else "apksigner"), "verify", "--print-certs", str(apk))
    sig = re.findall(r"certificate SHA-256 digest: ([0-9a-f]{64})", certs)
    return m.group(1), int(m.group(2)), sig


def build():
    need_crypto()
    import trust as T
    if not (KEYS / "catalog-dev.key").exists():
        init()
    gradle = str(ANDROID / ("gradlew.bat" if os.name == "nt" else "gradlew"))
    print("building :fixtureapp ...")
    run(gradle, "--no-daemon", "-q", ":fixtureapp:assembleDebug", cwd=ANDROID)
    apk = ANDROID / "fixtureapp" / "build" / "outputs" / "apk" / "debug" / "fixtureapp-debug.apk"
    pkg, vc, signers = apk_identity(apk)
    assert pkg == "app.retrohatch.testfixture" and len(signers) == 1, (pkg, signers)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # a second copy signed by a different key (throw-away keystore): same package, different signing certificate
    wrong_ks = OUT / "wrong.jks"
    run("keytool", "-genkeypair", "-keystore", str(wrong_ks), "-storepass", "wrongwrong", "-keypass", "wrongwrong", "-alias", "w", "-keyalg", "EC", "-keysize", "256", "-dname", "CN=wrong signer (test)", "-validity", "3650")
    wrong_apk = OUT / "wrong-signer.apk"
    run(tool("apksigner.bat" if os.name == "nt" else "apksigner"), "sign", "--ks", str(wrong_ks), "--ks-pass", "pass:wrongwrong", "--out", str(wrong_apk), str(apk))
    wrong_pkg, wrong_vc, wrong_signers = apk_identity(wrong_apk)
    assert wrong_pkg == pkg and wrong_signers != signers
    wrong_ks.unlink()

    good = apk.read_bytes()
    tampered = bytearray(good); tampered[len(good) // 2] ^= 0xFF          # same size, different bytes
    served = {  # id -> (declared bytes -> hash/size in the catalog, bytes the server really sends, declared package, declared signers)
        "e2e-good": (good, good, pkg, signers),
        "e2e-badhash": (good, bytes(tampered), pkg, signers),
        "e2e-wrongsigner": (wrong_apk.read_bytes(), wrong_apk.read_bytes(), pkg, signers),
        "e2e-wrongpackage": (good, good, "app.retrohatch.notthis", signers),
        "e2e-slow": (good, good, pkg, signers),
        "e2e-added": (good, good, pkg, signers),
    }
    srv = OUT / "serve"
    cat = OUT / "catalog"
    for d in ("apps", "devices"):
        (cat / d).mkdir(parents=True)
    shutil.copy(ROOT / "catalog" / "devices" / "rg-rotate.json", cat / "devices")
    approvals = []
    for aid, name, why in APPS:
        decl, send, dpkg, dsig = served[aid]
        sha = hashlib.sha256(decl).hexdigest()
        base = f"https://github.com/retrohatch-fixture/{aid}"
        app = {"schema": 1, "id": aid, "name": name, "description": "TEST FIXTURE ONLY - not a real app. " + why, "developer": "retrohatch dev fixture", "source": base,
               "license": "MIT", "category": "utility",
               "artifacts": [{"device": "rg-rotate", "firmware": "android-12", "format": "apk", "status": "available", "version": "1.0.0-fixture",
                              "url": f"{base}/releases/download/v1.0.0/fixture.apk", "sha256": sha, "size": len(decl),
                              "android": {"package": dpkg, "version_code": vc, "signer_sha256": dsig},
                              "compatibility": {"level": "verified", "evidence": [{"sha256": sha, "date": "2026-11-09", "tester": "dev fixture", "note": "synthetic"}]}}]}
        (cat / "apps" / f"{aid}.json").write_text(json.dumps(app, indent=2) + "\n")
        approvals.append({"app": aid, "device": "rg-rotate", "firmware": "android-12", "sha256": sha, "size": len(decl), "release": f"{base}/releases/tag/v1.0.0",
                          "approved_by": "dev fixture", "date": "2026-11-09"})
        f = srv / aid / "releases" / "download" / "v1.0.0" / "fixture.apk"
        f.parent.mkdir(parents=True)
        f.write_bytes(send)
    (cat / "approvals.json").write_text(json.dumps({"schema": 1, "approvals": approvals, "revoked": []}, indent=2) + "\n")

    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    key = load_pem_private_key((KEYS / "catalog-dev.key").read_bytes(), None)
    other = ed25519.Ed25519PrivateKey.generate()
    all_approvals = {a["app"]: a for a in approvals}
    nano_src = ROOT / "tests" / "trust_fixture" / "catalog"

    def catalog_dir(name, ids, nano=False):
        d = OUT / "cats" / name
        for sub in ("apps", "devices"):
            (d / sub).mkdir(parents=True)
        shutil.copy(ROOT / "catalog" / "devices" / "rg-rotate.json", d / "devices")
        appr = []
        for i in ids:
            shutil.copy(cat / "apps" / f"{i}.json", d / "apps"); appr.append(all_approvals[i])
        if nano:   # a valid catalog that has NO app for RG Rotate: one synthetic Nano OPK app (tests/trust_fixture)
            shutil.copy(nano_src / "devices" / "rg-nano.json", d / "devices"); shutil.copy(nano_src / "apps" / "examplepad.json", d / "apps")
            appr += json.loads((nano_src / "approvals.json").read_text())["approvals"]
        (d / "approvals.json").write_text(json.dumps({"schema": 1, "approvals": appr, "revoked": []}, indent=2) + "\n")
        return d

    base_ids = [a[0] for a in APPS if a[0] != "e2e-added"]

    def write(name, serial, ids, signer=key, mutate=None, nano=False):
        doc = T.build(catalog_dir(name, ids, nano), serial, "2026-11-09")
        idx = T.canonical(doc)
        sig = T.sign(idx, signer)
        d = OUT / "catalogs" / name
        d.mkdir(parents=True)
        mutate and mutate(d, idx, sig)
        if not (d / "index.json").exists():
            (d / "index.json").write_bytes(idx); (d / "index.json.sig").write_bytes(sig)

    write("good", 2, base_ids)                                                  # first catalog the app fetches
    write("v3", 3, base_ids + ["e2e-added"])                                    # a newer valid catalog with one more entry
    write("rollback", 1, base_ids)                                              # valid and signed, but older than anything accepted so far
    write("unknownkey", 4, base_ids, signer=other)                              # genuine signature, key not trusted
    def badsig(d, idx, sig):
        s = json.loads(sig); raw = bytearray(base64.b64decode(s["sig"])); raw[5] ^= 1; s["sig"] = base64.b64encode(bytes(raw)).decode()
        (d / "index.json").write_bytes(idx); (d / "index.json.sig").write_bytes(T.canonical(s))
    write("badsig", 4, base_ids, mutate=badsig)
    def tamper(d, idx, sig):
        t = bytearray(idx); t[len(t) // 2] ^= 1
        (d / "index.json").write_bytes(bytes(t)); (d / "index.json.sig").write_bytes(sig)
    write("tampered", 4, base_ids, mutate=tamper)
    write("nomatch", 2, [], nano=True)                                          # valid, but nothing for RG Rotate
    live = srv / "catalog"                                                      # what the app fetches (https://traceroute87.github.io/RetroHatch/catalog/ in debug builds maps here)
    live.mkdir(parents=True)
    for f in ("index.json", "index.json.sig"):
        shutil.copy(OUT / "catalogs" / "good" / f, live / f)
    meta = {"package": pkg, "version_code": vc, "signer_sha256": signers, "wrong_signer_sha256": wrong_signers, "apk_size": len(good), "apk_sha256": hashlib.sha256(good).hexdigest(),
            "apps": [a[0] for a in APPS], "dev_key_id": T.key_id(bytes.fromhex((KEYS / "catalog-dev.pub").read_text().strip()))}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("fixture built:", OUT)
    print(json.dumps(meta, indent=2))


def real(ids=None, tested_file=None):
    """DEV experimental catalog of real apps (all inventory entries without a `hold`, or the given ids). Metadata comes from candidates/inventory-rg-rotate.json (read
    from the real APKs); nothing is typed in by hand. Every artifact is level "experimental": no approval, no claim of testing on RG Rotate. It is signed with the DEV key
    only. tools/trust.py and release builds REJECT such an index on purpose; only debug builds, which trust the DEV key, accept experimental entries."""
    need_crypto()
    import trust as T, validate
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    if not (KEYS / "catalog-dev.key").exists():
        init()
    inv = json.loads((ROOT / "candidates" / "inventory-rg-rotate.json").read_text(encoding="utf-8"))
    tested = json.loads(Path(tested_file).read_text(encoding="utf-8")) if tested_file else {}
    by = {a["id"]: a for a in inv["applications"]}
    dp = ROOT / "candidates" / "descriptions-rg-rotate.json"
    DESCRIPTIONS = json.loads(dp.read_text(encoding="utf-8"))["apps"] if dp.is_file() else {}
    want = [i.strip() for i in ids.split(",") if i.strip()] if ids else [a["id"] for a in inv["applications"] if not a.get("hold")]
    for i in want:
        if i not in by:
            raise SystemExit(f"not in the inventory: {i}")
        if by[i].get("hold"):
            raise SystemExit(f"{i} is on hold: {by[i]['hold']}")
        if by[i]["license"] == "unknown":
            raise SystemExit(f"{i}: licence unknown, cannot enter a catalog")
    d = OUT / "cats" / "real"
    if d.exists():
        shutil.rmtree(d)
    for sub in ("apps", "devices"):
        (d / sub).mkdir(parents=True)
    shutil.copy(ROOT / "catalog" / "devices" / "rg-rotate.json", d / "devices")
    for i in want:
        a = by[i]
        (pk,) = a["packages"]
        repo = a["sources"][0]["url"]
        t = tested.get(repo.removeprefix("https://github.com/"))
        # The text shown to the user comes from candidates/descriptions-rg-rotate.json (hand-written from each project's own README); the UI, not the
        # text, says EXPERIMENTAL. Without an entry there the repository's own one-line description is used and no long text is invented.
        txt = DESCRIPTIONS.get(i, {})
        desc = txt.get("description") or a["description"]
        comp = {"level": "experimental"}
        if t:
            comp["evidence"] = [{"sha256": pk["sha256"], "date": t["date"], "tester": "emulator rotate720 (x86_64, Android 12 API 31)", "note": t["note"]}]
        app = {"schema": 1, "id": re.sub(r"[^a-z0-9-]", "", i.lower()), "name": a["name"], "description": desc, "developer": repo.split("/")[3], "source": repo, "license": a["license"],
               **({"long_description": txt["long_description"]} if txt.get("long_description") else {}), **({"features": txt["features"]} if txt.get("features") else {}),
               "category": "application", "artifacts": [{"device": "rg-rotate", "firmware": "android-12", "format": "apk", "status": "available", "version": a["version"], "url": pk["url"],
                                                          "sha256": pk["sha256"], "size": pk["size"], "android": pk["android"], "compatibility": comp}]}
        (d / "apps" / f"{app['id']}.json").write_text(json.dumps(app, indent=2) + "\n")
    errs = validate.check(d, validate.ROOT / "schema")                 # the shared schema and cross-file rules
    if errs:
        raise SystemExit("catalog invalid: " + "; ".join(errs[:3]))
    doc = {"format": 1, "serial": (datetime.date.today() - datetime.date(2026, 1, 1)).days * 1440 + datetime.datetime.now().hour * 60 + datetime.datetime.now().minute,   # grows every minute, fits the verifier's 2^31 limit
           "generated": time.strftime("%Y-%m-%d"),
           "devices": [json.loads((d / "devices" / "rg-rotate.json").read_text())], "apps": [json.loads(p.read_text()) for p in sorted((d / "apps").glob("*.json"))], "approvals": [], "revoked": []}
    errs = T.strict_patterns(doc)
    if errs or T.shape(doc)[0] > T.MAX_TOKENS:
        raise SystemExit("index format: " + "; ".join(errs[:3]))
    idx = T.canonical(doc)
    key = load_pem_private_key((KEYS / "catalog-dev.key").read_bytes(), None)
    # direct DEV signing on purpose: T.sign() refuses an index without approvals and levels other than "verified" (production rules)
    sig = T.canonical({"v": 1, "alg": "ed25519", "key_id": T.key_id(T.raw_pub(key)), "sig": base64.b64encode(key.sign(idx)).decode()})
    out = OUT / "catalogs" / "real"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_bytes(idx); (out / "index.json.sig").write_bytes(sig)
    (out / "expect.json").write_text(json.dumps({by[i]["packages"][0]["android"]["package"]: by[i]["packages"][0]["android"] for i in want}, indent=1) + chr(10))   # what the e2e test compares the installed app with
    bundled = DEBUG_SRC / "assets" / "dev" / "catalog"                 # debug builds ship this signed DEV snapshot, so the app lists the apps without any server
    bundled.mkdir(parents=True, exist_ok=True)
    (bundled / "index.json").write_bytes(idx); (bundled / "index.json.sig").write_bytes(sig)
    print(f"signed DEV catalog (EXPERIMENTAL, serial {doc['serial']}) with {len(want)} real app(s): {', '.join(want)}\n  -> {out}\n  -> {bundled} (bundled into the debug APK)")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(OUT / "serve"), **k)

    def log_message(self, fmt, *a):
        with open(OUT / "server.log", "a") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % a))

    def copyfile(self, src, dst):
        if "/e2e-slow/" in self.path:                                           # 1 KB/s: ~8 s even for the 8 KB test APK
            while chunk := src.read(256):
                dst.write(chunk); dst.flush(); time.sleep(0.25)
        else:
            super().copyfile(src, dst)


def serve():
    if not (OUT / "serve").exists():
        raise SystemExit("run 'build' first")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(KEYS / "server.pem", KEYS / "server.key")
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"serving {OUT / 'serve'} on https://0.0.0.0:{PORT}/ (emulator: https://10.0.2.2:{PORT}/)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    real(*(sys.argv[2:4] if sys.argv[2:3] != ["-"] else [None] + sys.argv[3:4])) if cmd == "real" else {"init": init, "build": build, "serve": serve}[cmd]()
