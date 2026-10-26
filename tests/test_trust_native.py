"""Run: python tests/test_trust_native.py   (needs WSL Ubuntu with gcc/make; skips with a message otherwise)

Cross-checks the native verifier (core/rh_catalog.c + vendored Monocypher) against tools/trust.py:
 - vendored files are unmodified; the denylist and the Ed25519 entry point match what the design promises
 - Python-signed catalogs verify natively; every tamper/policy/limit case is rejected with the expected code
 - differential: ~3000 validly-signed mutated indexes + byte-level fuzz; the native verifier must reject everything
   Python rejects (it may be stricter, never looser), and the two must agree on every accepted index
 - performance and peak memory of one verification
"""
import copy, hashlib, json, os, random, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE.parent / "tools"))
import trust as T
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FX = HERE / "trust_fixture"
PINNED = {  # vendor/monocypher/PROVENANCE.md
    "monocypher.c": "57eb914fc88136119bd41655cccb8c250048bf54d470540625186f8ab16f64be",
    "monocypher.h": "c494da712122da7ff679fdcf318a5317e84972b6c950fe9d896212947797facd",
    "monocypher-ed25519.c": "60fce3578fb00b00da96490653d993c4cb427b1e1be38183285c66e04d22cc18",
    "monocypher-ed25519.h": "abc4fad381879f5c29176ebe014b9189956b3dfe0a3e36459b6990bc57212380",
    "LICENCE.md": "5f8360e4c06ddcc584bdb4b210c6af824c4bb301e6a9a521869b6d90795ca4b3",
    "AUTHORS.md": "75a4d04559754a1016006f2c0e194cc7b459583cf9b1e2ce4ec10c74cb3de578",
}
for name, h in PINNED.items():
    assert hashlib.sha256((ROOT / "vendor/monocypher" / name).read_bytes()).hexdigest() == h, f"vendored {name} was modified"

# the verifier must use standard Ed25519 (SHA-512), never Monocypher's default BLAKE2b EdDSA
src = (ROOT / "core/rh_catalog.c").read_text()
assert "crypto_ed25519_check(" in src and "crypto_eddsa_check" not in src and "monocypher-ed25519.h" in src
assert "monocypher.h\"" not in src.replace("monocypher-ed25519.h", "")

# denylist copy in C == engine denylist (T.DENY is parsed from rh_install.c)
m = re.search(r"deny\[\] = \{(.*?)NULL\}", src, re.S)
assert {x.lower() for x in re.findall(r'"([^"]+)"', m.group(1))} == T.DENY, "rh_catalog.c denylist drifted from rh_install.c"

if subprocess.run(["wsl", "-d", "Ubuntu", "--", "true"], capture_output=True).returncode != 0:
    print("SKIP: WSL Ubuntu not available")
    sys.exit(0)


def wsl_path(p):
    p = Path(p).resolve()
    return "/mnt/" + p.drive[0].lower() + "/" + "/".join(p.parts[1:])


def wsl(*args, **kw):
    return subprocess.run(["wsl", "-d", "Ubuntu", "--", *args], capture_output=True, text=True, **kw)


r = wsl("bash", "-c", f"cd {wsl_path(HERE)} && make native-test native-tools 2>&1 | tail -3")
assert "native tests OK" in r.stdout and r.returncode == 0, r.stdout + r.stderr
print(r.stdout.strip().splitlines()[0])

ASAN, HOST = wsl_path(ROOT / "build/rh_verify_asan"), wsl_path(ROOT / "build/rh_verify_host")
KEY, KEY2 = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
PUB, PUB2 = T.raw_pub(KEY).hex(), T.raw_pub(KEY2).hex()
W = Path(tempfile.mkdtemp(dir=ROOT / "build"))
DEV, FW = "rg-nano", "funkeyos-drum78"
OK, E = 0, {n: i for i, n in enumerate("OK ARG SIZE NOKEY SIGDOC UNKNOWN_KEY BADSIG PARSE POLICY DEVICE ROLLBACK FORK LIMIT NOMEM".split())}


def sigdoc(payload, key=KEY, **over):
    d = {"v": 1, "alg": "ed25519", "key_id": T.key_id(T.raw_pub(key)), "sig": __import__("base64").b64encode(key.sign(payload)).decode()}
    d.update(over)
    return T.canonical(d)


def run_batch(cases, keys=(PUB,), state=None, dev=DEV, fw=FW, exe=ASAN):
    """cases: [(index_bytes, sig_bytes)] -> [(rc, text)] from ONE native process."""
    lines = []
    for i, (ib, sb) in enumerate(cases):
        a, b = W / f"{i}.idx", W / f"{i}.sig"
        a.write_bytes(ib)
        if sb is not None:
            b.write_bytes(sb)
        elif b.exists():
            b.unlink()
        lines.append(f"{wsl_path(a)} {wsl_path(b)}")
    lst = W / "list.txt"
    lst.write_text("\n".join(lines) + "\n")
    args = [exe, "--batch", wsl_path(lst), "--device", dev, "--firmware", fw]
    for k in keys:
        args += ["--pubkey", k]
    if state:
        args += ["--state", wsl_path(state)]
    r = wsl(*args)
    out = []
    for ln in r.stdout.splitlines():
        parts = ln.split(" ", 2)
        out.append((OK, ln) if parts[1] == "OK" else (int(parts[2].split()[0]), ln))
    assert len(out) == len(cases), r.stdout + r.stderr
    assert "ERROR" not in r.stderr and "runtime error" not in r.stderr, r.stderr   # ASan/UBSan clean
    return out


def py(idx, sig, keys=(PUB,), state=None):
    try:
        T.verify(idx, sig, list(keys), state)
        return True
    except T.TrustError:
        return False


def one(idx, sig, **kw):
    return run_batch([(idx, sig)], **kw)[0]


# ---------------- base catalogs ----------------
base = T.build(FX / "catalog", 3, "2026-10-26", "2026-12-31")
idx = T.canonical(base)
sig = sigdoc(idx)
assert py(idx, sig)
rc, line = one(idx, sig)
assert rc == OK and "serial=3 apps=1 artifacts=1" in line and "expires=2026-12-31" in line and hashlib.sha256(idx).hexdigest() in line, line
ex_idx, ex_sig = (FX / "signed" / "index.json").read_bytes(), (FX / "signed" / "index.json.sig").read_bytes()
rc, line = one(ex_idx, ex_sig, keys=((FX / "signed" / "PUBKEY.hex").read_text().strip(),))
assert rc == OK, line                                                      # the committed example verifies natively too

# a richer base: second device, second app, revoked entry, expires
rich = copy.deepcopy(base)
dev2 = copy.deepcopy(rich["devices"][0]); dev2.update(id="other-nano", firmware=["fw-two"])
app2 = copy.deepcopy(rich["apps"][0]); app2.update(id="otherpad", source="https://github.com/retrohatch-fixture/otherpad")
a2 = app2["artifacts"][0]; a2.update(device="other-nano", firmware="fw-two", url="https://github.com/retrohatch-fixture/otherpad/releases/download/v2/o.opk",
                                     sha256="e" * 64, size=99)
a2["install"] = {"dest_name": "otherpad.opk"}
a2["compatibility"] = {"level": "verified", "evidence": [{"sha256": "e" * 64, "date": "2026-10-26", "tester": "t", "note": "n"}]}
rich["devices"].append(dev2); rich["apps"].append(app2)
rich["approvals"].append({"app": "otherpad", "device": "other-nano", "firmware": "fw-two", "sha256": "e" * 64, "size": 99,
                          "release": "https://github.com/retrohatch-fixture/otherpad/releases/tag/v2", "approved_by": "me", "date": "2026-10-26"})
rich["revoked"].append({"app": "gone", "sha256": "f" * 64, "reason": "bad"})
assert T.check_index(rich) == [], T.check_index(rich)
ridx = T.canonical(rich)
assert one(ridx, sigdoc(ridx))[0] == OK and one(ridx, sigdoc(ridx), dev="other-nano", fw="fw-two")[1].count("artifacts=1") == 1

# ---------------- explicit rejection cases (expected native codes) ----------------
def expect(code, idx_, sig_, **kw):
    rc, line = one(idx_, sig_, **kw)
    assert rc == E[code], (code, line)
    return line


expect("BADSIG", idx.replace(b"ExamplePad", b"ExamplePwn"), sig)          # modified catalog
expect("BADSIG", idx + b"\n", sig)
expect("BADSIG", idx[:-1], sig)
bad = bytearray(__import__("base64").b64decode(json.loads(sig)["sig"])); bad[10] ^= 1
expect("BADSIG", idx, sigdoc(idx, sig=__import__("base64").b64encode(bytes(bad)).decode()))   # modified signature
expect("SIZE", idx, None)                                                   # missing signature
expect("SIZE", idx, b"")
expect("SIGDOC", idx, b"{}")
expect("SIGDOC", idx, b"not json")
expect("SIGDOC", idx, sig.replace(b'"v":1', b'"v":2'))
expect("SIGDOC", idx, sigdoc(idx, alg="ed448"))
expect("SIGDOC", idx, sigdoc(idx, sig="AAAA"))                              # wrong signature length
expect("SIGDOC", idx, sigdoc(idx, sig="A" * 85 + "B=="))                     # right length, non-canonical padding bits
expect("SIGDOC", idx, sigdoc(idx, key_id="XYZ"))
expect("SIGDOC", idx, sig[:-1] + b",}")                                     # malformed
expect("SIGDOC", idx, sig.replace(b'"alg"', b'"alg":"ed25519","alg"'))      # duplicate field
expect("SIGDOC", idx, json.dumps(json.loads(sig), indent=1).encode())       # non-canonical signature document
expect("SIGDOC", idx, sig + b" ")
expect("SIGDOC", idx, b"x" * 1024)
expect("SIZE", idx, b"x" * 1025)                                            # signature length bound, before crypto
expect("UNKNOWN_KEY", idx, sig, keys=(PUB2,))                               # incorrect public key
expect("UNKNOWN_KEY", idx, sigdoc(idx, key_id="0" * 16))
expect("NOKEY", idx, sig, keys=())                                          # no trusted key configured (fail closed)
expect("BADSIG", idx, sigdoc(idx, key=KEY2, key_id=T.key_id(T.raw_pub(KEY))))   # signed by another key, claims ours
# key rotation: overlap accepts both, retired / not-yet-trusted keys are rejected
assert one(idx, sig, keys=(PUB, PUB2))[0] == OK and one(idx, sigdoc(idx, key=KEY2), keys=(PUB, PUB2))[0] == OK
expect("UNKNOWN_KEY", idx, sig, keys=(PUB2,))
expect("UNKNOWN_KEY", idx, sigdoc(idx, key=KEY2), keys=(PUB,))
# device / firmware compatibility
expect("DEVICE", idx, sig, dev="some-other-handheld")
expect("DEVICE", idx, sig, fw="funkeyos-future")
# size and structure limits (properly signed, so only the limits can reject)
big = b"[" + b"0," * (T.MAX_INDEX // 2) + b"0]"
expect("SIZE", big, sigdoc(big))
many = T.canonical({**base, "revoked": [{"app": "a", "sha256": "0" * 64, "reason": "r"}] * 1300})   # > 8192 tokens, < 256 KiB
assert len(many) < T.MAX_INDEX
expect("LIMIT", many, sigdoc(many))
deep = b"[" * 40 + b"]" * 40
expect("LIMIT", deep, sigdoc(deep))
expect("PARSE", b"[]", sigdoc(b"[]"))
for raw in (b'{"a":1,"a":2}', b'{"b":1,"a":2}', b'{"a":1.5}', b'{"a":-1}', b'{"a":01}', b'{"a":1e3}', b'{"a": 1}', b'{"a":1}\n', b'{"a":"\\u0041"}',
            b'{"a":"\\/"}', b'{"a":"\\u00E9"}', b'{"a":"\xc3\xa9"}', b'{"a":"\x7f"}', b'{"a":2147483648}', b'{"\\u0061":1}', b"", b"{", b'{"a":tru}', b'{"a":nul}'):
    rc = one(raw, sigdoc(raw))[0]
    assert rc in (E["PARSE"], E["SIZE"]), (raw, rc)
    assert not py(raw, sigdoc(raw))
# canonical forms Python emits must parse natively (parse ok => reaches policy => POLICY, not PARSE)
for raw in (b'{"a":"\\u00e9\\ud83d\\ude00\\u007f\\u0001\\n\\"\\\\"}', b'{"a":""}', b'{"a":[true,false,null,0,12]}'):
    assert one(raw, sigdoc(raw))[0] == E["POLICY"], raw
assert T.canonical(json.loads(b'{"a":"\\u00e9\\ud83d\\ude00\\u007f\\u0001\\n\\"\\\\"}')) == b'{"a":"\\u00e9\\ud83d\\ude00\\u007f\\u0001\\n\\"\\\\"}'

# rollback / fork (state file as the caller would persist it)
def state_file(serial, h):
    p = W / f"state{serial}.txt"
    p.write_text(f"{serial} {h}\n")
    return p


h3 = hashlib.sha256(idx).hexdigest()
assert one(idx, sig, state=state_file(3, h3))[0] == OK                      # same index again (offline re-check)
assert one(idx, sig, state=state_file(2, "0" * 64))[0] == OK                # newer than stored
expect("ROLLBACK", idx, sig, state=state_file(4, "0" * 64))
expect("FORK", idx, sig, state=state_file(3, "1" * 64))
older = T.canonical(T.build(FX / "catalog", 2, "2026-10-26"))
expect("ROLLBACK", older, sigdoc(older), state=state_file(3, h3))
assert py(older, sigdoc(older), state={"serial": 2, "sha256": hashlib.sha256(older).hexdigest()})

# ---------------- policy: a valid signature must not launder a bad index ----------------
def signed_mut(f, b=base):
    d = copy.deepcopy(b); f(d)
    raw = T.canonical(d)
    return raw, sigdoc(raw)


art = lambda d: d["apps"][0]["artifacts"][0]
POLICY = {
    "no approval": lambda d: d["approvals"].clear(),
    "orphan approval": lambda d: d["approvals"].append({**d["approvals"][0], "sha256": "b" * 64}),
    "level community": lambda d: art(d)["compatibility"].update(level="community"),
    "unavailable": lambda d: art(d).update(status="unavailable"),
    "foreign url": lambda d: art(d).update(url="https://github.com/evil/x/releases/download/v1/a.opk"),
    "non-release url": lambda d: art(d).update(url="https://github.com/retrohatch-fixture/examplepad/raw/main/a.opk"),
    "protected dest": lambda d: art(d)["install"].update(dest_name="TaraFi.opk"),
    "protected dest case": lambda d: art(d)["install"].update(dest_name="RETROHATCH.OPK"),
    "revoked": lambda d: d["revoked"].append({"app": "examplepad", "sha256": art(d)["sha256"], "reason": "r"}),
    "approval size": lambda d: d["approvals"][0].update(size=1),
    "approval release": lambda d: d["approvals"][0].update(release="https://github.com/retrohatch-fixture/examplepad/releases/tag/v9"),
    "unknown license": lambda d: d["apps"][0].update(license="unknown"),
    "unknown device": lambda d: art(d).update(device="ghost"),
    "unknown firmware": lambda d: art(d).update(firmware="ghost"),
    "format mismatch": lambda d: art(d).update(format="apk"),
    "evidence for other hash": lambda d: art(d)["compatibility"]["evidence"][0].update(sha256="c" * 64),
    "no evidence": lambda d: art(d)["compatibility"].pop("evidence"),
    "extra top key": lambda d: d.update(keys=[PUB2]),
    "duplicate approval": lambda d: d["approvals"].append(copy.deepcopy(d["approvals"][0])),
    "duplicate app id": lambda d: d["apps"].append(copy.deepcopy(d["apps"][0])),
    "bad format": lambda d: d.update(format=2),
    "bad serial": lambda d: d.update(serial=0),
}
for name, f in POLICY.items():
    i2, s2 = signed_mut(f)
    rc, line = one(i2, s2)
    assert rc in (E["POLICY"], E["PARSE"]), (name, line)
    assert not py(i2, s2), name                                              # both sides reject
dup_dest = copy.deepcopy(rich); dup_dest["apps"][1]["artifacts"][0].update(device=DEV, firmware=FW); dup_dest["apps"][1]["artifacts"][0]["install"]["dest_name"] = "ExamplePad_funkey-s.opk"
dup_dest["approvals"][1].update(device=DEV, firmware=FW)
dd = T.canonical(dup_dest)
assert "also used by" in T.check_index(dup_dest)[0] or T.check_index(dup_dest)
assert "duplicate destination" in expect("POLICY", dd, sigdoc(dd))           # duplicate destinations (case-insensitive)

# ---------------- differential: structured mutations of validly signed indexes ----------------
def paths(v, p=()):
    yield p
    if isinstance(v, dict):
        for k in v:
            yield from paths(v[k], p + (k,))
    elif isinstance(v, list):
        for i in range(len(v)):
            yield from paths(v[i], p + (i,))


def get(d, p):
    for k in p:
        d = d[k]
    return d


def mutations(b):
    for p in paths(b):
        if not p:
            continue
        ops = [("del", None), ("null", None), ("zero", 0), ("neg", -1), ("empty", ""), ("x", "x"), ("true", True), ("arr", []), ("obj", {}),
               ("float", 1.5), ("big", 2**40)]
        node = get(b, p)
        if isinstance(node, str):
            ops += [("upper", node.upper()), ("nl", node + "\n"), ("sp", node + " "), ("cut", node[:-1]), ("pre", " " + node), ("uni", node + "é")]
        if isinstance(node, dict):
            ops.append(("extra", {**node, "zz": 1}))
        if isinstance(node, list) and node:
            ops += [("dup", node + [copy.deepcopy(node[0])]), ("rev", node[::-1])]
        if isinstance(node, int) and not isinstance(node, bool):
            ops += [("inc", node + 1), ("dec", node - 1)]
        for name, val in ops:
            d = copy.deepcopy(b)
            parent = get(d, p[:-1])
            if name == "del":
                del parent[p[-1]]
            else:
                parent[p[-1]] = val
            yield f"{'/'.join(map(str, p))}:{name}", d


def mut_bytes(d):
    try:
        return T.canonical(d)
    except (ValueError, TypeError):
        return None


cases, labels = [], []
for b in (base, rich):
    for label, d in mutations(b):
        raw = mut_bytes(d)
        if raw is not None:
            cases.append((raw, sigdoc(raw))); labels.append(label)
n_struct = len(cases)
rng = random.Random(8032)
for _ in range(1200):                                                         # byte-level mutations, re-signed
    ba = bytearray(rng.choice((idx, ridx)))
    for _ in range(rng.choice((1, 1, 2, 3))):
        op = rng.random()
        pos = rng.randrange(len(ba))
        if op < 0.5:
            ba[pos] = rng.randrange(256)
        elif op < 0.75:
            del ba[pos]
        else:
            ba.insert(pos, rng.randrange(256))
    raw = bytes(ba)
    cases.append((raw, sigdoc(raw))); labels.append(f"bytes#{len(cases)}")
for _ in range(300):                                                          # signature-document / stale-signature fuzz
    ba = bytearray(rng.choice((idx, ridx)))
    sg = bytearray(sig)
    if rng.random() < 0.5:
        ba[rng.randrange(len(ba))] ^= 1 << rng.randrange(8)
    else:
        sg[rng.randrange(len(sg))] = rng.randrange(32, 127)
    cases.append((bytes(ba), bytes(sg))); labels.append(f"stale#{len(cases)}")

res = run_batch(cases, keys=(PUB,))
only_native_strict, only_native_loose, crashes, accepted = [], [], [], 0
for (raw, sg), (rc, line), label in zip(cases, res, labels):
    try:
        p_ok = py(raw, sg)
    except Exception as e:                                                    # a crash in trust.py is a bug in trust.py
        crashes.append((label, repr(e)))
        continue
    n_ok = rc == OK
    accepted += n_ok
    if n_ok and not p_ok:
        only_native_loose.append((label, line))
    elif p_ok and not n_ok:
        only_native_strict.append((label, line))
print(f"differential: {len(cases)} cases ({n_struct} structural), {accepted} accepted by both, "
      f"native-looser {len(only_native_loose)}, native-stricter {len(only_native_strict)}, python crashes {len(crashes)}")
for x in crashes[:10]:
    print("  python crash", x)
for x in only_native_loose[:10]:
    print("  NATIVE LOOSER", x)
for x in only_native_strict[:15]:
    print("  native stricter", x)
assert not crashes and not only_native_loose, "native verifier accepted something Python rejects (or Python crashed)"
assert not only_native_strict, "implementations disagree on an index Python accepts"

# ---------------- performance and memory (host, -O2; ARM numbers are in docs/TRUST.md) ----------------
lst1 = [(idx, sig)]
t0 = time.perf_counter(); run_batch(lst1, exe=HOST); t1 = time.perf_counter() - t0
many_ok = [(ridx, sigdoc(ridx))] * 500
t0 = time.perf_counter(); run_batch(many_ok, exe=HOST); t500 = time.perf_counter() - t0
per = (t500 - t1) / 499 * 1000
lst = W / "list.txt"
r = wsl(HOST, "--batch", wsl_path(lst), "--device", DEV, "--firmware", FW, "--pubkey", PUB, "--stats")
rss = int(re.search(r"maxrss_kb=(\d+)", r.stderr).group(1))
print(f"host -O2: ~{per:.2f} ms per verification (incl. file IO and parsing); peak RSS of the whole process {rss} KiB")
assert per < 50 and rss < 8192

shutil.rmtree(W, ignore_errors=True)
print("native trust tests OK")
