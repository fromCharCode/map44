"""Fußgänger-Figuren für die Stadt (Blender 5.x, headless):

    flatpak run org.blender.Blender -b --python "<absoluter Pfad>/tools/blender/peds_build.py"
    ... -- ped_frau1 ped_senior        nur einzelne Figuren neu bauen

Erzeugt godot/assets/models/peds/ped_<name>.glb: je Figur EIN Mesh mit EINER Oberfläche, eine Armatur mit
20 Knochen (Namen wie bei den alten Figuren ped_m/ped_f/ped_k) und die Animationen Walk, Run, Idle, Talk,
Look (vor dem Queren nach links/rechts schauen) und Phone.

Farben stecken NICHT im Modell: Jede Fläche trägt in der UV-Koordinate nur ihre Teilnummer und eine Helligkeit
    u = (Teil + 0,5) / 8      Teil: 0 Haut, 1 Haar, 2 Oberteil, 3 Hose/Rock, 4 Schuhe, 5 Zubehör, 6 neutral, 7 Zweitfarbe
    v = Helligkeit (0,5 = Grundfarbe, darunter dunkler, darüber heller)
Der Shader in godot/scripts/peds.gd setzt daraus je Figur Haut-, Haar- und Kleidungsfarben ein (Instanz-Uniforms):
wenige Modelle ergeben so viele verschiedene Menschen, und jede Figur kostet nur einen Zeichenaufruf.

Die Geh-Animation wird gerechnet (Beine über Zwei-Knochen-IK aus einer Fußbahn, die im Stand am Boden haftet):
bei der Gangart-Geschwindigkeit Schrittlänge / Dauer gleiten die Füße nicht. Die Tabelle am Ende der Ausgabe
(Schrittlängen je Figur) gehört in peds.gd (Konstante MODELS).

Konventionen: Blender Z-up, Meter, Ursprung zwischen den Füßen am Boden, Blick +Y (= Godot -Z), links = -X.
"""
import bpy
import math
import os
import sys
from mathutils import Vector, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "godot", "assets", "models", "peds")
os.makedirs(OUT, exist_ok=True)

TAU = 2.0 * math.pi
FPS = 30
SKIN, HAIR, TOP, BOTTOM, SHOES, ACC, NEUT, TOP2 = range(8)
V = Vector


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------------ Geometrie-Sammler
class Soup:
    """Sammelt Punkte (mit Knochengewichten) und Flächen (mit Teilnummer und Helligkeit)."""

    def __init__(self):
        self.v = []
        self.w = []
        self.f = []

    def vert(self, co, w):
        self.v.append(V(co))
        self.w.append(w)
        return len(self.v) - 1

    def face(self, idx, part, shade, ref=None, out=None, flat=False):
        """Fläche mit nach außen zeigender Normale: weg vom Bezugspunkt ref bzw. entlang out."""
        pts = [self.v[i] for i in idx]
        n = V((0.0, 0.0, 0.0))
        for i in range(len(pts)):                      # Newell: auch bei leicht windschiefen Vierecken stabil
            a = pts[i]
            b = pts[(i + 1) % len(pts)]
            n += V(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        if n.length < 1e-10:
            return
        ctr = sum(pts, V((0.0, 0.0, 0.0))) / len(pts)
        d = out if out is not None else ctr - ref
        if n.dot(d) < 0.0:
            idx = tuple(reversed(idx))
        self.f.append((tuple(idx), part, shade, flat))

    def tris(self):
        return sum(len(f[0]) - 2 for f in self.f)


def loft(S, rings, segs, part, wfn, shade=0.5, axis="z", cap0=True, cap1=True, arc=None, sq=2.0):
    """Schlauch aus Ellipsenringen. rings: (cx, cy, cz, ra, rb[, rb_hinten]); axis "z": Ringe waagerecht,
    "y": Ringe in der XZ-Ebene (Schuhe). arc=(w0, w1): nur ein Winkelausschnitt (offene Bahn).
    wfn(k, co) liefert die Knochengewichte."""
    rows = []
    n = segs if arc is None else segs + 1
    for k, r in enumerate(rings):
        cx, cy, cz, ra, rb = r[:5]
        rbb = r[5] if len(r) > 5 else rb
        row = []
        for j in range(n):
            th = TAU * j / segs if arc is None else arc[0] + (arc[1] - arc[0]) * j / segs
            c = math.cos(th)
            s = math.sin(th)
            if sq != 2.0:
                c = math.copysign(abs(c) ** (2.0 / sq), c)
                s = math.copysign(abs(s) ** (2.0 / sq), s)
            b = rb if s >= 0.0 else rbb
            co = (cx + ra * c, cy + b * s, cz) if axis == "z" else (cx + ra * c, cy, cz + b * s)
            row.append(S.vert(co, wfn(k, V(co))))
        rows.append(row)
    for k in range(len(rings) - 1):
        ref = (V(rings[k][:3]) + V(rings[k + 1][:3])) * 0.5
        for j in range(segs):
            j2 = (j + 1) % n if arc is None else j + 1
            S.face((rows[k][j], rows[k][j2], rows[k + 1][j2], rows[k + 1][j]), part, shade, ref=ref)
    if arc is None:
        for cap, k, kn in ((cap0, 0, 1), (cap1, len(rings) - 1, len(rings) - 2)):
            if not cap:
                continue
            c = V(rings[k][:3])
            ci = S.vert(c, wfn(k, c))
            inner = V(rings[kn][:3])
            for j in range(segs):
                S.face((rows[k][j], rows[k][(j + 1) % segs], ci), part, shade, ref=inner)
    return rows


def ellipsoid(S, c, r, part, w, shade=0.5, nu=8, nv=6, fn=None, keep=None, sq=1.0, wfn=None, shade_fn=None):
    """Ellipsoid (Längen-/Breitenkreise). fn(d) -> Punkt ersetzt die Ellipsoidformel (Kopf, Haar),
    keep(d) wählt Flächen aus (offene Schalen), sq < 1 macht die Form kastiger."""
    c = V(c)
    grid = []
    for iv in range(nv + 1):
        phi = math.pi * iv / nv
        row = []
        for iu in range(nu):
            th = TAU * iu / nu
            d = V((math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi)))
            if fn is not None:
                co = fn(d)
            else:
                e = d
                if sq != 1.0:
                    e = V([math.copysign(abs(x) ** sq, x) for x in d])
                co = c + V((r[0] * e.x, r[1] * e.y, r[2] * e.z))
            row.append((S.vert(co, wfn(co) if wfn else w), d))
            if iv in (0, nv):
                row = row * nu
                break
        grid.append(row)
    for iv in range(nv):
        for iu in range(nu):
            a = grid[iv][iu]
            b = grid[iv][(iu + 1) % nu]
            cc = grid[iv + 1][(iu + 1) % nu]
            dd = grid[iv + 1][iu]
            quad = [a, b, cc, dd]
            if iv == 0:
                quad = [a, cc, dd]
            elif iv == nv - 1:
                quad = [a, b, cc]
            if keep is not None and not all(keep(q[1]) for q in quad):
                continue
            ctr = sum((S.v[q[0]] for q in quad), V((0, 0, 0))) / len(quad)
            dm = sum((q[1] for q in quad), V((0, 0, 0)))
            sh = shade_fn(ctr) if shade_fn else shade
            S.face(tuple(q[0] for q in quad), part, sh, out=dm if fn is not None else None, ref=c)


def box(S, c, half, part, w, shade=0.5, top=1.0):
    """Kantiger Kasten (flach schattiert); top: Breitenfaktor der Oberseite in y (Tüten laufen oben zusammen)."""
    c = V(c)
    idx = []
    for sz in (-1, 1):
        for sy in (-1, 1):
            for sx in (-1, 1):
                f = top if sz > 0 else 1.0
                idx.append(S.vert(c + V((sx * half[0] * (0.6 + 0.4 * f), sy * half[1] * f, sz * half[2])), w))
    for q in ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)):
        S.face(tuple(idx[i] for i in q), part, shade, ref=c, flat=True)


def strip(S, pts, nrm, width, part, wfn, shade=0.5, lift=0.004):
    """Flaches Band entlang einer Punktfolge auf einer Oberfläche (Gurte, Reißverschluss)."""
    rows = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        side = nrm[i].cross(t)
        if side.length < 1e-6:
            side = V((1, 0, 0))
        side = side.normalized() * (width * 0.5)
        q = p + nrm[i] * lift
        rows.append((S.vert(q - side, wfn(q)), S.vert(q + side, wfn(q))))
    for i in range(len(pts) - 1):
        S.face((rows[i][0], rows[i][1], rows[i + 1][1], rows[i + 1][0]), part, shade, out=nrm[i] + nrm[i + 1])


def wblend(z, nodes):
    """Stückweise lineare Gewichte entlang der Höhe: nodes = [(z, Knochen), ...] absteigend oder aufsteigend."""
    ns = sorted(nodes, key=lambda n: n[0])
    if z <= ns[0][0]:
        return {ns[0][1]: 1.0}
    for a, b in zip(ns, ns[1:]):
        if z <= b[0]:
            if a[1] == b[1]:
                return {a[1]: 1.0}
            t = (z - a[0]) / max(b[0] - a[0], 1e-6)
            return {a[1]: 1.0 - t, b[1]: t}
    return {ns[-1][1]: 1.0}


# ------------------------------------------------------------------ Figur
class Figure:
    def __init__(self, spec):
        self.spec = spec
        self.name = spec["name"]
        self.sex = spec["sex"]
        self.kind = spec["kind"]
        H = spec["H"]
        self.H = H
        kid = self.kind == "k"
        self.k = H / 1.76                      # Maßstab der Längen
        b = spec.get("build", 1.0)
        fem = self.sex == "f"
        self.kw = self.k * b * (0.93 if fem else 1.0) * (0.92 if kid else 1.0)     # Maßstab der Breiten
        self.hh = H / (6.3 if kid else 7.5)    # Kopfhöhe Kinn–Scheitel
        self.zChin = H - self.hh
        self.zAnk = 0.045 * H
        self.zKnee = (0.270 if kid else 0.285) * H
        self.zHipJ = (0.505 if kid else 0.527) * H
        self.zHips = self.zHipJ + 0.03 * H
        self.zN = self.zChin - 0.022 * H
        self.zSh = self.zN - 0.028 * H
        sp = self.zN - self.zHips
        self.zS1 = self.zHips + 0.16 * sp
        self.zS2 = self.zHips + 0.38 * sp
        self.zC = self.zHips + 0.60 * sp
        self.zHd = self.zChin + 0.12 * self.hh
        self.zBelt = self.zHips + 0.035 * H
        self.shx = (0.089 if fem else 0.099) * H * (0.95 if kid else 1.0) * (0.5 + 0.5 * b)
        self.hx = (0.050 if fem else 0.049) * H
        ua = 0.180 * H
        fa = 0.146 * H
        hd = 0.098 * H
        self.zEl = self.zSh - ua
        self.zWr = self.zEl - fa
        self.zHe = self.zWr - hd
        self.xEl = self.shx + 0.017 * self.k
        self.xWr = self.shx + 0.024 * self.k
        self.yWr = 0.022 * self.k
        self.L1 = self.zHipJ - self.zKnee
        self.L2 = self.zKnee - self.zAnk
        # Kopf
        s = self.hh / 0.235
        self.hrx = 0.0765 * s
        self.jaw = 0.27
        self.hry = 0.096 * s
        self.hrz = self.hh * 0.5
        self.hc = V((0.0, 0.012 * s, H - self.hrz))
        self.S = Soup()
        self.dr = {"tshirt": 0.003, "pulli": 0.009, "hoodie": 0.013, "jacke": 0.016, "mantel": 0.019,
                   "kleid": 0.004}[spec["top"]] * self.k
        self._torso_table()

    # --- Rumpf ---
    def _torso_table(self):
        H = self.H
        kw = self.kw
        fem = self.sex == "f"
        belly = self.spec.get("belly", 0.0)
        if fem:
            t = [(self.zHipJ - 0.045 * H, .132, .096, .108), (self.zHipJ, .172, .106, .122), (self.zBelt, .158, .104, .108),
                 (0.630 * H, .132, .100, .094), (0.685 * H, .142, .112, .100), (0.735 * H, .153, .130, .104),
                 (0.775 * H, .155, .112, .106), (self.zSh, .147, .090, .096), (self.zSh + 0.019 * H, .100, .070, .080),
                 (self.zN + 0.004 * H, .062, .054, .060)]
        else:
            t = [(self.zHipJ - 0.045 * H, .132, .094, .104), (self.zHipJ, .166, .104, .116), (self.zBelt, .160, .108, .104),
                 (0.625 * H, .150, .110, .098), (0.685 * H, .160, .113, .106), (0.740 * H, .174, .119, .112),
                 (0.785 * H, .176, .109, .112), (self.zSh, .168, .092, .100), (self.zSh + 0.020 * H, .116, .074, .084),
                 (self.zN + 0.004 * H, .072, .060, .066)]
        if self.kind == "k":                       # Kinder: Rumpfhöhen auf die kürzeren Beine umrechnen
            f0 = 0.527 * H
            t = [(z if i < 3 or i >= 7 else self.zBelt + (z - (0.527 + 0.065) * H) / ((0.815 - 0.592) * H) * (self.zSh - self.zBelt),
                  a, bb, c) for i, (z, a, bb, c) in enumerate(t)]
        res = []
        for i, (z, rx, rf, rb) in enumerate(t):
            add = belly * (1.0 if 2 <= i <= 4 else 0.4 if i in (1, 5) else 0.0)
            res.append((z, rx * kw + add * 0.4, rf * kw + add, rb * kw))
        self.torso = res

    def torso_at(self, z):
        t = self.torso
        if z <= t[0][0]:
            return t[0][1:]
        for a, b in zip(t, t[1:]):
            if z <= b[0]:
                u = (z - a[0]) / (b[0] - a[0])
                return tuple(lerp(a[i], b[i], u) for i in (1, 2, 3))
        return t[-1][1:]

    def torso_pt(self, z, th, extra=0.0):
        """Punkt und Außennormale auf dem Rumpf in Höhe z, Winkel th (0 = +X/rechts, 90° = vorn)."""
        rx, rf, rb = self.torso_at(z)
        c = math.cos(th)
        s = math.sin(th)
        ry = rf if s >= 0 else rb
        n = V((c / max(rx, 1e-4), s / max(ry, 1e-4), 0.0)).normalized()
        return V(((rx + extra) * c, (ry + extra) * s, z)), n

    def w_torso(self, co):
        z = co.z
        return wblend(z, [(self.zHips, "Hips"), ((self.zS1 + self.zS2) * 0.5, "Spine1"), ((self.zS2 + self.zC) * 0.5, "Spine2"),
                          (self.zC + 0.03 * self.H, "Chest"), (self.zN - 0.005, "Chest"), (self.zN + 0.03 * self.H, "Neck")])

    def w_skirt(self, co):
        """Rock/Mantelschoß: oben an der Hüfte, nach unten zunehmend an den Oberschenkeln (links/rechts weich)."""
        if co.z >= self.zHipJ + 0.02:
            return self.w_torso(co)
        t = min(max((self.zHipJ + 0.02 - co.z) / max(self.zHipJ - self.zKnee, 1e-3), 0.0), 1.0)
        leg = 0.85 * t ** 0.7
        r = smooth((co.x + self.hx * 1.2) / (self.hx * 2.4))
        w = {"Hips": 1.0 - leg, "UpperLeg_R": leg * r, "UpperLeg_L": leg * (1.0 - r)}
        return {k: v for k, v in w.items() if v > 0.01}

    def build_torso(self):
        S = self.S
        sp = self.spec
        top = sp["top"]
        dr = self.dr
        H = self.H
        k = self.k
        seg = 16
        t = self.torso
        # Becken (Hosenfarbe; bei Kleid/Rock darunter verdeckt)
        pel = [(0, 0, z, rx, rf, rb) for (z, rx, rf, rb) in t[:3]]
        pelpart = BOTTOM
        loft(S, pel, seg, pelpart, lambda i, co: self.w_torso(co), cap0=True, cap1=False)
        # Oberkörper
        up = []
        hem = {"tshirt": -0.012, "pulli": -0.030, "hoodie": -0.040, "jacke": -0.045, "mantel": -0.20, "kleid": 0.0}[top] * H
        z_hem = self.zBelt + hem
        if top == "mantel":
            z_hem = max(z_hem, self.zKnee + 0.06 * H) if not sp.get("langmantel") else self.zKnee + 0.015 * H
        if top != "kleid":
            # Saum: leicht ausgestellt, liegt über dem Becken/den Oberschenkeln
            zs = [z_hem]
            zz = z_hem
            while zz + 0.07 * H < self.zBelt:
                zz += 0.07 * H
                zs.append(zz)
            for z in zs:
                rx, rf, rb = self.torso_at(max(z, t[0][0]))
                if z < self.zHipJ:                 # unter der Hüfte: Breite der Hüfte halten, leicht A-förmig
                    rx, rf, rb = self.torso_at(self.zHipJ)
                    fl = (self.zHipJ - z) * 0.10
                    rx += fl
                    rf += fl * 0.6
                    rb += fl * 0.6
                e = dr + 0.006 * k
                up.append((0, 0, z, rx + e, rf + e, rb + e))
        for (z, rx, rf, rb) in t[2:]:
            e = dr * (1.0 if z < self.zSh + 0.01 else 0.5)
            up.append((0, 0, z, rx + e, rf + e, rb + e))
        self.z_hem = z_hem
        wf = (lambda i, co: self.w_skirt(co)) if top in ("mantel",) else (lambda i, co: self.w_torso(co))
        loft(S, up, seg, TOP, wf, cap0=False, cap1=True)
        if top in ("jacke", "mantel", "hoodie"):
            # offene Jacke: Streifen vorn in der Zweitfarbe (Hemd/Pullover darunter) + Kragen
            z = max(z_hem + 0.01, self.zHipJ - 0.02) if top != "hoodie" else self.zN - 0.10 * H
            ztop = self.zN - (0.026 if top != "hoodie" else 0.02) * H
            n = 7
            for dth in ((0.0,) if top != "hoodie" else (-0.16, 0.16)):
                pts = []
                nr = []
                for i in range(n + 1):
                    zz = lerp(z, ztop, i / n)
                    p, nn = self.torso_pt(zz, math.pi / 2 + dth, dr * (1.0 if zz < self.zSh else 0.5) + 0.002)
                    pts.append(p)
                    nr.append(nn)
                if top != "hoodie":
                    strip(S, pts, nr, 0.050 * k, TOP2, lambda co: self.w_torso(co), lift=0.003)
                else:
                    strip(S, pts, nr, 0.007 * k, NEUT, lambda co: self.w_torso(co), shade=0.85, lift=0.003)   # Kordeln
            if top != "hoodie":
                # Kragen: Wulst um den Hals
                zc = self.zN + 0.004 * H
                rx, rf, rb = self.torso_at(self.zN + 0.004 * H)
                col = [(0, 0, zc - 0.012 * k, rx + 0.022 * k, rf + 0.018 * k, rb + 0.024 * k),
                       (0, 0, zc + 0.022 * k, rx + 0.016 * k, rf + 0.004 * k, rb + 0.020 * k),
                       (0, 0, zc + 0.028 * k, rx + 0.004 * k, rf - 0.004 * k, rb + 0.008 * k)]
                loft(S, col, 12, TOP, lambda i, co: {"Chest": 0.6, "Neck": 0.4}, shade=0.42, cap0=False, cap1=False)
        if top == "hoodie":
            # Kapuze im Nacken
            ellipsoid(S, (0, -0.085 * k, self.zN + 0.005 * H), (0.105 * k, 0.065 * k, 0.085 * k), TOP, {"Chest": 0.7, "Neck": 0.3},
                      shade=0.46, nu=10, nv=6)
        if top == "pulli":
            # Bündchen am Saum
            rx, rf, rb = up[0][3:6]
            loft(S, [(0, 0, z_hem - 0.004, rx + 0.004, rf + 0.004, rb + 0.004), (0, 0, z_hem + 0.03 * k, rx + 0.006, rf + 0.006, rb + 0.006)],
                 seg, TOP, lambda i, co: self.w_torso(co), shade=0.43, cap0=False, cap1=False)
        if sp.get("guertel") and top in ("tshirt",):
            rx, rf, rb = self.torso_at(self.zBelt)
            loft(S, [(0, 0, self.zBelt - 0.022 * k, rx + 0.004, rf + 0.004, rb + 0.004), (0, 0, self.zBelt + 0.012 * k, rx + 0.005, rf + 0.005, rb + 0.005)],
                 seg, NEUT, lambda i, co: self.w_torso(co), shade=0.12, cap0=False, cap1=False)
        # Rock/Kleid
        bottom = sp["bottom"]
        if bottom in ("rock", "kleid"):
            z0 = self.zBelt + 0.01 * H
            z1 = self.zKnee + sp.get("rock_len", 0.035) * H
            flare = sp.get("rock_weite", 0.25)
            rings = []
            n = 5
            for i in range(n + 1):
                u = i / n
                z = lerp(z0, z1, u)
                rx, rf, rb = self.torso_at(max(z, self.zHipJ) if z < self.zHipJ else z)
                e = 0.012 * k + (self.zHipJ - z) * flare if z < self.zHipJ else 0.010 * k
                if top == "kleid":
                    e += 0.002
                rings.append((0, 0, z, rx + e, rf + e * 0.8, rb + e * 0.8))
            loft(S, list(reversed(rings)), seg, TOP if bottom == "kleid" else BOTTOM, lambda i, co: self.w_skirt(co),
                 cap0=False, cap1=False)

    # --- Beine und Schuhe ---
    def build_legs(self):
        S = self.S
        sp = self.spec
        H = self.H
        k = self.k
        kw = self.kw
        bottom = sp["bottom"]
        fem = self.sex == "f"
        f = 0.96 if fem else 1.0
        base = [(self.zHipJ + 0.035 * H, .080, 0.0), (self.zHipJ - 0.04 * H, .084 * (1.04 if fem else 1.0), 0.0), (0.40 * H, .071, 0.0),
                (self.zKnee + 0.025 * H, .058, 0.004), (self.zKnee - 0.02 * H, .053, 0.002), (0.205 * H, .056, -0.010),
                (0.115 * H, .042, -0.004), (self.zAnk + 0.012 * H, .036, 0.0)]
        if self.kind == "k":
            base[2] = ((self.zHipJ + self.zKnee) * 0.5, .071, 0.0)
        for side, sx in (("L", -1.0), ("R", 1.0)):
            x = sx * self.hx
            nodes = [(self.zHipJ + 0.05 * H, "Hips"), (self.zHipJ - 0.035 * H, "UpperLeg_" + side), (self.zKnee + 0.05 * H, "UpperLeg_" + side),
                     (self.zKnee - 0.05 * H, "LowerLeg_" + side), (self.zAnk + 0.04 * H, "LowerLeg_" + side), (self.zAnk - 0.01, "Foot_" + side)]
            wf = lambda i, co, nodes=nodes: wblend(co.z, nodes)
            skin_part = TOP2 if sp.get("strumpf") else SKIN
            skin_shade = 0.5
            if bottom == "hose":
                eng = sp.get("hose_eng", False)
                rings = []
                for i, (z, r, cy) in enumerate(base):
                    rr = r * f * kw + (0.004 if eng else 0.008) * k
                    if not eng and i >= 3:
                        rr = max(rr, lerp(0.068, 0.060, (i - 3) / 4.0) * kw)
                    if i == len(base) - 1:
                        z = self.zAnk + 0.005 * H
                    rings.append((x, cy * k, z, rr, rr * 1.04))
                loft(S, rings, 12, BOTTOM, wf, cap0=True, cap1=True)
            elif bottom == "shorts":
                zc = self.zKnee + 0.05 * H
                rings = [(x, cy * k, z, r * f * kw + 0.012 * k, r * f * kw + 0.014 * k) for (z, r, cy) in base[:3]]
                rings.append((x, 0.002, zc, 0.074 * kw, 0.078 * kw))
                loft(S, rings, 12, BOTTOM, wf, cap0=True, cap1=True)
                rings = [(x, 0.002, zc + 0.02 * H, 0.060 * f * kw, 0.060 * f * kw)] + [(x, cy * k, z, r * f * kw, r * f * kw * 1.04) for (z, r, cy) in base[3:]]
                loft(S, rings, 12, SKIN, wf, cap0=True, cap1=True)
            else:                                    # Rock/Kleid: ganze Beine in Haut oder Strumpfhose
                rings = [(x, cy * k, z, r * f * kw, r * f * kw * 1.04) for (z, r, cy) in base]
                loft(S, rings, 12, skin_part, wf, shade=skin_shade, cap0=True, cap1=True)
            # Schuh (Längsschnitte von der Ferse zur Spitze)
            wsh = {"Foot_" + side: 1.0}
            hi = sp.get("stiefel", False)
            a = self.zAnk
            ks = self.k * (1.0 if not fem else 0.93)
            prof = [(-0.078, .030, .030, .034), (-0.055, .043, .050, .052), (-0.010, .049, .056, .058), (0.050, .052, .044, .046),
                    (0.105, .054, .034, .036), (0.150, .050, .027, .029), (0.185, .038, .020, .022), (0.202, .020, .012, .014)]
            rings = [(x, y * ks, cz * ks, rx * ks, rz * ks, cz * ks * 0.98) for (y, rx, rz, cz) in prof]
            loft(S, rings, 10, SHOES, lambda i, co: wsh, axis="y", cap0=True, cap1=True, sq=2.6)
            # Schaft bis über den Knöchel
            zt = a + (0.13 * H if hi else 0.028 * H)
            rr = 0.044 * ks
            sh = [(x, -0.012 * ks, 0.045 * ks, rr * 1.05, rr * 1.2), (x, -0.008 * ks, a + 0.005, rr, rr * 1.08), (x, -0.004 * ks, zt, rr * (1.12 if hi else 0.98), rr * (1.14 if hi else 1.0))]
            wn = [(self.zAnk + 0.04 * H, "LowerLeg_" + side), (self.zAnk - 0.005, "Foot_" + side)]
            loft(S, sh, 10, SHOES, lambda i, co, wn=wn: wblend(co.z, wn), cap0=False, cap1=True)
            # Sohle: dunkle Platte
            sole = [(x, y * ks, 0.006 * ks, rx * ks * 1.03, 0.007 * ks) for (y, rx, rz, cz) in prof[1:-1]]
            loft(S, sole, 8, NEUT, lambda i, co: wsh, shade=sp.get("sohle", 0.10), axis="y", cap0=True, cap1=True, sq=3.0)

    # --- Arme und Hände ---
    def build_arms(self):
        S = self.S
        sp = self.spec
        H = self.H
        k = self.k
        kw = self.kw
        fem = self.sex == "f"
        fa = (0.86 if fem else 1.0) * (0.9 if self.kind == "k" else 1.0)
        top = sp["top"]
        short = top in ("tshirt",) or sp.get("kurzarm", False)
        e = self.dr * 0.8 + 0.002
        for side, sx in (("L", -1.0), ("R", 1.0)):
            def cx(z):
                if z >= self.zEl:
                    u = (self.zSh - z) / (self.zSh - self.zEl)
                    return sx * lerp(self.shx, self.xEl, u), lerp(0.0, 0.004 * k, u)
                u = (self.zEl - z) / (self.zEl - self.zWr)
                return sx * lerp(self.xEl, self.xWr, u), lerp(0.004 * k, self.yWr, u)
            nodes = [(self.zSh + 0.05 * H, "Chest"), (self.zSh + 0.012 * H, "UpperArm_" + side), (self.zEl + 0.035 * H, "UpperArm_" + side),
                     (self.zEl - 0.035 * H, "LowerArm_" + side), (self.zWr + 0.025 * H, "LowerArm_" + side), (self.zWr - 0.012 * H, "Hand_" + side)]
            wf = lambda i, co, nodes=nodes: wblend(co.z, nodes)
            prof = [(self.zSh + 0.015 * H, .018), (self.zSh + 0.009 * H, .036), (self.zSh - 0.006 * H, .047), (self.zSh - 0.03 * H, .049), ((self.zSh + self.zEl) * 0.5, .045),
                    (self.zEl + 0.01 * H, .039), (self.zEl - 0.03 * H, .041), ((self.zEl + self.zWr) * 0.5, .036), (self.zWr + 0.008 * H, .028)]
            def ring(z, r, add):
                x, y = cx(min(z, self.zSh))
                rr = r * fa * kw + add
                return (x, y, z, rr, rr * 1.03)
            if short:
                zc = self.zSh - (0.085 if top == "tshirt" else 0.06) * H
                up = [ring(z, r, e) for (z, r) in prof if z > zc] + [ring(zc, .048, e + 0.003)]
                loft(S, up, 10, TOP, wf, cap0=True, cap1=True)
                lo = [ring(zc + 0.015 * H, .044, 0.0)] + [ring(z, r, 0.0) for (z, r) in prof if z < zc]
                loft(S, lo, 10, SKIN, wf, cap0=True, cap1=True)
            else:
                rings = [ring(z, r, e) for (z, r) in prof]
                z, r = prof[-1]
                rings[-1] = ring(z, r + 0.004, e)             # Ärmelsaum etwas weiter
                loft(S, rings, 10, TOP, wf, cap0=True, cap1=True)
            # Handgelenk und Hand (Fäustling mit Daumen nach vorn)
            hw = {"Hand_" + side: 1.0}
            xw, yw = cx(self.zWr)
            hk = fa * self.k
            wn = [(self.zWr + 0.02 * H, "LowerArm_" + side), (self.zWr - 0.012 * H, "Hand_" + side)]
            loft(S, [(xw, yw - 0.001, self.zWr + 0.022 * H, 0.026 * hk, 0.029 * hk), (xw, yw, self.zWr - 0.012 * H, 0.022 * hk, 0.031 * hk)], 8, SKIN,
                 lambda i, co, wn=wn: wblend(co.z, wn), cap0=True, cap1=True)
            hl = (self.zWr - self.zHe)
            hc = V((xw, yw + 0.004 * k, self.zWr - hl * 0.50))
            def hand(d, hc=hc, hk=hk, hl=hl):
                tz = (1.0 - d.z) * 0.5                 # 0 Handgelenk .. 1 Fingerspitzen
                wy = 0.043 * hk * (0.80 + 0.30 * math.sin(math.pi * min(tz * 1.2, 1.0)))
                ez = math.copysign(abs(d.z) ** 0.75, d.z)
                return hc + V((0.020 * hk * d.x * (1.0 - 0.25 * tz), wy * d.y + 0.012 * hk * tz * tz, hl * 0.50 * ez))
            ellipsoid(S, hc, None, SKIN, hw, nu=8, nv=6, fn=hand)
            ellipsoid(S, hc + V((-sx * 0.004 * hk, 0.040 * hk, hl * 0.10)), (0.012 * hk, 0.015 * hk, 0.034 * hk), SKIN, hw, nu=6, nv=4)

    # --- Kopf, Gesicht, Hals ---
    def head_pt(self, d, sc=1.0, drop=0.0):
        x = self.hrx * d.x
        y = self.hry * d.y
        z = self.hrz * d.z
        if d.z < 0.0:
            t = -d.z
            x *= 1.0 - self.jaw * t * t                 # Kiefer schmaler
            if d.y > 0.0:
                y *= 1.0 - 0.14 * t * t                 # Kinn leicht zurück
            else:
                y *= 1.0 - 0.42 * t * t                 # Hinterkopf läuft zum Nacken ein
        if d.y > 0.0:
            y *= 0.93                                   # Gesicht flacher als der Hinterkopf
        if d.z > 0.0:
            x *= 1.0 + 0.04 * (1.0 - d.z)               # Schädel oben etwas breiter
        return self.hc + V((x * sc, y * sc, z * sc - drop))

    def face_pt(self, x, z):
        """Punkt auf der Gesichtsfläche bei seitlichem Versatz x und Höhe z über Kopfmitte."""
        dz = min(max(z / self.hrz, -0.95), 0.95)
        jaw = 1.0 - self.jaw * dz * dz if dz < 0 else 1.0 + 0.04 * (1.0 - dz)
        dx = min(max(x / (self.hrx * jaw), -0.9), 0.9)
        dy = math.sqrt(max(1.0 - dx * dx - dz * dz, 0.0))
        d = V((dx, dy, dz))
        return self.head_pt(d), d

    def build_head(self):
        S = self.S
        sp = self.spec
        k = self.hh / 0.235
        hw = {"Head": 1.0}
        ellipsoid(S, self.hc, None, SKIN, hw, nu=18, nv=12, fn=lambda d: self.head_pt(d))
        # Hals
        rn = (0.050 if self.sex == "f" else 0.058) * self.kw * (0.9 if self.kind == "k" else 1.0)
        neck = [(0, -0.004, self.zN - 0.012 * self.H, rn * 1.25, rn * 1.15), (0, 0.0, self.zN + 0.012 * self.H, rn, rn),
                (0, 0.006 * k, self.zChin + 0.05 * self.hh, rn * 0.98, rn), (0, 0.008 * k, self.zChin + 0.30 * self.hh, rn * 0.98, rn)]
        nn = [(self.zN - 0.01, "Chest"), (self.zN + 0.015 * self.H, "Neck"), (self.zHd, "Neck"), (self.zHd + 0.03, "Head")]
        loft(S, neck, 10, SKIN, lambda i, co: wblend(co.z, nn), shade=0.46, cap0=False, cap1=False)
        # Ohren
        for sx in (-1.0, 1.0):
            ellipsoid(S, self.hc + V((sx * self.hrx * 0.99, -0.008 * k, -0.012 * k)), (0.010 * k, 0.016 * k, 0.030 * k), SKIN, hw, shade=0.45, nu=6, nv=4)
        # Nase
        p, d = self.face_pt(0.0, -0.022 * k)
        ellipsoid(S, p + V((0, 0.004 * k, 0.0)), (0.0125 * k, 0.017 * k, 0.027 * k), SKIN, hw, shade=0.47, nu=6, nv=5)
        # Augen: heller Augapfel, dunkle Iris, Braue
        for sx in (-1.0, 1.0):
            p, d = self.face_pt(sx * 0.031 * k, 0.010 * k)
            ellipsoid(S, p - d * 0.004 * k, (0.0150 * k, 0.0075 * k, 0.0085 * k), NEUT, hw, shade=0.86, nu=8, nv=4)
            ellipsoid(S, p - d * 0.0020 * k + V((0, 0.0, 0.0)), (0.0078 * k, 0.0070 * k, 0.0082 * k), NEUT, hw, shade=0.07, nu=6, nv=4)
            p2, d2 = self.face_pt(sx * 0.032 * k, 0.031 * k)
            ellipsoid(S, p2 - d2 * 0.002 * k, (0.0185 * k, 0.0060 * k, 0.0042 * k), HAIR, hw, shade=0.36, nu=6, nv=4)
        # Mund
        p, d = self.face_pt(0.0, -0.064 * k)
        ellipsoid(S, p - d * 0.0035 * k, (0.021 * k, 0.0065 * k, 0.0052 * k), SKIN, hw, shade=0.30, nu=8, nv=4)
        if sp.get("bart"):
            def keep(d):
                return d.z < -0.30 and d.y > -0.25 and not (d.z > -0.52 and abs(d.x) < 0.20 and d.y > 0)
            ellipsoid(S, self.hc, None, HAIR, hw, shade=0.44, nu=18, nv=14, fn=lambda d: self.head_pt(d, 1.035), keep=keep)
        if sp.get("brille"):
            for sx in (-1.0, 1.0):
                p, d = self.face_pt(sx * 0.031 * k, 0.010 * k)
                ring = [V((p.x + 0.020 * k * math.cos(TAU * i / 10), p.y + 0.008 * k, p.z + 0.015 * k * math.sin(TAU * i / 10))) for i in range(11)]
                strip(S, ring, [V((0, 1, 0))] * 11, 0.0045 * k, NEUT, lambda co: hw, shade=0.06, lift=0.0)
            p, d = self.face_pt(0.0, 0.012 * k)
            strip(S, [V((-0.012 * k, p.y + 0.002, p.z + 0.004 * k)), V((0.012 * k, p.y + 0.002, p.z + 0.004 * k))], [V((0, 1, 0))] * 2, 0.004 * k, NEUT, lambda co: hw, shade=0.06)
            for sx in (-1.0, 1.0):
                a = V((sx * 0.052 * k, self.hc.y + self.hry * 0.72, self.hc.z + 0.014 * k))
                b = V((sx * self.hrx * 1.02, self.hc.y - 0.005 * k, self.hc.z + 0.012 * k))
                strip(S, [a, b], [V((sx, 0, 0))] * 2, 0.004 * k, NEUT, lambda co: hw, shade=0.06, lift=0.002)

    # --- Haare und Kopfbedeckungen ---
    def build_hair(self):
        S = self.S
        sp = self.spec
        k = self.hh / 0.235
        hw = {"Head": 1.0}
        style = sp["hair"]
        hc = self.hc

        def shell(keep, sc=1.07, part=HAIR, shade=0.5, drop=0.0, nu=18, nv=14, sfn=None):
            ellipsoid(S, hc, None, part, hw, shade=shade, nu=nu, nv=nv, fn=lambda d: self.head_pt(d, sc, drop), keep=keep, shade_fn=sfn)

        def line(d, front, back, y0=0.05, y1=0.50):
            """Haaransatz: vorn bis front (dz), hinten/seitlich hinab bis back."""
            return d.z > lerp(back, front, smooth((d.y - y0) / (y1 - y0)))

        if style in ("kurz", "kurz2", "muetze", "kappe", "hut"):
            back = -0.42 if style != "kurz2" else -0.50
            sc = 1.06 if style != "kurz2" else 1.09
            shell(lambda d: line(d, 0.56, back), sc)
            if style == "kurz2":                        # voller Schopf vorn/oben
                ellipsoid(S, hc + V((0.01 * k, 0.025 * k, self.hrz * 0.86)), (self.hrx * 0.86, self.hry * 0.80, 0.036 * k), HAIR, hw, shade=0.54, nu=10, nv=5)
        elif style == "kranz":                          # Haarkranz (Glatze oben)
            shell(lambda d: d.y < 0.30 and -0.45 < d.z < 0.42, 1.05)
        elif style == "glatze":
            shell(lambda d: line(d, 0.72, -0.35), 1.02, shade=0.62)
        elif style in ("bob", "lang", "locken"):
            sc = {"bob": 1.11, "lang": 1.09, "locken": 1.17}[style]
            back = {"bob": -0.78, "lang": -0.70, "locken": -0.62}[style]
            shell(lambda d: line(d, 0.50, back, 0.20, 0.62) or (d.z > 0.30 and abs(d.x) > 0.55), sc, nu=20, nv=14)
            if style == "bob":                          # Pony
                shell(lambda d: d.y > 0.25 and d.z > 0.36, 1.12, shade=0.47)
            if style == "lang":                         # Haar fällt über Nacken und Schultern
                zt = hc.z - self.hrz * 0.55
                zb = self.zSh - 0.10 * self.H
                rings = []
                for i in range(5):
                    u = i / 4.0
                    z = lerp(zt, zb, u)
                    rings.append((0, hc.y - self.hry * lerp(0.48, 0.80, min(u * 2, 1.0)) - 0.01 * u, z, self.hrx * lerp(1.06, 0.92, u), self.hry * lerp(0.42, 0.26, u)))
                nn = [(zb, "Chest"), (self.zN, "Neck"), (self.zHd + 0.02, "Head")]
                loft(S, rings, 12, HAIR, lambda i, co: wblend(co.z, nn), shade=0.47, cap0=True, cap1=True)
            if style == "locken":
                ellipsoid(S, hc + V((0, -0.01 * k, 0.03 * k)), (self.hrx * 1.30, self.hry * 1.22, self.hrz * 1.02), HAIR, hw, shade=0.48, nu=12, nv=8,
                          keep=lambda d: d.z > -0.25 and not (d.y > 0.45 and d.z < 0.50))
        elif style in ("zopf", "dutt", "dutt_tief", "zoepfe"):
            shell(lambda d: line(d, 0.52, -0.50, 0.15, 0.55), 1.07)
            if style == "zopf":                         # Pferdeschwanz
                p0 = hc + V((0, -self.hry * 0.92, self.hrz * 0.30))
                rings = []
                for i in range(6):
                    u = i / 5.0
                    rings.append((0, p0.y - 0.05 * k * math.sin(u * 2.2) - 0.012 * k, p0.z - 0.26 * k * u, lerp(0.030, 0.014, u) * k * (1.3 if i == 1 else 1.0), lerp(0.030, 0.016, u) * k))
                loft(S, rings, 8, HAIR, lambda i, co: {"Head": 1.0} if i < 4 else {"Head": 0.6, "Neck": 0.4}, shade=0.46, cap0=True, cap1=True)
            elif style == "dutt":
                ellipsoid(S, hc + V((0, -self.hry * 0.62, self.hrz * 0.80)), (0.042 * k, 0.042 * k, 0.038 * k), HAIR, hw, shade=0.46, nu=8, nv=6)
            elif style == "dutt_tief":
                ellipsoid(S, hc + V((0, -self.hry * 1.00, -self.hrz * 0.12)), (0.045 * k, 0.036 * k, 0.040 * k), HAIR, hw, shade=0.46, nu=8, nv=6)
            else:                                       # zwei seitliche Zöpfe
                for sx in (-1.0, 1.0):
                    p0 = hc + V((sx * self.hrx * 0.98, -self.hry * 0.25, -self.hrz * 0.10))
                    rings = [(p0.x + sx * 0.012 * k * u, p0.y, p0.z - 0.20 * k * u, lerp(0.026, 0.013, u) * k, lerp(0.026, 0.013, u) * k) for u in (0.0, 0.25, 0.6, 1.0)]
                    loft(S, rings, 7, HAIR, lambda i, co: hw, shade=0.46, cap0=True, cap1=True)
        elif style == "kopftuch":
            shell(lambda d: not (d.y > 0.42 and -0.80 < d.z < 0.52 and abs(d.x) < 0.80), 1.10, part=ACC, nu=20, nv=14)
            rx, rf, rb = self.torso_at(self.zSh + 0.018 * self.H)
            zc = self.zChin
            rings = [(0, 0.0, self.zSh + 0.012 * self.H, rx * 0.86, rf * 1.12, rb * 1.08), (0, 0.004, self.zN + 0.01 * self.H, self.hrx * 1.22, self.hry * 0.92, self.hry * 1.0),
                     (0, hc.y - 0.012, zc + 0.02 * k, self.hrx * 1.06, self.hry * 0.86, self.hry * 0.98)]
            nn = [(self.zN - 0.02, "Chest"), (self.zN + 0.02, "Neck"), (self.zHd + 0.02, "Head")]
            loft(S, rings, 14, ACC, lambda i, co: wblend(co.z, nn), shade=0.46, cap0=False, cap1=False)
        # Kopfbedeckungen
        if style == "muetze":
            shell(lambda d: d.z > lerp(0.05, 0.40, smooth((d.y - 0.1) / 0.5)), 1.12, part=ACC, drop=-0.004)
            shell(lambda d: lerp(0.0, 0.34, smooth((d.y - 0.1) / 0.5)) < d.z < lerp(0.30, 0.62, smooth((d.y - 0.1) / 0.5)), 1.155, part=ACC, shade=0.42, drop=-0.004)
        elif style == "kappe":
            shell(lambda d: d.z > lerp(0.20, 0.46, smooth((d.y - 0.1) / 0.5)), 1.10, part=ACC)
            ellipsoid(S, hc + V((0, self.hry * 0.98, self.hrz * 0.47)), (0.072 * k, 0.072 * k, 0.007 * k), ACC, hw, shade=0.42, nu=10, nv=4)
        elif style == "hut":
            shell(lambda d: d.z > 0.36, 1.10, part=ACC)
            ellipsoid(S, hc + V((0, 0.0, self.hrz * 0.42)), (self.hrx * 1.75, self.hry * 1.55, 0.008 * k), ACC, hw, shade=0.44, nu=14, nv=4)
            shell(lambda d: 0.36 < d.z < 0.56, 1.115, part=NEUT, shade=0.10)

    # --- Zubehör ---
    def build_acc(self):
        S = self.S
        sp = self.spec
        H = self.H
        k = self.k
        for a in sp.get("acc", []):
            if a == "rucksack":
                rx, rf, rb = self.torso_at(self.zC)
                e = self.dr
                small = self.kind == "k"
                hz = (0.17 if not small else 0.15) * k
                c = V((0.0, -(rb + e) - 0.060 * k, self.zC - 0.005 * H if not small else self.zC - 0.02 * H))
                wb = {"Chest": 0.6, "Spine2": 0.4}
                ellipsoid(S, c, (0.135 * k, 0.078 * k, hz), ACC, wb, nu=10, nv=8, sq=0.55)
                ellipsoid(S, c + V((0, -0.062 * k, -0.05 * k)), (0.095 * k, 0.035 * k, 0.075 * k), ACC, wb, shade=0.42, nu=8, nv=6, sq=0.6)
                for sx in (-1.0, 1.0):            # Gurte: vorn über die Schulter bis unter die Achsel
                    pts = []
                    nr = []
                    for i in range(7):
                        u = i / 6.0
                        z = lerp(self.zC - 0.07 * H, self.zSh + 0.012 * H, u)
                        th = math.pi / 2 - sx * lerp(1.05, 0.62, u)
                        p, n = self.torso_pt(z, th, e + 0.003)
                        pts.append(p)
                        nr.append(n)
                    pts.append(V((sx * self.shx * 0.62, -0.02, self.zSh + 0.024 * H + e)))
                    nr.append(V((0, 0, 1)))
                    pts.append(V((sx * self.shx * 0.60, -(rb + e) - 0.01, self.zSh - 0.005 * H)))
                    nr.append(V((0, -0.5, 1)).normalized())
                    strip(S, pts, nr, 0.036 * k, ACC, lambda co: self.w_torso(co), shade=0.40)
            elif a == "umhaengetasche":
                rx, rf, rb = self.torso_at(self.zHipJ + 0.03 * H)
                e = self.dr + 0.004
                sx = 1.0
                c = V((sx * (rx + e + 0.035 * k), 0.01, self.zHipJ + 0.035 * H))
                wb = {"Hips": 0.7, "Spine1": 0.3}
                ellipsoid(S, c, (0.045 * k, 0.130 * k, 0.095 * k), ACC, wb, nu=8, nv=8, sq=0.55)
                ellipsoid(S, c + V((sx * 0.012 * k, 0, 0.045 * k)), (0.040 * k, 0.134 * k, 0.050 * k), ACC, wb, shade=0.42, nu=8, nv=6, sq=0.55)
                for sgn in (1.0, -1.0):            # Riemen diagonal über Brust und Rücken zur anderen Schulter
                    pts = []
                    nr = []
                    for i in range(9):
                        u = i / 8.0
                        z = lerp(self.zHipJ + 0.09 * H, self.zSh + 0.014 * H, u)
                        th = sgn * lerp(0.25, math.pi - 1.05, u ** 0.85)
                        p, n = self.torso_pt(z, th, e + 0.002)
                        pts.append(p)
                        nr.append(n)
                    pts.append(V((-self.shx * 0.55, 0.0, self.zSh + 0.026 * H + e)))
                    nr.append(V((0, 0, 1)))
                    strip(S, pts, nr, 0.030 * k, ACC, lambda co: self.w_torso(co), shade=0.40)
            elif a in ("tuete", "aktentasche", "handtasche"):
                sx = 1.0
                wh = {"Hand_R": 1.0}
                x = sx * (self.xWr + 0.012 * k)
                y = self.yWr
                if a == "tuete":
                    c = V((x + 0.01, y, self.zHe - 0.15 * k))
                    box(S, c, (0.055 * k, 0.150 * k, 0.175 * k), ACC, wh, shade=0.56, top=0.82)
                    for dy in (-0.05, 0.05):      # Henkel
                        strip(S, [V((x, y + dy * k * 1.2, c.z + 0.16 * k)), V((x, y + dy * k * 0.4, self.zHe + 0.035 * k))], [V((sx, 0, 0))] * 2, 0.008 * k, ACC, lambda co: wh, shade=0.45)
                elif a == "aktentasche":
                    c = V((x + 0.012, y, self.zHe - 0.115 * k))
                    box(S, c, (0.038 * k, 0.200 * k, 0.140 * k), ACC, wh, shade=0.42)
                    box(S, c + V((0.0, 0.0, 0.085 * k)), (0.041 * k, 0.203 * k, 0.050 * k), ACC, wh, shade=0.36)
                    strip(S, [V((x, y - 0.045 * k, c.z + 0.135 * k)), V((x, y, self.zHe + 0.03 * k)), V((x, y + 0.045 * k, c.z + 0.135 * k))], [V((sx, 0, 0))] * 3, 0.012 * k, NEUT, lambda co: wh, shade=0.10)
                else:
                    c = V((x + 0.012, y, self.zHe - 0.11 * k))
                    ellipsoid(S, c, (0.050 * k, 0.125 * k, 0.090 * k), ACC, wh, nu=8, nv=8, sq=0.5)
                    for dy in (-0.045, 0.045):
                        strip(S, [V((x, y + dy * k * 1.6, c.z + 0.085 * k)), V((x, y + dy * k * 0.3, self.zHe + 0.035 * k))], [V((sx, 0, 0))] * 2, 0.010 * k, ACC, lambda co: wh, shade=0.42)
            elif a == "schal":
                rn = (0.050 if self.sex == "f" else 0.058) * self.kw
                z = self.zN + 0.012 * H
                rings = [(0, 0.0, z - 0.028 * k, rn + 0.042 * k, rn + 0.036 * k, rn + 0.040 * k), (0, 0.002, z, rn + 0.040 * k, rn + 0.036 * k, rn + 0.040 * k),
                         (0, 0.004, z + 0.030 * k, rn + 0.026 * k, rn + 0.024 * k, rn + 0.030 * k), (0, 0.004, z + 0.040 * k, rn + 0.010 * k, rn + 0.010 * k, rn + 0.014 * k)]
                loft(S, rings, 12, ACC, lambda i, co: {"Neck": 0.5, "Chest": 0.5}, cap0=False, cap1=False)
                # loses Ende vorn
                pts = []
                nr = []
                for i in range(5):
                    zz = lerp(z - 0.02 * k, self.zC - 0.02 * H, i / 4.0)
                    p, n = self.torso_pt(zz, math.pi / 2 + 0.28, self.dr + 0.008)
                    pts.append(p)
                    nr.append(n)
                strip(S, pts, nr, 0.075 * k, ACC, lambda co: self.w_torso(co), shade=0.46, lift=0.006)

    # --- Mesh + Armatur ---
    def bones(self):
        H = self.H
        b = [("Hips", (0, 0, self.zHips), (0, 0, self.zS1), None),
             ("Spine1", (0, 0, self.zS1), (0, 0, self.zS2), "Hips"),
             ("Spine2", (0, 0, self.zS2), (0, 0, self.zC), "Spine1"),
             ("Chest", (0, 0, self.zC), (0, 0, self.zN), "Spine2"),
             ("Neck", (0, 0, self.zN), (0, 0, self.zHd), "Chest"),
             ("Head", (0, 0, self.zHd), (0, 0, H), "Neck")]
        for side, sx in (("L", -1.0), ("R", 1.0)):
            b += [("Shoulder_" + side, (sx * 0.02, 0, self.zSh + 0.02 * H), (sx * self.shx, 0, self.zSh), "Chest"),
                  ("UpperArm_" + side, (sx * self.shx, 0, self.zSh), (sx * self.xEl, 0.004 * self.k, self.zEl), "Shoulder_" + side),
                  ("LowerArm_" + side, (sx * self.xEl, 0.004 * self.k, self.zEl), (sx * self.xWr, self.yWr, self.zWr), "UpperArm_" + side),
                  ("Hand_" + side, (sx * self.xWr, self.yWr, self.zWr), (sx * self.xWr, self.yWr, self.zHe), "LowerArm_" + side),
                  ("UpperLeg_" + side, (sx * self.hx, 0, self.zHipJ), (sx * self.hx, 0, self.zKnee), "Hips"),
                  ("LowerLeg_" + side, (sx * self.hx, 0, self.zKnee), (sx * self.hx, 0, self.zAnk), "UpperLeg_" + side),
                  ("Foot_" + side, (sx * self.hx, 0, self.zAnk), (sx * self.hx, 0.15 * self.k, 0.02), "LowerLeg_" + side)]
        return b

    def build(self):
        self.build_torso()
        self.build_legs()
        self.build_arms()
        self.build_head()
        self.build_hair()
        self.build_acc()
        return self.S


def make_objects(fig):
    S = fig.S
    used = sorted({i for f in S.f for i in f[0]})
    remap = {o: n for n, o in enumerate(used)}
    verts = [S.v[i] for i in used]
    faces = [tuple(remap[i] for i in f[0]) for f in S.f]
    me = bpy.data.meshes.new(fig.name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for p, f in zip(me.polygons, S.f):
        p.use_smooth = not f[3]
        for li in p.loop_indices:
            uv.data[li].uv = ((f[1] + 0.5) / 8.0, f[2])
    me.update()
    mat = bpy.data.materials.get("Ped") or bpy.data.materials.new("Ped")
    me.materials.append(mat)
    ob = bpy.data.objects.new(fig.name, me)
    bpy.context.scene.collection.objects.link(ob)
    # Armatur
    ad = bpy.data.armatures.new("Armature")
    arm = bpy.data.objects.new("Armature", ad)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for name, head, tail, parent in fig.bones():
        eb = ad.edit_bones.new(name)
        eb.head = head
        eb.tail = tail
        eb.roll = 0.0
        if parent:
            eb.parent = ad.edit_bones[parent]
            eb.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    groups = {b[0]: ob.vertex_groups.new(name=b[0]) for b in fig.bones()}
    for n, o in enumerate(used):
        w = S.w[o]
        tot = sum(w.values())
        for bn, val in w.items():
            if val / tot > 0.005:
                groups[bn].add([n], val / tot, "REPLACE")
    ob.parent = arm
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return ob, arm


# ------------------------------------------------------------------ Animation
def rx(a):
    return Quaternion((1, 0, 0), a)


def ry(a):
    return Quaternion((0, 1, 0), a)


def rz(a):
    return Quaternion((0, 0, 1), a)


def rot2(a, y, z):
    return y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)


class Gait:
    """Fußbahn eines Schritts im Bodensystem; die Hüfte steht bei Phase ph an der Stelle S * ph."""

    def __init__(self, fig, S, f, a_hs, a_to, lift, drop):
        self.fig = fig
        self.S = S
        self.f = f
        self.a_hs = a_hs
        self.a_to = a_to
        self.lift = lift
        self.drop = drop
        k = fig.k
        self.heel = (-0.070 * k, -fig.zAnk)
        self.ball = (0.150 * k, -fig.zAnk)
        self.toe = (0.200 * k, -fig.zAnk + 0.012)
        self.Y0 = S * f * 0.37

    def stance(self, ph):
        f = self.f
        p1 = 0.16 * f
        p2 = 0.52 * f
        if ph < p1:
            a = self.a_hs * (1.0 - smooth(ph / p1))
            vy, vz = rot2(a, -self.heel[0], -self.heel[1])
            return self.Y0 + self.heel[0] + vy, vz, a
        if ph < p2:
            return self.Y0, self.fig.zAnk, 0.0
        u = (ph - p2) / (f - p2)
        a = -self.a_to * u * u
        vy, vz = rot2(a, -self.ball[0], -self.ball[1])
        return self.Y0 + self.ball[0] + vy, vz, a

    def track(self, ph):
        ph = ph % 1.0
        f = self.f
        if ph < f:
            return self.stance(ph)
        ys, zs, as_ = self.stance(f - 1e-6)
        ye, ze, ae = self.stance(0.0)
        ye += self.S
        u = (ph - f) / (1.0 - f)
        e = smooth(u)
        y = lerp(ys, ye, e)
        z = lerp(zs, ze, e) + self.lift * math.sin(math.pi * u) ** 2
        a = lerp(as_, ae, smooth(min(u * 1.25, 1.0)))
        # Bodenfreiheit von Spitze und Ferse in der Schwungphase
        w = min(1.0, 4.0 * u * (1.0 - u) * 1.6)
        low = min(z + rot2(a, self.toe[0], self.toe[1])[1], z + rot2(a, self.heel[0], self.heel[1])[1])
        if low < 0.015:
            z += (0.015 - low) * w
        return y, z, a

    def rel(self, ph):
        """Knöchel relativ zum Hüftgelenk (vor/zurück), Höhe über Boden, Fußneigung."""
        ph = ph % 1.0
        y, z, a = self.track(ph)
        return y - self.S * ph, z, a


def leg_ik(fig, yrel, dz):
    """Zwei-Knochen-IK in der Laufebene: Oberschenkelwinkel (vor +) und Kniebeugung."""
    L1 = fig.L1
    L2 = fig.L2
    d = math.hypot(yrel, dz)
    d = min(max(d, abs(L1 - L2) + 0.02), (L1 + L2) * 0.9995)
    al = math.atan2(yrel, dz)
    cb = (L1 * L1 + d * d - L2 * L2) / (2.0 * L1 * d)
    be = math.acos(min(max(cb, -1.0), 1.0))
    cg = (L1 * L1 + L2 * L2 - d * d) / (2.0 * L1 * L2)
    kn = math.pi - math.acos(min(max(cg, -1.0), 1.0))
    return al + be, kn


def legs_pose(fig, pose, feet, hz):
    """feet: {"L": (yrel, z, a), "R": ...}, hz: Höhe des Hüftgelenks über Boden."""
    for side in ("L", "R"):
        y, z, a = feet[side]
        th, kn = leg_ik(fig, y, hz - z)
        pose["UpperLeg_" + side] = rx(th)
        pose["LowerLeg_" + side] = rx(-kn)
        pose["Foot_" + side] = rx(a - (th - kn))
    pose["hips"] = V((0.0, 0.0, hz - fig.zHipJ))


def hip_heights(fig, g, n):
    """Hüfthöhe je Bild: so hoch wie möglich, ohne dass ein Bein überstreckt; geglättet (ergibt das Wippen)."""
    L = (fig.L1 + fig.L2) * 0.9985
    hs = []
    for i in range(n):
        ph = i / n
        h = fig.zHipJ - g.drop
        for off in (0.0, 0.5):
            y, z, a = g.rel(ph + off)
            h = min(h, z + math.sqrt(max(L * L - y * y, 0.0)))
        hs.append(h)
    for _ in range(3):
        hs = [0.25 * hs[i - 1] + 0.5 * hs[i] + 0.25 * hs[(i + 1) % n] for i in range(n)]
    res = []
    for i in range(n):
        ph = i / n
        h = hs[i]
        for off in (0.0, 0.5):
            y, z, a = g.rel(ph + off)
            h = min(h, z + math.sqrt(max(L * L - y * y, 0.0)) - 0.001)
        res.append(h)
    return res


def posture(fig, pose):
    """Grundhaltung (gebeugt bei Älteren) auf jede Pose aufschlagen."""
    st = fig.spec.get("stoop", 0.0)
    if st:
        for bn, fac in (("Spine1", -0.45), ("Spine2", -0.60), ("Chest", -0.70), ("Neck", 0.55), ("Head", 0.55)):
            pose[bn] = rx(st * fac) @ pose.get(bn, Quaternion())
        for side in ("L", "R"):
            pose["Shoulder_" + side] = rx(-st * 0.25) @ pose.get("Shoulder_" + side, Quaternion())
    return pose


def arm_base(fig, pose, swL=0.0, swR=0.0, elL=0.12, elR=0.12):
    ab = fig.spec.get("arm_ab", 0.03 if fig.sex == "m" else 0.05)
    if fig.spec["top"] in ("mantel", "jacke"):
        ab += 0.015
    pose["UpperArm_L"] = rx(swL) @ ry(ab)
    pose["UpperArm_R"] = rx(swR) @ ry(-ab)
    pose["LowerArm_L"] = rx(elL)
    pose["LowerArm_R"] = rx(elR)


def anim_walk(fig, run=False):
    sp = fig.spec
    leg = fig.L1 + fig.L2
    if run:
        S = leg * 2.35
        T = 0.70
        g = Gait(fig, S, 0.36, 0.10, 0.75, 0.16 * fig.k, 0.045 * fig.k)
        lean, arm, el0, el1, yaw = 0.16, 0.70, 1.35, 0.25, 0.10
    else:
        S = leg * sp.get("stride", 1.56)
        T = sp.get("walk_T", 1.02)
        g = Gait(fig, S, 0.61, 0.30, 0.80, 0.035 * fig.k, 0.008 * fig.k)
        lean, arm, el0, el1, yaw = 0.035, sp.get("arm_swing", 0.36), 0.16, 0.20, 0.07
    n = int(round(T * FPS))
    hs = hip_heights(fig, g, n)
    carry = any(a in ("tuete", "aktentasche", "handtasche") for a in sp.get("acc", []))
    frames = []
    for i in range(n + 1):
        ph = (i % n) / n
        pose = {}
        legs_pose(fig, pose, {"L": g.rel(ph), "R": g.rel(ph + 0.5)}, hs[i % n])
        c = math.cos(TAU * ph)
        s = math.sin(TAU * ph)
        pose["hips"] = pose["hips"] + V((-0.012 * fig.k * s, 0.0, 0.0))
        pose["Hips"] = rz(-yaw * c) @ ry(0.035 * s)
        pose["Spine1"] = rx(-lean) @ rz(0.5 * yaw * c) @ ry(-0.035 * s)
        pose["Spine2"] = rz(0.6 * yaw * c)
        pose["Chest"] = rz(0.7 * yaw * c)
        pose["Neck"] = rz(-0.4 * yaw * c)
        pose["Head"] = rx(lean * 0.8) @ rz(-0.4 * yaw * c)
        c2 = math.cos(TAU * (ph - 0.04))
        swL = -arm * c2 + 0.05
        swR = arm * c2 + 0.05
        elL = el0 + el1 * (0.5 - 0.5 * c2)
        elR = el0 + el1 * (0.5 + 0.5 * c2)
        if carry and not run:
            swR = 0.25 * arm * c2 + 0.03
            elR = 0.10
        arm_base(fig, pose, swL, swR, elL, elR)
        frames.append(posture(fig, pose))
    return frames, T, S


def stand_pose(fig, drop=0.006):
    pose = {}
    legs_pose(fig, pose, {"L": (0.0, fig.zAnk, 0.0), "R": (0.0, fig.zAnk, 0.0)}, fig.zHipJ - drop * fig.k - fig.spec.get("stoop", 0.0) * 0.05)
    return pose


def anim_idle(fig, kind):
    T = {"Idle": 4.0, "Talk": 4.0, "Look": 3.2, "Phone": 4.0}[kind]
    n = int(round(T * FPS))
    frames = []
    for i in range(n + 1):
        t = (i % n) / n
        s1 = math.sin(TAU * t)
        s2 = math.sin(TAU * 2 * t)
        pose = stand_pose(fig, 0.006 + 0.003 * s1)
        pose["Chest"] = rx(0.012 * s2)
        swL = 0.03 * s1
        swR = -0.03 * s1
        elL = 0.14
        elR = 0.14
        pose["Head"] = rz(0.10 * s1) @ rx(0.02 * s2)
        pose["Spine1"] = rz(0.02 * s1)
        if kind == "Talk":
            pose["Head"] = rz(0.14 * s1) @ rx(-0.07 * s2)
            pose["Spine2"] = rx(-0.03 - 0.02 * s2)
            swR = 0.38 + 0.10 * s2
            elR = 1.25 + 0.35 * math.sin(TAU * 2 * t + 0.7)
            swL = 0.06 + 0.04 * s1
            elL = 0.30 + 0.08 * s2
        elif kind == "Look":
            # erst nach links, dann nach rechts schauen (Kopf führt, Schultern drehen leicht mit)
            a = 0.95 * math.sin(TAU * t) * (0.75 + 0.25 * math.cos(TAU * t))
            pose["Neck"] = rz(0.40 * a)
            pose["Head"] = rz(0.60 * a)
            pose["Chest"] = rz(0.13 * a)
            pose["Spine2"] = rz(0.08 * a)
        elif kind == "Phone":
            pose["Neck"] = rx(-0.22 + 0.015 * s1)
            pose["Head"] = rx(-0.25 + 0.02 * s2) @ rz(-0.05)
            pose["Spine2"] = rx(-0.05)
            swR = 0.30 + 0.015 * s1
            elR = 1.50 + 0.03 * s2
        arm_base(fig, pose, swL, swR, elL, elR)
        if kind == "Phone":
            pose["UpperArm_R"] = pose["UpperArm_R"] @ rz(0.55)
            pose["Hand_R"] = rx(0.25)
        if kind == "Talk":
            pose["UpperArm_R"] = pose["UpperArm_R"] @ rz(0.30)
        frames.append(posture(fig, pose))
    return frames, T


def bake(arm, name, frames):
    """Posen (Drehungen in den Achsen der Ruhelage) in Knochenkoordinaten umrechnen und als Aktion verschlüsseln."""
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = act
    rest = {b.name: b.matrix_local.to_quaternion() for b in arm.data.bones}
    prev = {}
    for fi, pose in enumerate(frames):
        for pb in arm.pose.bones:
            R = rest[pb.name]
            E = pose.get(pb.name, Quaternion())
            q = R.inverted() @ E @ R
            if pb.name in prev and prev[pb.name].dot(q) < 0.0:
                q = -q
            prev[pb.name] = q
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=fi)
            if pb.name == "Hips":
                pb.location = R.inverted() @ pose.get("hips", V((0, 0, 0)))
                pb.keyframe_insert("location", frame=fi)
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = (0, 0, 0)
    return act


def foot_slip(fig, frames, S, f_stance):
    """Prüfwert: größte Abweichung der Sohle vom Boden-Haftpunkt während der Standphase (m), rein aus den Posen."""
    n = len(frames) - 1
    worst = 0.0
    lo = 9.0
    for side, off in (("L", 0.0), ("R", 0.5)):
        base = None
        for i in range(n):
            ph = (i / n + off) % 1.0
            pose = frames[i]
            hz = fig.zHipJ + pose["hips"].z
            th = pose["UpperLeg_" + side].to_axis_angle()
            a1 = th[1] * (1 if th[0].x >= 0 else -1)
            kq = pose["LowerLeg_" + side].to_axis_angle()
            a2 = a1 + kq[1] * (1 if kq[0].x >= 0 else -1)
            ky, kz = rot2(a1, 0.0, -fig.L1)
            ay, az = rot2(a2, 0.0, -fig.L2)
            y = ky + ay + S * (i / n)                  # Knöchel im Bodensystem
            z = hz + kz + az
            lo = min(lo, z)
            if 0.16 * f_stance <= ph <= 0.52 * f_stance:
                yy = y - S * ph                      # ph läuft je Bein von 0 an: Haftpunkt = fester Wert
                yy = y - S * (i / n) + (S * (i / n) - S * ph) - (S if (i / n + off) >= 1.0 else 0.0) * 0.0
                yy = (ky + ay) + S * ph
                if base is None:
                    base = yy
                worst = max(worst, abs(yy - base))
    return worst, lo


# ------------------------------------------------------------------ Figurenliste
MODELS = [
    dict(name="frau1", sex="f", kind="f", H=1.68, hair="lang", top="jacke", bottom="hose", hose_eng=True, acc=["umhaengetasche"]),
    dict(name="frau2", sex="f", kind="f", H=1.64, hair="zopf", top="pulli", bottom="rock", strumpf=True, rock_len=0.05, acc=["rucksack"]),
    dict(name="frau3", sex="f", kind="f", H=1.71, hair="bob", top="mantel", bottom="hose", stiefel=True, acc=["schal", "tuete"], brille=True),
    dict(name="frau4", sex="f", kind="f", H=1.66, hair="dutt", top="kleid", bottom="kleid", kurzarm=True, rock_len=0.03, rock_weite=0.34, acc=["umhaengetasche"], sohle=0.8),
    dict(name="frau5", sex="f", kind="f", H=1.62, hair="kopftuch", top="mantel", langmantel=True, bottom="hose", acc=["handtasche"], build=1.06),
    dict(name="frau6", sex="f", kind="f", H=1.73, hair="locken", top="tshirt", bottom="hose", acc=[], sohle=0.85, guertel=True),
    dict(name="mann1", sex="m", kind="m", H=1.81, hair="kurz", top="jacke", bottom="hose", acc=[]),
    dict(name="mann2", sex="m", kind="m", H=1.77, hair="kurz2", top="mantel", bottom="hose", acc=["schal", "aktentasche"], brille=True),
    dict(name="mann3", sex="m", kind="m", H=1.86, hair="muetze", top="hoodie", bottom="hose", acc=["rucksack"], sohle=0.85),
    dict(name="mann4", sex="m", kind="m", H=1.75, hair="glatze", bart=True, top="tshirt", bottom="shorts", build=1.12, belly=0.035, acc=[], sohle=0.8, guertel=True),
    dict(name="mann5", sex="m", kind="m", H=1.79, hair="kappe", top="pulli", bottom="hose", hose_eng=True, acc=["umhaengetasche"], bart=True),
    dict(name="kind1", sex="m", kind="k", H=1.30, hair="kurz2", top="pulli", bottom="hose", acc=["rucksack"], walk_T=0.86, stride=1.50, sohle=0.8),
    dict(name="kind2", sex="f", kind="k", H=1.20, hair="zoepfe", top="tshirt", bottom="rock", rock_len=0.05, rock_weite=0.40, acc=[], walk_T=0.82, stride=1.50, sohle=0.85),
    dict(name="seniorin", sex="f", kind="a", H=1.59, hair="dutt_tief", top="mantel", bottom="rock", strumpf=True, rock_len=-0.02, rock_weite=0.16,
         acc=["handtasche"], stoop=0.26, stride=1.24, walk_T=1.14, arm_swing=0.20, build=1.08, belly=0.02, brille=True),
    dict(name="senior", sex="m", kind="a", H=1.71, hair="hut", top="jacke", bottom="hose", acc=[], stoop=0.24, stride=1.28, walk_T=1.14,
         arm_swing=0.22, build=1.06, belly=0.04),
]


def build_model(spec):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = FPS
    fig = Figure(spec)
    S = fig.build()
    ob, arm = make_objects(fig)
    info = {"name": "ped_" + spec["name"], "kind": spec["kind"], "tris": S.tris(), "H": fig.H}
    acts = []
    fr, T, St = anim_walk(fig, False)
    slip, lo = foot_slip(fig, fr, St, 0.61)
    info.update(walk=St, walk_T=T, slip=slip)
    acts.append(bake(arm, "Walk", fr))
    fr, T, St = anim_walk(fig, True)
    info.update(run=St, run_T=T)
    acts.append(bake(arm, "Run", fr))
    for kind in ("Idle", "Talk", "Look", "Phone"):
        fr, T = anim_idle(fig, kind)
        acts.append(bake(arm, kind, fr))
    ad = arm.animation_data
    for act in acts:
        tr = ad.nla_tracks.new()
        tr.name = act.name
        st = tr.strips.new(act.name, 0, act)
        st.name = act.name
    arm["walk_len"] = round(info["walk"], 4)          # Schrittzyklen als glTF-"extras" (Godot: Metadaten des Knotens)
    arm["run_len"] = round(info["run"], 4)
    arm["kind"] = spec["kind"]
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    path = os.path.join(OUT, info["name"] + ".glb")
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
              export_skins=True, export_animations=True, export_animation_mode="NLA_TRACKS",
              export_force_sampling=True, export_optimize_animation_size=True, export_frame_range=False,
              export_materials="EXPORT", export_texcoords=True, export_normals=True, export_tangents=False,
              export_cameras=False, export_lights=False, export_extras=True, export_morph=False,
              export_def_bones=False, export_reset_pose_bones=True)
    known = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in known})
    return info


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    infos = []
    for spec in MODELS:
        if argv and ("ped_" + spec["name"]) not in argv and spec["name"] not in argv:
            continue
        infos.append(build_model(spec))
    print("\n=== Fußgänger gebaut ===")
    for i in infos:
        print("%-14s %s  %4.2f m  %5d Dreiecke  Gehen %.3f m / %.2f s = %.2f m/s (Standfuß-Abweichung %.1f mm)  Laufen %.3f m / %.2f s" % (
            i["name"], i["kind"], i["H"], i["tris"], i["walk"], i["walk_T"], i["walk"] / i["walk_T"], i["slip"] * 1000.0, i["run"], i["run_T"]))
    print("\n# Tabelle für godot/scripts/peds.gd (MODELS): Datei, Art, Schrittzyklus Gehen (m), Laufen (m)")
    for i in infos:
        print('\t["%s", "%s", %.3f, %.3f],' % (i["name"], i["kind"], i["walk"], i["run"]))


main()
