#!/usr/bin/env python3
"""Build the RH Probe test OPK (MIT, code we own) and its DEV-only catalog entry. Run in WSL.
   -> build/probe/rhprobe_<version>.opk  and  dev/catalog/apps/rhprobe.json
The OPK is NOT shipped inside RetroHatchDev.opk: it is placed in the DEV cache by hand."""
import hashlib, json, os, shutil, subprocess, tempfile
from PIL import Image
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSIONS = ["1.0.0", "1.1.0"]   # the DEV catalog advertises the last one; 1.0.0 stays reproducible for the installed record
COMMENT = {"1.1.0": "RetroHatch test package v1.1.0"}   # the only content difference: desktop Comment
DEST = "rhprobe_funkey-s.opk"
def build(version):
    stage = tempfile.mkdtemp()
    for f in ("LICENSE-MIT.txt", "run.sh", "rhprobe.funkey-s.desktop"):
        shutil.copy(os.path.join(ROOT, "dev", "probe", f), stage)
    if version in COMMENT:
        dp = os.path.join(stage, "rhprobe.funkey-s.desktop"); t = open(dp).read().replace("Comment=RetroHatch test package", "Comment=" + COMMENT[version])
        open(dp, "w", newline="\n").write(t)
    os.chmod(os.path.join(stage, "run.sh"), 0o755)
    # icon: Lucide package, green on the app background, 32x32
    pk = Image.open(os.path.join(ROOT, "ui", "assets", "ic_package_28.png")).convert("RGBA")
    bg = Image.new("RGBA", (32, 32), (0x27, 0x27, 0x21, 255))
    tint = Image.new("RGBA", pk.size, (0x82, 0xA7, 0x79, 255)); tint.putalpha(pk.getchannel("A"))
    bg.alpha_composite(tint, (2, 2)); bg.save(os.path.join(stage, "rhprobe.png"))
    out = os.path.join(ROOT, "build", "probe"); os.makedirs(out, exist_ok=True)
    opk = os.path.join(out, "rhprobe_%s.opk" % version)
    if os.path.exists(opk): os.remove(opk)
    subprocess.check_call(["mksquashfs", stage, opk, "-all-root", "-noappend", "-no-xattrs", "-comp", "gzip",
                           "-mkfs-time", "0", "-all-time", "0"], stdout=subprocess.DEVNULL)
    shutil.rmtree(stage)

    data = open(opk, "rb").read(); sha = hashlib.sha256(data).hexdigest()
    open(opk + ".sha256", "w").write("%s  %s\n" % (sha, os.path.basename(opk)))
    print(opk, len(data), sha)
    return len(data), sha

last = None
for v in VERSIONS:
    last = (v,) + build(v)
version, size, sha = last
entry = {"schema": 1, "id": "rhprobe", "name": "RH Probe (test)",
         "description": "TEST ENTRY - DEV catalog only. Not a real app.",
         "developer": "traceroute87", "source": "https://example.invalid/rhprobe", "license": "MIT", "category": "application",
         "artifacts": [{"device": "rg-nano", "firmware": "funkeyos-drum78", "format": "opk", "status": "available",
                        "version": version, "size": size, "sha256": sha, "install": {"dest_name": DEST},
                        "compatibility": {"level": "verified"}}]}
json.dump(entry, open(os.path.join(ROOT, "dev", "catalog", "apps", "rhprobe.json"), "w"), indent=1)
