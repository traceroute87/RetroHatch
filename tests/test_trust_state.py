"""Run: python tests/test_trust_state.py   (needs WSL Ubuntu with gcc/make; state dirs live on WSL's own /tmp)

Persistent rollback state through the real verifier CLI (rh_verify --state-dir): catalogs are verified completely
before the saved serial/hash may advance; rollbacks, same-serial forks, corrupt/odd state, interrupted and failed
writes, repeated catalogs. Fixtures use throwaway keys generated here and never stored."""
import copy, hashlib, re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE.parent / "tools"))
import trust as T
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import base64

FX = HERE / "trust_fixture"
DEV, FW = "rg-nano", "funkeyos-drum78"
E = {n: i for i, n in enumerate("OK ARG SIZE NOKEY SIGDOC UNKNOWN_KEY BADSIG PARSE POLICY DEVICE ROLLBACK FORK LIMIT NOMEM STATE".split())}


def wsl_path(p):
    p = Path(p).resolve()
    return "/mnt/" + p.drive[0].lower() + "/" + "/".join(p.parts[1:])


def sh(cmd):
    r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", cmd], capture_output=True, text=True)
    return r.stdout.strip()


if subprocess.run(["wsl", "-d", "Ubuntu", "--", "true"], capture_output=True).returncode != 0:
    print("SKIP: WSL Ubuntu not available")
    sys.exit(0)
r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", f"cd {wsl_path(HERE)} && make state-test native-tools 2>&1 | tail -2"], capture_output=True, text=True)
assert "state tests OK" in r.stdout or "rh_verify_host" in r.stdout, r.stdout
assert subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", f"cd {wsl_path(HERE)} && ./trust_state_test"], capture_output=True, text=True).stdout.strip().endswith("state tests OK")

EXE = wsl_path(ROOT / "build/rh_verify_asan")
KEY = Ed25519PrivateKey.generate()
PUB = T.raw_pub(KEY).hex()
W = Path(tempfile.mkdtemp(dir=ROOT / "build"))
ST = f"/tmp/rhstate-py-{W.name}"
sh(f"rm -rf {ST}")


def sigdoc(payload, key=KEY):
    return T.canonical({"v": 1, "alg": "ed25519", "key_id": T.key_id(T.raw_pub(key)), "sig": base64.b64encode(key.sign(payload)).decode()})


def catalog(serial, mutate=None, date="2026-10-26"):
    d = T.build(FX / "catalog", serial, date)
    if mutate:
        mutate(d)
    raw = T.canonical(d)
    return raw, sigdoc(raw)


_n = [0]


def verify(idx_sig, dev=DEV, fw=FW, inject=None, state=ST):
    idx, sig = idx_sig
    _n[0] += 1
    a, b = W / f"{_n[0]}.idx", W / f"{_n[0]}.sig"
    a.write_bytes(idx); b.write_bytes(sig)
    cmd = f"{EXE} --index {wsl_path(a)} --sig {wsl_path(b)} --pubkey {PUB} --device {dev} --firmware {fw} --state-dir {state}"
    if inject:
        cmd += f" --inject {inject}"
    out = sh(cmd)
    m = re.match(r"(OK|FAIL (\d+))", out)
    assert m, out
    return (0 if m.group(1) == "OK" else int(m.group(2))), out


def state_file():
    return sh(f"cat {ST}/catalog.state 2>/dev/null")


def files():
    return sh(f"ls -A {ST} 2>/dev/null | tr '\\n' ' '").split()


def expect(res, code):
    rc, out = res
    assert rc == E[code], (code, out)
    return out


s3, s4, s5, s6, s7 = (catalog(n) for n in (3, 4, 5, 6, 7))
s5_fork = catalog(5, date="2026-11-01")
assert s5[0] != s5_fork[0]
h = lambda c: hashlib.sha256(c[0]).hexdigest()
no_approval = catalog(8, lambda d: d["approvals"].clear())

# first run (no state dir at all), then repeated catalogs
assert files() == []
expect(verify(s3), "OK")
st = state_file()
assert st.startswith("RHCS1 3 " + h(s3)) and files() == ["catalog.state"], (st, files())
expect(verify(s3), "OK")                                             # same catalog again
assert state_file() == st and files() == ["catalog.state"]
# advance, then rollback and fork are refused and leave the state alone
expect(verify(s5), "OK")
st5 = state_file()
assert st5.startswith("RHCS1 5 " + h(s5)), st5
expect(verify(s4), "ROLLBACK"); expect(verify(s3), "ROLLBACK"); expect(verify(s5_fork), "FORK")
assert state_file() == st5
expect(verify(s5), "OK"); assert state_file() == st5
# a catalog that fails ANY check never advances the state
bad_sig = (s6[0].replace(b"ExamplePad", b"ExamplePwn"), s6[1])
expect(verify(bad_sig), "BADSIG")
expect(verify((s6[0], b"")), "SIZE")
expect(verify((s6[0], s6[1][:-5])), "SIGDOC")
expect(verify(no_approval), "POLICY")
expect(verify(s6, dev="other-handheld"), "DEVICE")
expect(verify(s6, fw="funkeyos-future"), "DEVICE")
other = Ed25519PrivateKey.generate()
raw = T.canonical(T.build(FX / "catalog", 9, "2026-10-26"))
expect(verify((raw, sigdoc(raw, other))), "UNKNOWN_KEY")
expect(verify((b'{"a":', sigdoc(b'{"a":'))), "PARSE")
assert state_file() == st5 and files() == ["catalog.state"]
expect(verify(s6), "OK")
st6 = state_file()
assert st6.startswith("RHCS1 6 " + h(s6))

# corrupt existing state is refused, never reset (even for an otherwise valid, newer catalog)
good = st6
for name, cmd in {
    "serial edited": f"sed -i 's/^RHCS1 6/RHCS1 7/' {ST}/catalog.state",
    "truncated": f"head -c 30 {ST}/catalog.state > {ST}/x && mv {ST}/x {ST}/catalog.state",
    "empty": f": > {ST}/catalog.state",
    "garbage": f"echo garbage > {ST}/catalog.state",
    "directory": f"rm {ST}/catalog.state && mkdir {ST}/catalog.state",
}.items():
    sh(cmd)
    before = sh(f"ls -lA {ST} | tail -n +2")
    out = expect(verify(s7), "STATE")
    assert "refusing" in out, (name, out)
    expect(verify(s3), "STATE")                                      # an old catalog is not accepted as a "reset" either
    assert sh(f"ls -lA {ST} | tail -n +2") == before, name           # nothing rewritten
    sh(f"rm -rf {ST}/catalog.state; printf '%s\n' '{good}' > {ST}/catalog.state")
assert state_file() == good
# unreadable state (permission) is also refused
sh(f"chmod 000 {ST}/catalog.state")
rc, out = verify(s7)
if sh("id -u") != "0":
    assert rc == E["STATE"], out
sh(f"chmod 644 {ST}/catalog.state")

# interrupted writes while advancing 6 -> 7: whichever step the power fails at, the state stays valid and monotonic
for step in ("tmp_open", "tmp_written", "bak_made", "renamed", "synced"):
    sh(f"rm -rf {ST}")
    expect(verify(s3), "OK")
    rc, out = verify(s6, inject=f"{step}:crash")
    assert rc == E["STATE"], (step, out)                              # power loss: the process never reports success
    left = state_file()
    on_disk = sh(f"ls -A {ST} | tr '\\n' ' '")
    # state is the old record, the new record, or only the parked old record (never empty, never corrupt)
    rc2, out2 = verify(s3)
    if step in ("renamed", "synced"):
        assert left.startswith("RHCS1 6 "), (step, left)
        assert rc2 == E["ROLLBACK"], (step, out2)
    else:
        assert left.startswith("RHCS1 3 ") or (left == "" and "catalog.state.bak" in on_disk), (step, left, on_disk)
        assert rc2 == E["OK"], (step, out2)
    expect(verify(s6), "OK")                                          # the retry completes the advance
    assert state_file().startswith("RHCS1 6 " + h(s6)) and "catalog.state.tmp" not in files(), (step, files())
    assert "catalog.state.bak" not in files(), (step, files())

# failed writes (I/O error, failed rename): the catalog is NOT trusted, the old state survives, a retry works
for step in ("tmp_open", "tmp_written", "bak_made"):
    sh(f"rm -rf {ST}")
    expect(verify(s3), "OK")
    out = expect(verify(s5, inject=f"{step}:err"), "STATE")
    assert "not trusting" in out, out
    assert state_file().startswith("RHCS1 3 " + h(s3)) and files() == ["catalog.state"], (step, files())
    expect(verify(s5), "OK")
sh(f"rm -rf {ST}")
expect(verify(s3), "OK")
sh(f"mkdir {ST}/catalog.state.bak && touch {ST}/catalog.state.bak/x")      # real failing rename
expect(verify(s5), "STATE")
assert state_file().startswith("RHCS1 3 ")
sh(f"rm -rf {ST}/catalog.state.bak; mkdir {ST}/catalog.state.tmp")        # real failing open
expect(verify(s5), "STATE")
assert state_file().startswith("RHCS1 3 ")
sh(f"rmdir {ST}/catalog.state.tmp")
expect(verify(s5), "OK")

# first-run write failure: no trust is granted
sh(f"rm -rf {ST}")
expect(verify(s3, inject="tmp_written:err"), "STATE")
assert files() == [], files()
expect(verify(s3), "OK")

# documented limitation: removing all state is indistinguishable from a first run
sh(f"rm -rf {ST}")
expect(verify(s5), "OK"); expect(verify(s3), "ROLLBACK")
sh(f"rm -f {ST}/catalog.state")
expect(verify(s3), "OK")                                                  # an old signed catalog is accepted again

# state lives in its own directory: unrelated engine files are untouched
sh(f"rm -rf {ST}; mkdir -p {ST}; echo keep > {ST}/installed.tsv; echo j > {ST}/journal")
expect(verify(s3), "OK")
assert sh(f"cat {ST}/installed.tsv {ST}/journal") == "keep\nj" and sorted(files()) == ["catalog.state", "installed.tsv", "journal"]

sh(f"rm -rf {ST}")
import shutil
shutil.rmtree(W, ignore_errors=True)
print("trust state tests OK")
