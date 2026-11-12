"""Steinbögen unter historischen Bogenbrücken (Nachbearbeitung): city["bridge_arches"] = {"tris": [...], "n": [...]}

  python tools/bridge_arches.py [E,N ...]     (ohne Argument: alle Kacheln)

Für jede Brücke der Bauart sandstein_bogen bzw. bahn_eue_historisch aus data/research/bruecken.json (Spannweiten,
Pfeilerzahl, Bogenstich) entsteht unter dem befahrbaren Deck: Stirnwände (Zwickel) mit Bogenöffnungen auf beiden
Seiten, Bogenlaibungen (Unterseite der Gewölbe), Pfeiler mit spitzen Wellenbrechern. Achse = OSM-Brückenweg(e),
Bogenfolge mittig auf der Achse. Höhe: Fahrbahn (city roads) bzw. LoD2-Deck; Boden = Gelände/Elbspiegel.
Ausgabe als Dreiecksliste [x, y, z, ...] mit Normalen je Dreieck (Sandstein im Spiel).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import linemerge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge_clear import Under, best_station, raw_roads, soffit_floor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
RESEARCH = ROOT / "data" / "research" / "bruecken.json"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
TYPES = ("sandstein_bogen", "bahn_eue_historisch")


def water_y(x, z):
    return 2.8535e-4 * x + 1.0877e-4 * z - 8.4254           # Elbspiegel im Spiel (boats.gd)


def _local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def _lit(v):
    """Felder, die als Python-Darstellung (Text) vorliegen, einlesen."""
    if isinstance(v, str) and v[:1] in "{[":
        import ast
        try:
            return ast.literal_eval(v)
        except Exception:
            import re
            m = re.search(r"'piers':\s*\[([^\]]*)\]", v)
            if m:
                return {"piers": [float(x) for x in m.group(1).split(",") if x.strip()]}
            return None
    return v


def arch_bridges():
    if not RESEARCH.exists():
        return []
    out = []
    for b in json.loads(RESEARCH.read_text(encoding="utf-8")).get("bridges", []):
        if not b.get("spans_m") or b.get("type") in ("abgerissen", "fuss_holz_klein"):
            continue
        ids = set()
        for w in b.get("osm_way_ids") or []:
            try:
                ids.add(int(str(w).lstrip("w")))
            except ValueError:
                pass
        if ids:
            b = dict(b)
            b["arch"] = _lit(b.get("arch")) or {}
            b["pier_stations_m"] = _lit(b.get("pier_stations_m"))
            out.append((b, ids))
    return out


def _beam(tris, norms, a, b, side, w, h):
    """Kastenträger von a nach b (x, y, z), Breite w quer (side = (nx, nz)), Höhe h; Dreiecke mit Normalen."""
    ax, ay, az = a
    bx, by, bz = b
    sx, sz = side[0] * w * 0.5, side[1] * w * 0.5
    hh = h * 0.5
    c = [(ax - sx, ay - hh, az - sz), (ax + sx, ay - hh, az + sz), (ax + sx, ay + hh, az + sz), (ax - sx, ay + hh, az - sz),
         (bx - sx, by - hh, bz - sz), (bx + sx, by - hh, bz + sz), (bx + sx, by + hh, bz + sz), (bx - sx, by + hh, bz - sz)]
    faces = [(0, 1, 5, 4, (0, -1, 0)), (3, 7, 6, 2, (0, 1, 0)), (0, 4, 7, 3, (-side[0], 0, -side[1])),
             (1, 2, 6, 5, (side[0], 0, side[1]))]
    for i0, i1, i2, i3, n in faces:
        for tri in ((i0, i1, i2), (i0, i2, i3)):
            for i in tri:
                tris.extend(c[i])
            norms.extend([round(n[0], 3), round(n[1], 3), round(n[2], 3)])


def _strut(tris, norms, a, b, side, w, t):
    """Schräge Strebe von a nach b: Querschnitt w (quer zur Brücke, side) × t (senkrecht zu Strebe und side)."""
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    dx, dy, dz = dx / L, dy / L, dz / L
    sx, sy, sz = side[0], 0.0, side[1]
    ux, uy, uz = dy * sz - dz * sy, dz * sx - dx * sz, dx * sy - dy * sx      # u = d × s
    ul = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
    ux, uy, uz = ux / ul, uy / ul, uz / ul
    hw, ht = w * 0.5, t * 0.5

    def c(p, i, j):
        return (p[0] + sx * hw * i + ux * ht * j, p[1] + sy * hw * i + uy * ht * j, p[2] + sz * hw * i + uz * ht * j)
    cs = [c(a, -1, -1), c(a, 1, -1), c(a, 1, 1), c(a, -1, 1), c(b, -1, -1), c(b, 1, -1), c(b, 1, 1), c(b, -1, 1)]
    faces = [(0, 4, 5, 1, (-ux, -uy, -uz)), (3, 2, 6, 7, (ux, uy, uz)), (0, 3, 7, 4, (-sx, -sy, -sz)),
             (1, 5, 6, 2, (sx, sy, sz))]
    for i0, i1, i2, i3, n in faces:
        for tri in ((i0, i1, i2), (i0, i2, i3)):
            for i in tri:
                tris.extend(cs[i])
            norms.extend([round(n[0], 3), round(n[1], 3), round(n[2], 3)])


def generic_piers(city, skip_ids, under, ground, deck_y, in_tile, report):
    """Standardpfeiler (früher roads.gd _piers) für Brückenwege ohne recherchiertes Bauwerk und OSM-Plattenbrücken:
    alle ~30 m bei Brücken ab 40 m, wenn das Deck > 1,5 m über dem Gelände liegt – aber nie auf einem Verkehrsband
    (verschoben bis ±40 % des Pfeilerabstands, sonst seitlich ausgespart). [x, z, yaw, breite, oben, unten, dicke]"""
    out = []
    slab_ids = {int(b["id"]) for b in city.get("bridges", [])}
    items = []
    for r in city.get("roads", []):
        if r.get("bridge") and int(r["id"]) not in slab_ids and int(r["id"]) not in skip_ids:
            items.append((r["pts"], float(r["width"]) + 2.0, 1.0, r.get("name") or r["id"]))
    for b in city.get("bridges", []):
        w = max(float(b["width"]), 2.5) + (2.0 if b.get("kind") == "drive" else 0.0)
        items.append((b["pts"], w, 0.9, b["id"]))
    for pts, w, thick, nm in items:
        if len(pts) < 2:
            continue
        cum = [0.0]
        for a, b in zip(pts[:-1], pts[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        total = cum[-1]
        if total < 40.0:
            continue
        n = int(total / 30.0)
        spacing = total / (n + 1)
        line = LineString([(p[0], p[1]) for p in pts])
        ys = np.array([p[2] for p in pts], dtype=float)
        cum = np.array(cum)

        def frame(sv):
            sv = min(max(sv, 0.0), total)
            p = line.interpolate(sv)
            q = line.interpolate(min(sv + 1.0, total))
            r0 = line.interpolate(max(sv - 1.0, 0.0))
            tx, tz = q.x - r0.x, q.y - r0.y
            tl = math.hypot(tx, tz) or 1.0
            return p.x, p.y, tx / tl, tz / tl

        def yat(sv):
            return float(np.interp(sv, cum, ys))
        wp = w * 0.55
        foot = line.buffer(wp * 0.5 + 1.0, cap_style="flat")
        bands = under.bands(foot, lambda x, z: yat(line.project(Point(x, z))))
        for k in range(1, n + 1):
            st = spacing * k
            px, pz, tx, tz = frame(st)
            if not in_tile(px, pz):
                continue
            if yat(st) - thick - ground(px, pz) < 1.5:
                continue

            def yr(x_, z_):
                return ground(x_, z_) - 2.5, yat(line.project(Point(x_, z_))) - thick
            st2, pcs = best_station(frame, st, 2.0, total - 2.0, 1.2, wp * 0.5, bands, yr, spacing * 0.4)
            if st2 is None or not pcs:
                report.append(f"Standardpfeiler {nm} bei s={st:.0f} entfällt (Verkehrsband)")
                continue
            px, pz, tx, tz = frame(st2)
            top = yat(st2) - thick
            gy = ground(px, pz)
            if top - gy < 1.5:
                continue
            if abs(st2 - st) > 0.01 or len(pcs) > 1 or pcs[0][1] - pcs[0][0] < wp - 0.02:
                report.append(f"Standardpfeiler {nm} s={st:.0f} -> {st2:.1f}, {len(pcs)} Teil(e)")
            yaw = math.atan2(tx, tz)
            for v0, v1 in pcs:
                vc = 0.5 * (v0 + v1)
                out.append([round(px - tz * vc, 2), round(pz + tx * vc, 2), round(yaw, 3), round(v1 - v0, 2),
                            round(top, 2), round(gy - 2.5, 2), 2.4])
    return out


def tile_arches(name, bridges):
    d = TILES / name
    cf = d / "city.json"
    of = RAW / name / "osm" / "bridges.json"
    if not cf.exists() or not of.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)

    def ground(x, z):
        c = min(max(x - x0 - 0.5, 0.0), 1998.999)
        r = min(max(z - z0 - 0.5, 0.0), 1998.999)
        c0, r0 = int(c), int(r)
        fc, fr = c - c0, r - r0
        top = ter[r0, c0] * (1 - fc) + ter[r0, c0 + 1] * fc
        bot = ter[r0 + 1, c0] * (1 - fc) + ter[r0 + 1, c0 + 1] * fc
        return float(top * (1 - fr) + bot * fr)

    ways = {}
    for el in json.loads(of.read_text(encoding="utf-8")).get("elements", []):
        g = el.get("geometry") or []
        if el.get("type") == "way" and len(g) >= 2:
            ways[el["id"]] = [_local(p["lon"], p["lat"]) for p in g]
    # Fahrbahnhöhen der Brückenwege (city roads/rails mit bridge=True), entlang der Linie interpoliert
    from shapely.strtree import STRtree
    dlines = []
    for r in city.get("roads", []) + city.get("rails", []):
        if r.get("bridge") and len(r["pts"]) >= 2:
            ln = LineString([(p[0], p[1]) for p in r["pts"]])
            if ln.length > 0.5:
                cum = [0.0]
                for a_, b_ in zip(r["pts"][:-1], r["pts"][1:]):
                    cum.append(cum[-1] + math.hypot(b_[0] - a_[0], b_[1] - a_[1]))
                dlines.append((ln, np.array(cum), np.array([p[2] for p in r["pts"]])))
    dtree = STRtree([d[0] for d in dlines]) if dlines else None

    def deck_y(x, z):
        if dtree is None:
            return None
        p = Point(x, z)
        best = None
        for i in dtree.query(p.buffer(15.0)):
            ln, cum, ys = dlines[int(i)]
            dd = ln.distance(p)
            if dd < 15.0 and (best is None or dd < best[0]):
                best = (dd, float(np.interp(ln.project(p), cum, ys)))
        return best[1] if best else None

    tris, norms = [], []

    def tri(a, b, c, n):
        tris.extend([*a, *b, *c])
        norms.extend([round(n[0], 3), round(n[1], 3), round(n[2], 3)])

    def quad(a, b, c, dpt, n):
        tri(a, b, c, n)
        tri(a, c, dpt, n)

    xmin, xmax, zmin, zmax = x0, x0 + 2000.0, z0, z0 + 2000.0
    count = 0
    way_ids, lod2_ids = set(), set()
    piers_out = []
    steel_tris, steel_n = [], []
    steel_col = "#c9ccd0"
    groups = {}                                   # (mat, farbe) -> [tris, n]: Blechträger, Gussstützen, Betonstirn
    report = []                                   # Lichtraum nicht erreichbar (Deck zu tief) / Pfeiler verschoben
    under = Under(city, raw_roads(RAW / name / "osm" / "roads.json"), ground, _local)

    def group(mat, col):
        return groups.setdefault((mat, col), [[], []])

    def in_tile(x, z):
        return xmin <= x < xmax and zmin <= z < zmax

    def axis_frame(axis, L):
        def frame(sv):
            p = axis.interpolate(min(max(sv, 0.0), L))
            q = axis.interpolate(min(sv + 1.0, L))
            r0 = axis.interpolate(max(sv - 1.0, 0.0))
            tx, tz = q.x - r0.x, q.y - r0.y
            tl = math.hypot(tx, tz) or 1.0
            return p.x, p.y, tx / tl, tz / tl
        return frame

    def footprint(axis, L, hw):
        cs = [axis.interpolate(v).coords[0] for v in np.linspace(0.0, L, max(2, int(L / 2.0) + 1))]
        return LineString(cs).buffer(hw, cap_style="flat")

    def along(axis, g):
        """Projektion einer Fläche auf die Achse: (s_lo, s_hi)"""
        from bridge_clear import _coords
        ss = [axis.project(Point(c)) for c in _coords(g)]
        return (min(ss), max(ss)) if ss else (0.0, 0.0)

    def gquad(G, a, b, c, d_, n):
        nn = [round(n[0], 3), round(n[1], 3), round(n[2], 3)]
        G[0].extend([*a, *b, *c, *a, *c, *d_])
        G[1].extend(nn + nn)

    def box_poly(G, corners, y0, y1, top=True):
        """senkrechter Quader über einem Viereck (x, z) von y0 bis y1; G = None -> Sandstein (tris/norms)"""
        cx = sum(c[0] for c in corners) / 4.0
        cz = sum(c[1] for c in corners) / 4.0
        for i in range(4):
            a, b2 = corners[i], corners[(i + 1) % 4]
            ex, ez = b2[0] - a[0], b2[1] - a[1]
            el = math.hypot(ex, ez) or 1.0
            nx, nz = ez / el, -ex / el
            if (0.5 * (a[0] + b2[0]) - cx) * nx + (0.5 * (a[1] + b2[1]) - cz) * nz < 0:
                nx, nz = -nx, -nz
            qa, qb, qc, qd = (a[0], y0, a[1]), (b2[0], y0, b2[1]), (b2[0], y1, b2[1]), (a[0], y1, a[1])
            if G is None:
                quad(qa, qb, qc, qd, (nx, 0.0, nz))
            else:
                gquad(G, qa, qb, qc, qd, (nx, 0.0, nz))
        if top:
            qs = [(c[0], y1, c[1]) for c in corners]
            if G is None:
                quad(qs[0], qs[1], qs[2], qs[3], (0.0, 1.0, 0.0))
            else:
                gquad(G, qs[0], qs[1], qs[2], qs[3], (0.0, 1.0, 0.0))

    def rect_c(px, pz, tx, tz, s0, s1, v0, v1):
        """Ecken eines Vierecks: entlang der Achse s0..s1 (relativ zu p), seitlich v0..v1"""
        nx, nz = -tz, tx
        return [(px + tx * s0 + nx * v0, pz + tz * s0 + nz * v0), (px + tx * s1 + nx * v0, pz + tz * s1 + nz * v0),
                (px + tx * s1 + nx * v1, pz + tz * s1 + nz * v1), (px + tx * s0 + nx * v1, pz + tz * s0 + nz * v1)]

    def truss_bridge(b, axis, L):
        """Stahlfachwerk mit untenliegender Fahrbahn (Hafenbrücken, kurze EÜ): zwei Fachwerkwände an den Deckrändern,
        Rautenfachwerk mit Pfosten, Obergurt an den Enden abgerundet, oberer Windverband (über dem Lichtraum),
        Endportale. Farbe aus der Recherche."""
        cols = b.get("colors") or {}
        col = cols.get("steel") or (cols.get("steel_rail_bridge") if "Eisenbahn" in (b.get("traffic") or []) else cols.get("steel_road_bridge")) or "#3d5a8a"
        G = group("steel", col)
        try:
            width = float(b.get("width_m") or 0.0)
        except (TypeError, ValueError):
            width = 0.0
        if not (3.0 <= width <= 20.0):
            width = 7.0
        hw = width * 0.5
        H = min(max(L / 8.0, 4.8), 9.0)                    # Systemhöhe (Lichtraum über der Fahrbahn bleibt frei)
        frame = axis_frame(axis, L)
        npan = max(2, int(round(L / max(H * 0.9, 3.5))))
        ss = [L * i / npan for i in range(npan + 1)]

        def top_h(sv):
            u = min(sv, L - sv) / max(L * 0.16, 1e-3)          # Abrundung im ersten/letzten Sechstel
            return H * (1.0 if u >= 1.0 else math.sqrt(max(0.0, 1.0 - (1.0 - u) ** 2)) * 0.75 + 0.25)
        node = []
        any_in = False
        for sv in ss:
            px, pz, tx, tz = frame(sv)
            yd = deck_y(px, pz)
            node.append((px, pz, tx, tz, yd))
            any_in = any_in or in_tile(px, pz)
        if not any_in or all(nd[4] is None for nd in node):
            return False
        last = next(nd[4] for nd in node if nd[4] is not None)
        node = [(px, pz, tx, tz, (yd if yd is not None else last)) for px, pz, tx, tz, yd in node]

        def pnt(i, sd, up):
            px, pz, tx, tz, yd = node[i]
            y0 = yd - 0.35
            return (px - tz * hw * sd, y0 + (top_h(ss[i]) if up else 0.0), pz + tx * hw * sd)
        for i in range(npan):
            mx = 0.5 * (node[i][0] + node[i + 1][0])
            mz = 0.5 * (node[i][1] + node[i + 1][1])
            if not in_tile(mx, mz):
                continue
            tx, tz = node[i][2], node[i][3]
            for sd in (1.0, -1.0):
                side = (-tz * sd, tx * sd)
                a0, a1 = pnt(i, sd, False), pnt(i + 1, sd, False)
                t0, t1 = pnt(i, sd, True), pnt(i + 1, sd, True)
                _strut(G[0], G[1], a0, a1, (tx, tz), 0.45, 0.55)        # Untergurt
                _strut(G[0], G[1], t0, t1, (tx, tz), 0.45, 0.45)        # Obergurt
                _strut(G[0], G[1], a0, t1, side, 0.28, 0.22)           # Rautenfachwerk: beide Diagonalen
                _strut(G[0], G[1], t0, a1, side, 0.28, 0.22)
                _strut(G[0], G[1], a0, t0, side, 0.3, 0.25)             # Pfosten
                if i == npan - 1:
                    _strut(G[0], G[1], a1, t1, side, 0.3, 0.25)
            # oberer Windverband (nur wo das Fachwerk hoch genug ist) und Querträger unter dem Deck
            if top_h(ss[i]) > 4.6 and top_h(ss[i + 1]) > 4.6:
                l0, r0 = pnt(i, 1.0, True), pnt(i, -1.0, True)
                l1, r1 = pnt(i + 1, 1.0, True), pnt(i + 1, -1.0, True)
                _strut(G[0], G[1], l0, r1, (0.0, 1.0) if False else (tx, tz), 0.18, 0.18)
                _strut(G[0], G[1], r0, l1, (tx, tz), 0.18, 0.18)
                _strut(G[0], G[1], l0, r0, (tx, tz), 0.25, 0.3)
            lb, rb = pnt(i, 1.0, False), pnt(i, -1.0, False)
            _strut(G[0], G[1], (lb[0], lb[1] - 0.5, lb[2]), (rb[0], rb[1] - 0.5, rb[2]), (tx, tz), 0.3, 0.5)
        return True

    def lod2_y(x, z, ids=None):
        """Oberkante der LoD2-Decks (nach DOM-Korrektur) an (x, z), optional nur bestimmte Teile"""
        best = None
        for bm in city.get("bridge_meshes", []):
            if ids and bm.get("id") not in ids:
                continue
            t = bm.get("top0") or bm.get("top") or []
            for k in range(0, len(t) - 8, 9):
                x0_, y0_, z0_, x1_, y1_, z1_, x2_, y2_, z2_ = t[k:k + 9]
                d = (z1_ - z2_) * (x0_ - x2_) + (x2_ - x1_) * (z0_ - z2_)
                if abs(d) < 1e-9:
                    continue
                l1 = ((z1_ - z2_) * (x - x2_) + (x2_ - x1_) * (z - z2_)) / d
                l2 = ((z2_ - z0_) * (x - x2_) + (x0_ - x2_) * (z - z2_)) / d
                l3 = 1.0 - l1 - l2
                if min(l1, l2, l3) >= -0.02:
                    y = l1 * y0_ + l2 * y1_ + l3 * y2_
                    best = y if best is None else max(best, y)
        return best

    def cable_stayed(b, segs):
        """Schrägseil-Fußgängerbrücke (Pieschener Molenbrücke): Schrägseilteil = längster OSM-Weg, Rückfeld am freien
        Ende (Länge Schrägseilteil − Hauptfeld), Doppelrohr-Pylon (Höhe aus "special"), Fächerseile in zwei Ebenen."""
        import re
        if not segs:
            return False
        main = max(segs, key=lambda g: g.length)
        others = [g for g in segs if g is not main]
        cs = list(main.coords)
        if others and min(Point(cs[0]).distance(o) for o in others) < min(Point(cs[-1]).distance(o) for o in others):
            main = LineString(cs[::-1])                     # freies Ende zuerst
        Lm = main.length
        span = float(max(float(v) for v in b["spans_m"]))
        back = max(Lm - span, 8.0)
        hgt = 34.5
        for sp_ in b.get("special") or []:
            m_ = re.search(r"Pylon\s+([0-9]+[,.]?[0-9]*)\s*m", str(sp_))
            if m_:
                hgt = float(m_.group(1).replace(",", "."))
        try:
            hw = max(float(b.get("width_m") or 3.4) * 0.5, 1.4)
        except (TypeError, ValueError):
            hw = 1.7
        frame = axis_frame(main, Lm)
        lod = b.get("lod2")
        lod = _lit(lod) if isinstance(lod, str) else lod
        lids = set((lod or {}).get("ids") or []) if isinstance(lod, dict) else set()

        def dy(x, z):
            v = deck_y(x, z)
            return v if v is not None else lod2_y(x, z, lids or None)
        px, pz, tx, tz = frame(back)
        if not in_tile(px, pz):
            return False
        yd = dy(px, pz)
        if yd is None:
            return False
        gnd = max(ground(px, pz), water_y(px, pz))
        top_y = gnd + hgt
        nx, nz = -tz, tx
        G = group("steel", "#8a8d8f")
        C = group("steel", "#3c3f42")
        d45 = ((tx - tz) / math.sqrt(2.0), (tz + tx) / math.sqrt(2.0))
        tops = []
        for sd in (1.0, -1.0):
            foot = (px + nx * (hw + 1.4) * sd - tx * 1.2 * sd, gnd - 0.5, pz + nz * (hw + 1.4) * sd - tz * 1.2 * sd)
            tip = (px + nx * 0.6 * sd, top_y, pz + nz * 0.6 * sd)
            for side in ((tx, tz), d45):
                _strut(G[0], G[1], foot, tip, side, 0.75, 0.75)
            tops.append(tip)
        # Seile: 5 ins Hauptfeld, 4 ins Rückfeld, je Ebene (Deckrand)
        for cnt, base, step, s0, ds in ((5, 2.5, 1.6, back + span * 0.25, span * 0.17), (4, 3.0, 1.8, back * 0.15, back * 0.22)):
            for k in range(cnt):
                sv = min(s0 + ds * k, Lm - 1.0)
                qx, qz, qtx, qtz = frame(sv)
                qy = dy(qx, qz)
                if qy is None:
                    continue
                for sd in (1.0, -1.0):
                    a3 = (qx - qtz * hw * sd, qy + 0.9, qz + qtx * hw * sd)
                    t3 = tops[0 if sd > 0 else 1]
                    _strut(C[0], C[1], a3, (t3[0], t3[1] - base - step * k, t3[2]), (qtx, qtz), 0.07, 0.07)
        return True

    def girder_bridge(b, axis, L):
        """Eisenbahnüberführung der Hochlegung (bahn_eue_historisch): genietete Blechträger (original) bzw.
        Betonstirn (erneuert) an beiden Deckkanten, Untersicht, Sandsteinwiderlager mit Gesims an den Enden,
        bei mehreren Feldern gusseiserne Pendelstützen mit Kapitell – nur außerhalb der Verkehrsbänder."""
        from bridge_clear import free_pieces
        var = b.get("variant") or "erneuert"
        cols = b.get("colors") or {}
        try:
            width = float(b.get("width_m") or 0.0)
        except (TypeError, ValueError):
            width = 0.0
        if not (4.0 <= width <= 40.0):
            width = 10.0
        hw = width * 0.5
        frame = axis_frame(axis, L)
        try:
            depth = float(b.get("deck_depth_m") or 0.0)
        except (TypeError, ValueError):
            depth = 0.0
        if not (0.6 <= depth <= 2.2):
            depth = 1.6 if var == "original" else 1.2
        stations = list(np.linspace(0.0, L, max(2, int(L / 1.25) + 1)))
        fr = [frame(sv) for sv in stations]
        yds = [deck_y(f[0], f[1]) for f in fr]
        if all(v is None for v in yds):
            return False
        last = next(v for v in yds if v is not None)
        for i, v in enumerate(yds):
            if v is None:
                yds[i] = last
            last = yds[i]
        bands = under.bands(footprint(axis, L, hw + 0.5), deck_y)
        need_of = []
        for g_, k_, y_, need in bands:
            lo, hi = along(axis, g_)
            need_of.append((lo, hi, need, k_, y_))
        dmin = depth
        worst = None
        for sv, yd in zip(stations, yds):
            for lo, hi, need, k_, y_ in need_of:
                if lo - 0.5 <= sv <= hi + 0.5 and yd - 0.15 - need < dmin:
                    dmin = yd - 0.15 - need
                    worst = (k_, yd - 0.15 - y_)
        if dmin < depth:
            if dmin < 0.5 and worst is not None:
                report.append(f"{b.get('name')}: Lichtraum {worst[0]} nur {worst[1] - 0.5:.2f} m (Deck zu tief)")
            depth = max(dmin, 0.5)
        steel_c = cols.get("steel") or ("#3a3632" if var == "original" else "#4a4846")
        G_web = group("steel", steel_c) if var == "original" else group("concrete", cols.get("concrete_deck") or "#b5b0a5")
        G_st = group("steel", steel_c)
        any_in = False
        for i in range(len(stations) - 1):
            (ax_, az_, atx, atz), (bx_, bz_, btx, btz) = fr[i], fr[i + 1]
            if not in_tile(0.5 * (ax_ + bx_), 0.5 * (az_ + bz_)):
                continue
            any_in = True
            ya, yb_ = yds[i], yds[i + 1]
            for sd in (1.0, -1.0):
                anx, anz = -atz * sd, atx * sd
                bnx, bnz = -btz * sd, btx * sd
                A = (ax_ + anx * hw, ya - 0.05, az_ + anz * hw)
                B = (bx_ + bnx * hw, yb_ - 0.05, bz_ + bnz * hw)
                Ab = (A[0], ya - 0.15 - depth, A[2])
                Bb = (B[0], yb_ - 0.15 - depth, B[2])
                gquad(G_web, Ab, Bb, B, A, (anx, 0.0, anz))                # Außenseite (Stirn/Steg)
                Ai = (A[0] - anx * 0.03, A[1], A[2] - anz * 0.03)
                Bi = (B[0] - bnx * 0.03, B[1], B[2] - bnz * 0.03)
                gquad(G_web, (Ai[0], Ab[1], Ai[2]), (Bi[0], Bb[1], Bi[2]), Bi, Ai, (-anx, 0.0, -anz))
                if var == "original":
                    # Gurte oben/unten (0,45 m breit) – der Untergurt steht nach außen vor
                    for yy, hh in ((ya - 0.15 - depth + 0.03, 0.06), (ya - 0.08, 0.06)):
                        _beam(G_st[0], G_st[1], (A[0] + anx * 0.12, yy, A[2] + anz * 0.12),
                              (B[0] + bnx * 0.12, yy + (yb_ - ya), B[2] + bnz * 0.12), (anx, anz), 0.45, hh)
                    # senkrechte Aussteifungen alle 1,25 m
                    _strut(G_st[0], G_st[1], (A[0] + anx * 0.07, Ab[1] + 0.06, A[2] + anz * 0.07),
                           (A[0] + anx * 0.07, A[1] - 0.06, A[2] + anz * 0.07), (atx, atz), 0.12, 0.12)
            # Untersicht zwischen den Trägern
            L1 = (ax_ - atz * hw, ya - 0.15 - depth + 0.02, az_ + atx * hw)
            R1 = (ax_ + atz * hw, ya - 0.15 - depth + 0.02, az_ - atx * hw)
            L2 = (bx_ - btz * hw, yb_ - 0.15 - depth + 0.02, bz_ + btx * hw)
            R2 = (bx_ + btz * hw, yb_ - 0.15 - depth + 0.02, bz_ - btx * hw)
            gquad(G_st if var == "original" else G_web, R1, R2, L2, L1, (0.0, -1.0, 0.0))
        if not any_in:
            return False
        # Widerlager (Elbsandstein, bossiert) mit Abschlussgesims an beiden Enden, nur außerhalb der Bänder
        for s_end, sgn in ((0.0, -1.0), (L, 1.0)):
            px, pz, tx, tz = frame(s_end)
            if not in_tile(px, pz):
                continue
            yd = deck_y(px, pz)
            if yd is None:
                continue
            yb = yd - 0.15 - depth
            g_in = ground(px - sgn * tx * 2.5, pz - sgn * tz * 2.5)
            gb = min(g_in, ground(px, pz)) - 0.5
            if yb - gb < 0.8:
                continue
            cx, cz = px + sgn * tx * 0.8, pz + sgn * tz * 0.8
            from shapely.geometry import Polygon as _Poly
            ab_poly = _Poly(rect_c(px, pz, tx, tz, -sgn * 0.3, sgn * 1.9, -hw - 1.1, hw + 1.1))
            ab_bands = under.bands(ab_poly, lambda x_, z_, _y=yd: _y)   # Straßen neben/hinter dem Brückenende
            pcs = free_pieces(cx, cz, tx, tz, 0.8, hw + 0.8, bands + ab_bands, gb, yb)
            for v0, v1 in pcs:
                box_poly(None, rect_c(px, pz, tx, tz, 0.0, sgn * 1.6, v0, v1), gb, yb)
                box_poly(None, rect_c(px, pz, tx, tz, -sgn * 0.15, sgn * 1.6, v0 - 0.12, v1 + 0.12), yb - 0.35, yb)
        # Pendelstützen (Gusseisen) an den Feldgrenzen, zum Bordstein hin verschoben
        sp = [float(v) for v in b.get("spans_m") or []]
        if len(sp) >= 2:
            S = sum(sp)
            k = L / S
            acc = 0.0
            G_c = group("cast", cols.get("piers") or "#4a463e")
            for v in sp[:-1]:
                acc += v * k

                def yr(px, pz):
                    return ground(px, pz) - 0.3, (deck_y(px, pz) or yds[0]) - 0.15 - depth
                st2, pcs = best_station(frame, acc, 1.5, L - 1.5, 0.35, hw - 0.4, bands, yr, max(1.0, min(sp) * k * 0.3))
                if st2 is None or not pcs:
                    report.append(f"{b.get('name')}: Stützenreihe bei s={acc:.0f} entfällt (Verkehrsband)")
                    continue
                px, pz, tx, tz = frame(st2)
                if not in_tile(px, pz):
                    continue
                yb = (deck_y(px, pz) or yds[0]) - 0.15 - depth
                d45 = ((tx - tz) / math.sqrt(2.0), (tz + tx) / math.sqrt(2.0))
                for v0, v1 in pcs:
                    nc = max(1, int((v1 - v0 - 0.7) / 3.5) + 1)
                    for j in range(nc):
                        vc = v0 + 0.35 + ((v1 - v0 - 0.7) * j / (nc - 1) if nc > 1 else 0.5 * (v1 - v0 - 0.7))
                        cx, cz = px - tz * vc, pz + tx * vc
                        g0 = ground(cx, cz) - 0.2
                        if yb - g0 < 1.5:
                            continue
                        for sd_ in ((tx, tz), d45):                 # achteckiger Schaft
                            _strut(G_c[0], G_c[1], (cx, g0, cz), (cx, yb - 0.45, cz), sd_, 0.34, 0.34)
                        _strut(G_c[0], G_c[1], (cx, yb - 0.45, cz), (cx, yb, cz), (tx, tz), 0.8, 0.8)   # Kapitell
                        _strut(G_c[0], G_c[1], (cx, g0, cz), (cx, g0 + 0.7, cz), (tx, tz), 0.6, 0.6)    # Sockel
        return True
    for b, ids in bridges:
        segs = [LineString(ways[i]) for i in ids if i in ways]
        if not segs:
            continue
        m = linemerge(segs)
        axis = max(getattr(m, "geoms", [m]), key=lambda g: g.length)
        L = axis.length
        arch_i = b.get("arch") or {}
        ps_i = b.get("pier_stations_m") if isinstance(b.get("pier_stations_m"), dict) else {}
        if isinstance(arch_i, dict) and "Stahlbogen" in str(arch_i.get("shape", "")) and ps_i.get("arch_springing"):
            # Stahlbogen über der Fahrbahn (Waldschlößchenbrücke): zwei Kastenbögen + Hänger
            brg = b.get("bearing_deg")
            p_a, p_b = axis.coords[0], axis.coords[-1]
            ax_brg = math.degrees(math.atan2(p_b[0] - p_a[0], -(p_b[1] - p_a[1]))) % 360.0
            if brg is not None and abs(((ax_brg - float(brg)) + 180.0) % 360.0 - 180.0) > 90.0:
                axis = LineString(list(axis.coords)[::-1])
            # Bogenebenen symmetrisch zur Brückenmitte: Achse = Mitte zwischen den Richtungsfahrbahnen (die längste
            # OSM-Linie ist nur eine davon – Hänger standen sonst auf der Gegenfahrbahn)
            drive_lines = [LineString([(q[0], q[1]) for q in r["pts"]]) for r in city.get("roads", [])
                           if r.get("bridge") and int(r["id"]) in ids and len(r["pts"]) >= 2]
            lat = []
            for dl in drive_lines:
                for k_ in range(11):
                    q = dl.interpolate(dl.length * k_ / 10.0)
                    s_ = axis.project(q)
                    a_ = axis.interpolate(max(s_ - 1.0, 0.0))
                    b_ = axis.interpolate(min(s_ + 1.0, axis.length))
                    tl = math.hypot(b_.x - a_.x, b_.y - a_.y) or 1.0
                    c_ = axis.interpolate(s_)
                    lat.append(((q.x - c_.x) * (-(b_.y - a_.y) / tl) + (q.y - c_.y) * ((b_.x - a_.x) / tl)))
            if lat and max(lat) - min(lat) > 3.0:
                cen = 0.5 * (max(lat) + min(lat))
                pts_ = []
                for v in np.linspace(0.0, axis.length, max(2, int(axis.length / 2.0) + 1)):
                    a_ = axis.interpolate(max(v - 1.0, 0.0))
                    b_ = axis.interpolate(min(v + 1.0, axis.length))
                    tl = math.hypot(b_.x - a_.x, b_.y - a_.y) or 1.0
                    c_ = axis.interpolate(v)
                    pts_.append((c_.x - (b_.y - a_.y) / tl * cen, c_.y + (b_.x - a_.x) / tl * cen))
                axis = LineString(pts_)
                L = axis.length
            sa, sb = (float(v) for v in ps_i["arch_springing"][:2])
            rises = arch_i.get("rise_m") or [26.0]
            crown_over_water = float(rises[0]) if rises and rises[0] else 26.0
            off = min(float(b.get("width_m") or 24.0) * 0.5 - 2.5, 12.0)
            col = (b.get("colors") or {}).get("steel_arch") or "#c9ccd0"
            mid = 0.5 * (sa + sb)
            pm = axis.interpolate(mid)
            yc = water_y(pm.x, pm.y) + crown_over_water
            n_seg = 48
            prev = None
            for k in range(n_seg + 1):
                sv = sa + (sb - sa) * k / n_seg
                p = axis.interpolate(min(max(sv, 0.0), L))
                q = axis.interpolate(min(sv + 1.0, L))
                r0 = axis.interpolate(max(sv - 1.0, 0.0))
                tx, tz = q.x - r0.x, q.y - r0.y
                tl = math.hypot(tx, tz) or 1.0
                tx, tz = tx / tl, tz / tl
                nx, nz = -tz, tx
                ysp = max(ground(p.x, p.y), water_y(p.x, p.y)) + 1.0
                u = (sv - mid) / (0.5 * (sb - sa))
                y = ysp + (yc - ysp) * (1.0 - u * u)
                cur = (p.x, p.y, y, nx, nz, tx, tz)
                if prev is not None and (xmin <= p.x < xmax and zmin <= p.y < zmax):
                    for sd in (1.0, -1.0):
                        a3 = (prev[0] + prev[3] * off * sd, prev[2], prev[1] + prev[4] * off * sd)
                        b3 = (cur[0] + cur[3] * off * sd, cur[2], cur[1] + cur[4] * off * sd)
                        _beam(steel_tris, steel_n, a3, b3, (cur[3], cur[4]), 1.0, 1.7)
                        # Hänger zur Fahrbahn alle 2 Segmente, wo der Bogen über dem Deck liegt
                        yd = deck_y(cur[0], cur[1])
                        if k % 2 == 0 and yd is not None and cur[2] > yd + 2.0:
                            h0 = (b3[0], yd + 0.3, b3[2])
                            _beam(steel_tris, steel_n, h0, (b3[0], cur[2] - 0.8, b3[2]), (cur[3], cur[4]), 0.12, 0.12)
                prev = cur
            steel_col = col
            # Vorlandbrücken auf V-förmigen Doppelstreben (Recherche pier_shape: je Achse zwei V-Paare unter den
            # Stahltrögen). Einzelfelder 30–80 m nicht einzeln belegt -> gleichmäßig ≈ 52 m (Schätzung).
            stations = []
            for f0, f1 in ((0.0, sa), (sb, L)):
                fl = f1 - f0
                nf = max(1, int(round(fl / 52.0)))
                stations += [f0 + fl * i / nf for i in range(1, nf)]
            stations += [sa, sb]                                  # am Bogenfuß ebenfalls Streben statt Pfeilerscheibe
            v_off = min(float(b.get("width_m") or 24.0) * 0.5 - 6.5, 8.0)
            for sv in stations:
                p = axis.interpolate(sv)
                if not (xmin <= p.x < xmax and zmin <= p.y < zmax):
                    continue
                yd = deck_y(p.x, p.y)
                if yd is None:
                    continue
                gnd = max(ground(p.x, p.y), water_y(p.x, p.y))
                hgt = yd - 2.6 - gnd                              # Unterkante Stahltrog ≈ Deck − 2,5 m
                if hgt < 2.0:
                    continue
                q = axis.interpolate(min(sv + 1.0, L))
                r0 = axis.interpolate(max(sv - 1.0, 0.0))
                tx, tz = q.x - r0.x, q.y - r0.y
                tl = math.hypot(tx, tz) or 1.0
                tx, tz = tx / tl, tz / tl
                nx, nz = -tz, tx
                spread = min(max(hgt * 0.75, 3.0), 7.0)          # halbe Öffnung oben (längs)
                vb = under.bands(Point(p.x, p.y).buffer(v_off + spread + 3.0), deck_y)
                for sd in (1.0, -1.0):
                    fx, fz = p.x + nx * v_off * sd, p.y + nz * v_off * sd
                    vpoly = LineString([(fx - tx * spread, fz - tz * spread), (fx + tx * spread, fz + tz * spread)]).buffer(1.3)
                    if any(g_.intersects(vpoly) for g_, _k, _y, _n in vb):
                        report.append(f"V-Strebe bei ({fx:.0f},{fz:.0f}) über Verkehrsband ausgelassen")
                        continue
                    foot = (fx, gnd - 0.5, fz)
                    for lg in (1.0, -1.0):
                        top = (fx + tx * spread * lg, yd - 2.5, fz + tz * spread * lg)
                        _strut(steel_tris, steel_n, foot, top, (nx, nz), 1.1, 0.9)
                    # Fundament-Sockel
                    _beam(steel_tris, steel_n, (fx - tx * 1.0, gnd - 0.4, fz - tz * 1.0),
                          (fx + tx * 1.0, gnd - 0.4, fz + tz * 1.0), (nx, nz), 2.2, 1.0)
            way_ids.update(ids)
            continue                                              # keine Standard-Pfeilerscheiben
        if b.get("type") == "fuss_rad_stahl" and "Schrägseil" in str(b.get("structure_de") or ""):
            if cable_stayed(b, segs):
                count += 1
        if b.get("type") == "stahl_fachwerk" and b.get("variant") != "bergbahn"                 and "Blaues Wunder" not in (b.get("name") or "") and "Loschwitzer" not in (b.get("name") or "")                 and max(float(v) for v in b["spans_m"]) >= 18.0:
            if truss_bridge(b, axis, L):
                count += 1
        if b.get("type") not in TYPES:
            # Balken-/Stahlbrücken: Pfeiler an den echten Feldgrenzen (statt gleichmäßiger Standardpfeiler)
            sp = [float(v) for v in b["spans_m"]]
            if "Blaues Wunder" in (b.get("name") or "") or "Loschwitzer" in (b.get("name") or ""):
                way_ids.update(ids)                       # Uferpfeiler/Türme liefert das Modell (landmarks)
                continue
            S = sum(sp)
            if S < 10.0 or len(sp) < 2:
                continue
            k = min(L / S, 1.0)
            st = 0.5 * (L - S * k)
            wpier = min(max(float(b.get("width_m") or 12.0), 6.0), 30.0) * 0.85
            frame = axis_frame(axis, L)
            bands = under.bands(footprint(axis, L, wpier * 0.5 + 1.5), deck_y)
            added = False
            sts = []
            for v in sp[:-1]:
                st += v * k
                sts.append((st, v * k))
            for i, (st, span) in enumerate(sts):
                p = axis.interpolate(st)
                if not (xmin <= p.x < xmax and zmin <= p.y < zmax):
                    continue
                yd = deck_y(p.x, p.y)
                if yd is None:
                    continue
                gnd = max(ground(p.x, p.y), water_y(p.x, p.y)) - 1.0
                if yd - gnd < 2.5:
                    continue

                def yr(px, pz, _yd=yd):
                    return max(ground(px, pz), water_y(px, pz)) - 1.0, (deck_y(px, pz) or _yd) - 1.2
                nxt = sts[i + 1][1] if i + 1 < len(sts) else span
                st2, pcs = best_station(frame, st, 1.5, L - 1.5, 1.1, wpier * 0.5, bands, yr, max(1.0, min(span, nxt) * 0.3))
                if st2 is None or not pcs:
                    report.append(f"Pfeiler {b.get('name')} bei s={st:.0f} entfällt (Verkehrsband)")
                    continue
                if abs(st2 - st) > 0.01 or len(pcs) > 1 or pcs[0][1] - pcs[0][0] < wpier - 0.02:
                    report.append(f"Pfeiler {b.get('name')} s={st:.0f} -> {st2:.1f}, {len(pcs)} Teil(e)")
                px, pz, tx, tz = frame(st2)
                yd2 = deck_y(px, pz) or yd
                gnd2 = max(ground(px, pz), water_y(px, pz)) - 1.0
                yaw = math.atan2(tx, tz)
                for v0, v1 in pcs:
                    vc = 0.5 * (v0 + v1)
                    piers_out.append([round(px - tz * vc, 2), round(pz + tx * vc, 2), round(yaw, 3), round(v1 - v0, 2),
                                      round(yd2 - 1.2, 2), round(gnd2, 2)])
                added = True
            if added:
                way_ids.update(ids)
            continue
        if b.get("type") == "bahn_eue_historisch":
            # Hochlegung 1890–1901: Stahlträger auf Sandsteinwiderlagern, keine Bögen (Recherche: structure beam_steel)
            if girder_bridge(b, axis, L):
                count += 1
                way_ids.update(ids)
            continue
        spans = [float(s) for s in b["spans_m"]]
        npier = max(len(spans) - 1, 0)
        S = sum(spans)
        big = max(spans) > 20.0
        wp = 4.5 if big else 2.2                                # Pfeilerbreite längs
        run = S + npier * wp
        if run > L * 1.08:                                      # Achse kürzer (Kachelgrenze/Teilweg): stauchen
            k = L / run
            spans = [s * k for s in spans]
            wp *= k
            run = L
        s0 = max((L - run) * 0.5, 0.0)
        width = float(b.get("width_m") or 0.0)
        if not (6.0 <= width <= 40.0):
            width = 18.0 if big else 10.0
        hw = width * 0.5
        arch = b.get("arch") or {}
        rises = arch.get("rise_m") if isinstance(arch.get("rise_m"), list) else None
        def rise_of(i, sp):
            r_ = None
            if rises and i < len(rises) and rises[i]:
                try:
                    r_ = float(rises[i])
                except (TypeError, ValueError):
                    r_ = None
            if not r_:
                r_ = sp / (2.0 if sp < 14.0 else 5.5)            # klein: Halbkreis/Stich 1:2, groß: Segment 1:5,5
            return min(r_, sp * 0.5)
        intervals = []                                          # (a, b, art, stich)
        ps = b.get("pier_stations_m")
        piers = ps.get("piers") if isinstance(ps, dict) else None
        thick = set(round(float(v), 1) for v in (ps.get("thick_piers_6_8m") or [])) if isinstance(ps, dict) else set()
        if piers and len(piers) == npier and abs(piers[-1] - piers[0]) < L + 10:
            # echte Pfeilerlagen (aus den Kanzeln der OSM-Fläche), gemessen ab dem angegebenen Ende in Kompassrichtung
            brg = b.get("bearing_deg")
            p_a, p_b = axis.coords[0], axis.coords[-1]
            ax_brg = math.degrees(math.atan2(p_b[0] - p_a[0], -(p_b[1] - p_a[1]))) % 360.0
            if brg is not None and abs(((ax_brg - float(brg)) + 180.0) % 360.0 - 180.0) > 90.0:
                axis = LineString(list(axis.coords)[::-1])
            wps = [(7.0 if round(float(pc), 1) in thick else wp) for pc in piers]
            prev_e = float(piers[0]) - wps[0] * 0.5 - spans[0]
            for i, pc in enumerate(piers):
                a_ = float(pc) - wps[i] * 0.5
                intervals.append((max(prev_e, 0.0), a_, "arch", rise_of(i, a_ - prev_e)))
                intervals.append((a_, a_ + wps[i], "pier", 0.0))
                prev_e = a_ + wps[i]
            intervals.append((prev_e, min(prev_e + spans[-1], L), "arch", rise_of(len(piers), spans[-1])))
        else:
            s = s0
            for i, sp in enumerate(spans):
                intervals.append((s, s + sp, "arch", rise_of(i, sp)))
                s += sp
                if i < npier:
                    intervals.append((s, s + wp, "pier", 0.0))
                    s += wp

        def frame(sv):
            p = axis.interpolate(min(max(sv, 0.0), L))
            q = axis.interpolate(min(sv + 1.0, L))
            r0 = axis.interpolate(max(sv - 1.0, 0.0))
            tx, tz = q.x - r0.x, q.y - r0.y
            tl = math.hypot(tx, tz) or 1.0
            return p.x, p.y, tx / tl, tz / tl

        # --- Lichtraum: Pfeiler neben die Verkehrsbänder, Bögen über ihnen hoch genug -------------------
        bands = under.bands(footprint(axis, L, hw + 0.5), deck_y) if intervals else []
        if bands:
            orig = {(round(a, 2), round(e, 2)): r for a, e, k_, r in intervals if k_ == "arch"}
            s_first, s_last = intervals[0][0], intervals[-1][1]
            pl = [((a + e) * 0.5, e - a) for a, e, k_, r in intervals if k_ == "pier"]
            newp = []
            for i, (c, wpi) in enumerate(pl):
                prev_c = newp[-1][0] + newp[-1][1] * 0.5 if newp else s_first
                next_c = pl[i + 1][0] - pl[i + 1][1] * 0.5 if i + 1 < len(pl) else s_last

                def yr(px, pz):
                    yd_ = deck_y(px, pz)
                    return max(ground(px, pz), water_y(px, pz)) - 1.0, (yd_ - 0.9) if yd_ is not None else 1e4
                ms = max(1.0, min(c - prev_c, next_c - c) * 0.35)
                st2, _pc = best_station(frame, c, prev_c + wpi * 0.5 + 2.0, next_c - wpi * 0.5 - 2.0, wpi * 0.5, hw,
                                        bands, yr, ms, need_full=True)
                if st2 is None:
                    report.append(f"{b.get('name')}: Bogenpfeiler bei s={c:.0f} entfällt (Verkehrsband)")
                    continue
                if abs(st2 - c) > 0.01:
                    report.append(f"{b.get('name')}: Bogenpfeiler s={c:.0f} -> {st2:.1f} (Verkehrsband)")
                newp.append((st2, wpi))
            intervals = []
            sv = s_first
            for c, wpi in newp:
                a_ = c - wpi * 0.5
                intervals.append((sv, a_, "arch", orig.get((round(sv, 2), round(a_, 2)), rise_of(999, a_ - sv))))
                intervals.append((a_, a_ + wpi, "pier", 0.0))
                sv = a_ + wpi
            intervals.append((sv, s_last, "arch", orig.get((round(sv, 2), round(s_last, 2)), rise_of(999, s_last - sv))))

        def bot_at(sv, a, e, rise, floor):
            px, pz, _tx, _tz = frame(sv)
            yd_ = deck_y(px, pz)
            if yd_ is None:
                return 1e9
            top_ = yd_ - 0.9
            gnd_ = max(ground(px, pz), water_y(px, pz)) - 1.0
            crown_ = top_ - 0.7
            spring_ = max(crown_ - rise, gnd_ + 1.0, floor)
            hh_ = crown_ - spring_
            if hh_ <= 0.2:
                return top_ - 0.5
            half_ = (e - a) * 0.5
            R_ = (half_ * half_ + hh_ * hh_) / (2 * hh_)
            dx_ = ((sv - a) / (e - a) - 0.5) * (e - a)
            return max(crown_ - (R_ - math.sqrt(max(R_ * R_ - dx_ * dx_, 0.0))), spring_)

        iv2 = []
        for a, e, kind, rise in intervals:
            floor = -1e4
            if kind == "arch" and bands and e - a > 0.5:
                sp_, nd_ = [], []
                for g_, k_, y_, need in bands:
                    lo, hi = along(axis, g_)
                    lo, hi = max(lo, a), min(hi, e)
                    if hi <= lo:
                        continue
                    for sv in (lo, 0.5 * (lo + hi), hi):
                        sp_.append(sv)
                        nd_.append(need)
                if sp_:
                    ys_ = [deck_y(*frame(sv)[:2]) for sv in (a, 0.5 * (a + e), e)]
                    ys_ = [v for v in ys_ if v is not None]
                    hi_f = (min(ys_) - 1.6 - 0.21) if ys_ else 1e4
                    f = soffit_floor(lambda sv, fl: bot_at(sv, a, e, rise, fl), sp_, nd_, -1e4, hi_f)
                    if f is None:
                        report.append(f"{b.get('name')}: Bogen s={a:.0f}..{e:.0f} – Lichtraum nicht erreichbar (Deck zu tief)")
                        f = hi_f
                    elif f > -1e4:
                        report.append(f"{b.get('name')}: Bogen s={a:.0f}..{e:.0f} abgeflacht (Kämpfer {f:.1f})")
                    floor = f
            iv2.append((a, e, kind, rise, floor))

        ring_t = 1.1 if big else 0.6
        inside = False
        # Konsolgesims unter der Brüstung über die ganze Länge (0,35 m hoch, 0,18 m vortretend)
        if iv2:
            s_a, s_b = iv2[0][0], iv2[-1][1]
            ng = max(2, int((s_b - s_a) / 1.0) + 1)
            gprev = None
            for k_ in range(ng):
                sv = s_a + (s_b - s_a) * k_ / (ng - 1)
                gx, gz, gtx, gtz = frame(sv)
                gyd = deck_y(gx, gz)
                if gyd is None or not in_tile(gx, gz):
                    gprev = None
                    continue
                gcur = (gx, gz, -gtz, gtx, gyd)
                if gprev is not None:
                    for sd in (1.0, -1.0):
                        (ax_, az_, anx, anz, ay), (bx_, bz_, bnx, bnz, by) = gprev, gcur
                        o = hw + 0.18
                        y0a, y1a, y0b, y1b = ay - 0.45, ay - 0.1, by - 0.45, by - 0.1
                        A = (ax_ + anx * o * sd, y0a, az_ + anz * o * sd)
                        B = (bx_ + bnx * o * sd, y0b, bz_ + bnz * o * sd)
                        C = (bx_ + bnx * o * sd, y1b, bz_ + bnz * o * sd)
                        D = (ax_ + anx * o * sd, y1a, az_ + anz * o * sd)
                        quad(A, B, C, D, (anx * sd, 0.0, anz * sd))
                        Ai = (ax_ + anx * hw * sd, y0a, az_ + anz * hw * sd)
                        Bi = (bx_ + bnx * hw * sd, y0b, bz_ + bnz * hw * sd)
                        quad(Ai, Bi, B, A, (0.0, -1.0, 0.0))
                        Ai2 = (ax_ + anx * hw * sd, y1a, az_ + anz * hw * sd)
                        Bi2 = (bx_ + bnx * hw * sd, y1b, bz_ + bnz * hw * sd)
                        quad(D, C, Bi2, Ai2, (0.0, 1.0, 0.0))
                gprev = gcur
        for a, e, kind, rise, floor in iv2:
            n = max(2, int((e - a) / 0.6) + 1)
            prev = None
            for k in range(n):
                sv = a + (e - a) * k / (n - 1)
                px, pz, tx, tz = frame(sv)
                if not (xmin <= px < xmax and zmin <= pz < zmax):
                    prev = None
                    continue
                inside = True
                nx, nz = -tz, tx
                yd = deck_y(px, pz)
                if yd is None:
                    prev = None
                    continue
                top = yd - 0.9                                     # unter dem LoD2-/Straßendeck
                gnd = max(ground(px, pz), water_y(px, pz)) - 1.0
                if kind == "arch":
                    u = (sv - a) / (e - a)                        # 0..1 über die Öffnung
                    crown = top - 0.7
                    spring = max(crown - rise, gnd + 1.0, floor)
                    hh = crown - spring
                    if hh <= 0.2:
                        bot = top - 0.5
                    else:
                        # Segmentbogen: Kreisabschnitt durch Kämpfer und Scheitel
                        half = (e - a) * 0.5
                        R = (half * half + hh * hh) / (2 * hh)
                        dx = (u - 0.5) * (e - a)
                        bot = crown - (R - math.sqrt(max(R * R - dx * dx, 0.0)))
                        bot = max(bot, spring)
                else:
                    bot = gnd
                cur = (px, pz, top, bot, nx, nz)
                if prev is not None:
                    for sd in (1.0, -1.0):
                        ax_, az_, at, ab, anx, anz = prev
                        bx_, bz_, bt, bb, bnx, bnz = cur
                        A = (ax_ + anx * hw * sd, ab, az_ + anz * hw * sd)
                        B = (bx_ + bnx * hw * sd, bb, bz_ + bnz * hw * sd)
                        C = (bx_ + bnx * hw * sd, bt, bz_ + bnz * hw * sd)
                        D = (ax_ + anx * hw * sd, at, az_ + anz * hw * sd)
                        nrm = (anx * sd, 0.0, anz * sd)
                        if sd > 0:
                            quad(A, B, C, D, nrm)
                        else:
                            quad(B, A, D, C, nrm)
                    if kind == "arch":
                        # Laibung (Gewölbeunterseite), Normale nach unten
                        ax_, az_, at, ab, anx, anz = prev
                        bx_, bz_, bt, bb, bnx, bnz = cur
                        L1 = (ax_ + anx * hw, ab, az_ + anz * hw)
                        R1 = (ax_ - anx * hw, ab, az_ - anz * hw)
                        L2 = (bx_ + bnx * hw, bb, bz_ + bnz * hw)
                        R2 = (bx_ - bnx * hw, bb, bz_ - bnz * hw)
                        quad(R1, R2, L2, L1, (0.0, -1.0, 0.0))
                        # Stirnring: um 7 cm vortretendes Band entlang der Bogenlinie (Keilsteinring)
                        for sd in (1.0, -1.0):
                            o = hw + 0.07
                            A = (ax_ + anx * o * sd, ab, az_ + anz * o * sd)
                            B = (bx_ + bnx * o * sd, bb, bz_ + bnz * o * sd)
                            C = (bx_ + bnx * o * sd, min(bb + ring_t, bt), bz_ + bnz * o * sd)
                            D = (ax_ + anx * o * sd, min(ab + ring_t, at), az_ + anz * o * sd)
                            quad(A, B, C, D, (anx * sd, 0.0, anz * sd))
                            Ai = (ax_ + anx * hw * sd, ab, az_ + anz * hw * sd)
                            Bi = (bx_ + bnx * hw * sd, bb, bz_ + bnz * hw * sd)
                            quad(Ai, Bi, B, A, (0.0, -1.0, 0.0))
                prev = cur
            if kind == "pier" and inside:
                # Stirnflächen des Pfeilers zu den Bogenöffnungen hin (sonst hohl: von unten/vom Schiff sichtbar)
                for sv_, sg_ in ((a, -1.0), (e, 1.0)):
                    qx, qz, qtx, qtz = frame(sv_)
                    if not (xmin <= qx < xmax and zmin <= qz < zmax):
                        continue
                    qyd = deck_y(qx, qz)
                    if qyd is None:
                        continue
                    qn = (-qtz, qtx)
                    qg = max(ground(qx, qz), water_y(qx, qz)) - 1.0
                    qt = qyd - 0.9
                    if qt - qg < 0.3:
                        continue
                    A_ = (qx + qn[0] * hw, qg, qz + qn[1] * hw)
                    B_ = (qx - qn[0] * hw, qg, qz - qn[1] * hw)
                    quad(A_, B_, (B_[0], qt, B_[2]), (A_[0], qt, A_[2]), (qtx * sg_, 0.0, qtz * sg_))
                # Wellenbrecher: spitze Vorköpfe beidseits bis Kämpferhöhe
                px, pz, tx, tz = frame((a + e) * 0.5)
                if not (xmin <= px < xmax and zmin <= pz < zmax):
                    continue
                yd = deck_y(px, pz)
                if yd is None:
                    continue
                nx, nz = -tz, tx
                gnd = max(ground(px, pz), water_y(px, pz)) - 1.0
                ytop = gnd + 1.0 + max(1.5, (yd - gnd) * 0.45)
                half = (e - a) * 0.5
                for sd in (1.0, -1.0):
                    base = (px + nx * hw * sd, pz + nz * hw * sd)
                    tip = (px + nx * (hw + 2.2) * sd, pz + nz * (hw + 2.2) * sd)
                    l = (base[0] - tx * half, base[1] - tz * half)
                    rr = (base[0] + tx * half, base[1] + tz * half)
                    for (p1, p2) in ((l, tip), (tip, rr)):
                        ex, ez = p2[0] - p1[0], p2[1] - p1[1]
                        el = math.hypot(ex, ez) or 1.0
                        on = (ez / el * sd * (1 if p1 == l else 1), 0.0, -ex / el * sd)
                        quad((p1[0], gnd, p1[1]), (p2[0], gnd, p2[1]), (p2[0], ytop, p2[1]), (p1[0], ytop, p1[1]), on)
                    # Abdeckung (schräg)
                    tri((l[0], ytop, l[1]), (tip[0], ytop - 0.6, tip[1]), (rr[0], ytop, rr[1]), (0.0, 1.0, 0.0))
        if inside:
            count += 1
            way_ids.update(ids)
            lod = b.get("lod2")
            if isinstance(lod, str):
                lod = _lit(lod)
            if isinstance(lod, dict):
                lod2_ids.update(lod.get("ids") or [])
    gpiers = generic_piers(city, way_ids, under, ground, deck_y, in_tile, report)
    city["bridge_arches"] = {"tris": [round(v, 3) for v in tris], "n": norms, "ways": sorted(way_ids),
                             "lod2": sorted(lod2_ids), "piers": piers_out, "gpiers": gpiers,
                             "steel": {"tris": [round(v, 3) for v in steel_tris], "n": steel_n, "color": steel_col},
                             "groups": [{"mat": m, "color": c, "tris": [round(v, 3) for v in g[0]], "n": g[1]}
                                        for (m, c), g in groups.items() if g[0]]}
    for line in report:
        print("  " + line)
    cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return count


def main():
    bridges = arch_bridges()
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = 0
    for nm in names:
        tot += tile_arches(nm, bridges)
    print(f"Bogenbrücken: {tot} Bauwerksteile in {len(names)} Kacheln ({len(bridges)} recherchierte Bogenbrücken)")


if __name__ == "__main__":
    main()
