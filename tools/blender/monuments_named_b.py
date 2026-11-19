"""Baut benannte Dresdner Brunnen und Denkmalanlagen nach Fotovorlagen (Wikimedia Commons, nur als Vorlage)
nach godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_b.py" \
      [-- name ...] [--nopreview]

Bausteine, Konventionen und Materialien stammen aus monuments_build.py (Blender Z-up, Meter, Ursprung =
Bodenmitte, Vorderseite +Y). Maße: belegt, wo im Kommentar "belegt" steht (Wikipedia), sonst aus den Fotos
in data/research/denkmal_fotos/ geschätzt. Zusätzliche Materialien (reine PBR-Farben): Marmor,
Sandstein_dunkel (patinierter, fast schwarzer Sandstein), Eisen (Schmiedeeisen), Zinkblech (Kuppeldeckung).
"""
import math
import os
import sys

import bpy
import bmesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import monuments_build as MB  # noqa: E402
from monuments_build import (L, V, Soup, mat, loft, lathe, cyl, cbox, tube, circle, rrect, build, finish,  # noqa: E402
                             ico, M_T, M_R, TAU, STONE, BRONZE, GOLD, GRANITE, WATER, stack, prism_y, limb)

MARBLE, DARK, IRON, ZINC = "Marmor", "Sandstein_dunkel", "Eisen", "Zinkblech"
PEDS = os.path.join(L.ROOT, "godot", "assets", "models", "peds")


def mats():
    MB.mats()
    mat(MARBLE, "#E4E1DA", 0.55)
    mat(DARK, "#4F473D", 0.9)
    mat(IRON, "#26292B", 0.6, 0.6)
    mat(ZINC, "#5C5E5C", 0.55, 0.5)


# ====================================================================== Figuren
def _legs(l, r):
    return [("UpperLeg_L", l[0]), ("LowerLeg_L", l[1]), ("UpperLeg_R", r[0]), ("LowerLeg_R", r[1])]


def _arms(l, r):
    return [("UpperArm_L", l[0]), ("LowerArm_L", l[1]), ("UpperArm_R", r[0]), ("LowerArm_R", r[1])]


POSES = {
    "rest": [],
    # Togafigur: linke Hand mit Buch vor der Brust, rechter Arm hängt, Blick nach oben
    "toga": [("UpperLeg_L", (-0.03, 0.14, -1.0)), ("LowerLeg_L", (-0.02, -0.04, -1.0)),
             ("Neck", (0.0, 0.0, 1.0)), ("Head", (0.10, -0.10, 1.0)),
             ("UpperArm_L", (-0.20, 0.18, -0.95)), ("LowerArm_L", (0.50, 0.78, 0.22)), ("Hand_L", (0.5, 0.5, 0.6)),
             ("UpperArm_R", (0.16, 0.0, -1.0)), ("LowerArm_R", (0.08, 0.12, -1.0))],
    # Heiligenfigur: beide Unterarme vor dem Leib
    "saint": _arms(((-0.15, 0.1, -1.0), (0.35, 0.8, 0.35)), ((0.15, 0.1, -1.0), (-0.35, 0.8, 0.2))),
    # Tänzerinnen
    "dance_a": _legs(((-0.04, 0.10, -1.0), (0.0, -0.05, -1.0)), ((0.06, -0.40, -0.92), (0.0, -0.80, -0.55)))
    + _arms(((-0.85, 0.15, -0.45), (-0.80, 0.35, -0.10)), ((0.45, 0.25, 0.86), (0.10, 0.15, 1.0)))
    + [("Head", (0.15, 0.1, 1.0))],
    "dance_b": _legs(((-0.06, 0.48, -0.88), (0.0, -0.25, -0.97)), ((0.05, -0.15, -1.0), (0.0, -0.15, -1.0)))
    + _arms(((-0.50, 0.30, 0.82), (-0.15, 0.20, 0.97)), ((0.55, 0.70, -0.40), (0.30, 0.90, 0.25)))
    + [("Head", (-0.12, 0.1, 1.0))],
    "dance_c": _arms(((-0.55, 0.25, -0.80), (-0.45, 0.55, 0.55)), ((0.28, 0.20, -0.92), (-0.60, 0.62, 0.42)))
    + [("Head", (0.0, 0.22, 1.0))],
    # Lagernde: Beine nach vorn, Oberkörper zurückgelehnt, ein Arm stützt
    "recl_a": [("Spine1", (0.0, -0.42, 0.90))]
    + _legs(((-0.12, 1.0, 0.22), (0.0, 0.85, -0.55)), ((0.14, 1.0, 0.02), (0.0, 1.0, -0.12)))
    + _arms(((-0.45, -0.45, -0.75), (-0.10, -0.35, -0.93)), ((0.35, 0.65, -0.55), (0.05, 0.75, 0.55))),
    "recl_b": [("Spine1", (0.0, -0.30, 0.95))]
    + _legs(((-0.14, 1.0, 0.02), (0.0, 1.0, -0.12)), ((0.12, 1.0, 0.30), (0.0, 0.75, -0.65)))
    + _arms(((-0.30, 0.55, -0.70), (0.25, 0.80, 0.30)), ((0.50, -0.40, -0.75), (0.10, -0.35, -0.93))),
    # Sitzende auf der Kante: Unterschenkel hängen
    "sit": _legs(((-0.14, 1.0, -0.02), (0.02, 0.18, -1.0)), ((0.16, 1.0, 0.08), (0.0, 0.05, -1.0)))
    + _arms(((-0.30, 0.15, -0.95), (0.10, 0.85, -0.30)), ((0.45, 0.45, -0.60), (0.0, 0.60, 0.80))),
    # Putto: Knie angezogen, Arme nach vorn
    "ride": _legs(((-0.45, 0.85, -0.25), (-0.10, -0.10, -1.0)), ((0.45, 0.85, -0.25), (0.10, -0.10, -1.0)))
    + _arms(((-0.35, 0.80, -0.30), (0.20, 0.90, 0.30)), ((0.35, 0.80, -0.30), (-0.20, 0.90, 0.30)))
    + [("Head", (0.25, 0.3, 1.0))],
    # Kämpfende
    "fight_a": [("Spine1", (0.0, 0.32, 0.95))]
    + _legs(((-0.12, 0.62, -0.78), (0.0, -0.30, -0.95)), ((0.10, -0.50, -0.86), (0.0, -0.45, -0.90)))
    + _arms(((-0.70, 0.50, 0.35), (-0.20, 0.90, 0.30)), ((0.50, 0.25, 0.83), (0.0, 0.50, 0.87))),
    "fight_b": [("Spine1", (0.15, -0.38, 0.91))]
    + _legs(((-0.15, 0.85, -0.45), (0.0, 0.20, -1.0)), ((0.20, 0.55, -0.80), (0.0, -0.60, -0.80)))
    + _arms(((-0.80, 0.25, 0.45), (-0.45, 0.60, 0.65)), ((0.60, 0.50, 0.55), (-0.30, 0.70, 0.60))),
    # Gänsedieb: weit ausschreitend, vorgebeugt, je eine Gans unter dem Arm bzw. am Hals gepackt
    "thief": [("Spine1", (0.0, 0.30, 0.95)), ("Head", (0.1, 0.35, 0.93))]
    + _legs(((-0.10, 0.58, -0.82), (0.0, -0.10, -1.0)), ((0.10, -0.32, -0.95), (0.0, -0.55, -0.83)))
    + _arms(((-0.35, 0.10, -0.93), (-0.25, 0.50, -0.83)), ((0.32, 0.20, -0.92), (-0.50, 0.80, 0.25))),
}
FIGS = {}


def load_figures():
    files = {"m": "ped_m.glb", "f": "ped_f.glb", "k": "ped_kind1.glb"}
    for g, fn in files.items():
        MB.PED = os.path.join(PEDS, fn)
        poses = dict(POSES)
        if g == "m":
            poses.update({k: v for k, v in MB.POSES.items() if k not in poses})
        res = MB._figures(poses)
        for k, v in res.items():
            FIGS[(g, k)] = v
            if g == "m":
                MB.FIG[k] = v
        s = res["rest"][0]
        print(f"[fig] {g}: {len(s.v)} v, Höhe {max(v.z for v in s.v):.2f}")


def decim(s, ratio, m=None):
    """Vereinfacht eine Soup per Decimate-Modifier (vorher verschweißt)."""
    me = bpy.data.meshes.new("_d")
    me.from_pydata([tuple(v) for v in s.v], [], [tuple(f[0]) for f in s.f])
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("_d", me)
    bpy.context.scene.collection.objects.link(ob)
    md = ob.modifiers.new("d", "DECIMATE")
    md.ratio = ratio
    dg = bpy.context.evaluated_depsgraph_get()
    eo = ob.evaluated_get(dg)
    m2 = eo.to_mesh()
    out = Soup()
    mm = m or s.f[0][1]
    for v in m2.vertices:
        out.vert(v.co)
    for p in m2.polygons:
        out.face(list(p.vertices), mm)
    eo.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return out


def F(g, pose, m, ratio=None):
    s, j = FIGS[(g, pose)]
    s = s.copy()
    if ratio:
        s = decim(s, ratio)
    return s.setmat(m), j


def robe(levels, m, n=10):
    """Gewand als Ellipsen-Loft: levels = [(z, cx, cy, rx, ry)] von unten nach oben."""
    return loft([circle(0, n, z, cx, cy, rx=rx, ry=ry) for z, cx, cy, rx, ry in levels], m, orient=V((0, 0, 1)))


def place(s, phi, r, z=0.0, face="out", extra=0.0):
    """Setzt eine Soup (Blick +Y) auf den Kreis r beim Azimut phi (Grad, 90 = +Y). face: out | in | tan."""
    th = phi - 90.0 + {"out": 0.0, "in": 180.0, "tan": 90.0}[face] + extra
    a = math.radians(phi)
    return s.rot((0, 0, 1), th).move(math.cos(a) * r, math.sin(a) * r, z)


def ground(s):
    lo = min(v.z for v in s.v)
    return s.move(0, 0, -lo)


# ====================================================================== Stein-Bausteine
def basin(R, h, t, zf, n, m, z0=0.0, wl=None, bulge=0.05, foot=0.0):
    """Rundes/vieleckiges Becken: Außenwand, Randwulst, Innenwand, geschlossener Boden bei zf, Wasser bei wl."""
    prof = [(R + foot, z0), (R + foot, z0 + 0.12), (R, z0 + 0.18)] if foot else [(R, z0)]
    prof += [(R, z0 + h - 0.16), (R + bulge, z0 + h - 0.11), (R + bulge, z0 + h), (R - t, z0 + h), (R - t - 0.02, zf)]
    s = lathe(prof, n, m)
    if wl is not None:
        s.poly(circle(R - t - 0.01, n, wl, a0=math.pi / n), WATER)
    return s


def arch_panel(w, z0, zs, za, zg, jamb, t, m, k=4, zsh=None):
    """Wimperg mit Spitzbogenöffnung in der XZ-Ebene (Dicke t um y = 0): Fuß z0, Kämpfer zs, Bogenscheitel za,
    Giebelspitze zg, Giebelansatz zsh."""
    hw, iw = w / 2, w / 2 - jamb
    zsh = zs if zsh is None else zsh
    f = (za - zs) / (math.sqrt(3) * iw)
    arc = []
    for i in range(k + 1):
        u = math.radians(60.0 * i / k)
        arc.append((-iw + 2 * iw * math.cos(u), zs + 2 * iw * math.sin(u) * f))
    pts = [(-hw, z0), (-hw, zsh), (0, zg), (hw, zsh), (hw, z0), (iw, z0)] + arc + [(-x, z) for x, z in arc[-2::-1]] \
        + [(-iw, z0)]
    return prism_y(pts, -t / 2, t / 2, m)


def four(s, d=0.0):
    """Vier Kopien um die Hochachse; die Vorlage liegt bei y = +d."""
    out = Soup()
    for k in range(4):
        out.add(s.copy().move(0, d, 0).rot((0, 0, 1), 90 * k))
    return out


def pinnacle(w, z0, z1, m, cx=0.0, cy=0.0):
    """Fiale: quadratischer Schaft mit Helm."""
    zs = z0 + (z1 - z0) * 0.35
    return stack([(w, w, z0), (w, w, zs), (w * 1.25, w * 1.25, zs + 0.03), (0.02, 0.02, z1)], m, cx=cx, cy=cy)


def rock(r, m, seed, sx=1.0, sy=1.0, sz=0.7):
    s = ico(r, m, 1)
    n = MB.noise

    def w(co):
        k = 1.0 + 0.35 * n.noise(co * (1.6 / r) + MB.Vector((seed, seed * 1.7, seed * 0.3)))
        return (co.x * k * sx, co.y * k * sy, co.z * k * sz)
    return s.warp(w)


def floor0(s, z=0.0):
    return s.warp(lambda co: (co.x, co.y, max(co.z, z)))


def goose(m, spread=False, k=1.0):
    """Gans, Brust nach +Y, Rumpfmitte im Ursprung."""
    s = limb([(-0.30, 0.03, 0.02, 0.02), (-0.20, 0.03, 0.09, 0.08), (0.0, 0.0, 0.14, 0.13), (0.17, 0.04, 0.11, 0.10),
              (0.25, 0.10, 0.06, 0.06)], 8, m, sub=2)
    s.add(limb([(0.20, 0.08, 0.055, 0.055), (0.31, 0.22, 0.04, 0.04), (0.35, 0.36, 0.035, 0.035),
                (0.40, 0.42, 0.045, 0.05), (0.47, 0.40, 0.03, 0.035), (0.56, 0.38, 0.012, 0.015)], 6, m, sub=2))
    for sx in (-1, 1):
        if spread:
            st = [(0.08, 0.02, 0.06, 0.17, 0.035), (0.45, 0.0, 0.22, 0.17, 0.03), (0.85, -0.06, 0.30, 0.12, 0.02),
                  (1.15, -0.14, 0.33, 0.03, 0.01)]
        else:
            st = [(0.10, 0.02, 0.04, 0.16, 0.03), (0.15, -0.12, 0.05, 0.13, 0.025), (0.13, -0.30, 0.06, 0.04, 0.01)]
        rings = [[V((sx * x, cy + math.cos(TAU * i / 6) * ch, cz + math.sin(TAU * i / 6) * th)) for i in range(6)]
                 for x, cy, cz, ch, th in st]
        s.add(loft(rings, m))
    return s.scale(k, k, k)


def railing(pts, h, m, z0=0.0, bars=0, r=0.022, closed=False):
    """Geländer entlang einer Polylinie: Pfosten an den Punkten, Ober- und Untergurt, optional Stäbe."""
    s = Soup()
    pts = [V(p) for p in pts]
    segs = list(zip(pts, pts[1:] + (pts[:1] if closed else [])))
    if not closed:
        segs = segs[:len(pts) - 1]
    sq = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    for p in pts:
        s.add(cbox(p.x, p.y, z0, 0.07, 0.07, h + 0.06, m))
    for a, b in segs:
        for zz in (z0 + 0.12, z0 + h):
            s.add(tube([a + V((0, 0, zz)), b + V((0, 0, zz))], r, 4, m, caps=False, prof=sq))
        for i in range(1, bars + 1):
            p = a.lerp(b, i / (bars + 1))
            s.add(tube([p + V((0, 0, z0 + 0.12)), p + V((0, 0, z0 + h))], r * 0.6, 4, m, caps=False, prof=sq))
    return s


# ====================================================================== Modelle
MODELS = {}
VIEWS = {}


def model(views=None):
    def deco(fn):
        MODELS[fn.__name__] = fn
        if views:
            VIEWS[fn.__name__] = views
        return fn
    return deco


@model(views=((20, 10), (45, 28)))
def mon_cholerabrunnen():
    """Cholerabrunnen (Semper 1846), Sophienstraße. Belegt (Wikipedia): achteckiges Granitbecken
    Ø ca. 6,76 m, vier ca. 0,9 m große Figuren. Gesamthöhe 18 m ist NICHT belegt (verbreitete Angabe, im Artikel
    nicht enthalten; passt zu den Fotoproportionen). Stockwerkshöhen und Breiten aus Fotos geschätzt."""
    D = DARK
    s = Soup()
    a8 = math.pi / 8
    cf = math.cos(a8)
    # Stufenplatte und Gitter (achteckig)
    s.add(lathe([(4.9, 0), (4.9, 0.16), (4.75, 0.16)], 8, GRANITE))
    RF = 4.6
    corners = [V((math.cos(a8 + TAU * k / 8) * RF, math.sin(a8 + TAU * k / 8) * RF, 0)) for k in range(8)]
    s.add(railing(corners, 1.15, IRON, z0=0.16, closed=True))
    sq = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    for k in range(8):                      # Rautengitter
        a, b = corners[k], corners[(k + 1) % 8]
        nd = 5
        for i in range(nd):
            p0, p1 = a.lerp(b, i / nd), a.lerp(b, (i + 1) / nd)
            for q0, q1 in ((p0, p1), (p1, p0)):
                s.add(tube([q0 + V((0, 0, 0.30)), q1 + V((0, 0, 1.30))], 0.014, 4, IRON, caps=False, prof=sq))
    # Becken: Achteck, 6,76 m über die Flächen
    RB = 3.38 / cf
    s.add(basin(RB, 0.86, 0.34, 0.55, 8, GRANITE, z0=0.16, wl=0.90, bulge=0.06, foot=0.08))
    # Pfeilerfuß und Schaft
    s.add(stack([(2.5, 2.5, 0.5), (2.5, 2.5, 1.25), (2.3, 2.3, 1.45), (1.6, 1.6, 1.6), (1.6, 1.6, 5.1)], D))
    for sx in (-1, 1):
        for sy in (-1, 1):                  # Eckstreben mit Fialen
            s.add(stack([(0.56, 0.56, 1.3), (0.56, 0.56, 3.6), (0.50, 0.50, 3.7), (0.50, 0.50, 5.0),
                         (0.60, 0.60, 5.05), (0.60, 0.60, 5.15), (0.30, 0.30, 5.25)], D, cx=sx * 0.84, cy=sy * 0.84))
            s.add(pinnacle(0.24, 5.2, 6.4, D, cx=sx * 0.84, cy=sy * 0.84))
    # Inschrifttafeln, Konsolen, Figuren, Baldachine je Seite
    face = Soup()
    face.add(cbox(0, 0.80, 2.55, 0.95, 0.06, 0.95, D))
    face.add(stack([(1.05, 0.10, 3.5), (1.05, 0.34, 3.62), (0.95, 0.34, 3.72)], D, cy=0.86))
    f, _ = F("m", "saint", D, 0.30)
    f.add(robe([(0.02, 0, 0.02, 0.30, 0.25), (0.55, 0, 0.01, 0.24, 0.20), (1.0, 0, 0, 0.21, 0.16),
                (1.38, 0, 0, 0.20, 0.14)], D, 8))
    kf = 0.95 / 1.78
    f.scale(kf, kf, kf).move(0, 0.93, 3.72)
    face.add(f)
    face.add(prism_y([(-0.42, 4.78), (0.42, 4.78), (0.42, 4.9), (0, 5.3), (-0.42, 4.9)], 0.80, 1.12, D))
    s.add(four(face))
    # Eckbrunnen: Trägerfigur (vereinfacht als Konsole), große Schale, Löwenkopfschale, Kelch
    unit = Soup()
    unit.add(stack([(0.5, 0.5, 0.5), (0.5, 0.5, 0.62), (0.36, 0.42, 0.7), (0.42, 0.5, 1.3), (0.3, 0.3, 1.5)], D))
    unit.add(lathe([(0.20, 1.4), (0.34, 1.52), (0.56, 1.66), (0.60, 1.74), (0.60, 2.28), (0.64, 2.32), (0.64, 2.38),
                    (0.52, 2.38), (0.50, 2.2)], 12, D))
    unit.poly(circle(0.51, 12, 2.33, a0=math.pi / 12), WATER)
    unit.add(lathe([(0.22, 2.2), (0.20, 2.5), (0.26, 2.62), (0.40, 2.72), (0.42, 2.78), (0.42, 3.0), (0.36, 3.04),
                    (0.20, 3.08), (0.15, 3.16), (0.14, 3.48), (0.19, 3.54), (0.25, 3.60), (0.27, 3.66), (0.27, 3.86),
                    (0.20, 3.86), (0.19, 3.74)], 8, D))
    for k in range(4):                      # grüne Echsen als Bronzetupfer am Kelch und am Schalenrand
        a = TAU * k / 4 + 0.4
        unit.add(cbox(math.cos(a) * 0.28, math.sin(a) * 0.28, 3.68, 0.09, 0.09, 0.22, BRONZE))
        unit.add(cbox(math.cos(a) * 0.62, math.sin(a) * 0.62, 2.26, 0.12, 0.12, 0.16, BRONZE))
    for k in range(4):
        s.add(place(unit.copy(), 45 + 90 * k, 1.86))
    # Gesims, Tabernakel (offenes Geschoss mit Wimpergen)
    s.add(stack([(1.75, 1.75, 5.05), (2.0, 2.0, 5.15), (2.0, 2.0, 5.3), (1.9, 1.9, 5.34)], D))
    for sx in (-1, 1):
        for sy in (-1, 1):
            s.add(stack([(0.36, 0.36, 5.3), (0.36, 0.36, 8.5)], D, cx=sx * 0.77, cy=sy * 0.77))
            s.add(pinnacle(0.26, 8.5, 10.1, D, cx=sx * 0.77, cy=sy * 0.77))
    s.add(four(arch_panel(1.9, 7.3, 7.4, 8.45, 9.6, 0.22, 0.26, D, zsh=8.3), 0.80))
    s.add(stack([(1.5, 1.5, 8.9), (1.5, 1.5, 9.3), (1.3, 1.3, 9.4)], D))
    # schlankes offenes Geschoss
    for sx in (-1, 1):
        for sy in (-1, 1):
            s.add(stack([(0.22, 0.22, 9.3), (0.22, 0.22, 12.5)], D, cx=sx * 0.57, cy=sy * 0.57))
            s.add(pinnacle(0.17, 12.5, 13.7, D, cx=sx * 0.57, cy=sy * 0.57))
        for sy in (-1, 1):                  # Wasserspeier
            s.add(tube([V((sx * 0.6, sy * 0.6, 12.35)), V((sx * 1.05, sy * 1.05, 12.45))], 0.07, 5, D,
                       rs=[0.08, 0.05]))
    for k in range(4):                      # Mittelstäbe
        a = TAU * k / 4
        s.add(cbox(math.cos(a) * 0.57, math.sin(a) * 0.57, 9.3, 0.10, 0.10, 3.0, D))
    s.add(four(arch_panel(1.36, 11.7, 11.8, 12.5, 13.3, 0.12, 0.18, D, zsh=12.4), 0.58))
    s.add(stack([(1.2, 1.2, 12.4), (1.2, 1.2, 12.8), (1.0, 1.0, 12.9)], D))
    # Helm mit Krabben und Kreuzblume
    s.add(lathe([(0.60, 12.85), (0.11, 17.0), (0.16, 17.06), (0.16, 17.12), (0.08, 17.18), (0.08, 17.42)], 8, D))
    for k in range(8):
        a = a8 + TAU * k / 8
        for i in range(1, 8):
            t = i / 8
            r = 0.60 + (0.11 - 0.60) * t + 0.03
            c = ico(0.085 - 0.03 * t, D, 0).scale(1, 1, 1.4)
            s.add(c.move(math.cos(a) * r, math.sin(a) * r, 12.85 + (17.0 - 12.85) * t))
    for zz, w in ((17.42, 0.62), (17.68, 0.40)):
        s.add(cbox(0, 0, zz, w, 0.13, 0.13, D)).add(cbox(0, 0, zz, 0.13, w, 0.13, D))
        s.add(cbox(0, 0, zz + 0.13, 0.10, 0.10, 0.14, D))
    s.add(lathe([(0.06, 17.9), (0.10, 17.94), (0.0, 18.0)], 6, D, cap0=False))
    return s, ("Cholerabrunnen (Semper 1846): neugotische Fiale 18 m in achteckigem Granitbecken Ø 6,76 m, "
               "vier Eckbrunnen mit Schalen, vier Nischenfiguren, achteckiges Eisengitter. Inschriftseiten ±X/±Y.")


@model(views=((30, 12), (20, 35)))
def mon_artesischer_brunnen():
    """Artesischer Brunnen (Erlwein 1906), Albertplatz: Rundtempel mit acht ionischen Säulen im runden Becken.
    Keine Maße belegt; alles aus Fotos geschätzt (Säulenhöhe ca. 3,3 m angenommen)."""
    s = Soup()
    # Becken mit Pollerkranz
    s.add(lathe([(4.75, 0), (4.75, 0.10), (4.62, 0.14), (4.60, 0.50), (4.68, 0.56), (4.68, 0.66), (4.22, 0.66),
                 (4.20, 0.20)], 32, STONE))
    s.poly(circle(4.21, 32, 0.50, a0=math.pi / 32), WATER)
    nb = 12
    bol = lathe([(0.27, 0), (0.27, 0.10), (0.23, 0.14), (0.23, 0.78), (0.26, 0.82), (0.26, 0.90), (0.20, 1.0),
                 (0.10, 1.07), (0.0, 1.10)], 10, GRANITE, cap1=False)
    bp = []
    for k in range(nb):
        a = TAU * (k + 0.5) / nb
        bp.append(V((math.cos(a) * 5.35, math.sin(a) * 5.35, 0)))
        s.add(bol.copy().move(bp[-1].x, bp[-1].y, 0))
    for k in range(nb):
        a, b = bp[k], bp[(k + 1) % nb]
        s.add(tube([a + V((0, 0, 0.62)), b + V((0, 0, 0.62))], 0.03, 5, IRON, caps=False))
    # Felssockel und Stylobat
    s.add(lathe([(1.95, 0.20), (1.98, 0.75), (1.88, 1.05)], 10, GRANITE, cap1=False))
    s.add(lathe([(1.86, 1.02), (1.86, 1.12), (1.78, 1.15), (1.78, 1.24), (1.10, 1.24), (1.05, 1.05)], 24, STONE))
    s.poly(circle(1.06, 24, 1.18, a0=math.pi / 24), WATER)
    # Säulen
    RC, z0, hc = 1.42, 1.24, 3.30
    col = lathe([(0.30, 0), (0.30, 0.07), (0.27, 0.10), (0.29, 0.15), (0.25, 0.22), (0.245, 0.30),
                 (0.235, 1.20), (0.205, hc - 0.26), (0.225, hc - 0.24)], 10, STONE, cap1=False)
    col.add(cbox(0, 0, 0, 0.64, 0.64, 0.06, STONE).move(0, 0, -0.05))
    cap = Soup()
    cap.add(cbox(0, 0, hc - 0.24, 0.50, 0.50, 0.10, GOLD))
    cap.add(cbox(0, 0, hc - 0.10, 0.60, 0.60, 0.10, STONE))
    for sx in (-1, 1):                      # Voluten
        cap.add(cyl(0.11, 0.56, 8, GOLD).rot((1, 0, 0), 90).move(sx * 0.27, 0.28, hc - 0.19))
    col.add(cap)
    for k in range(8):
        s.add(place(col.copy(), 22.5 + 45 * k, RC, z0))
    for k in range(8):                      # Girlanden zwischen den Kapitellen
        a0, a1 = math.radians(22.5 + 45 * k), math.radians(67.5 + 45 * k)
        pts = []
        for i in range(6):
            t = i / 5
            a = a0 + (a1 - a0) * t
            sag = 0.42 * math.sin(math.pi * t)
            pts.append(V((math.cos(a) * (RC + 0.26), math.sin(a) * (RC + 0.26), z0 + hc - 0.34 - sag)))
        s.add(tube(pts, 0.05, 5, GOLD, rs=[0.035, 0.05, 0.065, 0.065, 0.05, 0.035]))
    # Gebälk, Kranzgesims, Kuppel
    ze = z0 + hc
    s.add(lathe([(1.20, ze), (1.72, ze), (1.72, ze + 0.22), (1.76, ze + 0.25), (1.72, ze + 0.28), (1.72, ze + 0.72),
                 (1.80, ze + 0.78), (1.98, ze + 0.86), (2.02, ze + 0.90), (2.02, ze + 0.98)], 32, STONE, cap1=False))
    for k in range(8):                      # goldene Rosetten im Fries
        s.add(place(cbox(0, 0, 0, 0.24, 0.05, 0.24, GOLD), 45 * k, 1.72, ze + 0.38))
    zd = ze + 0.98
    s.add(lathe([(2.04, zd - 0.02), (2.06, zd + 0.04), (1.96, zd + 0.16), (1.88, zd + 0.42), (1.70, zd + 0.80),
                 (1.40, zd + 1.12), (1.02, zd + 1.36), (0.70, zd + 1.48), (0.66, zd + 1.60), (0.56, zd + 1.62)],
                24, ZINC))
    # Krone: Reif auf Bügeln
    zk = zd + 1.62
    ring = [V((math.cos(TAU * i / 20) * 0.60, math.sin(TAU * i / 20) * 0.60, zk + 0.62)) for i in range(20)]
    s.add(tube(ring, 0.035, 5, GOLD, closed_path=True))
    ring2 = [V((math.cos(TAU * i / 20) * 0.60, math.sin(TAU * i / 20) * 0.60, zk + 0.03)) for i in range(20)]
    s.add(tube(ring2, 0.035, 5, GOLD, closed_path=True))
    for k in range(8):
        a = TAU * k / 8
        ca, sa = math.cos(a), math.sin(a)
        pts = [V((ca * r, sa * r, zk + dz)) for r, dz in ((0.60, 0.03), (0.72, 0.22), (0.68, 0.45), (0.60, 0.62))]
        s.add(tube(pts, 0.03, 4, GOLD))
        s.add(ico(0.07, GOLD, 0).move(ca * 0.72, sa * 0.72, zk + 0.26))
    return s, ("Artesischer Brunnen (Albertplatz): Rundtempel mit acht ionischen Säulen, Goldkapitellen und "
               "Girlanden, Zinkkuppel mit goldener Krone, rundes Becken Ø 9,4 m mit Pollerkranz. Maße geschätzt.")


def _albert(calm):
    """Zwillingsbrunnen Albertplatz (Diez 1894). Belegt: Granitbecken Ø 18 m, innere Steinschale Ø 7,20 m,
    obere Bronzeschale Ø ca. 5 m in ca. 5 m Höhe. Figuren stark vereinfacht."""
    s = Soup()
    B = BRONZE
    # Außenbecken: flacher, breiter Granitwulst
    s.add(lathe([(9.75, 0), (9.75, 0.06), (9.05, 0.08), (9.0, 0.12), (9.02, 0.36), (8.92, 0.50), (8.70, 0.55),
                 (8.45, 0.50), (8.38, 0.36), (8.36, 0.10)], 40, GRANITE))
    s.poly(circle(8.37, 40, 0.36, a0=math.pi / 40), WATER)
    # innere Steinschale Ø 7,2 m
    s.add(lathe([(3.40, 0.10), (3.56, 0.50), (3.60, 0.78), (3.52, 0.92), (3.50, 0.98), (3.22, 0.98),
                 (3.18, 0.70)], 32, GRANITE))
    s.poly(circle(3.19, 32, 0.90, a0=math.pi / 32), WATER)
    # Steinsockel, Bronzeplinthe, Schaft, Schale
    s.add(lathe([(2.55, 0.70), (2.55, 1.02), (2.40, 1.10), (2.40, 1.44), (2.48, 1.50)], 24, GRANITE, cap1=False))
    s.add(lathe([(2.46, 1.50), (2.52, 1.55), (2.52, 1.64), (2.36, 1.70)], 24, B))
    zp = 1.70
    s.add(lathe([(1.45, 1.70), (1.28, 1.92), (1.05, 2.25), (1.12, 2.70), (1.18, 3.00), (1.02, 3.35), (0.78, 3.60),
                 (0.72, 3.84), (0.86, 3.94)], 16, B, cap0=False, cap1=False))
    s.add(lathe([(0.82, 3.90), (1.05, 4.14), (1.55, 4.40), (2.10, 4.60), (2.42, 4.76), (2.50, 4.90), (2.50, 4.99),
                 (2.36, 4.99), (2.22, 4.86)], 32, B, cap0=False))
    s.poly(circle(2.23, 32, 4.95, a0=math.pi / 32), WATER)
    s.add(lathe([(0.30, 4.86), (0.22, 5.05), (0.10, 5.12), (0.05, 5.30)], 8, B, cap0=False))
    k = 1.85                                # laut Foto etwa doppelte Lebensgröße (Sitzhöhe ~2 m)
    if calm:
        # vier ruhige Gruppen: Lagernde und Sitzende, dazu zwei Kinder
        spec = [("f", "recl_a", 15, 1.72, "tan", 0), ("f", "sit", 110, 2.0, "out", 0),
                ("f", "recl_b", 195, 1.72, "tan", 180), ("m", "sit", 290, 2.0, "out", 0)]
        for g, pose, phi, r, face, ex in spec:
            f, j = F(g, pose, B, 0.42)
            if pose == "sit":
                f.move(0, 0, -(j["Hips"][0].z - 0.11))
            else:
                ground(f)
            f.scale(k, k, k)
            s.add(place(f, phi, r, zp, face, ex))
        for phi, pose in ((62, "sit"), (245, "rest")):       # Kinder
            f, j = F("k", pose, B, 0.22)
            f.scale(1.25, 1.25, 1.25)
            if pose == "sit":
                f.move(0, 0, -(j["Hips"][0].z * 1.25 - 0.11))
                s.add(place(f, phi, 1.55, zp + 1.25, "out"))
                s.add(place(rock(0.75, B, 3.0, sz=1.1), phi, 1.45, zp + 0.55))
            else:
                s.add(place(f, phi, 1.95, zp, "out"))
        for phi, sd in ((150, 1.0), (335, 2.0)):             # Schildkröte, Muschel
            s.add(place(rock(0.5, B, sd, sz=0.45), phi, 2.1, zp + 0.12))
    else:
        # Seeross (steigend, halb versunken), Kämpfende bis über die Knie im Wasser, Seeschlangen
        g, _ = MB.horse(B, True)
        g = decim(g, 0.6)
        g.scale(1.15, 1.15, 1.15).move(0, 0.2, -0.75)
        s.add(place(g, 100, 1.45, zp, "tan"))
        spec = [("m", "fight_a", 55, 1.85, "out", 35), ("m", "fight_a", 190, 1.95, "tan", 0),
                ("m", "fight_b", 250, 1.9, "out", 20), ("m", "fight_a", 318, 1.95, "tan", 180),
                ("m", "fight_b", 10, 1.9, "out", -25)]
        for gg, pose, phi, r, face, ex in spec:
            f, j = F(gg, pose, B, 0.40)
            ground(f)
            f.move(0, 0, -0.52)
            f.add(limb([(0.0, 0.10, 0.17, 0.15), (0.45, 0.06, 0.13, 0.11), (0.85, 0.10, 0.09, 0.07),
                        (1.10, 0.30, 0.05, 0.04), (1.22, 0.50, 0.14, 0.02)], 6, B, sub=2))
            kk = k * (0.92 if pose == "fight_a" else 1.0)
            f.scale(kk, kk, kk)
            s.add(place(f, phi, r, zp, face, ex))
        for phi0, sd in ((140, 0.0), (275, 1.5)):            # Seeschlangen: wogende Schläuche
            pts, rs = [], []
            for i in range(9):
                t = i / 8
                a = math.radians(phi0 + 60 * t)
                rr = 2.12 + 0.12 * math.sin(t * 7 + sd)
                pts.append(V((math.cos(a) * rr, math.sin(a) * rr, zp + 0.25 + 0.5 * abs(math.sin(t * math.pi * 2.5)))))
                rs.append(0.10 + 0.16 * math.sin(math.pi * min(t * 1.4, 1.0)))
            s.add(tube(pts, 0.15, 6, B, rs=rs))
    return s


@model(views=((25, 10), (40, 30)))
def mon_stuermische_wogen():
    return _albert(False), ("Brunnen Stürmische Wogen (Diez, Albertplatz West): Granitbecken Ø 18 m, innere "
                            "Steinschale Ø 7,2 m, Bronzegruppe (Sturm auf Ross, Kämpfende, Seeschlangen) um den "
                            "Schaft, Bronzeschale Ø 5 m in 5 m Höhe. Figuren stark vereinfacht.")


@model(views=((25, 10), (40, 30)))
def mon_stille_wasser():
    return _albert(True), ("Brunnen Stille Wasser (Diez, Albertplatz Ost): Granitbecken Ø 18 m, innere "
                           "Steinschale Ø 7,2 m, lagernde und sitzende Nymphen mit Kindern um den Schaft, "
                           "Bronzeschale Ø 5 m in 5 m Höhe. Figuren stark vereinfacht.")


@model(views=((20, 12), (200, 25)))
def mon_mozartbrunnen():
    """Mozartbrunnen (Hosaeus 1907), Bürgerwiese: drei vergoldete Figuren (Anmut, Ernst, Heiterkeit) tanzen um
    eine Stele. Keine Maße belegt; aus Fotos geschätzt (Figuren ca. 2,1 m, Brüstung ca. 10,5 m breit)."""
    s = Soup()
    S = STONE
    # gerade Brüstung (Schauseite +Y) mit Endpfosten
    for sx in (-1, 1):
        s.add(stack([(3.7, 0.50, 0), (3.7, 0.50, 0.90), (3.75, 0.58, 0.93), (3.75, 0.58, 1.02)], S, cx=sx * 3.5, cy=0))
        s.add(stack([(0.62, 0.72, 0), (0.62, 0.72, 1.10), (0.70, 0.80, 1.13), (0.70, 0.80, 1.22)], S, cx=sx * 5.35,
                    cy=0))
    # Halbrundbecken auf der Rückseite (-Y), niedriger Rand

    def dring(R, z, n=14):
        return [V((math.cos(math.pi + math.pi * i / n) * R, -0.15 + math.sin(math.pi + math.pi * i / n) * R, z))
                for i in range(n + 1)]
    s.add(loft([dring(5.3, 0), dring(5.3, 0.36), dring(5.24, 0.42), dring(4.86, 0.42), dring(4.84, 0.08)], S,
               orient=V((0, 0, 1))))
    s.poly(dring(4.85, 0.30), WATER)
    # Stufensockel: Block mit Stufen zum Becken hin
    s.add(stack([(4.4, 4.6, 0), (4.4, 4.6, 0.36), (4.0, 3.9, 0.36), (4.0, 3.9, 0.72)], S, cy=-0.75))
    s.add(stack([(3.6, 3.2, 0.0), (3.6, 3.2, 1.08), (3.4, 2.9, 1.08), (3.4, 2.9, 1.40), (3.5, 3.0, 1.44),
                 (3.5, 3.0, 1.52), (3.3, 2.8, 1.55)], S, cy=-0.2))
    zp = 1.55
    cyp = -0.2
    # Stele (grauer Stein, rund, mit Kopfprofil), etwa schulterhoch
    s.add(lathe([(0.60, zp), (0.60, zp + 0.12), (0.48, zp + 0.20), (0.43, zp + 0.30), (0.41, zp + 1.10),
                 (0.46, zp + 1.16), (0.53, zp + 1.22), (0.53, zp + 1.32), (0.40, zp + 1.37), (0.28, zp + 1.45)],
                14, GRANITE, cy=cyp))
    s.add(cbox(0, cyp + 0.41, zp + 0.78, 0.5, 0.04, 0.16, GOLD))          # Inschrift MOZART
    kf = 2.1 / 1.66
    dress = [(0.02, 0, 0.0, 0.26, 0.23), (0.45, 0, 0.0, 0.20, 0.17), (0.84, 0, 0, 0.18, 0.14), (1.0, 0, 0, 0.165, 0.125)]
    for pose, phi, long in (("dance_a", 90, False), ("dance_b", 210, False), ("dance_c", 330, True)):
        f, j = F("f", pose, GOLD)
        if long:
            f.add(robe(dress, GOLD))
        else:                               # kurzes, wehendes Tuch um die Hüfte
            f.add(robe([(0.52, 0.03, -0.10, 0.30, 0.26), (0.70, 0.0, -0.03, 0.21, 0.17), (0.90, 0, 0, 0.18, 0.14),
                        (1.0, 0, 0, 0.165, 0.125)], GOLD))
        ground(f).scale(kf, kf, kf)
        s.add(place(f, phi, 1.0, zp, "tan").move(0, cyp, 0))
    return s, ("Mozartbrunnen (Bürgerwiese): drei vergoldete tanzende Frauenfiguren um eine runde Steinstele auf "
               "Stufensockel; gerade Sandsteinbrüstung 11 m (Schauseite +Y), dahinter (-Y) Stufen und flaches "
               "Halbrundbecken. Maße geschätzt.")


@model(views=((15, 12), (40, 35)))
def mon_schillerdenkmal():
    """Schillerdenkmal (Werner/Hempel 1914), Jorge-Gomondai-Platz. Belegt: Standbild 3,40 m, Rotunde Ø 7,50 m,
    Laaser Marmor; Wandhöhe 'schulterhoch' (hier 1,55 m), Sockel und Pfeiler geschätzt."""
    M = MARBLE
    s = Soup()
    Ro, Ri, hw = 3.75, 3.45, 1.55
    gap = math.radians(21)                  # halber Öffnungswinkel der Eingangsseite (+Y)
    n = 28
    angs = [math.pi / 2 + gap + (TAU - 2 * gap) * i / n for i in range(n + 1)]
    prof = [(Ro + 0.10, 0.0), (Ro + 0.10, 0.10), (Ro, 0.16), (Ro, hw - 0.12), (Ro + 0.05, hw - 0.10), (Ro + 0.05, hw),
            (Ri - 0.03, hw), (Ri - 0.03, hw - 0.10), (Ri, hw - 0.12), (Ri, 0.0)]
    rings = [[V((math.cos(a) * r, math.sin(a) * r, z)) for a in angs] for r, z in prof]
    s.add(loft(rings, M, closed=False))
    # Bodenplatte (Marmor) und neun Reliefplatten innen
    s.add(lathe([(Ro, 0.0), (Ro, 0.04), (0.0, 0.04)], 28, M, cap0=False, cap1=False))
    for i in range(9):
        a = math.degrees(angs[0]) + (360 - 2 * math.degrees(gap)) * (i + 0.5) / 9
        s.add(place(cbox(0, 0, 0, 1.25, 0.05, 0.95, M), a, Ri - 0.02, 0.35))
    # Eingangspfeiler mit Masken, Eisentor
    xg = math.sin(gap) * Ro
    for sx in (-1, 1):
        cx, cy = sx * (xg + 0.12), math.cos(gap) * Ro + 0.02
        s.add(stack([(1.0, 0.62, 0), (1.0, 0.62, 1.95), (1.08, 0.70, 1.98), (1.08, 0.70, 2.08), (1.0, 0.62, 2.10)],
                    M, cx=cx, cy=cy))
        s.add(ico(0.21, M, 1).scale(0.95, 0.45, 1.2).move(cx, cy + 0.31, 1.55))
    y_g = math.cos(gap) * Ro + 0.05
    x0 = xg - 0.38
    s.add(railing([(-x0, y_g, 0), (0, y_g, 0), (x0, y_g, 0)], 1.45, IRON, bars=6, r=0.02))
    # Sockel und Standbild
    s.add(stack([(1.9, 1.9, 0.04), (1.9, 1.9, 0.20), (1.6, 1.6, 0.20), (1.6, 1.6, 0.34), (1.25, 1.25, 0.42),
                 (1.20, 1.20, 1.42), (1.34, 1.34, 1.50), (1.34, 1.34, 1.60)], M))
    for k in range(4):                      # Girlande am Sockel
        pts = [V((-0.5 + 0.25 * i, 0.62, 1.30 - 0.16 * math.sin(math.pi * i / 4))) for i in range(5)]
        s.add(tube(pts, 0.05, 5, M).rot((0, 0, 1), 90 * k))
    f, j = F("m", "toga", M)
    f.add(robe([(0.02, -0.02, 0.03, 0.36, 0.31), (0.50, -0.03, 0.02, 0.28, 0.24), (0.95, -0.04, 0.0, 0.235, 0.185),
                (1.22, -0.05, 0.0, 0.205, 0.165), (1.40, -0.09, -0.01, 0.15, 0.14)], M))
    # Buch, Haar
    hand, tip = j["Hand_L"]
    f.add(cbox(0, 0, -0.08, 0.13, 0.035, 0.17, M).rot((1, 0, 0), -20).move(*(hand + (tip - hand) * 0.5 + V((0, 0.05, 0)))))
    hd = j["Head"][0]
    f.add(ico(0.115, M, 1).scale(1.0, 0.9, 0.95).move(hd.x, hd.y - 0.05, hd.z + 0.085))
    f.add(cbox(0, 0.02, -0.03, 0.80, 0.72, 0.05, M))
    kf = 3.40 / 1.80
    f.scale(kf, kf, kf).move(0, 0, 1.60 + 0.03 * kf)
    s.add(f)
    return s, ("Schillerdenkmal (Werner/Hempel 1914): Marmorstandbild 3,4 m in Toga mit Buch auf Sockel in "
               "schulterhoher Marmorrotunde Ø 7,5 m mit Reliefplatten, Eingang mit zwei Maskenpfeilern und "
               "Eisentor vorn (+Y).")


@model(views=((25, 10), (205, 28)))
def mon_gaensediebbrunnen():
    """Gänsediebbrunnen (Diez 1880), Weiße Gasse. Keine Maße belegt; aus Fotos geschätzt (Figur lebensgroß
    angenommen → Gesamthöhe ca. 4,7 m, Bodenbecken Ø ca. 6 m)."""
    s = Soup()
    B, G = BRONZE, GRANITE
    s.add(lathe([(4.65, 0), (4.65, 0.16), (3.95, 0.16), (3.95, 0.32), (3.05, 0.32)], 40, G, cap1=False))
    s.add(lathe([(2.88, 0.32), (3.00, 0.52), (3.03, 0.78), (2.95, 0.98), (2.97, 1.04), (2.95, 1.10), (2.64, 1.10),
                 (2.60, 0.62)], 40, G))
    s.poly(circle(2.61, 40, 0.96, a0=math.pi / 40), WATER)
    # Mittelpfeiler (achteckig) mit vier Säulchen, Auffangschale
    s.add(lathe([(1.05, 0.62), (1.05, 0.95), (0.86, 1.04), (0.74, 1.12), (0.70, 1.72), (0.80, 1.82)], 8, G,
                cap1=False))
    for k in range(4):
        a = TAU * k / 4 + TAU / 8
        s.add(lathe([(0.13, 1.02), (0.10, 1.08), (0.09, 1.74), (0.12, 1.80)], 6, G, cx=math.cos(a) * 0.86,
                    cy=math.sin(a) * 0.86, cap0=False, cap1=False))
    s.add(lathe([(0.62, 1.78), (0.92, 1.86), (1.08, 2.00), (1.13, 2.12), (1.13, 2.20), (0.99, 2.20),
                 (0.96, 2.08)], 24, G, cap0=False))
    s.poly(circle(0.97, 24, 2.15, a0=math.pi / 24), WATER)
    # Postament mit Bronzeschmuck
    s.add(stack([(0.98, 0.98, 2.08), (0.98, 0.98, 2.30), (0.82, 0.82, 2.36), (0.74, 0.74, 2.96), (0.90, 0.90, 3.03),
                 (0.98, 0.98, 3.10), (0.98, 0.98, 3.17)], G, r=0.12))
    for k in range(4):                      # Voluten an den Ecken, Girlanden an den Seiten
        a = TAU * k / 4 + TAU / 8
        ca, sa = math.cos(a), math.sin(a)
        pts = [V((ca * r, sa * r, z)) for r, z in ((0.50, 2.95), (0.56, 2.70), (0.70, 2.42), (0.90, 2.30), (1.00, 2.40),
                                                    (0.95, 2.50))]
        s.add(tube(pts, 0.06, 5, B, rs=[0.05, 0.06, 0.07, 0.07, 0.06, 0.04]))
        s.add(cyl(0.11, 0.10, 8, B).rot((1, 0, 0), 90).move(0, 0.05, 0).rot((0, 0, 1), math.degrees(a) - 90)
              .move(ca * 0.92, sa * 0.92, 2.42))
        g0 = [V((-0.34 + 0.17 * i, 0.44, 2.80 - 0.14 * math.sin(math.pi * i / 4))) for i in range(5)]
        s.add(tube(g0, 0.05, 5, B).rot((0, 0, 1), 90 * k))
    for phi in (90, 270):                   # zwei Gänse mit gespreizten Flügeln
        s.add(place(goose(B, True, 1.15), phi, 0.52, 2.62, "out"))
    # Figur: Gänsedieb mit zwei Gänsen
    zf = 3.17
    s.add(stack([(0.86, 0.86, zf), (0.80, 0.80, zf + 0.08)], B, r=0.2))
    f, j = F("m", "thief", B)
    hd, ht = j["Head"]
    up = (ht - hd).normalized()
    hat = lathe([(0.19, 0.0), (0.20, 0.02), (0.11, 0.05), (0.10, 0.14), (0.03, 0.19)], 8, B)
    q = V((0, 0, 1)).rotation_difference(up)
    hat.xf(M_T(*(hd + up * 0.17)) @ q.to_matrix().to_4x4())
    f.add(hat)
    hr = j["Hand_R"][0]
    f.add(goose(B, False, 0.95).rot((0, 0, 1), 70).move(hr.x - 0.10, hr.y - 0.02, hr.z - 0.02))
    hl = j["Hand_L"][0]
    f.add(goose(B, False, 0.9).rot((1, 0, 0), 60).rot((0, 0, 1), -30).move(hl.x - 0.05, hl.y + 0.05, hl.z - 0.28))
    f.add(cbox(0, 0, 0, 0.26, 0.12, 0.22, B).move(0.02, -0.20, 1.02))      # Ranzen
    ground(f)
    kf = 0.95
    f.scale(kf, kf, kf).move(0, -0.05, zf + 0.08)
    s.add(f)
    return s, ("Gänsediebbrunnen (Diez, Weiße Gasse): Bronzefigur mit zwei Gänsen auf Granitpostament mit "
               "Bronzevoluten und zwei Gänsen, Auffangschale auf Pfeiler mit vier Säulchen, rundes Granitbecken "
               "Ø 6 m auf zwei Stufen. Maße geschätzt. Figur schreitet nach +Y.")


@model(views=((20, 14), (50, 35)))
def mon_delphinbrunnen():
    """Delphinbrunnen (um 1750), Brühlscher Garten: Putto auf Delphin über einer Muschelschale auf Felsen vor
    der Stützmauer, davor flaches Becken. Keine Maße belegt; aus Fotos geschätzt."""
    s = Soup()
    S = STONE
    ZD = -1.5                               # Becken und Mauer reichen als geschlossener Sockel 1,5 m unter den Ursprung (Hanglage)
    # Stützmauer (Rückseite -Y), drei Felder, das mittlere zurückgesetzt
    yw = -2.3
    for cx, w, dy in ((-4.4, 4.2, 0.35), (0.0, 4.6, 0.0), (4.4, 4.2, 0.35)):
        s.add(stack([(w, 0.7, ZD), (w, 0.7, 0.45), (w - 0.05, 0.6, 0.5), (w - 0.05, 0.6, 2.05), (w + 0.05, 0.74, 2.1),
                     (w + 0.05, 0.74, 2.25)], S, cx=cx, cy=yw + dy))
        s.add(cbox(cx, yw + dy + 0.31, 0.75, w - 1.0, 0.03, 1.05, S))    # Spiegelfeld
    for cx in (-6.5, -2.3, 2.3, 6.5):
        s.add(stack([(0.6, 0.9, ZD), (0.6, 0.9, 2.12), (0.7, 1.0, 2.16), (0.7, 1.0, 2.30)], S, cx=cx, cy=yw + 0.3))
    s.add(railing([(-6.5, yw + 0.3, 0), (-2.3, yw + 0.3, 0), (2.3, yw + 0.3, 0), (6.5, yw + 0.3, 0)], 0.95, IRON,
                  z0=2.30, bars=9, r=0.02))
    # Becken: flache, vorn gerundete Schale
    W, Dp, r, t = 13.0, 5.6, 2.4, 0.35
    cy = 0.45
    rings = [rrect(W, Dp, r, 4, ZD, 0, cy), rrect(W, Dp, r, 4, 0.22, 0, cy), rrect(W - 0.08, Dp - 0.08, r, 4, 0.28, 0, cy),
             rrect(W - 2 * t, Dp - 2 * t, r - t, 4, 0.28, 0, cy), rrect(W - 2 * t - 0.03, Dp - 2 * t - 0.03, r - t, 4, 0.05, 0, cy)]
    s.add(loft(rings, S, orient=V((0, 0, 1))))
    s.poly(rrect(W - 2 * t - 0.03, Dp - 2 * t - 0.03, r - t, 4, 0.18, 0, cy), WATER)
    # Felsen, Muschelschale
    for i, (x, y, rr, zz) in enumerate(((0.0, -1.2, 0.95, 0.35), (-0.9, -1.3, 0.6, 0.25), (0.9, -1.25, 0.65, 0.25),
                                        (-0.3, -0.75, 0.55, 0.2), (0.5, -0.8, 0.5, 0.2), (-3.2, -1.4, 0.55, 0.2),
                                        (3.3, -1.4, 0.6, 0.2))):
        s.add(floor0(rock(rr, GRANITE, 1.3 * i + 0.5, sz=0.8).move(x, y, zz), 0.05))
    zb = 1.05
    n = 16
    sh = []
    for r_, z_ in ((0.25, zb - 0.28), (0.95, zb - 0.12), (1.40, zb + 0.06), (1.48, zb + 0.14), (1.36, zb + 0.14),
                   (1.30, zb + 0.04)):
        ring = []
        for i in range(n):
            a = TAU * i / n + math.pi / n
            sc = 1.0 + 0.06 * math.cos(a * 6)                 # gewellter Muschelrand
            ring.append(V((math.cos(a) * r_ * sc, math.sin(a) * r_ * sc * 0.72 - 1.0, z_)))
        sh.append(ring)
    s.add(loft(sh, S, orient=V((0, 0, 1))))
    s.poly(circle(1.0, n, zb + 0.07, 0, -1.0, a0=math.pi / n, rx=1.30, ry=0.94), WATER)
    for sx in (-1, 1):                      # Voluten seitlich der Schale
        s.add(cyl(0.34, 0.30, 10, S).rot((1, 0, 0), 90).move(sx * 1.05, -1.55, zb + 0.42))
    # Delphin (Kopf unten vorn, Schwanz nach oben) und Putto
    d = limb([(-0.95, zb + 0.55, 0.26, 0.24), (-1.25, zb + 0.20, 0.30, 0.26), (-1.55, zb + 0.42, 0.30, 0.30),
              (-1.72, zb + 0.95, 0.24, 0.24), (-1.60, zb + 1.50, 0.16, 0.15), (-1.40, zb + 1.90, 0.10, 0.08),
              (-1.30, zb + 2.25, 0.30, 0.04)], 8, S, sub=3)
    s.add(d)
    f, j = F("k", "ride", S, 0.6)
    hz = j["Hips"][0].z
    kf = 1.0
    f.move(0, 0, -hz).scale(kf, kf, kf).rot((0, 0, 1), -25).move(0.05, -1.45, zb + 0.78)
    s.add(f)
    return s, ("Delphinbrunnen (Brühlscher Garten): Putto auf Delphin über Muschelschale auf Felsen, vor "
               "dreiteiliger Sandstein-Stützmauer mit Eisengeländer (Rückseite -Y), flaches Becken 13 × 5,6 m "
               "davor; Becken- und Mauersockel reichen 1,5 m unter den Ursprung (Hanglage). Maße geschätzt.")


CLOSE = {"mon_cholerabrunnen": ((0, 0, 3.2), 4.2, ((15, 8), (45, 20))),
         "mon_stuermische_wogen": ((0, 0, 3.0), 4.2, ((20, 8), (200, 8))),
         "mon_stille_wasser": ((0, 0, 3.0), 4.2, ((20, 8), (200, 8))),
         "mon_mozartbrunnen": ((0, -0.2, 2.6), 2.8, ((10, 8), (200, 10))),
         "mon_schillerdenkmal": ((0, 0, 3.3), 2.6, ((10, 5), (60, 10))),
         "mon_gaensediebbrunnen": ((0, 0, 3.4), 2.4, ((15, 5), (110, 10))),
         "mon_delphinbrunnen": ((0, -1.2, 1.9), 2.6, ((10, 10), (50, 20))),
         "mon_artesischer_brunnen": ((0, 0, 4.2), 4.6, ((10, 5), (40, 15)))}


def closeup(name, c, R, views):
    """Kontrollbilder (nicht Teil der Auslieferung) nach tools/blender/monb_tmp/."""
    sc = bpy.context.scene
    cam = sc.camera
    D = R / math.sin(cam.data.angle / 2) * 1.02
    for k, (az, el) in enumerate(views):
        a, e = math.radians(az), math.radians(el)
        d = V((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        cam.location = V(c) + d * D
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sc.render.resolution_x = sc.render.resolution_y = 640
        sc.render.filepath = os.path.join(HERE, "monb_tmp", f"{name}_c{k}.png")
        bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    L.NOPREVIEW = "--nopreview" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MODELS)
    load_figures()
    for name in names:
        L.reset()
        mats()
        soup, notes = MODELS[name]()
        ob = build(soup, name, smooth_angle=42, merge=True)
        finish(name, [ob], notes, views=VIEWS.get(name))
        if "--close" in argv and name in CLOSE and not L.NOPREVIEW:
            closeup(name, *CLOSE[name])
    try:
        os.rmdir(L.TMP)
    except OSError:
        pass


if __name__ == "__main__":
    main()
