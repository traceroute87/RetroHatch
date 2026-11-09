"""Run inside WSL:  python3 tests/test_zip.py     (needs gcc, zlib)

core/rh_zip.c under ASan/UBSan against hand-built ZIP files: the good cases and every refusal (symlink, directory, device, encrypted, ZIP64,
multi-part, bzip2, traversal and odd names, duplicates, size and CRC lies, a deflate bomb, truncation, garbage, an existing destination)."""
import os, struct, subprocess, sys, tempfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
r = subprocess.run(["make", "-C", str(ROOT / "tests"), "../build/zip_cli"], capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
CLI = str(ROOT / "build" / "zip_cli")
W = Path(tempfile.mkdtemp(prefix="rhzip-"))
fails = checks = 0


def deflate(b):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(b) + c.flush()


def entry(name, data, method=8, flags=0, host=3, attrs=0o100644 << 16, crc=None, usize=None, csize=None, comp=None, local_name=None, disk=0, extra=b""):
    nm = name.encode() if isinstance(name, str) else name
    c = comp if comp is not None else (deflate(data) if method == 8 else data)
    return dict(nm=nm, ln=(local_name.encode() if local_name else nm), data=data, c=c, method=method, flags=flags, host=host, attrs=attrs,
                crc=zlib.crc32(data) if crc is None else crc, usize=len(data) if usize is None else usize,
                csize=len(c) if csize is None else csize, disk=disk, extra=extra)


def mkzip(entries, comment=b"", disks=(0, 0), count=None, tail_garbage=b""):
    body = b""
    cd = b""
    for e in entries:
        off = len(body)
        body += struct.pack("<IHHHHHIIIHH", 0x04034b50, 20, e["flags"], e["method"], 0, 0x21, e["crc"], e["csize"], e["usize"], len(e["ln"]), len(e["extra"])) + e["ln"] + e["extra"] + e["c"]
        cd += struct.pack("<IBBHHHHHIIIHHHHHII", 0x02014b50, 20, e["host"], 20, e["flags"], e["method"], 0, 0x21, e["crc"], e["csize"], e["usize"],
                          len(e["nm"]), 0, 0, e["disk"], 0, e["attrs"], off) + e["nm"]
    n = len(entries) if count is None else count
    eocd = struct.pack("<IHHHHIIH", 0x06054b50, disks[0], disks[1], n, n, len(cd), len(body), len(comment)) + comment
    return body + cd + eocd + tail_garbage


def run(name, zbytes, member="game.opk", maxo=1 << 20, want=0, pre_dest=False, expect_file=None):
    global fails, checks
    z = W / (name + ".zip")
    z.write_bytes(zbytes)
    d = W / (name + ".out")
    if d.exists():
        d.unlink()
    if pre_dest:
        d.write_bytes(b"keep me")
    p = subprocess.run([CLI, str(z), member, str(d), str(maxo)], capture_output=True, text=True, timeout=60)
    checks += 1
    ok = p.returncode == 0 and p.stdout.startswith("rc=%d " % want)
    if ok and want == 0:
        ok = d.read_bytes() == expect_file
    elif ok and pre_dest:
        ok = d.read_bytes() == b"keep me"
    elif ok:
        ok = not d.exists()           # a refusal leaves nothing behind
    if not ok:
        fails += 1
        print("FAIL %s: %s %s" % (name, p.stdout.strip(), p.stderr.strip()[:300]))


OPK = b"hsqs" + os.urandom(3000)
# --- accepted
run("deflate", mkzip([entry("game.opk", OPK)]), expect_file=OPK)
run("stored", mkzip([entry("game.opk", OPK, method=0)]), expect_file=OPK)
run("nested_path", mkzip([entry("opk/funkey/game.opk", OPK), entry("README", b"x")]), expect_file=OPK)
run("other_files_ignored", mkzip([entry("a/other.opk", b"hsqs1"), entry("game.opk", OPK), entry("../evil", b"x")]), expect_file=OPK)   # a bad name elsewhere is never extracted
run("zip_comment", mkzip([entry("game.opk", OPK)], comment=b"hello"), expect_file=OPK)
run("data_descriptor_flag", mkzip([entry("game.opk", OPK, flags=0x08)]), expect_file=OPK)
run("dos_host", mkzip([entry("game.opk", OPK, host=0, attrs=0x20)]), expect_file=OPK)
run("unix_no_mode", mkzip([entry("game.opk", OPK, attrs=0)]), expect_file=OPK)
run("exactly_max", mkzip([entry("game.opk", OPK)]), maxo=len(OPK), expect_file=OPK)
# --- refused (rc: 1 io, 2 format, 3 not found, 4 ambiguous, 5 unsupported, 6 unsafe, 7 size, 8 crc)
run("not_found", mkzip([entry("other.opk", OPK)]), want=3)
run("dir_entry_only", mkzip([entry("game.opk/", b"", method=0, attrs=(0o040755 << 16) | 0x10)]), want=3)
run("ambiguous", mkzip([entry("a/game.opk", OPK), entry("b/game.opk", OPK)]), want=4)
run("symlink", mkzip([entry("game.opk", b"/etc/passwd", method=0, attrs=0o120777 << 16)]), want=6)
run("device", mkzip([entry("game.opk", OPK, attrs=0o060644 << 16)]), want=6)
run("dos_directory", mkzip([entry("game.opk", OPK, host=0, attrs=0x10)]), want=6)
run("encrypted", mkzip([entry("game.opk", OPK, flags=0x01)]), want=5)
run("strong_encryption", mkzip([entry("game.opk", OPK, flags=0x40)]), want=5)
run("bzip2", mkzip([entry("game.opk", OPK, method=12, comp=OPK)]), want=5)
run("zip64_size", mkzip([entry("game.opk", OPK, csize=0xFFFFFFFF)]), want=5)
run("zip64_count", mkzip([entry("game.opk", OPK)], count=0xFFFF), want=5)
run("multi_part", mkzip([entry("game.opk", OPK)], disks=(1, 0)), want=5)
run("entry_other_disk", mkzip([entry("game.opk", OPK, disk=1)]), want=5)
run("traversal_dotdot", mkzip([entry("../game.opk", OPK)]), want=6)
run("traversal_mid", mkzip([entry("a/../../game.opk", OPK)]), want=6)
run("absolute", mkzip([entry("/etc/game.opk", OPK)]), want=6)
run("backslash_name_no_match", mkzip([entry("a\\game.opk", OPK)]), want=3)           # the base name is "a\game.opk": it does not match
run("backslash_member", mkzip([entry("x/a\\game.opk", OPK)]), member="a\\game.opk", want=6)
run("control_char", mkzip([entry("x/game.opk\x01", OPK)]), member="game.opk\x01", want=6)
run("empty_member", mkzip([entry("game.opk", b"", method=0)]), want=7)
run("too_large", mkzip([entry("game.opk", OPK)]), maxo=len(OPK) - 1, want=7)
run("stored_size_mismatch", mkzip([entry("game.opk", OPK, method=0, csize=len(OPK) - 1)]), want=7)
run("usize_smaller_than_data", mkzip([entry("game.opk", OPK, usize=len(OPK) - 10)]), want=7)
run("usize_larger_than_data", mkzip([entry("game.opk", OPK, usize=len(OPK) + 10)]), want=7)
run("bad_crc", mkzip([entry("game.opk", OPK, crc=1234)]), want=8)
run("bad_crc_stored", mkzip([entry("game.opk", OPK, method=0, crc=1234)]), want=8)
big = bytes(50 << 20)                                                  # 50 MB of zeros deflates to ~50 KB
bomb = deflate(big)
run("bomb_declared_big", mkzip([entry("game.opk", big, comp=bomb)]), maxo=1 << 20, want=7)                       # refused from the headers alone
run("bomb_lying_usize", mkzip([entry("game.opk", big, comp=bomb, usize=1 << 19)]), maxo=1 << 20, want=7)         # declares 512 KB, inflates to 50 MB: stopped at the declared size
run("ratio_lie", mkzip([entry("game.opk", OPK, comp=deflate(OPK), usize=10 << 20)]), maxo=64 << 20, want=7)
good = mkzip([entry("game.opk", OPK)])
run("truncated_half", good[: len(good) // 2], want=2)
run("truncated_eocd", good[:-5], want=2)
run("garbage", os.urandom(5000), want=2)
run("tiny", b"PK\x05\x06", want=2)
run("empty", b"", want=2)
run("trailing_garbage", mkzip([entry("game.opk", OPK)], tail_garbage=b"junk"), want=2)
run("cut_deflate", mkzip([entry("game.opk", OPK, comp=deflate(OPK)[:-20])]), want=2)                              # stream ends early
run("extra_after_stream", mkzip([entry("game.opk", OPK, comp=deflate(OPK) + b"JUNKJUNK")]), want=2)
run("corrupt_deflate", mkzip([entry("game.opk", OPK, comp=b"\xff" * 200)]), want=2)
run("local_name_differs", mkzip([entry("game.opk", OPK, local_name="gamX.opk")]), want=2)
run("dest_exists", mkzip([entry("game.opk", OPK)]), want=1, pre_dest=True)                                          # never overwrites
run("bad_request_slash", good, member="a/game.opk", want=2)
run("bad_request_empty", good, member="", want=2)
p = subprocess.run([CLI, str(W / "nope.zip"), "game.opk", str(W / "nope.out"), "1000"], capture_output=True, text=True)
checks += 1
if not p.stdout.startswith("rc=1 "):
    fails += 1
    print("FAIL missing file:", p.stdout)
print("zip tests: %d checks, %d failed" % (checks, fails))
sys.exit(1 if fails else 0)
