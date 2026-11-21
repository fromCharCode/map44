"""Befahrbare Straßentunnel (Nachbearbeitung, alle Kacheln auf einmal): city["tunnels"], Gelände/Kollision angepasst.

  python tools/tunnels.py [--dry]

OSM-Wege mit tunnel=yes (Kfz-Straßen, ≥ 25 m) werden zu Ketten verbunden (Portal bis Portal), ihr Längsprofil läuft
linear zwischen den Höhen der anschließenden Straßen (city.json roads) an beiden Portalen. Je Stützpunkt (2 m):
  * Überdeckung = sichtbares Gelände (terrain.f32) − Fahrbahn. Liegt sie unter 4,95 m (Röhrendecke 4,8 m), ist der Abschnitt
    ein Portal-/Trogbauwerk ("box"): im Spiel ein Betonkasten mit Decke. Sonst Röhre unter dem Hang.
  * Sichtbares Gelände im Lichtraum blendet der Shader aus.
  * Kollisionsraster (terrain_col.f32) im ganzen Tunnelband unter die Fahrbahnplatte abgesenkt; über der Röhre legt das
    Spiel einen Kollisionsdeckel in Geländehöhe (scripts/tunnels.gd).
  * Sichtbares Gelände über Kasten, Portal und flach überdeckter Röhre geglättet (_cover_terrain); kurze Kästen vor
    steilem Hang bekommen eine Stirnwand bis ans Gelände ("h0"/"h1", _head) und werden bis dorthin überschüttet.
Ausgabe je Kachel: city["tunnels"] = [{"name", "w", "pts": [[x, z, y, gelände], …], "box": [0|1, …], "p0", "p1",
"h0", "h1"}]
(Stützpunkte der Kette, die in der Kachel ± 30 m liegen; p0/p1 = Portal am Kettenanfang/-ende liegt in der Kachel).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import linemerge

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
VEH = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
       "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
CLEAR = 4.8          # lichte Höhe
ROOF = 0.6           # Deckenstärke
COVER = CLEAR + 0.15     # darunter ragte die Röhrendecke aus dem Gelände -> Bauwerk
WALL = 1.2           # Wandstärke
STEP = 2.0
MARGIN = 30.0
EXT = 2.0            # Verlängerung an den Portalen
SKIP = set(json.loads((ROOT / "tools" / "overrides.json").read_text(encoding="utf-8")).get("skip_tunnels", []))


def _local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def tile_of(x, z):
    e = int(math.floor((x + ORIGIN_E) / 1000.0))
    n = int(math.floor((ORIGIN_N - z) / 1000.0))
    return f"{e - e % 2}_{n - n % 2}"


def tile_origin(name):
    e_km, n_km = (int(v) for v in name.split("_"))
    return e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)


_cache = {}


def _tile(name):
    if name not in _cache:
        d = TILES / name
        if not (d / "city.json").exists():
            _cache[name] = None
        else:
            raw = np.frombuffer((d / "terrain_raw.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)
            ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)
            raw = ter                       # sichtbares Gelände (Anfahrtströge, Terrassen) zählt, nicht das DGM
            city = json.loads((d / "city.json").read_text(encoding="utf-8"))
            _cache[name] = {"raw": raw, "roads": city.get("roads", []), "graph": city.get("graph", {})}
    return _cache[name]


def raw_at(x, z):
    t = _tile(tile_of(x, z))
    if t is None:
        return None
    x0, z0 = tile_origin(tile_of(x, z))
    c = min(max(int(x - x0), 0), 1999)
    r = min(max(int(z - z0), 0), 1999)
    return float(t["raw"][r, c])


def road_at(x, z):
    """Höhe und Breite der an (x, z) anschließenden Straße (nächster Stützpunkt ≤ 4 m)."""
    t = _tile(tile_of(x, z))
    if t is None:
        return None
    best = None
    for r in t["roads"]:
        for p in r["pts"]:
            d = math.hypot(p[0] - x, p[1] - z)
            if d < 4.0 and (best is None or d < best[0]):
                best = (d, float(p[2]), float(r["width"]))
    return best[1:] if best else None


def node_near(x, z, rad=3.0):
    """Graphknoten (Kachel, Knoten-dict) am Portal (nächster ≤ rad m)."""
    tn = tile_of(x, z)
    t = _tile(tn)
    if t is None:
        return None
    best = None
    for n in t["graph"].get("nodes", []):
        if n.get("tnode"):
            continue
        d = math.hypot(n["pos"][0] - x, n["pos"][2] - z)
        if d < rad and (best is None or d < best[0]):
            best = (d, n)
    return (tn, best[1]) if best else None


def approach(pt, inward, w):
    """Anfahrtstrog vor einem Portal: der Straße ab dem Portal nach außen folgen, solange das Gelände neben der
    Fahrbahn höher liegt (Einschnitt). Ergebnis [[x, z, y, wand_links, wand_rechts], …] (Wandhöhe über der Fahrbahn,
    0 = keine), links/rechts in Laufrichtung vom Portal weg – oder None."""
    t = _tile(tile_of(*pt))
    if t is None:
        return None
    best = None
    for r in t["roads"]:
        ps = r["pts"]
        if len(ps) < 2 or r.get("bridge") or r["cls"] not in VEH:
            continue
        for end, seq in ((0, ps), (-1, ps[::-1])):
            d = math.hypot(ps[end][0] - pt[0], ps[end][1] - pt[1])
            if d > 4.0:
                continue
            dx, dz = seq[1][0] - seq[0][0], seq[1][1] - seq[0][1]
            dl = math.hypot(dx, dz) or 1.0
            if (dx * inward[0] + dz * inward[1]) / dl > 0.2:
                continue                                    # führt in den Tunnel hinein
            if best is None or d < best[0]:
                best = (d, seq, r)
    if best is None:
        return None
    _d, seq, road = best
    ln = LineString([(q[0], q[1]) for q in seq])
    cum = np.concatenate([[0.0], np.cumsum([math.dist(a_[:2], b_[:2]) for a_, b_ in zip(seq[:-1], seq[1:])])])
    ys = [q[2] for q in seq]
    others = [(np.array([[q[0], q[1], q[2]] for q in r["pts"]]), float(r["width"]) * 0.5 + 0.6)
              for r in t["roads"] if r is not road and r["cls"] in VEH and len(r["pts"]) >= 2]
    e = max(w, float(road["width"])) * 0.5 + 0.35
    out = []
    L = min(ln.length, 240.0)
    n = max(2, int(L / 2.0) + 1)
    for i in range(n):
        s_ = L * i / (n - 1)
        p = ln.interpolate(s_)
        a_, b_ = ln.interpolate(max(s_ - 1.0, 0.0)), ln.interpolate(min(s_ + 1.0, ln.length))
        dl = math.hypot(b_.x - a_.x, b_.y - a_.y) or 1.0
        nx, nz = -(b_.y - a_.y) / dl, (b_.x - a_.x) / dl
        y = float(np.interp(s_, cum, ys))
        hs = []
        for sd in (-1.0, 1.0):                              # −n = links der Laufrichtung (Godot: x/z-Ebene)
            wx, wz = p.x + nx * e * sd, p.y + nz * e * sd
            tops = [raw_at(p.x + nx * (e + o) * sd, p.y + nz * (e + o) * sd) for o in (0.8, 1.6, 2.6, 3.6)]
            tops = [v for v in tops if v is not None]
            h = (max(tops) - y) if tops else 0.0
            for arr, rad in others:                          # andere Fahrbahn auf gleicher Höhe direkt daneben: keine Wand
                dd = np.hypot(arr[:, 0] - wx, arr[:, 1] - wz)
                j = int(dd.argmin())
                if dd[j] < rad + 1.5 and abs(arr[j, 2] - y) < 1.5:
                    h = 0.0
                    break
            hs.append(h)
        out.append([round(p.x, 2), round(p.y, 2), round(y, 3), hs[0], hs[1]])
    # glätten (Oberkante folgt dem Gelände ohne Zacken), Ende des Einschnitts suchen
    for k in (3, 4):
        v = np.array([q[k] for q in out])
        sm = np.array([v[max(i - 2, 0):i + 3].max() for i in range(len(v))])
        sm = np.array([sm[max(i - 2, 0):i + 3].mean() for i in range(len(sm))])
        for i, q in enumerate(out):
            q[k] = round(min(float(sm[i]) + 0.15, 9.0), 2) if sm[i] >= 0.7 else 0.0
    last = max((i for i, q in enumerate(out) if q[3] > 0 or q[4] > 0), default=-1)
    if last < 3:
        return None
    return out[:last + 2], max(w, float(road["width"]))


def chains():
    ways = {}
    for d in sorted(RAW.iterdir()):
        f = d / "osm" / "roads.json"
        if not f.exists():
            continue
        for el in json.loads(f.read_text(encoding="utf-8")).get("elements", []):
            t = el.get("tags") or {}
            if el.get("type") != "way" or el["id"] in ways or t.get("tunnel") != "yes" or t.get("highway") not in VEH:
                continue
            g = el.get("geometry") or []
            if len(g) < 2:
                continue
            ways[el["id"]] = (LineString([_local(p["lon"], p["lat"]) for p in g]), t)
    # Teilstücke derselben Fahrtrichtung verbinden (Endpunkt = Anfangspunkt)
    merged = linemerge([ln for ln, _ in ways.values()])
    out = []
    for ln in getattr(merged, "geoms", [merged]):
        if ln.length < 25.0:
            continue
        # Name/Klasse/Fahrstreifen vom längsten Teilweg der Kette
        best = max((w for w in ways.values() if w[0].distance(ln.interpolate(0.5, normalized=True)) < 3.0
                    or ln.buffer(1.0).contains(w[0].interpolate(0.5, normalized=True))),
                   key=lambda w: w[0].length, default=(None, {}))
        if best[0] is not None:
            w0 = best[0]
            m = w0.interpolate(0.5, normalized=True)
            sw = w0.project(m)
            a1, b1 = w0.interpolate(max(sw - 2, 0)), w0.interpolate(min(sw + 2, w0.length))
            sc = ln.project(m)
            a2, b2 = ln.interpolate(max(sc - 2, 0)), ln.interpolate(min(sc + 2, ln.length))
            if (b1.x - a1.x) * (b2.x - a2.x) + (b1.y - a1.y) * (b2.y - a2.y) < 0:
                ln = LineString(list(ln.coords)[::-1])
        zone = ln.buffer(1.0)
        ids = {wid for wid, (w, _t) in ways.items() if zone.contains(w.interpolate(0.5, normalized=True))}
        out.append((ln, best[1], ids))
    return out


def _in_city(ids, ln):
    """Kette ist schon als Straße in city.json (build_city.find_underpasses: Unterführung unter einer Brücke)?"""
    for k in range(5):
        p = ln.interpolate(k / 4.0, normalized=True)
        t = _tile(tile_of(p.x, p.y))
        if t is not None and any(int(r["id"]) in ids for r in t["roads"]):
            return True
    return False


def build():
    dry = "--dry" in sys.argv
    per_tile = {}
    troughs = {}           # Kachel -> Anfahrtströge
    graph_add = {}         # Kachel -> [(Kante, Endknoten aus Nachbarkachel oder None)]
    n_ch = 0
    for ln, tags, ids in chains():
        if _in_city(ids, ln):
            print(f"  (Unterführung als Straße gebaut: {tags.get('name') or tags.get('highway')}, {ln.length:.0f} m)")
            continue
        a, b = ln.coords[0], ln.coords[-1]
        ra, rb = road_at(*a), road_at(*b)
        if ra is None or rb is None:
            continue                     # Kette endet nicht an einer Straße im Spiel (z. B. außerhalb)
        ya, yb = ra[0], rb[0]
        w = max(min(0.5 * (ra[1] + rb[1]), 14.0), 6.0)
        # an beiden Portalen 2 m nach außen verlängern (Portalwand vor dem Hangfuß, kein Geländestreifen davor)
        cs = list(ln.coords)
        def _ext(p_end, p_in, y_end):
            # nach außen, solange der Hang noch über der Fahrbahn liegt (Portal z. B. direkt hinter der A17-
            # Talbrücke: OSM-Tunnel beginnt erst am Hangfuß), dann noch EXT m
            dx, dz = p_end[0] - p_in[0], p_end[1] - p_in[1]
            dl = math.hypot(dx, dz) or 1.0
            dx, dz = dx / dl, dz / dl
            e = 0.0
            while e < 40.0:
                g = raw_at(p_end[0] + dx * (e + 1.0), p_end[1] + dz * (e + 1.0))
                if g is None or g < y_end + 1.0:
                    break
                e += 1.0
            e += EXT
            return (p_end[0] + dx * e, p_end[1] + dz * e), e
        pa, ea = _ext(cs[0], cs[1], ya)
        pb, eb = _ext(cs[-1], cs[-2], yb)
        ln = LineString([pa] + cs + [pb])
        L = ln.length
        # Höhe an den verlängerten Enden = anschließende Straße bzw. Gelände dort (sonst Stufe an der Platte,
        # wenn die Anfahrt außerhalb des Portals steigt/fällt)
        def _end_y(pt, y_portal):
            # Gelände dort, wo die Verlängerung endet (darauf fährt man an); unter einer Brücke (Gelände weit
            # unten, A17) die anschließende Straße
            g = raw_at(*pt)
            if g is not None and abs(g - y_portal) < 2.5:
                return g
            r = road_at(*pt)
            if r is not None and abs(r[0] - y_portal) < 4.0:
                return r[0]
            return y_portal
        ya_x, yb_x = _end_y(pa, ya), _end_y(pb, yb)

        def prof(s_):
            if s_ <= ea:
                return ya_x + (ya - ya_x) * (s_ / ea if ea > 0 else 1.0)
            if s_ >= L - eb:
                return yb + (yb_x - yb) * ((s_ - (L - eb)) / eb if eb > 0 else 0.0)
            return ya + (yb - ya) * (s_ - ea) / max(L - ea - eb, 1e-6)
        n = max(2, int(L / STEP) + 1)
        pts, box = [], []
        for i in range(n):
            s = L * i / (n - 1)
            p = ln.interpolate(s)
            y = prof(s)
            g = raw_at(p.x, p.y)
            cover = (g - y) if g is not None else 99.0
            pts.append([round(p.x, 2), round(p.y, 2), round(y, 3), round(g if g is not None else y + 99.0, 2)])
            box.append(1 if cover < COVER else 0)
        # einzelne Röhrenstücke zwischen Kästen (< 10 m) schließen, kurze Kästen in der Röhre zulassen
        for i in range(1, n - 1):
            if box[i] == 0 and box[i - 1] == 1 and i + 4 < n and any(box[i + 1:i + 5]):
                box[i] = 1
        hp = (_head(pts, box), _head(pts[::-1], box[::-1]))
        name = tags.get("name") or tags.get("tunnel:name") or ""
        if name in SKIP:
            print(f"  (übersprungen laut overrides.json: {name})")
            continue
        if L < 40.0 or (n - sum(box)) * STEP < 20.0:
            # kurze Unterführungen ohne Überdeckung (unter Bahn-/Straßenbrücken): Gelände liegt schon auf
            # Fahrbahnhöhe, ein Betonkasten stieße an die Brücke darüber -> nichts bauen
            print(f"  (übersprungen: {name or tags.get('highway')}, {L:.0f} m, Röhre {(n - sum(box)) * STEP:.0f} m)")
            continue
        n_ch += 1
        # Anfahrtströge: senkrechte Betonwände statt der gezackten Geländeböschung neben der Rampe
        for pt, inw in ((a, (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])), (b, (cs[-2][0] - cs[-1][0], cs[-2][1] - cs[-1][1]))):
            il = math.hypot(*inw) or 1.0
            res = approach(pt, (inw[0] / il, inw[1] / il), w)
            if res:
                # Trogbreite = breitere von Röhre und anschließender Straße (sonst standen die Trogwände in der
                # Fahrbahn einer breiteren Zufahrt, z. B. Waldschlößchen Ost: Röhre 7 m, Straße 9,5 m)
                tr, tw = res
                for tn in {tile_of(q[0], q[1]) for q in tr}:
                    x0_, z0_ = tile_origin(tn)
                    sub = [q for q in tr if x0_ - MARGIN <= q[0] < x0_ + 2000 + MARGIN and z0_ - MARGIN <= q[1] < z0_ + 2000 + MARGIN]
                    if len(sub) >= 2:
                        troughs.setdefault(tn, []).append({"w": round(tw, 2), "pts": sub})
        print(f"  Tunnel {name or tags.get('highway')}: {L:.0f} m, y {ya:.1f} → {yb:.1f}, Breite {w:.1f} m, "
              f"Bauwerk {sum(box) * STEP:.0f} m / Röhre {(n - sum(box)) * STEP:.0f} m")
        tiles = {tile_of(p[0], p[1]) for p in pts}
        for tn in tiles:
            x0, z0 = tile_origin(tn)
            keep = [i for i, p in enumerate(pts) if x0 - MARGIN <= p[0] < x0 + 2000 + MARGIN
                    and z0 - MARGIN <= p[1] < z0 + 2000 + MARGIN]
            if len(keep) < 2:
                continue
            i0, i1 = keep[0], keep[-1]
            sub = {"name": name, "w": round(w, 2), "pts": pts[i0:i1 + 1], "box": box[i0:i1 + 1],
                   "p0": i0 == 0 and tile_of(*pts[0][:2]) == tn, "p1": i1 == n - 1 and tile_of(*pts[-1][:2]) == tn,
                   "h0": hp[0], "h1": hp[1]}
            per_tile.setdefault(tn, []).append(sub)
        # Verkehrsgraph: Kante Portalknoten -> Portalknoten, damit die KI durch den Tunnel fährt
        na, nb = node_near(*a), node_near(*b)
        if na and nb:
            ta, nda = na
            tb, ndb = nb
            hwy = tags.get("highway")
            ow = 1 if (tags.get("oneway") in ("yes", "1", "true") or hwy in ("motorway", "motorway_link")) else 0
            try:
                spd = float(str(tags.get("maxspeed", "")).split()[0])
            except (ValueError, IndexError):
                spd = 0.0
            if spd <= 0.0:
                spd = {"motorway": 80.0, "trunk": 70.0, "primary": 50.0}.get(hwy, 50.0)
            try:
                lanes = int(str(tags.get("lanes", "2")).split(";")[0])
            except ValueError:
                lanes = 2
            epts = [[round(nda["pos"][0], 2), round(nda["pos"][2], 2), round(nda["pos"][1], 3)]]
            for i in range(n):
                si = L * i / (n - 1)
                if ea + 1.0 < si < L - eb - 1.0 and i % 2 == 0:
                    epts.append(pts[i][:3])
            epts.append([round(ndb["pos"][0], 2), round(ndb["pos"][2], 2), round(ndb["pos"][1], 3)])
            edge = {"a": int(nda["id"]), "b": int(ndb["id"]), "cls": hwy, "lanes": lanes, "oneway": ow, "speed": spd,
                    "width": round(w, 2), "len": round(L - ea - eb, 1), "bridge": False, "pts": epts, "name": name,
                    "wid": 0, "pl": 0.0, "pr": 0.0, "prio": True, "rb": False, "bus": False, "tunnel": True}
            graph_add.setdefault(ta, []).append((edge, None if tb == ta else ndb))
    _unify_heads(per_tile)
    print(f"{n_ch} Tunnelketten, Kacheln: {len(per_tile)}, Verkehrskanten: {sum(len(v) for v in graph_add.values())}, "
          f"Anfahrtströge: {sum(len(v) for v in troughs.values())}")
    if dry:
        return
    for d in sorted(TILES.iterdir()):
        cf = d / "city.json"
        if not cf.exists():
            continue
        tl = per_tile.get(d.name, [])
        city = json.loads(cf.read_text(encoding="utf-8"))
        had = bool(city.get("tunnels"))
        if not tl and not had and not troughs.get(d.name) and "troughs" not in city:
            continue
        city["tunnels"] = tl
        if troughs.get(d.name):
            city["troughs"] = troughs[d.name]
        else:
            city.pop("troughs", None)
        # Verkehrskanten: alte Tunnelkanten/-knoten entfernen (wiederholbar), neue anhängen
        g = city.get("graph")
        if g is not None:
            g["edges"] = [e for e in g["edges"] if not e.get("tunnel")]
            g["nodes"] = [nd for nd in g["nodes"] if not nd.get("tnode")]
            for edge, other in graph_add.get(d.name, []):
                e = dict(edge)
                if other is not None:
                    nid = len(g["nodes"])
                    g["nodes"].append({"id": nid, "pos": other["pos"], "signal": False, "tnode": True})
                    e["b"] = nid
                g["edges"].append(e)
        if tl:
            _clear_objects(d, city, tl)
            _terrain(d, tl)
            _cover_terrain(d, tl)
            # Bäume im Grundriss der Portalbauwerke entfernen (stünden sonst auf/in der Decke)
            x0, z0 = tile_origin(d.name)
            boxes = []
            for t in tl:
                for i, p in enumerate(t["pts"]):
                    if t["box"][i]:
                        boxes.append((p[0], p[1], t["w"] * 0.5 + WALL + 1.0))
            if boxes and city.get("trees"):
                bx = np.array(boxes)
                keep = []
                for tr in city["trees"]:
                    dd = np.hypot(bx[:, 0] - tr[0], bx[:, 1] - tr[1])
                    if not (dd < bx[:, 2]).any():
                        keep.append(tr)
                city["trees"] = keep
        if troughs.get(d.name):
            _trough_terrain(d, troughs[d.name])
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")


def _trough_terrain(d, trs):
    """Gelände im Trog bis an die Wände auf die Fahrbahnhöhe absenken (sichtbar und Kollision): das Geländemodell
    hat dort eine gezackte Böschung, die vor den senkrechten Wänden in die Fahrbahn ragte."""
    x0, z0 = tile_origin(d.name)
    for fn, n, off in (("terrain.f32", 2000, 0.5), ("terrain_col.f32", 2001, 0.0)):
        f = d / fn
        if not f.exists():
            continue
        arr = np.frombuffer(f.read_bytes(), dtype="<f4").reshape(n, n).copy()
        ch = 0
        for tr in trs:
            pts = tr["pts"]
            e = tr["w"] * 0.5 + 1.45                    # bis hinter die Wand (1,4 m stark): kein Geländekeil davor
            for a, b in zip(pts[:-1], pts[1:]):
                dx, dz = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dz)
                if L < 0.05:
                    continue
                tx, tz = dx / L, dz / L
                nx, nz = -tz, tx
                lo = -e if max(a[3], b[3]) > 0 else 0.0     # nur zur Seite mit Wand
                hi = e if max(a[4], b[4]) > 0 else 0.0
                if hi - lo < 0.5:
                    continue
                c0 = int(max(min(a[0], b[0]) - x0 - e - 2, 0)); c1 = int(min(max(a[0], b[0]) - x0 + e + 3, n))
                r0 = int(max(min(a[1], b[1]) - z0 - e - 2, 0)); r1 = int(min(max(a[1], b[1]) - z0 + e + 3, n))
                if c1 <= c0 or r1 <= r0:
                    continue
                gx, gz = np.meshgrid(np.arange(c0, c1) + off + x0, np.arange(r0, r1) + off + z0)
                s_ = (gx - a[0]) * tx + (gz - a[1]) * tz
                v_ = (gx - a[0]) * nx + (gz - a[1]) * nz
                m = (s_ >= -0.6) & (s_ <= L + 0.6) & (v_ >= lo) & (v_ <= hi)
                if not m.any():
                    continue
                y = a[2] + (b[2] - a[2]) * np.clip(s_ / L, 0.0, 1.0)
                sub = arr[r0:r1, c0:c1]
                low = m & (sub > y + 0.04)
                sub[low] = y[low]
                ch += int(low.sum())
        f.write_bytes(arr.astype("<f4").tobytes())
        print(f"  {d.name}: Trog-Gelände {fn}: {ch} Punkte abgesenkt")


HEAD_MAX = 4.0       # Stirnwand höchstens so viel über die Kastendecke hinaus
HEAD_RUN = 30.0      # längere Kästen am Portal: Decke liegt frei (offene Bauweise), keine hohe Stirnwand


def _head(pts, box):
    """Höhe der Stirnwand über der Fahrbahn am Kettenanfang: Endet der Kasten am Portal nach kurzer Strecke an
    einem steilen Hang (Überdeckung der Röhre dahinter höher als die Kastendecke), reicht die Portalwand bis an das
    Gelände dahinter, und der Kasten wird bis dorthin überschüttet (sonst Mulde/Geländekante über dem Portal)."""
    k = 0
    while k < len(box) and box[k]:
        k += 1
    deck = CLEAR + ROOF
    if k >= len(box) or k * STEP > HEAD_RUN:
        return round(deck, 2)
    cov = sorted(p[3] - p[2] for p in pts[max(k, 1):max(k, 1) + 4])
    return round(min(max(cov[len(cov) // 2], deck), deck + HEAD_MAX), 2)


def _unify_heads(per_tile, rad=25.0):
    """Nebeneinanderliegende Portale (Zwillingsröhren, Rampen mit gemeinsamem Bauwerk) bekommen dieselbe
    Stirnwandhöhe (die größte der Gruppe) – sonst stehen unterschiedlich hohe Portalrahmen nebeneinander."""
    ends = []
    for subs in per_tile.values():
        for t in subs:
            for key, i in (("p0", 0), ("p1", -1)):
                if t.get(key):
                    ends.append((t, "h" + key[1], t["pts"][i][0], t["pts"][i][1]))
    grp = list(range(len(ends)))

    def root(i):
        while grp[i] != i:
            grp[i] = grp[grp[i]]
            i = grp[i]
        return i
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            if math.hypot(ends[i][2] - ends[j][2], ends[i][3] - ends[j][3]) < rad:
                grp[root(i)] = root(j)
    top = {}
    for i, e in enumerate(ends):
        top[root(i)] = max(top.get(root(i), 0.0), e[0][e[1]])
    for i, e in enumerate(ends):
        e[0][e[1]] = top[root(i)]


COVER_BLEND = 3.0    # Übergang der geglätteten Decke ins umliegende Gelände (m)


def _cover_terrain(d, tl):
    """Sichtbares Gelände über den Tunnelbauwerken glätten (terrain.f32): Das Geländemodell (2-m-Raster) hat über
    Portal und Kasten Buckel und Mulden – über dem flachen Kastendach ragten Geländebuckel heraus, an flach
    überdeckten Röhrenstücken schnitt der Shader Löcher bis in die Röhre. Im Band (Außenwand + 0,5 m):
      * Kasten ("box"): Gelände knapp unter die Dachoberkante -> das Betondach ist die glatte Decke, höheres
        Gelände daneben läuft über COVER_BLEND m auf die Dachkante herunter,
      * Röhre: Gelände mindestens auf Dachoberkante (keine Löcher in der Überdeckung),
      * kurzer Kasten am Portal vor steilem Hang (Stirnwand "h0"/"h1" höher als die Decke, _head): Kasten bis auf
        Stirnwandhöhe überschüttet, Gelände daneben läuft in beide Richtungen auf diese Höhe.
    Wiederholbar (nur Klemmungen)."""
    f = d / "terrain.f32"
    if not f.exists():
        return
    x0, z0 = tile_origin(d.name)
    arr = np.frombuffer(f.read_bytes(), dtype="<f4").reshape(2000, 2000).copy()
    orig = arr.copy()
    # Schutzflächen: Lichtraum aller Röhren (Rand eines Kastens darf nicht in die Nachbarröhre) und die Zufahrt vor
    # jedem Portal (versetzte Zwillingsportale: Band/Rand der einen Röhre stünde sonst vor der Öffnung der anderen)
    corr = np.zeros((2000, 2000), dtype=bool)
    appr = np.zeros((2000, 2000), dtype=bool)
    for t in tl:
        pts = t["pts"]
        band = t["w"] * 0.5 + WALL + 0.5
        segs = [(pts[i], pts[i + 1], -0.6, 0.6, corr) for i in range(len(pts) - 1)]
        if t.get("p0"):
            segs.append((pts[0], pts[1], -10.0, None, appr))
        if t.get("p1"):
            segs.append((pts[-1], pts[-2], -10.0, None, appr))
        for a, b, lo_, hi_, mk in segs:
            dx, dz = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dz)
            if L < 0.05:
                continue
            hi_ = 0.0 if hi_ is None else L + hi_
            r = band + 1.0
            c0 = int(max(min(a[0], b[0]) - x0 - r - 11, 0)); c1 = int(min(max(a[0], b[0]) - x0 + r + 12, 2000))
            r0 = int(max(min(a[1], b[1]) - z0 - r - 11, 0)); r1 = int(min(max(a[1], b[1]) - z0 + r + 12, 2000))
            if c1 <= c0 or r1 <= r0:
                continue
            gx, gz = np.meshgrid(np.arange(c0, c1) + 0.5 + x0, np.arange(r0, r1) + 0.5 + z0)
            s_ = ((gx - a[0]) * dx + (gz - a[1]) * dz) / L
            v_ = np.abs((gx - a[0]) * -dz + (gz - a[1]) * dx) / L
            mk[r0:r1, c0:c1] |= (s_ >= lo_) & (s_ <= hi_) & (v_ <= (band if mk is corr else r))
    for pass_box in (False, True):                       # erst Röhren anheben, dann Kästen (Kasten gewinnt)
        for t in tl:
            pts, box = t["pts"], t["box"]
            band = t["w"] * 0.5 + WALL + 0.5
            e = band + COVER_BLEND
            n = len(pts)
            lev = [CLEAR + ROOF] * n                     # Geländehöhe über der Fahrbahn im Band
            for key, idx in (("p0", range(n)), ("p1", range(n - 1, -1, -1))):
                hh = float(t.get("h" + key[1], 0.0))
                if t.get(key) and hh > CLEAR + ROOF + 0.05:
                    for j in idx:
                        if not box[j]:
                            break
                        lev[j] = hh
            for i in range(n - 1):
                if bool(box[i] or box[i + 1]) != pass_box:
                    continue
                a, b = pts[i], pts[i + 1]
                dx, dz = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dz)
                if L < 0.05:
                    continue
                tx, tz = dx / L, dz / L
                nx, nz = -tz, tx
                # 2 m vor der Portalwand enden: der Abhang zum Trog bleibt im Band (Shader blendet ihn aus),
                # sonst stünde er als Geländewand vor der Öffnung
                s_lo = 2.0 if (i == 0 and t.get("p0")) else -0.6
                s_hi = L - 2.0 if (i == n - 2 and t.get("p1")) else L + 0.6
                c0 = int(max(min(a[0], b[0]) - x0 - e - 2, 0)); c1 = int(min(max(a[0], b[0]) - x0 + e + 3, 2000))
                r0 = int(max(min(a[1], b[1]) - z0 - e - 2, 0)); r1 = int(min(max(a[1], b[1]) - z0 + e + 3, 2000))
                if c1 <= c0 or r1 <= r0:
                    continue
                gx, gz = np.meshgrid(np.arange(c0, c1) + 0.5 + x0, np.arange(r0, r1) + 0.5 + z0)
                s_ = (gx - a[0]) * tx + (gz - a[1]) * tz
                v_ = np.abs((gx - a[0]) * nx + (gz - a[1]) * nz)
                inb = (s_ >= s_lo) & (s_ <= s_hi) & (v_ <= band)
                deck = a[2] + (b[2] - a[2]) * np.clip(s_ / L, 0.0, 1.0) + CLEAR + ROOF
                sub = arr[r0:r1, c0:c1]
                ap = appr[r0:r1, c0:c1]
                inb &= ~ap
                rim = (s_ >= s_lo) & (s_ <= s_hi) & (v_ > band) & (v_ <= e) & ~ap & ~corr[r0:r1, c0:c1]
                if not pass_box:
                    up = inb & (sub < deck)
                    sub[up] = deck[up]
                    continue
                head = max(lev[i], lev[i + 1]) - (CLEAR + ROOF)
                k = np.clip((v_ - band) / COVER_BLEND, 0.0, 1.0)
                if head > 0.05:
                    # überschütteter Kasten: Band auf Stirnwandhöhe, Rand in beide Richtungen angeglichen
                    top = deck + head
                    sub[inb] = top[inb]
                    tgt = top + (sub - top) * k
                    sub[rim] = tgt[rim]
                    continue
                sub[inb] = deck[inb] - 0.05
                # daneben: höheres Gelände läuft auf die Dachkante herunter
                tgt = deck + (sub - deck) * k
                lo = rim & (sub > tgt)
                sub[lo] = tgt[lo]
    ch = int((np.abs(arr - orig) > 0.01).sum())
    f.write_bytes(arr.astype("<f4").tobytes())
    print(f"  {d.name}: Gelände über Tunnelbauwerken: {ch} Punkte geglättet")


def _clear_objects(d, city, tl):
    """Objekte im Lichtraum der Röhre entfernen (vorher endete die Straße am Portal: Treppen, Mauern, Laternen,
    Masten … standen dort im Weg). Was oben auf dem Hang steht (Gelände ≥ Röhrendach), bleibt."""
    x0, z0 = tile_origin(d.name)
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)
    from shapely.geometry import MultiLineString
    from shapely.strtree import STRtree
    segs = []
    for t in tl:
        hw = t["w"] * 0.5 + WALL + 0.8
        q = t["pts"]
        for i in range(len(q) - 1):
            segs.append((LineString([(q[i][0], q[i][1]), (q[i + 1][0], q[i + 1][1])]), hw, q[i][2], q[i + 1][2]))
    tree = STRtree([sg[0] for sg in segs])

    def low_inside(x, z):
        p = Point(x, z)
        for j in tree.query(p.buffer(12.0)):
            ln, hw, ya, yb = segs[int(j)]
            if ln.distance(p) < hw:
                t_ = ln.project(p) / max(ln.length, 1e-6)
                y = ya + (yb - ya) * t_
                c = min(max(int(x - x0), 0), 1999)
                r = min(max(int(z - z0), 0), 1999)
                if float(ter[r, c]) < y + CLEAR + ROOF + 0.3:
                    return True
        return False

    n = 0
    for key in ("lamps", "props", "tram_poles", "signals", "signal_heads", "manholes", "grates", "parked", "trees"):
        lst = city.get(key)
        if not lst:
            continue
        keep = [it for it in lst if not low_inside(float(it[0]), float(it[1]))]
        n += len(lst) - len(keep)
        city[key] = keep
    life = city.get("life") or {}
    for key, ix in (("furniture", 1), ("signs", 2), ("litter", 1)):
        lst = life.get(key)
        if lst:
            keep = []
            for it in lst:
                try:
                    x, z = float(it[ix]), float(it[ix + 1])
                except (TypeError, ValueError, IndexError):
                    keep.append(it)
                    continue
                if not low_inside(x, z):
                    keep.append(it)
            n += len(lst) - len(keep)
            life[key] = keep
    # LoD2-Brückenteile (oft das Portalbauwerk selbst als "Brücke" erfasst): Dreiecke im Lichtraum entfernen
    def in_clear(x, y, z):
        p = Point(x, z)
        for j in tree.query(p.buffer(12.0)):
            ln, hw, ya, yb = segs[int(j)]
            if ln.distance(p) < hw - 0.8:
                t_ = ln.project(p) / max(ln.length, 1e-6)
                yf = ya + (yb - ya) * t_
                return yf - 0.6 < y < yf + CLEAR + 0.2
        return False
    for m in city.get("bridge_meshes", []):
        for key in ("top", "top0", "side", "bot", "top_walk", "top_ballast", "top_conc", "curb"):
            v = m.get(key) or []
            if not v:
                continue
            out = []
            dropped = 0
            for k in range(0, len(v) - 8, 9):
                cx = (v[k] + v[k + 3] + v[k + 6]) / 3.0
                cy = (v[k + 1] + v[k + 4] + v[k + 7]) / 3.0
                cz = (v[k + 2] + v[k + 5] + v[k + 8]) / 3.0
                if in_clear(cx, cy, cz):
                    dropped += 1
                    continue
                out.extend(v[k:k + 9])
            if dropped:
                m[key] = out
                n += dropped
    # Linienobjekte (Mauern, Zäune, Treppen) im Lichtraum herausschneiden (1-m-Stücke)
    for key in ("barriers", "steps"):
        lst = city.get(key)
        if not lst:
            continue
        out = []
        for it in lst:
            ps = it.get("pts") or []
            if len(ps) < 2:
                out.append(it)
                continue
            run, cut = [], False
            pieces = []
            for a, b in zip(ps[:-1], ps[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                k = max(1, int(L))
                for m in range(k + 1):
                    tt = m / k
                    q = [a[i] + (b[i] - a[i]) * tt for i in range(len(a))]
                    if low_inside(q[0], q[1]):
                        cut = True
                        if len(run) >= 2:
                            pieces.append(run)
                        run = []
                    else:
                        if not run or (run[-1][0], run[-1][1]) != (q[0], q[1]):
                            run.append([round(v, 2) for v in q])
            if len(run) >= 2:
                pieces.append(run)
            if not cut:
                out.append(it)
                continue
            n += 1
            for pc in pieces:
                e = dict(it)
                e["pts"] = pc
                out.append(e)
        city[key] = out
    if n:
        print(f"  {d.name}: {n} Objekte aus dem Tunnel-Lichtraum entfernt/gekürzt")


def _terrain(d, tl):
    """terrain_col.f32: ganzes Tunnelband unter die Fahrbahnplatte abgesenkt (das sichtbare Gelände bleibt; der
    Gelände-Shader blendet es im Lichtraum der Röhre aus, scripts/tunnels.gd baut Deckel-Kollision über der Röhre)."""
    x0, z0 = tile_origin(d.name)
    col = np.frombuffer((d / "terrain_col.f32").read_bytes(), dtype="<f4").reshape(2001, 2001).copy()
    for t in tl:
        pts = t["pts"]
        hw = t["w"] * 0.5 + WALL
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            ax, az, bx, bz = a[0] - x0, a[1] - z0, b[0] - x0, b[1] - z0
            dx, dz = bx - ax, bz - az
            L = math.hypot(dx, dz) or 1.0
            nx, nz = -dz / L, dx / L
            ux, uz = dx / L * 0.6, dz / L * 0.6           # leicht überlappend, aber nicht über das Portal hinaus
            ua = 0.0 if (i == 0 and t.get("p0")) else 1.0   # (sonst 1,2 m tiefer Schlitz vor der Öffnung)
            ub = 0.0 if (i == len(pts) - 2 and t.get("p1")) else 1.0
            quad = [(ax - ux * ua + nx * hw, az - uz * ua + nz * hw), (bx + ux * ub + nx * hw, bz + uz * ub + nz * hw),
                    (bx + ux * ub - nx * hw, bz + uz * ub - nz * hw), (ax - ux * ua - nx * hw, az - uz * ua - nz * hw)]
            c0 = int(max(min(q[0] for q in quad) - 1, 0)); c1 = int(min(max(q[0] for q in quad) + 2, 2001))
            r0 = int(max(min(q[1] for q in quad) - 1, 0)); r1 = int(min(max(q[1] for q in quad) + 2, 2001))
            if c1 <= c0 or r1 <= r0:
                continue
            im = Image.new("L", (c1 - c0, r1 - r0), 0)
            ImageDraw.Draw(im).polygon([(qx - c0, qz - r0) for qx, qz in quad], fill=255)
            m = np.asarray(im) > 0
            sub = col[r0:r1, c0:c1]
            sub[m] = np.minimum(sub[m], min(a[2], b[2]) - 1.2)
    (d / "terrain_col.f32").write_bytes(col.astype("<f4").tobytes())
    # Bodenbewuchs (cover.png, 2 m/px) im Tunnelband abschalten (wüchse sonst in den Portalbauwerken)
    cp = d / "cover.png"
    if cp.exists():
        cov = np.array(Image.open(cp).convert("RGB"))
        im = Image.new("L", (cov.shape[1], cov.shape[0]), 0)
        dr = ImageDraw.Draw(im)
        for t in tl:
            pts = t["pts"]
            hw = (t["w"] * 0.5 + WALL + 1.0) / 2.0
            line = [((p[0] - x0) / 2.0, (p[1] - z0) / 2.0) for p in pts]
            dr.line(line, fill=255, width=max(2, int(hw * 2 + 1)))
        m = np.asarray(im) > 0
        if m.any():
            cov[m] = 0
            Image.fromarray(cov, "RGB").save(cp, optimize=False, compress_level=3)


if __name__ == "__main__":
    build()
