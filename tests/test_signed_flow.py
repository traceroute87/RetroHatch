"""Run: python tests/test_signed_flow.py    (needs WSL Ubuntu with gcc, SDL host libs, mbedTLS in ~/mbedtls_native, openssl)

DEV UI + ops + signed catalog + HTTPS downloads against a local TLS server (throwaway CA, throwaway signing key)."""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "build" / "sf-test"
r = subprocess.run([sys.executable, str(ROOT / "tools" / "make_dev_catalog.py"), "--out", str(FX)], capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr


def wsl_path(p):
    p = Path(p).resolve()
    return "/mnt/" + p.drive[0].lower() + "/" + "/".join(p.parts[1:])


r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", f"cd {wsl_path(ROOT)} && python3 tests/signed_flow_wsl.py {wsl_path(FX)}"], capture_output=True, text=True)
print(r.stdout.strip()); print(r.stderr.strip()[-1500:])
assert r.returncode == 0 and "0 failed" in r.stdout, "signed flow test failed"
print("signed flow tests OK")
