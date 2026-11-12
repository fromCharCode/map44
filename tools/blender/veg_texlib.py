"""Hilfsfunktionen für prozedurale Texturen (Unterholz + Fassadenteile).

Läuft mit dem Projekt-venv (PIL, numpy, scipy), NICHT in Blender.
Alle Rauschfunktionen sind per FFT erzeugt und damit nahtlos kachelbar.
"""
from __future__ import annotations

import colorsys
import math
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(HERE, "tex")
os.makedirs(TEX_DIR, exist_ok=True)


# ---------------------------------------------------------------- Rauschen
def fnoise(h, w, beta=2.0, sx=1.0, sy=1.0, seed=0, fmin=0.0, fmax=None):
    """Periodisches 1/f^beta-Rauschen (Mittel 0, Std 1).

    sx/sy > 1 dämpfen Frequenzen in x bzw. y stärker -> Strukturen werden
    in dieser Richtung länger (sy groß = vertikale Fasern).
    """
    rng = np.random.default_rng(seed)
    ky = np.fft.fftfreq(h)[:, None] * h
    kx = np.fft.fftfreq(w)[None, :] * w
    k = np.sqrt((kx * sx) ** 2 + (ky * sy) ** 2)
    k[0, 0] = 1.0
    amp = 1.0 / k ** (beta / 2.0)
    if fmin:
        amp = amp * (1.0 - np.exp(-(k / fmin) ** 4))
    if fmax:
        amp = amp * np.exp(-(k / fmax) ** 2)
    amp[0, 0] = 0.0
    spec = (rng.normal(size=(h, w)) + 1j * rng.normal(size=(h, w))) * amp
    n = np.real(np.fft.ifft2(spec))
    n = (n - n.mean()) / (n.std() + 1e-9)
    return n


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    t = np.asarray(t, dtype=float)
    if t.ndim and t.shape[-1] != 1 and (a.ndim or b.ndim):
        t = t[..., None]
    return a + (b - a) * t


def srgb(c):
    """Hex oder (r,g,b) 0..255 -> float 0..1."""
    if isinstance(c, str):
        c = c.lstrip("#")
        return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], float) / 255.0
    return np.asarray(c, float) / (255.0 if max(c) > 1.0 else 1.0)


def jitter_color(c, rng, dh=0.02, ds=0.08, dv=0.10):
    r, g, b = [float(x) for x in c]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + rng.uniform(-dh, dh)) % 1.0
    s = float(np.clip(s * (1 + rng.uniform(-ds, ds)), 0, 1))
    v = float(np.clip(v * (1 + rng.uniform(-dv, dv)), 0, 1))
    return np.array(colorsys.hsv_to_rgb(h, s, v))


# ---------------------------------------------------------------- Normalen
def normal_from_height(hgt, strength=2.0):
    """Höhenfeld (beliebige Einheit) -> OpenGL-Normalmap (glTF-Konvention)."""
    dx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) * 0.5
    drow = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) * 0.5
    nx = -dx * strength
    ny = drow * strength
    nz = np.ones_like(hgt)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / ln, ny / ln, nz / ln], -1)
    return Image.fromarray(np.clip((n * 0.5 + 0.5) * 255 + 0.5, 0, 255).astype(np.uint8), "RGB")


# ---------------------------------------------------------------- Speichern
def to_img(rgb, alpha=None):
    rgb = np.clip(np.asarray(rgb, float), 0, 1)
    if alpha is None:
        return Image.fromarray((rgb * 255 + 0.5).astype(np.uint8), "RGB")
    a = np.clip(np.asarray(alpha, float), 0, 1)
    arr = np.concatenate([rgb, a[..., None]], -1)
    return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGBA")


def save(img, name):
    p = os.path.join(TEX_DIR, name)
    img.save(p, optimize=True)
    return p


# ---------------------------------------------------------------- Zeichnen
class Canvas:
    """Supersampeltes RGBA-Zeichnen; .result() liefert heruntergerechnetes
    Bild mit Kantenauffüllung (Farbe läuft in transparente Bereiche, damit
    Mipmaps keine dunklen/hellen Säume bekommen)."""

    def __init__(self, w, h, ss=2):
        self.w, self.h, self.ss = w, h, ss
        self.img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def P(self, pts):
        s = self.ss
        return [(float(x) * s, float(y) * s) for x, y in pts]

    @staticmethod
    def C(c, a=1.0):
        c = np.clip(np.asarray(c, float), 0, 1)
        return (int(c[0] * 255 + .5), int(c[1] * 255 + .5), int(c[2] * 255 + .5), int(a * 255 + .5))

    def poly(self, pts, col, a=1.0):
        if len(pts) >= 3:
            self.d.polygon(self.P(pts), fill=self.C(col, a))

    def line(self, pts, col, width, a=1.0):
        w = max(1, int(round(width * self.ss)))
        self.d.line(self.P(pts), fill=self.C(col, a), width=w, joint="curve")

    def ellipse(self, cx, cy, rx, ry, col, a=1.0):
        s = self.ss
        self.d.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s], fill=self.C(col, a))

    def thick_curve(self, pts, w0, w1, col, a=1.0):
        """Polylinie mit von w0 nach w1 verjüngter Breite als Polygonband."""
        pts = np.asarray(pts, float)
        n = len(pts)
        if n < 2:
            return
        left, right = [], []
        for i in range(n):
            if i == 0:
                t = pts[1] - pts[0]
            elif i == n - 1:
                t = pts[-1] - pts[-2]
            else:
                t = pts[i + 1] - pts[i - 1]
            t = t / (np.linalg.norm(t) + 1e-9)
            nrm = np.array([-t[1], t[0]])
            w = (w0 + (w1 - w0) * i / (n - 1)) * 0.5
            left.append(pts[i] + nrm * w)
            right.append(pts[i] - nrm * w)
        self.poly(left + right[::-1], col, a)

    def result(self, pad=True, alpha_gamma=1.0):
        arr = np.asarray(self.img).astype(np.float32) / 255.0
        s = self.ss
        H, W = self.h, self.w
        a = arr[..., 3:4]
        prem = arr[..., :3] * a
        prem = prem.reshape(H, s, W, s, 3).mean((1, 3))
        a = a.reshape(H, s, W, s, 1).mean((1, 3))
        rgb = np.where(a > 1e-4, prem / np.maximum(a, 1e-4), 0.0)
        a = a[..., 0]
        if alpha_gamma != 1.0:
            a = a ** alpha_gamma
        if pad:
            rgb = pad_rgb(rgb, a)
        return rgb, a


def pad_rgb(rgb, a, thresh=0.3):
    """Farbe der nächstgelegenen deckenden Pixel in transparente Pixel
    kopieren, danach leicht weichzeichnen (nur im transparenten Bereich)."""
    valid = a > thresh
    if not valid.any():
        return rgb
    _, idx = ndi.distance_transform_edt(~valid, return_indices=True)
    filled = rgb[idx[0], idx[1]]
    blur = np.stack([ndi.gaussian_filter(filled[..., c], 3.0, mode="wrap") for c in range(3)], -1)
    out = np.where(valid[..., None], rgb, blur)
    # Halb-transparente Randpixel behalten ihre eigene Farbe
    return out


def leaf_outline(L, W, shape="ovate", serr=0.0, nserr=0, n=28, tip=1.0):
    """Blattumriss in lokalen Koordinaten: Basis (0,0), Spitze (0,-L) (Bild-y nach unten = vorne).

    Gibt (links, rechts) als Listen von (x, y) zurück (beide von Basis zur Spitze)."""
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        if shape == "ovate":        # Hasel: breit, rundlich, kurze Träufelspitze
            w = math.sin(math.pi * min(1.0, t ** 0.85)) ** 0.75 * (1.0 - 0.15 * t)
            w *= 1.0 - 0.75 * max(0.0, (t - 0.78) / 0.22) ** 1.5 * tip
        elif shape == "elliptic":   # Buche/Liguster
            w = math.sin(math.pi * t) ** 0.85
        elif shape == "lanceolate":  # Holunder-Fiederblättchen, Weide
            w = math.sin(math.pi * t ** 0.8) ** 1.1
        elif shape == "cordate":    # Brennnessel: herzförmig, lang zugespitzt
            w = (math.sin(math.pi * min(1.0, t ** 0.6)) ** 0.9) * (1.0 - 0.55 * t)
        else:
            w = math.sin(math.pi * t)
        w *= W * 0.5
        if nserr and 0.08 < t < 0.97:
            ph = (t * nserr) % 1.0
            w *= 1.0 + serr * (ph - 0.5) * 2.0
        y = -t * L
        left.append((-w, y))
        right.append((w, y))
    return left, right


def xform(pts, cx, cy, ang):
    """Lokale Punkte drehen (ang = Richtung der Blattspitze, Bildwinkel, 0 = nach oben) und verschieben."""
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for x, y in pts:
        # lokales -y ist "vorne"; Drehung im Bild (y nach unten)
        X = x * ca - y * sa
        Y = x * sa + y * ca
        out.append((cx + X, cy + Y))
    return out


def draw_leaf(cv, cx, cy, ang, L, W, col, rng, shape="ovate", serr=0.08, nserr=14,
              veins=True, petiole=0.0, stem_col=None):
    """Zweifarbiges Blatt (Licht-/Schattenhälfte), Mittelrippe, Seitenadern."""
    if petiole > 0:
        p0 = (cx, cy)
        p1 = (cx + math.sin(ang) * petiole, cy - math.cos(ang) * petiole)
        cv.line([p0, p1], stem_col if stem_col is not None else col * 0.8, max(1.0, W * 0.05))
        cx, cy = p1
    left, right = leaf_outline(L, W, shape, serr, nserr)
    outline = left + right[::-1]
    dark = col * rng.uniform(0.80, 0.90)
    light = np.clip(col * rng.uniform(1.0, 1.08), 0, 1)
    edge = col * 0.68
    # leicht größere dunkle Kontur (Blattrand)
    big_l, big_r = leaf_outline(L * 1.02, W * 1.06, shape, serr, nserr)
    cv.poly(xform(big_l + big_r[::-1], cx, cy + 0.0, ang), edge)
    cv.poly(xform(outline, cx, cy, ang), light)
    side = right if rng.random() < 0.5 else left
    half = [(0.0, 0.0)] + side + [(0.0, -L)]
    cv.poly(xform(half, cx, cy, ang), dark)
    if veins:
        vein = np.clip(col * 1.25 + np.array([0.05, 0.05, 0.0]), 0, 1)
        cv.line(xform([(0, 0), (0, -L * 0.92)], cx, cy, ang), vein, max(0.6, W * 0.03), a=0.55)
        nv = 5 if L > 25 else 3
        for k in range(1, nv + 1):
            t = k / (nv + 1)
            y0 = -t * L * 0.9
            for sgn in (-1, 1):
                wx = sgn * W * 0.42 * math.sin(math.pi * min(1, t ** 0.85)) ** 0.7
                cv.line(xform([(0, y0), (wx, y0 - L * 0.14)], cx, cy, ang), vein, max(0.5, W * 0.02), a=0.22)


def mult_noise(rgb, a, amount=0.12, seed=1, beta=1.6):
    h, w = a.shape
    n = fnoise(h, w, beta=beta, seed=seed)
    return np.clip(rgb * (1.0 + amount * n[..., None]), 0, 1)
