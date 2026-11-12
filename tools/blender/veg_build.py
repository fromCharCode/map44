"""Unterholz/Bodendecker für Wald (Dresdner Heide) und Parks (Großer Garten).

Aufruf:
  .venv/bin/python tools/blender/veg_textures.py            # Texturen (einmalig)
  flatpak run org.blender.Blender -b --python tools/blender/veg_build.py [-- name ...]

Ausgabe: godot/assets/models/vegetation/<name>.glb + MANIFEST.json

Konventionen je Modell:
  * EIN Mesh, höchstens 2 Materialien ("Leaves"/"Grass" + "Bark" bzw. "Rock").
  * Ursprung = Mitte am Boden, Modell steht auf y=0 (Wurzel-/Stammfuß ein paar cm im Boden).
  * Blätter/Gras: Alpha-Scissor (glTF MASK, cutoff 0.5).
  * COLOR_0  = Umgebungsverdeckung (grau, multipliziert die Albedo; Godot setzt dafür
               automatisch vertex_color_use_as_albedo).
  * TEXCOORD_1 (Godot UV2) = Wind: x = Auslenkungsgewicht 0 (Fuß) .. 1 (Spitze/außen),
               y = Phase 0..1 je Karte/Wedel.
  * Büsche/Farn: doppelseitiges Material, Normalen "aufgebläht" (Kugel um Buschmitte + oben),
    Karten zeigen nach außen. Gras/Heide: einseitig, Karten als Vorder-+Rückseite
    dupliziert, Normalen zeigen nach oben (gleichmäßig wie der Boden beleuchtet).
"""
from __future__ import annotations

import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Vector, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veg_facade_lib as L  # noqa: E402

OUT = os.path.join(L.MODELS, "vegetation")
os.makedirs(OUT, exist_ok=True)
UP = Vector((0, 0, 1))


# ---------------------------------------------------------------- Hilfen
def ao_val(lo, hi, t):
    t = max(0.0, min(1.0, t))
    v = lo + (hi - lo) * t
    return (v, v, v)


def rand_unit(rng):
    while True:
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.05 < v.length <= 1.0:
            return v.normalized()


def frame_from_normal(n, roll, up_hint=UP):
    n = n.normalized()
    u = up_hint - n * up_hint.dot(n)
    if u.length < 1e-4:
        u = Vector((0, 1, 0)) - n * n.y
    u.normalize()
    r = u.cross(n).normalized()
    # Rollen um n
    rot = Matrix.Rotation(roll, 3, n)
    return rot @ r, rot @ u, n


def foliage_card(mb, mat, c, n, roll, w, h, fold, normal_fn, ao_fn, wind_fn, phase,
                 uv_rect=(0.0, 0.0, 1.0, 1.0), base_at_center=False, up_hint=UP):
    """Gefaltete Blattkarte (2 Quads), doppelseitig.  Textur-v=0 = Zweigbasis."""
    r, u, nn = frame_from_normal(n, roll, up_hint)
    hw, hh = w * 0.5, h * 0.5
    cf, sf = math.cos(fold), math.sin(fold)
    off = -u * hh * 0.0 if not base_at_center else u * hh
    c = c + off
    P = {
        "LB": c - r * hw * cf - nn * hw * sf - u * hh,
        "B": c - u * hh,
        "RB": c + r * hw * cf - nn * hw * sf - u * hh,
        "LT": c - r * hw * cf - nn * hw * sf + u * hh,
        "T": c + u * hh,
        "RT": c + r * hw * cf - nn * hw * sf + u * hh,
    }
    u0, v0, u1, v1 = uv_rect
    um = (u0 + u1) * 0.5
    UV = {"LB": (u0, v0), "B": (um, v0), "RB": (u1, v0), "LT": (u0, v1), "T": (um, v1), "RT": (u1, v1)}
    for quad in (("LB", "B", "T", "LT"), ("B", "RB", "RT", "T")):
        pts = [P[k] for k in quad]
        mb.poly(pts, mat, uv=[UV[k] for k in quad], n=[normal_fn(p) for p in pts],
                col=[ao_fn(p) for p in pts], uv2=[(wind_fn(p), phase) for p in pts])


def blade_card(mb, mat, base, d_out, width, height, segs, lean, uv_rect, ao_lo, wind_h, phase,
               normal_up=0.85, sink=0.035, curve=1.6):
    """Senkrechte Grasskarte (segs Abschnitte), als Vorder- + Rückseite dupliziert."""
    side = UP.cross(d_out).normalized()
    u0, v0, u1, v1 = uv_rect
    rows = []
    for i in range(segs + 1):
        t = i / segs
        z = -sink + height * t
        off = d_out * lean * height * (t ** curve)
        cpt = base + off + UP * z
        rows.append((cpt - side * width * 0.5, cpt + side * width * 0.5, t))
    nrm = (UP * normal_up + d_out * (1 - normal_up)).normalized()
    for i in range(segs):
        a0, a1, t0 = rows[i]
        b0, b1, t1 = rows[i + 1]
        va = v0 + (v1 - v0) * t0
        vb = v0 + (v1 - v0) * t1
        pts = [a0, a1, b1, b0]
        uv = [(u0, va), (u1, va), (u1, vb), (u0, vb)]
        cols = [ao_val(ao_lo, 1.0, t0 ** 0.7)] * 2 + [ao_val(ao_lo, 1.0, t1 ** 0.7)] * 2
        w2 = [(min(1.0, (t0 * height / wind_h) ** 1.5), phase)] * 2 + [(min(1.0, (t1 * height / wind_h) ** 1.5), phase)] * 2
        mb.poly(pts, mat, uv=uv, n=[nrm] * 4, col=cols, uv2=w2)
        mb.poly(pts[::-1], mat, uv=uv[::-1], n=[nrm] * 4, col=cols[::-1], uv2=w2[::-1])


# =====================================================================
# Büsche
# =====================================================================
def crown_cards(mb, rng, C, R, n_cards, size, fold, z_min, top, vase=0.0, lump=0.2,
                tilt=(0.55, 1.15), ao_lo=0.38, rr_range=(0.5, 0.92), phase_fn=None):
    """Blattkarten "federartig" um eine unregelmäßige Ellipsoid-Hülle.

    Kartennormale um tilt (rad) gegen die Hüllnormale gekippt, Textur-oben (Blattspitzen)
    zeigt nach außen, Zweigbasis nach innen -> keine geraden Kartenkanten an der Silhouette.
    """
    off = Vector((rng.uniform(0, 90), rng.uniform(0, 90), rng.uniform(0, 90)))

    def hscale(z):
        t = max(0.0, min(1.0, (z - z_min) / max(1e-3, top - z_min)))
        return 1.0 - vase * (1.0 - t)

    def grad(p):
        d = p - C
        g = Vector((d.x / R.x ** 2, d.y / R.y ** 2, d.z / R.z ** 2))
        return g.normalized() if g.length > 1e-6 else UP

    def ell(p):
        d = p - C
        return Vector((d.x / R.x, d.y / R.y, d.z / R.z)).length

    def nfn(p):
        return (grad(p) * 0.75 + UP * 0.45).normalized()

    def aofn(p):
        hz = max(0.0, min(1.0, p.z / top))
        return ao_val(ao_lo, 1.0, 0.55 * min(1.0, ell(p)) ** 1.3 + 0.45 * hz)

    def wfn(p):
        return max(0.0, min(1.0, (p.z / top) ** 1.2 * (0.4 + 0.6 * min(1.0, ell(p)))))

    placed = tries = 0
    while placed < n_cards and tries < n_cards * 60:
        tries += 1
        d = rand_unit(rng)
        if d.z < -0.6:
            continue
        rr = rng.uniform(*rr_range) * (1.0 + lump * noise.noise(d * 1.7 + off))
        p = C + Vector((d.x * R.x, d.y * R.y, d.z * R.z)) * rr
        hs = hscale(p.z)
        p = Vector((C.x + (p.x - C.x) * hs, C.y + (p.y - C.y) * hs, p.z))
        if p.z < z_min:
            continue
        g = grad(p)
        t = g.cross(rand_unit(rng))
        if t.length < 1e-3:
            continue
        t.normalize()
        beta = rng.uniform(*tilt)
        n = g * math.cos(beta) + t * math.sin(beta)
        sz = size * rng.uniform(0.8, 1.15)
        ph = phase_fn(p) if phase_fn else rng.random()
        foliage_card(mb, "Leaves", p, n, rng.uniform(-0.35, 0.35), sz, sz, fold, nfn, aofn, wfn, ph,
                     up_hint=g)
        placed += 1
    return placed


def bush(name, seed, tex, center_z, rad_xy, rad_z, n_cards, size, fold, stems, z_min, leaf_rough=0.7,
         vase=0.0, lump=0.2, stem_h=0.6):
    rng = random.Random(seed)
    mb = L.MB()
    C = Vector((0, 0, center_z))
    R = Vector((rad_xy, rad_xy * rng.uniform(0.85, 1.0), rad_z))
    top = center_z + rad_z
    # Stämmchen (unten sichtbar), schräg nach außen
    for s in range(stems):
        a = 2 * math.pi * s / max(1, stems) + rng.uniform(-0.4, 0.4)
        lean = rng.uniform(0.25, 0.5)
        d = Vector((math.cos(a), math.sin(a), 0))
        ln = rng.uniform(0.8, 1.0) * stem_h
        path = [Vector((0, 0, -0.05)) + d * 0.05 * rng.random()]
        for k in (1, 2, 3):
            t = k / 3
            path.append(path[0] + d * lean * ln * t ** 1.2 + UP * ln * t)
        radii = [0.02, 0.016, 0.011, 0.007]
        cols = [ao_val(0.4, 1.0, p.z / top) for p in path]
        u2 = [(min(1.0, max(0.0, p.z / top)) * 0.5, 0.0) for p in path]
        mb.tube(path, radii, 5, "Bark", u_range=(0.0, 0.25), v_scale=1.6, cols=cols, uv2=u2,
                rot0=rng.uniform(0, 6.28))
    crown_cards(mb, rng, C, R, n_cards, size, fold, z_min, top, vase=vase, lump=lump)
    mats = {
        "Leaves": L.material("Leaves", col=tex, clip=0.5, double=True, rough=leaf_rough, vcol=True, specular=0.35),
        "Bark": L.material("Bark", col="veg_bark_smooth_col.png", nrm="veg_bark_smooth_nrm.png", rough=0.9, vcol=True),
    }
    return mb.build(name, mats)


def young_tree(name, seed):
    rng = random.Random(seed)
    mb = L.MB()
    H = 2.5
    trunk = []
    lean = Vector((rng.uniform(-0.06, 0.06), rng.uniform(-0.06, 0.06), 0))
    for k in range(7):
        t = k / 6
        trunk.append(Vector((0, 0, -0.05 + (H - 0.25) * t)) + lean * t * t + Vector(
            (0.015 * math.sin(t * 7 + 1), 0.012 * math.cos(t * 5), 0)))
    radii = [0.034 * (1 - 0.8 * (k / 6)) + 0.005 for k in range(7)]

    def aofn(p):
        return ao_val(0.45, 1.0, p.z / H)

    def wfn_trunk(p):
        return max(0.0, min(1.0, (p.z / H) ** 2))

    mb.tube(trunk, radii, 6, "Bark", u_range=(0.0, 0.5), v_scale=0.9, cols=[aofn(p) for p in trunk],
            uv2=[(wfn_trunk(p) * 0.6, 0.0) for p in trunk], rot0=0.3)
    # Äste
    tips = []
    nb = 6
    for b in range(nb):
        t = 0.38 + 0.52 * b / (nb - 1)
        i = t * 6
        i0 = int(i)
        f = i - i0
        p0 = trunk[i0].lerp(trunk[min(6, i0 + 1)], f)
        a = b * 2.4 + rng.uniform(-0.3, 0.3)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(0.35, 0.8))).normalized()
        ln = rng.uniform(0.35, 0.65) * (1.15 - t * 0.5)
        path = [p0, p0 + d * ln * 0.5 + UP * 0.03, p0 + d * ln + UP * rng.uniform(0.02, 0.1)]
        ph = rng.random()
        mb.tube(path, [0.012, 0.007, 0.003], 4, "Bark", u_range=(0.0, 0.25), v_scale=1.5,
                cols=[aofn(p) for p in path], uv2=[(wfn_trunk(p) * 0.6 + 0.4 * k / 2, ph) for k, p in enumerate(path)])
        tips.append((p0, path[-1], ph))
    C = Vector((0.02, 0.0, 1.72))
    R = Vector((0.62, 0.56, 0.80))
    crown_cards(mb, rng, C, R, 54, 0.5, math.radians(22), 0.95, H, vase=-0.15, lump=0.3,
                tilt=(0.5, 1.1), ao_lo=0.45, rr_range=(0.45, 0.95))
    mats = {
        "Leaves": L.material("Leaves", col="veg_leaf_beech.png", clip=0.5, double=True, rough=0.65, vcol=True, specular=0.4),
        "Bark": L.material("Bark", col="veg_bark_smooth_col.png", nrm="veg_bark_smooth_nrm.png", rough=0.85, vcol=True),
    }
    return mb.build(name, mats)


# =====================================================================
# Farn (Adlerfarn)
# =====================================================================
def fern(name, seed):
    rng = random.Random(seed)
    mb = L.MB()
    n_fronds = 6
    segs = 6
    for f in range(n_fronds):
        a = 2 * math.pi * f / n_fronds + rng.uniform(-0.35, 0.35)
        d = Vector((math.cos(a), math.sin(a), 0))
        side = UP.cross(d).normalized()
        Ltot = rng.uniform(0.85, 1.15)
        W = Ltot * rng.uniform(0.85, 0.95)
        base = d * rng.uniform(0.0, 0.07) - UP * 0.03
        stipe_f = 0.34
        el0 = math.radians(rng.uniform(70, 82))    # Stiel fast senkrecht
        el1 = math.radians(rng.uniform(35, 50))    # Spreitenanfang
        el2 = math.radians(rng.uniform(-25, -10))  # Spitze hängt
        pts = [base]
        ds = Ltot / segs
        cur = base.copy()
        tvals = [0.0]
        # dichtere Abtastung, dann 7 Punkte entnehmen
        fine = 60
        fp = [cur.copy()]
        for i in range(fine):
            t = (i + 0.5) / fine
            if t < stipe_f:
                el = el0
            else:
                u = (t - stipe_f) / (1 - stipe_f)
                el = el1 + (el2 - el1) * u ** 1.2
            step = d * math.cos(el) + UP * math.sin(el)
            cur = cur + step * (Ltot / fine)
            fp.append(cur.copy())
        sel = [fp[round(i * fine / segs)] for i in range(segs + 1)]
        twist = rng.uniform(-0.25, 0.25)
        ph = rng.random()
        rows = []
        for i, p in enumerate(sel):
            t = i / segs
            ww = W * 0.5
            vlift = math.radians(18) * min(1.0, t / stipe_f) if t > 0 else 0
            sd = (Matrix.Rotation(twist * t, 3, d) @ side)
            lift = UP * ww * math.sin(vlift)
            rows.append((p - sd * ww * math.cos(vlift) + lift, p, p + sd * ww * math.cos(vlift) + lift, t))
        H = max(p.z for p in fp) + 0.02

        def nfn_row(i):
            if i == 0:
                tng = rows[1][1] - rows[0][1]
            elif i == segs:
                tng = rows[-1][1] - rows[-2][1]
            else:
                tng = rows[i + 1][1] - rows[i - 1][1]
            sn = side.cross(tng.normalized()) * -1
            if sn.z < 0:
                sn = -sn
            return (sn * 0.5 + UP * 0.6).normalized()

        for i in range(segs):
            l0, c0, r0, t0 = rows[i]
            l1, c1, r1, t1 = rows[i + 1]
            n0, n1 = nfn_row(i), nfn_row(i + 1)
            for (A, B, C2, D, ua, ub) in ((l0, c0, c1, l1, 0.0, 0.5), (c0, r0, r1, c1, 0.5, 1.0)):
                pts = [A, B, C2, D]
                uv = [(ua, t0), (ub, t0), (ub, t1), (ua, t1)]
                nn = [n0, n0, n1, n1]
                # Oberseite = Vorderseite
                fnrm = L.face_normal(pts)
                if fnrm.z < 0 and t0 > 0.2:
                    pts, uv, nn = pts[::-1], uv[::-1], nn[::-1]
                cols = [ao_val(0.42, 1.0, 0.25 + 0.75 * (q.z / H)) for q in pts]
                w2 = [(min(1.0, (q - base).length / Ltot) ** 1.3, ph) for q in pts]
                mb.poly(pts, "Leaves", uv=uv, n=nn, col=cols, uv2=w2)
    mats = {"Leaves": L.material("Leaves", col="veg_fern.png", clip=0.5, double=True, rough=0.7, vcol=True, specular=0.35)}
    return mb.build(name, mats)


# =====================================================================
# Gräser / Zwergsträucher
# =====================================================================
def grass_tuft(name, seed):
    rng = random.Random(seed)
    mb = L.MB()
    n = 6
    for i in range(n):
        a = math.pi * i / n + rng.uniform(-0.2, 0.2)       # Kartenebenen über 180° verteilt
        d = Vector((math.cos(a), math.sin(a), 0))
        out = UP.cross(d)                                   # Kartennormale (Lehnrichtung)
        if rng.random() < 0.5:
            out = -out
        base = out * rng.uniform(0.02, 0.06)
        w = rng.uniform(0.34, 0.42)
        h = rng.uniform(0.36, 0.44)
        u0 = rng.choice([0.0, 0.25, 0.5])
        blade_card(mb, "Grass", base, out, w, h, 2, rng.uniform(0.15, 0.3), (u0, 0.0, u0 + 0.5, 1.0),
                   0.5, 0.4, rng.random())
    mats = {"Grass": L.material("Grass", col="veg_grass.png", clip=0.5, double=False, rough=0.8, vcol=True, specular=0.3)}
    return mb.build(name, mats)


def grass_tall(name, seed):
    rng = random.Random(seed)
    mb = L.MB()
    cards = [("g", 0.9)] * 5 + [("n", 0.95)] * 3
    for i, (kind, hmax) in enumerate(cards):
        a = math.pi * i / len(cards) * 2.0 + rng.uniform(-0.25, 0.25)
        d = Vector((math.cos(a), math.sin(a), 0))
        out = UP.cross(d)
        base = Vector((math.cos(a * 1.7), math.sin(a * 1.7), 0)) * rng.uniform(0.02, 0.12)
        h = hmax * rng.uniform(0.85, 1.0)
        w = h * 0.5
        uvr = (0.0, 0.0, 0.5, 1.0) if kind == "g" else (0.5, 0.0, 1.0, 1.0)
        blade_card(mb, "Grass", base, out, w, h, 3, rng.uniform(0.06, 0.16) if kind == "g" else 0.03,
                   uvr, 0.45, 0.9, rng.random(), curve=1.8)
    mats = {"Grass": L.material("Grass", col="veg_grass_tall.png", clip=0.5, double=False, rough=0.8, vcol=True, specular=0.3)}
    return mb.build(name, mats)


def heather(name, seed):
    rng = random.Random(seed)
    mb = L.MB()
    cards = ["b", "h", "b", "b", "h", "b", "b", "h", "b", "h"]
    for i, kind in enumerate(cards):
        a = rng.uniform(0, 2 * math.pi)
        rad = rng.uniform(0.0, 0.16) if i > 1 else 0.0
        pos = Vector((math.cos(a), math.sin(a), 0)) * rad
        b = rng.uniform(0, math.pi)
        d = Vector((math.cos(b), math.sin(b), 0))
        out = UP.cross(d)
        if out.dot(pos) < 0:
            out = -out
        w = rng.uniform(0.38, 0.52)
        h = w * 0.62 * rng.uniform(0.9, 1.12) * (1.0 - 0.8 * rad)
        uvr = (0.0, 0.5, 1.0, 1.0) if kind == "b" else (0.0, 0.0, 1.0, 0.5)
        blade_card(mb, "Leaves", pos, out, w, h, 1, rng.uniform(0.2, 0.45) * (0.5 + rad * 4), uvr, 0.5,
                   0.3, rng.random(), sink=0.04, curve=1.0)
    mats = {"Leaves": L.material("Leaves", col="veg_heather.png", clip=0.5, double=False, rough=0.75, vcol=True, specular=0.3)}
    return mb.build(name, mats)


# =====================================================================
# Totholz, Stumpf, Findling
# =====================================================================
def deadwood(name, seed):
    rng = random.Random(seed)
    mb = L.MB()
    n = 7
    path, radii = [], []
    for k in range(n):
        t = k / (n - 1)
        x = -1.0 + 2.0 * t
        y = 0.13 * math.sin(t * 2.6 + 0.3) - 0.06
        r = 0.105 * (1 - t) + 0.05 * t
        z = r - 0.03 + 0.03 * math.sin(t * 4.2 + 0.8)
        path.append(Vector((x, y, z)))
        radii.append(r * (1 + 0.06 * math.sin(k * 2.1)))
    aofn = lambda p: ao_val(0.45, 1.0, (p.z - 0.0) / 0.18)  # noqa: E731
    cols = [ao_val(0.75, 1.0, 1.0)] * n
    mb.tube(path, radii, 7, "Bark", cap0=True, cap1=True, u_range=(0.0, 0.75), v_scale=1.0 / 0.8,
            cols=cols, uv2=[(0.0, 0.0)] * n, cap_uv=None, rot0=0.4)
    # Deckel-UVs: Schnittfläche (Atlas oben rechts) bzw. Bruchholz
    caps = [f for f in mb.faces if len(f["idx"]) == 7]
    for f, (cu, cv) in zip(caps, ((0.875, 0.875), (0.875, 0.625))):
        cen = sum((mb.v[i] for i in f["idx"]), Vector()) / 7
        ax = (path[1] - path[0]).normalized()
        b1 = ax.cross(UP).normalized()
        b2 = ax.cross(b1).normalized()
        f["uv"] = [(cu + (mb.v[i] - cen).dot(b1) / radii[0] * 0.115, cv + (mb.v[i] - cen).dot(b2) / radii[0] * 0.115) for i in f["idx"]]
    # Aststummel
    # (Position, Länge, seitlich +-1, Steigung): eher waagerecht, einer schräg in den Boden
    for k, (t, ln, sd, dz) in enumerate(((0.28, 0.45, 1, 0.22), (0.52, 0.22, -1, 0.35),
                                         (0.74, 0.6, -1, -0.12), (0.86, 0.18, 1, 0.5))):
        i = t * (n - 1)
        p0 = path[int(i)].lerp(path[int(i) + 1], i - int(i))
        ax = (path[int(i) + 1] - path[int(i)]).normalized()
        side = ax.cross(UP).normalized() * sd
        d = (side + ax * 0.7 + UP * dz).normalized()
        p1 = p0 + d * ln * 0.55 + UP * 0.01
        p2 = p0 + d * ln
        if p2.z < -0.02:
            p2.z = -0.02
        br = [p0, p1, p2]
        rr = [0.042, 0.03, 0.02] if ln > 0.3 else [0.035, 0.03, 0.026]
        mb.tube(br, rr, 5, "Bark", cap1=True, u_range=(0.0, 0.4), v_scale=1.5,
                cols=[ao_val(0.6, 1.0, q.z / 0.25) for q in br], uv2=[(0.0, 0.0)] * 3,
                cap_uv=(0.875, 0.625, 0.08), rot0=k)
    # AO: Unterseite dunkel
    for f in mb.faces:
        f["col"] = [aofn(mb.v[i]) for i in f["idx"]]
    mats = {"Bark": L.material("Bark", col="veg_bark_dead_col.png", nrm="veg_bark_dead_nrm.png", rough=0.92, vcol=True)}
    return mb.build(name, mats)


def stump(name, seed):
    rng = random.Random(seed)
    mb = L.MB()
    sides = 15
    R0 = 0.29
    zs = [-0.12, -0.04, 0.03, 0.10, 0.19, 0.30, 0.40]
    phi = rng.uniform(0, 6.28)
    rings = []
    for zi, z in enumerate(zs):
        ring = []
        flare = max(0.0, 1.0 - (z + 0.12) / 0.36) ** 1.8
        for k in range(sides):
            a = 2 * math.pi * k / sides
            lobes = 0.5 + 0.5 * math.cos(5 * a + phi + 0.4 * math.sin(2 * a))
            r = R0 * (1 + 0.04 * math.sin(3 * a + 1)) * (1 + flare * (0.12 + 1.1 * lobes ** 3))
            zz = z
            if zi == len(zs) - 1:
                zz = z + 0.07 * math.cos(a - 0.6) + 0.015 * math.sin(4 * a)   # schräger Sägeschnitt
            ring.append(Vector((r * math.cos(a), r * math.sin(a), zz)))
        rings.append(ring)
    idx = [[mb.vert(p) for p in ring] + [None] for ring in rings]
    # Saum-Vertices für UV-Naht (u=0.75)
    for zi in range(len(rings)):
        idx[zi][sides] = mb.vert(rings[zi][0])
    cen = Vector((0, 0, sum(zs[:2]) / 2))
    vscale = 1.0 / 0.6
    H = max(p.z for p in rings[-1])
    for zi in range(len(rings) - 1):
        for k in range(sides):
            a, b = idx[zi][k], idx[zi][k + 1]
            c, d = idx[zi + 1][k + 1], idx[zi + 1][k]
            pa, pb = rings[zi][k], rings[zi][(k + 1) % sides]
            pc, pd = rings[zi + 1][(k + 1) % sides], rings[zi + 1][k]
            u0, u1 = 0.75 * k / sides, 0.75 * (k + 1) / sides
            uv = [(u0, pa.z * vscale), (u1, pb.z * vscale), (u1, pc.z * vscale), (u0, pd.z * vscale)]
            nn = []
            for p in (pa, pb, pc, pd):
                q = Vector((p.x, p.y, 0)).normalized()
                nn.append((q + UP * (0.35 if p.z < 0.12 else 0.05)).normalized())
            cols = [ao_val(0.4, 1.0, (p.z + 0.05) / 0.3) for p in (pa, pb, pc, pd)]
            mb.face([a, b, c, d], "Bark", uv=uv, n=nn, col=cols, uv2=[(0.0, 0.0)] * 4)
    # Schnittfläche
    top = [idx[-1][k] for k in range(sides)]
    rt = max(Vector((p.x, p.y, 0)).length for p in rings[-1])
    uv = [(0.875 + rings[-1][k].x / rt * 0.118, 0.875 + rings[-1][k].y / rt * 0.118) for k in range(sides)]
    tn = L.face_normal(rings[-1])
    mb.face(top, "Bark", uv=uv, n=[tn] * sides, col=[(0.95, 0.95, 0.95)] * sides, uv2=[(0.0, 0.0)] * sides)
    mats = {"Bark": L.material("Bark", col="veg_bark_furrow_col.png", nrm="veg_bark_furrow_nrm.png", rough=0.92, vcol=True)}
    return mb.build(name, mats)


def rock(name, seed):
    import bmesh
    rng = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.5)
    off = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
    planes = []
    for k in range(5):
        pn = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.2, 1.0))).normalized()
        planes.append((pn, rng.uniform(0.33, 0.42)))
    for v in bm.verts:
        p = v.co.copy()
        n1 = noise.noise(p * 1.6 + off)
        n2 = noise.noise(p * 3.7 + off * 1.3)
        s = 1.0 + 0.22 * n1 + 0.07 * n2
        p = p * s
        p.x *= 1.0
        p.y *= 0.78
        p.z *= 0.72
        for (pn, pd) in planes:
            e = p.dot(pn) - pd
            if e > 0:
                p = p - pn * e * 0.85
        if p.z < -0.12:
            p.z = -0.12 + (p.z + 0.12) * 0.25
        v.co = p
    bm.normal_update()
    zmin = min(v.co.z for v in bm.verts)
    zmax = max(v.co.z for v in bm.verts)
    lift = -zmin - 0.08            # 8 cm im Boden
    target_h = 0.6
    sc = target_h / (zmax + lift)
    mb = L.MB()
    vid = {}
    for v in bm.verts:
        p = Vector((v.co.x, v.co.y, v.co.z + lift)) * sc
        vid[v.index] = mb.vert(p)
    vn = {v.index: v.normal.copy() for v in bm.verts}
    for f in bm.faces:
        ids = [vid[v.index] for v in f.verts]
        pts = [mb.v[i] for i in ids]
        fnrm = L.face_normal(pts)
        uv = [L.box_uv(p, fnrm, 1.0 / 0.9) for p in pts]
        cols = [ao_val(0.45, 1.0, (p.z + 0.02) / 0.25) for p in pts]
        mb.face(ids, "Rock", uv=uv, n=[vn[v.index] for v in f.verts], col=cols, uv2=[(0.0, 0.0)] * 3)
    bm.free()
    mats = {"Rock": L.material("Rock", col="veg_rock_col.png", nrm="veg_rock_nrm.png", rough=0.85, vcol=True)}
    return mb.build(name, mats)


# =====================================================================
MODELS = {
    "bush_a": (lambda n: bush(n, 101, "veg_leaf_hazel.png", 0.95, 0.82, 0.60, 92, 0.64, math.radians(25), 6, 0.28,
                              vase=0.45, lump=0.25, stem_h=0.75),
               "Laubbusch Hasel/Holunder-artig ~1.5 m, vasenförmig, 5 Stämmchen unten sichtbar."),
    "bush_b": (lambda n: bush(n, 202, "veg_leaf_dense.png", 0.42, 0.56, 0.38, 64, 0.40, math.radians(28), 0, 0.02,
                              vase=0.15, lump=0.22),
               "Dichter kleiner Busch ~0.9 m (Liguster/Weißdorn-artig), bis zum Boden belaubt."),
    "bush_young_tree": (lambda n: young_tree(n, 303),
                        "Jungbaum/Schössling ~2.5 m (Buche/Hainbuche-artig), dünner Stamm + 6 Äste."),
    "fern": (lambda n: fern(n, 404), "Adlerfarn-Büschel, 6 Wedel (Stiel steil, Spreite überhängend)."),
    "grass_tuft": (lambda n: grass_tuft(n, 505), "Grasbüschel, 6 Karten (je Vorder-+Rückseite)."),
    "grass_tall": (lambda n: grass_tall(n, 606), "Hohes Gras mit Rispen + Brennnessel, 8 Karten (je Vorder-+Rückseite)."),
    "heather": (lambda n: heather(n, 707), "Zwergstrauch-Polster: 6 Karten Blaubeere + 4 Karten Heidekraut (blühend)."),
    "deadwood": (lambda n: deadwood(n, 808), "Liegender Totholz-Ast ~2 m entlang X, teils entrindet, Moos, 4 Aststummel (einer im Boden)."),
    "stump": (lambda n: stump(n, 909), "Baumstumpf Ø~0.6 m mit Wurzelanläufen, schräger Sägeschnitt mit Jahresringen."),
    "rock_small": (lambda n: rock(n, 111), "Findling (Granodiorit) ~0.6 m hoch, 8 cm im Boden, Flechten/Moos."),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = argv or list(MODELS)
    L.reset()
    entries = []
    for name in names:
        L.clear_scene_objects()
        fn, notes = MODELS[name]
        ob = fn(name)
        tris = L.tri_count(ob)
        path = os.path.join(OUT, name + ".glb")
        size = L.export_glb(ob, path, vcol=True)
        mn, mx = L.bbox_godot(ob)
        mats = [m.name for m in ob.data.materials]
        e = dict(file=name + ".glb", height=round(mx[1], 3), bbox_min=mn, bbox_max=mx, tris=tris,
                 materials=mats, notes=notes + " COLOR_0=AO, UV2=(Windgewicht, Phase).",
                 size_bytes=size)
        entries.append(e)
        print(f"[veg] {name}: {tris} tris, bbox {mn} .. {mx}, {mats}, {size} B")
    L.write_manifest(OUT, entries)


if __name__ == "__main__":
    main()
