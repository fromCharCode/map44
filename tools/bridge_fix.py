"""Höhenkorrektur der LoD2-Brücken mit dem Oberflächenmodell DOM1.

Die LoD2-"Bauwerke" (Brücken) sind oft grobe Klötze mit geschätzter, flacher Oberkante – teils mehrere Meter
neben der echten Fahrbahn (z. B. Freiberger Straße: LoD2 8,06 m, DOM/Fahrbahn 10,4 m). Das DOM (Laserscan,
erste Reflexion) zeigt die tatsächliche Oberfläche. Je Brückenteil wird robust eine Ebene
    DOM − LoD2 ≈ a + b·Δe + c·Δn
angepasst (Huber-IRLS; Fahrzeuge, Bäume, Oberleitungen, Geländer sind Ausreißer), nur auf Pixeln, auf denen
dieses Teil das oberste ist (darunterliegende Decks gestapelter Brücken sieht das DOM nicht). Ist die Ebene gut
gestützt, wird das ganze Teil (Dach, Wände, Boden) um sie verschoben.
"""
import numpy as np
from PIL import Image

from config import BASE_HEIGHT, RAW
from road_surface import raster_tris

Image.MAX_IMAGE_PIXELS = None
import os as _os
DEBUG = bool(_os.environ.get("BRIDGE_DEBUG"))


class DomMosaic:
    """DOM1-Kacheln (2x2 km GeoTIFF) bei Bedarf geladen; Höhen relativ zu BASE_HEIGHT, NaN = keine Daten."""

    def __init__(self):
        self._cache = {}

    def _tile(self, e_km: int, n_km: int):
        k = (e_km, n_km)
        if k not in self._cache:
            d = RAW / "dom" / f"dom1_33{e_km % 1000}_{n_km}_2_sn_tiff"
            fs = list(d.glob("dom1_*_sn.tif")) if d.exists() else []
            if fs:
                a = np.array(Image.open(fs[0]), dtype=np.float32)
                a[a < -1000] = np.nan
                self._cache[k] = a - BASE_HEIGHT
            else:
                self._cache[k] = None
        return self._cache[k]

    def sample(self, e, n):
        """Nächster Pixel (1 m) an UTM-Positionen."""
        e = np.asarray(e, dtype=float)
        n = np.asarray(n, dtype=float)
        out = np.full(e.shape, np.nan, dtype=np.float32)
        ek = (np.floor(e / 2000.0) * 2).astype(int)
        nk = (np.floor(n / 2000.0) * 2).astype(int)
        for key in set(zip(ek.ravel().tolist(), nk.ravel().tolist())):
            a = self._tile(*key)
            if a is None:
                continue
            m = (ek == key[0]) & (nk == key[1])
            c = np.clip(np.floor(e[m] - key[0] * 1000).astype(int), 0, a.shape[1] - 1)
            r = np.clip(np.floor((key[1] + 2) * 1000 - n[m]).astype(int), 0, a.shape[0] - 1)
            out[m] = a[r, c]
        return out


def _tris(part, tri_fn, key="roofs"):
    _, utm = tri_fn(part[key])
    return [[(q[0], q[1], q[2] - BASE_HEIGHT) for q in tri] for tri in utm]


def correct_parts(parts, dom: DomMosaic, tri_fn, log=print):
    """tri_fn: Triangulierung von LoD2-Polygonen (build_city._oriented_tris)."""
    """Gibt neue Teile-Liste zurück (korrigierte Kopien). Schreibt ein kurzes Protokoll."""
    # Oberste Deckhöhe aller Teile (für "dieses Teil ist oben")
    allt = []
    per = []
    for p in parts:
        t = _tris(p, tri_fn)
        per.append(t)
        allt += t
    if not allt:
        return parts
    es = [q[0] for t in allt for q in t]
    ns = [q[1] for t in allt for q in t]
    x0, ytop = float(np.floor(min(es))) - 2, float(np.ceil(max(ns))) + 2
    w, h = int(np.ceil(max(es) - x0)) + 3, int(np.ceil(ytop - min(ns))) + 3
    if w * h > 60_000_000:
        log("  Brückenkorrektur: Gebiet zu groß, übersprungen")
        return parts
    top_all, _ = raster_tris(allt, x0, ytop, w, h)
    out = []
    n_fix = 0
    for p, t in zip(parts, per):
        if not t:
            out.append(p)
            continue
        pe = [q[0] for tri in t for q in tri]
        pn = [q[1] for tri in t for q in tri]
        c0, c1 = int(min(pe) - x0), int(max(pe) - x0) + 1
        r0, r1 = int(ytop - max(pn)), int(ytop - min(pn)) + 1
        zp, _ = raster_tris(t, x0 + c0, ytop - r0, c1 - c0 + 1, r1 - r0 + 1)
        from scipy.ndimage import binary_erosion
        inner = binary_erosion(np.isfinite(zp), iterations=2)
        if inner.sum() < 30:
            inner = np.isfinite(zp)
        rr, cc = np.nonzero(inner)
        if len(rr) < 15:
            out.append(p)
            continue
        z = zp[rr, cc]
        top = z >= top_all[rr + r0, cc + c0] - 0.3
        if top.sum() < max(15, 0.3 * len(z)):
            out.append(p)
            continue
        e = x0 + c0 + cc[top] + 0.5
        n = ytop - r0 - rr[top] - 0.5
        d = dom.sample(e, n) - z[top]
        ok = np.isfinite(d) & (np.abs(d) < 6.0)
        if ok.sum() < 15:
            out.append(p)
            continue
        e, n, d = e[ok], n[ok], d[ok]
        ce, cn = float(e.mean()), float(n.mean())
        # Brückenachse (Hauptrichtung der Deckpixel); Modell entlang der Achse quadratisch (Bögen), quer linear
        ev, evec = np.linalg.eigh(np.cov(np.vstack([e - ce, n - cn])))
        ax, ay = evec[0, 1], evec[1, 1]
        u = (e - ce) * ax + (n - cn) * ay
        v = -(e - ce) * ay + (n - cn) * ax
        L = max(float(np.abs(u).max()), 1.0)
        quad = L >= 12.0

        def design(uu, vv):
            t = np.clip(uu / L, -1.1, 1.1)
            cols = [np.ones_like(uu), t, vv] + ([t * t] if quad else [])
            return np.column_stack(cols)
        X = design(u, v)
        # untere Hüllfläche: Fahrzeuge/Bäume/Leitungen liegen nur darüber -> oberhalb stark abwerten
        coef = np.zeros(X.shape[1])
        coef[0] = np.percentile(d, 30)
        for _ in range(12):
            res = d - X @ coef
            wts = np.where(res > 0.2, 0.02, 1.0 / np.maximum(1.0, np.abs(res) / 0.2))
            sw = np.sqrt(wts)
            coef, *_ = np.linalg.lstsq(X * sw[:, None], d * sw, rcond=None)
        res = np.abs(d - X @ coef)
        inl = float((res < 0.35).mean())
        pe_a, pn_a = np.array(pe), np.array(pn)
        uv_u = (pe_a - ce) * ax + (pn_a - cn) * ay
        uv_v = -(pe_a - ce) * ay + (pn_a - cn) * ax
        corr_v = design(uv_u, uv_v) @ coef
        ts = np.linspace(-1, 1, 21)
        slope = np.abs(coef[1] + (2 * coef[3] * ts if quad else 0.0)) / L
        spread = float(corr_v.max() - corr_v.min())
        if inl < 0.55 or slope.max() > 0.08 or abs(coef[2]) > 0.08 or np.abs(corr_v).max() > 4.5 \
                or (quad and ok.sum() / (2 * L) < 3.0) \
                or (spread > 2.5 and inl < 0.6) \
                or (float(np.median(corr_v)) < -0.6 and (inl < 0.8 or ok.sum() < 0.5 * len(z))) \
                or (abs(float(np.median(corr_v))) < 0.6 and np.abs(corr_v).max() < 1.0):
            # LoD2 ist meist genau: nur grobe Fehler korrigieren
            if DEBUG:
                log(f"  (abgelehnt {p['id']}: passend {inl*100:.0f} %, Steigung {slope.max()*100:.1f} %, quer {coef[2]*100:.1f} %, "
                    f"Korrektur {corr_v.min():+.2f}..{corr_v.max():+.2f}, Länge {2*L:.0f} m)")
            out.append(p)
            continue

        def corr(q0, q1):
            uu = (q0 - ce) * ax + (q1 - cn) * ay
            vv = -(q0 - ce) * ay + (q1 - cn) * ax
            return float(design(np.array([uu]), np.array([vv]))[0] @ coef)

        def shift(polys):
            res_ = []
            for ext, holes in polys:
                def mv(ring):
                    return [(q[0], q[1], q[2] + corr(q[0], q[1])) for q in ring]
                res_.append((mv(ext), [mv(hh) for hh in holes]))
            return res_
        q = dict(p)
        q["roofs"], q["walls"], q["ground"] = shift(p["roofs"]), shift(p["walls"]), shift(p["ground"])
        q["dom_fix"] = round(float(np.median(corr_v)), 2)
        out.append(q)
        n_fix += 1
        log(f"  Brücke {p['id']}: DOM-Korrektur {np.median(corr_v):+.2f} m ({corr_v.min():+.2f}..{corr_v.max():+.2f}, "
            f"{inl*100:.0f} % passend, {int(ok.sum())} Pixel, Länge {2*L:.0f} m)")
    log(f"  Brückenkorrektur: {n_fix} von {len(parts)} LoD2-Teilen angepasst")
    return out
