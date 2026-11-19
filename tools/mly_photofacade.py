"""Fotofassaden: entzerrte Fassadentextur einer Hauswand aus einem Mapillary-Rundumbild (Prototyp).

Die Bilddrehung ist zuverlässig, die Position nicht. Deshalb: Ansicht senkrecht auf die Wand rechnen (nur Drehung
nötig), darin die seitlichen Hauskanten suchen (starker senkrechter Farbwechsel nahe der Lage laut Pose). Aus der
bekannten Wandlänge folgt der wahre Abstand d = L / (tan_rechts − tan_links) und damit Trauf- und Bodenlinie.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mly_facade as mf                                           # noqa: E402
import mly_windows as mw                                          # noqa: E402
import dds_bc1                                                    # noqa: E402

N = 1024
TH, TU, TD = 1.6, 1.9, 0.35                                       # Bildfeld der Suchansicht in tan-Einheiten


def project(im, cam, pw, ph):
    """Kamerastrahlen (rechts, unten, vorn) -> Bildkoordinaten (fx, fy) und Gültigkeit. Rundumbild: Kugelabbildung;
    normales Bild: Lochkamera mit radialer Verzeichnung (Mapillary camera_parameters = Brennweite/max(B,H), k1, k2)."""
    if im is None or im.get("camera_type") == "spherical":
        lon = np.arctan2(cam[..., 0], cam[..., 2])
        lat = np.arctan2(-cam[..., 1], np.hypot(cam[..., 0], cam[..., 2]))
        fx = (lon / (2 * math.pi) + 0.5) * pw - 0.5
        fy = np.clip((0.5 - lat / math.pi) * ph - 0.5, 0, ph - 1.001)
        return fx, fy, np.ones(fx.shape, bool)
    f, k1, k2 = (list(im.get("camera_parameters") or [0.7, 0.0, 0.0]) + [0.0, 0.0])[:3]
    z = cam[..., 2]
    ok = z > 0.05
    zs = np.where(ok, z, 1.0)
    xn, yn = cam[..., 0] / zs, cam[..., 1] / zs
    r2 = xn * xn + yn * yn
    dist = 1.0 + k1 * r2 + k2 * r2 * r2
    fpx = f * max(pw, ph)
    fx = pw / 2.0 + fpx * xn * dist - 0.5
    fy = ph / 2.0 + fpx * yn * dist - 0.5
    ok &= (r2 < 4.0) & (fx >= 0) & (fx <= pw - 1.001) & (fy >= 0) & (fy <= ph - 1.001)
    return np.clip(fx, 0, pw - 1.001), np.clip(fy, 0, ph - 1.001), ok


def is_pano(im):
    return im.get("camera_type") == "spherical"


def view(pano, R, nrm, th=None, tu=TU, td=TD, n=N, im=None):
    th = TH if th is None else th
    ph, pw = pano.shape[:2]
    fwd = np.array([-nrm[0], nrm[1], 0.0])
    fwd /= np.linalg.norm(fwd)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up)
    xs = (np.arange(n) + 0.5) / n * 2 * th - th
    ys = tu - (np.arange(n) + 0.5) / n * (tu + td)
    xx, yy = np.meshgrid(xs, ys)
    cam = (fwd[None, None, :] + xx[..., None] * right + yy[..., None] * up) @ R.T
    fx, fy, ok = project(im, cam, pw, ph)
    x0 = np.floor(fx).astype(int)
    y0 = np.floor(fy).astype(int)
    wx = (fx - x0)[..., None]
    wy = (fy - y0)[..., None]
    p = pano.astype(float)
    x1 = (x0 + 1) % pw if (im is None or is_pano(im)) else np.minimum(x0 + 1, pw - 1)
    a = p[y0, x0 % pw] * (1 - wx) + p[y0, x1] * wx
    b = p[y0 + 1, x0 % pw] * (1 - wx) + p[y0 + 1, x1] * wx
    out = (a * (1 - wy) + b * wy).astype(np.uint8)
    out[~ok] = 128                                               # außerhalb des Bildes: neutrales Grau
    return out


def fit(img, L, H, d_pose, along, cam_h, TH=TH):
    """Abstand und seitliche Lage der Wand im entzerrten Bild: Suche über (d, Versatz). Bewertet werden die beiden
    Hauskanten (senkrechter Farbwechsel im oberen Wandbereich) und die Trauflinie (darüber Himmel, darunter Wand)."""
    n = img.shape[1]
    px = 2 * TH / n
    py = (TU + TD) / n
    f = img.astype(float)
    mx, mn = f.max(2), f.min(2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    sky = ((mx > 150) & ((sat < 0.16) | (f[..., 2] > f[..., 0] * 1.08))).astype(float)
    r0, r1 = int(n * (TU - 1.0) / (TU + TD)), int(n * (TU - 0.25) / (TU + TD))
    k = max(3, int(0.012 / px))
    col = f[r0:r1].mean(0)
    cs = np.cumsum(np.vstack([np.zeros((1, 3)), col]), 0)
    edge = np.zeros(n)
    edge[k:n - k] = np.abs((cs[2 * k:n] - cs[k:n - k]) / k - (cs[k:n - k] - cs[0:n - 2 * k]) / k).sum(1)
    edge = np.minimum(edge / 120.0, 1.0)
    skc = np.cumsum(np.vstack([np.zeros((1, n)), sky]), 0)       # Himmel aufsummiert je Spalte (für Rechteckmittel)
    best = None
    for d in d_pose * np.linspace(0.6, 1.7, 34):
        top = (H - cam_h) / d
        if top > TU - 0.2:
            continue
        rt = int((TU - top) / py)
        ra, rb = max(0, rt - int(0.14 / py)), min(n - 1, rt + int(0.14 / py))
        for sh in np.linspace(-4.0, 4.0, 21):
            xl, xr = (-L / 2 - along - sh) / d, (L / 2 - along - sh) / d
            cl, cr = int((xl + TH) / px), int((xr + TH) / px)
            if cl < k + 2 or cr > n - k - 2 or cr - cl < 20:
                continue
            ci, cj = cl + (cr - cl) // 6, cr - (cr - cl) // 6
            above = (skc[rt, ci:cj] - skc[ra, ci:cj]).mean() / max(rt - ra, 1)
            below = (skc[rb, ci:cj] - skc[rt, ci:cj]).mean() / max(rb - rt, 1)
            el = edge[cl - 2:cl + 3].max()
            er = edge[cr - 2:cr + 3].max()
            score = el + er + 1.6 * (above - below) - 0.25 * abs(math.log(d / d_pose)) - 0.03 * abs(sh)
            if best is None or score > best[0]:
                best = (score, d, sh, float(el), float(er), float(above - below))
    return best


def pano_orig(im):
    """Rundumbild in Originalgröße (für die endgültige Textur), zwischengespeichert; None, wenn nicht abrufbar"""
    f = mf.CACHE / f"{im['id']}_orig.jpg"
    if not f.exists():
        try:
            url = im.get("thumb_original_url")
            try:
                data = mf.get(url, binary=True, auth=False) if url else None
            except Exception:                                    # noqa: BLE001 – Adresse abgelaufen
                data = None
            if data is None:
                d = mf.get(f"https://graph.mapillary.com/{im['id']}?fields=thumb_original_url")
                data = mf.get(d["thumb_original_url"], binary=True, auth=False)
            f.write_bytes(data)
        except Exception:                                        # noqa: BLE001
            return None
    try:
        return np.asarray(Image.open(f).convert("RGB"))
    except Exception:                                            # noqa: BLE001
        return None


def facade(im, c, p0, p1, H, cam_h=2.3, ppm=28.0, fixed=None):
    """fixed = (d, Versatz): Anpassung überspringen und mit dem Originalbild in voller Auflösung abtasten"""
    """(Texturbild, Info) oder (None, Grund). p0 -> p1 läuft für den Betrachter von links nach rechts."""
    L = float(np.linalg.norm(p1 - p0))
    dirv = (p1 - p0) / L
    nrm = np.array([-dirv[1], dirv[0]])
    off = c - (p0 + p1) / 2
    d_pose = float(off @ nrm)
    along = float(off @ dirv)
    if d_pose < 3.0:
        return None, "Kamera hinter/zu nah an der Wand"
    R = mf.rodrigues(im["computed_rotation"])
    pano = mw.pano_2048(im)
    th = TH if is_pano(im) else 3.2                              # normale Bilder sehen die Wand meist schräg von vorn
    img = view(pano, R, nrm, th=th, im=im) if fixed is None else None
    xl, xr = (-L / 2 - along) / d_pose, (L / 2 - along) / d_pose
    if xl < -th * 0.95 or xr > th * 0.95:
        return None, "Wand nicht im Bildfeld"
    if fixed is None:
        bf = fit(img, L, H, d_pose, along, cam_h, TH=th)
        if bf is None:
            return None, "Traufe oberhalb des Bildfelds (zu nah)"
    else:
        bf = (0.0, fixed[0], fixed[1], 1.0, 1.0, 1.0)
        big = pano_orig(im)
        if big is not None and big.shape[1] > pano.shape[1]:
            pano = big
    score, d, sh, sl, sr, skyq = bf
    el, er = (-L / 2 - along - sh) / d, (L / 2 - along - sh) / d
    top, bot = (H - cam_h) / d, -cam_h / d
    w, h = max(64, int(L * ppm)), max(64, int(H * ppm))
    # zweite, genaue Abtastung nur des Wandrechtecks
    ph, pw = pano.shape[:2]
    fwd = np.array([-nrm[0], nrm[1], 0.0])
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up)
    xs = el + (np.arange(w) + 0.5) / w * (er - el)
    ys = top - (np.arange(h) + 0.5) / h * (top - bot)
    xx, yy = np.meshgrid(xs, ys)
    cam = (fwd[None, None, :] + xx[..., None] * right + yy[..., None] * up) @ R.T
    fx, fy, ok = project(im, cam, pw, ph)
    if ok.mean() < 0.985:
        return None, "Wand nicht ganz im Bild"
    sx = np.clip((fx + 0.5).astype(int), 0, pw - 1) % pw
    sy = np.clip((fy + 0.5).astype(int), 0, ph - 1)
    tex = pano[sy, sx]
    return tex, {"d": float(d), "d_pose": round(d_pose, 1), "versatz": float(sh), "guete": round(float(score), 2),
                 "kanten": [round(sl, 2), round(sr, 2)], "traufe": round(skyq, 2)}


def wall_runs(ring, min_len=7.0):
    """gerade Wandzüge eines Grundrisses: aufeinanderfolgende Kanten mit < 6° Richtungswechsel zusammengefasst"""
    pts = [np.array(q[:2], float) for q in ring[:-1]] if len(ring) > 3 else []
    n = len(pts)
    if n < 3:
        return []
    dirs = []
    for i in range(n):
        v = pts[(i + 1) % n] - pts[i]
        ln = np.linalg.norm(v)
        dirs.append(v / ln if ln > 1e-6 else np.zeros(2))
    start = 0
    for i in range(n):                                           # an einer echten Ecke beginnen
        if float(dirs[i - 1] @ dirs[i]) < 0.9945:
            start = i
            break
    runs, a = [], start
    for step in range(1, n + 1):
        i = (start + step) % n
        if step == n or float(dirs[i - 1] @ dirs[i]) < 0.9945:
            q0, q1 = pts[a], pts[i]
            if np.linalg.norm(q1 - q0) >= min_len:
                runs.append((q0, q1))
            a = i
    return runs


def tex_ok(tex, ppm=28.0):
    """Plausibilität der fertigen Textur: wenig Laub davor, Geschosshöhe 2,4–5,2 m (aus der senkrechten Wiederholung
    der Fensterreihen). Zu stark vergrößerte Ausschnitte zeigen riesige Fenster und fallen hier durch.
    Liefert (ok, Grund)."""
    f = tex.astype(float)
    mx, mn = f.max(2), f.min(2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    green = (f[..., 1] > f[..., 0] * 1.06) & (f[..., 1] > f[..., 2] * 1.06) & (sat > 0.2)
    h = tex.shape[0]
    if green[: int(h * 0.8)].mean() > 0.16:
        return False, "Laub"
    # Himmel in der Wandfläche = Ausschnitt verrutscht (Dach, Lücke, Nachbarhaus)
    # (nur blauer Himmel – bedeckter Himmel ist von hellem Putz nicht zu unterscheiden)
    sky = (mx > 150) & (f[..., 2] > f[..., 0] * 1.18) & (f[..., 2] > f[..., 1] * 1.04) & (sat > 0.18)
    if sky[: int(h * 0.5)].mean() > 0.06:
        return False, "Himmel im Ausschnitt"
    g = f.mean(2)[: int(h * 0.85)]
    dark = (g < np.median(g) - 22.0).astype(float)
    if not 0.03 < dark.mean() < 0.55:
        return False, "keine Fenster"
    per, strength = mw._period(dark.mean(1), int(2.2 * ppm), min(int(6.5 * ppm), len(g) // 2))
    if per == 0 or strength < 0.12:
        return len(g) / ppm < 7.5, "keine Geschossteilung"       # niedrige Wände dürfen ohne Wiederholung sein
    fh = per / ppm
    return 2.4 <= fh <= 5.2, f"Geschosshöhe {fh:.1f} m"


def brighten(tex):
    """Belichtung angleichen: Fotos zeigen die Wand oft im Schatten; im Spiel wird sie ohnehin noch einmal beleuchtet
    bzw. verschattet. Helle Wandteile (90. Perzentil) auf ~0,74 anheben, höchstens ×1,9."""
    f = tex.astype(np.float32) / 255.0
    p90 = float(np.percentile(f.max(2), 90))
    gain = min(max(0.74 / max(p90, 0.05), 1.0), 1.9)
    return np.clip(f * gain * 255.0, 0, 255).astype(np.uint8)


def good(info):
    """strenge Annahme: beide Hauskanten deutlich und Trauflinie gefunden"""
    if min(info["kanten"]) >= 0.55 and info["traufe"] >= 0.15:
        return True
    # zweite Annahme (Häuserzeilen ohne sichtbare Hauskante, z. B. Blockrand): Trauflinie deutlich gefunden und der
    # daraus bestimmte Abstand passt zur Bildposition (±15 %) – dann stimmt auch die Lage entlang der Wand ungefähr
    return info["traufe"] >= 0.5 and abs(math.log(max(info["d"], 0.1) / max(info["d_pose"], 0.1))) < 0.14 \
        and abs(info.get("versatz", 0.0)) <= 1.6


def tile_facades(name, max_cand=3, budget=None):
    import os
    budget = int(os.environ.get("PF_BUDGET", "500")) if budget is None else budget
    """Fotofassaden einer Kachel: data/processed/tiles/<kachel>/facades/*.jpg + facades.json
    [{"a": [x, z], "b": [x, z], "h": Wandhöhe, "tex": Datei, "gid": Gebäude, "bild": Mapillary-ID, "von": Urheber}]"""
    import json
    import mly_colors as mc
    from shapely.geometry import LineString, Point, Polygon
    from shapely.strtree import STRtree
    tdir = mf.TILES / name
    city = json.loads((tdir / "city.json").read_text(encoding="utf-8"))
    feet, blds = [], []
    for b in city["buildings"]:
        try:
            pg = Polygon([(q[0], q[1]) for q in b["rings"][0]])
        except (ValueError, IndexError, KeyError, TypeError):
            continue
        if pg.is_valid and pg.area > 20 and not b.get("stacked"):
            feet.append(pg)
            blds.append(b)
    if not feet:
        return
    tree = STRtree(feet)
    # Normale Kamerabilder (PF_KAMERA=1) sind technisch möglich, liefern aber fast nur verdeckte oder verrutschte
    # Ausschnitte (Probe 11/2026: 2 von 3 angenommenen unbrauchbar) – Standard sind deshalb nur Rundumbilder.
    kamera = os.environ.get("PF_KAMERA") == "1"
    images = [t for t in mc.tile_images(name) if t[0].get("computed_rotation") and
              (is_pano(t[0]) or (kamera and t[0].get("camera_type") == "perspective" and t[0].get("camera_parameters")
                                 and t[0].get("width") and t[0].get("height")))]
    if not images:
        print(f"  {name}: keine Bilder", flush=True)
        return
    pts = STRtree([Point(c[0], c[1]) for _, c in images])
    out_dir = tdir / "facades"
    out_dir.mkdir(exist_ok=True)
    # 1. Schritt (ohne Bildabruf): je Wand die geometrisch passenden Bilder. Rundumbilder stehen vor der Wand; normale
    # Kamerabilder sehen sie schräg von vorn – die vier Wandecken müssen dann im Bild liegen.
    jobs = []
    for b in blds:
        H = float(b["eave"])
        if H < 5.0 or b.get("elev"):
            continue
        for q0, q1 in wall_runs(b["rings"][0], 6.5):
            L = float(np.linalg.norm(q1 - q0))
            if L > 60.0:
                continue
            mid, dirv = (q0 + q1) / 2, (q1 - q0) / L
            nrm = np.array([-dirv[1], dirv[0]])
            cands = []
            for k in pts.query(Point(mid[0], mid[1]).buffer(45.0)):
                im, c = images[k]
                off = c - mid
                dist = float(off @ nrm)
                al = abs(float(off @ dirv))
                pano = is_pano(im)
                if pano:
                    if not 4.5 <= abs(dist) <= 24.0 or al > L * 0.45:
                        continue
                else:
                    if not 5.0 <= abs(dist) <= 26.0 or (al + L / 2) / abs(dist) > 2.9 or al / abs(dist) > 1.3:
                        continue
                    R = mf.rodrigues(im["computed_rotation"])
                    cor = []
                    for q in (q0, q1):
                        for hh in (0.3 - 2.3, H - 2.3 + 0.4):
                            cor.append([q[0] - c[0], -(q[1] - c[1]), hh])
                    fx, fy, okc = project(im, np.array(cor) @ R.T, float(im["width"]), float(im["height"]))
                    mx_, my_ = 0.02 * im["width"], 0.02 * im["height"]
                    if not okc.all() or fx.min() < mx_ or fx.max() > im["width"] - mx_ or fy.min() < my_ or fy.max() > im["height"] - my_:
                        continue
                    if (fx.max() - fx.min()) < 0.12 * im["width"]:
                        continue                                  # Wand zu klein im Bild
                sight = LineString([tuple(c), tuple(mid + off / np.linalg.norm(off) * 0.6)])
                if any(feet[j].intersects(sight) for j in tree.query(sight)):
                    continue
                # ideal: etwa Wandhöhe als Abstand, möglichst frontal, neuere Bilder; Rundumbilder bevorzugt
                sc = abs(abs(dist) - max(H * 0.9, 8.0)) / 12.0 + (al / L if pano else 0.25 + 0.35 * al / abs(dist)) \
                    - 0.03 * (im["captured_at"] / 3.15e10 - 54.0)
                cands.append((sc, k, dist > 0))
            if cands:
                cands.sort()
                jobs.append((not any(is_pano(images[k][0]) for _, k, _ in cands[:max_cand]), -L * H, b, q0, q1, H, L, cands[:max_cand]))
    jobs.sort(key=lambda j: (j[0], j[1]))
    for f in list(out_dir.glob("*.jpg")) + list(out_dir.glob("*.dds")):
        f.unlink()
    res, tried = [], 0
    for _, _, b, q0, q1, H, L, cands in jobs:
        if tried >= budget:
            break
        if True:
            best = None
            for _, k, front in cands:
                im, c = images[k]
                p0, p1 = (q0, q1) if front else (q1, q0)
                try:
                    tex, info = facade(im, c, p0, p1, H)
                except Exception as ex:                              # noqa: BLE001 – einzelnes Bild defekt
                    print("  Fehler", im["id"], ex, flush=True)
                    continue
                tried += 1
                if tex is not None and good(info) and tex_ok(tex)[0] and (best is None or info["guete"] > best[1]["guete"]):
                    best = (tex, info, im, p0, p1)
                    if is_pano(im):
                        break
            if best:
                tex, info, im, p0, p1 = best
                # endgültige Textur aus dem Originalbild (schärfer), mit der gefundenen Lage
                c_im = next(c_ for i_, c_ in images if i_["id"] == im["id"])
                try:
                    hi, _ = facade(im, c_im, p0, p1, H, ppm=48.0 if is_pano(im) else 40.0, fixed=(info["d"], info["versatz"]))
                    if hi is not None:
                        tex = hi
                except Exception as ex:                              # noqa: BLE001
                    print("  Fehler (Original)", im["id"], ex, flush=True)
                fn = f"{len(res):04d}.dds"
                dds_bc1.save_dds(Image.fromarray(brighten(tex)), out_dir / fn)
                res.append({"a": [round(float(p0[0]), 2), round(float(p0[1]), 2)], "b": [round(float(p1[0]), 2), round(float(p1[1]), 2)],
                            "h": round(H, 2), "tex": fn, "gid": b.get("gid") or b["id"], "bild": im["id"],
                            "von": (im.get("creator") or {}).get("username", ""), "art": "rundum" if is_pano(im) else "kamera"})
    (tdir / "facades.json").write_text(json.dumps(res, separators=(",", ":")), encoding="utf-8")
    print(f"  {name}: {len(res)} Fotofassaden ({sum(1 for r in res if r['art'] == 'kamera')} aus normalen Bildern) aus {tried} "
          f"Auswertungen, {len(jobs)} Wände mit passendem Bild ({len(images)} Bilder)", flush=True)


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "tile":
    for nm in sys.argv[2:]:
        tile_facades(nm.replace(",", "_"))
    sys.exit(0)

if __name__ == "__main__":
    import json
    import mly_colors as mc
    from shapely.geometry import LineString, Polygon
    from shapely.strtree import STRtree
    tile, x, z, radius, outdir = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    city = json.loads((mf.TILES / tile / "city.json").read_text(encoding="utf-8"))
    feet, blds = [], []
    for b in city["buildings"]:
        pg = Polygon([(q[0], q[1]) for q in b["rings"][0]])
        if pg.is_valid and pg.area > 20 and not b.get("stacked"):
            feet.append(pg)
            blds.append(b)
    tree = STRtree(feet)
    images = [t for t in mc.load_images(x, z, radius + 30.0, True) if t[0].get("camera_type") == "spherical"]
    n = 0
    for b in blds:
        if math.hypot(b["pos"][0] - x, b["pos"][1] - z) > radius or float(b["eave"]) < 8.0:
            continue
        ring = b["rings"][0]
        best = None
        for q0, q1 in wall_runs(ring, 8.0):
            L = float(np.linalg.norm(q1 - q0))
            mid, dirv = (q0 + q1) / 2, (q1 - q0) / L
            nrm = np.array([-dirv[1], dirv[0]])
            for im, c in images:
                off = c - mid
                dist = float(off @ nrm)
                p0, p1 = (q0, q1) if dist > 0 else (q1, q0)
                dist = abs(dist)
                if dist < 5.0 or dist > 22.0 or abs(float(off @ dirv)) > L * 0.3:
                    continue
                sight = LineString([tuple(c), tuple(mid + (c - mid) / np.linalg.norm(c - mid) * 0.6)])
                if any(feet[j].intersects(sight) for j in tree.query(sight)):
                    continue
                sc = abs(dist - 12.0) / 12.0 + abs(float(off @ dirv)) / L
                if best is None or sc < best[0]:
                    best = (sc, im, c, p0, p1)
        if best is None:
            continue
        _, im, c, p0, p1 = best
        tex, info = facade(im, c, p0, p1, float(b["eave"]))
        n += 1
        if tex is None:
            print(f"{n:02d} {b['id']}: {info}")
        else:
            Image.fromarray(tex).save(f"{outdir}/f_{n:02d}.jpg", quality=88)
            info = {k: (float(v) if not isinstance(v, list) else v) for k, v in info.items()}
            print(f"{n:02d} {'GUT ' if good(info) else '    '}{b['id']} L {np.linalg.norm(p1 - p0):.0f} H {b['eave']}: {info}")
        if n >= 24:
            break
