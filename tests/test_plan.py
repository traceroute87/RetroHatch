"""Run in WSL/Linux: python3 tests/test_plan.py  (needs gcc + jsonschema; no framework)."""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import plan, validate

(ROOT / "build").mkdir(exist_ok=True)
subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Wno-unused-result", "-o", str(plan.CLI),
                str(ROOT / "platforms/nano/cli/rh_host_cli.c"), str(ROOT / "platforms/nano/rh_install.c"),
                str(ROOT / "core/sha256.c")], check=True)

DEV, FW = "rg-nano", "funkeyos-drum78"
DEST = "rhprobe_funkey-s.opk"
BLOB = b"R" * 4096
SHA = hashlib.sha256(BLOB).hexdigest()
tmp = Path(tempfile.mkdtemp())
(tmp / "mounts").write_text("/dev/root / ext4 ro 0 0\n")
(tmp / "sys").mkdir()
plan.ENGINE_EXTRA = ["--mounts", str(tmp / "mounts"), "--sysblock", str(tmp / "sys")]
blob = tmp / "probe.opk"
blob.write_bytes(BLOB)


def probe(**art):
    a = {"device": DEV, "firmware": FW, "format": "opk", "status": "available", "version": "1",
         "url": "https://x.test/p.opk", "sha256": SHA, "size": 4096, "install": {"dest_name": DEST},
         "compatibility": {"level": "verified", "evidence": [{"sha256": SHA, "date": "2026-01-01", "tester": "t"}]}}
    a.update(art)
    return {"schema": 1, "id": "probe", "name": "Probe", "description": "d", "developer": "d",
            "source": "https://x.test", "license": "MIT", "category": "other", "artifacts": [a]}


def world(app=None, name="probe"):
    """fresh catalog copy (+ optional app), apps dir, state dir"""
    w = Path(tempfile.mkdtemp(dir=tmp))
    shutil.copytree(validate.ROOT, w / "catalog")
    if app:
        (w / "catalog/apps" / f"{name}.json").write_text(json.dumps(app))
    (w / "apps").mkdir()
    return w / "catalog", w / "apps", w / "state"


def refused(fn, *a, **k):
    try:
        fn(*a, **k)
    except plan.Refused as e:
        return str(e)
    return None


def inst(c, apps, st, app="probe", fw=FW, dev=DEV, file=blob):
    return plan.install(c, app, dev, fw, apps, st, file)


# real catalog: TaraFi must stay non-installable
c, apps, st = world()
assert "unavailable" in refused(inst, c, apps, st, app="tarafi")
assert not list(apps.iterdir())

# happy path through the real engine
c, apps, st = world(probe())
rc, out = inst(c, apps, st)
assert rc == 0 and "result=0" in out, out
assert hashlib.sha256((apps / DEST).read_bytes()).hexdigest() == SHA
assert f"probe\t1\t{SHA}" in (st / "installed.tsv").read_text()
rc, out = plan.uninstall(c, "probe", DEV, FW, apps, st)
assert rc == 0 and "result=0" in out, out
assert not (apps / DEST).exists() and "probe\t" not in (st / "installed.tsv").read_text()

# artifact rejections (nothing may be written)
def rejected(app, why, **kw):
    c, apps, st = world(app)
    r = refused(inst, c, apps, st, **kw)
    assert r and why in r, (why, r)
    assert not list(apps.iterdir()), why

lvl = lambda l: {"compatibility": {"level": l}}
rejected(probe(**lvl("untested")), "catalog invalid")      # validator already bars it
a = probe(**lvl("community")); rejected(a, "need 'verified'")
a = probe(**lvl("experimental")); rejected(a, "need 'verified'")
a = probe(status="unavailable", unavailable_reason="not released", compatibility={"level": "untested"}); rejected(a, "unavailable")
c, apps, st = world(probe())
assert "not on device" in refused(inst, c, apps, st, fw="other-fw")
assert "unknown device" in refused(inst, c, apps, st, dev="rg35xx")
assert "unknown app" in refused(inst, c, apps, st, app="nope")
a = probe(); del a["artifacts"][0]["install"]; rejected(a, "dest_name")
a = probe(); a["license"] = "unknown"; rejected(a, "catalog invalid")
a = probe(url="http://x.test/p.opk"); rejected(a, "catalog invalid")
a = probe(); a["artifacts"][0]["compatibility"]["evidence"][0]["sha256"] = "0" * 64; rejected(a, "catalog invalid")

# local file checks: wrong size (plan) and wrong bytes (engine)
c, apps, st = world(probe())
short = tmp / "short.opk"; short.write_bytes(b"R" * 10)
assert "size differs" in refused(inst, c, apps, st, file=short)
bad = tmp / "bad.opk"; bad.write_bytes(b"X" * 4096)
rc, out = inst(c, apps, st, file=bad)
assert rc != 0 and "sha256 mismatch" in out and not list(apps.iterdir())

# protected names: even a "verified" TaraFi entry cannot be installed over the engine denylist
t = json.loads((validate.ROOT / "apps/tarafi.json").read_text())
t.update(license="MIT")
t["artifacts"][0] = probe(install={"dest_name": "TaraFi.opk"})["artifacts"][0]
t["artifacts"][0]["install"] = {"dest_name": "TaraFi.opk"}
c, apps, st = world(t, name="tarafi")
rc, out = inst(c, apps, st, app="tarafi")
assert rc != 0 and "destination not allowed" in out and not list(apps.iterdir())

# unmanaged file is never overwritten
c, apps, st = world(probe())
(apps / DEST).write_text("someone else's")
rc, out = inst(c, apps, st)
assert rc != 0 and "not installed by RetroHatch" in out and (apps / DEST).read_text() == "someone else's"

# real catalog is untouched / still valid
assert validate.check() == []
shutil.rmtree(tmp)
print("plan tests OK")
