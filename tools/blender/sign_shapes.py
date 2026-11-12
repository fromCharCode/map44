"""Gemeinsame Umrissdefinition der Verkehrszeichen-Platten.

Wird von make_traffic_signs.py (PIL-Atlas) UND von build_street_models.py (Blender) importiert,
damit Texturkante und Plattengeometrie exakt übereinstimmen.

Koordinaten in Metern, Ursprung = Mitte der (scharfkantigen) Umrissbox, x nach rechts, y nach oben.
UV: u = (x + w/2) / w, v = (y + h/2) / h  (Blender-Konvention, v=0 unten).
"""
import math

SQ3 = math.sqrt(3.0)

# w/h = Umrissbox der scharfkantigen Grundform, r = Eckradius (außen)
PLATES = {
    "plate_round":         {"w": 0.60, "h": 0.60, "kind": "circle"},
    "plate_triangle":      {"w": 0.90, "h": 0.90 * SQ3 / 2, "kind": "poly", "r": 0.036},
    "plate_triangle_down": {"w": 0.90, "h": 0.90 * SQ3 / 2, "kind": "poly", "r": 0.036},
    "plate_octagon":       {"w": 0.60, "h": 0.60, "kind": "poly", "r": 0.008},
    "plate_diamond":       {"w": 0.60 * math.sqrt(2), "h": 0.60 * math.sqrt(2), "kind": "poly", "r": 0.024},
    "plate_square":        {"w": 0.60, "h": 0.60, "kind": "poly", "r": 0.030},
    "plate_rect":          {"w": 0.60, "h": 0.90, "kind": "poly", "r": 0.030},
    "plate_rect_wide":     {"w": 0.90, "h": 0.60, "kind": "poly", "r": 0.030},
    "plate_oneway":        {"w": 0.90, "h": 0.30, "kind": "poly", "r": 0.024},
}


def sharp_polygon(name):
    """Scharfe Eckpunkte (gegen den Uhrzeigersinn, y nach oben)."""
    p = PLATES[name]
    w, h = p["w"], p["h"]
    if name == "plate_triangle":
        return [(-w / 2, -h / 2), (w / 2, -h / 2), (0.0, h / 2)]
    if name == "plate_triangle_down":
        return [(0.0, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    if name == "plate_octagon":
        R = (w / 2) / math.cos(math.radians(22.5))
        return [(R * math.cos(math.radians(22.5 + 45 * k)), R * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
    if name == "plate_diamond":
        return [(0.0, -h / 2), (w / 2, 0.0), (0.0, h / 2), (-w / 2, 0.0)]
    # Rechtecke
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def _line_isect(p1, d1, p2, d2):
    den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)


def inset_sharp(pts, d):
    """Konvexes Polygon (CCW) um d nach innen versetzen."""
    n = len(pts)
    lines = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L  # Innennormale bei CCW
        lines.append(((a[0] + nx * d, a[1] + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        p1, d1 = lines[i - 1]
        p2, d2 = lines[i]
        out.append(_line_isect(p1, d1, p2, d2))
    return out


def round_corners(pts, r, seg=10):
    """Ecken eines konvexen CCW-Polygons mit Radius r abrunden."""
    if r <= 1e-6:
        return list(pts)
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        a = (p0[0] - p1[0], p0[1] - p1[1])
        b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        a = (a[0] / la, a[1] / la)
        b = (b[0] / lb, b[1] / lb)
        cos_t = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
        theta = math.acos(cos_t)                 # Innenwinkel
        t = r / math.tan(theta / 2)              # Abstand Ecke -> Tangentenpunkt
        bis = (a[0] + b[0], a[1] + b[1])
        lbis = math.hypot(*bis)
        bis = (bis[0] / lbis, bis[1] / lbis)
        c = (p1[0] + bis[0] * r / math.sin(theta / 2), p1[1] + bis[1] * r / math.sin(theta / 2))
        ta = (p1[0] + a[0] * t, p1[1] + a[1] * t)
        tb = (p1[0] + b[0] * t, p1[1] + b[1] * t)
        a0 = math.atan2(ta[1] - c[1], ta[0] - c[0])
        a1 = math.atan2(tb[1] - c[1], tb[0] - c[0])
        da = a1 - a0
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        for k in range(seg + 1):
            ang = a0 + da * k / seg
            out.append((c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)))
    return out


def outline(name, inset=0.0, seg=10, circle_seg=48):
    """Umriss (CCW, Meter) der Platte, optional nach innen versetzt."""
    p = PLATES[name]
    if p["kind"] == "circle":
        R = p["w"] / 2 - inset
        return [(R * math.cos(2 * math.pi * k / circle_seg), R * math.sin(2 * math.pi * k / circle_seg))
                for k in range(circle_seg)]
    sharp = sharp_polygon(name)
    r = p["r"]
    if inset > 0:
        sharp = inset_sharp(sharp, inset)
        r = max(r - inset, 0.0)
    return round_corners(sharp, r, seg)


def uv_of(name, x, y):
    p = PLATES[name]
    return ((x + p["w"] / 2) / p["w"], (y + p["h"] / 2) / p["h"])
