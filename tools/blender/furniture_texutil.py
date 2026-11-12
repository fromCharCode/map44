"""Hilfsfunktionen fuer prozedurale Texturen (numpy/scipy/PIL, laeuft in .venv).

Wird von furniture_textures.py (Modelltexturen) und furniture_litter.py (Decal-Atlas)
benutzt. Alles deterministisch ueber Seeds.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage


def rng(seed):
    return np.random.default_rng(seed)


def value_noise(h, w, cells, seed=0, wrap=True):
    """Glattes Wertrauschen 0..1, `cells` Gitterzellen ueber die kuerzere Seite."""
    r = rng(seed)
    ch = max(2, int(round(cells * h / min(h, w))))
    cw = max(2, int(round(cells * w / min(h, w))))
    g = r.random((ch, cw))
    out = ndimage.zoom(g, (h / ch, w / cw), order=3,
                       mode="grid-wrap" if wrap else "reflect", grid_mode=True)
    out = out[:h, :w]
    if out.shape != (h, w):
        out = np.pad(out, ((0, h - out.shape[0]), (0, w - out.shape[1])), mode="edge")
    return out


def fbm(h, w, base=4, octaves=5, seed=0, persistence=0.55, wrap=True):
    acc = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        acc += amp * value_noise(h, w, base * 2 ** o, seed + 101 * o, wrap)
        tot += amp
        amp *= persistence
    acc /= tot
    lo, hi = np.percentile(acc, 1), np.percentile(acc, 99)
    return np.clip((acc - lo) / (hi - lo + 1e-9), 0, 1)


def blur(a, s):
    if a.ndim == 3:
        return np.stack([ndimage.gaussian_filter(a[..., i], s, mode="wrap")
                         for i in range(a.shape[2])], -1)
    return ndimage.gaussian_filter(a, s, mode="wrap")


def hexcol(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def lerp(a, b, t):
    t = np.asarray(t)
    if t.ndim == 2:
        t = t[..., None]
    return a + (b - a) * t


def solid(h, w, col):
    return np.ones((h, w, 3)) * hexcol(col) if isinstance(col, str) else np.ones((h, w, 3)) * col


def to_img(rgb, alpha=None):
    rgb = np.clip(rgb, 0, 1)
    if alpha is None:
        return Image.fromarray((rgb * 255 + 0.5).astype(np.uint8), "RGB")
    a = np.clip(alpha, 0, 1)
    return Image.fromarray((np.dstack([rgb, a]) * 255 + 0.5).astype(np.uint8), "RGBA")


def from_img(im):
    a = np.asarray(im).astype(np.float64) / 255.0
    return a


class Canvas:
    """Supersampelte Zeichenflaeche fuer Masken (Graustufen 0..1)."""

    def __init__(self, w, h, ss=3):
        self.w, self.h, self.ss = w, h, ss
        self.im = Image.new("L", (w * ss, h * ss), 0)
        self.d = ImageDraw.Draw(self.im)

    def _p(self, pts):
        return [(x * self.ss, y * self.ss) for x, y in pts]

    def poly(self, pts, v=255):
        self.d.polygon(self._p(pts), fill=v)

    def ellipse(self, cx, cy, rx, ry, v=255):
        s = self.ss
        self.d.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s], fill=v)

    def rect(self, x0, y0, x1, y1, v=255):
        s = self.ss
        self.d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], fill=v)

    def line(self, pts, width, v=255, joint=True):
        self.d.line(self._p(pts), fill=v, width=max(1, int(round(width * self.ss))),
                    joint="curve" if joint else None)
        if joint:
            r = width * 0.5
            for x, y in pts:
                self.ellipse(x, y, r, r, v)

    def mask(self, soften=0.0):
        im = self.im.resize((self.w, self.h), Image.LANCZOS)
        if soften > 0:
            im = im.filter(ImageFilter.GaussianBlur(soften))
        return np.asarray(im).astype(np.float64) / 255.0


def rot_pts(pts, cx, cy, ang):
    c, s = np.cos(ang), np.sin(ang)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def blob_poly(cx, cy, r, n=24, rough=0.25, seed=0, sx=1.0, sy=1.0):
    """Unregelmaessiger Klecks als Polygon."""
    rr = rng(seed)
    ph = rr.random(4) * 6.28
    pts = []
    for i in range(n):
        a = 2 * np.pi * i / n
        k = 1 + rough * (0.5 * np.sin(2 * a + ph[0]) + 0.3 * np.sin(3 * a + ph[1])
                         + 0.2 * np.sin(5 * a + ph[2])) + rough * 0.25 * (rr.random() - 0.5)
        pts.append((cx + np.cos(a) * r * k * sx, cy + np.sin(a) * r * k * sy))
    return pts
