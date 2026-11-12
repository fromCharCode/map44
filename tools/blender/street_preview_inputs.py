"""Hilfsbilder nur für die Vorschau-Renderings der Straßenmodelle (werden nicht exportiert).

Aufruf: .venv/bin/python tools/blender/street_preview_inputs.py
Schreibt nach tools/blender/street_tmp/ (Blender-Flatpak sieht /tmp nicht).
"""
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TEX = os.path.join(ROOT, "godot", "assets", "textures", "street")
OUT = os.path.join(HERE, "street_tmp")


def main():
    os.makedirs(os.path.join(OUT, "cells"), exist_ok=True)
    atlas = Image.open(os.path.join(TEX, "traffic_signs.png")).convert("RGBA")
    meta = json.load(open(os.path.join(TEX, "traffic_signs.json"), encoding="utf-8"))
    cp = meta["cell_px"]
    for name, c in meta["cells"].items():
        x, y = c["col"] * cp, c["row"] * cp
        atlas.crop((x, y, x + cp, y + cp)).save(os.path.join(OUT, "cells", name + ".png"))
    # Litfaß-Mantel: unten 3 Plakate (4/1-Bogen), oben 6 Plakate (A1) -> wie im Shader-Vorschlag
    post = Image.open(os.path.join(TEX, "posters.png")).convert("RGB")
    pw, ph = 512, 724
    cells = [post.crop(((i % 4) * pw, (i // 4) * ph, (i % 4 + 1) * pw, (i // 4 + 1) * ph)) for i in range(8)]
    m = Image.new("RGB", (3 * pw, ph + ph // 2))
    for k, i in enumerate((0, 4, 6)):
        m.paste(cells[i], (k * pw, ph // 2))
    for k, i in enumerate((3, 1, 7, 2, 5, 3)):
        m.paste(cells[i].resize((pw // 2, ph // 2), Image.LANCZOS), (k * pw // 2, 0))
    m.save(os.path.join(OUT, "litfass_mantle.png"))
    bb = Image.open(os.path.join(TEX, "billboard_posters.png")).convert("RGB")
    bm = json.load(open(os.path.join(TEX, "billboard_posters.json"), encoding="utf-8"))
    cw, ch = bm["cell_px"]
    bb.crop((0, 0, cw, ch)).save(os.path.join(OUT, "billboard_poster.png"))
    print("ok")


if __name__ == "__main__":
    main()
