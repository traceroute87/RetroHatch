#!/usr/bin/env python3
"""Static launch-metadata inspection of an OPK (squashfs) BEFORE anything is installed or run. Nothing is mounted or executed.

  python3 tools/opk_inspect.py FILE.opk [--libs lib1,lib2,...] [--comp 1,4]      (needs `unsquashfs`; run in WSL)
  -> one JSON object: {"verdict": "ok" | "skip" | "manual", "reasons": [...], "notes": [...], "desktop": {...}, "exec": "...", "files": N}

skip   = unsafe, suspicious or incompatible: the batch tool never installs or launches it
manual = nothing wrong found but something cannot be judged from the file (reported, not run unattended)
Checks: device nodes / setuid / absolute links to system paths in the image; a FunKey desktop entry whose Exec target exists; the launch scripts
(Exec target and *.sh) for commands that change the system (mount, dd, flashing, module loading, reboot, writes to /etc /usr /dev/mmcblk ..., network
tools, killing system daemons, keymap/frontend changes); ELF files (ARM 32-bit EABI5, the loader the program asks for must be the device's musl one or
shipped in the package, needed libraries present on the device or in the package); squashfs compression the device kernel supports.
`libs` = library file names present on the device (default: not checked), `comp` = squashfs compression ids the device kernel supports (default 1 = gzip)."""
import json, os, re, shutil, struct, subprocess, sys, tempfile

MUSL = "/lib/ld-musl-armhf.so.1"
SYSTEM_LINK = re.compile(r"^/(etc|dev|proc|sys|boot|mnt|root|sbin|bin|usr/(s?bin|local/s?bin))(/|$)")
# (pattern, why). Matched per non-comment line of a launch script.
STRONG = [
    (r"(^|[\s;&|(`])(mount|umount)(\s|$)", "mounts or unmounts a filesystem"),
    (r"(^|[\s;&|(`])(dd|mkfs(\.\w+)?|fdisk|sfdisk|parted|losetup|flashcp|flash_erase|nandwrite|fw_setenv|mkswap|swapon|swapoff)(\s|$)", "writes devices, partitions or firmware settings"),
    (r"(^|[\s;&|(`])(insmod|modprobe|rmmod|depmod)(\s|$)", "loads or removes kernel modules"),
    (r"(^|[\s;&|(`])(reboot|poweroff|halt|shutdown)(\s|$)|(^|[\s;&|(`])init\s+[0-6](\s|$)", "reboots or powers off the console"),
    (r"/dev/(mmcblk\d*|mtd\w*|sd[a-z]\d*|mem|kmem|ram\d*)", "touches a storage or memory device"),
    (r"(^|[\s;&|(`])(rm|mv|cp|ln|chmod|chown|tee|touch|mkdir|sed\s+-i|install)\b[^#\n]*\s/(etc|usr|bin|sbin|lib|boot|proc|sys|dev|opt)(/|\s|$)", "changes system directories"),
    (r">>?\s*/(etc|usr|bin|sbin|lib|boot|proc|sys|opt)(/|\s|$)", "writes into system directories"),
    (r"rm\s+(-\w+\s+)*/((mnt|home|root)?/?\*?)(\s|$)", "deletes from the filesystem root"),
    (r"/mnt/(instant_play|last_opk|disable_frontend|prevent_launcher|FunKey/\.last_mapping)", "touches launcher or firmware flag files"),
    (r"(^|[\s;&|(`])(wget|curl|nc|ncat|netcat|telnet|ssh|scp|ftp|tftp|ftpget)(\s|$)", "uses a network download or remote tool"),
    (r"(^|[\s;&|(`])(base64|xxd\s+-r|openssl\s+enc)(\s|$)|\beval\b", "decodes or evals hidden commands"),
    (r"(pkill|killall|kill\s+-9)\s+\S*(fkgpiod|retrofe|gmenu2x|dropbear|init|wpa_supplicant|udhcpc|frontend|syslogd)", "kills system daemons"),
    (r"fkgpiod|/etc/fkgpiod", "changes the button daemon or key map"),
    (r"(^|[\s;&|(`])keymap(\s|$)", "runs the console key-map command"),
    (r"(^|[\s;&|(`])frontend\s+(set|init)|disable_frontend|prevent_launcher", "changes the launcher"),
    (r"/mnt/Applications|/mnt/Settings|\.retrohatch", "writes to the application folders or RetroHatch state"),
    (r"(^|[\s;&|(`])(passwd|adduser|useradd|su|sudo|chroot)(\s|$)", "changes users or privileges"),
]
PATHY = {"touches a storage or memory device", "changes system directories", "writes into system directories", "deletes from the filesystem root",
         "writes to the application folders or RetroHatch state", "changes the button daemon or key map", "changes the launcher", "touches launcher or firmware flag files"}
STRONG = [(re.compile(p), w) for p, w in STRONG]
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
KEYMAP_OK = re.compile(r"^\s*(#.*|CLEAR|UNMAP\s+\S+|MAP\s+\S+\s+TO\s+(KEY|COMMAND)\s*.*|)\s*$")


def comp_id(path):
    with open(path, "rb") as f:
        h = f.read(30)
    if h[:4] != b"hsqs":
        return None
    return struct.unpack_from("<H", h, 20)[0]


def elf_info(path):
    """None if not an ELF; else dict(arm, class32, eabi5, hardfloat, interp, needed)."""
    with open(path, "rb") as f:
        h = f.read(64)
        if h[:4] != b"\x7fELF":
            return None
        r = {"class32": h[4] == 1, "le": h[5] == 1}
        if not (r["class32"] and r["le"]):
            r.update(arm=False, eabi5=False, hardfloat=False, interp="", needed=[]); return r
        etype, mach, _, _, phoff, shoff, flags, _, phentsize, phnum = struct.unpack_from("<HHIIIIIHHH", h, 16)[0:10]
        r["arm"] = mach == 40
        r["eabi5"] = (flags >> 24) == 5
        r["hardfloat"] = bool(flags & 0x400)
        r["interp"], r["needed"] = "", []
        try:
            dyn = None
            for i in range(min(phnum, 64)):
                f.seek(phoff + i * phentsize)
                p_type, p_off, p_vaddr, _, p_filesz = struct.unpack("<IIIII", f.read(20))
                if p_type == 3 and p_filesz < 256:        # PT_INTERP
                    f.seek(p_off); r["interp"] = f.read(p_filesz).split(b"\0")[0].decode("latin-1")
                if p_type == 2:                           # PT_DYNAMIC
                    dyn = (p_off, p_filesz)
            if dyn and dyn[1] < (1 << 20):
                f.seek(dyn[0]); d = f.read(dyn[1]); ents = [struct.unpack_from("<II", d, o) for o in range(0, len(d) - 7, 8)]
                strtab = next((v for t, v in ents if t == 5), None)
                if strtab is not None:   # DT_STRTAB is a vaddr; map it through the program headers
                    off = None
                    for i in range(min(phnum, 64)):
                        f.seek(phoff + i * phentsize)
                        p_type, p_off, p_vaddr, _, p_filesz = struct.unpack("<IIIII", f.read(20))
                        if p_type == 1 and p_vaddr <= strtab < p_vaddr + p_filesz:
                            off = strtab - p_vaddr + p_off
                    if off is not None:
                        for t, v in ents:
                            if t == 1:
                                f.seek(off + v); r["needed"].append(f.read(128).split(b"\0")[0].decode("latin-1"))
        except (struct.error, OSError):
            pass
        return r


def scan_script(path, rel):
    hits = []
    try:
        text = open(path, "r", encoding="latin-1").read(262144)
    except OSError:
        return hits
    for n, line in enumerate(text.splitlines(), 1):
        code = line.split("#", 1)[0] if not line.lstrip().startswith("#!") else ""
        if not code.strip():
            continue
        blank = QUOTED.sub('""', code)   # words inside quotes (echo messages) are text, not commands; paths and redirects are judged on the raw line
        for rx, why in STRONG:
            if rx.search(code if why in PATHY else blank):
                hits.append(f"{rel}:{n}: {why}: {line.strip()[:100]}")
                break
    return hits


def parse_desktop(path):
    d = {}
    for line in open(path, "r", encoding="utf-8", errors="replace").read(65536).splitlines():
        if "=" in line and not line.startswith("#") and not line.startswith("["):
            k, v = line.split("=", 1); d.setdefault(k.strip(), v.strip())
    return d


def inspect_tree(root, libs=None, comps=(1,), comp=None, listing=None):
    """root = an extracted OPK. listing = optional [(mode_char, mode_int, name)] from unsquashfs -ll (types and setuid bits survive only there)."""
    out = {"verdict": "ok", "reasons": [], "notes": [], "desktop": {}, "exec": "", "files": 0}
    skip, manual, notes = out["reasons"], [], out["notes"]
    if comp is not None and comp not in comps:
        skip.append(f"squashfs compression {comp} is not supported by the device kernel")
    for t, mode, name in listing or []:
        if t in "cbps":
            skip.append(f"special file in the image: {name}")
        if mode & 0o6000:
            skip.append(f"setuid/setgid file in the image: {name}")
    files = []
    for dp, dns, fns in os.walk(root):
        for n in fns + dns:
            p = os.path.join(dp, n); rel = os.path.relpath(p, root)
            if os.path.islink(p):
                tgt = os.readlink(p)
                if tgt.startswith("/") and SYSTEM_LINK.match(tgt):
                    skip.append(f"link {rel} points to the system path {tgt}")
                elif not tgt.startswith("/") and not os.path.realpath(p).startswith(os.path.realpath(root)):
                    skip.append(f"link {rel} leaves the package ({tgt})")
            elif os.path.isfile(p):
                files.append((p, rel))
    out["files"] = len(files)
    desk = sorted(rel for p, rel in files if rel.endswith(".funkey-s.desktop") and os.sep not in rel)
    if not desk:
        skip.append("no FunKey desktop entry (*.funkey-s.desktop): the Apps drawer would not list it")
        out["verdict"] = "skip"; return out
    d = parse_desktop(os.path.join(root, desk[0])); out["desktop"] = {k: d[k] for k in ("Name", "Exec", "Categories", "Terminal", "FK-Keymap") if k in d}
    exe = (d.get("Exec") or "").split()
    ex = exe[0] if exe else ""
    out["exec"] = ex
    tgt = os.path.normpath(os.path.join(root, ex)) if ex and not ex.startswith("/") else ""
    if not ex:
        skip.append("desktop entry has no Exec")
    elif ex.startswith("/"):
        skip.append(f"Exec runs a program outside the package: {ex}")
    elif not tgt.startswith(os.path.realpath(root)) and not os.path.abspath(tgt).startswith(os.path.abspath(root)):
        skip.append(f"Exec escapes the package: {ex}")
    elif not os.path.isfile(tgt):
        skip.append(f"Exec target {ex} is not in the package")
    km = d.get("FK-Keymap")
    if km:
        kp = os.path.join(root, km.lstrip("/")) if not km.startswith("/opk/") else os.path.join(root, km[5:])
        if not os.path.isfile(kp):
            notes.append(f"FK-Keymap {km} not found in the package")
        else:
            bad = [l for l in open(kp, encoding="latin-1").read(65536).splitlines() if not KEYMAP_OK.match(l)]
            cmds = [l.strip() for l in open(kp, encoding="latin-1").read(65536).splitlines() if re.search(r"TO\s+COMMAND", l)]
            if bad:
                skip.append(f"key map has lines the button daemon may not understand: {bad[0][:60]}")
            if cmds:
                skip.append(f"key map runs console commands: {cmds[0][:60]}")
    scripts = [(p, rel) for p, rel in files if rel.endswith(".sh") or (tgt and os.path.abspath(p) == os.path.abspath(tgt))]
    for p, rel in scripts:
        with open(p, "rb") as f:
            head = f.read(4)
        if head[:4] == b"\x7fELF":
            continue
        skip += scan_script(p, rel)
    elfs = 0
    for p, rel in files:
        e = elf_info(p)
        if not e:
            continue
        elfs += 1
        primary = bool(tgt and os.path.abspath(p) == os.path.abspath(tgt)) or (os.access(p, os.X_OK) and ".so" not in os.path.basename(p))   # the Exec target or any other program
        if not (e["arm"] and e["class32"] and e["le"]):
            (skip if primary else notes).append(f"{rel} is not a 32-bit ARM program" if primary else f"{rel}: not 32-bit ARM")
            continue
        if not e["eabi5"]:
            (skip if primary else notes).append(f"{rel}: not EABI5")
        if not e["hardfloat"] and primary:
            notes.append(f"{rel}: soft-float build")
        itp = e["interp"]
        if itp and itp != MUSL and not os.path.exists(os.path.join(root, itp.lstrip("/"))):
            (skip if primary else notes).append(f"{rel} needs the loader {itp}, which the device does not have")
        if primary and libs is not None:
            have = set(libs) | {n for dp, dns, fns in os.walk(root) for n in fns + dns}
            miss = [n for n in e["needed"] if n not in have and not n.startswith("ld-")]
            if miss:
                skip.append(f"needs libraries the device and package lack: {', '.join(miss[:4])}")
    if not elfs and not any(rel.endswith(".sh") for p, rel in files) and ex:
        manual.append("no program or script found to judge")
    out["verdict"] = "skip" if skip else "manual" if manual else "ok"
    out["reasons"] = skip + manual
    return out


def inspect_opk(opk, libs=None, comps=(1,)):
    c = comp_id(opk)
    if c is None:
        return {"verdict": "skip", "reasons": ["not a squashfs image"], "notes": [], "desktop": {}, "exec": "", "files": 0}
    tmp = tempfile.mkdtemp(prefix="rhinsp-")
    try:
        ll = subprocess.run(["unsquashfs", "-ll", opk], capture_output=True, text=True, timeout=120)
        listing = []
        total = 0
        for line in ll.stdout.splitlines():
            m = re.match(r"^([-dlcbps])([-rwxsStT]{9})\s+\S+\s+(\d+(?:,\s*\d+)?)\s+\S+\s+\S+\s+(.*)$", line)
            if m:
                mode = 0
                s = m.group(2)
                if s[2] in "sS": mode |= 0o4000
                if s[5] in "sS": mode |= 0o2000
                listing.append((m.group(1), mode, m.group(4))); total += int(m.group(3).split(",")[0])
        if ll.returncode or total > (400 << 20) or len(listing) > 20000:
            return {"verdict": "skip", "reasons": ["image unreadable or too large to inspect (%d MB, %d entries)" % (total >> 20, len(listing))], "notes": [], "desktop": {}, "exec": "", "files": len(listing)}
        r = subprocess.run(["unsquashfs", "-no-xattrs", "-f", "-d", os.path.join(tmp, "x"), opk], capture_output=True, text=True, timeout=300)
        if not os.path.isdir(os.path.join(tmp, "x")):
            return {"verdict": "skip", "reasons": ["image could not be unpacked: " + r.stderr.strip()[:100]], "notes": [], "desktop": {}, "exec": "", "files": 0}
        return inspect_tree(os.path.join(tmp, "x"), libs=libs, comps=comps, comp=c, listing=listing)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    libs = comps = None
    if "--libs" in a: i = a.index("--libs"); libs = [x for x in a[i + 1].split(",") if x]; del a[i:i + 2]
    if "--comp" in a: i = a.index("--comp"); comps = tuple(int(x) for x in a[i + 1].split(",")); del a[i:i + 2]
    print(json.dumps(inspect_opk(a[0], libs=libs, comps=comps or (1,))))
