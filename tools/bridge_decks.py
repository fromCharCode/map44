"""Fahrbahn auf Brücken (Nachbearbeitung nach bridge_arches.py): Breite/Spuren und Deckaufbau wie in echt.

  python tools/bridge_decks.py [E,N ...]     (ohne Argument: alle Kacheln)

1. Fahrbahnbreite und Fahrstreifen der Brückenwege aus der Recherche (data/research/bruecken.json, Feld "deck":
   carriageway_m, lanes, tram_tracks). Richtungsfahrbahnen (zwei Einbahnwege) teilen sich die Angaben. Gilt auch
   für die Kanten des Verkehrsgraphen (KI-Spur). Ursprungswerte bleiben in w_osm/lanes_osm (wiederholbar).
2. Straßenbahn in Straßenmitte (alle Straßen): "tram_mid" = halbe Breite des Gleisbereichs -> keine Leitlinie
   über den Gleisen, sondern Begrenzung daneben (roads.gd).
3. Deckaufbau der LoD2-Brückendecks: Asphalt nur in Fahrbahnbreite, Schotterbett unter Eisenbahngleisen,
   übrige Fläche bei Straßenbrücken erhöhter Gehweg (+15 cm, Gehwegplatten) mit Bordsteinkante, bei Bahnbrücken
   Betonkappe. Ergebnis je Deck: top (Asphalt), top_walk, top_ballast, top_conc, curb (senkrechte Flächen);
   das Original liegt in top0. Brückengeländer über Gehwegen werden mit angehoben.
Dreiecke: Umlauf so, dass −(b−a)×(c−a) die Normale ist (roads.gd _tris_to_surface).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge_arches import _lit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RESEARCH = ROOT / "data" / "research" / "bruecken.json"
WALK_RAISE = 0.15
TRAM_ZONE = {1: 1.7, 2: 3.3}                 # halbe Breite des Gleisbereichs (Lichtraum) bei 1 bzw. 2 Gleisen


def research_decks():
    out = {}
    if not RESEARCH.exists():
        return out
    for b in json.loads(RESEARCH.read_text(encoding="utf-8")).get("bridges", []):
        if b.get("type") == "abgerissen":
            continue
        deck = _lit(b.get("deck"))
        if not isinstance(deck, dict):
            continue
        for w in b.get("osm_way_ids") or []:
            try:
                out[int(str(w).lstrip("w"))] = (b, deck)
            except ValueError:
                pass
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def set_widths(city, decks):
    """Schritt 1: Breite/Spuren der Brückenwege aus der Recherche."""
    n = 0
    roads = city.get("roads", [])
    for r in roads:
        if "w_osm" in r:                                  # wiederholbar: vom Ursprung ausgehen
            r["width"], r["lanes"] = r["w_osm"], r["lanes_osm"]
        if "pl_osm" in r:
            r["pl"], r["pr"] = r["pl_osm"], r["pr_osm"]
    by_bridge = {}
    for r in roads:
        if r.get("bridge") and int(r["id"]) in decks:
            b, deck = decks[int(r["id"])]
            by_bridge.setdefault(b["id"], []).append(r)
    changed = {}
    for bid, rs in by_bridge.items():
        b, deck = decks[int(rs[0]["id"])]
        cw = _num(deck.get("carriageway_m"))
        lanes = int(_num(deck.get("lanes")) or 0)
        if not cw or not (3.0 <= cw <= 40.0):
            continue
        dirs = {int(r.get("oneway", 0)) for r in rs}
        # Richtungsfahrbahnen: Einbahnwege beider Richtungen auf derselben Brücke (Digitalisierrichtung prüfen)
        dual = all(int(r.get("oneway", 0)) != 0 for r in rs) and len({int(r["id"]) for r in rs}) >= 2 and _opposed(rs)
        for r in rs:
            w = cw * 0.5 if dual else cw
            ln = max(1, lanes // 2) if dual and lanes else (lanes or int(r.get("lanes", 1)))
            if 0 in dirs and len(dirs) > 1 and int(r.get("oneway", 0)) != 0:
                continue                                  # Rampen/Nebenwege einer Brücke mit Hauptfahrbahn
            r["w_osm"], r["lanes_osm"] = r["width"], r["lanes"]
            pl, pr = float(r.get("pl", 0.0)), float(r.get("pr", 0.0))
            r["width"] = round(w + pl + pr, 2)
            r["lanes"] = int(ln)
            changed[int(r["id"])] = (r["width"], r["lanes"])
            n += 1
    for e in city.get("graph", {}).get("edges", []):
        wid = int(e.get("wid", -1))
        if "w_osm" in e:
            e["width"], e["lanes"] = e["w_osm"], e["lanes_osm"]
        if "pl_osm" in e:
            e["pl"], e["pr"] = e["pl_osm"], e["pr_osm"]
        if wid in changed and e.get("bridge"):
            e["w_osm"], e["lanes_osm"] = e["width"], e["lanes"]
            e["width"], e["lanes"] = changed[wid]
    return n


def _opposed(rs):
    """Gibt es unter den Einbahnwegen zwei mit entgegengesetzter Fahrtrichtung (parallel)?"""
    vs = []
    for r in rs:
        p = r["pts"]
        dx, dz = p[-1][0] - p[0][0], p[-1][1] - p[0][1]
        L = math.hypot(dx, dz) or 1.0
        s = 1.0 if int(r.get("oneway", 1)) > 0 else -1.0
        vs.append((dx / L * s, dz / L * s))
    return any(a[0] * b[0] + a[1] * b[1] < -0.7 for i, a in enumerate(vs) for b in vs[i + 1:])


def clamp_to_decks(city, decks):
    """Fahrbahn nicht breiter als das LoD2-Deck zwischen den Geländern (je Seite 0,45 m für Kappe/Geländer).
    Gemessen quer zur Achse alle 3 m (20-%-Quantil); nur Wege ohne recherchierte Breite. Kanten des Graphen folgen."""
    parts = []
    for bm in city.get("bridge_meshes", []):
        t = _tri_list(bm.get("top0") or bm.get("top") or [])
        ps = [Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])]) for q in t]
        ps = [pg if pg.is_valid else pg.buffer(0) for pg in ps if pg.area > 1e-4]
        if ps:
            parts.append(unary_union(ps).buffer(0.05).buffer(-0.05))
    if not parts:
        return 0
    D = unary_union(parts)
    n = 0
    changed = {}
    for r in city.get("roads", []):
        if not r.get("bridge") or len(r["pts"]) < 2 or "w_osm" in r:
            continue                                      # recherchierte Fahrbahnbreite (set_widths) bleibt
        ln = LineString([(p[0], p[1]) for p in r["pts"]])
        if ln.length < 4.0 or not ln.intersects(D):
            continue
        dls, drs = [], []
        for sv in np.arange(1.5, ln.length - 1.0, 3.0):
            q = ln.interpolate(sv)
            if not D.contains(q):
                continue
            a = ln.interpolate(max(sv - 1.0, 0.0))
            b = ln.interpolate(min(sv + 1.0, ln.length))
            tx, tz = b.x - a.x, b.y - a.y
            tl = math.hypot(tx, tz) or 1.0
            nx, nz = -tz / tl, tx / tl
            dl = dr = None
            for sgn in (1.0, -1.0):
                cut = LineString([(q.x, q.y), (q.x + nx * sgn * 30.0, q.y + nz * sgn * 30.0)]).intersection(D)
                seg = None
                for g in getattr(cut, "geoms", [cut]):
                    if g.geom_type == "LineString" and g.distance(q) < 0.05:
                        seg = g
                if seg is None:
                    continue
                L = seg.length
                if sgn > 0:
                    dl = L
                else:
                    dr = L
            if dl is not None and dr is not None:
                dls.append(dl)
                drs.append(dr)
        if len(dls) < 2:
            continue
        hl, hr = float(np.percentile(dls, 20)), float(np.percentile(drs, 20))
        w = float(r["width"])
        pl, pr = float(r.get("pl", 0.0)), float(r.get("pr", 0.0))
        allow = 2.0 * min(hl, hr) - 0.9
        if w <= allow + 0.05:
            continue
        lanes0 = max(1, int(r.get("lanes", 1)))
        if allow < max(3.0, 2.75 * min(lanes0, 2)):
            continue                                      # Deck passt nicht zur Achse (Datenfehler) – nicht raten
        r.setdefault("w_osm", r["width"])
        r.setdefault("lanes_osm", r["lanes"])
        r["width"] = round(allow, 2)
        if pl + pr > 0:
            r.setdefault("pl_osm", pl)
            r.setdefault("pr_osm", pr)
            r["pl"], r["pr"] = 0.0, 0.0
        dw = r["width"]
        lanes = int(r["lanes"])
        if lanes > 1 and dw / lanes < 2.75:
            r["lanes"] = max(1, int(dw / 2.75))
        changed[int(r["id"])] = (r["width"], r["lanes"])
        n += 1
    for e in city.get("graph", {}).get("edges", []):
        wid = int(e.get("wid", -1))
        if wid in changed and e.get("bridge"):
            e.setdefault("w_osm", e["width"])
            e.setdefault("lanes_osm", e["lanes"])
            e["width"], e["lanes"] = changed[wid]
            if float(e.get("pl", 0.0)) + float(e.get("pr", 0.0)) > 0:
                e.setdefault("pl_osm", e.get("pl", 0.0))
                e.setdefault("pr_osm", e.get("pr", 0.0))
                e["pl"], e["pr"] = 0.0, 0.0
    return n


def tram_mid(city):
    """Schritt 2: Straßenbahn in Fahrbahnmitte -> halbe Breite des Gleisbereichs je Straße."""
    trams = [LineString([(p[0], p[1]) for p in r["pts"]]) for r in city.get("rails", [])
             if r.get("kind") == "tram" and len(r["pts"]) >= 2]
    trams = [t for t in trams if t.length > 0.5]
    if not trams:
        for r in city.get("roads", []):
            r.pop("tram_mid", None)
        return 0
    tree = STRtree(trams)
    n = 0
    for r in city.get("roads", []):
        r.pop("tram_mid", None)
        if len(r["pts"]) < 2:
            continue
        ln = LineString([(p[0], p[1]) for p in r["pts"]])
        if ln.length < 8.0:
            continue
        near = [trams[int(i)] for i in tree.query(ln.buffer(3.0))]
        if not near:
            continue
        ss = np.linspace(0.0, ln.length, max(3, int(ln.length / 4.0)))
        hit, two = 0, 0
        for s in ss:
            q = ln.interpolate(s)
            ds = sorted(t.distance(q) for t in near)
            if ds and ds[0] < 1.4:
                hit += 1
                if len(ds) > 1 and ds[1] < 2.6:
                    two += 1
        if hit >= 0.6 * len(ss):
            r["tram_mid"] = TRAM_ZONE[2] if two >= 0.5 * hit else TRAM_ZONE[1]
            n += 1
    return n


# --- Schritt 3: Deckaufbau ----------------------------------------------------------------------------------------
def _tri_list(flat):
    a = np.asarray(flat, dtype=float)
    return a.reshape(-1, 3, 3) if a.size else np.zeros((0, 3, 3))


def _emit(out, a, b, c, want):
    """Dreieck mit Umlauf so, dass −(b−a)×(c−a) in Richtung want zeigt."""
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cr = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
    if -(cr[0] * want[0] + cr[1] * want[1] + cr[2] * want[2]) < 0:
        b, c = c, b
    for p in (a, b, c):
        out.extend([round(p[0], 3), round(p[1], 3), round(p[2], 3)])


def _plane(t):
    """y = ax + bz + c aus einem Dreieck (x, y, z)"""
    A = np.array([[t[0][0], t[0][2], 1.0], [t[1][0], t[1][2], 1.0], [t[2][0], t[2][2], 1.0]])
    try:
        return np.linalg.solve(A, np.array([t[0][1], t[1][1], t[2][1]]))
    except np.linalg.LinAlgError:
        return None


class DeckIndex:
    """Höhe des Original-Decks an (x, z) über die Dreiecksebenen."""

    def __init__(self, tris, polys):
        self.tris, self.polys = tris, polys
        self.tree = STRtree(polys)

    def y(self, x, z):
        q = Point(x, z)
        for i in self.tree.query(q.buffer(0.05)):
            if self.polys[int(i)].buffer(0.05).contains(q):
                pl = _plane(self.tris[int(i)])
                if pl is not None:
                    return float(pl[0] * x + pl[1] * z + pl[2])
        return None


def _fill(out, geom, pl, dy):
    """Fläche (2D) als Dreiecke auf der Ebene pl (+dy) ausgeben."""
    if geom.is_empty or geom.area < 0.01:
        return
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type != "Polygon" or g.area < 0.01:
            continue
        for tr in shapely.constrained_delaunay_triangles(g).geoms:
            if tr.area < 1e-4:
                continue
            cs = list(tr.exterior.coords)[:3]
            pts = [(x, float(pl[0] * x + pl[1] * z + pl[2]) + dy, z) for x, z in cs]
            _emit(out, pts[0], pts[1], pts[2], (0.0, 1.0, 0.0))


def deck_layout(city, raw_walk_lines):
    rails_y = []
    for r in city.get("rails", []):
        if r.get("bridge") and len(r["pts"]) >= 2:
            rails_y.append((LineString([(p[0], p[1]) for p in r["pts"]]), [p[2] for p in r["pts"]], r.get("kind")))
    roads_y = []
    for r in city.get("roads", []):
        if r.get("bridge") and len(r["pts"]) >= 2:
            roads_y.append((LineString([(p[0], p[1]) for p in r["pts"]]), [p[2] for p in r["pts"]],
                            float(r["width"]) - float(r.get("pl", 0.0)) - float(r.get("pr", 0.0)) + 0.0, r.get("cls", "")))
    stats = {"decks": 0, "walk": 0, "rail": 0}
    for bm in city.get("bridge_meshes", []):
        top0 = bm.get("top0") or bm.get("top") or []
        bm["top0"] = top0
        tris = _tri_list(top0)
        for k in ("top_walk", "top_ballast", "top_conc", "curb"):
            bm.pop(k, None)
        if len(tris) == 0:
            continue
        polys = [Polygon([(t[0][0], t[0][2]), (t[1][0], t[1][2]), (t[2][0], t[2][2])]) for t in tris]
        polys = [p if p.is_valid else p.buffer(0) for p in polys]
        deck2d = unary_union([p for p in polys if p.area > 1e-4])
        if deck2d.is_empty:
            continue
        dix = DeckIndex(tris, polys)

        def on_deck(ln, ys):
            """Linie liegt auf diesem Deck (Höhe ±1 m über den Deckpunkten)? ys None = Höhe egal"""
            part = ln.intersection(deck2d)
            if part.is_empty or part.length < 2.0:
                return None
            if ys is None:
                return part
            cum = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(ln.coords[:-1], ln.coords[1:])])])
            ok = 0
            tot = 0
            for s in np.linspace(0.0, ln.length, max(2, int(ln.length / 2.0))):
                q = ln.interpolate(s)
                yd = dix.y(q.x, q.y)
                if yd is None:
                    continue
                tot += 1
                if abs(float(np.interp(s, cum, ys)) - yd) < 1.0:
                    ok += 1
            return part if tot and ok >= 0.6 * tot else None

        road_b, tram_b, rail_b = [], [], []
        fast = True                                          # nur Autobahn/Schnellstraße: Kappe statt Gehweg
        for ln, ys, w, cls in roads_y:
            part = on_deck(ln, ys)
            if part is not None:
                road_b.append(ln.buffer(max(w, 2.5) * 0.5, cap_style="flat").intersection(deck2d.buffer(0.01)))
                fast = fast and cls in ("motorway", "trunk", "motorway_link", "trunk_link")
        for ln, ys, kind in rails_y:
            part = on_deck(ln, ys)
            if part is None:
                continue
            if kind == "tram":
                tram_b.append(ln.buffer(1.6, cap_style="flat"))
            else:
                rail_b.append(ln.buffer(2.1, cap_style="flat"))
        walk_on = any(on_deck(ln, None) is not None for ln in raw_walk_lines(deck2d))
        UR = unary_union(road_b + tram_b) if (road_b or tram_b) else Polygon()
        RB = unary_union(rail_b).difference(UR) if rail_b else Polygon()
        has_road = bool(road_b)
        if not has_road and not tram_b and not rail_b and not walk_on:
            mode_rest = "conc"                               # Deck ohne Verkehrsweg: Betonkappe statt Asphalt
        elif has_road or tram_b:
            mode_rest = "walk"
        elif rail_b:
            mode_rest = "conc"
        else:
            mode_rest = "walkflat"                           # reine Fußgängerbrücke: Plattenbelag auf Deckhöhe
        out = {"top": [], "top_walk": [], "top_ballast": [], "top_conc": [], "curb": []}
        for t, pg in zip(tris, polys):
            if pg.area < 1e-4:
                continue
            pl = _plane(t)
            if pl is None:
                continue
            a_road = pg.intersection(UR) if not UR.is_empty else Polygon()
            a_rail = pg.intersection(RB) if not RB.is_empty else Polygon()
            rest = pg
            if not a_road.is_empty:
                rest = rest.difference(UR)
            if not a_rail.is_empty:
                rest = rest.difference(RB)
            _fill(out["top"], a_road, pl, 0.0)
            _fill(out["top_ballast"], a_rail, pl, 0.0)
            if mode_rest == "walk" and fast and road_b:
                _fill(out["top_conc"], rest, pl, WALK_RAISE)    # erhöhte Betonkappe (Autobahnbrücke)
            elif mode_rest == "walk":
                _fill(out["top_walk"], rest, pl, WALK_RAISE)
            elif mode_rest == "walkflat":
                _fill(out["top_walk"], rest, pl, 0.0)
            else:
                _fill(out["top_conc"], rest, pl, 0.0)
        if mode_rest == "walk":
            _curbs(out["curb"], tris, polys, deck2d, UR)
            stats["walk"] += 1
        if rail_b:
            stats["rail"] += 1
        bm["top"] = out["top"]
        for k in ("top_walk", "top_ballast", "top_conc", "curb"):
            if out[k]:
                bm[k] = out[k]
        bm["walk_raise"] = WALK_RAISE if mode_rest == "walk" else 0.0
        stats["decks"] += 1
    return stats


def _curbs(out, tris, polys, deck2d, UR):
    """Bordsteinkante (15 cm) an der Grenze Fahrbahn–Gehweg und Außenkante des Gehwegs am Deckrand."""
    tree = STRtree(polys)

    def y_at(x, z):
        for i in tree.query(Point(x, z).buffer(0.05)):
            if polys[int(i)].buffer(0.05).contains(Point(x, z)):
                pl = _plane(tris[int(i)])
                if pl is not None:
                    return float(pl[0] * x + pl[1] * z + pl[2])
        return None

    def wall(line, toward):
        """senkrechte Flächen entlang line (2D), Normale zur Seite toward(x, z)->bool"""
        cs = list(line.coords)
        for a, b in zip(cs[:-1], cs[1:]):
            L = math.dist(a, b)
            if L < 0.05:
                continue
            n = max(1, int(L / 2.0))
            for k in range(n):
                p0 = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                p1 = (a[0] + (b[0] - a[0]) * (k + 1) / n, a[1] + (b[1] - a[1]) * (k + 1) / n)
                y0, y1 = y_at(*p0), y_at(*p1)
                if y0 is None or y1 is None:
                    continue
                ex, ez = p1[0] - p0[0], p1[1] - p0[1]
                el = math.hypot(ex, ez) or 1.0
                nx, nz = ez / el, -ex / el
                mx, mz = 0.5 * (p0[0] + p1[0]), 0.5 * (p0[1] + p1[1])
                if not toward(mx + nx * 0.2, mz + nz * 0.2):
                    nx, nz = -nx, -nz
                A, B = (p0[0], y0, p0[1]), (p1[0], y1, p1[1])
                C, D = (p1[0], y1 + WALK_RAISE, p1[1]), (p0[0], y0 + WALK_RAISE, p0[1])
                _emit(out, A, B, C, (nx, 0.0, nz))
                _emit(out, A, C, D, (nx, 0.0, nz))

    inner = deck2d.buffer(-0.02)
    if not UR.is_empty:
        edge = UR.boundary.intersection(inner)
        for g in getattr(edge, "geoms", [edge]):
            if g.geom_type == "LineString" and g.length > 0.1:
                wall(g, lambda x, z: UR.contains(Point(x, z)))
    # Außenkante des erhöhten Gehwegs am Deckrand (sonst 15-cm-Schlitz zur LoD2-Seitenwand)
    outer = deck2d.boundary.difference(UR.buffer(0.05)) if not UR.is_empty else deck2d.boundary
    for g in getattr(outer, "geoms", [outer]):
        if g.geom_type == "LineString" and g.length > 0.1:
            wall(g, lambda x, z: not deck2d.contains(Point(x, z)))


def bridge_tram_poles(city):
    """Fahrleitungsmasten auf Straßenbahnbrücken: alle ~36 m abwechselnd am Deckrand (0,6 m innen), nicht in der
    Fahrbahn. Format wie build_city.build_tram_poles + Fußhöhe [.., y_fuss]. Wiederholbar über tram_poles0."""
    if "tram_poles0" not in city:
        city["tram_poles0"] = [list(p) for p in city.get("tram_poles", [])]
    poles = [list(p) for p in city["tram_poles0"]]
    parts = []
    for bm in city.get("bridge_meshes", []):
        t = _tri_list(bm.get("top0") or bm.get("top") or [])
        if len(t) == 0:
            continue
        polys = [Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])]) for q in t]
        polys = [pg if pg.is_valid else pg.buffer(0) for pg in polys]
        parts.append((unary_union([pg for pg in polys if pg.area > 1e-4]), DeckIndex(t, polys), float(bm.get("walk_raise", 0.0))))
    if not parts:
        return 0
    roads = [LineString([(p[0], p[1]) for p in r["pts"]]).buffer(max(float(r["width"]) * 0.5, 1.5), cap_style="flat")
             for r in city.get("roads", []) if r.get("bridge") and len(r["pts"]) >= 2]
    RB = unary_union(roads) if roads else Polygon()
    have = [(p[0], p[1]) for p in poles]
    n = 0
    for r in city.get("rails", []):
        if r.get("kind") != "tram" or not r.get("bridge") or len(r["pts"]) < 2:
            continue
        pts = r["pts"]
        ln = LineString([(p[0], p[1]) for p in pts])
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(pts[:-1], pts[1:])])])
        side = 1.0
        sv = 12.0
        while sv < ln.length - 6.0:
            a = ln.interpolate(max(sv - 1.0, 0.0))
            b = ln.interpolate(min(sv + 1.0, ln.length))
            q = ln.interpolate(sv)
            tx, tz = b.x - a.x, b.y - a.y
            tl = math.hypot(tx, tz) or 1.0
            nx, nz = -tz / tl * side, tx / tl * side
            best = None
            for deck2d, dix, wr in parts:
                last = None
                d = 2.5
                while d <= 14.0:
                    c = Point(q.x + nx * d, q.y + nz * d)
                    if deck2d.contains(c):
                        last = (d, dix, wr)
                    elif last is not None:
                        break
                    d += 0.25
                if last is not None and (best is None or last[0] > best[0]):
                    best = last
            sv_cur = sv
            sv += 36.0
            side = -side
            if best is None:
                continue
            d, dix, wr = best
            px, pz = q.x + nx * (d - 0.6), q.y + nz * (d - 0.6)
            if RB.contains(Point(px, pz)) or any(math.hypot(px - hx, pz - hz) < 9.0 for hx, hz in have):
                continue
            yb = dix.y(px, pz)
            if yb is None:
                continue
            gy_t = float(np.interp(sv_cur, cum, [p[2] for p in pts]))
            yaw = math.atan2(-(q.y - pz), q.x - px)
            poles.append([round(px, 2), round(pz, 2), round(yb + wr, 2), round(yaw, 3), round(q.x, 2), round(q.y, 2),
                          round(gy_t, 2), round(yb + wr, 2)])
            have.append((px, pz))
            n += 1
    city["tram_poles"] = poles
    return n


def fix_steep_slabs(city, ter, x0, z0):
    """OSM-Plattenbrücken (ohne LoD2-Deck) mit unmöglicher Steigung (> 12 %): Profilhöhe kam aus dem
    Oberflächenmodell (Baumkrone/Dach über einem freien Ende). Neu: linear zwischen den Anschlusshöhen der
    Nachbarwege bzw. dem Gelände an freien Enden. Gilt für Platte, Straße und Graphkanten (Ursprung: pts0)."""
    roads = city.get("roads", [])
    ends = {}
    for r in roads:
        for p in (r["pts"][0], r["pts"][-1]):
            ends.setdefault((round(p[0], 0), round(p[1], 0)), []).append((int(r["id"]), p[2]))

    def ter_at(x, z):
        c_, r_ = int(x - x0), int(z - z0)
        return float(ter[r_, c_]) if 0 <= c_ < 2000 and 0 <= r_ < 2000 else None
    n = 0
    for b in city.get("bridges", []):                      # wiederholbar: alle Profile vom Ursprung (auch Stege)
        if "pts0" in b:
            b["pts"] = [list(q) for q in b["pts0"]]
    for e in city.get("graph", {}).get("edges", []):
        if "pts0" in e:
            e["pts"] = [list(q) for q in e["pts0"]]
    slabs = {int(b["id"]): b for b in city.get("bridges", []) if b.get("kind") == "drive"}
    for r in roads:
        if "pts0" in r:
            r["pts"] = [list(q) for q in r["pts0"]]
    for r in roads:
        rid = int(r["id"])
        if not r.get("bridge") or rid not in slabs or len(r["pts"]) < 2:
            continue
        pts = r["pts"]
        cum = [0.0]
        for a, b in zip(pts[:-1], pts[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        L = cum[-1]
        if L < 3.0 or L > 150.0:
            continue
        g = max(abs(b[2] - a[2]) / max(cum[i + 1] - cum[i], 0.5) for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])))
        if g <= 0.12:
            continue
        ys = []
        for p in (pts[0], pts[-1]):
            nb = [y for i, y in ends.get((round(p[0], 0), round(p[1], 0)), []) if i != rid]
            if nb:
                ys.append(float(np.median(nb)))
            else:
                t_ = ter_at(p[0], p[1])
                ys.append(t_ if t_ is not None else p[2])
        if abs(ys[1] - ys[0]) / L > 0.12:
            continue                                      # Anschlüsse selbst steil: nicht raten
        r.setdefault("pts0", [list(q) for q in pts])
        new = [[q[0], q[1], round(ys[0] + (ys[1] - ys[0]) * (cum[i] / L), 2)] for i, q in enumerate(pts)]
        r["pts"] = new
        sb = slabs[rid]
        sb.setdefault("pts0", [list(q) for q in sb["pts"]])
        ln = LineString([(q[0], q[1]) for q in new])
        sb["pts"] = [[q[0], q[1], round(ys[0] + (ys[1] - ys[0]) * (ln.project(Point(q[0], q[1])) / L), 2)] for q in sb["pts"]]
        for e in city.get("graph", {}).get("edges", []):
            if int(e.get("wid", -1)) == rid:
                e.setdefault("pts0", [list(q) for q in e["pts"]])
                e["pts"] = [[q[0], q[1], round(ys[0] + (ys[1] - ys[0]) * (ln.project(Point(q[0], q[1])) / L), 2)] for q in e["pts0"]]
        n += 1
    return n


CLR_BELOW = {"motorway": 4.7, "trunk": 4.5, "primary": 4.5, "secondary": 4.5, "tertiary": 4.2, "motorway_link": 4.5,
             "trunk_link": 4.5, "primary_link": 4.5, "secondary_link": 4.5, "tertiary_link": 4.2}


def raise_low_slabs(city):
    """OSM-Plattenbrücken (Stege, kleine Straßenbrücken ohne LoD2), die eine Straße/ein Gleis zu tief kreuzen (Höhe
    aus dem Oberflächenmodell ist bei 1,5-m-Stegen ungenau: Steg über der A4 nur 2 m über der Fahrbahn): an der
    Kreuzung auf Lichtraum + Plattendicke heben, zu den Enden linear auslaufen (Rampe/Treppe). Wiederholbar über pts0
    (gemeinsam mit fix_steep_slabs; diese Funktion läuft danach)."""
    under = []
    for r in city.get("roads", []):
        if r.get("bridge") or len(r["pts"]) < 2:
            continue
        under.append((LineString([(q[0], q[1]) for q in r["pts"]]), r["pts"], CLR_BELOW.get(r.get("cls", ""), 4.0)))
    for r in city.get("rails", []):
        if r.get("bridge") or len(r["pts"]) < 2:
            continue
        under.append((LineString([(q[0], q[1]) for q in r["pts"]]), r["pts"], 4.7 if r.get("kind") == "tram" else 5.5))
    if not under:
        return 0
    tree = STRtree([u[0] for u in under])
    roads_by = {int(r["id"]): r for r in city.get("roads", []) if r.get("bridge")}
    n = 0
    for b in city.get("bridges", []):
        pts = b.get("pts", [])
        if len(pts) < 2:
            continue
        ln = LineString([(q[0], q[1]) for q in pts])
        L = ln.length
        if L < 6.0:
            continue
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b_[:2]) for a, b_ in zip(pts[:-1], pts[1:])])])
        ys = np.array([q[2] for q in pts], dtype=float)
        thick = 0.9
        lifts = []
        for i in tree.query(ln):
            uln, upts, need = under[int(i)]
            x = ln.intersection(uln)
            for g in getattr(x, "geoms", [x]):
                if g.is_empty or g.geom_type != "Point":
                    continue
                s_ = ln.project(g)
                ucum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b_[:2]) for a, b_ in zip(upts[:-1], upts[1:])])])
                yu = float(np.interp(uln.project(g), ucum, [q[2] for q in upts]))
                ys_ = float(np.interp(s_, cum, ys))
                gap = ys_ - thick - yu
                if gap < 0.8 - thick or gap >= need - 0.2:
                    continue                                   # ebenerdig (Anschluss) oder hoch genug
                lifts.append((s_, need - gap))
        if not lifts:
            continue
        lift = np.zeros(len(pts))
        ok = True
        for s_, dz in lifts:
            if dz > 4.5:
                ok = False
                break
            for k, sv in enumerate(cum):
                ramp = max(s_, 1e-3) if sv <= s_ else max(L - s_, 1e-3)
                lift[k] = max(lift[k], dz * max(0.0, 1.0 - abs(sv - s_) / ramp))
        if not ok:
            continue
        new = ys + lift
        g_max = max(abs(new[k + 1] - new[k]) / max(cum[k + 1] - cum[k], 0.5) for k in range(len(pts) - 1))
        if g_max > (0.12 if b.get("kind") == "drive" else 0.3):
            continue
        b.setdefault("pts0", [list(q) for q in pts])
        b["pts"] = [[q[0], q[1], round(float(new[k]), 2)] for k, q in enumerate(pts)]
        r = roads_by.get(int(b["id"]))
        if r is not None:
            r.setdefault("pts0", [list(q) for q in r["pts"]])
            rl = LineString([(q[0], q[1]) for q in r["pts"]])
            r["pts"] = [[q[0], q[1], round(float(np.interp(ln.project(Point(q[0], q[1])), cum, new)), 2)] for q in r["pts"]]
            for e in city.get("graph", {}).get("edges", []):
                if int(e.get("wid", -1)) == int(b["id"]):
                    e.setdefault("pts0", [list(q) for q in e["pts"]])
                    e["pts"] = [[q[0], q[1], round(float(np.interp(ln.project(Point(q[0], q[1])), cum, new)), 2)] for q in e["pts0"]]
        n += 1
    return n


def fill_decks(city, ter=None, x0=0.0, z0=0.0):
    """Brückenfahrbahnen, die nur teilweise auf einem LoD2-Deck bzw. einer OSM-Platte liegen (Deck schmaler als die
    Fahrbahn, zweiter Überbau fehlt in LoD2): fehlende Fläche als Deck in Profilhöhe ergänzen ("fill:<weg>",
    1 m dick, Stirnseiten nur an freien Kanten). Wiederholbar (alte Füllstücke werden ersetzt)."""
    city["bridge_meshes"] = [bm for bm in city.get("bridge_meshes", []) if not str(bm.get("id", "")).startswith("fill:")]
    parts = []
    for bm in city["bridge_meshes"]:
        t = _tri_list(bm.get("top0") or bm.get("top") or [])
        ps = [Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])]) for q in t]
        ps = [pg if pg.is_valid else pg.buffer(0) for pg in ps if pg.area > 1e-4]
        if ps:
            parts.append(unary_union(ps))
    if not parts:
        return 0
    D = unary_union(parts).buffer(0.05)
    slabs = [LineString([(p[0], p[1]) for p in b["pts"]]).buffer(max(float(b["width"]), 2.5) * 0.5 + (1.0 if b.get("kind") == "drive" else 0.0), cap_style="flat")
             for b in city.get("bridges", []) if len(b.get("pts", [])) >= 2]
    S = unary_union(slabs) if slabs else Polygon()
    # nie über anderen Straßen/Gleisen (Rampen, Uferstraßen unter der Brücke): deren Band + 0,5 m frei lassen
    # Straßen/Gleise darunter: nur dort nicht füllen, wo sonst ihr Lichtraum (4,5 m unter der Füllstück-Unterseite)
    # verloren ginge
    below = []
    for r in city.get("roads", []) + city.get("rails", []):
        if r.get("bridge") or len(r["pts"]) < 2:
            continue
        ln_b = LineString([(q[0], q[1]) for q in r["pts"]])
        if ln_b.length < 0.5:
            continue
        hw_b = float(r.get("width", 4.0)) * 0.5 + 0.5 if "cls" in r else 2.2
        cum_b = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(r["pts"][:-1], r["pts"][1:])])])
        below.append((ln_b.buffer(hw_b, cap_style="flat"), ln_b, cum_b, [q[2] for q in r["pts"]]))
    btree = STRtree([b_[0] for b_ in below]) if below else None

    def blocks_below(x, z, y):
        if btree is None:
            return False
        q = Point(x, z)
        for i in btree.query(q):
            band_, ln_b, cum_b, ys_b = below[int(i)]
            if band_.contains(q) and float(np.interp(ln_b.project(q), cum_b, ys_b)) > y - 1.0 - 4.5:
                return True
        return False
    n = 0
    for r in city.get("roads", []):
        if not r.get("bridge") or len(r["pts"]) < 2:
            continue
        ln = LineString([(p[0], p[1]) for p in r["pts"]])
        if ln.length < 2.0:
            continue
        band = ln.buffer(float(r["width"]) * 0.5, cap_style="flat")
        if not band.intersects(D):
            continue                                       # ganz ohne LoD2-Deck: OSM-Platte aus build_city
        unc = band.difference(D)
        if not S.is_empty:
            unc = unc.difference(S)
        unc = unc.buffer(-0.15).buffer(0.15)
        if unc.is_empty or unc.area < 3.0:
            continue
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(r["pts"][:-1], r["pts"][1:])])])
        ys = [p[2] for p in r["pts"]]

        def yat(x, z):
            return float(np.interp(ln.project(Point(x, z)), cum, ys))

        def hole(x, z, y):
            """nur dort füllen, wo sonst ein Loch wäre (Gelände ≥ 0,5 m unter der Fahrbahn)"""
            if ter is None:
                return True
            c_, r_ = int(x - x0), int(z - z0)
            if not (0 <= c_ < 2000 and 0 <= r_ < 2000):
                return True
            return float(ter[r_, c_]) < y - 0.5
        top, bot, side = [], [], []
        for g in getattr(unc, "geoms", [unc]):
            if g.geom_type != "Polygon" or g.area < 1.0:
                continue
            for tr in shapely.constrained_delaunay_triangles(g).geoms:
                if tr.area < 1e-4:
                    continue
                cs = list(tr.exterior.coords)[:3]
                pt = [(x, yat(x, z), z) for x, z in cs]
                cxm, czm = sum(c[0] for c in cs) / 3.0, sum(c[1] for c in cs) / 3.0
                if not hole(cxm, czm, yat(cxm, czm)) or blocks_below(cxm, czm, yat(cxm, czm)):
                    continue
                _emit(top, pt[0], pt[1], pt[2], (0.0, 1.0, 0.0))
                pb = [(x, y - 1.0, z) for x, y, z in pt]
                _emit(bot, pb[0], pb[1], pb[2], (0.0, -1.0, 0.0))
            # Stirnseiten an freien Kanten (nicht am LoD2-Deck)
            free = g.exterior.difference(D.buffer(0.1))
            for e in getattr(free, "geoms", [free]):
                if e.geom_type != "LineString":
                    continue
                cs = list(e.coords)
                for a, b in zip(cs[:-1], cs[1:]):
                    if math.dist(a, b) < 0.05:
                        continue
                    ya, yb = yat(*a), yat(*b)
                    if not hole(0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]), 0.5 * (ya + yb)) \
                            or blocks_below(0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]), 0.5 * (ya + yb)):
                        continue
                    ex, ez = b[0] - a[0], b[1] - a[1]
                    el = math.hypot(ex, ez)
                    nx, nz = ez / el, -ex / el
                    if g.contains(Point(0.5 * (a[0] + b[0]) + nx * 0.2, 0.5 * (a[1] + b[1]) + nz * 0.2)):
                        nx, nz = -nx, -nz
                    A, B = (a[0], ya - 1.0, a[1]), (b[0], yb - 1.0, b[1])
                    _emit(side, A, B, (b[0], yb, b[1]), (nx, 0.0, nz))
                    _emit(side, A, (b[0], yb, b[1]), (a[0], ya, a[1]), (nx, 0.0, nz))
        if top:
            city["bridge_meshes"].append({"id": f"fill:{int(r['id'])}", "top": top, "side": side, "bot": bot})
            n += 1
    return n


def lift_lamps(city):
    """Laternen, die über einem Brückendeck liegen, aber am Boden darunter stehen (OSM-Punkt auf dem Brückenweg,
    Höhe aus dem Gelände) -> auf das Deck (+ Gehweghöhe). Laternen an Straßen unter der Brücke bleiben unten.
    Wiederholbar über lamps0."""
    if "lamps0" not in city:
        city["lamps0"] = [list(l) for l in city.get("lamps", [])]
    lamps = [list(l) for l in city["lamps0"]]
    decks = []
    for bm in city.get("bridge_meshes", []):
        t = _tri_list(bm.get("top0") or bm.get("top") or [])
        if len(t) == 0:
            continue
        ps = [Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])]) for q in t]
        ps = [pg if pg.is_valid else pg.buffer(0) for pg in ps]
        u = unary_union([pg for pg in ps if pg.area > 1e-4])
        decks.append((u, DeckIndex(t, ps), float(bm.get("walk_raise", 0.0))))
    under = []
    for r in city.get("roads", []):
        if not r.get("bridge") and len(r["pts"]) >= 2:
            under.append((LineString([(p[0], p[1]) for p in r["pts"]]), r["pts"]))
    utree = STRtree([u[0] for u in under]) if under else None
    n = 0
    for l in lamps:
        q = Point(l[0], l[1])
        for u, dix, wr in decks:
            if not u.contains(q):
                continue
            yd = dix.y(l[0], l[1])
            if yd is None or yd - float(l[2]) < 2.0:
                break
            near_road = False
            if utree is not None:
                for i in utree.query(q.buffer(8.0)):
                    ln, pts = under[int(i)]
                    if ln.distance(q) < 8.0:
                        s_ = ln.project(q)
                        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(pts[:-1], pts[1:])])])
                        if abs(float(np.interp(s_, cum, [p[2] for p in pts])) - float(l[2])) < 1.5:
                            near_road = True
                            break
            if not near_road:
                l[2] = round(yd + wr, 2)
                n += 1
            break
    city["lamps"] = lamps
    return n


def missing_rails(city, terrain, x0, z0, ext_rails=()):
    """Geländer an allen echten Absturzkanten der Decks (≥ 1 m über dem Gelände davor), wo noch keins steht –
    z. B. an Kanzeln über den Pfeilern (Albertbrücke: eine Seite hatte nur 52 von 330 m). Stil vom nächsten
    vorhandenen Geländer derselben Brücke (≤ 60 m), sonst Betonkappe mit Stahlgeländer."""
    base = city.get("bridge_rails0", [])
    polys, idxs = [], []
    for bm in city.get("bridge_meshes", []):
        t = _tri_list(bm.get("top0") or bm.get("top") or [])
        if len(t) == 0:
            continue
        ps = [Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])]) for q in t]
        ps = [pg if pg.is_valid else pg.buffer(0) for pg in ps]
        u = unary_union([pg for pg in ps if pg.area > 1e-4])
        if u.is_empty:
            continue
        polys.append(u)
        idxs.append(DeckIndex(t, ps))
    if not polys:
        return []
    D = unary_union([g.buffer(0.05) for g in polys]).buffer(-0.05)
    bands = [LineString([(q[0], q[1]) for q in r["pts"]]).buffer(float(r["width"]) * 0.5 - 0.1, cap_style="flat")
             for r in city.get("roads", []) if r.get("bridge") and len(r["pts"]) >= 2]
    bands = [b_ for b_ in bands if not b_.is_empty]
    bands_tree = STRtree(bands) if bands else None
    allr = list(base) + list(ext_rails)
    rl = [LineString([(r[0], r[1]), (r[2], r[3])]) for r in allr]
    rtree = STRtree(rl) if rl else None
    base = allr
    out = []

    def ter(x, z):
        c, r_ = int(x - x0), int(z - z0)
        if 0 <= c < 2000 and 0 <= r_ < 2000:
            return float(terrain[r_, c])
        return None

    def deck_y(x, z):
        for dix in idxs:
            y = dix.y(x, z)
            if y is not None:
                return y
        return None
    for g in getattr(D, "geoms", [D]):
        if g.geom_type != "Polygon":
            continue
        for ring in [g.exterior] + list(g.interiors):
            cs = list(ring.simplify(0.2).coords)
            for a, b in zip(cs[:-1], cs[1:]):
                L = math.dist(a, b)
                if L < 0.4:
                    continue
                n = max(1, int(math.ceil(L / 3.0)))
                for k in range(n):
                    p0 = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                    p1 = (a[0] + (b[0] - a[0]) * (k + 1) / n, a[1] + (b[1] - a[1]) * (k + 1) / n)
                    mx, mz = 0.5 * (p0[0] + p1[0]), 0.5 * (p0[1] + p1[1])
                    if not (x0 <= mx < x0 + 2000.0 and z0 <= mz < z0 + 2000.0):
                        continue                              # Kante gehört der Nachbarkachel
                    if bands_tree is not None and any(bands[int(i)].contains(Point(mx, mz)) for i in bands_tree.query(Point(mx, mz))):
                        continue                              # nie quer in einer Brückenfahrbahn
                    ex, ez = p1[0] - p0[0], p1[1] - p0[1]
                    el = math.hypot(ex, ez) or 1.0
                    nx, nz = ez / el, -ex / el
                    if g.contains(Point(mx + nx * 0.3, mz + nz * 0.3)):
                        nx, nz = -nx, -nz                     # n zeigt nach außen
                    yd = deck_y(mx - nx * 0.4, mz - nz * 0.4)
                    tg = ter(mx + nx * 1.0, mz + nz * 1.0)
                    if yd is None or tg is None or yd - tg < 1.0:
                        continue                              # Deckende/Anschluss ans Gelände
                    if rtree is not None and any(rl[int(i)].distance(Point(mx, mz)) < 0.9
                                                 for i in rtree.query(Point(mx, mz).buffer(0.9))):
                        continue
                    art, col, h = "concrete", "#a4a6a3", 1.0
                    if rtree is not None:
                        near = [(rl[int(i)].distance(Point(mx, mz)), int(i)) for i in rtree.query(Point(mx, mz).buffer(60.0))]
                        if near:
                            j = min(near)[1]
                            r0 = base[j]
                            art = r0[5] if len(r0) > 5 else art
                            col = r0[6] if len(r0) > 6 else col
                            h = r0[7] if len(r0) > 7 else h
                    out.append([round(p0[0] - nx * 0.15, 2), round(p0[1] - nz * 0.15, 2), round(p1[0] - nx * 0.15, 2),
                                round(p1[1] - nz * 0.15, 2), round(yd, 2), art, col, h])
    return out


def raise_rails(city, extra=None):
    """Brückengeländer über erhöhten Gehwegen um die Bordhöhe anheben (wiederholbar über bridge_rails0)."""
    if "bridge_rails0" not in city:
        city["bridge_rails0"] = [list(r) for r in city.get("bridge_rails", [])]
    base = city["bridge_rails0"] + (extra or [])
    parts = []
    for bm in city.get("bridge_meshes", []):
        if bm.get("walk_raise", 0.0) > 0 and (bm.get("top_walk") or bm.get("top_conc")):
            t = _tri_list(bm.get("top_walk") or bm.get("top_conc"))
            parts.append(unary_union([Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])]).buffer(0.01)
                                      for q in t]).buffer(0.6))
    W = unary_union(parts) if parts else None
    # Fahrbahnen auf Deckhöhe: Anschlüsse an den Brückenenden (ohne Brückenflag, Band + 0,2 m) und die
    # Brückenfahrbahnen selbst (Band − 0,2 m: OSM-Achse seitlich versetzt, Deck schmaler) – dort kein Geländer
    bands = []
    for r in city.get("roads", []):
        if len(r["pts"]) < 2:
            continue
        ln = LineString([(p[0], p[1]) for p in r["pts"]])
        if ln.length < 0.5:
            continue
        hw = float(r["width"]) * 0.5 + (-0.2 if r.get("bridge") else 0.2)
        if hw <= 0.5:
            continue
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(r["pts"][:-1], r["pts"][1:])])])
        bands.append((ln.buffer(hw, cap_style="flat"), ln, cum, [p[2] for p in r["pts"]]))
    btree = STRtree([b[0] for b in bands]) if bands else None
    out = []
    cut = 0
    for r in base:
        segs = [list(r)]
        if btree is not None:
            seg = LineString([(r[0], r[1]), (r[2], r[3])])
            hit = []
            for i in btree.query(seg):
                g, ln, cum, ys = bands[int(i)]
                if not g.intersects(seg):
                    continue
                m = g.intersection(seg).representative_point()
                yr = float(np.interp(ln.project(m), cum, ys))
                if abs(yr - float(r[4])) < 1.5:
                    hit.append(g)
            if hit:
                rest = seg.difference(unary_union(hit))
                segs = []
                for g in getattr(rest, "geoms", [rest]):
                    if g.geom_type == "LineString" and g.length >= 0.5:
                        c = list(g.coords)
                        q = list(r)
                        q[0], q[1], q[2], q[3] = round(c[0][0], 2), round(c[0][1], 2), round(c[-1][0], 2), round(c[-1][1], 2)
                        segs.append(q)
                cut += 1
        for r2 in segs:
            if W is not None and W.contains(Point(0.5 * (r2[0] + r2[2]), 0.5 * (r2[1] + r2[3]))):
                r2[4] = round(float(r2[4]) + WALK_RAISE, 3)
            out.append(r2)
    city["bridge_rails"] = out
    return cut


def write_cache(name):
    """Kleiner Auszug je Kachel für die Nachbarn: Deck-Oberkanten (top0, ohne Füllstücke) und Geländer."""
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return
    city = json.loads(cf.read_text(encoding="utf-8"))
    parts = [bm.get("top0") or bm.get("top") or [] for bm in city.get("bridge_meshes", [])
             if not str(bm.get("id", "")).startswith(("fill:", "ext:"))]
    rails = city.get("bridge_rails0") or city.get("bridge_rails", [])
    (d / "deck_cache.json").write_text(json.dumps({"parts": [p_ for p_ in parts if p_], "rails": rails},
                                                  separators=(",", ":")), encoding="utf-8")


def neighbours(name):
    """Deckteile und Geländer der 8 Nachbarkacheln (aus deck_cache.json)"""
    e_km, n_km = (int(v) for v in name.split("_"))
    parts, rails = [], []
    for de in (-2, 0, 2):
        for dn in (-2, 0, 2):
            if de == dn == 0:
                continue
            f = TILES / f"{e_km + de}_{n_km + dn}" / "deck_cache.json"
            if f.exists():
                j = json.loads(f.read_text(encoding="utf-8"))
                parts += j.get("parts", [])
                rails += j.get("rails", [])
    return parts, rails


def tile_decks(name, decks):
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return None
    city = json.loads(cf.read_text(encoding="utf-8"))
    # Nachbardecks vorübergehend als "ext:" einhängen (Brücken über Kachelgrenzen: ein LoD2-Teil gehört nur einer
    # Kachel) – für Deckbreite, Füllstücke, Geländer und Laternen; vor Deckaufbau und Speichern wieder entfernt
    ext_parts, ext_rails = neighbours(name)
    # alte Füllstücke zuerst weg (sonst zählen sie bei der Deckbreite als Deck und erhalten sich selbst)
    city["bridge_meshes"] = [bm for bm in city.get("bridge_meshes", []) if not str(bm.get("id", "")).startswith(("ext:", "fill:"))]
    ext = [{"id": f"ext:{i}", "top": t, "top0": t} for i, t in enumerate(ext_parts)]
    city["bridge_meshes"] += ext
    nw = set_widths(city, decks)
    nc = clamp_to_decks(city, decks)
    nt = tram_mid(city)
    ter = np.fromfile(d / "terrain.f32", dtype="<f4").reshape(2000, 2000)
    e_km, n_km = (int(v) for v in name.split("_"))
    ns = fix_steep_slabs(city, ter, e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0))
    ns += raise_low_slabs(city)
    nf = fill_decks(city, ter, e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0))
    raw = ROOT / "data" / "raw" / "tiles" / name / "osm" / "roads.json"
    walk_lines = []
    if raw.exists():
        from bridge_arches import _local
        for el in json.loads(raw.read_text(encoding="utf-8")).get("elements", []):
            t = el.get("tags") or {}
            if t.get("highway") in ("footway", "path", "cycleway", "pedestrian", "steps") and t.get("bridge") not in (None, "no"):
                g = el.get("geometry") or []
                if len(g) >= 2:
                    walk_lines.append(LineString([_local(p["lon"], p["lat"]) for p in g]))
    wtree = STRtree(walk_lines) if walk_lines else None

    def raw_walk(poly):
        return [walk_lines[int(i)] for i in wtree.query(poly)] if wtree is not None else []
    own = [bm for bm in city["bridge_meshes"] if not str(bm.get("id", "")).startswith("ext:")]
    allm = city["bridge_meshes"]
    city["bridge_meshes"] = own
    st = deck_layout(city, raw_walk)
    city["bridge_meshes"] = own + [bm for bm in allm if str(bm.get("id", "")).startswith("ext:")]
    if "bridge_rails0" not in city:
        city["bridge_rails0"] = [list(r) for r in city.get("bridge_rails", [])]
    extra = missing_rails(city, ter, e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0), ext_rails)
    st["rails_add"] = len(extra)
    st["rails_cut"] = raise_rails(city, extra)
    st["poles"] = bridge_tram_poles(city)
    st["lamps"] = lift_lamps(city)
    city["bridge_meshes"] = [bm for bm in city["bridge_meshes"] if not str(bm.get("id", "")).startswith("ext:")]
    cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    print(f"  {name}: {nw} Brückenwege mit recherchierter Breite, {nc} auf Deckbreite begrenzt, {nt} Straßen mit Gleis in der Mitte, "
          f"{st['decks']} Decks ({st['walk']} mit Gehweg, {st['rail']} mit Schotterbett), {st['poles']} Brückenmasten, "
          f"{st['rails_add']} Geländerstücke ergänzt, {st['rails_cut']} an Fahrbahnen gekürzt, {nf} Fahrbahnen mit ergänztem Deck, {ns} Plattenbrücken im Profil korrigiert, {st['lamps']} Laternen aufs Deck")
    return st


def main():
    decks = research_decks()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    names = [a.replace(",", "_") for a in args] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    if "--cache" in sys.argv:
        for nm in names:
            write_cache(nm)
        return
    for nm in names:
        tile_decks(nm, decks)


if __name__ == "__main__":
    main()
