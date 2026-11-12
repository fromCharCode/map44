"""Erzeugt die Modelltexturen fuer die Stadtmoebel (godot/assets/models/furniture).

Aufruf (Projektordner):  source .venv/bin/activate && python tools/blender/furniture_textures.py
Ausgabe: tools/blender/furniture_tex/*.png (<= 512 px), werden von furniture_build.py
in die .glb eingebettet. Alles selbst erzeugt (keine Fremdtexturen, keine Logos).
"""
import os
import numpy as np
from PIL import Image, ImageDraw
from furniture_texutil import (fbm, blur, hexcol, lerp, solid, to_img, Canvas, rng,
                               blob_poly, rot_pts, value_noise)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "furniture_tex")
os.makedirs(OUT, exist_ok=True)


def save(name, rgb, alpha=None):
    p = os.path.join(OUT, name)
    to_img(rgb, alpha).save(p, optimize=True)
    print("tex", name, rgb.shape[1], "x", rgb.shape[0])


def grime(h, w, seed, bottom=0.25, streaks=0.3, amount=1.0):
    """Schmutzmaske 0..1 (Bild-y nach unten): Spritzer unten + Regenstreifen von oben."""
    y = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 6, 5, seed)
    low = np.clip((y - (1 - bottom)) / bottom, 0, 1) ** 1.6
    low = low * (0.55 + 0.9 * n)
    # vertikale Streifen: Rauschen nur ueber x, nach unten auslaufend
    sx = value_noise(4, w, 28, seed + 7)[0][None, :]
    sx2 = value_noise(4, w, 70, seed + 9)[0][None, :]
    st = np.clip((sx * 0.6 + sx2 * 0.4 - 0.55) * 3.5, 0, 1)
    fade = np.clip(1 - y * (1.0 + 0.8 * value_noise(h, w, 3, seed + 3)), 0, 1)
    strk = st * fade * streaks * (0.6 + 0.4 * n)
    g = np.clip(low + strk, 0, 1) * amount
    spots = np.clip((fbm(h, w, 40, 3, seed + 11) - 0.9) * 4, 0, 1) * 0.12 * amount
    return np.clip(g + spots, 0, 1)


# ---------------------------------------------------------------- Verteilerkasten
def cabinet():
    W = H = 512
    # u: Umfang 3.2 m: Front 0..0.375 | Seite(-X) ..0.5 | Rueck ..0.875 | Seite(+X) ..1
    # v: Koerper z 0.08..1.25 (1.17 m), Bild-y 0 = oben
    base = hexcol("#c4c6c1")
    n = fbm(H, W, 8, 5, 3)
    rgb = base * (0.95 + 0.07 * n[..., None])
    px_m_u = W / 3.2
    px_m_v = H / 1.17

    def U(m):  # Front-Meter (0 = linke Kante von vorn gesehen) -> px
        return m * px_m_u

    def V(z):  # z ueber Koerperunterkante -> Bild-y
        return H - (z - 0.08) * px_m_v

    seams = Canvas(W, H)
    hl = Canvas(W, H)
    # Tueren: Rahmen 3 cm, Mittelfuge bei 0.6 m
    for x0, x1 in ((0.035, 0.595), (0.605, 1.165)):
        pts = [(U(x0), V(1.22)), (U(x1), V(1.22)), (U(x1), V(0.12)), (U(x0), V(0.12)),
               (U(x0), V(1.22))]
        seams.line(pts, 1.6, 255, joint=False)
        hl.line([(U(x0) + 1.5, V(1.22) + 2), (U(x1) - 1, V(1.22) + 2)], 1.0, 255)
    # Schloesser
    dark = Canvas(W, H)
    for xl in (0.54, 0.66):
        dark.ellipse(U(xl), V(0.78), 3.2, 4.5, 255)
    # Lueftungsschlitze auf beiden Seiten und Rueckseite oben
    for s0 in (1.2, 2.8):  # Seitenflaechen beginnen bei 1.2 m bzw. 2.8 m Umfang
        for i in range(7):
            z = 1.10 - i * 0.035
            seams.line([(U(s0 + 0.08), V(z)), (U(s0 + 0.32), V(z))], 2.2, 255, joint=False)
            hl.line([(U(s0 + 0.08), V(z) + 2.2), (U(s0 + 0.32), V(z) + 2.2)], 1.0, 255)
    rgb = lerp(rgb, hexcol("#3b3d3c"), seams.mask() * 0.85)
    rgb = lerp(rgb, hexcol("#e2e3df"), hl.mask() * 0.5)
    rgb = lerp(rgb, hexcol("#1c1c1c"), dark.mask())
    # Warnaufkleber (gelbes Dreieck mit Blitz, generisch) oben links auf der linken Tuer
    tri = Canvas(W, H)
    cx, cy, s = U(0.18), V(1.06), 13
    tri.poly([(cx, cy - s), (cx + s * 1.1, cy + s * 0.8), (cx - s * 1.1, cy + s * 0.8)])
    tri_in = Canvas(W, H)
    s2 = s * 0.72
    tri_in.poly([(cx, cy - s2 + 1.5), (cx + s2 * 1.1, cy + s2 * 0.8 + 1), (cx - s2 * 1.1, cy + s2 * 0.8 + 1)])
    bolt = Canvas(W, H)
    bolt.line([(cx + 2, cy - 5), (cx - 2, cy + 2), (cx + 2, cy + 1), (cx - 2, cy + 9)], 1.4, 255)
    rgb = lerp(rgb, hexcol("#202020"), tri.mask())
    rgb = lerp(rgb, hexcol("#f2c200"), tri_in.mask())
    rgb = lerp(rgb, hexcol("#202020"), bolt.mask())
    # Aufkleberreste (zerrissen, verblasst)
    r = rng(5)
    st = Canvas(W, H)
    for (xm, zm, w, h) in ((0.85, 0.95, 0.07, 0.10), (0.30, 0.55, 0.05, 0.05), (2.95, 0.70, 0.08, 0.06)):
        pts = [(U(xm), V(zm)), (U(xm + w), V(zm + 0.005)), (U(xm + w * 0.9), V(zm - h)),
               (U(xm + w * 0.4), V(zm - h * 0.8)), (U(xm + 0.005), V(zm - h * 1.05))]
        st.poly(pts)
    m = st.mask() * (0.5 + 0.5 * fbm(H, W, 30, 3, 9))
    rgb = lerp(rgb, hexcol("#ecead8"), np.clip(m, 0, 1) * 0.8)
    # Graffiti-Tag (abstrakte Schlaufen, kein Text) auf rechter Tuer
    tag = Canvas(W, H)
    pts = []
    t = np.linspace(0, 1, 60)
    for k in t:
        x = 0.72 + 0.36 * k
        z = 0.42 + 0.06 * np.sin(k * 23) + 0.04 * np.sin(k * 7 + 1) + 0.02 * k
        pts.append((U(x), V(z)))
    tag.line(pts, 2.4, 255)
    tag.line([(U(0.74), V(0.36)), (U(1.10), V(0.345))], 1.6, 255)
    rgb = lerp(rgb, hexcol("#2a2340"), tag.mask() * 0.85)
    # Schmutz
    g = grime(H, W, 21, bottom=0.22, streaks=0.35, amount=0.85)
    rgb = lerp(rgb, hexcol("#5b5244"), g * 0.7)
    save("cabinet_grey.png", rgb)


# ---------------------------------------------------------------- Parkscheinautomat
def P_letter(c, x, y, h, wline):
    """Buchstabe P aus Strichen: (x,y) = links oben, Hoehe h."""
    c.line([(x, y), (x, y + h)], wline, 255, joint=False)
    bw = h * 0.36
    n = 16
    pts = [(x, y)]
    for i in range(n + 1):
        a = -np.pi / 2 + np.pi * i / n
        pts.append((x + bw * 0.55 + np.cos(a) * bw, y + h * 0.28 + np.sin(a) * h * 0.28))
    pts.append((x, y + h * 0.56))
    c.line(pts, wline, 255)


def meter():
    W, H = 256, 512  # Flaeche 0.34 x 0.74 m
    rgb = solid(H, W, "#8d9296") * (0.96 + 0.06 * fbm(H, W, 6, 4, 2)[..., None])
    def Y(f): return f * H
    def X(f): return f * W
    # blaues Band oben mit weissem P
    band = Canvas(W, H)
    band.rect(0, 0, W, Y(0.10))
    rgb = lerp(rgb, hexcol("#1f4fa0"), band.mask())
    p = Canvas(W, H)
    P_letter(p, X(0.42), Y(0.018), Y(0.064), 6)
    rgb = lerp(rgb, hexcol("#f4f4f4"), p.mask())
    # Display
    fr = Canvas(W, H); fr.rect(X(0.12), Y(0.13), X(0.88), Y(0.30))
    lcd = Canvas(W, H); lcd.rect(X(0.17), Y(0.155), X(0.83), Y(0.275))
    rgb = lerp(rgb, hexcol("#2b2e30"), fr.mask())
    rgb = lerp(rgb, hexcol("#7f9a86"), lcd.mask())
    seg = Canvas(W, H)
    for i, wl in enumerate((0.55, 0.35, 0.6)):
        y = Y(0.18 + i * 0.03)
        seg.line([(X(0.22), y), (X(0.22 + wl * 0.55), y)], 3, 255, joint=False)
    rgb = lerp(rgb, hexcol("#2f3b33"), seg.mask() * 0.8)
    # Tastenreihe gruen / grau / rot
    for fx, col in ((0.25, "#2e9a48"), (0.5, "#c9cbcc"), (0.75, "#c8312b")):
        b = Canvas(W, H); b.ellipse(X(fx), Y(0.345), 12, 12)
        rim = Canvas(W, H); rim.ellipse(X(fx), Y(0.345), 15, 15)
        rgb = lerp(rgb, hexcol("#3a3d40"), rim.mask())
        rgb = lerp(rgb, hexcol(col), b.mask())
    # Ziffernblock 3x4
    kb = Canvas(W, H); kk = Canvas(W, H)
    kb.rect(X(0.22), Y(0.39), X(0.78), Y(0.585))
    for r_ in range(4):
        for c_ in range(3):
            x0 = X(0.25 + c_ * 0.18); y0 = Y(0.40 + r_ * 0.046)
            kk.rect(x0, y0, x0 + X(0.14), y0 + Y(0.036))
    rgb = lerp(rgb, hexcol("#3a3d40"), kb.mask())
    rgb = lerp(rgb, hexcol("#b9bcbf"), kk.mask())
    # Muenzeinwurf links, Kartenschlitz rechts
    cp = Canvas(W, H); cp.rect(X(0.10), Y(0.61), X(0.42), Y(0.66))
    cs = Canvas(W, H); cs.rect(X(0.24), Y(0.622), X(0.28), Y(0.65))
    ks = Canvas(W, H); ks.rect(X(0.55), Y(0.625), X(0.90), Y(0.645))
    rgb = lerp(rgb, hexcol("#c7c9c6"), cp.mask())
    rgb = lerp(rgb, hexcol("#111111"), cs.mask())
    rgb = lerp(rgb, hexcol("#111111"), ks.mask())
    # Infotafel (weiss, Textzeilen als graue Balken)
    it = Canvas(W, H); it.rect(X(0.10), Y(0.685), X(0.90), Y(0.845))
    rgb = lerp(rgb, hexcol("#eeeeea"), it.mask())
    hd = Canvas(W, H); hd.rect(X(0.10), Y(0.685), X(0.90), Y(0.705))
    rgb = lerp(rgb, hexcol("#1f4fa0"), hd.mask())
    tl = Canvas(W, H)
    r = rng(3)
    for i in range(9):
        y = Y(0.718 + i * 0.0135)
        tl.line([(X(0.14), y), (X(0.14 + 0.45 + 0.25 * r.random()), y)], 2.0, 255, joint=False)
    rgb = lerp(rgb, hexcol("#6c6f73"), tl.mask() * 0.85)
    # Ticketausgabe
    tb = Canvas(W, H); tb.rect(X(0.20), Y(0.875), X(0.80), Y(0.975))
    ti = Canvas(W, H); ti.rect(X(0.24), Y(0.885), X(0.76), Y(0.965))
    rgb = lerp(rgb, hexcol("#2c2f31"), tb.mask())
    rgb = lerp(rgb, hexcol("#0d0d0d"), ti.mask())
    g = grime(H, W, 17, bottom=0.12, streaks=0.2, amount=0.5)
    rgb = lerp(rgb, hexcol("#4c4740"), g * 0.5)
    save("meter_face.png", rgb)


# ---------------------------------------------------------------- Rattan
def rattan():
    S = 256
    y, x = np.mgrid[0:S, 0:S] / S
    k = 16  # Baender je Kachel
    a = (x + y) * k
    b = (x - y) * k
    fa = np.abs(((a % 1) - 0.5)) * 2
    fb = np.abs(((b % 1) - 0.5)) * 2
    over = ((np.floor(a) + np.floor(b)) % 2) == 0
    band_a = 1 - fa ** 3
    band_b = 1 - fb ** 3
    h = np.where(over, band_a, band_b)
    n = fbm(S, S, 16, 3, 4)
    base = lerp(hexcol("#5e4a38"), hexcol("#a08566"), np.clip(h * 0.9 + 0.1 * n, 0, 1))
    gaps = np.clip((np.minimum(fa, fb) - 0.88) * 8, 0, 1)
    rgb = lerp(base, hexcol("#2a2018"), gaps * 0.8)
    save("rattan.png", rgb)


# ---------------------------------------------------------------- Karton
def cardboard():
    W, H = 512, 512
    n = fbm(H, W, 10, 5, 31)
    fibre = value_noise(H, W, 180, 33)
    rgb = lerp(hexcol("#9c7447"), hexcol("#c49a66"), 0.35 + 0.45 * n)
    rgb = rgb * (0.95 + 0.08 * fibre[..., None])
    main_h = 448
    # Faltkanten (Druckspuren) und Klebeband im Flaechenbereich
    c = Canvas(W, H)
    for xf in (0.33, 0.66):
        c.line([(W * xf, 6), (W * xf, main_h - 6)], 2.0)
    c.line([(6, main_h * 0.5), (W - 6, main_h * 0.5)], 1.5)
    rgb = lerp(rgb, hexcol("#6b4c2c"), c.mask() * 0.55)
    tape = Canvas(W, H)
    tape.poly([(W * 0.42, 0), (W * 0.57, 0), (W * 0.58, main_h), (W * 0.43, main_h)])
    tm = tape.mask() * (0.7 + 0.3 * fbm(H, W, 40, 2, 7))
    rgb = lerp(rgb, hexcol("#d8b98a"), tm * 0.7)
    # generische Piktogramme: zwei Pfeile "oben", Regenschirm
    pic = Canvas(W, H)
    for px in (W * 0.12, W * 0.20):
        pic.line([(px, 150), (px, 95)], 5, 255, joint=False)
        pic.poly([(px - 12, 100), (px + 12, 100), (px, 78)])
    # Regenschirm
    cx, cy = W * 0.82, 110
    pts = [(cx + np.cos(a) * 26, cy - np.sin(a) * 22) for a in np.linspace(0, np.pi, 14)]
    pic.poly(pts + [(cx - 26, cy)])
    pic.line([(cx, cy), (cx, cy + 30), (cx - 8, cy + 34)], 3.5, 255)
    for d in (-1.4, -0.4, 0.6):
        pic.line([(cx + d * 14, cy + 34), (cx + d * 14 - 6, cy + 46)], 2.5, 255)
    pm = pic.mask() * (0.75 + 0.25 * n)
    rgb = lerp(rgb, hexcol("#2a221c"), pm * 0.85)
    # Flecken / Wasserraender
    st = np.clip((fbm(H, W, 5, 4, 77) - 0.7) * 4, 0, 1)
    rgb = lerp(rgb, hexcol("#7a5733"), st * 0.45)
    # Wellpappenkante unten (Streifen 64 px)
    y, x = np.mgrid[0:H, 0:W]
    edge = (y >= main_h)
    flute = 0.5 + 0.5 * np.sin(x / W * 2 * np.pi * 120)
    ed = lerp(hexcol("#7d5a35"), hexcol("#b58b58"), flute)
    lines = (np.abs(y - main_h - 6) < 2) | (np.abs(y - (H - 6)) < 2)
    ed = np.where(lines[..., None], hexcol("#c9a06c"), ed)
    rgb = np.where(edge[..., None], ed * (0.9 + 0.15 * n[..., None]), rgb)
    save("cardboard.png", rgb)


# ---------------------------------------------------------------- Matratze
def mattress():
    W, H = 512, 512
    top_h = 384
    y, x = np.mgrid[0:H, 0:W].astype(float)
    n = fbm(H, W, 8, 5, 41)
    # Steppmuster (Rauten)
    k = 10
    u = x / W * k
    v = y / top_h * k * 1.9
    d = np.minimum(np.abs(((u + v) % 1) - 0.5), np.abs(((u - v) % 1) - 0.5))
    quilt = np.clip(d * 4.0, 0, 1)
    rgb = lerp(hexcol("#b7b2a6"), hexcol("#e9e5da"), 0.4 + 0.6 * quilt ** 0.5)
    rgb = rgb * (0.94 + 0.08 * n[..., None])
    # Flecken
    r = rng(8)
    for i in range(5):
        c = Canvas(W, H)
        cx, cy = r.uniform(40, W - 40), r.uniform(40, top_h - 40)
        c.poly(blob_poly(cx, cy, r.uniform(18, 55), 28, 0.35, i))
        m = c.mask(3.0)
        ring = np.clip(m - blur(m, 6) * 0.9, 0, 1) * 1.5
        rgb = lerp(rgb, hexcol("#b49a62"), np.clip(m * 0.35 + ring * 0.5, 0, 1))
    # Randband (unten 128 px): Streifenstoff mit Paspel
    band = y >= top_h
    stripes = 0.5 + 0.5 * np.sign(np.sin(x / W * 2 * np.pi * 64))
    bd = lerp(hexcol("#59708a"), hexcol("#8ea2b6"), stripes * 0.6)
    pip = (np.abs(y - top_h - 5) < 4) | (np.abs(y - (H - 5)) < 4)
    bd = np.where(pip[..., None], hexcol("#d6d3cb"), bd)
    rgb = np.where(band[..., None], bd * (0.9 + 0.12 * n[..., None]), rgb)
    g = grime(H, W, 44, bottom=0.2, streaks=0.0, amount=0.6)
    rgb = lerp(rgb, hexcol("#6b604d"), g * 0.5)
    save("mattress.png", rgb)


# ---------------------------------------------------------------- Bauzaungitter
def fence_mesh():
    S = 512  # Kachel = 1 m x 1 m, senkrechte Draehte alle 10 cm, waagrecht alle 25 cm
    c = Canvas(S, S)
    for i in range(10):
        x = (i + 0.5) * S / 10
        c.line([(x, -2), (x, S + 2)], 3.2, 255, joint=False)
    for j in range(4):
        y = (j + 0.5) * S / 4
        c.line([(-2, y), (S + 2, y)], 3.6, 255, joint=False)
    a = c.mask()
    a = np.clip(a * 1.25, 0, 1)
    n = fbm(S, S, 12, 3, 51)
    rgb = lerp(hexcol("#8f9493"), hexcol("#c5c9c7"), n)
    save("fence_mesh.png", rgb, a)


# ---------------------------------------------------------------- Speichen
def spokes():
    S = 512
    c = Canvas(S, S)
    cx = cy = S / 2
    R = S / 2 - 1  # Speichen bis zum Bildrand (= Felgeninnenseite)
    rh = S * 0.035
    n = 36
    for i in range(n):
        a0 = 2 * np.pi * i / n
        # Tangentiale Kreuzspeichung: Nabenpunkt versetzt
        off = (0.35 if i % 2 else -0.35)
        ah = a0 + off
        p0 = (cx + np.cos(ah) * rh, cy + np.sin(ah) * rh)
        p1 = (cx + np.cos(a0) * R, cy + np.sin(a0) * R)
        c.line([p0, p1], 1.6, 255, joint=False)
    c.ellipse(cx, cy, rh * 1.25, rh * 1.25)
    a = np.clip(c.mask() * 1.4, 0, 1)
    rgb = solid(S, S, "#b9bdc0")
    save("spokes.png", rgb, a)


# ---------------------------------------------------------------- Blattwerk
def foliage(name, seed, flowers=None):
    S = 256
    r = rng(seed)
    rgb = solid(S, S, "#1f3317")
    for layer in range(3):
        c = Canvas(S, S)
        col = [hexcol("#2c4a1f"), hexcol("#3f6a2a"), hexcol("#5d8a3a")][layer]
        for i in range(260):
            x, y = r.uniform(-10, S + 10), r.uniform(-10, S + 10)
            a = r.uniform(0, np.pi)
            L = r.uniform(7, 13)
            pts = rot_pts([(x - L, y), (x, y - L * 0.38), (x + L, y), (x, y + L * 0.38)], x, y, a)
            c.poly(pts, int(r.uniform(150, 255)))
        m = c.mask()
        shade = 0.8 + 0.35 * fbm(S, S, 6, 3, seed + layer)
        rgb = lerp(rgb, col * shade[..., None], m)
    if flowers:
        for col, cnt in flowers:
            c = Canvas(S, S)
            ctr = Canvas(S, S)
            for i in range(cnt):
                x, y = r.uniform(6, S - 6), r.uniform(6, S - 6)
                rr = r.uniform(5.0, 8.0)
                a0 = r.random() * 6.28
                for k in range(5):
                    a = a0 + 2 * np.pi * k / 5
                    c.ellipse(x + np.cos(a) * rr * 0.62, y + np.sin(a) * rr * 0.62, rr * 0.5, rr * 0.5)
                ctr.ellipse(x, y, rr * 0.28, rr * 0.28)
            m = c.mask()
            sh = Canvas(S, S)
            rgb = lerp(rgb, rgb * 0.55, np.clip(blur(m, 1.5) * 1.2, 0, 1))  # Schatten unter Blueten
            rgb = lerp(rgb, hexcol(col) * (0.85 + 0.2 * fbm(S, S, 10, 2, 9)[..., None]), m)
            rgb = lerp(rgb, hexcol("#e8b830"), ctr.mask() * 0.9)
    save(name, rgb)


# ---------------------------------------------------------------- Beton
def concrete():
    S = 256
    n = fbm(S, S, 6, 6, 61)
    pores = np.clip((value_noise(S, S, 90, 62) - 0.82) * 6, 0, 1)
    rgb = lerp(hexcol("#8c8a84"), hexcol("#b3b0a8"), n)
    rgb = lerp(rgb, hexcol("#5f5d58"), pores * 0.6)
    save("concrete.png", rgb)


# ---------------------------------------------------------------- Container (Glas/Papier)
def bottle(c, cx, cy, h):
    w = h * 0.34
    neck = h * 0.12
    pts = [(cx - neck / 2, cy - h / 2), (cx + neck / 2, cy - h / 2),
           (cx + neck / 2, cy - h * 0.18), (cx + w / 2, cy - h * 0.02),
           (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2), (cx - w / 2, cy - h * 0.02),
           (cx - neck / 2, cy - h * 0.18)]
    c.poly(pts)


def container_tex(name, body, pict, seed, kind="glass"):
    S = 256
    n = fbm(S, S, 6, 5, seed)
    rgb = hexcol(body) * (0.93 + 0.1 * n[..., None])
    # Etikett mittig oben (weisse Tafel mit Piktogramm, kein Text)
    lab = Canvas(S, S); lab.rect(S * 0.32, S * 0.34, S * 0.68, S * 0.58)
    rgb = lerp(rgb, hexcol("#f1f1ec"), lab.mask())
    pc = Canvas(S, S)
    if kind == "glass":
        bottle(pc, S * 0.44, S * 0.46, S * 0.19)
        bottle(pc, S * 0.56, S * 0.47, S * 0.16)
    else:  # Papier: Zeitungsstapel
        for i in range(3):
            y = S * (0.50 - i * 0.045)
            pc.poly([(S * 0.38, y), (S * 0.62, y - 3), (S * 0.63, y + 7), (S * 0.39, y + 10)])
    rgb = lerp(rgb, hexcol(pict), pc.mask())
    rim = Canvas(S, S)
    rim.line([(S * 0.32, S * 0.34), (S * 0.68, S * 0.34), (S * 0.68, S * 0.58), (S * 0.32, S * 0.58),
              (S * 0.32, S * 0.34)], 1.5, 255, joint=False)
    rgb = lerp(rgb, hexcol("#555555"), rim.mask() * 0.6)
    g = grime(S, S, seed + 5, bottom=0.3, streaks=0.45, amount=0.9)
    rgb = lerp(rgb, hexcol("#4a463c"), g * 0.55)
    save(name, rgb)


# ---------------------------------------------------------------- Briefkasten-Tafel
def postbox_plate():
    W, H = 128, 128
    rgb = solid(H, W, "#f2f2ee")
    hd = Canvas(W, H); hd.rect(0, 0, W, 18)
    rgb = lerp(rgb, hexcol("#2a2a2a"), hd.mask())
    tl = Canvas(W, H)
    r = rng(12)
    for i in range(7):
        y = 30 + i * 13
        x1 = 14 + r.uniform(40, 95)
        tl.line([(12, y), (x1, y)], 3.0, 255, joint=False)
        tl.line([(W - 34, y), (W - 12, y)], 3.0, 255, joint=False)
    rgb = lerp(rgb, hexcol("#555a5f"), tl.mask())
    save("postbox_plate.png", rgb)


if __name__ == "__main__":
    cabinet()
    meter()
    rattan()
    cardboard()
    mattress()
    fence_mesh()
    spokes()
    foliage("foliage.png", 71)
    foliage("flowers.png", 73, flowers=[("#d8344a", 55), ("#c0407a", 30), ("#f4f0f6", 30), ("#f2d23c", 20)])
    concrete()
    container_tex("glass_white.png", "#e9ebe6", "#8aa8b8", 81)
    container_tex("glass_green.png", "#2f6e3b", "#2f6e3b", 82)
    container_tex("glass_brown.png", "#6b4428", "#6b4428", 83)
    container_tex("paper_blue.png", "#1f4f9c", "#1f4f9c", 84, kind="paper")
    postbox_plate()
