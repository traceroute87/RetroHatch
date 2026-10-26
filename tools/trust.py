#!/usr/bin/env python3
"""Trusted catalog: build -> sign -> verify. Host side, Ed25519 via the `cryptography` package (no custom crypto).

  trust.py keygen --out KEYFILE                   (KEYFILE must live outside the repo)
  trust.py build  [--catalog DIR] [--out index.json] [--serial N] [--date YYYY-MM-DD] [--expires YYYY-MM-DD]
  trust.py sign   index.json --key KEYFILE [--out index.json.sig]
  trust.py verify index.json [--sig FILE] [--pubkey HEX ...] [--state FILE]

Trust decisions stay separate: artifact integrity (sha256/size), source identity (URL under the source repo's release),
compatibility (verified + evidence for the exact sha256), and human approval (catalog/approvals.json). A catalog
signature only says "the key holder published this"; it never replaces any of those checks, and `check_index`
re-runs them so neither build nor sign can bypass them.
"""
import argparse, base64, hashlib, json, os, re, sys, tempfile
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

import validate

ROOT = validate.ROOT.parent
FORMAT = 1
MAX_INDEX = 256 * 1024     # the Nano verifier (core/rh_catalog.h) uses the same limits
MAX_TOKENS = 8192
MAX_DEPTH = 12
MAX_INT = 2**31 - 1
MAX_ITEMS = 256
MAX_DEVICES = 16
PUBLISH_LEVELS = {"verified"}   # hardware tested on the exact sha256; community/experimental are never published
# Raw 32-byte Ed25519 public keys (hex) the verifier trusts. Empty until the production key is generated offline:
# an empty list makes verify() fail closed. Rotation: see docs/TRUST.md (ship [old, new] in a client update first).
def _prod_keys():
    p = ROOT / "catalog" / "production.pub"   # written by tools/set_prod_key.py; absent until the key ceremony
    return (p.read_text().strip(),) if p.is_file() else ()


TRUSTED_KEYS = _prod_keys()
TOP = {"format", "serial", "generated", "devices", "apps", "approvals", "revoked"}


class TrustError(Exception):
    pass


def _deny():
    src = (ROOT / "platforms" / "nano" / "rh_install.c").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"deny\[\]\s*=\s*\{(.*?)NULL", src, re.S)
    names = {n.lower() for n in re.findall(r'"([^"]+)"', m.group(1))} if m else set()
    if "tarafi.opk" not in names:
        raise RuntimeError("could not read the engine destination denylist from rh_install.c")
    return names


DENY = _deny()


# ---- canonical JSON ----------------------------------------------------------------------------

def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def strict_loads(b):
    """UTF-8 JSON with no duplicate keys, NaN or floats. Raises TrustError."""
    def pairs(ps):
        d = {}
        for k, v in ps:
            if k in d:
                raise TrustError(f"duplicate key '{k}'")
            d[k] = v
        return d
    def bad(x):
        raise TrustError(f"disallowed number '{x}'")
    def to_int(x):
        if x.startswith("-") or int(x) > MAX_INT:
            raise TrustError(f"disallowed number '{x}'")
        return int(x)
    try:
        return json.loads(b.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad, parse_float=bad, parse_int=to_int)
    except TrustError:
        raise
    except (ValueError, UnicodeDecodeError) as e:
        raise TrustError(f"malformed JSON: {e}")


# ---- policy checks (shared by build, sign, verify, artifact_verify) -----------------------------

def release_ok(source, url, release=None):
    """Artifact URL must be a release download of the entry's own GitHub source repo (identity of the URL, not the publisher)."""
    m = re.fullmatch(r"https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?", source or "")
    if not m:
        return False
    base = f"https://github.com/{m.group(1)}/{m.group(2)}".lower()
    u = re.fullmatch(re.escape(base) + r"/releases/download/([^/\s]+)/[^/\s]+", (url or "").lower())
    if not u:
        return False
    return release is None or release.lower() == f"{base}/releases/tag/{u.group(1)}"


def approval_key(a):
    return (a.get("app"), a.get("device"), a.get("firmware"), a.get("sha256"))


def dest_problems(apps):
    """Protected destinations, and two artifacts that would write the same file on one device (case-insensitive: FAT).
    The same app may reuse a file name across different firmware profiles; anything else is a conflict."""
    errs, seen = [], []
    for app in apps:
        for art in app.get("artifacts", []):
            d = (art.get("install") or {}).get("dest_name")
            if not d:
                errs.append(f"{app['id']}: artifact has no install.dest_name")
                continue
            if d.lower() in DENY or not d.lower().endswith(".opk"):
                errs.append(f"{app['id']}: destination '{d}' is protected or not .opk")
            for (a, dev, fw, other) in seen:
                if dev == art["device"] and other == d.lower() and (a != app["id"] or fw == art["firmware"]):
                    errs.append(f"{app['id']}: destination '{d}' also used by '{a}'")
            seen.append((app["id"], art["device"], art["firmware"], d.lower()))
    return errs


def shape(v, depth=0):
    """-> (tokens, max depth) the way the native parser counts them."""
    if isinstance(v, dict):
        t, d = 1, depth
        for x in v.values():
            a, b = shape(x, depth + 1)
            t, d = t + 1 + a, max(d, b)
        return t, d
    if isinstance(v, list):
        t, d = 1, depth
        for x in v:
            a, b = shape(x, depth + 1)
            t, d = t + a, max(d, b)
        return t, d
    return 1, depth


SHA = re.compile(r"[0-9a-f]{64}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


URLISH = re.compile(r"https://[\x21\x23-\x5b\x5d-\x7e]+")   # ASCII, no space, quote or backslash: what the device parser accepts
DEST = re.compile(r"[A-Za-z0-9._-]{1,64}")


def strict_patterns(doc):
    """jsonschema patterns end in `$`, which also matches before a trailing newline; re-check the fields the device parser is strict about."""
    errs = []
    def need(ok, what):
        if not ok:
            errs.append(f"strict format: {what}")
    for d in doc["devices"]:
        need(ID.fullmatch(d["id"]) and all(ID.fullmatch(f) for f in d["firmware"]), f"device {d['id']!r} ids")
    for a in doc["apps"]:
        need(ID.fullmatch(a["id"]), f"app id {a['id']!r}")
        need(URLISH.fullmatch(a["source"]) and ("website" not in a or URLISH.fullmatch(a["website"])), f"{a['id']} urls")
        for x in a["artifacts"]:
            need(ID.fullmatch(x["device"]) and ID.fullmatch(x["firmware"]) and SHA.fullmatch(x.get("sha256", "")) and URLISH.fullmatch(x.get("url", "")),
                 f"{a['id']} artifact fields")
            need(DEST.fullmatch((x.get("install") or {}).get("dest_name", "")), f"{a['id']} dest_name")
            for e in x["compatibility"].get("evidence", []):
                need(SHA.fullmatch(e["sha256"]) and DATE.fullmatch(e["date"]), f"{a['id']} evidence")
    return errs


def check_index(doc):
    """All publish gates on an index document. -> list of errors (empty = ok)."""
    if not isinstance(doc, dict):
        return ["index is not an object"]
    errs = []
    tokens, depth = shape(doc)
    if tokens > MAX_TOKENS or depth > MAX_DEPTH:
        return [f"index too complex for the device verifier ({tokens} tokens, depth {depth})"]
    extra = set(doc) - TOP - {"expires"}
    if extra or TOP - set(doc):
        return [f"index keys wrong: missing {sorted(TOP - set(doc))}, unexpected {sorted(extra)}"]
    if doc["format"] != FORMAT or isinstance(doc["format"], bool):
        errs.append(f"unsupported format {doc['format']!r}")
    if not isinstance(doc["serial"], int) or isinstance(doc["serial"], bool) or doc["serial"] < 1:
        errs.append("serial must be an integer >= 1")
    for f in ("generated", "expires"):
        if f in doc and not (isinstance(doc[f], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc[f])):
            errs.append(f"{f} must be YYYY-MM-DD")
    if not all(isinstance(doc[k], list) and all(isinstance(x, dict) for x in doc[k]) for k in ("devices", "apps", "approvals", "revoked")):
        return errs + ["devices/apps/approvals/revoked must be lists of objects"]
    if len(doc["devices"]) > MAX_DEVICES or len(doc["approvals"]) > MAX_ITEMS:
        return errs + ["too many devices or approvals for the device verifier"]
    for kind in ("devices", "apps"):
        ids = [x.get("id") for x in doc[kind]]
        if len(ids) != len(set(map(str, ids))):
            errs.append(f"duplicate {kind[:-1]} id")
    with tempfile.TemporaryDirectory() as t:
        for kind in ("devices", "apps"):
            (Path(t) / kind).mkdir()
            for x in doc[kind]:
                if not isinstance(x.get("id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", x["id"]):
                    return errs + [f"{kind}: bad id"]
                (Path(t) / kind / f"{x['id']}.json").write_text(json.dumps(x), encoding="utf-8")
        errs += validate.check(Path(t), validate.ROOT / "schema")
    if errs:   # structure is not trustworthy enough for the policy pass below
        return errs
    errs += strict_patterns(doc)
    appr = {}
    for a in doc["approvals"]:
        if set(a) != {"app", "device", "firmware", "sha256", "size", "release", "approved_by", "date"}:
            errs.append(f"approval {a.get('app')}: wrong fields")
            continue
        if not (all(isinstance(a[k], str) for k in ("app", "device", "firmware", "sha256", "release", "approved_by", "date"))
                  and ID.fullmatch(a["app"]) and ID.fullmatch(a["device"]) and ID.fullmatch(a["firmware"]) and SHA.fullmatch(a["sha256"])
                  and DATE.fullmatch(a["date"]) and a["approved_by"] and URLISH.fullmatch(a["release"])
                  and isinstance(a["size"], int) and not isinstance(a["size"], bool) and a["size"] >= 1):
            errs.append(f"approval {a.get('app')}: bad field value")
            continue
        if approval_key(a) in appr:
            errs.append(f"duplicate approval {approval_key(a)}")
        appr[approval_key(a)] = a
    revoked = set()
    for r in doc["revoked"]:
        if set(r) != {"app", "sha256", "reason"} or not (all(isinstance(r[k], str) for k in r) and ID.fullmatch(r["app"])
                                                       and SHA.fullmatch(r["sha256"]) and r["reason"]):
            errs.append("revoked entry: wrong fields")
        else:
            revoked.add((r["app"], r["sha256"]))
    used = set()
    if sum(len(a.get("artifacts", [])) for a in doc["apps"]) > MAX_ITEMS:
        errs.append("too many artifacts for the device verifier")
    for app in doc["apps"]:
        if not app.get("artifacts"):
            errs.append(f"{app['id']}: published app has no artifacts")
        for art in app.get("artifacts", []):
            w = f"{app['id']}/{art.get('device')}"
            k = (app["id"], art.get("device"), art.get("firmware"), art.get("sha256"))
            if art.get("status") != "available":
                errs.append(f"{w}: only available artifacts may be published")
            if art.get("compatibility", {}).get("level") not in PUBLISH_LEVELS:
                errs.append(f"{w}: compatibility level '{art.get('compatibility', {}).get('level')}' is not publishable")
            if not release_ok(app.get("source"), art.get("url")):
                errs.append(f"{w}: url is not a release download of the source repo")
            a = appr.get(k)
            if not a:
                errs.append(f"{w}: no human approval for this exact sha256")
            else:
                used.add(k)
                if a["size"] != art.get("size") or not release_ok(app.get("source"), art.get("url"), a["release"]):
                    errs.append(f"{w}: approval does not match artifact size/release")
            if (app["id"], art.get("sha256")) in revoked:
                errs.append(f"{w}: artifact is revoked")
    errs += [f"approval {k} matches no published artifact" for k in sorted(set(appr) - used, key=str)]
    return errs + dest_problems(doc["apps"])


# ---- build -------------------------------------------------------------------------------------

def build(catalog, serial, day, expires=None):
    """Catalog dir -> index dict containing ONLY approved, verified, available artifacts. Raises TrustError."""
    default = Path(catalog).resolve() == validate.ROOT.resolve()
    errs = validate.check(Path(catalog), None if default else validate.ROOT / "schema")
    if errs:
        raise TrustError("catalog invalid: " + errs[0])
    load = validate.load
    raw = load(Path(catalog) / "approvals.json") if (Path(catalog) / "approvals.json").is_file() else {"schema": 1, "approvals": [], "revoked": []}
    if set(raw) != {"schema", "approvals", "revoked"} or raw["schema"] != 1:
        raise TrustError("approvals.json must be {schema:1, approvals:[], revoked:[]}")
    apps = {p.stem: load(p) for p in sorted((Path(catalog) / "apps").glob("*.json"))}
    revoked = {(r["app"], r["sha256"]) for r in raw["revoked"]}
    keep, out_apps = {approval_key(a): a for a in raw["approvals"]}, []
    if len(keep) != len(raw["approvals"]):
        raise TrustError("duplicate approval entries")
    keep = {k: a for k, a in keep.items() if (k[0], k[3]) not in revoked}   # revoked: approval dropped, hash stays in `revoked`
    for a in apps.values():
        arts = [x for x in a["artifacts"] if x["status"] == "available" and (a["id"], x["sha256"]) not in revoked
                and (a["id"], x["device"], x["firmware"], x["sha256"]) in keep]
        for x in arts:   # approved but not publishable: say so instead of silently dropping
            if x["compatibility"]["level"] not in PUBLISH_LEVELS:
                raise TrustError(f"{a['id']}: approved artifact has level '{x['compatibility']['level']}', need verified")
        if arts:
            out_apps.append({**a, "artifacts": arts})
    pub = {(a["id"], x["device"], x["firmware"], x["sha256"]) for a in out_apps for x in a["artifacts"]}
    orphan = sorted(set(keep) - pub, key=str)
    if orphan:
        raise TrustError(f"approvals without a publishable artifact: {orphan[0]}")
    doc = {"format": FORMAT, "serial": serial, "generated": day, "devices": [load(p) for p in sorted((Path(catalog) / "devices").glob("*.json"))],
           "apps": out_apps, "approvals": sorted(keep.values(), key=lambda a: str(approval_key(a))),
           "revoked": sorted(raw["revoked"], key=lambda r: (r["app"], r["sha256"]))}
    if expires:
        doc["expires"] = expires
    errs = check_index(doc)
    if errs:
        raise TrustError("; ".join(errs))
    return doc


# ---- sign / verify -----------------------------------------------------------------------------

def key_id(pub_raw):
    return hashlib.sha256(pub_raw).hexdigest()[:16]


def raw_pub(priv):
    return priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def sign(index_bytes, priv):
    """Refuses to sign anything check_index or the canonical form rejects. Ed25519 is deterministic (RFC 8032)."""
    doc = strict_loads(index_bytes)
    if canonical(doc) != index_bytes:
        raise TrustError("index is not in canonical form")
    errs = check_index(doc)
    if errs:
        raise TrustError("refusing to sign: " + "; ".join(errs))
    sig = priv.sign(index_bytes)
    return canonical({"v": 1, "alg": "ed25519", "key_id": key_id(raw_pub(priv)), "sig": base64.b64encode(sig).decode()})


def verify(index_bytes, sig_bytes, trusted=None, state=None, now=None):
    """Fail closed. -> (doc, new_state, warnings). `state` = {"serial", "sha256"} of the newest index accepted so far.
    `now` (date or None) only produces a warning for `expires`; the Nano clock is never trusted for a decision."""
    trusted = TRUSTED_KEYS if trusted is None else trusted
    if not trusted:
        raise TrustError("no trusted key configured")
    if not isinstance(index_bytes, bytes) or not isinstance(sig_bytes, bytes) or not index_bytes or not sig_bytes:
        raise TrustError("missing index or signature")
    if len(index_bytes) > MAX_INDEX or len(sig_bytes) > 4096:
        raise TrustError("index or signature too large")
    s = strict_loads(sig_bytes)
    if not isinstance(s, dict) or set(s) != {"v", "alg", "key_id", "sig"} or s["v"] != 1 or s["alg"] != "ed25519":
        raise TrustError("unsupported signature document")
    try:
        sig = base64.b64decode(s["sig"], validate=True)
        if base64.b64encode(sig).decode() != s["sig"]:
            raise ValueError("non-canonical base64")
        keys = {key_id(bytes.fromhex(k)): bytes.fromhex(k) for k in trusted}
    except (ValueError, TypeError):
        raise TrustError("malformed signature or key")
    if len(sig) != 64 or s["key_id"] not in keys:
        raise TrustError("unknown signing key" if len(sig) == 64 else "malformed signature")
    try:
        Ed25519PublicKey.from_public_bytes(keys[s["key_id"]]).verify(sig, index_bytes)
    except (InvalidSignature, ValueError):
        raise TrustError("bad signature")
    doc = strict_loads(index_bytes)   # parse only after the signature holds
    if canonical(doc) != index_bytes:
        raise TrustError("index is not in canonical form")
    errs = check_index(doc)
    if errs:
        raise TrustError("signed index violates policy: " + errs[0])
    h = hashlib.sha256(index_bytes).hexdigest()
    if state:
        if doc["serial"] < state["serial"]:
            raise TrustError(f"rollback: serial {doc['serial']} < {state['serial']}")
        if doc["serial"] == state["serial"] and h != state["sha256"]:
            raise TrustError("same serial, different content")
    warn = []
    if now and now.year >= 2026 and "expires" in doc and now.isoformat() > doc["expires"]:
        warn.append(f"catalog expired {doc['expires']} (clock may be wrong; not enforced)")
    return doc, {"serial": doc["serial"], "sha256": h}, warn


# ---- CLI ---------------------------------------------------------------------------------------

def outside_repo(p):
    p = Path(p).resolve()
    if ROOT.resolve() in (p, *p.parents):
        raise TrustError(f"{p} is inside the repository; keep signing keys elsewhere")
    return p


def load_key(path):
    pw = os.environ.get("RH_KEY_PASSPHRASE")
    return serialization.load_pem_private_key(outside_repo(path).read_bytes(), pw.encode() if pw else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    k = sp.add_parser("keygen"); k.add_argument("--out", required=True)
    b = sp.add_parser("build"); b.add_argument("--catalog", type=Path, default=validate.ROOT)
    b.add_argument("--out", type=Path, default=ROOT / "build" / "index.json"); b.add_argument("--serial", type=int)
    b.add_argument("--date", default=date.today().isoformat()); b.add_argument("--expires")
    g = sp.add_parser("sign"); g.add_argument("index", type=Path); g.add_argument("--key", required=True); g.add_argument("--out", type=Path)
    v = sp.add_parser("verify"); v.add_argument("index", type=Path); v.add_argument("--sig", type=Path)
    v.add_argument("--pubkey", action="append"); v.add_argument("--state", type=Path)
    a = ap.parse_args()
    try:
        if a.cmd == "keygen":
            out = outside_repo(a.out)
            if out.exists():
                raise TrustError("key file exists; refusing to overwrite")
            priv = Ed25519PrivateKey.generate()
            pw = os.environ.get("RH_KEY_PASSPHRASE")
            enc = serialization.BestAvailableEncryption(pw.encode()) if pw else serialization.NoEncryption()
            out.write_bytes(priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc))
            os.chmod(out, 0o600)
            print(f"public key (hex): {raw_pub(priv).hex()}\nkey id: {key_id(raw_pub(priv))}\nencrypted: {bool(pw)}")
        elif a.cmd == "build":
            serial = a.serial
            if serial is None:
                prev = strict_loads(a.out.read_bytes())["serial"] if a.out.is_file() else 0
                serial = prev + 1
            doc = build(a.catalog, serial, a.date, a.expires)
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_bytes(canonical(doc))
            print(f"{a.out}: serial {serial}, {len(doc['apps'])} apps (unsigned)")
        elif a.cmd == "sign":
            data = a.index.read_bytes()
            out = a.out or a.index.with_name(a.index.name + ".sig")
            out.write_bytes(sign(data, load_key(a.key)))
            print(f"signed {a.index} -> {out}")
        else:
            data = a.index.read_bytes()
            sigf = a.sig or a.index.with_name(a.index.name + ".sig")
            st = json.loads(a.state.read_text()) if a.state and a.state.is_file() else None
            doc, ns, warn = verify(data, sigf.read_bytes() if sigf.is_file() else b"", a.pubkey, st, date.today())
            if a.state:
                a.state.write_text(json.dumps(ns))
            print(f"OK serial {ns['serial']}, {len(doc['apps'])} apps")
            for w in warn:
                print("warning:", w)
    except (TrustError, OSError, ValueError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
