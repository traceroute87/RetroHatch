#!/usr/bin/env python3
"""Build the Android adaptive launcher icon from the ORIGINAL RetroHatch artwork (nothing is redrawn):
  foreground = Retro_Hatch2.png (the egg / handheld / nest mark on transparency), trimmed to its content and placed inside the adaptive safe zone
  background = Header2.png (the sunset forest), full bleed
Writes res/mipmap-*dpi/ic_launcher_foreground.png, ic_launcher_background.png and a flattened legacy ic_launcher.png, plus
build/launcher-preview.png (the icon under circle / squircle / rounded-square masks) for a visual check.
    python android/tools/make_launcher_icon.py"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "android" / "app" / "src" / "main" / "res"
DPI = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
FILL = 0.64          # the mark's longest side as a share of the 108 dp layer. Safe zone = 66 dp circle (61%); launchers mask to ~72 dp (67%).


def layers(px):
    mark = Image.open(ROOT / "Retro_Hatch2.png").convert("RGBA")
    mark = mark.crop(mark.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
    k = FILL * px / max(mark.size)
    mark = mark.resize((round(mark.width * k), round(mark.height * k)), Image.LANCZOS)
    fg = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    fg.alpha_composite(mark, ((px - mark.width) // 2, (px - mark.height) // 2))
    bg = Image.open(ROOT / "Header2.png").convert("RGB").resize((px, px), Image.LANCZOS)
    return fg, bg


def mask(shape, px):
    m = Image.new("L", (px * 4, px * 4), 0); d = ImageDraw.Draw(m); s = px * 4
    inset = s * (1 - 72 / 108) / 2                      # the visible window of an adaptive icon is the centre 72 dp
    box = [inset, inset, s - inset, s - inset]
    if shape == "circle": d.ellipse(box, fill=255)
    elif shape == "squircle": d.rounded_rectangle(box, radius=(s - 2 * inset) * 0.36, fill=255)
    else: d.rounded_rectangle(box, radius=(s - 2 * inset) * 0.16, fill=255)
    return m.resize((px, px), Image.LANCZOS)


def main():
    for name, scale in DPI.items():
        px = round(108 * scale)
        fg, bg = layers(px)
        out = RES / f"mipmap-{name}"; out.mkdir(parents=True, exist_ok=True)
        fg.save(out / "ic_launcher_foreground.png", optimize=True)
        bg.save(out / "ic_launcher_background.png", optimize=True)
        legacy = round(48 * scale)                         # pre-adaptive launchers: the same artwork, flattened, cropped to the visible 72/108 window
        flat = bg.copy(); flat.paste(fg, (0, 0), fg)
        c = round(px * (1 - 72 / 108) / 2)
        flat.crop((c, c, px - c, px - c)).resize((legacy, legacy), Image.LANCZOS).convert("RGB").save(out / "ic_launcher.png", optimize=True)
    any26 = RES / "mipmap-anydpi-v26"; any26.mkdir(exist_ok=True)
    (any26 / "ic_launcher.xml").write_text('<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                                           '    <background android:drawable="@mipmap/ic_launcher_background" />\n    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n</adaptive-icon>\n', encoding="utf-8")
    # preview sheet: xxxhdpi layers under the three common masks, on a dark and a light wallpaper
    fg, bg = layers(432)
    flat = bg.copy(); flat.paste(fg, (0, 0), fg)
    sheet = Image.new("RGB", (432 * 3 + 40, 432 * 2 + 30), (30, 30, 30))
    sheet.paste(Image.new("RGB", (sheet.width, 432 + 15), (225, 225, 225)), (0, 432 + 15))
    for i, shape in enumerate(("circle", "squircle", "rounded")):
        for j in (0, 1):
            sheet.paste(flat, (10 + i * (432 + 10), 10 + j * (432 + 15)), mask(shape, 432))
    out = ROOT / "android" / "build"; out.mkdir(exist_ok=True)
    sheet.save(out / "launcher-preview.png")
    print("ok", RES)


if __name__ == "__main__":
    main()
