"""Symbol-Atlas für Ladenschilder aus den Piktogramm-Sets Maki und Temaki (beide CC0, keine Marken/Logos).

Aufruf:  .venv/bin/python tools/blender/make_shop_icons.py   (braucht Pillow und cairosvg)
Quelle:  tools/shop_icons/*.svg   (Herkunft je Datei: tools/shop_icons/SOURCES.txt)
Ausgabe: godot/assets/textures/street/shop_icons.png    8 x 7 Zellen à 256 px, weiß auf transparent
         godot/assets/textures/street/shop_icons.json   {"grid": [8, 7], "cells": {name: index}}
Die Farbe setzt das Spiel (Vertexfarbe = Schriftfarbe der Ladenkategorie).
"""
import glob
import io
import json
import os

import cairosvg
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT, "tools", "shop_icons")
OUT_DIR = os.path.join(ROOT, "godot", "assets", "textures", "street")
GX, GY = 8, 7
CELL = 256
PAD = 16                    # Rand je Zelle (gegen Ausfransen beim Mipmapping)


def render(path):
    inner = CELL - 2 * PAD
    png = cairosvg.svg2png(url=path, output_width=inner, output_height=inner)
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    white = Image.new("RGBA", im.size, (255, 255, 255, 0))
    white.putalpha(im.getchannel("A"))
    return white


def main():
    files = sorted(glob.glob(os.path.join(SRC_DIR, "*.svg")))
    assert len(files) <= GX * GY, f"{len(files)} Symbole passen nicht in {GX}x{GY}"
    atlas = Image.new("RGBA", (GX * CELL, GY * CELL), (255, 255, 255, 0))
    cells = {}
    for i, f in enumerate(files):
        atlas.paste(render(f), ((i % GX) * CELL + PAD, (i // GX) * CELL + PAD))
        cells[os.path.splitext(os.path.basename(f))[0]] = i
    os.makedirs(OUT_DIR, exist_ok=True)
    atlas.save(os.path.join(OUT_DIR, "shop_icons.png"))
    with open(os.path.join(OUT_DIR, "shop_icons.json"), "w") as fh:
        json.dump({"grid": [GX, GY], "cells": cells}, fh, indent=1)
    print(f"{len(cells)} Symbole -> {OUT_DIR}/shop_icons.png")


if __name__ == "__main__":
    main()
