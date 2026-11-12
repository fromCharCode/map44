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
    KIND = "dom"

    def __init__(self):
        self._cache = {}

    def _tile(self, e_km: int, n_km: int):
        k = (e_km, n_km)
        if k not in self._cache:
            d = RAW / self.KIND / f"{self.KIND}1_33{e_km % 1000}_{n_km}_2_sn_tiff"
            fs = list(d.glob(f"{self.KIND}1_*_sn.tif")) if d.exists() else []
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


class DgmMosaic(DomMosaic):
    """DGM1 (Gelände ohne Bauwerke) – an Brückenenden = Damm-/Rampenkrone, zur Bestätigung der DOM-Korrektur."""
    KIND = "dgm"


def _tris(part, tri_fn, key="roofs"):
    _, utm = tri_fn(part[key])
    return [[(q[0], q[1], q[2] - BASE_HEIGHT) for q in tri] for tri in utm]


def _ends_confirm(dgm, ce, cn, ax, ay, u, v, zt, corr_at):
    """Bestätigt eine Korrektur über das Gelände hinter den Deckenden: Brücken schließen an Damm/Rampe an.
    Geprüft werden beide Hauptrichtungen (fast quadratische Überführungen: die Achse aus der Pixelverteilung kann
    quer liegen). True, wenn mindestens ein Ende nach der Korrektur passt (≤ 0,8 m) und vorher deutlich nicht
    (≥ 1,5 m) und kein Ende der Korrektur widerspricht (> 1,5 m nachher, aber ≤ 0,8 m vorher)."""
    if dgm is None:
        return False
    good = 0
    for w, dx, dy, along in ((u, ax, ay, True), (v, -ay, ax, False)):
        for sgn, we in ((-1.0, float(w.min())), (1.0, float(w.max()))):
            sel = np.abs(w - we) < 4.0
            if sel.sum() < 3:
                continue
            ws = we + sgn * np.array([2.0, 3.0, 4.0, 5.0])
            g = dgm.sample(ce + ws * dx, cn + ws * dy)
            g = g[np.isfinite(g)]
            if len(g) < 2:
                continue
            g = float(np.median(g))
            z_end = float(np.median(zt[sel]))
            c_end = float(np.median([corr_at(uu, vv) for uu, vv in zip(u[sel][:20], v[sel][:20])]))
            before, after = abs(z_end - g), abs(z_end + c_end - g)
            if after <= 0.8 and before >= 1.5:
                good += 1
            elif after > 1.5 and before <= 0.8:
                return False
    return good >= 1


def _piecewise(u, d):
    """Abschnittsweise Korrektur entlang der Achse (Stützstellen alle 30 m, untere Hülle je Fenster ±20 m) für lange
    Teile, die eine Ebene/Parabel nicht beschreibt (Hochstraße mit Rampen in EINEM LoD2-Teil: Löbtauer Brücke lag in
    der Mitte 7 m zu tief). Rückgabe (knots_u, offsets) oder None."""
    lo, hi = float(u.min()), float(u.max())
    if hi - lo < 120.0:
        return None
    ks = np.arange(lo, hi + 1e-6, 30.0)
    if ks[-1] < hi - 5.0:
        ks = np.append(ks, hi)
    cs = np.full(len(ks), np.nan)
    for i, k in enumerate(ks):
        w = d[np.abs(u - k) < 20.0]
        if len(w) < 25:
            continue
        c = float(np.percentile(w, 30))
        sel = np.abs(w - c) < 0.5
        if sel.mean() < 0.4:
            continue
        cs[i] = float(np.median(w[sel]))
    good = np.isfinite(cs)
    # Lücken (dort liegt ein anderes Teil oben, DOM sieht nur das) werden überbrückt, wenn beide Enden gestützt sind
    idx = np.nonzero(good)[0]
    ends = len(idx) > 0 and idx[0] <= 1 and idx[-1] >= len(ks) - 2
    if good.sum() < 3 or not (good.mean() >= 0.6 or (good.mean() >= 0.3 and ends)):
        return None
    kv = ks[good]
    cs = np.interp(ks, ks[good], cs[good])
    if np.abs(np.diff(cs)).max() > 2.0 or np.abs(cs).max() > 9.0 or float(np.median(np.abs(cs))) < 0.8:
        return None
    near = np.min(np.abs(u[:, None] - kv[None, :]), axis=1) < 20.0      # nur Pixel in gestützten Fenstern
    res = (d - np.interp(u, ks, cs))[near]
    if len(res) < 50 or float((np.abs(res) < 0.4).mean()) < 0.6:
        return None
    return ks, cs


def correct_parts(parts, dom: DomMosaic, tri_fn, log=print, dgm=None):
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
        zt = z[top][ok]
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
        sane = slope.max() <= 0.08 and abs(coef[2]) <= 0.08 and np.abs(corr_v).max() <= 6.5 and spread <= 2.5 \
            and inl >= 0.3 and abs(float(np.median(corr_v))) >= 0.6
        ends_ok = sane and _ends_confirm(dgm, ce, cn, ax, ay, u, v, zt,
                                         lambda uu, vv: float(design(np.array([uu]), np.array([vv]))[0] @ coef))
        # sehr eindeutige Messung (lange Elbbrücken der Bahn liegen in LoD2 bis 4,7 m zu tief)
        strong = inl >= 0.85 and spread <= 1.5 and slope.max() <= 0.06 and abs(coef[2]) <= 0.05 \
            and np.abs(corr_v).max() <= 6.0 and abs(float(np.median(corr_v))) >= 0.6 and ok.sum() / (2 * L) >= 2.0
        ends_ok = ends_ok or strong
        if not ends_ok and (inl < 0.55 or slope.max() > 0.08 or abs(coef[2]) > 0.08 or np.abs(corr_v).max() > 4.5 \
                or (quad and ok.sum() / (2 * L) < 3.0) \
                or (spread > 2.5 and inl < 0.6) \
                or (float(np.median(corr_v)) < -0.6 and (inl < 0.8 or ok.sum() < 0.5 * len(z))) \
                or (abs(float(np.median(corr_v))) < 0.6 and np.abs(corr_v).max() < 1.0)):
            # LoD2 ist meist genau: nur grobe Fehler korrigieren
            pw = _piecewise(u, d)
            if pw is not None:
                ks, cs = pw

                def corr_pw(q0, q1, _ks=ks, _cs=cs):
                    return float(np.interp((q0 - ce) * ax + (q1 - cn) * ay, _ks, _cs))

                def shift_pw(polys):
                    return [([(q[0], q[1], q[2] + corr_pw(q[0], q[1])) for q in ext],
                             [[(q[0], q[1], q[2] + corr_pw(q[0], q[1])) for q in hh] for hh in holes]) for ext, holes in polys]
                q = dict(p)
                q["roofs"], q["walls"], q["ground"] = shift_pw(p["roofs"]), shift_pw(p["walls"]), shift_pw(p["ground"])
                q["dom_fix"] = round(float(np.median(cs)), 2)
                out.append(q)
                n_fix += 1
                log(f"  Brücke {p['id']}: DOM-Korrektur abschnittsweise {cs.min():+.2f}..{cs.max():+.2f} m "
                    f"({len(ks)} Stützstellen, Länge {u.max() - u.min():.0f} m)")
                continue
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
            f"{inl*100:.0f} % passend, {int(ok.sum())} Pixel, Länge {2*L:.0f} m{', Enden bestätigt' if ends_ok else ''})")
    log(f"  Brückenkorrektur: {n_fix} von {len(parts)} LoD2-Teilen angepasst")
    return out
