"""Straßenleben aus OSM: Läden (mit echten Namen), Stadtmöbel, Haltestellen, Verkehrszeichen, Straßennamen-
schilder, Café-Außenplätze und Müll. Wird von build_city.main() aufgerufen; Ausgabe city["life"].

Alle Koordinaten lokal (Spiel: x = Ost, z = −Nord), nur Objekte innerhalb der Kachel.
Ausgabeformat (kompakt, Listen):
  shops:     [b_id, x0, z0, x1, z1, nx, nz, y, name, cat, awning(0/1)]   Ladenfront auf der Wand (x0,z0)-(x1,z1)
  furniture: [model, x, z, yaw, y, var]                                  yaw: Vorderseite (-Z des Modells) zur Straße
  signs:     [plate, atlas, x, z, yaw, y]                                Verkehrszeichen am Pfosten
  names:     [x, z, yaw, y, name1, name2]                                Straßennamensschild (Pfosten mit 1-2 Tafeln)
  litter:    [cell, x, z, yaw, scale, y]                                 Boden-Decal
"""
import math
from collections import defaultdict

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

# Kategorie -> (Farbschema-Index, Markise?) – Farben setzt der Godot-Code
SHOP_CATS = {
    "food": ({"bakery", "butcher", "pastry", "confectionery", "greengrocer", "deli", "cheese", "coffee", "tea",
              "chocolate", "beverages", "wine", "alcohol", "seafood"}, True),
    "super": ({"supermarket", "convenience", "kiosk", "organic", "health_food", "variety_store", "department_store",
               "mall", "chemist", "drugstore"}, False),
    "fashion": ({"clothes", "shoes", "fashion", "boutique", "jewelry", "bag", "fabric", "tailor", "watches",
                 "fashion_accessories", "second_hand", "leather"}, False),
    "service": ({"hairdresser", "beauty", "optician", "laundry", "dry_cleaning", "travel_agency", "copyshop", "tattoo",
                 "mobile_phone", "electronics", "computer", "funeral_directors", "massage", "pawnbroker"}, False),
    "home": ({"furniture", "hardware", "doityourself", "interior_decoration", "kitchen", "florist", "garden_centre",
              "houseware", "bed", "lighting", "paint", "antiques", "art", "frame", "gift", "books", "stationery",
              "toys", "music", "musical_instrument", "photo", "bicycle", "sports", "outdoor", "pet", "car_parts",
              "newsagent", "lottery", "ticket", "games", "video_games", "erotic", "e-cigarette", "tobacco"}, False),
}
GASTRO = {"cafe": True, "restaurant": True, "fast_food": False, "bar": True, "pub": True, "ice_cream": True,
          "biergarten": True}
OTHER_AMENITY = {"pharmacy": "health", "bank": "bank", "post_office": "service", "bureau_de_change": "bank",
                 "doctors": "health", "dentist": "health", "clinic": "health", "veterinary": "health",
                 "cinema": "culture", "theatre": "culture", "library": "culture", "arts_centre": "culture",
                 "nightclub": "gastro", "car_rental": "service", "driving_school": "service"}

FURNITURE_AMENITY = {"bench": "bench", "waste_basket": "bin_public", "bicycle_parking": "bike_rack",
                     "post_box": "post_box", "vending_machine": None, "recycling": "recycling",
                     "telephone": None, "drinking_water": None, "parking_entrance": None}
FURNITURE_TAG = {("emergency", "fire_hydrant"): "hydrant", ("man_made", "street_cabinet"): "street_cabinet",
                 ("advertising", "column"): "litfass", ("advertising", "billboard"): "billboard",
                 ("advertising", "poster_box"): "billboard", ("vending", "parking_tickets"): "parking_meter",
                 ("barrier", "bollard"): "bollard"}

# OSM traffic_sign=DE:xxx -> (Platte, Atlasname)
DE_SIGNS = {"205": ("plate_triangle_down", "205"), "206": ("plate_octagon", "206"), "306": ("plate_diamond", "306"),
            "307": ("plate_diamond", "307"), "301": ("plate_triangle", "301"), "274": ("plate_round", "274_30"),
            "274.1": ("plate_rect", "274.1"), "274.2": ("plate_rect", "274.2"), "220": ("plate_rect", "220"),
            "267": ("plate_round", "267"), "250": ("plate_round", "250"), "242.1": ("plate_rect", "242.1"),
            "242.2": ("plate_rect", "242.2"), "350": ("plate_square", "350"), "314": ("plate_square", "314"),
            "283": ("plate_round", "283"), "286": ("plate_round", "286"), "237": ("plate_round", "237"),
            "240": ("plate_round", "240"), "357": ("plate_square", "357"), "325.1": ("plate_rect", "325.1"),
            "101": ("plate_triangle", "101"), "123": ("plate_triangle", "123"), "138": ("plate_triangle", "138"),
            "131": ("plate_triangle", "131")}
RANK = {"motorway": 9, "trunk": 8, "primary": 7, "secondary": 6, "tertiary": 5, "motorway_link": 6, "trunk_link": 6,
        "primary_link": 5, "secondary_link": 5, "tertiary_link": 4, "unclassified": 3, "residential": 2,
        "living_street": 1, "service": 0, "road": 2, "busway": 3}


def _h(*vals) -> float:
    """Deterministischer Hash 0..1."""
    x = 0
    for v in vals:
        x = (x * 1000003) ^ (int(v * 1000) & 0xFFFFFFFF)
        x &= 0xFFFFFFFFFFFF
    x ^= x >> 17
    x = (x * 0x9E3779B1) & 0xFFFFFFFF
    x ^= x >> 15
    return (x & 0xFFFFFF) / float(0xFFFFFF)


def _yaw_facing(dx, dz):
    """Yaw (Godot, um +Y), sodass die Modell-Vorderseite (-Z) in Richtung (dx, dz) zeigt."""
    return math.atan2(-dx, -dz)


class StreetLife:
    def __init__(self, pois, buildings, roads, graph, crossings, to_local, ground_local, tile_box_local, log=print):
        self.log = log
        self.to_local = to_local
        self.gy = ground_local
        self.box = tile_box_local
        self.x0, self.z0, self.x1, self.z1 = tile_box_local.bounds
        self.out = {"shops": [], "furniture": [], "signs": [], "names": [], "litter": []}
        # Straßen (lokal)
        self.roads = []
        for r in roads:
            pts = r["pts"]
            if len(pts) < 2:
                continue
            ln = LineString([(p[0], p[1]) for p in pts])
            if ln.length < 0.5:
                continue
            self.roads.append((ln, r))
        self.road_tree = STRtree([ln for ln, _ in self.roads]) if self.roads else None
        # Gebäude (lokal, nur am Boden stehende)
        self.bld = []
        for b in buildings:
            if b.get("elev") or b.get("stacked") or not b.get("rings") or len(b["rings"][0]) < 3:
                continue
            try:
                pg = Polygon(b["rings"][0])
                if not pg.is_valid:
                    pg = pg.buffer(0)
                if pg.is_empty or pg.geom_type != "Polygon" or pg.area < 12:
                    continue
            except Exception:
                continue
            self.bld.append((pg, b))
        self.bld_tree = STRtree([pg for pg, _ in self.bld]) if self.bld else None
        self.pois = pois
        self.graph = graph
        self.crossings = crossings
        self.used_edges = defaultdict(list)     # (b_id, edge) -> [(t0, t1)]

    # -------------------------------------------------------------------------
    def inside(self, x, z):
        return self.x0 <= x < self.x1 and self.z0 <= z < self.z1

    def nearest_road(self, x, z, maxd=40.0, drive_only=False):
        if self.road_tree is None:
            return None
        p = Point(x, z)
        best = None
        for i in self.road_tree.query(p.buffer(maxd)):
            ln, r = self.roads[int(i)]
            if drive_only and r["cls"] in ("footway", "path", "cycleway", "steps", "pedestrian"):
                continue
            d = ln.distance(p)
            if d < maxd and (best is None or d < best[0]):
                best = (d, ln, r)
        return best

    def road_dir_at(self, ln, x, z):
        s = ln.project(Point(x, z))
        a = ln.interpolate(max(s - 1.0, 0.0))
        b = ln.interpolate(min(s + 1.0, ln.length))
        dx, dz = b.x - a.x, b.y - a.y
        L = math.hypot(dx, dz) or 1.0
        q = ln.interpolate(s)
        return dx / L, dz / L, q.x, q.y

    def facing_road_yaw(self, x, z):
        """Yaw so, dass das Objekt zur nächsten Straße schaut (Vorderseite = −Z)."""
        nr = self.nearest_road(x, z, 30.0)
        if nr is None:
            return _h(x, z) * math.tau
        _, ln, _r = nr
        _dx, _dz, qx, qz = self.road_dir_at(ln, x, z)
        vx, vz = qx - x, qz - z
        if math.hypot(vx, vz) < 0.2:
            return math.atan2(-_dx, -_dz)
        return _yaw_facing(vx, vz)

    # --- Läden -----------------------------------------------------------------
    def _shop_cat(self, t):
        if t.get("shop") == "vacant" or ("disused:shop" in t and "shop" not in t):
            return "vacant", False
        if "shop" in t:
            s = t["shop"]
            for cat, (vals, aw) in SHOP_CATS.items():
                if s in vals:
                    return cat, aw
            return "other", False
        a = t.get("amenity")
        if a in GASTRO:
            return "gastro", GASTRO[a]
        if a in OTHER_AMENITY:
            return OTHER_AMENITY[a], False
        if t.get("shop") == "vacant" or t.get("disused:shop"):
            return "vacant", False
        if "craft" in t:
            return "service", False
        if t.get("tourism") in ("hotel", "hostel", "guest_house"):
            return "hotel", False
        return None, False

    def _street_edge(self, pg, x, z):
        """Gebäudekante, die zur Straße zeigt und dem Punkt am nächsten liegt: (i, a, b, n, t)."""
        ring = list(pg.exterior.coords)[:-1]
        if pg.exterior.is_ccw:
            ring = ring[::-1]                # im Uhrzeigersinn -> Normale (dz, -dx) zeigt nach außen
        best = None
        P = np.array([x, z])
        for i in range(len(ring)):
            a = np.array(ring[i])
            b = np.array(ring[(i + 1) % len(ring)])
            d = b - a
            L = float(np.hypot(*d))
            if L < 3.0:
                continue
            t = float(np.clip(np.dot(P - a, d) / (L * L), 0.0, 1.0))
            q = a + d * t
            dist = float(np.hypot(*(P - q)))
            n = np.array([d[1], -d[0]]) / L
            mid = (a + b) / 2
            # Straße vor der Kante?
            nr = self.nearest_road(*(mid + n * 4.0), maxd=18.0)
            road_pen = 0.0 if nr is not None else 25.0
            # Außenseite prüfen (Punkt 1 m vor der Kante liegt außerhalb)
            if pg.contains(Point(*(mid + n * 0.8))):
                n = -n
            score = dist + road_pen
            if best is None or score < best[0]:
                best = (score, i, a, b, n, t, L)
        return best

    def shops(self, osm_buildings_tags):
        if self.bld_tree is None:
            return
        cands = []
        for el in self.pois:
            t = el.get("tags", {})
            cat, aw = self._shop_cat(t)
            if not cat:
                continue
            x, z = self.to_local(*el["_utm"])
            if not self.inside(x, z):
                continue
            cands.append((x, z, t, cat, aw))
        # Gebäude-Polygone mit Laden-Tags (shop=* am Gebäude)
        for (x, z, t) in osm_buildings_tags:
            cat, aw = self._shop_cat(t)
            if cat and self.inside(x, z):
                cands.append((x, z, t, cat, aw))
        n_ok = 0
        for x, z, t, cat, aw in cands:
            p = Point(x, z)
            hits = [(self.bld[int(i)][0].distance(p), int(i)) for i in self.bld_tree.query(p.buffer(25.0))]
            if not hits:
                continue
            _d, bi = min(hits)
            pg, b = self.bld[bi]
            se = self._street_edge(pg, x, z)
            if se is None:
                continue
            _s, ei, a, bb, n, tc, L = se
            width = {"super": 9.0, "gastro": 6.0, "fashion": 6.0, "home": 6.0, "bank": 5.0, "culture": 8.0,
                     "hotel": 5.0}.get(cat, 4.5)
            width = min(width, L - 1.0)
            if width < 2.0:
                continue
            half = width / (2 * L)
            t0, t1 = max(tc - half, 0.5 / L), min(tc + half, 1.0 - 0.5 / L)
            # Überschneidung mit vorhandenen Läden derselben Kante vermeiden
            key = (b["id"], ei)
            for (u0, u1) in self.used_edges[key]:
                if t0 < u1 and t1 > u0:
                    if tc >= (u0 + u1) / 2:
                        t0 = u1 + 0.3 / L
                    else:
                        t1 = u0 - 0.3 / L
            if (t1 - t0) * L < 2.0:
                continue
            self.used_edges[key].append((t0, t1))
            q0 = a + (bb - a) * t0
            q1 = a + (bb - a) * t1
            mid = (q0 + q1) / 2
            y = self.gy(float(mid[0]), float(mid[1]))
            name = (t.get("name") or t.get("brand") or "").strip()[:40]
            self.out["shops"].append([b["id"], round(float(q0[0]), 2), round(float(q0[1]), 2), round(float(q1[0]), 2),
                                      round(float(q1[1]), 2), round(float(n[0]), 3), round(float(n[1]), 3), round(y, 2),
                                      name, cat, 1 if aw else 0])
            n_ok += 1
            # Außenplätze vor Gastronomie
            if cat == "gastro" and (t.get("outdoor_seating") == "yes" or (t.get("outdoor_seating") != "no" and aw)):
                self._seating(q0, q1, n, y)
        self.log(f"  Straßenleben: {n_ok} Läden/Gastronomie an Fassaden (von {len(cands)} POIs)")

    def _seating(self, q0, q1, n, y):
        # Platz bis zur Fahrbahn prüfen
        mid = (q0 + q1) / 2
        nr = self.nearest_road(*(mid + n * 2.5), maxd=30.0, drive_only=True)
        room = 8.0
        if nr is not None:
            d, ln, r = nr
            room = ln.distance(Point(*(mid))) - float(r["width"]) / 2 - 1.2
        if room < 2.6:
            return
        rows = 1 if room < 4.5 else 2
        L = float(np.hypot(*(q1 - q0)))
        tdir = (q1 - q0) / max(L, 1e-6)
        k = 0
        s = 1.0
        while s < L - 0.8:
            for rr in range(rows):
                p = q0 + tdir * s + n * (1.3 + rr * 1.7)
                if self.inside(p[0], p[1]):
                    yaw = _yaw_facing(-n[0], -n[1]) + (_h(p[0], p[1]) - 0.5) * 0.8
                    self.out["furniture"].append(["cafe_set", round(float(p[0]), 2), round(float(p[1]), 2), round(yaw, 3), round(y, 2), 0])
                    if (k + rr) % 2 == 0:
                        self.out["furniture"].append(["cafe_parasol", round(float(p[0]), 2), round(float(p[1]), 2), 0.0, round(y, 2), int(_h(L, s) * 6)])
            k += 1
            s += 1.9

    # --- Stadtmöbel ---------------------------------------------------------------
    def _stop_skip_ids(self):
        """OSM erfasst Haltestellen oft doppelt: Haltepunkt auf dem Gleis (railway=tram_stop) und Bahnsteig
        (public_transport=platform / highway=bus_stop). Gleis-Haltepunkte mit gleichnamigem Bahnsteig in der Nähe
        bekommen keinen eigenen Mast (sonst zwei Schilder nebeneinander, nachdem der Gleis-Mast an den Bordstein
        geschoben wurde)."""
        plats = defaultdict(list)
        for el in self.pois:
            t = el.get("tags", {})
            if t.get("highway") == "bus_stop" or (t.get("public_transport") == "platform" and el["type"] == "node"):
                plats[(t.get("name") or "").strip()].append(self.to_local(*el["_utm"]))
        skip = set()
        for el in self.pois:
            t = el.get("tags", {})
            if t.get("railway") != "tram_stop" or t.get("highway") == "bus_stop" or t.get("public_transport") == "platform":
                continue
            x, z = self.to_local(*el["_utm"])
            nm = (t.get("name") or "").strip()
            if any((x - a) ** 2 + (z - b) ** 2 < 45.0 ** 2 for a, b in plats.get(nm, [])):
                skip.add(el.get("id"))
        return skip

    def furniture(self):
        f = self.out["furniture"]
        have = defaultdict(list)
        stop_skip = self._stop_skip_ids()
        for el in self.pois:
            t = el.get("tags", {})
            x, z = self.to_local(*el["_utm"])
            if not self.inside(x, z):
                continue
            model = None
            a = t.get("amenity")
            if a in FURNITURE_AMENITY:
                model = FURNITURE_AMENITY[a]
                if a == "vending_machine":
                    model = "parking_meter" if t.get("vending") in ("parking_tickets", "public_transport_tickets") else None
                if a == "recycling":
                    if t.get("recycling_type") == "centre":
                        model = None
                    elif t.get("recycling:paper") == "yes" and t.get("recycling:glass_bottles") != "yes":
                        model = "paper_container"
                    else:
                        model = "glass_containers"
            for (k, v), m in FURNITURE_TAG.items():
                if t.get(k) == v:
                    model = m
            hw = t.get("highway")
            if hw == "bus_stop" or t.get("railway") == "tram_stop" or (t.get("public_transport") == "platform" and el["type"] == "node"):
                if el.get("id") in stop_skip:
                    continue
                if self._near(have["stop_pole"], x, z, 4.0):
                    continue                      # gleiche Haltestelle doppelt erfasst
                model = "stop_pole"
                if t.get("shelter") == "yes":
                    f.append(["bus_stop", round(x, 2), round(z, 2), round(self.facing_road_yaw(x, z), 3), round(self.gy(x, z), 2), 0])
            if not model:
                continue
            yaw = self.facing_road_yaw(x, z)
            row = [model, round(x, 2), round(z, 2), round(yaw, 3), round(self.gy(x, z), 2), int(_h(x, z) * 8)]
            if model == "stop_pole":
                row.append((t.get("name") or "")[:28])          # Haltestellenname auf der Fahne
            f.append(row)
            have[model].append((x, z))
        n_osm = len(f)
        # Ergänzungen, wo OSM Lücken hat
        self._fill_bins(have)
        self._fill_bikes(have)
        self.log(f"  Straßenleben: {n_osm} Stadtmöbel aus OSM, {len(f) - n_osm} ergänzt")

    def _near(self, lst, x, z, r):
        return any((x - a) ** 2 + (z - b) ** 2 < r * r for a, b in lst)

    def _sidewalk_point(self, ln, r, s, side):
        dx, dz, qx, qz = self.road_dir_at(ln, *ln.interpolate(s).coords[0])
        nx, nz = -dz, dx
        off = float(r["width"]) / 2 + 1.0
        return qx + nx * off * side, qz + nz * off * side, dx, dz, nx * side, nz * side

    def _fill_bins(self, have):
        bins = have["bin_public"]
        f = self.out["furniture"]
        for c in self.crossings:
            x, z = c[0], c[1]
            if not self.inside(x, z) or self._near(bins, x, z, 35.0):
                continue
            nr = self.nearest_road(x, z, 10.0, drive_only=True)
            if nr is None:
                continue
            d, ln, r = nr
            s = ln.project(Point(x, z))
            side = 1 if _h(x, z) > 0.5 else -1
            px, pz, dx, dz, nx, nz = self._sidewalk_point(ln, r, min(s + 3.0, ln.length), side)
            px += nx * 0.4
            pz += nz * 0.4
            if self.inside(px, pz) and not self._in_building(px, pz):
                f.append(["bin_public", round(px, 2), round(pz, 2), round(_yaw_facing(-nx, -nz), 3), round(self.gy(px, pz), 2), 0])
                bins.append((px, pz))
        # Haltestellen
        for (x, z) in have["stop_pole"]:
            if not self._near(bins, x, z, 12.0):
                px, pz = x + 1.4, z + 0.4
                if not self._in_building(px, pz):
                    f.append(["bin_public", round(px, 2), round(pz, 2), round(self.facing_road_yaw(px, pz), 3), round(self.gy(px, pz), 2), 0])
                    bins.append((px, pz))

    def _fill_bikes(self, have):
        f = self.out["furniture"]
        for (x, z) in have["bike_rack"]:
            n = int(_h(x, z, 3) * 4)
            for k in range(n):
                px = x - 1.2 + k * 0.8
                pz = z + 0.1
                f.append(["bicycle", round(px, 2), round(pz, 2), round(self.facing_road_yaw(x, z) + math.pi / 2, 3), round(self.gy(px, pz), 2), int(_h(px, pz) * 8)])

    def _in_building(self, x, z):
        if self.bld_tree is None:
            return False
        p = Point(x, z)
        return any(self.bld[int(i)][0].contains(p) for i in self.bld_tree.query(p))

    # --- Straßennamen und Verkehrszeichen ------------------------------------------
    def names_and_signs(self):
        nodes = {n["id"]: n for n in self.graph["nodes"]}
        inc = defaultdict(list)
        for e in self.graph["edges"]:
            pts = e["pts"]
            if len(pts) < 2:
                continue
            inc[e["a"]].append((e, pts, 1))
            inc[e["b"]].append((e, pts[::-1], -1))
        n_names = n_signs = 0
        for nid, lst in inc.items():
            if len(lst) < 3:
                continue
            nd = nodes[nid]
            jx, jz = nd["pos"][0], nd["pos"][2]
            if not self.inside(jx, jz):
                continue
            arms = []
            for e, pts, d in lst:
                # Richtung vom Knoten weg (Punkt in ~8 m)
                ln = LineString([(p[0], p[1]) for p in pts])
                q = ln.interpolate(min(8.0, ln.length))
                ang = math.atan2(q.y - jz, q.x - jx)
                arms.append((ang, e, ln, d))
            arms.sort(key=lambda a: a[0])
            rk = [RANK.get(a[1]["cls"], 2) for a in arms]
            max_rank = max(rk)
            # --- Straßennamensschild an der größten Ecke
            names = []
            for a in arms:
                nm = (a[1].get("name") or "").strip()
                if nm and nm not in names:
                    names.append(nm)
            if names:
                best = None
                for i in range(len(arms)):
                    a0 = arms[i][0]
                    a1 = arms[(i + 1) % len(arms)][0] + (math.tau if i == len(arms) - 1 else 0.0)
                    gap = a1 - a0
                    if best is None or gap > best[0]:
                        best = (gap, (a0 + a1) / 2, i)
                gap, bis, i = best
                w = max(float(arms[i][1]["width"]), float(arms[(i + 1) % len(arms)][1]["width"]))
                dist = w / 2 + 2.2
                px, pz = jx + math.cos(bis) * dist, jz + math.sin(bis) * dist
                if self.inside(px, pz) and not self._in_building(px, pz):
                    # Tafel parallel zur ersten Straße (Text vom Knoten aus lesbar)
                    ya = arms[i][0]
                    yaw = _yaw_facing(-math.cos(bis), -math.sin(bis))
                    self.out["names"].append([round(px, 2), round(pz, 2), round(yaw, 3), round(self.gy(px, pz), 2),
                                              names[0][:32], (names[1][:32] if len(names) > 1 else "")])
                    n_names += 1
            # --- Vorfahrt: Zufahrten untergeordneter Straßen bekommen "Vorfahrt gewähren"
            if nd.get("signal"):
                continue
            if max_rank >= 3 and len(set(rk)) > 1:
                for (ang, e, ln, d), r in zip(arms, rk):
                    if r >= max_rank or e["cls"] in ("service", "footway", "path"):
                        continue
                    ow = int(e.get("oneway", 0))
                    if ow != 0 and (ow == 1) == (d == 1):
                        continue                        # Einbahn vom Knoten weg: niemand fährt hier zu
                    s = min(7.0, ln.length * 0.6)
                    q = ln.interpolate(s)
                    dx, dz = q.x - jx, q.y - jz
                    L = math.hypot(dx, dz) or 1.0
                    ux, uz = dx / L, dz / L                # vom Knoten weg
                    # rechts der Fahrtrichtung (Fahrtrichtung = zum Knoten = -u): rechts = (-(-uz), -ux)?
                    rx, rz = uz, -ux
                    off = float(e["width"]) / 2 + 0.8
                    px, pz = q.x + rx * off, q.y + rz * off
                    if self.inside(px, pz) and not self._in_building(px, pz):
                        yaw = _yaw_facing(ux, uz)           # Schild schaut dem Verkehr entgegen
                        self._sign("205", px, pz, yaw)
                        n_signs += 1
        # Tempo/Einbahn/Fußgängerzone an Wegenden
        n_signs += self._road_end_signs()
        # OSM-Verkehrszeichen-Knoten
        for el in self.pois:
            t = el.get("tags", {})
            ts = t.get("traffic_sign", "")
            hw = t.get("highway")
            codes = []
            if ts.startswith("DE:"):
                for c in ts[3:].replace(";", ",").split(","):
                    c = c.split("[")[0].strip()
                    if c in DE_SIGNS:
                        codes.append(c)
            elif hw == "stop":
                codes = ["206"]
            elif hw == "give_way":
                codes = ["205"]
            if not codes:
                continue
            x, z = self.to_local(*el["_utm"])
            if not self.inside(x, z):
                continue
            nr = self.nearest_road(x, z, 12.0, drive_only=True)
            if nr is None:
                continue
            d, ln, r = nr
            dx, dz, qx, qz = self.road_dir_at(ln, x, z)
            if t.get("direction") == "backward":
                dx, dz = -dx, -dz
            off = float(r["width"]) / 2 + 0.8
            rx, rz = -dz, dx                    # rechts der Fahrtrichtung (Godot: x, z mit z nach Süden)
            px, pz = qx + rx * off, qz + rz * off
            if not self.inside(px, pz):
                continue
            self._sign(codes[0], px, pz, _yaw_facing(-dx, -dz))
            n_signs += 1
        self.log(f"  Straßenleben: {n_names} Straßennamensschilder, {n_signs} Verkehrszeichen")

    def _sign(self, code, x, z, yaw):
        plate, atlas = DE_SIGNS.get(code, ("plate_round", code))
        self.out["signs"].append([plate, atlas, round(x, 2), round(z, 2), round(yaw, 3), round(self.gy(x, z), 2)])

    # --- Einbahnstraßen: echte Einbahn vs. Richtungsfahrbahn ---------------------------
    DUAL_NAMED = 60.0      # max. Abstand gleichnamiger Gegenfahrbahn (St. Petersburger Str. ~45 m)
    DUAL_UNNAMED = 28.0

    @staticmethod
    def _dir_at(ln, s, sgn):
        L = ln.length
        a = ln.interpolate(max(s - 2.0, 0.0))
        b = ln.interpolate(min(s + 2.0, L))
        dx, dz = (b.x - a.x) * sgn, (b.y - a.y) * sgn
        n = math.hypot(dx, dz) or 1.0
        return dx / n, dz / n

    def oneway_kinds(self):
        """Je Straße (id(r)) die Art der Einbahnregel:
        'dual'   Richtungsfahrbahn einer Straße mit getrennten Fahrbahnen (OSM: zwei gegenläufige Einbahnwege)
                 -> keine Einbahnschilder (in echt stehen dort keine Zeichen 220/267),
        'rb'     Kreisverkehr, 'ramp' Rampe/Abbieger (*_link), 'service' Zufahrt/Parkplatzgasse -> keine Schilder,
        'real'   echte Einbahnstraße."""
        if hasattr(self, "_ow_kinds"):
            return self._ow_kinds
        kinds = {}
        ow = [i for i, (ln, r) in enumerate(self.roads) if int(r.get("oneway", 0)) != 0]
        tree = STRtree([self.roads[i][0] for i in ow]) if ow else None
        for i in ow:
            ln, r = self.roads[i]
            cls = r["cls"]
            if r.get("rb"):
                kinds[id(r)] = "rb"
                continue
            if cls.endswith("_link"):
                kinds[id(r)] = "ramp"
                continue
            if cls == "service":
                kinds[id(r)] = "service"
                continue
            sgn = 1 if int(r["oneway"]) > 0 else -1
            name = (r.get("name") or "").strip()
            dual = False
            L = ln.length
            for f in (0.15, 0.5, 0.85):
                s = L * f
                p = ln.interpolate(s)
                dx, dz = self._dir_at(ln, s, sgn)
                for j in tree.query(p.buffer(self.DUAL_NAMED)):
                    k = ow[int(j)]
                    if k == i:
                        continue
                    ln2, r2 = self.roads[k]
                    if r2["id"] == r["id"] or r2.get("rb"):
                        continue
                    name2 = (r2.get("name") or "").strip()
                    if name and name2:
                        if name != name2:
                            continue
                        lim = self.DUAL_NAMED
                    else:
                        if r2["cls"] != cls:
                            continue
                        lim = self.DUAL_UNNAMED
                    s2 = ln2.project(p)
                    q = ln2.interpolate(s2)
                    d = p.distance(q)
                    if d < 1.5 or d > lim:
                        continue
                    ex, ez = self._dir_at(ln2, s2, 1 if int(r2["oneway"]) > 0 else -1)
                    if dx * ex + dz * ez < -0.72:          # gegenläufig parallel
                        dual = True
                        break
                if dual:
                    break
            kinds[id(r)] = "dual" if dual else "real"
        # Ketten gleichnamiger, gleichgerichteter Einbahnstücke erben 'dual' (kurze Stücke an Knoten,
        # Gegenfahrbahn knapp außerhalb der Kachel …)
        ends = defaultdict(list)
        for i in ow:
            ln, r = self.roads[i]
            c = list(ln.coords)
            sgn = 1 if int(r["oneway"]) > 0 else -1
            p_in, p_out = (c[0], c[-1]) if sgn > 0 else (c[-1], c[0])
            ends[(round(p_in[0], 1), round(p_in[1], 1))].append((i, "in"))
            ends[(round(p_out[0], 1), round(p_out[1], 1))].append((i, "out"))
        par = {i: i for i in ow}

        def find(a):
            while par[a] != a:
                par[a] = par[par[a]]
                a = par[a]
            return a
        for lst in ends.values():
            ins = [i for i, t in lst if t == "in"]
            outs = [i for i, t in lst if t == "out"]
            for a in outs:
                for b in ins:
                    ra, rb = self.roads[a][1], self.roads[b][1]
                    if (ra.get("name") or "") == (rb.get("name") or "") and ra["cls"] == rb["cls"]:
                        par[find(a)] = find(b)
        dual_root = {find(i) for i in ow if kinds.get(id(self.roads[i][1])) == "dual"}
        for i in ow:
            if kinds.get(id(self.roads[i][1])) == "real" and find(i) in dual_root:
                kinds[id(self.roads[i][1])] = "dual"
        self._ow_kinds = kinds
        return kinds

    def _road_end_signs(self):
        n = 0
        kinds = self.oneway_kinds()
        ends = defaultdict(list)
        for ln, r in self.roads:
            c = list(ln.coords)
            for k, (pt, nb) in enumerate(((c[0], c[1]), (c[-1], c[-2]))):
                ends[(round(pt[0], 1), round(pt[1], 1))].append((r, pt, nb, k))
        for key, lst in ends.items():
            if len(lst) < 2:
                continue
            for r, pt, nb, k in lst:
                # Stücke desselben OSM-Wegs (Brücken-/Profilteilung) sind keine Einmündung
                others = [o for o in lst if o[0] is not r and o[0]["id"] != r["id"]]
                if not others:
                    continue
                if not self.inside(pt[0], pt[1]):
                    continue
                dx, dz = nb[0] - pt[0], nb[1] - pt[1]
                L = math.hypot(dx, dz) or 1.0
                ux, uz = dx / L, dz / L                    # in die Straße hinein
                rx, rz = -uz, ux                           # rechts der Einfahrtrichtung
                off = float(r["width"]) / 2 + 0.8
                px, pz = pt[0] + ux * 4.0 + rx * off, pt[1] + uz * 4.0 + rz * off
                if not self.inside(px, pz) or self._in_building(px, pz):
                    continue
                yaw = _yaw_facing(-ux, -uz)                # zum einfahrenden Verkehr
                code = None
                sp = r.get("speed", 50)
                other_sp = max(o[0].get("speed", 50) for o in others)
                if sp == 30 and other_sp > 30 and r["cls"] in ("residential", "unclassified", "living_street"):
                    code = "274.1"
                elif r["cls"] == "living_street" and all(o[0]["cls"] != "living_street" for o in others):
                    code = "325.1"
                elif int(r.get("oneway", 0)) != 0 and kinds.get(id(r)) == "real":
                    # Einfahrt in Fahrtrichtung: 220 am Anfang bzw. an Einmündungen; 267 nur am Ende der Einbahnstraße
                    forward_start = (k == 0) == (int(r["oneway"]) == 1)
                    nm = r.get("name") or ""

                    def _continues(o):
                        r2 = o[0]
                        if int(r2.get("oneway", 0)) == 0 or (r2.get("name") or "") != nm:
                            return False
                        return ((o[3] == 0) == (int(r2["oneway"]) == 1)) != forward_start
                    cont = [o for o in others if _continues(o)]
                    side = [o for o in others if o not in cont and o[0]["cls"] != "service"]
                    if side:
                        if forward_start:
                            code = "220"
                        elif not cont:
                            code = "267"
                if code and _h(px, pz, 7) < 0.85:
                    self._sign(code, px, pz, yaw)
                    n += 1
        return n

    # --- Fahrbahn freihalten -------------------------------------------------------------
    CLEARANCE = {"stop_pole": 0.5, "bus_stop": 1.7, "litfass": 0.9, "litfass_dresden": 0.9, "billboard": 0.9,
                 "glass_containers": 1.3, "paper_container": 1.0, "bench": 0.8, "bin_public": 0.5, "hydrant": 0.45,
                 "bike_rack": 0.9, "bicycle": 0.7, "parking_meter": 0.5, "post_box": 0.5, "street_cabinet": 0.6,
                 "cafe_set": 1.1, "cafe_parasol": 1.5, "cardboard": 0.4, "trash_bags": 0.4, "sandwich_board": 0.5}
    EXEMPT = {"bollard", "traffic_cone", "construction_fence"}
    REFACE = {"stop_pole", "bus_stop", "bench", "bin_public", "parking_meter", "post_box", "litfass", "litfass_dresden",
              "billboard", "street_cabinet", "hydrant", "glass_containers", "paper_container", "sandwich_board"}

    def keep_off_road(self, curb):
        """Alle Punktobjekte von der Fahrbahn an den Bordstein schieben (curb.Curb); unplatzierbare entfallen."""
        f_in = self.out["furniture"]
        f_out = []
        poles = []
        for row in f_in:
            model = row[0]
            if model in self.EXEMPT:
                f_out.append(row)
                continue
            q = curb.push(row[1], row[2], self.CLEARANCE.get(model, 0.6))
            if q is None:
                continue
            if (q[0], q[1]) != (row[1], row[2]):
                row = list(row)
                row[1], row[2] = round(q[0], 2), round(q[1], 2)
                row[4] = round(self.gy(q[0], q[1]), 2)
                if model in self.REFACE:
                    row[3] = round(self.facing_road_yaw(q[0], q[1]), 3)
            if model == "stop_pole":
                if any((row[1] - a) ** 2 + (row[2] - b) ** 2 < 3.5 ** 2 for a, b in poles):
                    continue
                poles.append((row[1], row[2]))
            if self.inside(row[1], row[2]) and not self._in_building(row[1], row[2]):
                f_out.append(row)
        self.out["furniture"] = f_out
        s_out = []
        for row in self.out["signs"]:
            q = curb.push(row[2], row[3], 0.45)
            if q is None:
                continue
            row = list(row)
            row[2], row[3] = round(q[0], 2), round(q[1], 2)
            row[5] = round(self.gy(q[0], q[1]), 2)
            if self.inside(row[2], row[3]) and not self._in_building(row[2], row[3]):
                s_out.append(row)
        self.out["signs"] = s_out
        n_out = []
        for row in self.out["names"]:
            q = curb.push(row[0], row[1], 0.6)
            if q is None:
                continue
            row = list(row)
            row[0], row[1] = round(q[0], 2), round(q[1], 2)
            row[3] = round(self.gy(q[0], q[1]), 2)
            if self.inside(row[0], row[1]) and not self._in_building(row[0], row[1]):
                n_out.append(row)
        self.out["names"] = n_out
        self.log(f"  Straßenleben: {curb.moved} Objekte von der Fahrbahn an den Bordstein verschoben, {curb.dropped} verworfen")

    # --- Baustellen -------------------------------------------------------------------
    def construction(self, landuse_polys, construction_ways):
        """Bauzäune um Baustellenflächen (landuse=construction), Leitkegel an gesperrten Straßen."""
        f = self.out["furniture"]
        n = 0
        for pg in landuse_polys:
            if pg.area < 60 or pg.area > 40000:
                continue
            ring = pg.exterior
            L = ring.length
            s = 0.0
            while s < L:
                a = ring.interpolate(s)
                b = ring.interpolate(min(s + 3.5, L))
                if self.inside(a.x, a.y) and not self._in_building(a.x, a.y):
                    mx, mz = (a.x + b.x) / 2, (a.y + b.y) / 2
                    yaw = math.atan2(-(b.y - a.y), (b.x - a.x))      # Zaun entlang X des Modells
                    f.append(["construction_fence", round(mx, 2), round(mz, 2), round(yaw, 3), round(self.gy(mx, mz), 2), 0])
                    n += 1
                s += 3.5
        for ln in construction_ways:
            for s in np.arange(1.0, ln.length, 2.5):
                q = ln.interpolate(s)
                if self.inside(q.x, q.y):
                    f.append(["traffic_cone", round(q.x, 2), round(q.y, 2), 0.0, round(self.gy(q.x, q.y), 2), 0])
                    n += 1
        self.log(f"  Straßenleben: {n} Bauzaun-Elemente/Leitkegel")

    # --- Müll ------------------------------------------------------------------------
    def litter(self, n_cells=16):
        li = self.out["litter"]
        shops = self.out["shops"]
        # Dichte: an Ladenfronten, Haltestellen, Bänken, Mülleimern mehr; sonst entlang von Bordsteinen
        spots = []
        for s in shops:
            mx, mz = (s[1] + s[3]) / 2 + s[5] * 2.0, (s[2] + s[4]) / 2 + s[6] * 2.0
            spots.append((mx, mz, 3.0, 3))
        for fu in self.out["furniture"]:
            if fu[0] in ("bin_public", "bench", "stop_pole", "bus_stop", "glass_containers", "paper_container"):
                spots.append((fu[1], fu[2], 2.2, 4 if fu[0] in ("glass_containers", "paper_container") else 2))
        for (x, z, rad, n) in spots:
            for k in range(n):
                a = _h(x, z, k) * math.tau
                rr = rad * math.sqrt(_h(z, x, k + 9))
                px, pz = x + math.cos(a) * rr, z + math.sin(a) * rr
                if self.inside(px, pz) and not self._in_building(px, pz):
                    li.append([int(_h(px, pz, 1) * n_cells), round(px, 2), round(pz, 2), round(_h(pz, px) * math.tau, 2),
                               round(0.5 + _h(px, pz, 4) * 0.9, 2), round(self.gy(px, pz), 2)])
        # Rinnstein: alle ~9 m ein Fleck/Laub/Kippe am Fahrbahnrand
        for ln, r in self.roads:
            if r["cls"] not in RANK or r["cls"] in ("service",):
                continue
            L = ln.length
            s = _h(L, 1) * 9.0
            while s < L:
                if _h(s, L) < 0.55:
                    side = 1 if _h(s, L, 2) > 0.5 else -1
                    px, pz, dx, dz, nx, nz = self._sidewalk_point(ln, r, s, side)
                    px -= nx * 1.15
                    pz -= nz * 1.15
                    if self.inside(px, pz):
                        li.append([int(_h(px, pz, 3) * n_cells), round(px, 2), round(pz, 2), round(_h(px, pz) * math.tau, 2),
                                   round(0.4 + _h(pz, px, 5) * 0.7, 2), round(self.gy(px, pz), 2)])
                s += 9.0
        # gelegentlich Müllsäcke/Kartons vor Wohnhäusern und Läden
        f = self.out["furniture"]
        for s in shops:
            if _h(s[1], s[2], 11) < 0.25:
                mx, mz = (s[1] + s[3]) / 2 + s[5] * 0.6, (s[2] + s[4]) / 2 + s[6] * 0.6
                f.append(["cardboard" if _h(mx, mz) < 0.6 else "trash_bags", round(mx, 2), round(mz, 2), round(_h(mz, mx) * 6.28, 2), s[7], 0])
        self.log(f"  Straßenleben: {len(li)} Müll-/Schmutz-Decals")
