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
                for sd in (1.0, -1.0):
                    fx, fz = p.x + nx * v_off * sd, p.y + nz * v_off * sd
                    foot = (fx, gnd - 0.5, fz)
                    for lg in (1.0, -1.0):
                        top = (fx + tx * spread * lg, yd - 2.5, fz + tz * spread * lg)
                        _strut(steel_tris, steel_n, foot, top, (nx, nz), 1.1, 0.9)
                    # Fundament-Sockel
                    _beam(steel_tris, steel_n, (fx - tx * 1.0, gnd - 0.4, fz - tz * 1.0),
                          (fx + tx * 1.0, gnd - 0.4, fz + tz * 1.0), (nx, nz), 2.2, 1.0)
            way_ids.update(ids)
            continue                                              # keine Standard-Pfeilerscheiben
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
            wpier = float(b.get("width_m") or 12.0)
            added = False
            for v in sp[:-1]:
                st += v * k
                p = axis.interpolate(st)
                if not (xmin <= p.x < xmax and zmin <= p.y < zmax):
                    continue
                q = axis.interpolate(min(st + 1.0, L))
                r0 = axis.interpolate(max(st - 1.0, 0.0))
                yaw = math.atan2(q.x - r0.x, q.y - r0.y)
                yd = deck_y(p.x, p.y)
                if yd is None:
                    continue
                gnd = max(ground(p.x, p.y), water_y(p.x, p.y)) - 1.0
                if yd - gnd < 2.5:
                    continue
                piers_out.append([round(p.x, 2), round(p.y, 2), round(yaw, 3), round(min(max(wpier, 6.0), 30.0), 1),
                                  round(yd - 1.2, 2), round(gnd, 2)])
                added = True
            if added:
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

        inside = False
        for a, e, kind, rise in intervals:
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
                    spring = max(crown - rise, gnd + 1.0)
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
                prev = cur
            if kind == "pier" and inside:
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
    city["bridge_arches"] = {"tris": [round(v, 3) for v in tris], "n": norms, "ways": sorted(way_ids),
                             "lod2": sorted(lod2_ids), "piers": piers_out,
                             "steel": {"tris": [round(v, 3) for v in steel_tris], "n": steel_n, "color": steel_col}}
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
