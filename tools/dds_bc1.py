"""Kleine BC1/DXT1-Kodierung mit Mipmaps (DDS), damit das Spiel Fototexturen komprimiert laden kann.

Godot komprimiert zur Laufzeit nicht (nur im Editor) – unkomprimiert bräuchten hunderte Fassaden mehrere GB
Grafikspeicher. Verfahren: je 4×4-Block die hellste und dunkelste Farbe als Endpunkte, Pixel auf die 4 Stufen runden.
"""
import struct

import numpy as np
from PIL import Image


def _565(c):
    c = c.astype(np.uint32)
    return ((c[..., 0] * 31 + 127) // 255) << 11 | ((c[..., 1] * 63 + 127) // 255) << 5 | ((c[..., 2] * 31 + 127) // 255)


def _un565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31], -1).astype(np.float32)


def bc1(rgb):
    """rgb: (h, w, 3) uint8, h und w Vielfache von 4 -> bytes"""
    h, w = rgb.shape[:2]
    blk = rgb.reshape(h // 4, 4, w // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3).astype(np.float32)
    lum = blk @ np.array([0.3, 0.59, 0.11], np.float32)
    n = np.arange(len(blk))
    c0 = _565(blk[n, lum.argmax(1)])
    c1 = _565(blk[n, lum.argmin(1)])
    sw = c0 < c1
    c0, c1 = np.where(sw, c1, c0), np.where(sw, c0, c1)
    p0, p1 = _un565(c0), _un565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)             # (n, 4, 3)
    d = ((blk[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)                 # (n, 16, 4)
    idx = d.argmin(-1).astype(np.uint32)
    idx[c0 == c1] = 0                                                            # gleiche Endpunkte: sonst 3-Farben-Modus
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.empty(len(blk), dtype=[("a", "<u2"), ("b", "<u2"), ("i", "<u4")])
    out["a"], out["b"], out["i"] = c0, c1, bits
    return out.tobytes()


def save_dds(img, path):
    """PIL-Bild als DDS (DXT1, alle Mipstufen); Größe wird auf Vielfache von 4 gebracht"""
    img = img.convert("RGB")
    w, h = max(4, img.width // 4 * 4), max(4, img.height // 4 * 4)
    if (w, h) != img.size:
        img = img.resize((w, h), Image.LANCZOS)
    levels, cur = [], img
    while True:
        cw, ch = cur.size
        pad = Image.new("RGB", ((cw + 3) // 4 * 4, (ch + 3) // 4 * 4))
        pad.paste(cur.resize(pad.size, Image.BILINEAR) if (cw < 4 or ch < 4) else cur)
        levels.append(bc1(np.asarray(pad)))
        if cw == 1 and ch == 1:
            break
        cur = cur.resize((max(1, cw // 2), max(1, ch // 2)), Image.BOX)
    hdr = struct.pack("<4s7I44x", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000, h, w, len(levels[0]), 0, len(levels))
    hdr += struct.pack("<2I4s5I", 32, 0x4, b"DXT1", 0, 0, 0, 0, 0)
    hdr += struct.pack("<5I", 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(hdr)
        for lv in levels:
            f.write(lv)


if __name__ == "__main__":
    import sys
    save_dds(Image.open(sys.argv[1]), sys.argv[2])
