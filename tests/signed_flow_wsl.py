"""Runs inside WSL (called by test_signed_flow.py): throwaway CA + local TLS server for the signed-catalog flow, then
ui_signed_test. Certificate and hostname verification stay on: the client trusts only this run's test CA.
   python3 tests/signed_flow_wsl.py <fixture_dir>"""
import http.server, os, shutil, socketserver, ssl, subprocess, sys, tempfile, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FX = Path(sys.argv[1]).resolve()
W = Path(tempfile.mkdtemp(prefix="rhsf-"))


def run(*a, check=True, **kw):
    r = subprocess.run(a, capture_output=True, text=True, cwd=W, **kw)
    if check:
        assert r.returncode == 0, (a, r.stdout, r.stderr)
    return r


run("openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", "ca.key", "-out", "ca.pem",
    "-subj", "/CN=rh-test-ca", "-days", "5", "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign")
run("openssl", "req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", "leaf.key", "-out", "leaf.csr", "-subj", "/CN=localhost")
(W / "leaf.ext").write_text("subjectAltName=DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n")
run("openssl", "x509", "-req", "-in", "leaf.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial", "-out", "leaf.pem", "-extfile", "leaf.ext", "-days", "5")

CATALOG = {  # variant -> (index file, sig file)
    "ok": ("index-2.json", "index-2.json.sig"), "tampered": ("index-2.tampered.json", "index-2.json.sig"),
    "stale": ("index-1.json", "index-1.json.sig"), "fork": ("index-2b.json", "index-2b.json.sig"),
}


def variant():
    return (FX / "variant.txt").read_text().strip()


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def reply(self, code, body, claim=None):
        self.wfile.write(f"HTTP/1.1 {code}\r\nContent-Length: {len(body) if claim is None else claim}\r\nConnection: close\r\n\r\n".encode() + body)
        self.wfile.flush(); self.close_connection = True
    def do_GET(self):
        v, p = variant(), self.path
        if v == "reset": self.close_connection = True; return
        if v == "404": return self.reply("404 Not Found", b"")
        if p.startswith("/catalog/"):
            name = p[len("/catalog/"):]
            if v == "junk": return self.reply("200 OK", b"this is not a catalog")
            idx, sig = CATALOG.get(v, CATALOG["ok"])
            f = FX / (idx if name == "index.json" else sig if name == "index.json.sig" else "nope")
            return self.reply("200 OK", f.read_bytes()) if f.is_file() else self.reply("404 Not Found", b"")
        if p.startswith("/gh/"):
            f = FX / ("wrong" if v == "wrong" else "gh") / p[len("/gh/"):]
            if not f.is_file(): return self.reply("404 Not Found", b"")
            b = f.read_bytes()
            return self.reply("200 OK", b[: len(b) // 2], claim=len(b)) if v == "trunc" else self.reply("200 OK", b)
        self.reply("404 Not Found", b"")


ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(W / "leaf.pem", W / "leaf.key")
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
srv.daemon_threads = True
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

r = subprocess.run(["make", "-C", str(ROOT / "tests"), "mc_host.o", "mce_host.o", "ui_signed_test"], capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
(FX / "variant.txt").write_text("ok")
r = subprocess.run([str(ROOT / "tests" / "ui_signed_test"), str(ROOT), str(FX), str(port), str(W / "ca.pem"), (FX / "pubkey.hex").read_text().strip()] + sys.argv[2:3],
                   capture_output=True, text=True, timeout=300)
print(r.stdout.strip())
print(r.stderr.strip()[-2000:])
shutil.rmtree(W, ignore_errors=True)
sys.exit(r.returncode)
