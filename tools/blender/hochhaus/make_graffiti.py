"""Graffiti-Textur „NADDL.UND.RONNY.SIEGT!“ für die WNW-Attika des Hochhauses Pirnaischer Platz (Zustand 2019–22).
Selbst gezeichnet nach der Beschreibung in data/research/pirnaischer_platz_hochhaus.md (keine Foto-Vorlage):
weiße Blockbuchstaben, schwarze Kontur (0,11 m), schwarzer Schlagschatten (0,10 m zurück/unten), leicht unregelmäßig,
verwittert auf rauem Sichtbeton; rechts daneben der kleine Tag „BIGI 44PG!“.
Textur deckt lokal X +25,8 … −14,0 (39,8 m) und Y 43,20 … 45,02 (1,82 m) ab; Ausgabe 8192 × 384 px (RGBA)."""
import math, random, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

out = sys.argv[1]
W, H = 8192, 384
X0, X1 = 25.8, -14.0           # u = 0 bei X0 (links aus Sicht des Betrachters), u = 1 bei X1
Y0, Y1 = 45.02, 43.20          # v = 0 oben
ppm_x = W / (X0 - X1)
ppm_y = H / (Y0 - Y1)
FONT = "/usr/share/fonts/google-noto/NotoSans-CondensedBlack.ttf"
rng = random.Random(1966)


def u(X):
    return (X0 - X) * ppm_x


def v(Y):
    return (Y0 - Y) * ppm_y


img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
cap_px = int(1.46 * ppm_y)
stroke = max(2, int(0.11 * ppm_x))
shadow_dx, shadow_dy = -int(0.10 * ppm_x), int(0.10 * ppm_y)
font = ImageFont.truetype(FONT, int(cap_px * 1.36))

# (Text, X von, X bis, Y unten, Y oben)  – Werte aus der Recherche (5.6)
words = [("NADDL", 25.18, 19.25, 43.38, 44.84), ("·", 19.05, 18.75, 43.95, 44.25), ("UND", 18.54, 15.09, 43.38, 44.84),
         (".", 14.85, 14.49, 43.38, 43.68), ("RONNY", 14.22, 7.39, 43.38, 44.84), (".", 7.29, 6.98, 43.55, 43.85),
         ("SIEGT", 6.88, 0.90, 43.38, 44.84), ("!", 0.70, 0.19, 43.38, 44.84)]


def glyph_layer(ch, w_px, h_px, dot=False):
    """Ein Zeichen (oder Punkt) als weiße Fläche mit schwarzer Kontur, auf w×h gestreckt."""
    pad = stroke * 3
    if dot:
        g = Image.new("RGBA", (w_px + 2 * pad, h_px + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(g)
        sw = max(2, stroke // 3)
        d.rectangle([pad - sw, pad - sw, pad + w_px + sw, pad + h_px + sw], fill=(18, 18, 18, 255))
        d.rectangle([pad, pad, pad + w_px, pad + h_px], fill=(236, 234, 228, 255))
        return g, pad
    bb = font.getbbox(ch, stroke_width=0)
    gw, gh = bb[2] - bb[0], bb[3] - bb[1]
    tmp = Image.new("RGBA", (gw + 4 * stroke, gh + 4 * stroke), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((2 * stroke - bb[0], 2 * stroke - bb[1]), ch, font=font, fill=(236, 234, 228, 255),
                             stroke_width=stroke, stroke_fill=(18, 18, 18, 255))
    tw = w_px + 2 * stroke
    th = h_px + 2 * stroke
    tmp = tmp.resize((max(tw, 4), max(th, 4)), Image.LANCZOS)
    return tmp, stroke


def paste_word(text, xa, xb, ya, yb):
    left, right = u(xa), u(xb)
    top, bot = v(yb), v(ya)
    w_total = right - left
    h = bot - top
    dot = text in ("·", ".")
    n = len(text)
    gap = 0.07 * h if n > 1 else 0.0
    cw = (w_total - gap * (n - 1)) / n
    for i, ch in enumerate(text):
        x = left + i * (cw + gap) + rng.uniform(-0.03, 0.03) * cw
        y = top + rng.uniform(-0.03, 0.04) * h
        sw = cw * rng.uniform(0.96, 1.04)
        sh = h * rng.uniform(0.97, 1.03)
        if ch == "!":
            sw = cw * 0.5
            x += cw * 0.25
        g, pad = glyph_layer(ch, int(sw), int(sh), dot)
        g = g.rotate(rng.uniform(-2.2, 2.2), resample=Image.BICUBIC, expand=True)
        # Schlagschatten
        sh_layer = Image.new("RGBA", g.size, (18, 18, 18, 0))
        sh_layer.putalpha(g.getchannel("A"))
        img.alpha_composite(sh_layer, (int(x - pad + shadow_dx), int(y - pad + shadow_dy)))
        img.alpha_composite(g, (int(x - pad), int(y - pad)))


for wd in words:
    paste_word(*wd)

# Tag "BIGI 44PG!": dünne, leicht schräge Handschrift (X −5,0 … −13,6, Y 43,5–44,6)
tag = Image.new("RGBA", (int(u(-13.6) - u(-5.0)) + 60, int(1.3 * ppm_y) + 40), (0, 0, 0, 0))
tf = ImageFont.truetype("/usr/share/fonts/google-noto/NotoSans-SemiCondensedSemiBold.ttf", int(0.95 * ppm_y))
ImageDraw.Draw(tag).text((20, 4), "BIGI 44PG!", font=tf, fill=(21, 21, 21, 235))
tag = tag.resize((int(u(-13.6) - u(-5.0)), tag.height), Image.LANCZOS)
tag = tag.transform(tag.size, Image.AFFINE, (1, 0.28, -20, 0, 1, 0), resample=Image.BICUBIC)   # kursiv
tag = tag.rotate(-2.5, resample=Image.BICUBIC, expand=True)
img.alpha_composite(tag, (int(u(-5.0)), int(v(44.6))))

# Verwitterung: fleckiges Ausbleichen, abgeplatzte Stellen, Schmutz von oben
noise = Image.effect_noise((W // 8, H // 8), 64).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
fine = Image.effect_noise((W // 2, H // 2), 90).resize((W, H), Image.BILINEAR)
a = img.getchannel("A")
px_a = a.load()
pn = noise.load()
pf = fine.load()
rgb = img.convert("RGB")
pr = rgb.load()
for yy in range(H):
    streak = 0.92 + 0.08 * (yy / H)
    for xx in range(0, W):
        al = px_a[xx, yy]
        if al == 0:
            continue
        n1 = pn[xx, yy] / 255.0
        n2 = pf[xx, yy] / 255.0
        fade = 0.80 + 0.2 * n1
        if n2 > 0.86:
            fade *= 0.55                # abgeplatzt
        r, g, b = pr[xx, yy]
        if r > 120:                     # weiße Füllung leicht vergraut/verschmutzt
            k = (0.88 + 0.1 * n1) * streak
            pr[xx, yy] = (int(r * k), int(g * k * 0.995), int(b * k * 0.985))
        px_a[xx, yy] = int(al * fade)
res = rgb.convert("RGBA")
res.putalpha(a)
res.save(out)
print("Graffiti gespeichert:", out, res.size, "Pixel/m", round(ppm_x, 1), round(ppm_y, 1))
