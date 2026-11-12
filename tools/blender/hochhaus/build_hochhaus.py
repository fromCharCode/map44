"""Appartement-Hochhaus „Pirnaisches Tor“ (Grunaer Straße 5, Typ P 27, 1964–66) im Zustand 2019–2022 mit dem
Graffito „NADDL.UND.RONNY.SIEGT!“ auf der WNW-Attika. Maße/Farben: data/research/pirnaischer_platz_hochhaus.md (5.x).

Koordinaten im Skript = Godot-Lokalkoordinaten des Modells: +X Längsachse nach NNE, −Z = WNW-Fassade (Schriftseite),
Y oben, Y = 0 Gelände. Umrechnung nach Blender: (x, y, z)_Godot -> (x, −z, y)_Blender (glTF-Export Y-up).
Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python build_hochhaus.py -- <graffiti.png> <out.glb>"""
import bpy, bmesh, sys, math, random
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
GRAFFITI, OUT = args[0], args[1]
rng = random.Random(1966)
bpy.ops.wm.read_factory_settings(use_empty=True)

LX = 26.92          # halbe Länge
LZ = 8.605          # halbe Tiefe
LOG_D = 1.20        # Loggientiefe
Y_EG = 5.80
Y_OG1 = 8.70
FLOOR = 2.80
N_FLOORS = 12
Y_ATT = Y_OG1 + N_FLOORS * FLOOR      # 42.30
Y_TOP = 45.00
Y_ROOF = 44.00
AX = 4.895          # Achsbreite (11 Achsen)


def hexcol(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


MATS = {}


def mat(name, hexc, rough=0.85, metal=0.0):
    if name in MATS:
        return name
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*hexcol(hexc), 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    MATS[name] = m
    return name


# Farben Variante N (2019–22)
mat("Schotten", "#E2DFD8")
mat("Panel", "#C9C1A0")
mat("Rail", "#E6E4DE", rough=0.5, metal=0.3)
mat("LoggiaWall", "#D8D4CC")
mat("LoggiaYellow", "#E0B43A")
mat("LoggiaRed", "#C65A3A")
mat("Glass", "#2C3238", rough=0.08, metal=0.2)
mat("Frame", "#E6E4DE", rough=0.6)
mat("Attika", "#827C73", rough=0.95)
mat("Joint", "#5F5A54", rough=0.95)
mat("Gable", "#C2BCB0", rough=0.92)
mat("PaintRed", "#C23A3A", rough=0.8)
mat("PaintGreen", "#4E9A4A", rough=0.8)
mat("Sockel", "#4F4746", rough=0.9)
mat("Stilt", "#A8A49C", rough=0.95)
mat("Ceiling", "#B9B6AE", rough=0.95)
mat("EGWall", "#9A9C9A", rough=0.4, metal=0.1)
mat("RoofSkin", "#505050", rough=0.95)
mat("RoofPlate", "#41555E", rough=0.8)
mat("RoofConcrete", "#8A847A", rough=0.95)
mat("RoofUnder", "#6E6A64", rough=0.95)
mat("GraffWall", "#5A5560", rough=0.9)
mat("GraffViolet", "#7B4FA0", rough=0.8)
mat("GraffMagenta", "#C23B8E", rough=0.8)
mat("GraffWhite", "#E6E4DE", rough=0.8)
mat("ShopWhite", "#E9E9E6", rough=0.7)
mat("ShopRoof", "#807E67", rough=0.95)
mat("ShopGlass", "#3A4450", rough=0.1, metal=0.2)
mat("ShopSign", "#1F5FA8", rough=0.5)

BMS = {}


def bm_of(name):
    if name not in BMS:
        BMS[name] = bmesh.new()
    return BMS[name]


def V(x, y, z):
    return Vector((x, -z, y))


def box(m, x0, x1, y0, y1, z0, z1):
    """Achsparallele Box in Godot-Koordinaten."""
    bm = bm_of(m)
    xa, xb = min(x0, x1), max(x0, x1)
    ya, yb = min(y0, y1), max(y0, y1)
    za, zb = min(z0, z1), max(z0, z1)
    v = [bm.verts.new(V(x, y, z)) for x in (xa, xb) for y in (ya, yb) for z in (za, zb)]
    # Index: x*4 + y*2 + z
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    for q in f:
        try:
            bm.faces.new([v[i] for i in q])
        except ValueError:
            pass


def quad_z(m, x0, x1, y0, y1, z, out_sign):
    """Rechteck in der Ebene z = const, Vorderseite zeigt nach out_sign·Z."""
    bm = bm_of(m)
    a, b = (x0, x1) if out_sign > 0 else (x1, x0)
    vs = [bm.verts.new(V(a, y0, z)), bm.verts.new(V(b, y0, z)), bm.verts.new(V(b, y1, z)), bm.verts.new(V(a, y1, z))]
    bm.faces.new(vs)


def quad_x(m, z0, z1, y0, y1, x, out_sign):
    bm = bm_of(m)
    a, b = (z1, z0) if out_sign > 0 else (z0, z1)
    vs = [bm.verts.new(V(x, y0, a)), bm.verts.new(V(x, y0, b)), bm.verts.new(V(x, y1, b)), bm.verts.new(V(x, y1, a))]
    bm.faces.new(vs)


# --------------------------------------------------------------------------------------------- Kern & Giebel
core_z = LZ - LOG_D
box("Gable", -LX, LX, Y_OG1, Y_ATT, -core_z, core_z)
# 1. OG: geschlossenes Sockelband
box("Sockel", -LX, LX, Y_EG, Y_OG1, -LZ, LZ)
# Attika (massiv bis Dachfläche) + Brüstung
box("Attika", -LX, LX, Y_ATT, Y_ROOF, -LZ, LZ)
for zz in (-LZ, LZ - 0.25):
    box("Attika", -LX, LX, Y_ROOF, Y_TOP, zz, zz + 0.25)
for xx in (-LX, LX - 0.25):
    box("Attika", xx, xx + 0.25, Y_ROOF, Y_TOP, -LZ, LZ)
box("RoofSkin", -LX + 0.25, LX - 0.25, Y_ROOF, Y_ROOF + 0.02, -LZ + 0.25, LZ - 0.25)
# Attika-Felder (Fugen) und Sockelfenster auf beiden Breitseiten
for s in (-1, 1):
    zf = s * (LZ + 0.004)
    for k in range(12):
        x = -LX + k * AX
        quad_z("Joint", x - 0.025, x + 0.025, Y_ATT, Y_TOP, zf, s)
    x = -LX + 1.2
    while x < LX - 0.8:
        quad_z("Glass", x, x + 0.6, 7.0, 7.6, zf, s)
        x += 2.45
# Giebel: Flurfensterachse mittig, Farbnasen oben
for sx in (-1, 1):
    xf = sx * (LX + 0.004)
    for i in range(N_FLOORS):
        y0 = Y_OG1 + i * FLOOR + 0.9
        quad_x("Glass", -0.45, 0.45, y0, y0 + 1.2, xf, sx)
    for k in range(5):
        zc = rng.uniform(-6.5, 6.5)
        ln = rng.uniform(1.0, 3.5)
        quad_x("PaintRed" if k % 2 == 0 else "PaintGreen", zc, zc + rng.uniform(0.15, 0.4), Y_ATT - ln, Y_ATT - 0.1, xf + sx * 0.002, sx)

# --------------------------------------------------------------------------------------------- Loggienfassaden
axes = [-LX + k * AX for k in range(12)]
for s in (-1, 1):
    zf = s * LZ                    # Fassadenebene (Vorderkante Schotten/Deckenstirn)
    zb = s * core_z                # Loggia-Rückwand
    # Hauptschotten an den Achsgrenzen, Zwischenschotten in Achsmitte
    for k, x in enumerate(axes):
        t = 0.20
        box("Schotten", x - t / 2 if 0 < k < 11 else (x if k == 0 else x - t), x + t / 2 if 0 < k < 11 else (x + t if k == 0 else x),
            Y_OG1, Y_ATT, zb, zf)
        if k < 11:
            xm = x + AX / 2
            box("Schotten", xm - 0.06, xm + 0.06, Y_OG1, Y_ATT, zb, zf)
    for i in range(N_FLOORS):
        y0 = Y_OG1 + i * FLOOR
        # Deckenplatte mit Stirn
        box("Schotten", -LX, LX, y0, y0 + 0.25, zb, zf)
        for k in range(11):
            for half in (0, 1):
                xa = axes[k] + (0.10 if half == 0 else AX / 2 + 0.06)
                xb = axes[k] + (AX / 2 - 0.06 if half == 0 else AX - 0.10)
                # Brüstungspaneel
                box("Panel", xa, xb, y0 + 0.25, y0 + 1.10, zf - s * 0.08, zf)
                # Rohrgeländer (leicht gekröpft) mit Pfosten
                zr = zf + s * 0.06
                box("Rail", xa, xb, y0 + 1.30, y0 + 1.35, zr - 0.025, zr + 0.025)
                n_p = max(2, int((xb - xa) / 0.8) + 1)
                for p in range(n_p):
                    xp = xa + 0.05 + (xb - xa - 0.1) * p / (n_p - 1)
                    box("Rail", xp - 0.02, xp + 0.02, y0 + 1.10, y0 + 1.33, zr - 0.02, zr + 0.02)
                # Rückwand (einzelne Bewohnerfarben) mit Balkontür + Fenster
                r = rng.random()
                wm = "LoggiaYellow" if r < 0.06 else ("LoggiaRed" if r < 0.10 else "LoggiaWall")
                quad_z(wm, xa, xb, y0 + 0.25, y0 + FLOOR, zb + s * 0.002, s)
                zw = zb + s * 0.012
                wl = xb - xa
                dx0 = xa + 0.15
                quad_z("Frame", dx0 - 0.05, dx0 + 0.85 + 0.05, y0 + 0.25, y0 + 0.25 + 2.10, zw, s)
                quad_z("Glass", dx0, dx0 + 0.85, y0 + 0.30, y0 + 0.25 + 2.05, zw + s * 0.004, s)
                wx0 = dx0 + 0.95
                wx1 = min(wx0 + 1.25, xb - 0.1)
                if wx1 - wx0 > 0.4:
                    quad_z("Frame", wx0 - 0.05, wx1 + 0.05, y0 + 0.95, y0 + 0.95 + 1.45, zw, s)
                    quad_z("Glass", wx0, wx1, y0 + 1.0, y0 + 1.0 + 1.35, zw + s * 0.004, s)

# --------------------------------------------------------------------------------------------- Erdgeschoss
# geschlossener Teil (NNE), 0,5 m eingerückt
box("EGWall", -14.06, LX - 0.3, 0.0, Y_EG, -LZ + 0.5, LZ - 0.5)
# Decke über dem offenen Durchgang (kassettiert angedeutet)
box("Ceiling", -LX, -14.06, Y_EG - 0.35, Y_EG, -LZ, LZ)
for k in range(6):
    xk = -LX + 0.6 + k * 2.1
    box("Sockel", xk, xk + 0.18, Y_EG - 0.6, Y_EG - 0.35, -LZ + 0.4, LZ - 0.4)
# 6 trapezförmige Stelzen
for xs in (-25.73, -20.76, -15.80):
    for zs in (-4.81, 4.81):
        bm = bm_of("Stilt")
        hb, ht = 1.0, 1.4
        vs = []
        for xx in (xs - 0.23, xs + 0.23):
            for (yy, hh) in ((0.0, hb), (Y_EG - 0.35, ht)):
                for zz in (zs - hh, zs + hh):
                    vs.append(bm.verts.new(V(xx, yy, zz)))
        # Index wie box(): x*4 + y*2 + z (Flächen nach außen)
        for q in [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]:
            bm.faces.new([vs[i] for i in q])

# --------------------------------------------------------------------------------------------- Dachaufbau (Flügeldach-Rest)
RX0, RX1 = -17.37, 1.85
RZ0, RZ1 = -6.67, 6.81
# zurückgesetzte Wand mit Graffiti-Pieces
box("GraffWall", RX0 + 1.5, RX1 - 1.5, Y_ROOF, 47.5, RZ0 + 1.5, RZ1 - 1.5)
for k in range(7):
    m = ("GraffViolet", "GraffMagenta", "GraffWhite")[k % 3]
    xa = rng.uniform(RX0 + 1.7, RX1 - 4.0)
    quad_z(m, xa, xa + rng.uniform(1.0, 2.6), 44.6 + rng.uniform(0, 0.6), 45.6 + rng.uniform(0, 1.2), RZ0 + 1.5 - 0.01, -1)
# Querrahmen (Stützen + Riegel)
for k in range(5):
    xr = RX0 + 0.3 + k * (RX1 - RX0 - 0.6) / 4
    for zz in (RZ0 + 0.2, RZ1 - 0.5):
        box("RoofConcrete", xr - 0.15, xr + 0.15, Y_ROOF, 47.9, zz, zz + 0.3)
    box("RoofConcrete", xr - 0.15, xr + 0.15, 47.55, 47.9, RZ0 + 0.2, RZ1 - 0.2)
# V-förmige Platte (Außenkanten 48,30, Kehle 47,90), offenes Rahmenfeld am SSW-Ende
def slab(x0, x1, z0, y0, z1, y1, th=0.35):
    bm = bm_of("RoofPlate")
    bu = bm_of("RoofUnder")
    # Reihenfolge (x0,z0)->(x1,z0)->(x1,z1)->(x0,z1): bei z1 > z0 zeigt die Normale nach unten -> umdrehen
    top = [bm.verts.new(V(x, y, z)) for (x, y, z) in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1))]
    bm.faces.new(list(reversed(top)) if z1 > z0 else top)
    bot = [bu.verts.new(V(x, y - th, z)) for (x, y, z) in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1))]
    bu.faces.new(bot if z1 > z0 else list(reversed(bot)))


for (xa, xb) in ((RX0 + 3.0, RX1), (RX0, RX0 + 0.5)):
    slab(xa, xb, RZ0, 48.30, 0.0, 47.90)
    slab(xa, xb, RZ1, 48.30, 0.0, 47.90)
box("RoofConcrete", RX0, RX1, 47.95, 48.32, RZ0 - 0.05, RZ0 + 0.25)
box("RoofConcrete", RX0, RX1, 47.95, 48.32, RZ1 - 0.25, RZ1 + 0.05)

# --------------------------------------------------------------------------------------------- Flachbau (Discounter) vor der WNW-Seite
FX0, FX1 = -14.1, 40.3
FZ0, FZ1 = -42.6, -LZ
box("ShopWhite", FX0, FX1, 0.0, 5.1, FZ0, FZ1)
box("ShopRoof", FX0 + 0.3, FX1 - 0.3, 5.1, 5.14, FZ0 + 0.3, FZ1 - 0.3)
quad_z("ShopGlass", FX0 + 2.0, FX1 - 2.0, 0.3, 3.4, FZ0 - 0.01, -1)
quad_x("ShopGlass", FZ0 + 2.0, FZ1 - 2.0, 0.3, 3.4, FX0 - 0.01, -1)
box("ShopSign", 8.0, 16.0, 3.8, 4.8, FZ0 - 0.15, FZ0 - 0.02)

# --------------------------------------------------------------------------------------------- Graffito-Fläche
img = bpy.data.images.load(GRAFFITI)
gm = bpy.data.materials.new("Graffiti")
gm.use_nodes = True
nt = gm.node_tree
bsdf = nt.nodes["Principled BSDF"]
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
# Alpha über "Greater Than 0.5" -> glTF alphaMode MASK (Alpha-Scissor in Godot, schreibt Tiefe)
cmp = nt.nodes.new("ShaderNodeMath")
cmp.operation = "GREATER_THAN"
cmp.inputs[1].default_value = 0.5
nt.links.new(tex.outputs["Alpha"], cmp.inputs[0])
nt.links.new(cmp.outputs[0], bsdf.inputs["Alpha"])
bsdf.inputs["Roughness"].default_value = 0.92
MATS["Graffiti"] = gm
bm = bm_of("Graffiti")
X0, X1, GY0, GY1 = 25.8, -14.0, 43.20, 45.02
zq = -LZ - 0.012
# Vorderseite nach −Z (Betrachter auf dem Platz); u = 0 links (bei X0)
vs = [bm.verts.new(V(X0, GY1, zq)), bm.verts.new(V(X0, GY0, zq)), bm.verts.new(V(X1, GY0, zq)), bm.verts.new(V(X1, GY1, zq))]
f = bm.faces.new(vs)
uv = bm.loops.layers.uv.new("UVMap")
for lp, (uu, vv) in zip(f.loops, ((0, 1), (0, 0), (1, 0), (1, 1))):
    lp[uv].uv = (uu, vv)
f.normal_update()
if f.normal.dot(V(0, 0, -1)) < 0:
    f.normal_flip()

# --------------------------------------------------------------------------------------------- Objekte erzeugen
root = bpy.data.objects.new("Hochhaus_PirnaischerPlatz", None)
bpy.context.collection.objects.link(root)
for name, bmx in BMS.items():
    me = bpy.data.meshes.new(name)
    bmx.to_mesh(me)
    bmx.free()
    me.materials.append(MATS[name])
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.parent = root
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_apply=True)
print("EXPORT", OUT, "Teile", len(BMS))
