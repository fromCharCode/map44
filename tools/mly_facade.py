"""Fassadentextur einer Hauswand aus Mapillary-Rundumbildern (Prototyp).

  python tools/mly_facade.py <kachel> <x,z> [--out datei.jpg] [--ppm 40]

Sucht die Gebäudekante, die dem Punkt (Spielkoordinaten, auf der Straße vor dem Haus) am nächsten liegt, wählt das
Rundumbild (spherical), das möglichst mittig und frontal davor steht, und projiziert es auf das Wandrechteck
(Kante × Traufhöhe). Kamerapose aus den von Mapillary berechneten Werten (computed_geometry, computed_rotation).
Token: ~/.config/map44/mapillary_token. Bilder: Mapillary, CC BY-SA 4.0 (Urheber je Bild im Ergebnis vermerkt).
"""
import argparse
import io
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
CACHE = ROOT / "data" / "raw" / "mapillary"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
TO_LL = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
UA = {"User-Agent": "map-data-research/1.0"}
FIELDS = "id,captured_at,camera_type,computed_geometry,geometry,computed_compass_angle,computed_rotation," \
         "computed_altitude,width,height,creator,thumb_2048_url,thumb_original_url"


def token():
    return (Path.home() / ".config" / "map44" / "mapillary_token").read_text().strip()


def get(url, binary=False, auth=True):
    h = dict(UA)
    if auth:
        h["Authorization"] = "OAuth " + token()
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=90) as r:
        d = r.read()
    return d if binary else json.loads(d.decode("utf-8"))


def images_near(x, z, radius):
    """Bilder im Umkreis (Spielkoordinaten); Antwort je Abfragekasten zwischengespeichert"""
    CACHE.mkdir(parents=True, exist_ok=True)
    e, n = x + ORIGIN_E, ORIGIN_N - z
    lo = TO_LL.transform(e - radius, n - radius)
    hi = TO_LL.transform(e + radius, n + radius)
    key = f"q_{round(x)}_{round(z)}_{round(radius)}.json"
    f = CACHE / key
    if f.exists():
        return json.loads(f.read_text())
    url = "https://graph.mapillary.com/images?" + urllib.parse.urlencode(
        {"fields": FIELDS, "bbox": f"{lo[0]:.6f},{lo[1]:.6f},{hi[0]:.6f},{hi[1]:.6f}", "limit": 2000})
    data = get(url).get("data", [])
    f.write_text(json.dumps(data))
    return data


def rodrigues(r):
    r = np.array(r, dtype=float)
    th = np.linalg.norm(r)
    if th < 1e-9:
        return np.eye(3)
    k = r / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)


def nearest_edge(city, x, z):
    best = None
    for b in city["buildings"]:
        if b.get("stacked") or float(b.get("eave", 0)) < 4.0:
            continue
        ring = b["rings"][0]
        for i in range(len(ring) - 1):
            a, c = np.array(ring[i][:2], float), np.array(ring[i + 1][:2], float)
            L = np.linalg.norm(c - a)
            if L < 5.0:
                continue
            t = np.clip(np.dot(np.array([x, z]) - a, c - a) / (L * L), 0, 1)
            d = np.linalg.norm(a + t * (c - a) - np.array([x, z]))
            if best is None or d < best[0]:
                best = (d, b, a, c)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tile")
    ap.add_argument("pos")
    ap.add_argument("--out", default="facade.jpg")
    ap.add_argument("--ppm", type=float, default=40.0)
    ap.add_argument("--cam_h", type=float, default=2.3, help="Kamerahöhe über Grund (m)")
    ap.add_argument("--image", default="", help="bestimmte Bild-ID erzwingen")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--fit", action="store_true", help="Abstand aus der Trauflinie übernehmen")
    a = ap.parse_args()
    x, z = (float(v) for v in a.pos.split(","))
    city = json.loads((TILES / a.tile / "city.json").read_text(encoding="utf-8"))
    d, b, p0, p1 = nearest_edge(city, x, z)
    # Reihenfolge so, dass p0 -> p1 für den Betrachter (auf der Seite des Punktes) von links nach rechts läuft
    dirv = (p1 - p0) / np.linalg.norm(p1 - p0)
    nrm = np.array([-dirv[1], dirv[0]])                    # dir × up in (x, z): (-dz, dx) – zeigt zum Betrachter
    if np.dot(np.array([x, z]) - (p0 + p1) / 2, nrm) < 0:
        p0, p1 = p1, p0
        dirv = -dirv
        nrm = -nrm
    L = float(np.linalg.norm(p1 - p0))
    H = float(b["eave"])
    mid = (p0 + p1) / 2
    print(f"Gebäude {b['id']} Stil {b['style']} Kante {L:.1f} m × {H:.1f} m, Abstand zum Punkt {d:.1f} m")

    cands = []
    for im in images_near(float(mid[0]), float(mid[1]), 45.0):
        if im.get("camera_type") != "spherical" or not im.get("computed_rotation"):
            continue
        g = (im.get("computed_geometry") or im["geometry"])["coordinates"]
        e, n = TO_UTM.transform(g[0], g[1])
        c = np.array([e - ORIGIN_E, -(n - ORIGIN_N)])
        dist = float(np.dot(c - mid, nrm))                 # senkrechter Abstand vor der Wand
        along = float(np.dot(c - mid, dirv))
        if a.debug:
            print(im['id'], round(dist, 1), round(along, 1))
        if dist < 4.0 or dist > 30.0 or abs(along) > L * 0.5 + 4.0:
            continue
        # frontal und nicht zu nah: Blickwinkel zu den Wandenden klein halten
        score = abs(along) / max(L, 1.0) + abs(dist - max(8.0, L * 0.6)) / 20.0 - 0.02 * (im["captured_at"] / 3.15e10 - 54.0)
        cands.append((score, im, c, dist, along))
    if a.image:
        cands = [c for c in cands if c[1]["id"] == a.image]
    if not cands:
        print("kein passendes Rundumbild")
        return
    cands.sort(key=lambda c_: c_[0])
    print(f"{len(cands)} Kandidaten; beste: " + ", ".join(f"{c[1]['id']} d={c[3]:.1f} a={c[4]:+.1f}" for c in cands[:4]))
    _, im, c, dist, along = cands[0]
    f = CACHE / f"{im['id']}.jpg"
    if not f.exists():
        f.write_bytes(get(im.get("thumb_original_url") or im["thumb_2048_url"], binary=True, auth=False))
    pano = np.asarray(Image.open(f).convert("RGB"))
    ph, pw = pano.shape[:2]
    R = rodrigues(im["computed_rotation"])                 # Welt (Ost, Nord, oben) -> Kamera (rechts, unten, vorn)
    # Abstand aus der Trauflinie: die berechnete Bildposition ist in Straßenschluchten oft mehrere Meter falsch.
    # Entlang senkrechter Schnitte vor der Wand wird von oben die Grenze Himmel/Bauwerk gesucht; aus ihrem
    # Höhenwinkel und der bekannten Traufhöhe folgt der wahre Abstand: D = (H − Kamerahöhe) / tan(Winkel).
    est = []
    hsv = np.asarray(Image.fromarray(pano).convert("HSV")).astype(float)
    for t_ in np.linspace(-0.35, 0.35, 15):
        base = (p0 + dirv * (L * (0.5 + t_))) - c          # Fußpunkt der Wand in diesem Schnitt, relativ zur Kamera
        dh = float(np.hypot(base[0], base[1]))
        hdir = base / dh
        prev_sky = True
        for el in np.radians(np.arange(85.0, 5.0, -0.5)):
            v = np.array([hdir[0] * math.cos(el), -hdir[1] * math.cos(el), math.sin(el)]) @ R.T
            lon_ = math.atan2(v[0], v[2])
            lat_ = math.atan2(-v[1], math.hypot(v[0], v[2]))
            qx = int((lon_ / (2 * math.pi) + 0.5) * pw) % pw
            qy = min(max(int((0.5 - lat_ / math.pi) * ph), 0), ph - 1)
            hh, ss, vv_ = hsv[qy, qx]
            sky = vv_ > 150 and (ss < 45 or 130 < hh < 185)        # hell und (grau/weiß oder blau)
            if not sky:
                if prev_sky and el < math.radians(84.0):
                    est.append((H - a.cam_h) / math.tan(el) * (dist / dh))   # auf senkrechten Abstand umgerechnet
                break
            prev_sky = sky
    if est:
        d_est = float(np.median(est))
        print(f"Abstand laut Pose {dist:.1f} m, laut Trauflinie {d_est:.1f} m (aus {len(est)} Schnitten, Streuung {np.std(est):.1f})")
        if a.fit and 2.0 < d_est < 40.0:
            c = c + nrm * (dist - d_est) * -1.0 if False else (mid + dirv * along + nrm * d_est)
            dist = d_est
    w, h = int(L * a.ppm), int(H * a.ppm)
    us = (np.arange(w) + 0.5) / a.ppm
    vs = H - (np.arange(h) + 0.5) / a.ppm                  # Höhe über dem Wandfuß
    uu, vv = np.meshgrid(us, vs)
    # Weltpunkt relativ zur Kamera in ENU: Ost = x, Nord = -z; Wandfuß und Kamerafuß auf gleicher Höhe angenommen
    px = p0[0] + dirv[0] * uu - c[0]
    pz = p0[1] + dirv[1] * uu - c[1]
    rel = np.stack([px, -pz, vv - a.cam_h], axis=-1)
    cam = rel @ R.T
    lon = np.arctan2(cam[..., 0], cam[..., 2])
    lat = np.arctan2(-cam[..., 1], np.hypot(cam[..., 0], cam[..., 2]))
    sx = ((lon / (2 * math.pi) + 0.5) * pw).astype(int) % pw
    sy = np.clip(((0.5 - lat / math.pi) * ph).astype(int), 0, ph - 1)
    out = pano[sy, sx]
    Image.fromarray(out).save(a.out, quality=90)
    who = (im.get("creator") or {}).get("username", "?")
    print(f"{a.out}: {w}×{h} px aus Bild {im['id']} ({pw}×{ph}, Abstand {dist:.1f} m, seitlich {along:+.1f} m), Urheber {who}")
    print(json.dumps({"a": [round(float(p0[0]), 2), round(float(p0[1]), 2)], "b": [round(float(p1[0]), 2), round(float(p1[1]), 2)], "h": H}))


if __name__ == "__main__":
    main()
