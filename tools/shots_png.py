#!/usr/bin/env python3
"""BMP screenshots -> PNG at 1x (exact 240x240). usage: shots_png.py in_dir out_dir"""
import sys, os
from PIL import Image
os.makedirs(sys.argv[2], exist_ok=True)
for f in sorted(os.listdir(sys.argv[1])):
    if f.endswith(".bmp"):
        Image.open(os.path.join(sys.argv[1], f)).convert("RGB").save(os.path.join(sys.argv[2], f[:-4] + ".png"))
