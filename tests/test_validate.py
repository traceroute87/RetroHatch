"""Run: python tests/test_validate.py  (no framework)."""
import json, shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import validate

H = "a" * 64


def run(mutate):
    with tempfile.TemporaryDirectory() as t:
        c = Path(t) / "catalog"
        shutil.copytree(validate.ROOT, c)
        p = c / "apps" / "tarafi.json"
        d = json.loads(p.read_text())
        mutate(d)
        p.write_text(json.dumps(d))
        return validate.check(c)


def avail(d, **kw):
    a = d["artifacts"][0]
    a.update(status="available", version="1.0", url="https://x.test/a.opk", sha256=H, size=1, **kw)
    a.pop("unavailable_reason")


def verified(d):
    d.update(license="MIT")
    avail(d)
    d["artifacts"][0]["compatibility"] = {"level": "verified"}


def verified_ok(d):
    verified(d)
    d["artifacts"][0]["compatibility"]["evidence"] = [{"sha256": H, "date": "2026-01-01", "tester": "t"}]


assert validate.check() == [], validate.check()
assert any("unknown license" in e for e in run(avail))
assert any("untested" in e for e in run(lambda d: (d.update(license="MIT"), avail(d))))
assert any("evidence" in e for e in run(verified))
assert run(verified_ok) == []
assert run(lambda d: d["artifacts"][0].update(url="http://x"))
assert run(lambda d: d["artifacts"][0].update(device="nope"))
assert run(lambda d: d["artifacts"][0].update(extra=1))
print("tests OK")
