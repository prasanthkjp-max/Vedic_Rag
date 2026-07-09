#!/usr/bin/env python3
"""Regenerate the Android launcher icons and splash screens from the brand mark.

The repo gitignores *.png, so the Android art exists only in the working tree;
run this after cloning (before building the APK) or whenever the brand icon or
theme background changes:

    python3 tools/gen_android_art.py

Reads  static/assets/oolaichuvadi_icon.png (transparent 512x512)
Writes android/app/src/main/res/drawable*/splash.png        (11 densities)
       android/app/src/main/res/mipmap-*dpi/ic_launcher.png (legacy, rounded-rect)
       android/app/src/main/res/mipmap-*dpi/ic_launcher_round.png
       android/app/src/main/res/mipmap-*dpi/ic_launcher_foreground.png (adaptive)

The background color must match --bg-deep in static/index.html and
brandBackground in android/app/src/main/res/values/colors.xml.
"""
import glob
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = os.path.join(ROOT, "static", "assets", "oolaichuvadi_icon.png")
RES = os.path.join(ROOT, "android", "app", "src", "main", "res")

BG = (253, 246, 234, 255)  # --bg-deep #fdf6ea

# name -> (px size per density dir is read from the existing file)
SPLASH_SIZES = {  # fallback sizes if a splash.png is ever missing
    "drawable": (480, 320),
    "drawable-land-mdpi": (480, 320), "drawable-land-hdpi": (800, 480),
    "drawable-land-xhdpi": (1280, 720), "drawable-land-xxhdpi": (1600, 960),
    "drawable-land-xxxhdpi": (1920, 1280),
    "drawable-port-mdpi": (320, 480), "drawable-port-hdpi": (480, 800),
    "drawable-port-xhdpi": (720, 1280), "drawable-port-xxhdpi": (960, 1600),
    "drawable-port-xxxhdpi": (1280, 1920),
}
MIPMAP_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FOREGROUND_SIZES = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}


def _base(icon, size, icon_frac):
    canvas = Image.new("RGBA", (size, size), BG)
    side = int(size * icon_frac)
    ic = icon.resize((side, side), Image.LANCZOS)
    canvas.paste(ic, ((size - side) // 2, (size - side) // 2), ic)
    return canvas


def _masked(img, draw_mask):
    s = img.size[0]
    mask = Image.new("L", (s, s), 0)
    draw_mask(ImageDraw.Draw(mask), s)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main():
    icon = Image.open(ICON).convert("RGBA")

    for dirname, fallback in SPLASH_SIZES.items():
        path = os.path.join(RES, dirname, "splash.png")
        w, h = Image.open(path).size if os.path.exists(path) else fallback
        canvas = Image.new("RGBA", (w, h), BG)
        side = int(min(w, h) * 0.42)
        ic = icon.resize((side, side), Image.LANCZOS)
        canvas.paste(ic, ((w - side) // 2, (h - side) // 2), ic)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        canvas.convert("RGB").save(path, "PNG", optimize=True)
        print("wrote", path)

    for density, size in MIPMAP_SIZES.items():
        d = os.path.join(RES, f"mipmap-{density}")
        os.makedirs(d, exist_ok=True)
        _masked(_base(icon, size, 0.78),
                lambda dr, s: dr.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.12), fill=255)
                ).save(os.path.join(d, "ic_launcher.png"), "PNG", optimize=True)
        _masked(_base(icon, size, 0.68),
                lambda dr, s: dr.ellipse([0, 0, s - 1, s - 1], fill=255)
                ).save(os.path.join(d, "ic_launcher_round.png"), "PNG", optimize=True)
        fg_size = FOREGROUND_SIZES[density]
        fg = Image.new("RGBA", (fg_size, fg_size), (0, 0, 0, 0))
        side = int(fg_size * 0.50)  # keep inside the adaptive-icon safe zone
        ic = icon.resize((side, side), Image.LANCZOS)
        fg.paste(ic, ((fg_size - side) // 2, (fg_size - side) // 2), ic)
        fg.save(os.path.join(d, "ic_launcher_foreground.png"), "PNG", optimize=True)
        print("wrote mipmaps for", density)


if __name__ == "__main__":
    main()
