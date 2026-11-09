"""Run inside WSL:  python3 tests/test_batch.py     (needs sh, awk, md5sum; no device, no network)

Focused offline checks for the batch compatibility tool: the launch-metadata inspection (tools/opk_inspect.py) on hostile and good package trees,
the verdict rules (tools/batch_test.py judge: a process alone is never PASS), and the on-device launch script (tools/batch_launch.sh) against stub
launchers that exit, crash, ignore SIGTERM or run until stopped."""
import os, struct, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import opk_inspect as I
import batch_test as BT

fails = checks = 0


def check(cond, what):
    global fails, checks
    checks += 1
    if not cond:
        fails += 1
        print("FAIL:", what)


def elf(machine=40, flags=0x05000400, interp="/lib/ld-musl-armhf.so.1", needed=("libSDL-1.2.so.0",), cls=1):
    """a minimal 32-bit ELF with PT_LOAD, PT_INTERP and PT_DYNAMIC (+ DT_NEEDED)"""
    interp_b = interp.encode() + b"\0" if interp else b""
    strtab = b"\0" + b"".join(n.encode() + b"\0" for n in needed)
    offs, o = [], 1
    for n in needed:
        offs.append(o); o += len(n) + 1
    phnum = 3 if interp else 2
    base = 52 + 32 * phnum
    interp_off = base; str_off = interp_off + len(interp_b)
    dyn = b"".join(struct.pack("<II", 1, x) for x in offs) + struct.pack("<II", 5, str_off) + struct.pack("<II", 0, 0)
    dyn_off = str_off + len(strtab); total = dyn_off + len(dyn)
    ident = b"\x7fELF" + bytes([cls, 1, 1, 0]) + bytes(8)
    hdr = ident + struct.pack("<HHIIIIIHHHHHH", 2, machine, 1, 0, 52, 0, flags, 52, 32, phnum, 40, 0, 0)
    ph = struct.pack("<IIIIIIII", 1, 0, 0, 0, total, total, 5, 4)
    if interp:
        ph += struct.pack("<IIIIIIII", 3, interp_off, 0, 0, len(interp_b), len(interp_b), 4, 1)
    ph += struct.pack("<IIIIIIII", 2, dyn_off, dyn_off, 0, len(dyn), len(dyn), 6, 4)
    return hdr + ph + interp_b + strtab + dyn


def tree(files, links=None):
    d = Path(tempfile.mkdtemp(prefix="rhtree-"))
    for name, data in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
        if name in ("game", "launch.sh"):
            p.chmod(0o755)
    for name, tgt in (links or {}).items():
        os.symlink(tgt, d / name)
    return d


DESK = "[Desktop Entry]\nName=Test\nExec=launch.sh\nType=Application\nCategories=games;\n"
GOOD_SH = "#!/bin/sh\ncd \"$(dirname \"$0\")\"\nmkdir -p \"$HOME/.test\"\nexec ./game\n"
good = {"t.funkey-s.desktop": DESK, "launch.sh": GOOD_SH, "game": elf()}


def verdict(files, **kw):
    r = I.inspect_tree(str(tree(files, kw.pop("links", None))), **kw)
    return r["verdict"], " | ".join(r["reasons"])


v, why = verdict(good, libs=["libSDL-1.2.so.0", "libc.so"])
check(v == "ok", "good tree is ok: %s %s" % (v, why))
v, why = verdict(good, libs=None); check(v == "ok", "without a device library list the libraries are not checked")
v, why = verdict(dict(good), libs=["libz.so.1"])
check(v == "skip" and "libSDL-1.2.so.0" in why, "missing library is skipped: %s" % why)
check(verdict(dict(good, **{"lib/libSDL-1.2.so.0": b"x"}), libs=[])[0] == "ok", "a library shipped in the package counts")
v, why = verdict({k: v for k, v in good.items() if k != "t.funkey-s.desktop"}); check(v == "skip" and "desktop" in why, "no FunKey desktop entry: " + why)
v, why = verdict({"t.anbernic.desktop": DESK, "launch.sh": GOOD_SH}); check(v == "skip", "only a stock-Anbernic desktop entry is not enough")
v, why = verdict({"t.funkey-s.desktop": DESK.replace("launch.sh", "missing.sh")}); check(v == "skip" and "not in the package" in why, "Exec target must exist: " + why)
v, why = verdict({"t.funkey-s.desktop": DESK.replace("launch.sh", "/bin/sh -c x"), "launch.sh": GOOD_SH}); check(v == "skip" and "outside the package" in why, "Exec outside the package: " + why)
v, why = verdict(dict(good, **{"lib/helper.so": elf(machine=3)})); check(v == "ok", "a non-ARM shared library is only a note")
v, why = verdict({"t.funkey-s.desktop": DESK.replace("launch.sh", "game"), "game": elf(machine=3)}); check(v == "skip" and "not a 32-bit ARM" in why, "x86 main program: " + why)
v, why = verdict({"t.funkey-s.desktop": DESK.replace("launch.sh", "game"), "game": elf(machine=183, cls=2)}); check(v == "skip", "64-bit ARM main program")
v, why = verdict({"t.funkey-s.desktop": DESK.replace("launch.sh", "game"), "game": elf(interp="/lib/ld-linux-armhf.so.3")}); check(v == "skip" and "loader" in why, "glibc loader not on the device: " + why)
v, why = verdict({"t.funkey-s.desktop": DESK.replace("launch.sh", "game"), "game": elf(interp="/lib/ld-linux-armhf.so.3"), "lib/ld-linux-armhf.so.3": b"x"}); check(v == "ok", "a shipped loader is fine: " + why)
v, why = verdict(good, comp=6); check(v == "skip" and "compression" in why, "unsupported squashfs compression: " + why)
check(verdict(good, comp=1)[0] == "ok" and verdict(good, comp=4, comps=(1, 4))[0] == "ok", "supported compressions pass")
v, why = verdict(good, links={"etc_link": "/etc/passwd"}); check(v == "skip" and "system path" in why, "absolute link to /etc: " + why)
v, why = verdict(good, links={"up": "../../outside"}); check(v == "skip" and "leaves the package" in why, "relative link out of the package: " + why)
v, why = verdict(good, links={"inside": "game"}); check(v == "ok", "a link inside the package is fine")
v, why = verdict(good, listing=[("c", 0, "dev/null")]); check(v == "skip" and "special file" in why, "device node in the image")
v, why = verdict(good, listing=[("-", 0o4000, "su")]); check(v == "skip" and "setuid" in why, "setuid file in the image")

BAD_LINES = {
    "mount -o bind /a /b": "mounts", "umount /opk": "mounts", "dd if=x of=/dev/mmcblk0 bs=1M": "devices", "mkfs.vfat /dev/x": "devices",
    "fw_setenv bootargs x": "firmware", "insmod x.ko": "kernel modules", "modprobe zram": "kernel modules", "reboot": "reboots", "poweroff -f": "reboots",
    "echo 1 > /dev/mmcblk0p1": "storage", "cp x /etc/y": "system directories", "rm -rf /usr/lib/foo": "system directories", "echo a >> /etc/passwd": "system directories",
    "rm -rf /": "root", "rm -rf /mnt/*": "root", "wget http://x/y": "network", "curl -O x": "network", "echo aGk= | base64 -d | sh": "hidden", "eval $X": "hidden",
    "pkill fkgpiod": "daemons", "killall retrofe": "daemons", "echo LOAD x > /tmp/fkgpiod.fifo": "button daemon", "keymap default": "key-map command",
    "frontend set none": "launcher", "touch /mnt/disable_frontend": "launcher", "cp x /mnt/Applications/y.opk": "application folders", "sudo x": "privileges",
    "swapon /x": "devices", "chroot /x sh": "privileges", "nc -l 99": "network", "rm -f /mnt/instant_play": "flag files", "rm -rf /mnt": "root", "rm -rf /home/*": "root"}
for line, tag in BAD_LINES.items():
    v, why = verdict({"t.funkey-s.desktop": DESK, "launch.sh": "#!/bin/sh\n" + line + "\nexec ./game\n", "game": elf()})
    check(v == "skip" and tag in why, "dangerous command skipped: %r -> %s %s" % (line, v, why[:80]))
GOOD_LINES = ["export HOME=/mnt/FunKey", "mkdir -p $HOME/.kishmish-nano", "echo \"mount point is not used; keymap loaded; reboot not needed\"", "# mount -o bind a b",
              "./lib/ld-musl-armhf.so.1 --library-path ./lib ./kishmish", "cd \"$(dirname \"$0\")\"", "ls -l kishmish lib/", "cp -r data \"$HOME/.game/\"", "printf 'wget is a tool'\\n", "rm -f /mnt/FunKey/.game/tmp", "rm -rf ./cache"]
for line in GOOD_LINES:
    v, why = verdict({"t.funkey-s.desktop": DESK, "launch.sh": "#!/bin/sh\n" + line + "\nexec ./game\n", "game": elf()})
    check(v == "ok", "harmless line accepted: %r -> %s %s" % (line, v, why[:80]))
v, why = verdict(dict(good, **{"x.key": "CLEAR\nMAP A TO KEY KEY_A\nMAP FN+A TO COMMAND poweroff\n", "t.funkey-s.desktop": DESK + "FK-Keymap=x.key\n"})); check(v == "skip" and "console commands" in why, "key map running a command: " + why)
v, why = verdict(dict(good, **{"x.key": "CLEAR\nMAP A TO KEY KEY_A\n", "t.funkey-s.desktop": DESK + "FK-Keymap=x.key\n"})); check(v == "ok", "plain key map accepted")
v, why = verdict(dict(good, **{"x.key": "CLEAR\nUNMAP FN+Y\nMAP A TO KEY KEY_A\n", "t.funkey-s.desktop": DESK + "FK-Keymap=x.key\n"})); check(v == "ok", "UNMAP lines are accepted: " + why)
v, why = verdict(dict(good, **{"x.key": "rm -rf /\n", "t.funkey-s.desktop": DESK + "FK-Keymap=x.key\n"})); check(v == "skip", "key map with arbitrary lines")
check(I.comp_id(__file__) is None, "a non-squashfs file has no compression id")

# ---- verdict rules: PASS only with a picture AND a clean stop; process-only is never PASS ----
K = {"ALIVE_AT_END": "1", "STOP": "term", "EXIT": "0", "LIFE_S": ""}
j = lambda k, log="", dm="", colors=100, top=0.4: BT.judge(dict(K, **k), log, "", dm, colors, top)[0]
check(j({}) == "PASS", "alive + picture + clean stop = PASS")
check(j({}, colors=1, top=1.0) == "NEEDS MANUAL CHECK", "alive but blank screen is never PASS")
check(j({}, colors=8, top=0.5) == "NEEDS MANUAL CHECK", "too few colours is never PASS")
check(j({}, colors=100, top=0.995) == "NEEDS MANUAL CHECK", "a nearly uniform screen is never PASS")
check(j({"STOP": "kill"}) == "HANG" and j({"STOP": "stuck"}) == "HANG", "ignoring SIGTERM is a HANG even with a picture")
check(j({"ALIVE_AT_END": "0", "EXIT": "1", "LIFE_S": "1"}, log="NanoCraft's runtime is missing") == "FAIL", "early exit with status 1 is FAIL")
check(j({"ALIVE_AT_END": "0", "EXIT": "0", "LIFE_S": "1"}) == "FAIL", "early exit with status 0 is also FAIL (it did not stay running)")
check(j({"ALIVE_AT_END": "0", "EXIT": "139", "LIFE_S": "2"}) == "CRASH" and j({"ALIVE_AT_END": "0", "EXIT": "132", "LIFE_S": "2"}) == "CRASH", "signal exit is CRASH")
check(j({"ALIVE_AT_END": "0", "EXIT": "1"}, log="Segmentation fault") == "CRASH", "segfault text is CRASH")
check(j({}, dm="game[123]: segfault at 0 ip 0 sp 0") == "CRASH", "kernel segfault line is CRASH even if it still ran")
check(j({}, log="ALSA lib pcm.c: Unknown PCM /dev/dsp1\nMeow audio ready") == "PASS", "a benign log warning does not stop a PASS")

# ---- the on-device launch script against stub launchers ----
T = Path(tempfile.mkdtemp(prefix="rhstub-"))
(T / "bin").mkdir(); (T / "app").mkdir(); (T / "rhb").mkdir()
for c in ("keymap", "termfix_all", "umount", "pid"):
    (T / "bin" / c).write_text("#!/bin/sh\necho $0 $* >> %s/calls\nexit 0\n" % T)
(T / "bin" / "dmesg").write_text("#!/bin/sh\necho k1\n")
(T / "bin" / "opkrun").write_text("""#!/bin/sh
case "$1" in
 *good*) ( trap 'exit 0' TERM; while :; do sleep 1; done ) & wait $! ;;
 *stubborn*) ( trap '' TERM; while :; do sleep 1; done ) & wait $! ;;
 *early*) echo "runtime is missing"; exit 1 ;;
 *crash*) sleep 2; kill -SEGV $$ ;;
esac
""")
for f in (T / "bin").iterdir():
    f.chmod(0o755)
(T / "fb.raw").write_bytes(os.urandom(115200)); (T / "msgs").write_text("")
for n in ("good", "stubborn", "early", "crash"):
    (T / "app" / (n + ".opk")).write_text("x")
env = dict(os.environ, PATH=str(T / "bin") + os.pathsep + os.environ["PATH"], RHB_DIR=str(T / "rhb"), RHB_FB=str(T / "fb.raw"), RHB_MSGS=str(T / "msgs"))


def launch(n):
    r = subprocess.run(["sh", str(ROOT / "tools" / "batch_launch.sh"), str(T / "app" / (n + ".opk")), n, "4", "6", "3"], capture_output=True, text=True, env=env, timeout=60)
    return BT.kv(r.stdout)


k = launch("good"); check(k.get("ALIVE_AT_END") == "1" and k.get("STOP") == "term" and k.get("EXIT") == "0" and k.get("DONE") == "1", "stub that stops on TERM: %s" % k)
check(k.get("KEYMAP_DEFAULT") == "0", "no 'default: LOAD' line in the syslog after clean-up is reported (KEYMAP_DEFAULT=0), not silently accepted")
(T / "msgs").write_text("Nov 7 19:00:00 FunKey user.notice keymap[1]: default: LOAD /etc/fkgpiod.conf\n")
check(launch("early").get("KEYMAP_DEFAULT") == "1", "a fresh 'default: LOAD' line is confirmed (KEYMAP_DEFAULT=1)")
(T / "msgs").write_text("")
check((T / "rhb" / "good.fb").stat().st_size == 115200 and "S4" in k and k["S4"].split(",")[-1] == k["S2"].split(",")[-1], "frame captured; identical frames are visible as identical")
k = launch("stubborn"); check(k.get("STOP") == "kill" and k.get("EXIT") == "137", "stub that ignores TERM is killed only after the wait: %s" % k)
k = launch("early"); check(k.get("ALIVE_AT_END") == "0" and k.get("EXIT") == "1" and k.get("STOP") == "none", "stub that exits by itself: %s" % k)
check("runtime is missing" in (T / "rhb" / "early.log").read_text(), "app output is kept")
k = launch("crash"); check(k.get("ALIVE_AT_END") == "0" and k.get("EXIT") == "139", "stub that crashes: %s" % k)
calls = (T / "calls").read_text()
check(calls.count("keymap rom") == 5 and calls.count("keymap default") == 5 and calls.count("termfix_all") == 5 and "pid record" in calls and "pid erase" in calls, "the frontend's own sequence runs every time (keymap rom, pid record/erase, termfix_all, keymap default)")
check(subprocess.run(["sh", str(ROOT / "tools" / "batch_launch.sh"), str(T / "app" / "nope.opk"), "nope"], capture_output=True, text=True, env=env).stdout.startswith("ERROR="), "a missing OPK is refused")
print("batch tests: %d checks, %d failed" % (checks, fails))
sys.exit(1 if fails else 0)
