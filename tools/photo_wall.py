"""Fassadenfoto entzerren und als Wandtextur eintragen.

  python tools/photo_wall.py <bild> <name> --px x0,y0 x1,y1 x2,y2 x3,y3 --wall ax,az bx,bz --h <m>
        [--y0 <m über Grund>] [--parts N] [--credit "Urheber|Lizenz|Commons-Dateiname"] [--rough 0.8]

--px: die vier Ecken der Wandfläche im Foto in der Reihenfolge unten links, unten rechts, oben rechts, oben links
      (Bildkoordinaten in Pixeln des Originals).
--wall: Fußpunkte der Wand im Spiel (x,z); a = linke, b = rechte Ecke vom Betrachter aus.
--h: Höhe der abgebildeten Fläche in Metern; --y0 hebt die Unterkante an (z. B. über einem Sockel).

Schreibt godot/assets/textures/landmarks/<name>_<i>.jpg (je Teil höchstens 4096 px breit, rund 100–160 px/m) und
ergänzt walls.json (liest landmarks.gd) sowie CREDITS.md. Nur gemeinfreie Architektur und frei lizenzierte Fotos.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "godot" / "assets" / "textures" / "landmarks"
Image.MAX_IMAGE_PIXELS = None


def homography(src, dst):
    """3×3-Abbildung dst -> src (für PIL: Koeffizienten der Rücktransformation)"""
    a = []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(a, dtype=float))
    h = vt[-1]
    return (h / h[8])[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("name")
    ap.add_argument("--px", nargs=4, required=True)
    ap.add_argument("--wall", nargs=2, required=True)
    ap.add_argument("--h", type=float, required=True)
    ap.add_argument("--y0", type=float, default=0.0)
    ap.add_argument("--parts", type=int, default=0)
    ap.add_argument("--credit", default="")
    ap.add_argument("--rough", type=float, default=0.8)
    a = ap.parse_args()
    px = [tuple(float(v) for v in p.split(",")) for p in a.px]
    wa, wb = (tuple(float(v) for v in p.split(",")) for p in a.wall)
    length = math.hypot(wb[0] - wa[0], wb[1] - wa[1])
    im = Image.open(a.image).convert("RGB")
    # Zielauflösung: so viel, wie das Foto hergibt, höchstens 160 px/m
    src_w = (math.hypot(px[1][0] - px[0][0], px[1][1] - px[0][1]) + math.hypot(px[2][0] - px[3][0], px[2][1] - px[3][1])) / 2
    ppm = min(160.0, src_w / length)
    parts = a.parts or max(1, math.ceil(length * ppm / 4096.0))
    w = int(round(length * ppm))
    w -= w % parts
    h = int(round(a.h * ppm))
    dst = [(0, h), (w, h), (w, 0), (0, 0)]
    out = im.transform((w, h), Image.PERSPECTIVE, tuple(homography(px, dst)), Image.BICUBIC)
    OUT.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(parts):
        fn = f"{a.name}_{i}.jpg"
        out.crop((i * w // parts, 0, (i + 1) * w // parts, h)).save(OUT / fn, quality=90)
        files.append(fn)
    wf = OUT / "walls.json"
    walls = json.loads(wf.read_text(encoding="utf-8")) if wf.exists() else []
    walls = [x for x in walls if x.get("name") != a.name]
    walls.append({"name": a.name, "a": [round(wa[0], 2), round(wa[1], 2)], "b": [round(wb[0], 2), round(wb[1], 2)],
                  "h": a.h, "y0": a.y0, "rough": a.rough, "tex": files})
    wf.write_text(json.dumps(walls, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.credit:
        cf = OUT / "CREDITS.md"
        who, lic, src = (a.credit.split("|") + ["", "", ""])[:3]
        line = f"| {a.name}_*.jpg | {a.name} (entzerrt, zugeschnitten) | {who} | {lic} | Wikimedia Commons, „{src}“ |"
        txt = cf.read_text(encoding="utf-8") if cf.exists() else ""
        if f"| {a.name}_*.jpg |" not in txt:
            lines = txt.rstrip("\n").split("\n")
            k = max(i for i, l_ in enumerate(lines) if l_.startswith("|"))
            lines.insert(k + 1, line)
            cf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{a.name}: {w}×{h} px ({ppm:.0f} px/m), {parts} Teil(e), Wand {length:.1f} m × {a.h} m")


if __name__ == "__main__":
    main()
