"""Echtes Parken aus OSM: Parkstreifen an Straßen (parking:* alt und neu) und Parkplatzflächen (amenity=parking).

Seitenangaben links/rechts beziehen sich auf die Wegrichtung. Lokale Spielkoordinaten: x = Ost, z = Süd;
rechts der Richtung (dx, dz) ist (-dz, dx).
"""
import math

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

# Breite, die ein Parkstreifen auf der Fahrbahn belegt (m)
LANE_W = {"parallel": 2.0, "diagonal": 4.6, "perpendicular": 5.0}
NO = {"no", "none", "separate", "no_parking", "no_stopping", "fire_lane", "no_standing", "sidepath"}
POS_ALIAS = {"yes": "lane", "lane": "lane", "on_street": "lane", "marked": "lane", "painted_area_only": "lane",
             "half_on_kerb": "half_on_kerb", "on_kerb": "on_kerb", "street_side": "street_side", "lay_by": "street_side",
             "layby": "street_side", "shoulder": "lane", "parallel": "lane", "diagonal": "lane", "perpendicular": "lane"}
LOT_TYPES = {None, "surface", "street_side", "lane", "layby", "lay_by", "yes", "on_kerb", "half_on_kerb"}


def _side_tags(tags, side):
    """(Position, Ausrichtung) oder None für eine Seite ('left'/'right'), alte und neue Schemata."""
    # neues Schema: parking:<side>=lane|street_side|on_kerb|half_on_kerb|shoulder|no|separate|yes
    v = tags.get(f"parking:{side}") or tags.get("parking:both")
    orient = tags.get(f"parking:{side}:orientation") or tags.get("parking:both:orientation")
    restr = tags.get(f"parking:{side}:restriction") or tags.get("parking:both:restriction")
    if v is None:
        # altes Schema: parking:lane:<side>=parallel|diagonal|perpendicular|no_parking|no_stopping|...
        ov = tags.get(f"parking:lane:{side}") or tags.get("parking:lane:both")
        if ov is None:
            return "untagged"
        if ov in NO:
            return None
        orient = ov if ov in LANE_W else (orient or "parallel")
        pos = tags.get(f"parking:lane:{side}:{ov}") or tags.get(f"parking:lane:both:{ov}") or "on_street"
        return (POS_ALIAS.get(pos, "lane"), orient if orient in LANE_W else "parallel")
    if v in NO or restr in ("no_parking", "no_stopping", "no_standing"):
        return None
    pos = POS_ALIAS.get(v)
    if pos is None:
        return None
    if orient not in LANE_W:
        orient = v if v in LANE_W else "parallel"
    return (pos, orient)


def park_sides(tags):
    """{'left': (pos, orient)|None|'untagged', 'right': ...} für einen OSM-Weg."""
    return {"left": _side_tags(tags, "left"), "right": _side_tags(tags, "right")}


def lane_widths(sides):
    """Fahrbahnbreite, die Parkstreifen links/rechts belegen."""
    out = []
    for side in ("left", "right"):
        s = sides[side]
        w = 0.0
        if isinstance(s, tuple):
            pos, orient = s
            if pos == "lane":
                w = LANE_W[orient]
            elif pos == "half_on_kerb":
                w = 1.0
        out.append(w)
    return out


def _hash(*vals):
    x = 0
    for v in vals:
        x = (x * 1000003) ^ (int(v * 1000) & 0xFFFFFFFF)
        x &= 0xFFFFFFFFFFFF
    x ^= x >> 17
    x = (x * 0x9E3779B1) & 0xFFFFFFFF
    x ^= x >> 15
    return (x & 0xFFFFFF) / float(0xFFFFFF)


class Parking:
    def __init__(self, curb, buildings, junctions, crossings, stops, signals, log=print):
        self.curb = curb
        self.log = log
        self.bld = []
        for b in buildings:
            if b.get("elev") or b.get("stacked") or not b.get("rings"):
                continue
            try:
                pg = Polygon(b["rings"][0])
                if not pg.is_valid:
                    pg = pg.buffer(0)
                if pg.geom_type == "Polygon" and pg.area > 4:
                    self.bld.append(pg)
            except Exception:
                pass
        self.bld_tree = STRtree(self.bld) if self.bld else None
        self.junc = np.array(junctions or [[1e9, 1e9]], dtype=float)
        self.cross = np.array(crossings or [[1e9, 1e9]], dtype=float)
        self.stops = np.array(stops or [[1e9, 1e9]], dtype=float)
        self.sig = np.array(signals or [[1e9, 1e9]], dtype=float)
        self.out = []
        self.cnt = {"lane": 0, "half_on_kerb": 0, "on_kerb": 0, "street_side": 0, "lot": 0}

    def _near(self, arr, x, z, r):
        return bool((np.hypot(arr[:, 0] - x, arr[:, 1] - z) < r).any())

    def _in_building(self, poly):
        if self.bld_tree is None:
            return False
        return any(self.bld[int(i)].intersects(poly) for i in self.bld_tree.query(poly))

    def _car_rect(self, x, z, yaw, L=4.5, W=1.8):
        """Grundriss eines Autos (Vorderseite -Z, gedreht um yaw)."""
        r = Polygon([(-W / 2, -L / 2), (W / 2, -L / 2), (W / 2, L / 2), (-W / 2, L / 2)])
        # Godot-Yaw um +Y: (x, z) -> (x cos + z sin, -x sin + z cos)
        c, s = math.cos(yaw), math.sin(yaw)
        pts = [(px * c + pz * s + x, -px * s + pz * c + z) for px, pz in r.exterior.coords[:-1]]
        return Polygon(pts)

    def _emit(self, x, z, yaw, kind):
        self.out.append([round(float(x), 2), round(float(z), 2), round(float(yaw), 3), int(_hash(x, z, 3) * 1000)])
        self.cnt[kind] += 1

    # --- Straßenrand ----------------------------------------------------------------------
    def street(self, roads, lots_near):
        """roads: Stadtstraßen mit "park" = {left, right}, "width", "pl", "pr" (lokal)."""
        for r in roads:
            sides = r.get("park")
            if not sides or r.get("bridge"):
                continue
            pts = [(p[0], p[1]) for p in r["pts"]]
            if len(pts) < 2:
                continue
            ln = LineString(pts)
            L = ln.length
            if L < 8.0:
                continue
            w = float(r["width"])
            for side, sgn in (("right", 1.0), ("left", -1.0)):
                s = sides.get(side)
                if s == "untagged" or s is None:
                    continue
                pos, orient = s
                lw = float(r["pr"] if side == "right" else r["pl"])
                if pos == "lane":
                    u = w / 2 - lw / 2
                elif pos == "half_on_kerb":
                    u = w / 2 - 0.1
                elif pos == "on_kerb":
                    u = w / 2 + 1.1
                else:   # street_side: Parkbucht neben der Fahrbahn – nur ohne eigene Parkfläche dort
                    u = w / 2 + 1.25
                if orient == "parallel":
                    pitch, rot = 5.9, 0.0
                elif orient == "diagonal":
                    pitch, rot = 3.3, math.radians(45)
                else:
                    pitch, rot = 2.6, math.radians(90)
                occ = 0.84 if pos in ("lane", "half_on_kerb") else 0.75
                sv = 6.0 + _hash(L, sgn) * pitch
                while sv < L - 6.0:
                    a = ln.interpolate(max(sv - 0.8, 0.0))
                    b = ln.interpolate(min(sv + 0.8, L))
                    p = ln.interpolate(sv)
                    tx, tz = b.x - a.x, b.y - a.y
                    tl = math.hypot(tx, tz) or 1.0
                    tx, tz = tx / tl, tz / tl
                    rx, rz = -tz, tx                     # rechts der Wegrichtung
                    x, z = p.x + rx * u * sgn, p.y + rz * u * sgn
                    sv += pitch
                    if _hash(x, z) > occ:
                        continue
                    if (self._near(self.junc, x, z, max(11.0, w * 0.5 + 6.0)) or self._near(self.cross, x, z, 6.0)
                            or self._near(self.stops, x, z, 16.0) or self._near(self.sig, x, z, 14.0)):
                        continue
                    if pos == "street_side" and lots_near(x, z):
                        continue
                    # Fahrtrichtung der Fahrspur auf dieser Seite (rechts: Wegrichtung, links: Gegenrichtung)
                    fx, fz = (tx, tz) if sgn > 0 else (-tx, -tz)
                    yaw = math.atan2(-fx, -fz)
                    if rot:
                        yaw += rot * (1.0 if _hash(z, x) > 0.15 else -1.0) if orient == "perpendicular" else rot
                    rect = self._car_rect(x, z, yaw)
                    if self._in_building(rect):
                        continue
                    # nicht in eine andere Fahrbahn ragen (Querstraßen, Gleise)
                    if self.curb.rect_overlap(rect, skip_id=r.get("id")) > 0.4:
                        continue
                    self._emit(x, z, yaw, pos)

    # --- Parkplatzflächen ---------------------------------------------------------------------
    def lots(self, polys):
        """polys: [(Polygon lokal, parking-Typ)]"""
        for pg, kind in polys:
            if pg.area < 20 or pg.area > 60000:
                continue
            rect = pg.minimum_rotated_rectangle
            cs = list(rect.exterior.coords)[:4]
            e0 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
            e1 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
            l0, l1 = math.hypot(*e0), math.hypot(*e1)
            if l0 >= l1:
                ux, uz, long_l, short_l = e0[0] / l0, e0[1] / l0, l0, l1
            else:
                ux, uz, long_l, short_l = e1[0] / l1, e1[1] / l1, l1, l0
            vx, vz = -uz, ux
            c = rect.centroid
            inner = pg.buffer(-0.3)
            if inner.is_empty:
                continue
            occ = 0.72
            # Reihen-Layout entlang der Längsachse
            if short_l < 3.6:
                rows = [(0.0, "par")]
            elif short_l < 7.5:
                rows = [(0.0, "perp")]
            else:
                rows = []
                period = 16.0              # Stellplatz 5 + Stellplatz 5 + Fahrgasse 6
                n = int((short_l + 6.0) // period) + 1
                start = -short_l / 2 + 2.6
                for k in range(n):
                    o = start + k * period
                    rows.append((o, "perp"))
                    rows.append((o + 5.0, "perp"))
            for off, mode in rows:
                pitch = 5.8 if mode == "par" else 2.55
                s = -long_l / 2 + pitch * 0.5
                while s < long_l / 2:
                    x = c.x + ux * s + vx * off
                    z = c.y + uz * s + vz * off
                    s += pitch
                    if _hash(x, z, 5) > occ:
                        continue
                    yaw = math.atan2(-ux, -uz) if mode == "par" else math.atan2(-vx, -vz) + (math.pi if _hash(x, z, 9) > 0.5 else 0.0)
                    car = self._car_rect(x, z, yaw)
                    if not inner.contains(car.centroid) or car.difference(pg).area > 0.8:
                        continue
                    if self._in_building(car) or self.curb.rect_overlap(car) > 0.3:
                        continue
                    self._emit(x, z, yaw, "lot")

    def report(self):
        self.log("  Parken: " + ", ".join(f"{k} {v}" for k, v in self.cnt.items()) + f" = {len(self.out)} Autos")
