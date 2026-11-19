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
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring, unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge_arches import _lit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RESEARCH = ROOT / "data" / "research" / "bruecken.json"
WALK_RAISE = 0.15
WALK_CLS_DECK = {"footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor"}
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
            # Gleise liegen in der Fahrbahn und werden mitbefahren (Marienbrücke, Albertbrücke): die Recherche zählt
            # Kfz-Streifen und Gleise getrennt, OSM zählt die Gleisstreifen als Fahrstreifen – dann gilt OSM je Weg
            tracks = int(_num(deck.get("tram_tracks")) or 0)
            if tracks and not dual and lanes and lanes < int(r.get("lanes", 1)) <= lanes + tracks \
                    and w / int(r["lanes"]) >= 2.75:
                ln = int(r["lanes"])
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


def separate_slabs(city):
    """Parallele OSM-Fahrbahnplatten (Richtungsfahrbahnen ohne LoD2-Deck), die sich überlappen: beide bis zur
    Mittellinie zwischen den Achsen kürzen (anteilig zur Breite, 5 cm Fuge). A17 in 412_5650: Achsen 13,45 m
    auseinander, je 14 m breit – Kappe und Geländer der einen Platte standen in der äußeren Spur der anderen.
    Wiederholbar (Ursprungsbreite w0)."""
    slabs = [b for b in city.get("bridges", []) if b.get("kind") == "drive" and len(b.get("pts", [])) >= 2]
    for b in slabs:
        if "w0" in b:
            b["width"] = b["w0"]
    if len(slabs) < 2:
        return 0
    lines = [LineString([(q[0], q[1]) for q in b["pts"]]) for b in slabs]
    # dazu parallele normale Fahrbahnen (unmarkierte Fortsetzung der Gegenrichtung, ohne Kappe): "Platten" ohne
    # eigene Begrenzung, nur als Nachbarn
    others = [{"width": float(r["width"]) - 2.0, "pts": r["pts"], "_road": True} for r in city.get("roads", [])
              if not r.get("bridge") and r.get("cls") in ("motorway", "trunk", "primary", "secondary", "motorway_link",
                                                          "trunk_link") and len(r["pts"]) >= 2]
    n_slab = len(slabs)
    slabs = slabs + others
    lines += [LineString([(q[0], q[1]) for q in o["pts"]]) for o in others]
    tree = STRtree(lines)
    lim = {}
    for i, b in enumerate(slabs[:n_slab]):
        li = lines[i]
        if li.length < 3.0:
            continue
        wi = float(b["width"])
        for j in tree.query(li.buffer(wi * 0.5 + 15.0)):
            j = int(j)
            if j == i:
                continue
            lj, wj = lines[j], float(slabs[j]["width"])
            ds = []
            for f in np.linspace(0.05, 0.95, 10):
                q = li.interpolate(f, normalized=True)
                d = lj.distance(q)
                if d >= 0.5 * (wi + wj) + 2.0 or d < 1.0:
                    continue
                # parallel und auf ähnlicher Höhe?
                a, c = li.interpolate(max(f * li.length - 1.0, 0.0)), li.interpolate(min(f * li.length + 1.0, li.length))
                sj = lj.project(q)
                if sj < 0.5 or sj > lj.length - 0.5:
                    continue                  # Lot fällt aufs Ende: Fortsetzung desselben Wegs, kein Nachbar daneben
                a2, c2 = lj.interpolate(max(sj - 1.0, 0.0)), lj.interpolate(min(sj + 1.0, lj.length))
                v1 = (c.x - a.x, c.y - a.y)
                v2 = (c2.x - a2.x, c2.y - a2.y)
                n1, n2 = math.hypot(*v1) or 1.0, math.hypot(*v2) or 1.0
                if abs(v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2) < 0.94:
                    continue
                yi = float(np.interp(li.project(q), [li.project(Point(p_[0], p_[1])) for p_ in b["pts"]], [p_[2] for p_ in b["pts"]]))
                pj = slabs[j]["pts"]
                yj = float(np.interp(sj, [lj.project(Point(p_[0], p_[1])) for p_ in pj], [p_[2] for p_ in pj]))
                if abs(yi - yj) < 2.0:
                    ds.append(d)
            if len(ds) >= 3:
                # Platte = Fahrbahn + je 1 m Kappe (roads.gd _bridge): Gesamtbreiten anteilig auf den Achsabstand
                d = float(np.percentile(ds, 20))
                hw = d * (wi + 2.0) / (wi + wj + 4.0) - 0.05
                lim[i] = min(lim.get(i, wi), 2.0 * hw - 2.0)
    n = 0
    roads = {int(r["id"]): r for r in city.get("roads", []) if r.get("bridge")}
    for i, w in lim.items():
        b = slabs[i]
        if w >= float(b["width"]) - 0.05 or w < 3.0:
            continue
        b.setdefault("w0", b["width"])
        b["width"] = round(w, 2)
        r = roads.get(int(b["id"]))
        if r is not None and float(r["width"]) > w:
            r.setdefault("w_osm", r["width"])
            r.setdefault("lanes_osm", r["lanes"])
            r["width"] = round(w, 2)
            if int(r["lanes"]) > 1 and w / int(r["lanes"]) < 2.75:
                r["lanes"] = max(1, int(w / 2.75))
        n += 1
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


def deck_layout(city, raw_walk_lines, ext_roads=()):
    rails_y = []
    for r in city.get("rails", []):
        # auch Gleise OHNE Brückenkennzeichnung, die auf dem Deck liegen (on_deck prüft die Höhe): Das Deck reicht oft
        # über das gekennzeichnete Stück hinaus, das Schotterbett endete dann als Rechteck mitten auf dem Deck
        if not r.get("tunnel") and len(r["pts"]) >= 2:
            rails_y.append((LineString([(p[0], p[1]) for p in r["pts"]]), [p[2] for p in r["pts"]], r.get("kind")))
    roads_y = []
    for r in city.get("roads", []):
        # auch Fahrwege OHNE Brückenkennzeichnung, die auf dem Deck liegen (on_deck prüft die Höhe): Autobahn-
        # fortsetzung auf dem Deckende bekam sonst die erhöhte Betonkappe in die Fahrspur
        if (r.get("bridge") or r.get("cls") not in WALK_CLS_DECK) and len(r["pts"]) >= 2:
            roads_y.append((LineString([(p[0], p[1]) for p in r["pts"]]), [p[2] for p in r["pts"]],
                            float(r["width"]) - float(r.get("pl", 0.0)) - float(r.get("pr", 0.0)) + 0.0, r.get("cls", "")))
    # Fahrbahnen der Nachbarkacheln: Ein LoD2-Deck gehört nur einer Kachel, reicht aber über die Kachelgrenze. Ohne
    # sie blieb die Deckhälfte jenseits der Grenze Beton bzw. Gehweg (A 17 Lockwitztal, Meixstraße).
    for r in ext_roads:
        if (r.get("bridge") or r.get("cls") not in WALK_CLS_DECK) and len(r["pts"]) >= 2:
            roads_y.append((LineString([(p[0], p[1]) for p in r["pts"]]), [p[2] for p in r["pts"]],
                            float(r["width"]) - float(r.get("pl", 0.0)) - float(r.get("pr", 0.0)) + 0.0, r.get("cls", "")))
    stats = {"decks": 0, "walk": 0, "rail": 0}
    road_tree = STRtree([q[0] for q in roads_y]) if roads_y else None
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
            # ab 0,5 m: Anschlussstücke am Deckende zählen mit (sonst endete der Asphalt als Rundung vor dem Deckende)
            if part.is_empty or part.length < 0.5:
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
        prof = []                                            # (Linie, Stationen, Höhen, Band) der Fahrwege auf dem Deck
        fast = True                                          # nur Autobahn/Schnellstraße: Kappe statt Gehweg
        cand = [roads_y[int(i)] for i in road_tree.query(deck2d)] if road_tree is not None else []
        for ln, ys, w, cls in cand:
            part = on_deck(ln, ys)
            if part is not None:
                # runde Enden: an Stößen zweier Wegstücke auf dem Deck blieb sonst ein Keil Gehweg mit Bordstein quer
                # in der Fahrbahn (Flügelwegbrücke, An der Röder)
                bnd = ln.buffer(max(w, 2.5) * 0.5, cap_style="round")
                road_b.append(bnd.intersection(deck2d.buffer(0.01)))
                cum_ = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(ln.coords[:-1], ln.coords[1:])])])
                prof.append((ln, cum_, ys, bnd.buffer(0.05)))
                fast = fast and cls in ("motorway", "trunk", "motorway_link", "trunk_link")
        ptree = STRtree([q[3] for q in prof]) if prof else None

        def road_y(x, z):
            """Profilhöhe des nächsten Fahrwegs, dessen Band (x, z) enthält"""
            if ptree is None:
                return None
            pt = Point(x, z)
            best = None
            for i in ptree.query(pt):
                ln, cum_, ys, bnd = prof[int(i)]
                if not bnd.contains(pt):
                    continue
                dd = ln.distance(pt)
                if best is None or dd < best[0]:
                    best = (dd, float(np.interp(ln.project(pt), cum_, ys)))
            return best[1] if best else None
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
        # Mittelstreifen: Restflächen, die fast ringsum an Fahrbahnen grenzen (zwischen Richtungsfahrbahnen), sind
        # erhöhte Betonkappen, kein gepflasterter Gehweg (Flügelwegbrücke)
        MED = Polygon()
        if mode_rest == "walk" and not fast and road_b:
            urb = UR.buffer(0.3)
            med = []
            rest_all = deck2d.difference(UR)
            for g in getattr(rest_all, "geoms", [rest_all]):
                if g.geom_type != "Polygon" or g.area < 2.0:
                    continue
                bl = g.exterior.length
                if bl > 1.0 and g.exterior.intersection(urb).length / bl >= 0.85:
                    med.append(g.buffer(0.02))
            if med:
                MED = unary_union(med)
                stats["median"] = stats.get("median", 0) + len(med)
        out = {"top": [], "top_walk": [], "top_ballast": [], "top_conc": [], "curb": []}
        # Fahrbahn auf dem Profil statt auf der LoD2-Ebene, wenn diese in der Fahrbahn > 0,3 m abweicht: sonst Stufe
        # zum Füllstück daneben (A17 Lockwitztal: LoD2-Deck quer verkippt, 1,5 m Sprung mitten in der Fahrbahn)
        # (ab 0,12 m legte es auch Richtungsfahrbahnen mit Quergefälle auf einem gemeinsamen Deck einzeln aufs Profil -> Rampe
        # im Überlappstreifen, Innsbrucker Straße)
        on_prof = False
        AR = deck2d.intersection(unary_union(road_b)) if road_b else Polygon()
        if not AR.is_empty and AR.area > 1.0:
            bx0, bz0, bx1, bz1 = AR.bounds
            for gx in np.arange(bx0 + 1.0, bx1, 3.0):
                for gz in np.arange(bz0 + 1.0, bz1, 3.0):
                    if not AR.contains(Point(gx, gz)):
                        continue
                    ry, dy_ = road_y(gx, gz), dix.y(gx, gz)
                    if ry is not None and dy_ is not None and abs(ry - dy_) > 0.3:
                        on_prof = True
                        break
                if on_prof:
                    break
        if on_prof:
            for g in getattr(AR, "geoms", [AR]):
                if g.geom_type != "Polygon" or g.area < 0.05:
                    continue
                gx0, gz0, gx1, gz1 = g.bounds
                for gx in np.arange(math.floor(gx0 / 3.0) * 3.0, gx1, 3.0):
                    for gz in np.arange(math.floor(gz0 / 3.0) * 3.0, gz1, 3.0):
                        cell = g.intersection(Polygon([(gx, gz), (gx + 3.0, gz), (gx + 3.0, gz + 3.0), (gx, gz + 3.0)]))
                        for h in getattr(cell, "geoms", [cell]):
                            if h.geom_type != "Polygon" or h.area < 0.01:
                                continue
                            for tr in shapely.constrained_delaunay_triangles(h).geoms:
                                if tr.area < 1e-4:
                                    continue
                                cs = list(tr.exterior.coords)[:3]
                                pts = []
                                for x, z in cs:
                                    yy = road_y(x, z)
                                    if yy is None:
                                        yy = dix.y(x, z)
                                    pts.append((x, yy, z))
                                if any(p_[1] is None for p_ in pts):
                                    continue
                                _emit(out["top"], pts[0], pts[1], pts[2], (0.0, 1.0, 0.0))
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
            if on_prof:
                # Fahrbahn schon auf dem Profil; nur Straßenbahn-Bänder ohne Fahrweg bleiben auf der Deckebene
                a_tram = a_road.difference(AR.buffer(0.01)) if not a_road.is_empty else a_road
                _fill(out["top"], a_tram, pl, 0.0)
            else:
                _fill(out["top"], a_road, pl, 0.0)
            _fill(out["top_ballast"], a_rail, pl, 0.0)
            if mode_rest == "walk" and fast and road_b:
                _fill(out["top_conc"], rest, pl, WALK_RAISE)    # erhöhte Betonkappe (Autobahnbrücke)
            elif mode_rest == "walk":
                if not MED.is_empty and rest.intersects(MED):
                    _fill(out["top_conc"], rest.intersection(MED), pl, WALK_RAISE)
                    rest = rest.difference(MED)
                _fill(out["top_walk"], rest, pl, WALK_RAISE)
            elif mode_rest == "walkflat":
                _fill(out["top_walk"], rest, pl, 0.0)
            else:
                _fill(out["top_conc"], rest, pl, 0.0)
        if mode_rest == "walk":
            _curbs(out["curb"], tris, polys, deck2d, UR, road_y if on_prof else None)
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


def _curbs(out, tris, polys, deck2d, UR, road_y=None):
    """Bordsteinkante (15 cm) an der Grenze Fahrbahn–Gehweg und Außenkante des Gehwegs am Deckrand. road_y: Fahrbahn
    liegt auf dem Profil (nicht auf der Deckebene) -> Kante von der Fahrbahnhöhe bis Kappe/Gehweg."""
    tree = STRtree(polys)

    def y_at(x, z):
        for i in tree.query(Point(x, z).buffer(0.05)):
            if polys[int(i)].buffer(0.05).contains(Point(x, z)):
                pl = _plane(tris[int(i)])
                if pl is not None:
                    return float(pl[0] * x + pl[1] * z + pl[2])
        return None

    def wall(line, toward, low=None):
        """senkrechte Flächen entlang line (2D), Normale zur Seite toward(x, z)->bool; low(x, z): Unterkante"""
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
                l0 = low(*p0) if low is not None else None
                l1 = low(*p1) if low is not None else None
                A, B = (p0[0], y0 if l0 is None else l0, p0[1]), (p1[0], y1 if l1 is None else l1, p1[1])
                C, D = (p1[0], y1 + WALK_RAISE, p1[1]), (p0[0], y0 + WALK_RAISE, p0[1])
                _emit(out, A, B, C, (nx, 0.0, nz))
                _emit(out, A, C, D, (nx, 0.0, nz))

    inner = deck2d.buffer(-0.02)
    if not UR.is_empty:
        edge = UR.boundary.intersection(inner)
        for g in getattr(edge, "geoms", [edge]):
            if g.geom_type == "LineString" and g.length > 0.1:
                wall(g, lambda x, z: UR.contains(Point(x, z)), road_y)
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
    # Fußstege ebenso (Grenze 20 %; Treppen ausgenommen): Steg 369524936 stieg auf 9 m Länge 6,5 m an (DOM-Baum am
    # freien Ende) und stand als schräge Platte in der Zufahrt, an der er beginnt
    slabs = {int(b["id"]): b for b in city.get("bridges", []) if b.get("kind") in ("drive", "walk")}
    for r in roads:
        if "pts0" in r:
            r["pts"] = [list(q) for q in r["pts0"]]
    for r in roads:
        rid = int(r["id"])
        if not r.get("bridge") or rid not in slabs or len(r["pts"]) < 2 or r.get("cls") == "steps":
            continue
        gmax = 0.12 if slabs[rid].get("kind") == "drive" else 0.20
        pts = r["pts"]
        cum = [0.0]
        for a, b in zip(pts[:-1], pts[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        L = cum[-1]
        if L < 3.0 or L > 150.0:
            continue
        g = max(abs(b[2] - a[2]) / max(cum[i + 1] - cum[i], 0.5) for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])))
        if g <= gmax:
            continue
        ys = []
        for p in (pts[0], pts[-1]):
            nb = [y for i, y in ends.get((round(p[0], 0), round(p[1], 0)), []) if i != rid]
            if nb:
                ys.append(float(np.median(nb)))
            else:
                t_ = ter_at(p[0], p[1])
                ys.append(t_ if t_ is not None else p[2])
        if abs(ys[1] - ys[0]) / L > gmax:
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


def trim_slabs_on_roads(city):
    """Platten-Enden, die IN einer anderen Fahrbahn auf ähnlicher Höhe liegen (Steg beginnt an einem Knoten mitten
    in der Zufahrt), kürzen bis an deren Rand: dort fährt man auf der Straße, eine Platte (1 m dick, Geländer) wäre ein
    Hindernis. Bleibt weniger als 1 m übrig, entfällt die Platte. Wiederholbar (Ursprung pts0 aus fix_steep_slabs)."""
    bands = []
    for r in city.get("roads", []):
        if r.get("bridge") or len(r["pts"]) < 2 or r.get("cls") in WALK_CLS_DECK:
            continue
        ln_r = LineString([(q[0], q[1]) for q in r["pts"]])
        if ln_r.length < 0.5:
            continue
        cum_r = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(r["pts"][:-1], r["pts"][1:])])])
        bands.append((ln_r.buffer(float(r.get("width", 5.0)) * 0.5, cap_style="flat"), ln_r, cum_r, [q[2] for q in r["pts"]]))
    if not bands:
        return 0
    tree = STRtree([b_[0] for b_ in bands])

    def on_road(x, z, y):
        q = Point(x, z)
        for i in tree.query(q):
            band_, ln_r, cum_r, ys_r = bands[int(i)]
            if band_.contains(q) and abs(float(np.interp(ln_r.project(q), cum_r, ys_r)) - y) < 1.2:
                return True
        return False
    n = 0
    keep = []
    for b in city.get("bridges", []):
        pts = b.get("pts", [])
        if len(pts) < 2:
            keep.append(b)
            continue
        ln = LineString([(q[0], q[1]) for q in pts])
        L = ln.length
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], c[:2]) for a, c in zip(pts[:-1], pts[1:])])])
        ys = [q[2] for q in pts]

        def y_at(sv):
            return float(np.interp(sv, cum, ys))
        s0, s1 = 0.0, L
        while s0 < L and on_road(*ln.interpolate(s0).coords[0], y_at(s0)):
            s0 += 0.25
        while s1 > s0 and on_road(*ln.interpolate(s1).coords[0], y_at(s1)):
            s1 -= 0.25
        if s0 == 0.0 and s1 == L:
            keep.append(b)
            continue
        n += 1
        b.setdefault("pts0", [list(q) for q in pts])
        if s1 - s0 < 1.0:
            continue                                      # ganz auf der Straße: keine Platte
        s0 = min(s0 + 0.2, s1) if s0 > 0.0 else s0
        s1 = max(s1 - 0.2, s0) if s1 < L else s1
        new = [[*ln.interpolate(s0).coords[0], round(y_at(s0), 2)]]
        new += [list(q) for q, c in zip(pts, cum) if s0 < c < s1]
        new.append([*ln.interpolate(s1).coords[0], round(y_at(s1), 2)])
        b["pts"] = [[round(q[0], 2), round(q[1], 2), q[2]] for q in new]
        keep.append(b)
    city["bridges"] = keep
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


def fill_decks(city, ter=None, x0=0.0, z0=0.0, decks=None):
    """Brückenfahrbahnen, die nur teilweise auf einem LoD2-Deck bzw. einer OSM-Platte liegen (Deck schmaler als die
    Fahrbahn, zweiter Überbau fehlt in LoD2): fehlende Fläche als Deck in Profilhöhe ergänzen ("fill:<weg>",
    1 m dick bzw. recherchierte Deckstärke bei hohen Brücken, Stirnseiten nur an freien Kanten). Wiederholbar (alte
    Füllstücke werden ersetzt)."""
    city["bridge_meshes"] = [bm for bm in city.get("bridge_meshes", []) if not str(bm.get("id", "")).startswith("fill:")]
    parts = []
    all_t, all_p = [], []
    for bm in city["bridge_meshes"]:
        t = _tri_list(bm.get("top0") or bm.get("top") or [])
        ps = []
        for q in t:
            pg = Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])])
            if pg.area > 1e-4:
                pg = pg if pg.is_valid else pg.buffer(0)
                ps.append(pg)
                all_t.append(q)
                all_p.append(pg)
        if ps:
            parts.append(unary_union(ps))
    if not parts:
        return 0
    dix = DeckIndex(all_t, all_p)
    bridge_bands = []
    for r_ in city.get("roads", []):
        if r_.get("cls") not in WALK_CLS_DECK and len(r_["pts"]) >= 2:
            l_ = LineString([(q[0], q[1]) for q in r_["pts"]])
            if l_.length > 0.5:
                bridge_bands.append((r_, l_.buffer(float(r_["width"]) * 0.5, cap_style="flat"), l_))
    bridge_tree = STRtree([b_[1] for b_ in bridge_bands]) if bridge_bands else None
    tri_tree = STRtree(all_p)
    tri_y = [float(np.mean(np.asarray(t)[:, 1])) for t in all_t]
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
        below.append((ln_b.buffer(hw_b, cap_style="flat"), ln_b, cum_b, [q[2] for q in r["pts"]], id(r)))
    btree = STRtree([b_[0] for b_ in below]) if below else None

    def blocks_below(x, z, y, own=None):
        if btree is None:
            return False
        q = Point(x, z)
        for i in btree.query(q):
            band_, ln_b, cum_b, ys_b, rid_ = below[int(i)]
            if rid_ == own:
                continue
            if not band_.contains(q):
                continue
            yb = float(np.interp(ln_b.project(q), cum_b, ys_b))
            # nur Wege wirklich UNTER der Füllstück-Unterseite (y − 1 m), deren Lichtraum verloren ginge – eine
            # Nachbarstraße auf gleicher Höhe (Flügelweg an der Flügelwegbrücke) verhinderte sonst das Füllstück
            if y - 1.0 - 4.5 < yb < y - 1.0 + 0.2:
                return True
        return False
    n = 0
    for r in city.get("roads", []):
        if len(r["pts"]) < 2:
            continue
        ln = LineString([(p[0], p[1]) for p in r["pts"]])
        if ln.length < 2.0:
            continue
        if r.get("bridge"):
            band = ln.buffer(float(r["width"]) * 0.5, cap_style="flat")
        else:
            # Weg ohne Brückenkennzeichnung, der auf einem Deck liegt (Profil = Deckhöhe; Bachbrücke, Durchlass als
            # tunnel=yes erfasst): nur der Abschnitt auf dem Deck ± 3 m, sonst entstünden Füllstücke über Gräben
            if not ln.intersects(D):
                continue
            cum0 = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(r["pts"][:-1], r["pts"][1:])])])
            ys0 = [p[2] for p in r["pts"]]
            on = []
            for sv in np.arange(0.0, ln.length + 1e-6, 2.0):
                q = ln.interpolate(sv)
                yd = dix.y(q.x, q.y)
                if yd is not None and abs(yd - float(np.interp(sv, cum0, ys0))) < 0.6:
                    on.append(sv)
            if len(on) < 2:
                continue
            band = substring(ln, max(min(on) - 3.0, 0.0), min(max(on) + 3.0, ln.length)).buffer(
                float(r["width"]) * 0.5, cap_style="flat")
        if not band.intersects(D):
            continue                                       # ganz ohne LoD2-Deck: OSM-Platte aus build_city
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(r["pts"][:-1], r["pts"][1:])])])
        ys = [p[2] for p in r["pts"]]
        # abgedeckt nur durch Decks auf Fahrbahnhöhe (±1,5 m): ein fremdes Teil 6 m tiefer (Löbtauer Westrampe über
        # einem Rampenbauwerk darunter) ließ die Rampe sonst ohne Fahrbahnplatte
        cov = []
        for i in tri_tree.query(band):
            c_ = all_p[int(i)].centroid
            if abs(tri_y[int(i)] - float(np.interp(ln.project(c_), cum, ys))) < 1.5:
                cov.append(all_p[int(i)])
        Dr = unary_union(cov).buffer(0.05) if cov else Polygon()
        unc = band.difference(Dr) if not Dr.is_empty else band
        if not S.is_empty:
            unc = unc.difference(S)
        # nicht in benachbarte Brückenfahrbahnen (Richtungsfahrbahnen auf einem Deck): die bekommen ihr eigenes
        # Füllstück auf ihrer Höhe – sonst stand die Kante des fremden in der äußeren Spur (A17 Lockwitztal)
        for j in (bridge_tree.query(band) if bridge_bands else []):
            o_ = bridge_bands[int(j)]
            if o_[0] is r or unc.is_empty:
                continue
            # Überlappstreifen an der Mittellinie zwischen den Achsen teilen – nur mit Fahrbahnen auf gleicher Höhe
            # (eine Straße unter dem Deck schnitte sonst ein Loch ins Füllstück darüber)
            lnj = o_[2]
            pj = o_[0]["pts"]
            cj = np.concatenate([[0.0], np.cumsum([math.dist(a_[:2], b_[:2]) for a_, b_ in zip(pj[:-1], pj[1:])])])
            dys = []
            for f_ in np.linspace(0.1, 0.9, 5):
                qi = ln.interpolate(f_, normalized=True)
                dys.append(abs(float(np.interp(lnj.project(qi), cj, [q_[2] for q_ in pj]))
                               - float(np.interp(ln.project(qi), cum, ys))))
            if min(dys) > 1.5:
                continue
            dij = float(np.median([lnj.distance(ln.interpolate(f_, normalized=True)) for f_ in np.linspace(0.1, 0.9, 9)]))
            hw_j = min(float(o_[0]["width"]) * 0.5, max(0.5 * dij - 0.05, 0.1))
            unc = unc.difference(lnj.buffer(hw_j, cap_style="flat"))
        unc = unc.buffer(-0.15).buffer(0.15)
        if unc.is_empty or unc.area < 3.0:
            continue

        def yat(x, z):
            return float(np.interp(ln.project(Point(x, z)), cum, ys))

        # Deckstärke: recherchiert (A17 Lockwitztal 3,0 m – der zweite Überbau war als 1-m-Platte neben dem LoD2-Kasten
        # sichtbar abgesetzt); je Ecke so, dass die Unterkante ≥ 6 m über dem Gelände bleibt (Lichtraum Bahn 5,6 m),
        # zu den Widerlagern hin stetig auf 1 m auslaufend
        thick = 1.0
        rb = (decks or {}).get(int(r["id"])) if r.get("bridge") else None
        dd = _num(rb[0].get("deck_depth_m")) if rb else None
        if dd and dd > 1.0 and ter is not None:
            thick = min(dd, 4.0)

        def th_at(x, z, y):
            if thick <= 1.0:
                return 1.0
            c_, r_ = int(x - x0), int(z - z0)
            if not (0 <= c_ < 2000 and 0 <= r_ < 2000):
                return 1.0
            return min(max(y - float(ter[r_, c_]) - 6.0, 1.0), thick)

        def hole(x, z, y):
            """nur dort füllen, wo sonst ein Loch wäre (Gelände ≥ 0,5 m unter der Fahrbahn)"""
            if ter is None:
                return True
            c_, r_ = int(x - x0), int(z - z0)
            if not (0 <= c_ < 2000 and 0 <= r_ < 2000):
                return True
            if float(ter[r_, c_]) < y - 0.15:
                return True
            # Geländekante (> 1 m Abfall) im Nachbarpixel: die Kollisionsfläche rundet sie in die Fahrbahn hinein
            # (0,6 m Mulde am Fahrbahnrand: Augustusbrücke am Terrassenufer, Löbtauer Brücke) -> auch dort Deck
            return float(ter[max(r_ - 1, 0):r_ + 2, max(c_ - 1, 0):c_ + 2].min()) < y - 1.0
        top, bot, side = [], [], []
        # in 3-m-Zellen zerlegen: die Loch-Prüfung (Gelände unter der Fahrbahn) gilt dann örtlich, nicht für große
        # Dreiecke über wechselndem Gelände (sonst blieben Lücken unter der äußeren Spur)
        cells = []
        bx0, bz0, bx1, bz1 = unc.bounds
        for gx in np.arange(math.floor(bx0 / 3.0) * 3.0, bx1, 3.0):
            for gz in np.arange(math.floor(bz0 / 3.0) * 3.0, bz1, 3.0):
                cell = unc.intersection(Polygon([(gx, gz), (gx + 3.0, gz), (gx + 3.0, gz + 3.0), (gx, gz + 3.0)]))
                if not cell.is_empty and cell.area > 0.05:
                    cells += [h for h in getattr(cell, "geoms", [cell]) if h.geom_type == "Polygon" and h.area > 0.05]
        for g in cells:
            for tr in shapely.constrained_delaunay_triangles(g).geoms:
                if tr.area < 1e-4:
                    continue
                cs = list(tr.exterior.coords)[:3]
                pt = [(x, yat(x, z), z) for x, z in cs]
                cxm, czm = sum(c[0] for c in cs) / 3.0, sum(c[1] for c in cs) / 3.0
                if not hole(cxm, czm, yat(cxm, czm)) or blocks_below(cxm, czm, yat(cxm, czm), id(r)):
                    continue
                _emit(top, pt[0], pt[1], pt[2], (0.0, 1.0, 0.0))
                pb = [(x, y - th_at(x, z, y), z) for x, y, z in pt]
                _emit(bot, pb[0], pb[1], pb[2], (0.0, -1.0, 0.0))
        for g in getattr(unc, "geoms", [unc]):
            if g.geom_type != "Polygon" or g.area < 0.5:
                continue
            # Stirnseiten an freien Kanten (nicht am LoD2-Deck; nicht an den Zellgrenzen)
            free = g.exterior.difference(Dr.buffer(0.1)) if not Dr.is_empty else g.exterior
            for e in getattr(free, "geoms", [free]):
                if e.geom_type != "LineString":
                    continue
                cs = list(e.coords)
                for a, b in zip(cs[:-1], cs[1:]):
                    if math.dist(a, b) < 0.05:
                        continue
                    ya, yb = yat(*a), yat(*b)
                    if not hole(0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]), 0.5 * (ya + yb)) \
                            or blocks_below(0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]), 0.5 * (ya + yb), id(r)):
                        continue
                    ex, ez = b[0] - a[0], b[1] - a[1]
                    el = math.hypot(ex, ez)
                    nx, nz = ez / el, -ex / el
                    if g.contains(Point(0.5 * (a[0] + b[0]) + nx * 0.2, 0.5 * (a[1] + b[1]) + nz * 0.2)):
                        nx, nz = -nx, -nz
                    A, B = (a[0], ya - th_at(a[0], a[1], ya), a[1]), (b[0], yb - th_at(b[0], b[1], yb), b[1])
                    _emit(side, A, B, (b[0], yb, b[1]), (nx, 0.0, nz))
                    _emit(side, A, (b[0], yb, b[1]), (a[0], ya, a[1]), (nx, 0.0, nz))
        if top:
            city["bridge_meshes"].append({"id": f"fill:{int(r['id'])}", "top": top, "side": side, "bot": bot})
            n += 1
    return n


def deepen_decks(city, decks, ter, x0, z0):
    """LoD2-Decks recherchierter Großbrücken (Konstruktionshöhe ≥ 1,8 m, Talbrücken) auf die recherchierte Stärke:
    LoD2 liefert dort 1-m-Platten mit örtlichen Ausbuchtungen nach unten (A17 Lockwitztal: 4 m tief in Feldmitte,
    daneben der ergänzte zweite Überbau). Unterseite = Oberseite − Stärke; nur vertieft, solange sie ≥ 6 m über dem
    Gelände bleibt; Ausbuchtungen nur hoch über dem Gelände eingeebnet (Widerlagerwände bleiben). Wiederholbar
    (Ursprung in bot0/side0)."""
    depth = {}
    seen = set()
    for b, _deck in decks.values():
        if id(b) in seen:
            continue
        seen.add(id(b))
        dd = _num(b.get("deck_depth_m"))
        lod = _lit(b.get("lod2"))
        if dd and dd >= 1.8 and isinstance(lod, dict):
            for i in lod.get("ids") or []:
                depth[str(i)] = min(dd, 4.0)
    n = 0
    for bm in city.get("bridge_meshes", []):
        dd = depth.get(str(bm.get("id")))
        if not dd:
            continue
        if "bot0" not in bm:
            bm["bot0"], bm["side0"] = list(bm.get("bot") or []), list(bm.get("side") or [])
        tt = _tri_list(bm.get("top0") or bm.get("top") or [])
        polys, planes = [], []
        for q in tt:
            pg = Polygon([(q[0][0], q[0][2]), (q[1][0], q[1][2]), (q[2][0], q[2][2])])
            pl = _plane(q)
            if pg.area > 1e-4 and pl is not None:
                polys.append(pg if pg.is_valid else pg.buffer(0))
                planes.append(pl)
        if not polys:
            continue
        tree = STRtree(polys)

        def top_y(x, z):
            pt = Point(x, z)
            best = None
            for i in tree.query(pt.buffer(1.0)):
                dd_ = polys[int(i)].distance(pt)
                if dd_ <= 1.0 and (best is None or dd_ < best[0]):
                    best = (dd_, int(i))
            if best is None:
                return None
            a, b_, c = planes[best[1]]
            return float(a * x + b_ * z + c)

        def ground(x, z):
            c_, r_ = int(x - x0), int(z - z0)
            if 0 <= c_ < 2000 and 0 <= r_ < 2000:
                return float(ter[r_, c_])
            return None

        def move(flat, lower_only):
            a = np.asarray(flat, dtype=float).reshape(-1, 3).copy()
            ch = 0
            for k in range(len(a)):
                x, y, z = a[k]
                ty = top_y(x, z)
                g = ground(x, z)
                if ty is None or g is None:
                    continue
                if lower_only and y > ty - 0.3:
                    continue                                   # Oberkante einer Seitenfläche
                th = min(dd, max(ty - g - 6.0, 1.0))
                tgt = ty - th
                if y > tgt + 0.05 or (y < tgt - 0.3 and ty - g > dd + 10.0):
                    a[k, 1] = tgt
                    ch += 1
            return [round(float(v), 3) for v in a.ravel()], ch
        bm["bot"], c1 = move(bm["bot0"], False)
        bm["side"], c2 = move(bm["side0"], True)
        if c1 + c2:
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


def raise_rails(city, extra=None, ext_roads=(), name=None):
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
    for r in list(city.get("roads", [])) + list(ext_roads):
        if len(r["pts"]) < 2:
            continue
        ln = LineString([(p[0], p[1]) for p in r["pts"]])
        if ln.length < 0.5:
            continue
        hw = float(r["width"]) * 0.5 + (-0.2 if r.get("bridge") else 0.2)
        if hw <= 0.5:
            continue
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2]) for a, b in zip(r["pts"][:-1], r["pts"][1:])])])
        # runde Enden (auch Brückenwege): sonst blieb am Wegstoß bzw. hinter dem Brückenende ein Geländerstück in der
        # Fahrbahn stehen (Sosaer Straße; 416_5648 Weg 23361961: 1,5-m-Stummel 1,3 m neben der Achse); seitliche
        # Geländer an den Fahrbahnkanten liegen außerhalb des Halbkreises und bleiben
        cap = "round"
        bands.append((ln.buffer(hw, cap_style=cap), ln, cum, [p[2] for p in r["pts"]]))
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
    if name:
        from bridge_styles import style_rails                # Bauart je Bauwerk (auch für ergänzte Stücke)
        style_rails(name, out)
    city["bridge_rails"] = _kanzel_rails(city, out)
    return cut


def _kanzel_rails(city, rails):
    """Pfeilerkanzeln (bridge_arches.py "kanzeln"): Brüstung an der Kanzel öffnen und im Halbrund um sie herumführen,
    dazu der Kanzelboden auf Gehweghöhe (bridge_arches["kz_tris"], Sandstein, mit Kollision)."""
    ar = city.get("bridge_arches")
    if not isinstance(ar, dict):
        return rails
    tris, norms = [], []
    for kx, kz, nx, nz, R, yd, stone, own in ar.get("kanzeln", []):
        if own:                                              # Deck hat dort schon eine Ausbuchtung mit Geländer
            continue
        tx, tz = -nz, nx
        best = None                                          # Geländer, das die Kanzelsehne quert
        for r in rails:
            dx, dz = r[2] - r[0], r[3] - r[1]
            ln = math.hypot(dx, dz)
            if ln < 0.5 or abs((dx * tx + dz * tz) / ln) < 0.9:
                continue
            sa, sb = (r[0] - kx) * tx + (r[1] - kz) * tz, (r[2] - kx) * tx + (r[3] - kz) * tz
            if min(sa, sb) > R - 0.6 or max(sa, sb) < -(R - 0.6):
                continue
            va, vb = (r[0] - kx) * nx + (r[1] - kz) * nz, (r[2] - kx) * nx + (r[3] - kz) * nz
            v0 = va + (vb - va) * (0.0 - sa) / (sb - sa) if abs(sb - sa) > 1e-6 else va
            if abs(v0) < 2.0 and abs(float(r[4]) - yd) < 1.5 and (best is None or abs(v0) < abs(best[0])):
                best = (v0, r)
        if best is None:
            v0, y, spec = 0.0, yd, ["stone", "#6E7378", 1.1]
        else:
            v0, y, spec = best[0], float(best[1][4]), list(best[1][5:]) or ["stone", "#6E7378", 1.1]
        if stone:
            spec = ["stone", "#6E7378", 1.1]
        hc = R - 0.3                                         # halbe Sehne
        keep = []
        for r in rails:
            dx, dz = r[2] - r[0], r[3] - r[1]
            ln = math.hypot(dx, dz)
            sa, sb = (r[0] - kx) * tx + (r[1] - kz) * tz, (r[2] - kx) * tx + (r[3] - kz) * tz
            va, vb = (r[0] - kx) * nx + (r[1] - kz) * nz, (r[2] - kx) * nx + (r[3] - kz) * nz
            if (ln < 0.01 or abs((dx * tx + dz * tz) / ln) < 0.9 or abs(0.5 * (va + vb) - v0) > 1.2
                    or abs(float(r[4]) - y) > 1.0 or min(sa, sb) >= hc or max(sa, sb) <= -hc):
                keep.append(r)
                continue
            lo, hi = (0, 2) if sa < sb else (2, 0)           # Reststücke links und rechts der Sehne
            s_lo, s_hi = min(sa, sb), max(sa, sb)
            if s_lo < -hc - 0.3:
                q = list(r)
                f = (-hc - sa) / (sb - sa)
                q[lo], q[lo + 1] = r[lo], r[lo + 1]
                q[hi], q[hi + 1] = round(r[0] + dx * f, 2), round(r[1] + dz * f, 2)
                keep.append(q)
            if s_hi > hc + 0.3:
                q = list(r)
                f = (hc - sa) / (sb - sa)
                q[hi], q[hi + 1] = r[hi], r[hi + 1]
                q[lo], q[lo + 1] = round(r[0] + dx * f, 2), round(r[1] + dz * f, 2)
                keep.append(q)
        rails = keep
        cx, cz = kx + nx * v0, kz + nz * v0                  # Sehnenmitte auf der Geländerlinie
        dep = max(R - 0.3 - v0, 1.2)                         # Tiefe der Ausbuchtung
        NS = 8
        arc = [(cx + tx * hc * math.cos(math.pi * j / NS) + nx * dep * math.sin(math.pi * j / NS),
                cz + tz * hc * math.cos(math.pi * j / NS) + nz * dep * math.sin(math.pi * j / NS)) for j in range(NS + 1)]
        for p1, p2 in zip(arc[:-1], arc[1:]):
            rails.append([round(p1[0], 2), round(p1[1], 2), round(p2[0], 2), round(p2[1], 2), round(y, 3)] + spec)
        yf = y - 0.01                                        # Boden: Fächer + Streifen 0,8 m unter den Gehweg hinein
        ia, ib = (cx + tx * hc - nx * 0.8, cz + tz * hc - nz * 0.8), (cx - tx * hc - nx * 0.8, cz - tz * hc - nz * 0.8)
        for a, b, c in [((cx, cz), p1, p2) for p1, p2 in zip(arc[:-1], arc[1:])] + [(arc[0], arc[-1], ib), (arc[0], ib, ia)]:
            tris.extend([round(a[0], 3), round(yf, 3), round(a[1], 3), round(b[0], 3), round(yf, 3), round(b[1], 3),
                         round(c[0], 3), round(yf, 3), round(c[1], 3)])
            norms.extend([0.0, 1.0, 0.0])
    ar["kz_tris"], ar["kz_n"] = tris, norms
    return rails


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


def neighbour_roads(name, margin=80.0):
    """Fahrbahnen der 8 Nachbarkacheln nahe der Kachelgrenze. Geländer eines LoD2-Brückenteils reichen bis zu
    Dutzende Meter in die Nachbarkachel; dort kennt diese Kachel die Fahrbahn nicht und ließ das Geländer in ihr
    stehen (A 17, 414_5648: Lärmschutzwand 1,25 m innerhalb der Fahrbahn von 412_5648)."""
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0)
    out = []
    for de in (-2, 0, 2):
        for dn in (-2, 0, 2):
            f = TILES / f"{e_km + de}_{n_km + dn}" / "city.json"
            if (de == dn == 0) or not f.exists():
                continue
            for attempt in range(6):                       # Nachbar wird bei parallelem Lauf evtl. gerade geschrieben
                try:
                    nb = json.loads(f.read_text(encoding="utf-8"))
                    break
                except json.JSONDecodeError:
                    time.sleep(2.0)
            else:
                continue
            for r in nb.get("roads", []):
                if len(r.get("pts", [])) >= 2 and any(x0 - margin < q[0] < x0 + 2000.0 + margin and
                                                       z0 - margin < q[1] < z0 + 2000.0 + margin for q in r["pts"]):
                    out.append({"pts": r["pts"], "width": r["width"], "bridge": r.get("bridge"), "cls": r.get("cls", ""),
                                "pl": r.get("pl", 0.0), "pr": r.get("pr", 0.0)})
    return out


def tile_decks(name, decks):
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return None
    city = json.loads(cf.read_text(encoding="utf-8"))
    # Nachbardecks vorübergehend als "ext:" einhängen (Brücken über Kachelgrenzen: ein LoD2-Teil gehört nur einer
    # Kachel) – für Deckbreite, Füllstücke, Geländer und Laternen; vor Deckaufbau und Speichern wieder entfernt
    ext_parts, ext_rails = neighbours(name)
    # Platten unter Bahnbrücken (tools/rail_slabs.py) sind kein Teil dieses Schritts; rail_slabs.py legt sie danach neu an
    city["bridges"] = [b for b in city.get("bridges", []) if b.get("kind") != "rail"]
    # alte Füllstücke zuerst weg (sonst zählen sie bei der Deckbreite als Deck und erhalten sich selbst)
    city["bridge_meshes"] = [bm for bm in city.get("bridge_meshes", []) if not str(bm.get("id", "")).startswith(("ext:", "fill:"))]
    ext = [{"id": f"ext:{i}", "top": t, "top0": t} for i, t in enumerate(ext_parts)]
    city["bridge_meshes"] += ext
    nw = set_widths(city, decks)
    nc = clamp_to_decks(city, decks)
    nc += separate_slabs(city)
    nt = tram_mid(city)
    ter = np.fromfile(d / "terrain.f32", dtype="<f4").reshape(2000, 2000)
    e_km, n_km = (int(v) for v in name.split("_"))
    ns = fix_steep_slabs(city, ter, e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0))
    ns += raise_low_slabs(city)
    ns += trim_slabs_on_roads(city)
    nf = fill_decks(city, ter, e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0), decks)
    nd = deepen_decks(city, decks, ter, e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0))
    if nd:
        print(f"  {name}: {nd} LoD2-Decks auf recherchierte Konstruktionshöhe gebracht")
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
    nbr_roads = neighbour_roads(name)
    st = deck_layout(city, raw_walk, nbr_roads)
    city["bridge_meshes"] = own + [bm for bm in allm if str(bm.get("id", "")).startswith("ext:")]
    if "bridge_rails0" not in city:
        city["bridge_rails0"] = [list(r) for r in city.get("bridge_rails", [])]
    extra = missing_rails(city, ter, e_km * 1000.0 - 411000.0, -((n_km + 2) * 1000.0 - 5656200.0), ext_rails)
    st["rails_add"] = len(extra)
    st["rails_cut"] = raise_rails(city, extra, nbr_roads, name)
    st["poles"] = bridge_tram_poles(city)
    # Laternen, die spätere Schritte ergänzt haben (nicht in lamps0), bleiben erhalten
    k0 = {(round(l[0], 1), round(l[1], 1)) for l in city.get("lamps0") or []}
    extra_lamps = [l for l in city.get("lamps", []) if (round(l[0], 1), round(l[1], 1)) not in k0] if k0 else []
    st["lamps"] = lift_lamps(city)
    city["lamps"] += extra_lamps
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
