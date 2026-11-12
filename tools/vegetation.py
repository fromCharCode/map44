"""Vegetation aus DOM1 (nDSM) und Farb-Infrarot-Luftbild (NDVI) für eine Kachel.

Aufruf:  DRESDEN_TILE=410,5656 python vegetation.py   (nach build_city.py)
- Bäume: Kronenspitzen aus DOM1 - DGM1 außerhalb von Gebäuden/Brücken (Höhen echt)
- Rasen/Wald: splat1.png (R = Gras, G = Wald) wird aus NDVI/Kronendach ergänzt
Schreibt city.json["trees"] neu: [x, z, y, h, nadel, krone] und splat1.png.
"""
import json
import sys

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

from config import BASE_HEIGHT, BBOX_UTM, ORIGIN_E, ORIGIN_N, PROCESSED, RAW, TILE, TILE_NAME, USER_AGENT

Image.MAX_IMAGE_PIXELS = None
MIN_E, MIN_N, MAX_E, MAX_N = BBOX_UTM
SIZE = int(MAX_E - MIN_E)
CIR_WMS = "https://geodienste.sachsen.de/wms_geosn_dop-cir/guest"
MAX_TREES = 16000


def read_tif(prefix: str, e_km: int, n_km: int):
    d = RAW / ("dom" if prefix == "dom1" else "dgm") / f"{prefix}_33{e_km}_{n_km}_2_sn_tiff"
    f = next(iter(d.glob(f"{prefix}_*_sn.tif")))
    a = np.array(Image.open(f), dtype=np.float32)
    a[a < -1000] = np.nan
    return a


def fetch_cir() -> np.ndarray:
    out = RAW / "tiles" / TILE_NAME / "cir.jpg"
    if not out.exists() or out.stat().st_size < 100_000:
        params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": "sn_dop_020_cir", "STYLES": "",
                  "CRS": "EPSG:25833", "BBOX": f"{MIN_E},{MIN_N},{MAX_E},{MAX_N}", "WIDTH": SIZE, "HEIGHT": SIZE,
                  "FORMAT": "image/jpeg"}
        for attempt in range(5):
            try:
                r = requests.get(CIR_WMS, params=params, timeout=180, headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                    out.write_bytes(r.content)
                    break
            except requests.RequestException:
                pass
            import time
            time.sleep(4 * (attempt + 1))
        else:
            sys.exit("CIR nicht ladbar")
    return np.array(Image.open(out).convert("RGB"), dtype=np.float32)


def local_to_px(x: float, z: float):
    return (x - (MIN_E - ORIGIN_E), z + (MAX_N - ORIGIN_N))


def draw_mask(polys) -> np.ndarray:
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    for rings in polys:
        for i, r in enumerate(rings):
            pts = [local_to_px(p[0], p[1]) for p in r]
            if len(pts) >= 3:
                d.polygon(pts, fill=255 if i == 0 else 0)
    return im


def box_blur(a: np.ndarray, r: int) -> np.ndarray:
    k = 2 * r + 1
    ap = np.pad(a, r, mode="edge")
    c = np.cumsum(np.cumsum(ap, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def local_max(a: np.ndarray, r: int) -> np.ndarray:
    m = a.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            m = np.maximum(m, np.roll(a, (dy, dx), axis=(0, 1)))
    return m


# Baumkataster (Landeshauptstadt Dresden, dl-de/by-2-0) -> Spielmodell je Gattung
NEEDLE_GENERA = {"Pinus", "Picea", "Abies", "Larix", "Pseudotsuga", "Taxus", "Thuja", "Chamaecyparis", "Juniperus",
                 "Metasequoia", "Taxodium", "Cedrus", "Sequoiadendron", "Tsuga"}
SMALL_GENERA = {"Prunus", "Malus", "Sorbus", "Crataegus", "Pyrus", "Amelanchier", "Cornus", "Corylus", "Syringa",
                "Magnolia", "Cercis", "Rhus", "Ilex", "Laburnum"}
MODEL_BY_GENUS = {"Tilia": "tree_linden", "Acer": "tree_maple", "Platanus": "tree_plane", "Quercus": "tree_linden_b",
                  "Fraxinus": "tree_maple_b", "Aesculus": "tree_plane_b", "Carpinus": "tree_maple_b",
                  "Gleditsia": "tree_maple_b", "Sophora": "tree_maple_b", "Robinia": "tree_maple_b",
                  "Populus": "tree_linden_b", "Betula": "tree_small_b", "Ulmus": "tree_linden_b"}


def merge_kataster(trees, e_km, n_km, ter, street_mask):
    """Katasterbäume übernehmen (exakter Standort, Höhe, Art). Höhenmodell-Spitzen in der Nähe eines Katasterbaums
    entfallen; auf Straßen, Gehwegen und Plätzen ohne Katasterbaum ebenfalls (dort meist Schirme, Stände, Masten,
    Werbeträger – alle öffentlichen Straßenbäume stehen im Kataster). Außerhalb (Gärten, Wald) bleiben sie."""
    try:
        from strassenraum import trees_for_tile
        kat = trees_for_tile(e_km, n_km)
    except Exception as ex:  # pragma: no cover
        print(f"  Baumkataster nicht verfügbar: {ex}", flush=True)
        return trees
    if not kat:
        return trees
    from scipy.spatial import cKDTree
    kx = np.array([[k["x"], k["z"]] for k in kat])
    kt = cKDTree(kx)
    out = []
    dropped = 0
    for t in trees:
        d, _i = kt.query([t[0], t[1]], k=1)
        px_x = int(t[0] - (MIN_E - ORIGIN_E))
        px_y = int(t[1] + (MAX_N - ORIGIN_N))
        on_street = 0 <= px_y < SIZE and 0 <= px_x < SIZE and bool(street_mask[px_y, px_x])
        if d < max(3.5, t[5] * 0.6) or (on_street and d > 3.5):
            dropped += 1
            continue
        out.append(t)
    added = 0
    for k in kat:
        x, z = float(k["x"]), float(k["z"])
        px_x = int(x - (MIN_E - ORIGIN_E))
        px_y = int(z + (MAX_N - ORIGIN_N))
        if not (0 <= px_y < SIZE and 0 <= px_x < SIZE):
            continue
        genus = (k.get("art_bot") or "").split(" ")[0]
        h = float(k.get("hoehe_m") or 0.0)
        cr = float(k.get("krone_m") or 0.0)
        if h <= 0.5:
            h = max(3.0, cr * 1.4) if cr > 0 else 8.0
        h = min(max(h, 2.5), 38.0)
        needle = 1 if genus in NEEDLE_GENERA else 0
        model = ""
        if not needle:
            if genus in SMALL_GENERA or h < 6.5:
                model = "tree_small" if (hash(k.get("id", "")) & 1) else "tree_small_b"
            else:
                model = MODEL_BY_GENUS.get(genus, "")
        out.append([round(x, 1), round(z, 1), round(float(ter[px_y, px_x]), 2), round(h, 1), needle,
                    round(max(cr * 0.5, 1.0), 1), model])
        added += 1
    print(f"  Baumkataster: {added} Bäume übernommen, {dropped} Höhenmodell-Spitzen ersetzt/entfernt", flush=True)
    return out


def main() -> None:
    if not TILE:
        sys.exit("DRESDEN_TILE setzen")
    e_km, n_km = (int(v) for v in TILE.split(","))
    city = json.loads((PROCESSED / "city.json").read_text(encoding="utf-8"))
    dom = read_tif("dom1", e_km % 1000, n_km)
    dgm = read_tif("dgm1", e_km % 1000, n_km)
    pf = PROCESSED / "platform.f32"
    if pf.exists():   # Terrassen/Bastionen (platforms.py): Boden ist dort die Plattform, nicht das DGM
        pl = np.frombuffer(pf.read_bytes(), dtype="<f4").reshape(dgm.shape) + BASE_HEIGHT
        dgm = np.where(np.isfinite(pl), np.fmax(dgm, pl), dgm)
    ndsm = np.nan_to_num(dom - dgm, nan=0.0)
    ndsm = np.clip(ndsm, -2.0, 60.0)
    cir = fetch_cir()
    nir, red = cir[:, :, 0], cir[:, :, 1]
    ndvi = (nir - red) / np.maximum(nir + red, 1.0)

    # Masken: Gebäude (mit Rand), Brückenflächen, Wasser, Straßen
    bm = draw_mask([b["rings"] for b in city["buildings"]]).filter(ImageFilter.MaxFilter(5))
    deck = Image.new("L", (SIZE, SIZE), 0)
    dd = ImageDraw.Draw(deck)
    for m in city.get("bridge_meshes", []):
        t = m.get("top0") or m["top"]
        for k in range(0, len(t) - 8, 9):
            dd.polygon([local_to_px(t[k], t[k + 2]), local_to_px(t[k + 3], t[k + 5]), local_to_px(t[k + 6], t[k + 8])], fill=255)
    deck = deck.filter(ImageFilter.MaxFilter(5))
    # alle LoD2-Einheiten (auch Wahrzeichen, die später durch Modelle ersetzt werden) maskieren
    import lod2
    lm_img = Image.new("L", (SIZE, SIZE), 0)
    ld = ImageDraw.Draw(lm_img)
    for part in lod2.read_area(BBOX_UTM):
        for ext, _h in part["roofs"] + part["ground"]:
            pts = [(q[0] - MIN_E, MAX_N - q[1]) for q in ext]
            if len(pts) >= 3:
                ld.polygon(pts, fill=255)
    lm_img = lm_img.filter(ImageFilter.MaxFilter(5))
    bm = Image.fromarray(np.maximum(np.array(bm), np.array(lm_img)))
    s0 = np.array(Image.open(PROCESSED / "splat0.png"))
    s1 = np.array(Image.open(PROCESSED / "splat1.png"))
    px = s0.shape[0]
    f = px // SIZE   # Splat-Pixel je Meter

    def down(ch):
        return np.array(Image.fromarray(ch).resize((SIZE, SIZE), Image.BOX), dtype=np.float32)

    water = down(s1[:, :, 3]) > 100
    road = down(s0[:, :, 0]) > 110
    walk = (down(s0[:, :, 1]) > 110) | (down(s0[:, :, 2]) > 110)
    solid = (np.array(bm) > 0) | (np.array(deck) > 0)

    # Kronendach: erosion+dilation entfernt dünne Objekte (Masten, Zäune, Autos)
    canopy = (ndsm > 2.5) & ~solid & ~water & ~road
    cim = Image.fromarray((canopy * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    canopy = np.array(cim) > 0

    # Kronenspitzen
    sm = box_blur(np.where(canopy, ndsm, 0.0), 1)
    lm = local_max(sm, 2)
    peaks = canopy & (sm >= lm - 1e-6) & (sm >= 3.0)
    ys, xs = np.nonzero(peaks)
    hs = sm[ys, xs]
    order = np.argsort(-hs)
    occ = {}
    keep = []
    rng = np.random.default_rng(42 + e_km * 100 + n_km)
    # Dichte je 20x20-m-Block bestimmt Mindestabstand (Wald dünner, Straßenbäume exakt)
    dens = np.zeros((SIZE // 20 + 1, SIZE // 20 + 1), dtype=np.int32)
    for i in order:
        dens[ys[i] // 20, xs[i] // 20] += 1
    for i in order:
        y, x, h = int(ys[i]), int(xs[i]), float(hs[i])
        d = dens[y // 20, x // 20]
        spacing = 2.6 if d < 28 else (3.6 if d < 60 else 5.0)
        cx, cy = int(x // spacing), int(y // spacing)
        ok = True
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                for (ox, oy) in occ.get((cx + ddx, cy + ddy), ()):
                    if (ox - x) ** 2 + (oy - y) ** 2 < spacing * spacing:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            occ.setdefault((cx, cy), []).append((x, y))
            keep.append(i)
    if len(keep) > MAX_TREES:
        sel = rng.choice(len(keep), MAX_TREES, replace=False)
        keep = [keep[j] for j in sorted(sel)]
    ter = np.frombuffer((PROCESSED / "terrain.f32").read_bytes(), dtype="<f4").reshape(SIZE, SIZE)
    trees = []
    for i in keep:
        y, x = int(ys[i]), int(xs[i])
        h = float(hs[i])
        lx = x + 0.5 + (MIN_E - ORIGIN_E)
        lz = y + 0.5 - (MAX_N - ORIGIN_N)
        # Nadelbaum: im (laubfreien) Winterbild noch hoher NDVI und eher schmal-hoch
        nd = float(ndvi[max(y - 1, 0):y + 2, max(x - 1, 0):x + 2].mean())
        if h > 24.0 and nd < 0.12:
            continue
        needle = 1 if (nd > 0.38 and h > 8.0) else 0
        trees.append([round(lx, 1), round(lz, 1), round(float(ter[y, x]), 2), round(min(h, 42.0), 1), needle, round(min(0.30 * h + 0.9, 8.5), 1)])
    trees = merge_kataster(trees, e_km, n_km, ter, road | walk)
    city["trees"] = trees
    # Baumscheiben: Straßenbäume im Gehweg stehen in einem offenen Erd-/Grasfeld (~1,8 m), mit Grün im Splat
    pits = Image.new("L", (s1.shape[1], s1.shape[0]), 0)
    pd_ = ImageDraw.Draw(pits)
    fpx = s1.shape[0] // SIZE
    for t in trees:
        if len(t) < 7:
            continue                                   # nur Katasterbäume
        px_x = int(t[0] - (MIN_E - ORIGIN_E))
        px_y = int(t[1] + (MAX_N - ORIGIN_N))
        if not (0 <= px_y < SIZE and 0 <= px_x < SIZE) or not walk[px_y, px_x]:
            continue
        cx, cy = (t[0] - (MIN_E - ORIGIN_E)) * fpx, (t[1] + (MAX_N - ORIGIN_N)) * fpx
        r = 0.9 * fpx
        pd_.rectangle([cx - r, cy - r, cx + r, cy + r], fill=200)

    # Splat: Gras aus NDVI, Wald unter dichtem Kronendach
    grass_px = (ndvi > 0.16) & (ndsm < 1.4) & ~solid & ~water & ~road & ~walk
    dense = box_blur(canopy.astype(np.float32), 6) > 0.55
    forest_px = dense & ~solid & ~water & ~road & ~walk
    g_up = np.kron(grass_px.astype(np.uint8), np.ones((f, f), dtype=np.uint8)) * 255
    f_up = np.kron(forest_px.astype(np.uint8), np.ones((f, f), dtype=np.uint8)) * 255
    gim = Image.fromarray(g_up).filter(ImageFilter.GaussianBlur(0.8))
    fim = Image.fromarray(f_up).filter(ImageFilter.GaussianBlur(2.0))
    s1[:, :, 0] = np.maximum(s1[:, :, 0], np.array(gim))
    s1[:, :, 0] = np.maximum(s1[:, :, 0], np.array(pits))
    # Gehweg/Pflaster an Baumscheiben aussparen (der Shader legt Gehweg über Gras); Platzpflaster (ALKIS-Straßen-
    # parzellen) auch dort, wo das Luftbild Bewuchs zeigt (Grünstreifen, Rasen in Plätzen)
    pa = np.array(pits).astype(np.int32)
    for ch in (1, 2):
        s0[:, :, ch] = np.minimum(s0[:, :, ch].astype(np.int32), 255 - pa).astype(np.uint8)
    gp = np.array(gim).astype(np.int32)
    s0[:, :, 2] = np.minimum(s0[:, :, 2].astype(np.int32), 255 - gp).astype(np.uint8)
    Image.fromarray(s0).save(PROCESSED / "splat0.png", optimize=False, compress_level=3)
    s1[:, :, 1] = np.maximum(s1[:, :, 1], np.array(fim))
    Image.fromarray(s1).save(PROCESSED / "splat1.png", optimize=False, compress_level=3)
    (PROCESSED / "city.json").write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    from make_cover import make as make_cover
    make_cover(PROCESSED)
    print(f"{TILE_NAME}: {len(trees)} Bäume (Spitzen {len(ys)}), Gras {grass_px.mean() * 100:.0f} %, Wald {forest_px.mean() * 100:.0f} %", flush=True)


if __name__ == "__main__":
    main()
