"""Befahrbare Straßentunnel (Nachbearbeitung, alle Kacheln auf einmal): city["tunnels"], Gelände/Kollision angepasst.

  python tools/tunnels.py [--dry]

OSM-Wege mit tunnel=yes (Kfz-Straßen, ≥ 25 m) werden zu Ketten verbunden (Portal bis Portal), ihr Längsprofil läuft
linear zwischen den Höhen der anschließenden Straßen (city.json roads) an beiden Portalen. Je Stützpunkt (2 m):
  * Überdeckung = sichtbares Gelände (terrain.f32) − Fahrbahn. Liegt sie unter 4,95 m (Röhrendecke 4,8 m), ist der Abschnitt
    ein Portal-/Trogbauwerk ("box"): im Spiel ein Betonkasten mit Decke. Sonst Röhre unter dem Hang.
  * Sichtbares Gelände bleibt unverändert (der Shader blendet es im Lichtraum der Röhre aus).
  * Kollisionsraster (terrain_col.f32) im ganzen Tunnelband unter die Fahrbahnplatte abgesenkt; über der Röhre legt das
    Spiel einen Kollisionsdeckel in Geländehöhe (scripts/tunnels.gd).
Ausgabe je Kachel: city["tunnels"] = [{"name", "w", "pts": [[x, z, y, gelände], …], "box": [0|1, …], "p0", "p1"}]
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
        out.append((ln, best[1]))
    return out


def build():
    dry = "--dry" in sys.argv
    per_tile = {}
    graph_add = {}         # Kachel -> [(Kante, Endknoten aus Nachbarkachel oder None)]
    n_ch = 0
    for ln, tags in chains():
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
                   "p0": i0 == 0 and tile_of(*pts[0][:2]) == tn, "p1": i1 == n - 1 and tile_of(*pts[-1][:2]) == tn}
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
    print(f"{n_ch} Tunnelketten, Kacheln: {len(per_tile)}, Verkehrskanten: {sum(len(v) for v in graph_add.values())}")
    if dry:
        return
    for d in sorted(TILES.iterdir()):
        cf = d / "city.json"
        if not cf.exists():
            continue
        tl = per_tile.get(d.name, [])
        city = json.loads(cf.read_text(encoding="utf-8"))
        had = bool(city.get("tunnels"))
        if not tl and not had:
            continue
        city["tunnels"] = tl
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
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")


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
            ux, uz = dx / L * 0.6, dz / L * 0.6           # leicht überlappend
            quad = [(ax - ux + nx * hw, az - uz + nz * hw), (bx + ux + nx * hw, bz + uz + nz * hw),
                    (bx + ux - nx * hw, bz + uz - nz * hw), (ax - ux - nx * hw, az - uz - nz * hw)]
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
