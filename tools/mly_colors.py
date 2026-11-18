"""Echte Wandfarben aus Mapillary-Rundumbildern (Prototyp/Bibliothek).

Für eine Gebäudekante wird aus dem nächsten frei sichtbaren Rundumbild die häufigste Farbe der Wandfläche bestimmt
(ohne Himmel, Grün und dunkle Fenster). Das verträgt die Lagefehler der Bilder (mehrere Meter), an denen eine
vollständige Fototextur scheitert. Bilder: Mapillary, CC BY-SA 4.0.
"""
import colorsys
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mly_facade as mf                                           # noqa: E402


def pano_small(im):
    """1024er Vorschau (reicht für Farben), zwischengespeichert"""
    f = mf.CACHE / f"{im['id']}_1024.jpg"
    if not f.exists():
        url = im.get("thumb_1024_url")
        try:
            data = mf.get(url, binary=True, auth=False) if url else None
        except Exception:                                  # noqa: BLE001 – Adresse abgelaufen: neu erfragen
            data = None
        if data is None:
            d = mf.get(f"https://graph.mapillary.com/{im['id']}?fields=thumb_1024_url")
            data = mf.get(d["thumb_1024_url"], binary=True, auth=False)
        f.write_bytes(data)
    return np.asarray(Image.open(f).convert("RGB"))


def wall_colour(pano, R, c, p0, p1, H, cam_h=2.3, persp=None):
    """häufigste Wandfarbe (r, g, b 0..255) und Anteil gültiger Pixel"""
    ph, pw = pano.shape[:2]
    L = float(np.linalg.norm(p1 - p0))
    dirv = (p1 - p0) / L
    us = np.linspace(0.2, 0.8, 40) * L
    vs = np.linspace(3.5, max(4.5, min(H - 1.0, 14.0)), 24)
    uu, vv = np.meshgrid(us, vs)
    rel = np.stack([p0[0] + dirv[0] * uu - c[0], -(p0[1] + dirv[1] * uu - c[1]), vv - cam_h], axis=-1)
    cam = rel @ R.T
    if persp is None:
        lon = np.arctan2(cam[..., 0], cam[..., 2])
        lat = np.arctan2(-cam[..., 1], np.hypot(cam[..., 0], cam[..., 2]))
        sx = ((lon / (2 * math.pi) + 0.5) * pw).astype(int) % pw
        sy = np.clip(((0.5 - lat / math.pi) * ph).astype(int), 0, ph - 1)
        px = pano[sy, sx].reshape(-1, 3).astype(float) / 255.0
    else:
        # Lochkamera mit radialer Verzeichnung (OpenSfM: Brennweite und Bildkoordinaten auf die längere Seite normiert)
        f_, k1, k2 = persp
        zc = cam[..., 2]
        front = zc > 0.5
        xn = np.where(front, cam[..., 0] / np.maximum(zc, 0.5), 9.0)
        yn = np.where(front, cam[..., 1] / np.maximum(zc, 0.5), 9.0)
        r2 = xn * xn + yn * yn
        dd = 1.0 + k1 * r2 + k2 * r2 * r2
        m = float(max(pw, ph))
        sxf = f_ * dd * xn * m + pw * 0.5
        syf = f_ * dd * yn * m + ph * 0.5
        inside = front & (sxf >= 2) & (sxf < pw - 2) & (syf >= 2) & (syf < ph - 2) & (r2 < 2.5)
        if inside.sum() < 120:
            return None, 0.0
        px = pano[syf[inside].astype(int), sxf[inside].astype(int)].astype(float) / 255.0
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    green = (px[:, 1] > px[:, 0] * 1.06) & (px[:, 1] > px[:, 2] * 1.06) & (sat > 0.2)
    blue_sky = (px[:, 2] > px[:, 0] * 1.15) & (mx > 0.55)
    ok = (mx > 0.36) & ~green & ~blue_sky & ~((mx > 0.93) & (sat < 0.06))
    good = px[ok]
    if len(good) < 60:
        return None, len(good) / len(px)
    q = (good * 11.999).astype(int)
    keys = q[:, 0] * 144 + q[:, 1] * 12 + q[:, 2]
    vals, inv = np.unique(keys, return_inverse=True)
    # helle Flächen bevorzugen: Wände sind meist heller als Türen, Schatten, Stämme und geparkte Autos
    counts = np.bincount(inv, weights=0.35 + good.max(1))
    top = vals[np.argmax(counts)]
    # Nachbarklassen mitnehmen (Helligkeitsverlauf einer Wand verteilt sich auf mehrere Klassen)
    sel = np.abs(q - np.array([top // 144, (top // 12) % 12, top % 12])).max(1) <= 1
    col = np.percentile(good[sel], 65, axis=0)
    # Fotos zeigen die Wand meist im Schatten/unterbelichtet: Helligkeit maßvoll anheben, Farbton bleibt
    mxc = float(col.max())
    col = col * (min(0.86, mxc * 1.18 + 0.04) / max(mxc, 1e-3))
    return tuple(int(round(v * 255)) for v in col), float(sel.sum()) / len(px)


def plausible(col, share, pano):
    """Himmel (bläulich), Laub (grünlich) und Blüten/Planen (violett) verwerfen; Fotos brauchen mehr gültige Fläche"""
    r, g, b_ = (int(col[i:i + 2], 16) for i in (1, 3, 5))
    if b_ > r + 6 or g > r + 10 or (b_ > g + 8 and r > g):
        return False
    return share >= (0.12 if pano else 0.3)


def building_colour(b, images, footprints, tree):
    """Farbe der am besten einsehbaren Kante eines Gebäudes: (hex, güte, bild-id) oder None"""
    ring = b["rings"][0]
    best = None
    H = float(b["eave"])
    for i in range(len(ring) - 1):
        p0, p1 = np.array(ring[i][:2], float), np.array(ring[i + 1][:2], float)
        L = float(np.linalg.norm(p1 - p0))
        if L < 6.0:
            continue
        mid = (p0 + p1) / 2
        dirv = (p1 - p0) / L
        for im, c in images:
            off = c - mid
            dist = abs(float(off[0] * -dirv[1] + off[1] * dirv[0]))
            along = abs(float(off @ dirv))
            pers = im.get("camera_type") != "spherical"
            if dist < 3.5 or dist > 28.0 or along > (L * 0.5 + (22.0 if pers else 0.0)):
                continue
            if pers:
                # Fahrtrichtungskamera: die Wandmitte muss im Bild liegen (höchstens ~38° neben der Blickachse)
                fw = mf.rodrigues(im["computed_rotation"]).T @ np.array([0.0, 0.0, 1.0])
                to = np.array([-off[0], off[1]])            # Kamera -> Wandmitte in (Ost, Nord)
                cosang = float(to @ fw[:2]) / (np.linalg.norm(to) * max(np.linalg.norm(fw[:2]), 1e-6))
                if cosang < 0.78:
                    continue
            sight = LineString([tuple(c), tuple(mid + (c - mid) / np.linalg.norm(c - mid) * 0.6)])
            if any(footprints[j].intersects(sight) for j in tree.query(sight)):
                continue                                    # anderes Haus (oder das eigene) dazwischen
            score = dist / 28.0 + along / max(L, 1.0) + (0.6 if pers else 0.0)      # Rundumbild bevorzugt
            if best is None or score < best[0]:
                best = (score, im, c, p0, p1)
    if best is None:
        return None
    _, im, c, p0, p1 = best
    cp = im.get("camera_parameters") if im.get("camera_type") != "spherical" else None
    col, share = wall_colour(pano_small(im), mf.rodrigues(im["computed_rotation"]), c, p0, p1, H,
                             persp=cp if cp and len(cp) >= 3 else None)
    if col is None:
        return None
    hx = "#%02x%02x%02x" % col
    if not plausible(hx, share, cp is None):
        return None
    return hx, round(share, 2), im["id"]


def load_images(x, z, radius, pano_only=False):
    out = []
    for im in mf.images_near(x, z, radius, pano_only):
        ct = im.get("camera_type")
        if not im.get("computed_rotation") or not (ct == "spherical" or (ct == "perspective" and im.get("camera_parameters"))):
            continue
        g = (im.get("computed_geometry") or im["geometry"])["coordinates"]
        e, n = mf.TO_UTM.transform(g[0], g[1])
        out.append((im, np.array([e - mf.ORIGIN_E, -(n - mf.ORIGIN_N)])))
    return out


def tile_images(name):
    """alle Rundumbilder einer Kachel (250-m-Kästen, zwischengespeichert)"""
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - mf.ORIGIN_E, -((n_km + 2) * 1000.0 - mf.ORIGIN_N)
    seen, out = set(), []
    for i in range(8):
        for j in range(8):
            for po in (True, False):                        # Rundumbilder vollständig, dazu alle übrigen (bis 2000)
                for im, c in load_images(x0 + 125.0 + 250.0 * i, z0 + 125.0 + 250.0 * j, 135.0, po):
                    if im["id"] not in seen:
                        seen.add(im["id"])
                        out.append((im, c))
    return out


def tile_colours(name):
    cf = mf.TILES / name / "city.json"
    if not cf.exists():
        return
    out_f = mf.CACHE / f"colours_{name}.json"
    city = json.loads(cf.read_text(encoding="utf-8"))
    feet, blds = [], []
    for b in city["buildings"]:
        try:
            pg = Polygon([(q[0], q[1]) for q in b["rings"][0]])
        except (ValueError, IndexError, KeyError, TypeError):
            continue
        if pg.is_valid and pg.area > 20 and not b.get("stacked"):
            feet.append(pg)
            blds.append((pg.area, b))
    if not feet:
        return
    tree = STRtree(feet)
    images = tile_images(name)
    pts = STRtree([__import__("shapely.geometry", fromlist=["Point"]).Point(c[0], c[1]) for _, c in images]) if images else None
    res, done = {}, set()
    for _, b in sorted(blds, key=lambda t: -t[0]):                 # größtes Teil je Gebäude zuerst
        gid = b.get("gid") or b["id"]
        if gid in done or float(b["eave"]) < 5.0 or pts is None:
            continue
        near = [images[k] for k in pts.query(Polygon([(q[0], q[1]) for q in b["rings"][0]]).buffer(30.0))]
        try:
            r = building_colour(b, near, feet, tree) if near else None
        except Exception as ex:                                    # noqa: BLE001 – einzelnes Bild defekt
            print("  Fehler", b["id"], ex, flush=True)
            r = None
        if r:
            done.add(gid)
            res[gid] = [r[0], r[1], r[2]]
    out_f.write_text(json.dumps(res, separators=(",", ":")))
    print(f"  {name}: {len(res)} Gebäude mit Fotofarbe ({len(images)} Rundumbilder)", flush=True)


def apply(name):
    """Fotofarben in city.json übernehmen (nur wo OSM keine Farbe nennt und der Stil eine Putz-/Steinfarbe trägt)"""
    cf, f = mf.TILES / name / "city.json", mf.CACHE / f"colours_{name}.json"
    if not (cf.exists() and f.exists()):
        return 0
    res = json.loads(f.read_text())
    city = json.loads(cf.read_text(encoding="utf-8"))
    n = 0
    for b in city["buildings"]:
        r = res.get(b.get("gid") or b["id"])
        if r and int(b.get("style", 0)) in (0, 2, 3, 6) and not b.get("wall_osm") and plausible(r[0], r[1], r[1] < 0.3):
            if b.get("wall") != r[0]:
                b["wall"] = r[0]
                n += 1
    if n:
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    print(f"  {name}: {n} Wandfarben übernommen")
    return n


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] in ("fetch", "apply"):
    for nm in sys.argv[2:]:
        (tile_colours if sys.argv[1] == "fetch" else apply)(nm.replace(",", "_"))
    sys.exit(0)

if __name__ == "__main__":
    tile, x, z, radius = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    city = json.loads((mf.TILES / tile / "city.json").read_text(encoding="utf-8"))
    feet, blds = [], []
    for b in city["buildings"]:
        try:
            pg = Polygon([(q[0], q[1]) for q in b["rings"][0]])
        except (ValueError, IndexError):
            continue
        if pg.is_valid and pg.area > 20 and not b.get("stacked"):
            feet.append(pg)
            blds.append(b)
    tree = STRtree(feet)
    images = load_images(x, z, radius + 30.0)
    n = 0
    for b in blds:
        if math.hypot(b["pos"][0] - x, b["pos"][1] - z) > radius or float(b["eave"]) < 5.0:
            continue
        r = building_colour(b, images, feet, tree)
        n += 1
        print(b["id"], [round(v) for v in b["pos"]], "bisher", b["wall"], "Foto", r)
    print(n, "Gebäude geprüft,", len(images), "Rundumbilder")
