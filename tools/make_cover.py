"""Bewuchsbild je Kachel für Godots GroundCover: cover.png (1000 × 1000, 2 m/px, RGB).
R = Wiese/Rasen, G = Wald (Kronendach), B = frei (keine Straße/kein Weg/Platz/Gleis/Wasser).
Aufruf: python make_cover.py [E,N ...]   (ohne Argument: alle Kacheln); wird auch von vegetation.py genutzt."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
TILES = Path(__file__).resolve().parent.parent / "data" / "processed" / "tiles"


def make(tile_dir: Path) -> bool:
    p0, p1 = tile_dir / "splat0.png", tile_dir / "splat1.png"
    if not (p0.exists() and p1.exists()):
        return False
    # Kanäle einzeln verkleinern: Pillow multipliert RGBA beim Skalieren mit Alpha (hier = Wassermaske)
    def chans(p):
        im = Image.open(p).convert("RGBA")
        return np.stack([np.asarray(b.resize((1000, 1000), Image.BOX), dtype=np.float32) / 255.0 for b in im.split()], axis=2)
    s0 = chans(p0)
    s1 = chans(p1)
    paved = s0.max(axis=2)
    free = np.clip(1.0 - paved - s1[:, :, 3], 0.0, 1.0)
    out = np.stack([s1[:, :, 0], s1[:, :, 1], free], axis=2)
    Image.fromarray((out * 255).astype(np.uint8), "RGB").save(tile_dir / "cover.png", optimize=False, compress_level=3)
    return True


if __name__ == "__main__":
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    n = sum(1 for nm in names if make(TILES / nm))
    print(f"cover.png für {n} Kacheln")
