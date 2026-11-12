"""Haltestellen wie in echt: Masten an den echten Steigen, Bahnsteige mit Bordhöhe/Breite, Wartehallen, Anzeiger.

Quellen:
- Landeshauptstadt Dresden, "Haltestellen Dresden – Barrierefreiheit" (OGC-API L1233, dl-de/by-2-0):
  data/raw/haltestellen/steige.json – jeder Haltesteig mit DHID, Name, Linien, Bordhöhe (cm), Breite (m),
  Leitstreifen (Rille/Rippe/Noppen/Kleinpflaster). Zwei Punkte mit gleicher DHID = Doppelhaltestelle.
- OpenStreetMap (ODbL): Bahnsteig-Linien (highway/railway/public_transport=platform) mit shelter, bench, bin,
  passenger_information_display/departures_board, width, tactile_paving.

Ausgabe city["stops"] (lokale Spielkoordinaten x, z; y = Bodenhöhe):
  masts:     [[x, z, yaw, y, name, lines, kind, dhid, rows, dfi]]  Vorderseite (−Z) zum Gleis/zur Fahrbahn; rows
             [[Linie, Ziel], …]; dfi = "dfi_small" (LED-Modul an der Fahne) oder ""
  shelters:  [[model, x, z, yaw, y, name]]                     Vorderseite (−Z) zum Gleis/zur Straße
  dfis:      [[model, x, z, yaw, y, name, lines]]              Abfahrtsanzeiger
  bins:      [[x, z, yaw, y]]
  platforms: [{"pts": [[x, z, y_top], …] (Umriss, gegen den Uhrzeigersinn), "tris": [i, …], "edge": [i0, i1, …]
               (Umrissindizes der Bahnsteigkante am Gleis), "h": Bordhöhe m, "kind": tram|bus, "tactile": Art}]
"""
import json
import math
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import triangulate
from shapely.strtree import STRtree

DATA = Path(__file__).resolve().parent.parent / "data" / "raw" / "haltestellen" / "steige.json"
EDGE_FROM_AXIS = 1.32        # Bahnsteigkante ab Gleisachse (Wagen 2,30–2,65 m, Spalt ~5 cm)
TRAM_LEN = 46.0              # Standardbahnsteig (45-m-Zug)
BUS_LEN = 20.0

_STEIGE = None
_ROUTES = None
ROUTE_FILES = [Path(__file__).resolve().parent.parent / "godot" / "data" / f for f in ("tram_routes.json", "bus_routes.json")]


def _routes():
    """Linienwege (godot/data/*_routes.json): ref -> [(LineString, Ziel)]"""
    global _ROUTES
    if _ROUTES is None:
        _ROUTES = defaultdict(list)
        for f in ROUTE_FILES:
            if not f.exists():
                continue
            for r in json.loads(f.read_text(encoding="utf-8")).get("routes", []):
                pts = r.get("pts", [])
                to = (r.get("to") or "").strip()
                if not to and "=>" in (r.get("name") or ""):
                    to = r["name"].split("=>")[-1].strip()
                for pre in ("Dresden, ", "Dresden "):
                    if to.startswith(pre) and len(to) > len(pre) + 3:
                        to = to[len(pre):]
                if len(pts) >= 2 and r.get("ref"):
                    _ROUTES[str(r["ref"])].append((LineString(pts), to))
    return _ROUTES


def line_rows(lines, x, z, fx, fz):
    """[[Linie, Ziel], …] für einen Steig: Ziel der Linienrichtung, die hier in Fahrtrichtung (fx, fz) vorbeifährt."""
    rows = []
    p = Point(x, z)
    for ref in [l for l in lines.split(",") if l]:
        best = None
        for ln, to in _routes().get(ref, []):
            d = ln.distance(p)
            if d > 45.0:
                continue
            s = ln.project(p)
            tx, tz = _tangent(ln, s)
            if tx * fx + tz * fz < 0.2:
                continue
            if s > ln.length - 25.0:
                continue                  # Endhaltestelle dieser Richtung
            if best is None or d < best[0]:
                best = (d, to)
        rows.append([ref, best[1] if best else ""])
    return rows


def _steige():
    global _STEIGE
    if _STEIGE is None:
        _STEIGE = json.loads(DATA.read_text(encoding="utf-8"))["steige"] if DATA.exists() else []
    return _STEIGE


def _tangent(ln, s):
    a = ln.interpolate(max(s - 1.5, 0.0))
    b = ln.interpolate(min(s + 1.5, ln.length))
    dx, dz = b.x - a.x, b.y - a.y
    L = math.hypot(dx, dz) or 1.0
    return dx / L, dz / L


def _yaw_facing(dx, dz):
    """Yaw (Godot, um +Y), so dass die Modell-Vorderseite (−Z) nach (dx, dz) zeigt."""
    return math.atan2(-dx, -dz)


def build_stops(ox, oy, inside, gy, rails, roads, osm_platforms, in_building, log=print):
    """ox/oy: UTM-Ursprung (x = E − ox, z = −(N − oy)); inside(x, z): in dieser Kachel; gy(x, z): Bodenhöhe;
    rails/roads: city-Listen; osm_platforms: [(tags, [(x, z), …])]; in_building(x, z) -> bool."""
    out = {"masts": [], "shelters": [], "dfis": [], "bins": [], "platforms": []}
    tram = [r for r in rails if r.get("kind") == "tram" and len(r["pts"]) >= 2]
    t_lines = [LineString([(p[0], p[1]) for p in r["pts"]]) for r in tram]
    t_tree = STRtree(t_lines) if t_lines else None
    drive = [(LineString([(p[0], p[1]) for p in r["pts"]]), r) for r in roads
             if len(r["pts"]) >= 2 and r["cls"] not in ("footway", "path", "cycleway", "steps", "pedestrian", "track",
                                                         "service", "platform", "bridleway")]
    d_tree = STRtree([ln for ln, _ in drive]) if drive else None
    pf = [(t, LineString(pts)) for t, pts in osm_platforms if len(pts) >= 2]
    pf_tree = STRtree([ln for _, ln in pf]) if pf else None

    # Steige der Kachel (mit kleinem Rand für Bahnsteige über die Kachelgrenze)
    by_id = defaultdict(list)
    for st in _steige():
        if st.get("x") is None or st.get("y") is None:
            continue
        x, z = st["x"] - ox, -(st["y"] - oy)
        if not inside(x, z):
            continue
        by_id[st["globale_id"]].append((x, z, st))

    used_pf = set()
    n_tram = n_bus = n_plat = 0
    for dhid, pts in by_id.items():
        st = pts[0][2]
        vm = st.get("verkehrsmittel") or ""
        is_tram = vm.startswith("Straßenbahn")
        lines = (st.get("verkehrende_linien") or "").replace(" ", "")
        name = (st.get("hst_name") or "")[:30]
        kerb = (st.get("bordhoehe") or (24.0 if is_tram else 16.0)) / 100.0
        kerb = min(max(kerb, 0.10), 0.30)
        width = st.get("breite") or 0.0
        tactile = st.get("ls_txt") or ""
        for (x, z, _s) in pts:
            p = Point(x, z)
            placed = False
            if is_tram and t_tree is not None:
                best = None
                for j in t_tree.query(p.buffer(14.0)):
                    d = t_lines[int(j)].distance(p)
                    if d < 14.0 and (best is None or d < best[0]):
                        best = (d, int(j))
                if best is not None:
                    ln = t_lines[best[1]]
                    s = ln.project(p)
                    q = ln.interpolate(s)
                    tx, tz = _tangent(ln, s)
                    lat = tx * (z - q.y) - tz * (x - q.x)          # > 0: Punkt rechts der Gleisrichtung
                    side = 1.0 if lat >= 0 else -1.0
                    # rechts aussteigen: Fahrtrichtung so, dass der Bahnsteig rechts liegt
                    fx, fz = (tx, tz) if side > 0 else (-tx, -tz)
                    nx, nz = -fz, fx                                 # rechts der Fahrtrichtung (x Ost, z Süd)
                    # Normale zur Bahnsteigseite: Vorzeichen so, dass sie zum Punkt zeigt
                    if (x - q.x) * nx + (z - q.y) * nz < 0:
                        nx, nz = -nx, -nz
                    w = width or 3.0
                    mx = q.x + nx * (EDGE_FROM_AXIS + min(0.9, w * 0.35))
                    mz = q.y + nz * (EDGE_FROM_AXIS + min(0.9, w * 0.35))
                    y_track = gy(q.x, q.y)
                    # Mast: Fahne quer zum Gleis, Vorderseite zur ankommenden Bahn
                    # Mast: Vorderseite (−Z) zum Gleis, Fahne hängt quer (Flächen längs zum Gleis lesbar)
                    out["masts"].append([round(mx, 2), round(mz, 2), round(_yaw_facing(-nx, -nz), 3),
                                         round(y_track + kerb, 2), name, lines, "tram", dhid,
                                         line_rows(lines, x, z, fx, fz), "", round(fx, 3), round(fz, 3)])
                    plat = _tram_platform(ln, s, fx, fz, nx, nz, w, kerb, gy, pf, pf_tree, used_pf, x, z)
                    if plat is not None:
                        out["platforms"].append(plat["mesh"])
                        n_plat += 1
                        _platform_furniture(out, plat, name, lines, in_building)
                    out["bins"].append([round(mx - fx * 1.2, 2), round(mz - fz * 1.2, 2), round(_yaw_facing(-nx, -nz), 3),
                                        round(y_track + kerb, 2)])
                    n_tram += 1
                    placed = True
            if placed or d_tree is None:
                continue
            # Bus: Mast an der Bordkante der nächsten Fahrbahn
            best = None
            for j in d_tree.query(p.buffer(25.0)):
                ln, r = drive[int(j)]
                d = ln.distance(p)
                if d < 25.0 and (best is None or d < best[0]):
                    best = (d, ln, r)
            if best is None:
                continue
            _d, ln, r = best
            s = ln.project(p)
            q = ln.interpolate(s)
            tx, tz = _tangent(ln, s)
            nx, nz = -tz, tx
            if (x - q.x) * nx + (z - q.y) * nz < 0:
                nx, nz = -nx, -nz
            off = float(r.get("width", 6.0)) * 0.5 + 0.55
            mx, mz = q.x + nx * off, q.y + nz * off
            if in_building(mx, mz):
                mx, mz = x, z
            # Fahrtrichtung: Haltestelle liegt rechts (rechts von f = (-fz, fx) = n)
            fx, fz = nz, -nx
            y0 = gy(mx, mz)
            tags = _osm_near(pf, pf_tree, mx, mz, 18.0)
            dfi = "dfi_small" if (tags.get("passenger_information_display") == "yes"
                                  or tags.get("departures_board") in ("realtime", "yes")) else ""
            out["masts"].append([round(mx, 2), round(mz, 2), round(_yaw_facing(-nx, -nz), 3), round(y0, 2), name,
                                 lines, "bus", dhid, line_rows(lines, x, z, fx, fz), dfi, round(fx, 3), round(fz, 3)])
            n_bus += 1
            # Wartehalle aus OSM (Bahnsteig- oder Haltestellenpunkt in der Nähe); Anzeiger als Modul am Mast
            if tags.get("shelter") == "yes":
                sx, sz = mx + nx * 1.6 - fx * 4.0, mz + nz * 1.6 - fz * 4.0
                if not in_building(sx, sz):
                    out["shelters"].append(["wall_shelter", round(sx, 2), round(sz, 2), round(_yaw_facing(-nx, -nz), 3),
                                            round(gy(sx, sz), 2), name])
            out["bins"].append([round(mx + fx * 1.5, 2), round(mz + fz * 1.5, 2), round(_yaw_facing(-nx, -nz), 3), round(y0, 2)])
    log(f"  Haltestellen: {n_tram} Tram-Masten, {n_bus} Bus-Masten, {n_plat} Bahnsteige, "
        f"{len(out['shelters'])} Wartehallen, {len(out['dfis'])} Anzeiger")
    return out


def _osm_near(pf, pf_tree, x, z, r):
    if pf_tree is None:
        return {}
    p = Point(x, z)
    best = None
    for j in pf_tree.query(p.buffer(r)):
        t, ln = pf[int(j)]
        d = ln.distance(p)
        if d < r and (best is None or d < best[0]):
            best = (d, t)
    return best[1] if best else {}


def _tram_platform(ln, s, fx, fz, nx, nz, width, kerb, gy, pf, pf_tree, used_pf, px, pz):
    """Bahnsteig entlang des Gleises: Länge aus OSM-Bahnsteig (falls vorhanden), sonst 46 m hinter dem Mast;
    Kante EDGE_FROM_AXIS neben der Gleisachse, Breite aus Steig-Daten/OSM. Nur mit OSM-Bahnsteig (sonst liegt der
    Halt oft im Gehweg/auf der Fahrbahn: Kap-/Zeitinsel – kein eigener Körper)."""
    if pf_tree is None:
        return None
    p = Point(px, pz)
    best = None
    for j in pf_tree.query(p.buffer(16.0)):
        t, pln = pf[int(j)]
        d = pln.distance(p)
        if d < 16.0 and (best is None or d < best[0]):
            best = (d, int(j), t, pln)
    if best is None:
        return None
    _d, idx, tags, pln = best
    if idx in used_pf:
        return None
    used_pf.add(idx)
    # Ausdehnung entlang des Gleises: Projektion der OSM-Linie
    ss = [ln.project(Point(c)) for c in pln.coords]
    s0, s1 = max(min(ss) - 0.5, 0.0), min(max(ss) + 0.5, ln.length)
    if s1 - s0 < 12.0:
        dirn = 1.0 if (fx, fz) == _tangent(ln, s) else -1.0
        s0, s1 = (s - TRAM_LEN, s + 2.0) if dirn > 0 else (s - 2.0, s + TRAM_LEN)
        s0, s1 = max(s0, 0.0), min(s1, ln.length)
    try:
        w = float(str(tags.get("width", "")).split()[0]) if tags.get("width") else width
    except ValueError:
        w = width
    w = min(max(w, 1.6), 6.0)
    # Umriss: Kante (am Gleis) und Rückseite, Stützpunkte alle ~2 m
    n = max(2, int((s1 - s0) / 2.0) + 1)
    edge, back = [], []
    for k in range(n):
        sk = s0 + (s1 - s0) * k / (n - 1)
        q = ln.interpolate(sk)
        tx, tz = _tangent(ln, sk)
        ux, uz = -tz, tx
        if ux * nx + uz * nz < 0:
            ux, uz = -ux, -uz
        yt = gy(q.x, q.y) + kerb
        edge.append((q.x + ux * EDGE_FROM_AXIS, q.y + uz * EDGE_FROM_AXIS, yt))
        back.append((q.x + ux * (EDGE_FROM_AXIS + w), q.y + uz * (EDGE_FROM_AXIS + w), yt))
    ring = edge + back[::-1]
    poly = Polygon([(a, b) for a, b, _ in ring])
    if not poly.is_valid or poly.area < 5.0:
        return None
    # Dreiecke: Streifen zwischen Kante und Rückseite (Umriss ist ein Band)
    tris = []
    for k in range(n - 1):
        a, b = k, k + 1
        c, d = 2 * n - 1 - (k + 1), 2 * n - 1 - k
        tris += [a, b, c, a, c, d]
    mesh = {"pts": [[round(x, 2), round(z, 2), round(y, 2)] for x, z, y in ring], "tris": tris,
            "edge": list(range(n)), "h": round(kerb, 3), "kind": "tram",
            "tactile": "rille" if tags.get("tactile_paving") == "yes" else ""}
    mid = ln.interpolate(0.5 * (s0 + s1))
    return {"mesh": mesh, "tags": tags, "s0": s0, "s1": s1, "ln": ln, "nx": nx, "nz": nz, "w": w, "kerb": kerb,
            "fx": fx, "fz": fz, "mid": (mid.x, mid.y), "gy": gy}


def _platform_furniture(out, plat, name, lines, in_building):
    tags, ln, nx, nz, w = plat["tags"], plat["ln"], plat["nx"], plat["nz"], plat["w"]
    fx, fz, gy, kerb = plat["fx"], plat["fz"], plat["gy"], plat["kerb"]
    L = plat["s1"] - plat["s0"]
    if tags.get("shelter") == "yes" and w >= 1.9:
        n_sh = 2 if L > 38.0 else 1
        for k in range(n_sh):
            sk = plat["s0"] + L * ((k + 1) / (n_sh + 1))
            q = ln.interpolate(sk)
            back = EDGE_FROM_AXIS + w - 0.85
            sx, sz = q.x + nx * back, q.y + nz * back
            model = "wall_shelter_long" if (w >= 3.0 and L > 30.0) else "wall_shelter"
            out["shelters"].append([model, round(sx, 2), round(sz, 2), round(_yaw_facing(-nx, -nz), 3),
                                    round(gy(q.x, q.y) + kerb, 2), name])
    if tags.get("passenger_information_display") == "yes" or tags.get("departures_board") in ("realtime", "yes"):
        sk = plat["s0"] + L * 0.5
        q = ln.interpolate(sk)
        off = EDGE_FROM_AXIS + 0.45
        dx_, dz_ = q.x + nx * off, q.y + nz * off
        out["dfis"].append(["dfi_large", round(dx_, 2), round(dz_, 2), round(_yaw_facing(-nx, -nz), 3),
                            round(gy(q.x, q.y) + kerb, 2), name, lines, round(fx, 3), round(fz, 3)])
