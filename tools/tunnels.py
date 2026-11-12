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
        n = max(2, int(L / STEP) + 1)
        pts, box = [], []
        for i in range(n):
            s = L * i / (n - 1)
            p = ln.interpolate(s)
            y = ya + (yb - ya) * s / L
            g = raw_at(p.x, p.y)
            cover = (g - y) if g is not None else 99.0
            pts.append([round(p.x, 2), round(p.y, 2), round(y, 3), round(g if g is not None else y + 99.0, 2)])
            box.append(1 if cover < COVER else 0)
        # einzelne Röhrenstücke zwischen Kästen (< 10 m) schließen, kurze Kästen in der Röhre zulassen
        for i in range(1, n - 1):
            if box[i] == 0 and box[i - 1] == 1 and i + 4 < n and any(box[i + 1:i + 5]):
                box[i] = 1
        name = tags.get("name") or tags.get("tunnel:name") or ""
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
