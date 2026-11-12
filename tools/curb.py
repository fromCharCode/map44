"""Fahrbahn freihalten: verschiebt Punktobjekte (Schilder, Masten, Haltestellen, Laternen ...) von der Fahrbahn
an den nächsten Bordstein.

Fahrbahn = befahrbare Straßen (Achse ± Breite/2) und Straßenbahngleise (± 1,5 m). Ein Objekt, das näher als
`clearance` an der Fahrbahn steht, wird auf den nächsten Punkt mit genau `clearance` Abstand geschoben. Liegt auch
dieser in einer anderen Fahrbahn (z. B. mitten in einer großen Kreuzung), wird das Objekt verworfen (None).
"""
import math

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union
from shapely.strtree import STRtree

NON_DRIVE = {"footway", "path", "cycleway", "steps", "pedestrian", "track", "bridleway", "corridor", "platform"}


class Curb:
    def __init__(self, roads, rails=None):
        """roads: [{"pts": [[x, z, y], ...], "width": w, "cls": ...}] (lokale Koordinaten);
        rails: [{"pts": [[x, z, y], ...], "kind"/"cls": "tram"|...}]"""
        self.geoms = []
        self.lines = []          # (LineString, halbe Breite) für Richtungsabfragen
        self.ids = []            # OSM-Weg-ID je Straßenfläche (gleiche Reihenfolge wie lines)
        for r in roads:
            if r.get("cls") in NON_DRIVE:
                continue
            pts = [(p[0], p[1]) for p in r.get("pts", [])]
            if len(pts) < 2:
                continue
            ln = LineString(pts)
            if ln.length < 0.3:
                continue
            hw = max(float(r.get("width") or 5.0) * 0.5, 1.2)
            self.geoms.append(ln.buffer(hw, quad_segs=4))
            self.lines.append((ln, hw))
            self.ids.append(r.get("id"))
        for r in rails or []:
            kind = r.get("cls") or r.get("kind") or r.get("type") or ""
            if kind not in ("tram", "light_rail", "rail"):
                continue
            pts = [(p[0], p[1]) for p in r.get("pts", [])]
            if len(pts) < 2:
                continue
            ln = LineString(pts)
            if ln.length < 0.3:
                continue
            self.geoms.append(ln.buffer(1.5, quad_segs=4))
        self.tree = STRtree(self.geoms) if self.geoms else None
        self.moved = 0
        self.dropped = 0

    def distance(self, x, z):
        """Abstand zur nächsten Fahrbahnfläche (0 = auf der Fahrbahn)."""
        if self.tree is None:
            return 1e9
        p = Point(x, z)
        best = 1e9
        for i in self.tree.query(p.buffer(30.0)):
            best = min(best, self.geoms[int(i)].distance(p))
            if best == 0.0:
                break
        return best

    def on_road(self, x, z, clearance=0.0):
        return self.distance(x, z) < clearance + 1e-6 if clearance > 0 else self.distance(x, z) == 0.0

    def push(self, x, z, clearance=0.5, max_move=12.0):
        """Gibt (x, z) zurück – unverändert, verschoben oder None (kein Platz)."""
        if self.tree is None:
            return x, z
        p = Point(x, z)
        idx = list(self.tree.query(p.buffer(clearance + 0.01)))
        if not idx or all(self.geoms[int(i)].distance(p) >= clearance for i in idx):
            return x, z
        near = [self.geoms[int(i)] for i in self.tree.query(p.buffer(clearance + max_move + 25.0))]
        try:
            area = unary_union(near).buffer(clearance, quad_segs=4)
        except Exception:
            return None
        if not area.contains(p):
            return x, z
        q = nearest_points(area.boundary, p)[0]
        dx, dz = q.x - x, q.y - z
        L = math.hypot(dx, dz)
        if L > max_move:
            self.dropped += 1
            return None
        if L < 1e-6:
            dx, dz, L = 1.0, 0.0, 1.0
        nx, nz = q.x + dx / L * 0.05, q.y + dz / L * 0.05
        if area.contains(Point(nx, nz)):
            self.dropped += 1
            return None
        self.moved += 1
        return nx, nz

    def rect_overlap(self, poly, skip_id=None):
        """Fläche, mit der ein Polygon fremde Fahrbahnen überdeckt (eigene Straße skip_id ausgenommen)."""
        if self.tree is None:
            return 0.0
        a = 0.0
        for i in self.tree.query(poly):
            i = int(i)
            if skip_id is not None and i < len(self.ids) and self.ids[i] == skip_id:
                continue
            g = self.geoms[i]
            if g.intersects(poly):
                a += g.intersection(poly).area
        return a

    def nearest_dir(self, x, z):
        """Richtung (dx, dz) der nächsten Fahrbahnachse am Lotpunkt und der Lotpunkt selbst."""
        p = Point(x, z)
        if self.tree is None:
            return None
        cand = []
        for i in self.tree.query(p.buffer(30.0)):
            i = int(i)
            if i < len(self.lines):
                ln, hw = self.lines[i]
                cand.append((ln.distance(p), ln))
        if not cand:
            return None
        d, ln = min(cand, key=lambda c: c[0])
        s = ln.project(p)
        a = ln.interpolate(max(s - 1.0, 0.0))
        b = ln.interpolate(min(s + 1.0, ln.length))
        dx, dz = b.x - a.x, b.y - a.y
        L = math.hypot(dx, dz) or 1.0
        q = ln.interpolate(s)
        return dx / L, dz / L, q.x, q.y
