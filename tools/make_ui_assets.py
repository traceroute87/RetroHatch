#!/usr/bin/env python3
"""Bake Nano UI assets into ui/assets (run in WSL: needs Pillow + resvg).
Icons: Lucide (ISC) paths, rasterised once at final size, white alpha masks
that the UI tints at draw time. Header/logo are pre-scaled so the device never
scales at runtime."""
import os, subprocess, tempfile, shutil
from PIL import Image, ImageEnhance

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "ui", "assets")
RESVG = os.path.expanduser("~/tools/resvg")
os.makedirs(OUT, exist_ok=True)

# official Lucide SVGs (lucide-static 0.468.0, ISC): fetched once into ~/lucide-official
LUCIDE = os.path.expanduser("~/lucide-official")
ICONS = {  # asset name: (lucide icon, [sizes])
 "chevron": ("chevron-right", [16]), "search": ("search", [20]), "grid": ("layout-grid", [20, 48]),
 "refresh": ("refresh-cw", [20, 48]), "gear": ("settings", [20]), "lock": ("lock", [24]),
 "download": ("download", [20]), "database": ("database", [20]), "wifi": ("wifi", [20]),
 "info": ("info", [20]), "trash": ("trash-2", [20]), "check": ("check", [20, 48]), "alert": ("triangle-alert", [48]), "phone": ("smartphone", [20]), "package": ("package", [28]),
}
tmp = tempfile.mkdtemp()
for name, (icon, sizes) in ICONS.items():
    svg = open(os.path.join(LUCIDE, icon + ".svg")).read().replace("currentColor", "#fff")
    p = os.path.join(tmp, name + ".svg"); open(p, "w").write(svg)
    for sz in sizes:
        subprocess.check_call([RESVG, "-w", str(sz), "-h", str(sz), p, os.path.join(OUT, "ic_%s_%d.png" % (name, sz))])
shutil.rmtree(tmp)

# header: the identity artwork (Header2, same illustration as the home hero) scaled to 240 wide, a 32px band through sun glow,
# mountains and tree edges, darkened in the centre so cream titles stay readable (was the pixel-art Header.png, which matched nothing else)
def darken(im, lo, width):
    px = im.load(); w, h = im.size
    for x in range(w):
        d = abs(x - w / 2) / (w / 2)               # 0 centre .. 1 edge
        f = lo if d < width else lo + (1 - lo) * min(1, (d - width) / 0.25)
        for y in range(h):
            r, g, b = px[x, y][:3]; px[x, y] = (int(r * f), int(g * f), int(b * f))
    return im
hdr = Image.open(os.path.join(ROOT, "Header2.png")).convert("RGB").resize((240, 240), Image.LANCZOS)
HDR_TOP = 70
darken(hdr.crop((0, HDR_TOP, 240, HDR_TOP + 32)), 0.30, 0.45).save(os.path.join(OUT, "header.png"))

# home hero: Header2 (square) scaled to 240 wide, 114px band through sun + mountains + forest, slightly dimmed
h2 = Image.open(os.path.join(ROOT, "Header2.png")).convert("RGB")
h2 = h2.resize((240, round(h2.height * 240 / h2.width)), Image.LANCZOS)
ImageEnhance.Brightness(h2.crop((0, 22, 240, 22 + 121))).enhance(0.8).save(os.path.join(OUT, "home_bg.png"))

# logo: square, aspect kept, no crop
Image.open(os.path.join(ROOT, "Retro_Hatch.png")).convert("RGBA").resize((120, 120), Image.LANCZOS).save(os.path.join(OUT, "logo.png"))

# empty-state mark: Retro_Hatch2 (logo without wordmark), trimmed to its artwork, centred on a square, 56x56
m2 = Image.open(os.path.join(ROOT, "Retro_Hatch2.png")).convert("RGBA")
m2 = m2.crop(m2.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox())
side = max(m2.size); msq = Image.new("RGBA", (side, side), (0, 0, 0, 0)); msq.paste(m2, ((side - m2.width) // 2, (side - m2.height) // 2))
msq.resize((56, 56), Image.LANCZOS).save(os.path.join(OUT, "mark.png"))

# launcher icon: Retro_Hatch2 (simplified mark), trimmed to its artwork, centred on a square, 32x32 + light sharpen
ic2 = Image.open(os.path.join(ROOT, "Retro_Hatch2.png")).convert("RGBA")
ic2 = ic2.crop(ic2.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox())
side = max(ic2.size); sq = Image.new("RGBA", (side, side), (0, 0, 0, 0)); sq.paste(ic2, ((side - ic2.width) // 2, (side - ic2.height) // 2))
from PIL import ImageFilter
sq.resize((32, 32), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0)).save(os.path.join(ROOT, "ui", "retrohatch.png"))

# DEV launcher icon: same mark with a solid error-red "DEV" band so it can never be mistaken for production
from PIL import ImageDraw, ImageFont
dev = Image.open(os.path.join(ROOT, "ui", "retrohatch.png")).convert("RGBA")
dr = ImageDraw.Draw(dev); dr.rectangle((0, 21, 31, 31), fill=(0xE8, 0x75, 0x55, 255))
fnt = ImageFont.load_default(size=9); tw = dr.textlength("DEV", font=fnt)
dr.text(((32 - tw) / 2, 21), "DEV", font=fnt, fill=(0x17, 0x1B, 0x19, 255))
dev.save(os.path.join(ROOT, "ui", "retrohatchdev.png"))

# fonts: 16px Unifont (body) + Kode Mono SemiBold 15 (titles); OFL notice kept. They are already committed in ui/assets
# (originally copied from TaraFi's assets/). Set RH_FONT_SRC=<dir> to refresh them from another copy of those files.
T = os.environ.get("RH_FONT_SRC", OUT)
for f in ("tarafi16.fnt", "15-KodeMono-SemiBold.fnt", "OFL-KodeMono.txt"):
    if os.path.abspath(os.path.join(T, f)) != os.path.abspath(os.path.join(OUT, f)):
        shutil.copy(os.path.join(T, f), os.path.join(OUT, f))
print("ok", sorted(os.listdir(OUT)))
