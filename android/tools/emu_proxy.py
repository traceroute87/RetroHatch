#!/usr/bin/env python3
"""Test infrastructure only: a tiny CONNECT-only TCP tunnel for the Android emulator when its own network cannot resolve DNS / open TCP (host VPN / firewall quirks).
The emulator reaches it as 10.0.2.2:PORT:   adb shell settings put global http_proxy 10.0.2.2:8899     (undo: ... http_proxy :0)
It only tunnels bytes: TLS stays end-to-end between the app and the real server, so certificate validation, the SHA-256 / package / signer checks and every redirect rule of the
app are exactly as without it. It refuses anything but CONNECT to port 443.
    python android/tools/emu_proxy.py [port]"""
import socket, sys, threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899


def pipe(a, b):
    try:
        while (d := a.recv(65536)):
            b.sendall(d)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass


def handle(c):
    try:
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 8192:
            d = c.recv(4096)
            if not d: return
            head += d
        line = head.split(b"\r\n", 1)[0].decode("latin-1").split()
        if len(line) < 2 or line[0] != "CONNECT" or not line[1].endswith(":443"):
            c.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n"); return
        host = line[1].rsplit(":", 1)[0]
        up = socket.create_connection((host, 443), timeout=20)
        c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        threading.Thread(target=pipe, args=(up, c), daemon=True).start()
        pipe(c, up)
    except OSError:
        c.close()


s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", PORT)); s.listen(64)
print("CONNECT proxy on", PORT, flush=True)
while True:
    conn, _ = s.accept(); threading.Thread(target=handle, args=(conn,), daemon=True).start()
