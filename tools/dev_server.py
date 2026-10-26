#!/usr/bin/env python3
"""LAN HTTPS test server for the DEV hardware test (Python 3 stdlib + the openssl command). Serves build/dev-catalog/ with a
throwaway CA, so the Nano verifies a REAL certificate chain and host name (the name is the PC's LAN address).

  python3 tools/dev_server.py --host 192.168.1.19 [--port 8443] [--dir build/dev-catalog] [--out build/dev-server]

Writes OUT/ca.pem, OUT/mirror.txt, OUT/catalog-url.txt (copy these three to <DEV state dir>/extra-ca.crt, mirror.txt,
catalog-url.txt on the Nano). Behaviour is switched by writing one word into <dir>/variant.txt while it runs:
  ok (serial 2 catalog, good files), stale (serial 1), tampered, fork, junk, wrong (packages with other bytes), trunc, reset, 404.
Stops with Ctrl+C. Logs every request."""
import argparse, http.server, shutil, socketserver, ssl, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--host", required=True)
ap.add_argument("--port", type=int, default=8443)
ap.add_argument("--dir", type=Path, default=Path("build/dev-catalog"))
ap.add_argument("--out", type=Path, default=Path("build/dev-server"))
a = ap.parse_args()
FX, OUT = a.dir.resolve(), a.out.resolve()
OUT.mkdir(parents=True, exist_ok=True)


def sh(*c):
    r = subprocess.run(c, capture_output=True, text=True, cwd=OUT)
    assert r.returncode == 0, (c, r.stderr)


sh("openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", "ca.key", "-out", "ca.pem",
   "-subj", "/CN=RetroHatch DEV test CA", "-days", "14", "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign")
sh("openssl", "req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", "leaf.key", "-out", "leaf.csr", "-subj", f"/CN={a.host}")
# mbedTLS 2.16 matches the host name against dNSName entries only, so the address goes in as a DNS name too
(OUT / "leaf.ext").write_text(f"subjectAltName=DNS:{a.host},IP:{a.host}\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n")
sh("openssl", "x509", "-req", "-in", "leaf.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial", "-out", "leaf.pem", "-extfile", "leaf.ext", "-days", "14")
base = f"https://{a.host}:{a.port}"
(OUT / "mirror.txt").write_bytes(f"https://github.com/ {base}/gh/\n".encode())
(OUT / "catalog-url.txt").write_bytes(f"{base}/catalog/\n".encode())
(FX / "variant.txt").write_text("ok")

CATALOG = {"ok": ("index-2.json", "index-2.json.sig"), "tampered": ("index-2.tampered.json", "index-2.json.sig"),
           "stale": ("index-1.json", "index-1.json.sig"), "fork": ("index-2b.json", "index-2b.json.sig")}


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, f, *x): print(f"[{(FX / 'variant.txt').read_text().strip()}] {self.client_address[0]} {self.path}", flush=True)
    def reply(self, code, body, claim=None):
        self.wfile.write(f"HTTP/1.1 {code}\r\nContent-Length: {len(body) if claim is None else claim}\r\nConnection: close\r\n\r\n".encode() + body)
        self.wfile.flush(); self.close_connection = True
    def do_GET(self):
        v, p = (FX / "variant.txt").read_text().strip(), self.path
        self.log_message("")
        if v == "reset": self.close_connection = True; return
        if v == "404": return self.reply("404 Not Found", b"")
        if p.startswith("/catalog/"):
            if v == "junk": return self.reply("200 OK", b"not a catalog")
            idx, sig = CATALOG.get(v, CATALOG["ok"])
            n = p[len("/catalog/"):]
            f = FX / (idx if n == "index.json" else sig if n == "index.json.sig" else "nope")
            return self.reply("200 OK", f.read_bytes()) if f.is_file() else self.reply("404 Not Found", b"")
        if p.startswith("/gh/"):
            f = FX / ("wrong" if v == "wrong" else "gh") / p[len("/gh/"):]
            if not f.is_file(): return self.reply("404 Not Found", b"")
            b = f.read_bytes()
            return self.reply("200 OK", b[: len(b) // 2], claim=len(b)) if v == "trunc" else self.reply("200 OK", b)
        self.reply("404 Not Found", b"")


ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(OUT / "leaf.pem", OUT / "leaf.key")
srv = socketserver.ThreadingTCPServer(("0.0.0.0", a.port), H)
srv.daemon_threads = True
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
print(f"serving {FX} at {base}/  (CA: {OUT / 'ca.pem'})  variant file: {FX / 'variant.txt'}", flush=True)
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
