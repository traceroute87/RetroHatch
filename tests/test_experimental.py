"""Run inside WSL:  python3 tests/test_experimental.py      (needs gcc, SDL host libs, OpenSSL headers in ~/ossl_native/root (see tests/Makefile), openssl, zlib)

Experimental test install (DEV only): builds fixture candidates (direct OPKs, ZIPs with good and hostile members, wrong hashes, HTML instead of a
package, 404, a GitLab file page, a cancelled download ...), serves them from a local TLS server with a throwaway CA (certificate and host name
checks stay on), then runs tests/ui_exp_test, which also classifies the REAL 130-candidate snapshot."""
import hashlib, http.server, json, os, shutil, socketserver, ssl, struct, subprocess, sys, tempfile, threading, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W = Path(tempfile.mkdtemp(prefix="rhexp-"))
FX = W / "fx"
(FX / "gh").mkdir(parents=True)


def run(*a, **kw):
    r = subprocess.run(a, capture_output=True, text=True, cwd=W, **kw)
    assert r.returncode == 0, (a, r.stdout, r.stderr)
    return r


def deflate(b):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(b) + c.flush()


def mkzip(entries):   # entries: (name, data, attrs, crc_override)
    body = cd = b""
    for name, data, attrs, crc in entries:
        nm = name.encode(); c = deflate(data); crc = zlib.crc32(data) if crc is None else crc; off = len(body)
        body += struct.pack("<IHHHHHIIIHH", 0x04034b50, 20, 0, 8, 0, 0x21, crc, len(c), len(data), len(nm), 0) + nm + c
        cd += struct.pack("<IBBHHHHHIIIHHHHHII", 0x02014b50, 20, 3, 20, 0, 8, 0, 0x21, crc, len(c), len(data), len(nm), 0, 0, 0, 0, attrs, off) + nm
    return body + cd + struct.pack("<IHHHHIIH", 0x06054b50, 0, 0, len(entries), len(entries), len(cd), len(body), 0)


def opk(tag, n=4000):
    return b"hsqs" + hashlib.sha256(tag.encode()).digest() * (n // 32)


REG = 0o100644 << 16
files = {}      # path under gh/ -> bytes
cands = []


def cand(cid, name, url, fmt="opk", container="", size=None, sha=None, data=None, version="v1.0"):
    pk = {"name": name, "format": fmt, "signature": "squashfs" if fmt == "opk" else "", "container": container, "more_packages": 0}
    if url:
        pk["url"] = url
        pk["size"] = size if size is not None else len(data or b"")
    if sha:
        pk["sha256"] = sha
    cands.append({"id": cid, "name": cid.capitalize(), "description": "test fixture", "topics": [], "version": version, "repo": "o/" + cid,
                  "source": "https://github.com/o/" + cid, "license": "MIT", "last_activity": "2026-11-06", "package": pk,
                  "claim": {"kind": "rg-nano", "text": "fixture", "where": "description"}, "hardware_test": "none", "approval": "unapproved"})


def gh(cid, fname, data):
    files["o/%s/releases/download/v1/%s" % (cid, fname)] = data
    return "https://github.com/o/%s/releases/download/v1/%s" % (cid, fname)


d = opk("direct"); cand("direct", "direct_funkey-s.opk", gh("direct", "direct_funkey-s.opk", d), data=d)
h = opk("hashed"); cand("hashed", "hashed_funkey-s.opk", gh("hashed", "hashed_funkey-s.opk", h), data=h, sha=hashlib.sha256(h).hexdigest())
b = opk("badhash"); cand("badhash", "badhash_funkey-s.opk", gh("badhash", "badhash_funkey-s.opk", b + b"x"), data=b, sha=hashlib.sha256(b).hexdigest())
z = opk("zipped"); (FX / "zipped.expect").write_bytes(z)
cand("zipped", "zipped_funkey-s.opk", gh("zipped", "zipped.zip", mkzip([("README", b"hello", REG, None), ("opk/zipped_funkey-s.opk", z, REG, None), ("../x", b"y", REG, None)])), container="zip", data=z)
cand("zipmissing", "nothere_funkey-s.opk", gh("zipmissing", "zipmissing.zip", mkzip([("other.opk", opk("o"), REG, None)])), container="zip", data=b"x")
cand("zipsym", "zipsym_funkey-s.opk", gh("zipsym", "zipsym.zip", mkzip([("zipsym_funkey-s.opk", b"/etc/passwd", 0o120777 << 16, None)])), container="zip", data=b"x")
cand("zipbad", "zipbad_funkey-s.opk", gh("zipbad", "zipbad.zip", mkzip([("zipbad_funkey-s.opk", opk("zb"), REG, 1234)])), container="zip", data=b"x")
cand("notzip", "notzip_funkey-s.opk", gh("notzip", "notzip.zip", b"this is not a zip file at all" * 10), container="zip", data=b"x")
cand("html", "html_funkey-s.opk", gh("html", "html_funkey-s.opk", b"<html><body>Sign in to GitHub</body></html>" * 20), data=b"x")
cand("notfound", "notfound_funkey-s.opk", "https://github.com/o/notfound/releases/download/v1/notfound_funkey-s.opk", size=1000)
g = opk("gitlab"); files["../gl/o/gl/-/raw/master/opk/gitlab_funkey-s.opk"] = g
cand("gitlab", "gitlab_funkey-s.opk", "https://gitlab.com/o/gl/-/blob/master/opk/gitlab_funkey-s.opk", data=g)
big = opk("cancel", 3 << 20); cand("cancel", "cancel_funkey-s.opk", gh("cancel", "cancel_funkey-s.opk", big), data=big)
p = opk("paren"); cand("paren", "Foo_(NES).opk", gh("paren", "Foo_(NES).opk", p), data=p)
c = opk("collide"); cand("collide", "collide.opk", gh("collide", "collide.opk", c), data=c)
dn = opk("denied"); cand("denied", "retrohatch.opk", gh("denied", "retrohatch.opk", dn), data=dn)
cand("source", "x.opk", "", fmt="")
cand("gmenu2x", "gmenu2x_funkey-s.opk", gh("gmenu2x", "gmenu2x_funkey-s.opk", opk("g")), data=opk("g"))
cand("core", "core.zip", gh("core", "core.zip", b"zip"), fmt="zip", container="zip", data=b"zip")
cand("huge", "huge_funkey-s.opk", "https://github.com/o/huge/releases/download/v1/huge_funkey-s.opk", size=200 << 20)
cand("plainhttp", "plain_funkey-s.opk", "http://example.com/plain_funkey-s.opk", size=1000)
(FX / "candidates.json").write_text(json.dumps({"schema": 1, "device": "rg-nano", "status": "test", "candidates": cands}))
for rel, data in files.items():
    f = FX / "gh" / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
(FX / "variant.txt").write_text("ok")

run("openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", "ca.key", "-out", "ca.pem",
    "-subj", "/CN=rh-test-ca", "-days", "5", "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign")
run("openssl", "req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", "leaf.key", "-out", "leaf.csr", "-subj", "/CN=localhost")
(W / "leaf.ext").write_text("subjectAltName=DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n")
run("openssl", "x509", "-req", "-in", "leaf.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial", "-out", "leaf.pem", "-extfile", "leaf.ext", "-days", "5")


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reply(self, code, body):
        self.wfile.write(("HTTP/1.1 %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (code, len(body))).encode() + body)
        self.wfile.flush()
        self.close_connection = True

    def do_GET(self):
        p = self.path
        if p.startswith("/gh/") or p.startswith("/gl/"):
            f = (FX / "gh" / p[4:]) if p.startswith("/gh/") else (FX / "gh" / ".." / "gl" / p[4:])
            f = f.resolve()
            if f.is_file() and str(f).startswith(str(FX.resolve())):
                return self.reply("200 OK", f.read_bytes())
        self.reply("404 Not Found", b"")


ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(W / "leaf.pem", W / "leaf.key")
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
srv.daemon_threads = True
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

r = subprocess.run(["make", "-C", str(ROOT / "tests"), "mc_host.o", "mce_host.o", "ui_exp_test"], capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
shots = sys.argv[1] if len(sys.argv) > 1 else None
args = [str(ROOT / "tests" / "ui_exp_test"), str(ROOT), str(FX), str(port), str(W / "ca.pem")] + ([shots] if shots else [])
r = subprocess.run(args, capture_output=True, text=True, timeout=600)
print(r.stdout.strip())
print(r.stderr.strip()[-2500:])
shutil.rmtree(W, ignore_errors=True)
assert r.returncode == 0 and " 0 failed" in r.stdout, "experimental test install tests failed"
print("experimental tests OK")
