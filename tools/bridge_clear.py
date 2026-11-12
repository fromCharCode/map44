"""Lichtraum unter Brücken: Verkehrsbänder (Fahrbahn, Gleis, Fußweg) und Hilfen, die Pfeiler, Stützen, Bögen und
Widerlager so setzen, dass jede Straße unter einer Brücke frei befahrbar bleibt (genutzt von bridge_arches.py).

Regeln (wie im echten Brückenbau, vgl. data/research/bruecken.json "spans_rule": "Pfeiler nie auf Fahrbahn/Gleis"):
  - ein Pfeiler/Stützenreihe wird entlang der Achse an die nächste freie Stelle verschoben (höchstens max_shift),
  - geht das nicht, werden die Teile seitlich ausgespart, die ein Band schneiden (Pfeiler beiderseits der Straße),
  - Bogenlaibungen über einem Band liegen mindestens Lichtraumhöhe über dessen Oberkante (Bogen wird flacher).
Lichtraum: Kfz 4,5 m, Straßenbahn 4,8 m, Eisenbahn 5,6 m, Fuß/Rad 2,6 m; seitlich Fahrbahnbreite + Zuschlag.
"""
import json
import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

WALK_CLS = {"footway", "path", "cycleway", "steps", "pedestrian", "bridleway"}
CLEAR = {"drive": 4.5, "tram": 4.8, "rail": 5.6, "walk": 2.6}
PAD = {"drive": 0.75, "tram": 0.45, "rail": 0.55, "walk": 0.3}
WALK_W = {"footway": 2.0, "path": 1.5, "cycleway": 2.0, "steps": 2.0, "pedestrian": 4.0, "bridleway": 1.5}


def _coords(g):
    if g.is_empty:
        return []
    if hasattr(g, "geoms"):
        out = []
        for h in g.geoms:
            out += _coords(h)
        return out
    if g.geom_type == "Polygon":
        return list(g.exterior.coords)
    return list(g.coords)


class Under:
    """Verkehrsbänder einer Kachel (ohne Brückenwege selbst). Höhen: Fahrbahn-/Gleisprofil, Fußwege = Gelände."""

    def __init__(self, city, raw_roads, ground, to_local):
        self.items = []
        for r in city.get("roads", []):
            if r.get("bridge") or len(r["pts"]) < 2:
                continue
            self._add([(p[0], p[1], p[2]) for p in r["pts"]], float(r.get("width", 5.0)) * 0.5, "drive")
        for r in city.get("rails", []):
            if r.get("bridge") or len(r["pts"]) < 2:
                continue
            k = "tram" if r.get("kind") == "tram" else "rail"
            self._add([(p[0], p[1], p[2]) for p in r["pts"]], 1.25 if k == "tram" else 1.6, k)
        for el in raw_roads:
            t = el.get("tags") or {}
            cls = t.get("highway")
            if cls not in WALK_CLS or t.get("bridge") not in (None, "no") or t.get("tunnel") not in (None, "no") \
                    or t.get("area") == "yes" or t.get("layer", "0").startswith("-"):
                continue
            g = el.get("geometry") or []
            if len(g) < 2:
                continue
            try:
                w = float(str(t.get("width", "")).split()[0]) if t.get("width") else WALK_W[cls]
            except ValueError:
                w = WALK_W[cls]
            pts = [to_local(p["lon"], p["lat"]) for p in g]
            self._add([(x, z, ground(x, z)) for x, z in pts], min(max(w, 1.0), 6.0) * 0.5, "walk")
        self.tree = STRtree([it[0] for it in self.items]) if self.items else None

    def _add(self, pts3, hw, kind):
        ln = LineString([(p[0], p[1]) for p in pts3])
        if ln.length < 0.5:
            return
        cum = [0.0]
        for a, b in zip(pts3[:-1], pts3[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        band = ln.buffer(hw + PAD[kind], cap_style="flat")
        self.items.append((band, ln, np.array(cum), np.array([p[2] for p in pts3], dtype=float), kind))

    def bands(self, poly, deck_y, gap=2.2):
        """Bänder, die poly schneiden und mindestens gap unter dem Deck verlaufen: [(geom, kind, y, need)]."""
        if self.tree is None or poly.is_empty:
            return []
        out = []
        for i in self.tree.query(poly):
            band, ln, cum, ys, kind = self.items[int(i)]
            g = band.intersection(poly)
            if g.is_empty or g.area < 0.3:
                continue
            part = ln.intersection(g.buffer(0.5))
            cs = _coords(part) or [g.representative_point().coords[0]]
            yv, dv = [], []
            for c in cs[:: max(1, len(cs) // 12)]:
                y = float(np.interp(ln.project(Point(c)), cum, ys))
                yv.append(y)
                d = deck_y(c[0], c[1])
                if d is not None:
                    dv.append(d - y)
            if not yv:
                continue
            if dv and float(np.median(dv)) < gap:
                continue                                      # Zufahrt auf Deckhöhe, keine Unterführung
            y = max(yv)
            out.append((g, kind, y, y + CLEAR[kind]))
        return out


def rect(px, pz, tx, tz, t_half, w_half, v0=None, v1=None):
    """Grundriss eines Pfeilers: t entlang der Achse (tx, tz), seitlich v0..v1 (Standard ±w_half)."""
    nx, nz = -tz, tx
    a, b = (-w_half, w_half) if v0 is None else (v0, v1)
    return Polygon([(px - tx * t_half + nx * a, pz - tz * t_half + nz * a), (px + tx * t_half + nx * a, pz + tz * t_half + nz * a),
                    (px + tx * t_half + nx * b, pz + tz * t_half + nz * b), (px - tx * t_half + nx * b, pz - tz * t_half + nz * b)])


def free_pieces(px, pz, tx, tz, t_half, w_half, bands, y_bot, y_top, min_w=0.8):
    """Seitliche Stücke (v0, v1) des Pfeilergrundrisses, die kein Band schneiden, dessen Lichtraum die Höhe
    y_bot..y_top des Pfeilers berührt."""
    nx, nz = -tz, tx
    r = rect(px, pz, tx, tz, t_half, w_half)
    blocked = []
    for g, kind, y, need in bands:
        if need <= y_bot or y >= y_top:
            continue
        inter = g.intersection(r)
        if inter.is_empty or inter.area < 0.05:
            continue
        vs = [(x - px) * nx + (z - pz) * nz for x, z in _coords(inter)]
        if vs:
            blocked.append((min(vs) - 0.25, max(vs) + 0.25))
    blocked.sort()
    free, cur = [], -w_half
    for a, b in blocked:
        if a > cur:
            free.append((cur, min(a, w_half)))
        cur = max(cur, b)
    if cur < w_half:
        free.append((cur, w_half))
    return [(a, b) for a, b in free if b - a >= min_w]


def best_station(frame, st, lo, hi, t_half, w_half, bands, y_range, max_shift, need_full=False):
    """Beste Station in st ± max_shift (innerhalb lo..hi): möglichst volle freie Breite, dann kleinste Verschiebung.
    frame(s) -> (px, pz, tx, tz); y_range(px, pz) -> (y_bot, y_top). Rückgabe (s, pieces) oder (None, [])."""
    best = None
    steps = int(max_shift / 0.5)
    for k in range(0, 2 * steps + 1):
        d = ((k + 1) // 2) * 0.5 * (1 if k % 2 else -1) if k else 0.0
        s = st + d
        if s < lo or s > hi:
            continue
        px, pz, tx, tz = frame(s)
        yb, yt = y_range(px, pz)
        pcs = free_pieces(px, pz, tx, tz, t_half, w_half, bands, yb, yt)
        fw = sum(b - a for a, b in pcs)
        full = fw >= 2 * w_half - 0.01
        key = (full, round(fw, 1), -abs(d))
        if best is None or key > best[0]:
            best = (key, s, pcs)
        if full and d == 0.0:
            break
    if best is None or (need_full and not best[0][0]):
        return None, []
    return best[1], best[2]


def soffit_floor(bot_at, s_pts, needs, lo, hi):
    """Kleinste Kämpferhöhe (spring floor), bei der die Bogenunterseite an allen Stationen s_pts über needs liegt.
    bot_at(s, floor) ist monoton steigend in floor. Rückgabe floor oder None (nicht erreichbar)."""
    def ok(f):
        return all(bot_at(s, f) >= n for s, n in zip(s_pts, needs))
    if ok(lo):
        return lo
    if not ok(hi):
        return None
    a, b = lo, hi
    for _ in range(30):
        m = 0.5 * (a + b)
        if ok(m):
            b = m
        else:
            a = m
    return b


def raw_roads(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("elements", [])
    except (OSError, ValueError):
        return []
