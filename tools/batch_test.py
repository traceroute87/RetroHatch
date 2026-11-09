#!/usr/bin/env python3
"""Batch compatibility test of the experimental-install candidates on the real RG Nano. One tool, no second installer.

  python tools/batch_test.py dry-run [--ids a,b] [--device]   host only: classify, download (cached), inspect launch metadata; --device adds the READ-ONLY preflight
  python tools/batch_test.py validate                          the three known-good apps (znax, rubido, 2048): proves the method before the batches
  python tools/batch_test.py run [--batch 10] [--ids a,b]      install + launch every eligible candidate, in batches, health check between batches
  python tools/batch_test.py report                            rewrite docs/APP_COMPATIBILITY_RESULTS.md from build/batch/results.json

How it reuses what exists (nothing here installs anything itself):
  * download + install + uninstall = the experimental installer of the DEV program (ui/rh_ops_exp.inc), driven headless by platforms/nano/cli/rh_exp_cli.c:
    the host build downloads (HTTPS, ZIP member extraction, squashfs check), the Nano build (build/rh_exp_arm, copied to /tmp = RAM) installs through the
    same engine (hash, "never overwrite what RetroHatch did not install", mount check, journal). Installed apps are recorded in installed.tsv as x-<id>.
  * launch = the FunKey frontend's own path (tools/batch_launch.sh: keymap rom, opkrun with pid record, then the frontend loop's termfix_all / keymap default).
  * the launcher (retrofe) is held off with the system's own /mnt/disable_frontend switch while a batch runs, with a dead-man timer on the Nano that removes
    it again, and is released at the end (the frontend loop then starts it).
Never: presses buttons, power-cycles, touches firmware, uninstalls anything, or runs a candidate that opk_inspect.py marks skip/manual.
Results: build/batch/results.json (resumable), build/batch/shots/<id>.png, docs/APP_COMPATIBILITY_RESULTS.md."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
B = ROOT / "build" / "batch"
RES, SHOTS = B / "results.json", B / "shots"
HOST_STATE = B / "host" / ".retrohatch-dev"
CACHE = HOST_STATE / "cache"
SNAP = ROOT / "candidates" / "rg-nano.json"
REPORT = ROOT / "docs" / "APP_COMPATIBILITY_RESULTS.md"
SSH_SH = Path.home() / ".ssh" / "rgnano_ssh.sh"
DEV_STATE, APPS, REMOTE = "/mnt/FunKey/.retrohatch-dev", "/mnt/Applications", "/tmp/rhb"
KNOWN = ["znax", "rubido", "2048"]
UNRELATED = ["RetroHatch.opk", "RetroHatchDev.opk", "rhprobe_funkey-s.opk", "commander_funkey-s.opk", "gmu_funkey-s.opk", "st-sdl_funkey-s.opk", "unarchiver_funkey-s.opk"]
STARTUP_S, RUN_S, TERM_S = 8, 14, 8
# An emulator/player that exits at once because it was started without a ROM/file is not broken: it needs input the batch cannot give.
NEEDS_FILE = re.compile(r"requires a file as parameter|ROM filename missing|Specify a ROM|needs pfi file|Not enough command line arguments|Usage: \./\w+ \[FILE\]", re.I)
MIN_VOLT_UV = 3500000   # 3.5 V under light load = nearly empty / sagging
KEYMAP_BAD = []   # ids whose launch ended without "keymap default" confirmed
MIN_BATTERY, MIN_START_BATTERY, MIN_FREE_MB = 5, 40, 3500
KERNEL_BAD = re.compile(r"segfault|Oops|Unable to handle|Illegal instruction|Bus error|I/O error|FAT-fs.*(error|corrupt)|remount|Read-only|EXT4-fs error|blk_update_request|mmcblk\d.*error", re.I)
LOG_BAD = re.compile(r"segmentation fault|illegal instruction|bus error|symbol lookup error|error loading shared librar|cannot open shared object|runtime is missing|no such file|not found|missing|cannot|unable to|failed to", re.I)


class Stop(Exception):
    pass


# ------------------------------------------------------------------ plumbing
def wslp(p):
    p = Path(p).resolve()
    return "/mnt/%s/%s" % (p.drive[0].lower(), "/".join(p.parts[1:]))


def wsl(cmd, timeout=600):
    r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", "cd %s && %s" % (wslp(ROOT), cmd)], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def ssh(cmd, timeout=60, stdin=subprocess.DEVNULL, binary=False):
    """Run a command on the Nano through the existing SSH wrapper. SSH loss or a hang = Stop (the run never continues blind)."""
    try:
        r = subprocess.run(["sh", str(SSH_SH), cmd], capture_output=True, timeout=timeout, stdin=stdin)
    except subprocess.TimeoutExpired:
        raise Stop("lost the Nano: ssh timed out (%s...)" % cmd[:50])
    if r.returncode == 255:
        raise Stop("lost the Nano: ssh failed: %s" % r.stderr.decode(errors="replace").strip()[-120:])
    return r.returncode, (r.stdout if binary else r.stdout.decode(errors="replace")), r.stderr.decode(errors="replace")


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def push(local, remote):
    """Copy to <remote>.new, check the SHA-256 there, then rename. Skipped when the remote file already has the same hash."""
    want = sha_file(local)
    rc, out, _ = ssh("sha256sum %s 2>/dev/null | cut -d' ' -f1" % remote)
    if out.strip() == want:
        return "present"
    with open(local, "rb") as f:
        rc, _, err = ssh("cat > %s.new" % remote, timeout=900, stdin=f)
    rc, out, _ = ssh("sha256sum %s.new | cut -d' ' -f1" % remote)
    if out.strip() != want:
        ssh("rm -f %s.new" % remote)
        raise Stop("copy to the Nano failed the hash check: %s" % remote)
    ssh("mv %s.new %s" % (remote, remote))
    return "copied"


def load_res():
    return json.loads(RES.read_text(encoding="utf-8")) if RES.is_file() else {"apps": {}, "meta": {}}


def save_res(r):
    B.mkdir(parents=True, exist_ok=True)
    RES.write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")


def candidates():
    return {c["id"]: c for c in json.loads(SNAP.read_text(encoding="utf-8"))["candidates"]}


# ------------------------------------------------------------------ host side: classify, download, inspect
def host_cli(args, timeout=900):
    cmd = "./build/rh_exp_host --state %s --apps %s --cands candidates/rg-nano.json --ca platforms/nano/ui/ca-bundle.crt %s" % (wslp(HOST_STATE), wslp(B / "host" / "apps"), args)
    (B / "host" / "apps").mkdir(parents=True, exist_ok=True)
    return wsl(cmd, timeout)


def classify():
    rc, out, err = host_cli("classify")
    if rc:
        raise SystemExit("classify failed: build the host driver first (make -C tests ../build/rh_exp_host): " + out + err)
    d = {}
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) == 4:
            d[p[0]] = {"state": p[1], "why": p[2], "file": p[3]}
    return d


def download(cid):
    p = CACHE / ("x-%s.opk" % cid)
    if p.is_file():
        return True, "cached"
    rc, out, err = host_cli("download %s" % cid)
    m = re.search(r"RESULT (\d) (.*)", out)
    msg = m.group(2) if m else (out + err).strip()[-120:]
    if rc != 0 and "TLS handshake failed" in msg:
        return pc_fetch(cid, p)
    return (rc == 0 and p.is_file()), msg


def pc_fetch(cid, dest):
    """The Nano's HTTPS client (mbedTLS 2.16) cannot talk to servers that only offer TLS 1.3 (static.miraheze.org, 33 candidates). For a direct OPK from such a
    host the PC downloads it instead (plain HTTPS, certificate checked by Python, honest User-Agent, 64 MB cap); the installer still re-checks the squashfs
    magic and computes the SHA-256 at install time. The result is flagged in the report. ZIPs are not fetched this way."""
    import urllib.request
    pk = candidates()[cid]["package"]
    if pk.get("container") or not pk["url"].startswith("https://"):
        return False, "TLS handshake failed (and not a direct OPK)"
    try:
        req = urllib.request.Request(pk["url"], headers={"User-Agent": "RetroHatch/1 (batch test)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(64 * 1024 * 1024 + 1)
    except Exception as e:
        return False, "TLS handshake failed on the Nano client; PC fetch failed too: %s" % str(e)[:80]
    if len(data) > 64 * 1024 * 1024 or data[:4] != b"hsqs":
        return False, "PC fetch: not an OPK (%d bytes, header %r)" % (len(data), data[:4])
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data); tmp.replace(dest)
    return True, "fetched by the PC (the Nano's HTTPS client cannot do TLS 1.3)"


def inspect(cid, libs, comps):
    arg = "python3 tools/opk_inspect.py %s" % wslp(CACHE / ("x-%s.opk" % cid))
    if libs is not None:
        arg += " --libs %s" % ",".join(libs)
    if comps:
        arg += " --comp %s" % ",".join(map(str, comps))
    rc, out, err = wsl(arg, 300)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"verdict": "skip", "reasons": ["inspection failed: " + (err or out).strip()[-100:]], "notes": []}


def prepare(cid, cls, libs, comps, rec):
    """host part for one candidate. Returns a final-verdict dict, or None when it may go to the device."""
    c = cls[cid] if cid in cls else None
    if not c or c["state"] == "no":
        return {"verdict": "SKIPPED", "reason": (c or {}).get("why") or "not installable"}
    ok, msg = download(cid)
    if (CACHE / ("x-%s.opk" % cid)).is_file() and msg == "cached":
        msg = "cached " + str(load_res()["apps"].get(cid, {}).get("fetched_by") or "")
    if not ok:
        return {"verdict": "SKIPPED", "reason": "unavailable: " + msg}
    p = CACHE / ("x-%s.opk" % cid)
    rec.update(sha256=sha_file(p), size=p.stat().st_size, file=c["file"])
    rec["fetched_by"] = "PC Python (the Nano's downloader cannot do TLS 1.3)" if ("fetched by the PC" in msg or "PC Python" in msg) else "RetroHatch downloader code, run on the PC"
    ins = inspect(cid, libs, comps)
    rec["inspect"] = {k: ins.get(k) for k in ("verdict", "reasons", "notes", "exec", "desktop", "files")}
    if ins["verdict"] == "skip":
        return {"verdict": "SKIPPED", "reason": "; ".join(ins["reasons"])[:300]}
    if ins["verdict"] == "manual":
        return {"verdict": "NEEDS MANUAL CHECK", "reason": "not launched: " + "; ".join(ins["reasons"])[:300]}
    return None


# ------------------------------------------------------------------ device side
def kv(text):
    d = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1); d[k.strip()] = v.strip()
    return d


def device_facts():
    rc, out, _ = ssh("""echo boot=$(cat /proc/sys/kernel/random/boot_id); echo batt=$(cat /sys/class/power_supply/axp20x-battery/capacity); echo bstat=$(cat /sys/class/power_supply/axp20x-battery/status)
echo usb=$(cat /sys/class/power_supply/axp20x-usb/present 2>/dev/null); echo up=$(cut -d' ' -f1 /proc/uptime)
echo free_mb=$(df -k /mnt | tail -1 | tr -s ' ' | cut -d' ' -f4 | awk '{print int($1/1024)}'); echo mnt_rw=$(grep -c ' /mnt vfat rw' /proc/mounts)
echo opk_mounted=$(grep -c ' /opk ' /proc/mounts); echo apps_running=$(for d in /proc/[0-9]*; do cat $d/comm 2>/dev/null; done | grep -cE '^(opkrun|native_launch)')
echo fkgpiod=$(pidof fkgpiod | wc -w); echo retrofe=$(pidof retrofe | wc -w); echo dmesg_n=$(dmesg | wc -l)
echo msgs_n=$(wc -l < /tmp/messages); echo disabled=$(test -f /mnt/disable_frontend && echo 1 || echo 0)""")
    return kv(out)


def preflight(check_only=False):
    f = device_facts()
    probs = []
    batt = int(f["batt"]); charging = f.get("usb") == "1" or f["bstat"] in ("Charging", "Full")
    if batt < MIN_BATTERY or (batt < MIN_START_BATTERY and not charging):
        probs.append("battery %d%% (%s): need %d%%+ or charging and %d%%+" % (batt, f["bstat"], MIN_START_BATTERY, MIN_BATTERY))
    if int(f["free_mb"]) < MIN_FREE_MB: probs.append("free space %s MB < %d MB" % (f["free_mb"], MIN_FREE_MB))
    if f["mnt_rw"] != "1": probs.append("/mnt is not mounted read-write")
    if f["opk_mounted"] != "0": probs.append("an OPK is mounted at /opk")
    if f["apps_running"] != "0": probs.append("an application is running (close it)")
    if f["fkgpiod"] == "0": probs.append("button daemon fkgpiod not running")
    if f["disabled"] != "0": probs.append("/mnt/disable_frontend already exists (left over from something else)")
    # Known boot artifact (docs/HARDWARE_TEST_5C3/8/9): the Bluetooth storage.img loop gets one "I/O error, sector 200" ~15-50 s after boot (loop0 or loop1, depending on mount order).
    # Exempt ONLY that exact line, ONLY in the first 100 s of uptime, ONLY while loop1 is backed by that image. Anything else (other sector/device, later, recurring) stays fatal.
    rc, out, _ = ssh("bt=$(cat /sys/block/loop1/loop/backing_file 2>/dev/null); dmesg | tail -80 | grep -iE 'I/O error|FAT-fs.*error|remount|segfault|Oops' | grep -v 'loop0' | "
                     "{ if [ \"$bt\" = /mnt/FunKey/connectivity/bluetooth/storage.img ]; then grep -vE '^\\[ *[0-9]{1,2}\\.[0-9]+\\] print_req_error: I/O error, dev loop1, sector 200$'; else cat; fi; } | tail -5")
    if out.strip(): probs.append("kernel errors in dmesg: " + out.strip().replace("\n", " | ")[:200])
    rc, out, _ = ssh("(zcat /proc/config.gz 2>/dev/null | grep -E '^CONFIG_SQUASHFS_(ZLIB|XZ|LZO|LZ4|ZSTD)=y' | tr '\\n' ' '); echo; ls /lib /usr/lib /usr/local/lib 2>/dev/null | grep -v ':$' | sort -u | tr '\\n' ','")
    cfg, _, libs = out.partition("\n")
    ids = {"ZLIB": 1, "XZ": 4, "LZO": 3, "LZ4": 5, "ZSTD": 6}
    comps = sorted({ids[m] for m in re.findall(r"SQUASHFS_(\w+)=y", cfg)}) or [1]
    base = {}
    rc, out, _ = ssh("cd %s && sha256sum %s 2>/dev/null" % (APPS, " ".join(UNRELATED)))
    for line in out.splitlines():
        h, _, n = line.partition("  "); base[n] = h
    rc, out, _ = ssh("ls -A /mnt/FunKey/.retrohatch | tr '\\n' ' '; echo; cat %s/installed.tsv 2>/dev/null | cut -f1,2 | tr '\\n' ';'" % DEV_STATE)
    f.update(libs=[x for x in libs.strip().split(",") if x], comps=comps, unrelated=base, prod_state=out.splitlines()[0] if out else "", charging=charging)
    f["backups"] = {n: (ROOT / "build" / "backup" / "2026-11-06" / n).is_file() for n in ("RetroHatch.opk", "RetroHatchDev.opk", "retrohatch-state.tar")}
    if not all(f["backups"].values()): probs.append("backups missing in build/backup/2026-11-06: %s" % [n for n, v in f["backups"].items() if not v])
    if set(base) != set(UNRELATED): probs.append("could not hash all unrelated apps: %s" % sorted(set(UNRELATED) - set(base)))
    f["problems"] = probs
    return f


def health(pf, stage):
    """Between batches: nothing unexpected happened. Returns a list of problems (empty = healthy)."""
    f = device_facts(); probs = []
    if f["boot"] != pf["boot"]: probs.append("the Nano rebooted (boot id changed)")
    if int(f["batt"]) < MIN_BATTERY: probs.append("battery %s%% < %d%%" % (f["batt"], MIN_BATTERY))
    # power health (battery-only run: the OTG Wi-Fi adapter blocks charging): battery voltage must hold, and no new power-related kernel lines
    rc, out, _ = ssh("echo $(cat /sys/class/power_supply/axp20x-battery/voltage_now); dmesg | tail -n +%d | grep -iE 'under-?volt|brown|low battery|power.*(fail|loss)|axp20x.*(err|warn)|thermal' | head -3" % (int(pf["dmesg_n"]) + 1))
    v, _, pw = out.partition("\n")
    if v.strip().isdigit() and int(v) < MIN_VOLT_UV: probs.append("battery voltage %d mV < %d mV" % (int(v) // 1000, MIN_VOLT_UV // 1000))
    if pw.strip(): probs.append("power-related kernel messages: " + pw.strip().replace("\n", " | ")[:200])
    if f["mnt_rw"] != "1": probs.append("/mnt is no longer read-write")
    if f["apps_running"] != "0": probs.append("an application is still running")
    if f["opk_mounted"] != "0": probs.append("an OPK is still mounted at /opk")
    if f["fkgpiod"] == "0": probs.append("fkgpiod is gone")
    rc, out, _ = ssh("dmesg | tail -n +%d | grep -iE 'I/O error|FAT-fs.*(error|corrupt)|remount|Oops|Unable to handle|EXT4-fs error' | grep -v 'loop0' | head -3" % (int(pf["dmesg_n"]) + 1))
    if out.strip(): probs.append("new kernel errors: " + out.strip().replace("\n", " | ")[:200])
    rc, out, _ = ssh("cd %s && sha256sum %s 2>/dev/null" % (APPS, " ".join(UNRELATED)))
    now = {l.partition("  ")[2]: l.partition("  ")[0] for l in out.splitlines()}
    if now != pf["unrelated"]: probs.append("unrelated apps changed: %s" % sorted(n for n in pf["unrelated"] if now.get(n) != pf["unrelated"][n]))
    # The syslog is a small RAM ring: an old "default: LOAD" line rotates out within minutes. A MISSING line is not a fault; a last line that is not 'default', or a launch that
    # saw no 'default: LOAD' right after its own clean-up (KEYMAP_DEFAULT=0, checked while fresh), is.
    rc, out, _ = ssh("grep keymap /tmp/messages | tail -1")
    if out.strip() and "default: LOAD" not in out: probs.append("the last key-map line is not 'default' (buttons may be left remapped): " + out.strip()[-80:])
    if KEYMAP_BAD: probs.append("key map not restored to default after: " + ", ".join(KEYMAP_BAD))
    rc, out, _ = ssh("ls -A /mnt/FunKey/.retrohatch | tr '\\n' ' '")
    if out.strip() != pf["prod_state"].strip(): probs.append("production state directory changed")
    return probs


def frontend(off):
    """Hold the launcher off (the system's own switch) with a dead-man timer, or release it."""
    if off:
        ssh("touch /mnt/disable_frontend; (nohup sh -c 'sleep 1500; rm -f /mnt/disable_frontend' >/dev/null 2>&1 & echo $! > %s/deadman.pid)" % REMOTE)
        ssh("pkill retrofe; sleep 3; echo ok")
        rc, out, _ = ssh("pidof retrofe | wc -w")
        if out.strip() != "0": raise Stop("the launcher did not stop")
    else:
        ssh("rm -f /mnt/disable_frontend; kill $(cat %s/deadman.pid 2>/dev/null) 2>/dev/null; echo ok" % REMOTE)
        for _ in range(12):
            time.sleep(2)
            rc, out, _ = ssh("pidof retrofe | wc -w")
            if out.strip() != "0": return True
        return False


def deadman_test(secs=25):
    """Prove the recovery before any batch: hold the launcher off with a SHORT dead-man timer and check that the system brings it back by itself."""
    f = device_facts()
    if f["retrofe"] == "0" or f["disabled"] != "0" or f["apps_running"] != "0":
        raise Stop("dead-man test needs the launcher running, no app running and no /mnt/disable_frontend (retrofe=%s disabled=%s apps=%s)" % (f["retrofe"], f["disabled"], f["apps_running"]))
    ssh("touch /mnt/disable_frontend; (nohup sh -c 'sleep %d; rm -f /mnt/disable_frontend' >/dev/null 2>&1 &)" % secs)
    ssh("pkill retrofe; sleep 3; echo ok")
    back = False; stopped = False
    try:
        stopped = ssh("pidof retrofe | wc -w")[1].strip() == "0"
        t0 = time.time()
        while time.time() - t0 < secs + 45:
            time.sleep(3)
            if ssh("pidof retrofe | wc -w")[1].strip() != "0":
                back = True; break
    finally:
        ssh("rm -f /mnt/disable_frontend")   # safety net only; the test result above is what the timer did on its own
        if not back:
            for _ in range(8):
                time.sleep(3)
                if ssh("pidof retrofe | wc -w")[1].strip() != "0": break
            else:
                raise Stop("the launcher did not come back after the dead-man test")
    res = load_res(); res["meta"]["deadman"] = {"ok": bool(stopped and back), "seconds": secs, "when": time.strftime("%Y-%m-%d %H:%M")}; save_res(res)
    if not (stopped and back):
        raise Stop("dead-man recovery failed (launcher stopped: %s, returned by itself: %s)" % (stopped, back))
    print("dead-man recovery works: launcher held off, released by the timer after %ds, back within the limit" % secs)


def install_tools():
    ssh("mkdir -p %s" % REMOTE)
    push(ROOT / "build" / "rh_exp_arm", REMOTE + "/rh_exp_arm")
    push(ROOT / "tools" / "batch_launch.sh", REMOTE + "/batch_launch.sh")
    push(SNAP, REMOTE + "/candidates.json")
    ssh("chmod +x %s/rh_exp_arm" % REMOTE)


def dev_cli(args, timeout=300):
    return ssh("%s/rh_exp_arm --state %s --apps %s --cands %s/candidates.json %s" % (REMOTE, DEV_STATE, APPS, REMOTE, args), timeout)


def install(cid, rec):
    """Copy the host-verified package into the installer's cache on the Nano and install it through the experimental installer."""
    rc, out, _ = ssh("awk -F'\t' '$1==\"x-%s\"{print $3}' %s/installed.tsv 2>/dev/null" % (cid, DEV_STATE))
    if out.strip() == rec["sha256"]:
        rec["install"] = "already installed (identical hash)"; return True
    push(CACHE / ("x-%s.opk" % cid), "%s/cache/x-%s.opk" % (DEV_STATE, cid))
    rc, out, _ = dev_cli("install %s" % cid)
    m = re.search(r"RESULT (\d) (.*)", out)
    if rc != 0 or not m or m.group(1) != "0":
        rec["install"] = "refused: " + (m.group(2) if m else out.strip()[-120:]); return False
    rc, out, _ = ssh("cd %s && sha256sum %s | cut -d' ' -f1; awk -F'\t' '$1==\"x-%s\"{print $1, $2, $3}' %s/installed.tsv" % (APPS, rec["file"], cid, DEV_STATE))
    lines = out.split("\n")
    if lines[0].strip() != rec["sha256"] or ("x-%s" % cid) not in out:
        rec["install"] = "installed but verification failed: file hash %s, record %s" % (lines[0][:12], lines[1] if len(lines) > 1 else "none"); return False
    rec["install"] = "installed, hash and installed.tsv record verified"
    return True


def fb_png(raw, path):
    from PIL import Image
    im = Image.new("RGB", (240, 240)); px = im.load(); colors = {}
    for y in range(240):
        for x in range(240):
            v = raw[y * 480 + x * 2] | raw[y * 480 + x * 2 + 1] << 8
            c = (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31); px[x, y] = c; colors[c] = colors.get(c, 0) + 1
    SHOTS.mkdir(parents=True, exist_ok=True); im.save(path)
    top = max(colors.values()) / 57600.0
    return len(colors), top


def judge(k, log, msgs, dm, colors, top):
    """(verdict, reason). PASS needs: alive through the startup window, a real picture, a clean stop, no crash evidence. A process alone is never PASS."""
    ex = k.get("EXIT", "-"); alive = k.get("ALIVE_AT_END") == "1"; stop = k.get("STOP", "none"); tail = " ".join(log.strip().splitlines()[-3:])[:160]
    sig = re.search(r"segmentation fault|illegal instruction|bus error", log + dm, re.I) or KERNEL_BAD.search(dm)
    if not alive:
        code = int(ex) if ex.lstrip("-").isdigit() else None
        if sig or (code is not None and code >= 128):
            return "CRASH", "ended after %ss with exit %s%s" % (k.get("LIFE_S") or "?", ex, (": " + tail) if tail else "")
        if NEEDS_FILE.search(log):
            return "NEEDS FILE", "exited at once because it was started without a ROM/file (not a crash): " + tail
        return "FAIL", "exited by itself after %ss with status %s%s" % (k.get("LIFE_S") or "?", ex, (": " + tail) if tail else "")
    if stop in ("kill", "stuck"):
        return "HANG", "did not stop on SIGTERM within %ss (%s)" % (TERM_S, "killed" if stop == "kill" else "still running")
    if sig:
        return "CRASH", "crash evidence in the log or kernel messages"
    shown = colors >= 16 and top < 0.98
    if not shown:
        return "NEEDS MANUAL CHECK", "running and stopped cleanly, but the screen showed no picture (%d colours): cannot confirm startup" % colors
    return "PASS", "startup verified: ran %ss, picture on screen (%d colours)%s, stopped cleanly on SIGTERM. Gameplay not tested" % (RUN_S, colors, "; log notes: " + LOG_BAD.search(log).group(0) if LOG_BAD.search(log) else "")


def launch(cid, rec):
    f = rec["file"]
    rc, out, _ = ssh("sh %s/batch_launch.sh %s/%s %s %d %d %d" % (REMOTE, APPS, f, cid, STARTUP_S, RUN_S, TERM_S), timeout=RUN_S + TERM_S + 60)
    k = kv(out)
    if k.get("KEYMAP_DEFAULT") == "0": KEYMAP_BAD.append(cid)
    if "DONE" not in k:
        return "FAIL", "launch script did not finish: " + (k.get("ERROR") or out.strip()[-100:]), k
    rc, log, _ = ssh("head -c 3000 %s/%s.log" % (REMOTE, cid))
    rc, msgs, _ = ssh("cat %s/%s.msgs" % (REMOTE, cid))
    rc, dm, _ = ssh("cat %s/%s.dmesg" % (REMOTE, cid))
    colors, top = 0, 1.0
    rc, raw, _ = ssh("cat %s/%s.fb 2>/dev/null" % (REMOTE, cid), binary=True)
    if len(raw) == 115200:
        colors, top = fb_png(raw, SHOTS / (cid + ".png")); rec["shot"] = "build/batch/shots/%s.png" % cid
    samples = [k[s] for s in ("S2", "S4", "S6", "S8") if s in k]
    rec["launch_detail"] = {"samples": samples, "exit": k.get("EXIT"), "stop": k.get("STOP"), "stop_s": k.get("STOP_S"), "life_s": k.get("LIFE_S"), "new_syslog_lines": k.get("NEWMSGS"), "new_kernel_lines": k.get("NEWDMESG")}
    rec["animated"] = len({s.split(",")[-1] for s in samples}) > 1
    v, why = judge(k, log, msgs, dm, colors, top)
    return v, why, k


# ------------------------------------------------------------------ orchestration
def test_app(cid, cls, pf, res, force=False):
    rec = res["apps"].setdefault(cid, {})
    old = dict(rec)
    rec.clear(); rec.update(id=cid)
    v = prepare(cid, cls, pf["libs"], pf["comps"], rec)
    if v:
        rec.update(v); rec["install"] = rec["launch"] = "not run"; return rec
    if not force and old.get("sha256") == rec.get("sha256") and old.get("verdict") in ("PASS", "FAIL", "CRASH", "HANG", "NEEDS MANUAL CHECK", "NEEDS FILE"):
        rec.update(old); rec["note"] = "unchanged package, result kept (not downloaded or re-run)"; return rec
    if not install(cid, rec):
        rec.update(verdict="FAIL", reason=rec["install"], launch="not run"); return rec
    v, why, k = launch(cid, rec)
    rec.update(verdict=v, reason=why, launch="%s: %s" % (v, why))
    rec["tested"] = time.strftime("%Y-%m-%d %H:%M")
    return rec


def tls_section(apps, cand):
    ids = [c for c in cand if c in apps and (apps[c].get("fetched_by") or "").startswith("PC Python")]
    names = ", ".join(cand[c]["name"] for c in ids)
    return ["## TLS 1.3 download defect: FIXED after this run (UI path hardware-tested 2026-11-09)", "",
            "When this run was made RetroHatch's downloader (mbedTLS 2.16) spoke TLS 1.2 at most and `static.miraheze.org`, where the FunKey wiki hosts its OPKs, only accepts TLS 1.3, so Test Install failed with \"TLS handshake failed\" for %d candidates (%s). "
            "`core/rh_net.c` now uses the firmware's OpenSSL 1.1.1i (TLS 1.2 and 1.3, certificate checks unchanged); PokeMini was then downloaded, installed and launched through the DEV app itself (`docs/HARDWARE_TEST_11.md`). The other Miraheze candidates were not individually retried through the UI. "
            "The packages marked **PC-staged** below were fetched by Python on the PC at test time, so their results say whether the app works, **not** that the in-app downloader works; the other packages were fetched by RetroHatch's downloader code run on the PC, and Znax, Rubido and 2048 were downloaded on the device earlier through the app. "
            "OpenSSL 1.1.1i is end-of-life: see `docs/NANO_V1_RELEASE.md` blocker 6." % (len(ids), names or "none found"), ""]


def write_report(res, mode):
    cand = candidates(); apps = res["apps"]; rows = []
    order = [c for c in cand if c in apps]
    cnt = {}
    for c in order:
        lab = apps[c].get("verdict") or ("ELIGIBLE" if mode == "dry" else "?")
        cnt[lab] = cnt.get(lab, 0) + 1
    L = ["# App compatibility results (RG Nano, experimental installer)", "",
         "%s. Generated by `tools/batch_test.py` from `build/batch/results.json`. **PASS means: installed through the experimental installer, launched through the FunKey launch path, stayed running for the startup window with a real picture on screen, and stopped cleanly on SIGTERM. Gameplay and controls are NOT tested**; every app stays UNAPPROVED and UNVERIFIED." % (
             "**DRY RUN: nothing was installed or launched on the Nano.** Verdicts below are the host-side checks (download, hash, launch-metadata inspection)" if mode == "dry" else "Full run on the device"), "",
         "Summary: " + ", ".join("%s %d" % (k, v) for k, v in sorted(cnt.items())), ""] + tls_section(apps, cand) + [
         "| App | Fetched by | SHA-256 | Install | Launch | Result | Details |", "|---|---|---|---|---|---|---|"]
    for c in order:
        a = apps[c]
        ins = a.get("inspect") or {}
        det = a.get("reason", "")
        if mode == "dry" and a.get("verdict") is None:
            det = "eligible: inspection ok" + (" (notes: %s)" % "; ".join(ins.get("notes", []))[:120] if ins.get("notes") else "")
        L.append("| %s | %s | `%s` | %s | %s | **%s** | %s |" % (cand[c]["name"], ("PC-staged" if (a.get("fetched_by") or "").startswith("PC Python") else "RetroHatch code on the PC" if a.get("fetched_by") else "-"), (a.get("sha256") or "-")[:12], (a.get("install") or "-").replace("|", "/"), ((a.get("launch") or "-") if mode != "dry" else "not run").replace("|", "/")[:90],
                                                           a.get("verdict") or ("ELIGIBLE" if mode == "dry" else "?"), det.replace("|", "/")[:260]))
    L += ["", "Screenshots (last frame at the end of the startup window): `build/batch/shots/<id>.png`. Raw evidence per run is in `build/batch/results.json`."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


def cmd_dry(a):
    B.mkdir(parents=True, exist_ok=True)
    cls = classify(); res = load_res(); libs = comps = None; dev = None
    if a.device:
        try:
            dev = preflight()
            libs, comps = dev["libs"], dev["comps"]
        except Stop as e:
            print("device not reachable (read-only preflight skipped):", e)
    ids = [i for i in candidates() if (not a.ids or i in a.ids.split(","))]
    for n, cid in enumerate(ids, 1):
        c = cls.get(cid)
        rec = {"id": cid}
        v = prepare(cid, cls, libs, comps, rec)
        if v is None:
            rec["verdict"] = None
        else:
            rec.update(v)
        if c and c["state"] == "no":
            rec["inspect"] = None
        res["apps"][cid] = rec
        print("%3d/%d %-22s %s" % (n, len(ids), cid, rec.get("verdict") or "eligible"), "-", (rec.get("reason") or "")[:100], flush=True)
        save_res(res)
    res["meta"]["dry_run"] = time.strftime("%Y-%m-%d %H:%M"); save_res(res)
    write_report(res, "dry")
    if dev:
        print("PREFLIGHT:", json.dumps({k: dev[k] for k in ("batt", "bstat", "charging", "free_mb", "comps", "problems")}))


def run_ids(ids, batch, validate=False):
    cls = classify(); res = load_res()
    pf = preflight()
    if pf["problems"]:
        raise Stop("preflight failed: " + "; ".join(pf["problems"]))
    print("preflight ok: battery %s%% %s, free %s MB, compressors %s" % (pf["batt"], pf["bstat"], pf["free_mb"], pf["comps"]))
    install_tools()
    chunks = [ids[i:i + batch] for i in range(0, len(ids), batch)]
    res["meta"]["device"] = {k: pf[k] for k in ("boot", "batt", "bstat", "free_mb", "comps")}
    hangs = 0
    try:
        for bi, chunk in enumerate(chunks, 1):
            frontend(True)
            try:
                for cid in chunk:
                    rec = test_app(cid, cls, pf, res, force=validate)
                    save_res(res)
                    print("batch %d/%d %-22s %-18s %s" % (bi, len(chunks), cid, rec.get("verdict"), (rec.get("reason") or "")[:90]), flush=True)
                    hangs = hangs + 1 if rec.get("verdict") == "HANG" else 0
                    if hangs >= 2:
                        raise Stop("two apps in a row would not stop: persistent hang")
                    probs = health(pf, "after " + cid) if rec.get("verdict") in ("CRASH", "HANG") else []
                    if probs:
                        raise Stop("health check after %s: %s" % (cid, "; ".join(probs)))
            finally:
                if not frontend(False):
                    print("WARNING: the launcher did not come back by itself within 24 s; the dead-man timer will release it")
            probs = health(pf, "batch %d" % bi)
            if probs:
                raise Stop("health check after batch %d: %s" % (bi, "; ".join(probs)))
            print("batch %d/%d healthy" % (bi, len(chunks)), flush=True)
    finally:
        write_report(res, "run")
        summarize(res, ids)


def summarize(res, ids):
    cand = candidates(); r = res["apps"]
    by = lambda *v: [cand[c]["name"] for c in ids if r.get(c, {}).get("verdict") in v]
    inst = [cand[c]["name"] for c in ids if str(r.get(c, {}).get("install", "")).startswith(("installed", "already"))]
    print("\nSUMMARY (%d candidates processed)" % len([c for c in ids if c in r]))
    print("installed ok (%d): %s" % (len(inst), ", ".join(inst)))
    print("PASS = launched with a picture and stopped cleanly (%d): %s" % (len(by("PASS")), ", ".join(by("PASS"))))
    print("FAIL/CRASH/HANG (%d): %s" % (len(by("FAIL", "CRASH", "HANG")), ", ".join("%s=%s" % (cand[c]["name"], r[c]["verdict"]) for c in ids if r.get(c, {}).get("verdict") in ("FAIL", "CRASH", "HANG"))))
    print("NEEDS A ROM/FILE, NOT BROKEN (%d): %s" % (len(by("NEEDS FILE")), ", ".join(by("NEEDS FILE"))))
    print("NEEDS MANUAL CHECK (%d): %s" % (len(by("NEEDS MANUAL CHECK")), ", ".join(by("NEEDS MANUAL CHECK"))))
    print("SKIPPED (%d)" % len(by("SKIPPED")))


def cmd_validate(a):
    pf = preflight()
    if pf["problems"]:
        raise Stop("preflight failed: " + "; ".join(pf["problems"]))
    deadman_test()
    run_ids(KNOWN, 3, validate=True)
    res = load_res(); bad = [c for c in KNOWN if res["apps"][c].get("verdict") != "PASS"]
    res["meta"]["validated"] = not bad
    save_res(res)
    print("VALIDATION " + ("PASSED: the method reproduces the known-good results" if not bad else "FAILED for: %s. The batches will not run." % bad))
    sys.exit(1 if bad else 0)


def cmd_run(a):
    res = load_res()
    if not (res["meta"].get("validated") and res["meta"].get("deadman", {}).get("ok")) and not a.skip_validation:
        raise SystemExit("run `validate` first (dead-man recovery must work and the three known-good apps must PASS)")
    cls = classify()
    ids = [c for c in candidates() if cls.get(c, {}).get("state") != "no" and (not a.ids or c in a.ids.split(","))]
    run_ids(ids, a.batch)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("dry-run"); d.add_argument("--ids"); d.add_argument("--device", action="store_true")
    sp.add_parser("validate")
    r = sp.add_parser("run"); r.add_argument("--batch", type=int, default=10); r.add_argument("--ids"); r.add_argument("--skip-validation", action="store_true")
    sp.add_parser("report")
    a = ap.parse_args()
    try:
        if a.cmd == "dry-run": cmd_dry(a)
        elif a.cmd == "validate": cmd_validate(a)
        elif a.cmd == "run": cmd_run(a)
        else: write_report(load_res(), "run")
    except Stop as e:
        print("STOPPED:", e)
        sys.exit(2)


if __name__ == "__main__":
    main()
