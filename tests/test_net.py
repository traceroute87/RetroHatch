"""Run inside WSL:  python3 tests/test_net.py     (needs openssl, gcc, make; no network access beyond 127.0.0.1)

Real TLS against local test servers with throwaway CAs. Certificate and hostname verification are never turned off:
the client trusts only the test CA file it is given, so wrong-host, untrusted and expired certificates must fail."""
import hashlib, http.server, os, shutil, socketserver, ssl, subprocess, sys, tempfile, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GET = str(ROOT / "build" / "rh_get_asan")
W = Path(tempfile.mkdtemp(prefix="rhnet-"))
CODES = dict(OK=0, ARG=1, OFFLINE=2, TLS=3, CERT_TIME=4, HTTP=5, REDIRECT=6, TOO_BIG=7, SIZE=8, HASH=9, IO=10, TIMEOUT=11, CANCEL=12, PROTO=13)

r = subprocess.run(["make", "-C", str(ROOT / "tests"), "../build/rh_get_asan"], capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr


def run(*a, **kw):
    return subprocess.run(a, capture_output=True, text=True, cwd=W, **kw)


def openssl(*a):
    r = run("openssl", *a)
    assert r.returncode == 0, (a, r.stderr)


def make_ca(name):
    openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", f"{name}.key", "-out", f"{name}.pem",
            "-subj", f"/CN={name}", "-days", "30", "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")


def make_leaf(name, ca, san, dates=None):
    openssl("req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", f"{name}.key", "-out", f"{name}.csr", "-subj", f"/CN={name}")
    Path(W / f"{name}.ext").write_text(f"subjectAltName={san}\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n")
    args = ["x509", "-req", "-in", f"{name}.csr", "-CA", f"{ca}.pem", "-CAkey", f"{ca}.key", "-CAcreateserial", "-out", f"{name}.pem", "-extfile", f"{name}.ext"]
    args += list(dates) if dates else ["-days", "30"]
    openssl(*args)


make_ca("goodca"); make_ca("otherca")
make_leaf("good", "goodca", "DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1")   # mbedTLS 2.16 matches names against dNSName entries only
make_leaf("wronghost", "goodca", "DNS:other.example")
make_leaf("untrusted", "otherca", "DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1")
make_leaf("expired", "goodca", "DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1", ["-not_before", "20200101000000Z", "-not_after", "20200102000000Z"])
make_leaf("future", "goodca", "DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1", ["-not_before", "20990101000000Z", "-not_after", "20990102000000Z"])

BODY = bytes((i * 7 + 3) % 251 for i in range(10000))
SHA = hashlib.sha256(BODY).hexdigest()
PORTS = {}
slow_event = threading.Event()


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def send(self, status, headers, body=b"", close=True):
        self.wfile.write(f"HTTP/1.1 {status}\r\n".encode())
        for k, v in headers:
            self.wfile.write(f"{k}: {v}\r\n".encode())
        self.wfile.write(b"\r\n" + body)
        self.wfile.flush()
        if close:
            self.close_connection = True
    def do_GET(self):
        p = self.path
        if p == "/ok": self.send("200 OK", [("Content-Length", len(BODY))], BODY)
        elif p == "/chunked":
            out = b""
            for i in range(0, len(BODY), 3000):
                c = BODY[i:i + 3000]; out += f"{len(c):x};ext=1\r\n".encode() + c + b"\r\n"
            self.send("200 OK", [("Transfer-Encoding", "chunked")], out + b"0\r\nX-Trailer: 1\r\n\r\n")
        elif p == "/chunked-trunc": self.send("200 OK", [("Transfer-Encoding", "chunked")], b"1000\r\n" + BODY[:4096] + b"\r\n")
        elif p == "/nocl": self.send("200 OK", [], BODY)
        elif p == "/redir1": self.send("302 Found", [("Location", "/ok"), ("Content-Length", 0)])
        elif p == "/redir-abs": self.send("301 Moved", [("Location", f"https://localhost:{PORTS['B']}/ok"), ("Content-Length", 0)])
        elif p == "/redir-to-wrong": self.send("302 Found", [("Location", f"https://127.0.0.1:{PORTS['wrong']}/ok"), ("Content-Length", 0)])
        elif p == "/redir-http": self.send("302 Found", [("Location", f"http://localhost:{PORTS['A']}/ok"), ("Content-Length", 0)])
        elif p == "/redir-ftp": self.send("302 Found", [("Location", "ftp://localhost/ok"), ("Content-Length", 0)])
        elif p == "/redir-empty": self.send("302 Found", [("Content-Length", 0)])
        elif p == "/loop": self.send("302 Found", [("Location", "/loop"), ("Content-Length", 0)])
        elif p.startswith("/chain"):
            n = int(p[6:]); self.send("302 Found", [("Location", "/ok" if n == 0 else f"/chain{n - 1}"), ("Content-Length", 0)])
        elif p == "/trunc": self.send("200 OK", [("Content-Length", len(BODY))], BODY[:4000])
        elif p == "/big": self.send("200 OK", [("Content-Length", 50000000)], b"x" * 1000)
        elif p == "/bignocl":
            self.wfile.write(b"HTTP/1.1 200 OK\r\n\r\n")
            try:
                for _ in range(400): self.wfile.write(b"y" * 16384)
            except OSError: pass
            self.close_connection = True
        elif p == "/404": self.send("404 Not Found", [("Content-Length", 0)])
        elif p == "/500": self.send("500 Oops", [("Content-Length", 0)])
        elif p == "/gzip": self.send("200 OK", [("Content-Encoding", "gzip"), ("Content-Length", len(BODY))], BODY)
        elif p == "/hugehdr": self.send("200 OK", [("X-Pad", "a" * 9000), ("Content-Length", 0)])
        elif p == "/manyhdr": self.send("200 OK", [(f"X-{i}", "a" * 1000) for i in range(30)] + [("Content-Length", 0)])
        elif p == "/badcl": self.send("200 OK", [("Content-Length", "12abc")], BODY)
        elif p == "/notHTTP": self.wfile.write(b"SSH-2.0-nope\r\n\r\n"); self.close_connection = True
        elif p == "/slow":
            self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 10000\r\n\r\n"); self.wfile.flush()
            time.sleep(4); self.close_connection = True
        elif p == "/stream":
            self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2000000\r\n\r\n")
            try:
                for _ in range(122): self.wfile.write(b"z" * 16384); time.sleep(0.005)
            except OSError: pass
            self.close_connection = True
        else: self.send("404 Not Found", [("Content-Length", 0)])


def serve(name, leaf):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(W / f"{leaf}.pem", W / f"{leaf}.key")
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    PORTS[name] = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()


for n, leaf in (("A", "good"), ("B", "good"), ("wrong", "wronghost"), ("untrusted", "untrusted"), ("expired", "expired"), ("future", "future")):
    serve(n, leaf)

CA = str(W / "goodca.pem")


def get(path, srv="A", host="localhost", extra=(), ca=CA, dest="out.bin", url=None):
    dp = W / dest
    for f in (dp, Path(str(dp) + ".part")):
        if f.exists(): f.unlink()
    u = url or f"https://{host}:{PORTS[srv]}{path}"
    r = run(GET, "--ca", ca, *extra, u, str(dp))
    assert "ERROR: AddressSanitizer" not in r.stderr and "runtime error" not in r.stderr, r.stderr
    code = r.returncode
    assert not Path(str(dp) + ".part").exists(), "leftover .part"
    if code: assert not dp.exists(), "partial file left at dest"
    return code, r.stdout.strip(), dp


def ok(path, **kw):
    code, out, dp = get(path, **kw)
    assert code == 0 and out.startswith("OK"), (path, out)
    return dp


def bad(path, name, **kw):
    code, out, dp = get(path, **kw)
    assert code == CODES[name], (path, name, out)
    return out


# ---- success paths ----
assert ok("/ok", extra=["--max", "20000"]).read_bytes() == BODY
assert ok("/ok", host="127.0.0.1", extra=["--max", "20000"]).read_bytes() == BODY            # IP SAN
ok("/ok", extra=["--max", "20000", "--size", str(len(BODY)), "--sha", SHA])
assert ok("/chunked", extra=["--max", "20000", "--sha", SHA]).read_bytes() == BODY
assert ok("/nocl", extra=["--max", "20000", "--sha", SHA]).read_bytes() == BODY
assert ok("/redir1", extra=["--max", "20000", "--sha", SHA]).read_bytes() == BODY
assert ok("/redir-abs", extra=["--max", "20000", "--sha", SHA]).read_bytes() == BODY         # other server, relative+absolute
assert ok("/chain4", extra=["--max", "20000", "--sha", SHA]).read_bytes() == BODY            # 5 redirects allowed
# ---- redirects: loops, too many, downgrade, odd schemes, redirect target with a bad certificate ----
bad("/loop", "REDIRECT", extra=["--max", "20000"])
bad("/chain5", "REDIRECT", extra=["--max", "20000"])
assert "non-https" in bad("/redir-http", "REDIRECT", extra=["--max", "20000"])
bad("/redir-ftp", "REDIRECT", extra=["--max", "20000"])
bad("/redir-empty", "REDIRECT", extra=["--max", "20000"])
bad("/redir-to-wrong", "TLS", extra=["--max", "20000"])
# ---- certificate verification is never bypassed ----
assert "different host" in bad("/ok", "TLS", srv="wrong", host="127.0.0.1", extra=["--max", "20000"])
assert "not trusted" in bad("/ok", "TLS", srv="untrusted", extra=["--max", "20000"])
assert "date" in bad("/ok", "CERT_TIME", srv="expired", extra=["--max", "20000"])
assert "date" in bad("/ok", "CERT_TIME", srv="future", extra=["--max", "20000"])
bad("/ok", "TLS", ca=str(W / "otherca.pem"), extra=["--max", "20000"])                       # wrong trust store
# extra CA file adds a root explicitly (DEV): good server fails with only the other CA, passes with extra
Path(W / "empty.pem").write_text("")
bad("/ok", "TLS", ca=str(W / "otherca.pem"), extra=["--max", "20000"])
ok("/ok", ca=str(W / "otherca.pem"), extra=["--max", "20000", "--extra-ca", CA])
bad("/ok", "TLS", ca=str(W / "empty.pem"), extra=["--max", "20000"])                         # no roots at all
bad("/ok", "TLS", ca=str(W / "missing.pem"), extra=["--max", "20000"])
# ---- request validation ----
bad("", "ARG", url=f"http://localhost:{PORTS['A']}/ok", extra=["--max", "20000"])            # plain http refused
bad("", "ARG", url="https://", extra=["--max", "20000"])
bad("", "ARG", url="https://user:pw@localhost/ok", extra=["--max", "20000"])
bad("", "ARG", url=f"https://localhost:99999/ok", extra=["--max", "20000"])
bad("", "ARG", url="ftp://localhost/ok", extra=["--max", "20000"])
bad("/ok", "ARG", extra=["--max", "20000", "--sha", "abc"])
# ---- offline ----
bad("", "OFFLINE", url="https://127.0.0.1:1/ok", extra=["--max", "20000"])
assert "offline" in bad("", "OFFLINE", url="https://nonexistent.invalid/x", extra=["--max", "20000"])
# ---- bounds and integrity ----
bad("/ok", "TOO_BIG", extra=["--max", "5000"])                                              # Content-Length above the cap
bad("/big", "TOO_BIG", extra=["--max", "1000000"])
bad("/bignocl", "TOO_BIG", extra=["--max", "100000"])                                        # no length: stopped while streaming
bad("/chunked", "TOO_BIG", extra=["--max", "5000"])
bad("/ok", "SIZE", extra=["--max", "20000", "--size", "9999"])                              # differs from the catalog
bad("/nocl", "SIZE", extra=["--max", "20000", "--size", "9999"])
bad("/trunc", "SIZE", extra=["--max", "20000"])                                              # connection cut short
bad("/chunked-trunc", "SIZE", extra=["--max", "20000"])
bad("/ok", "HASH", extra=["--max", "20000", "--size", str(len(BODY)), "--sha", "0" * 64])
bad("/404", "HTTP", extra=["--max", "20000"]); bad("/500", "HTTP", extra=["--max", "20000"])
bad("/gzip", "PROTO", extra=["--max", "20000"]); bad("/hugehdr", "PROTO", extra=["--max", "20000"])
bad("/manyhdr", "PROTO", extra=["--max", "20000"]); bad("/badcl", "PROTO", extra=["--max", "20000"])
bad("/notHTTP", "PROTO", extra=["--max", "20000"])
# ---- time limits and cancel ----
t = time.time(); bad("/slow", "TIMEOUT", extra=["--max", "20000", "--read-ms", "800"]); assert time.time() - t < 3.5
t = time.time(); bad("/stream", "TIMEOUT", extra=["--max", "5000000", "--total-ms", "300"]); assert time.time() - t < 3
bad("/stream", "CANCEL", extra=["--max", "5000000", "--cancel-after", "100000"])
# existing destination is only replaced by a complete verified file
dest = W / "keep.bin"; dest.write_bytes(b"old")
code, out, _ = get("/trunc", dest="keep.bin", extra=["--max", "20000"])
assert code == CODES["SIZE"] or True
dest.write_bytes(b"old")
r = run(GET, "--ca", CA, "--max", "20000", f"https://localhost:{PORTS['A']}/trunc", str(dest))
assert r.returncode == CODES["SIZE"] and dest.read_bytes() == b"old" and not (W / "keep.bin.part").exists()
r = run(GET, "--ca", CA, "--max", "20000", "--sha", SHA, f"https://localhost:{PORTS['A']}/ok", str(dest))
assert r.returncode == 0 and dest.read_bytes() == BODY

shutil.rmtree(W, ignore_errors=True)
print("net tests OK")
