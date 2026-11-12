"""Baualters-Raster für ganz Dresden aus offenen Daten (Stil-Zuordnung der Gebäude).

Quellen (Rohdaten in data/raw/baujahre/, Recherche: data/research/baujahre.md):
  * Zensus 2022 – Gebäude mit Wohnraum nach Baujahr (Jahrzehnte), 100-m-/1-km-Gitter (EPSG:3035)
  * Zensus 2022 – Gebäude mit Wohnraum nach Gebäudetyp und Größe, 100-m-Gitter
      Quelle: © Statistische Ämter des Bundes und der Länder, Zensus 2022, dl-de/by-2-0
  * Landeshauptstadt Dresden, Umweltamt – Nutzungsarten (Strukturtypen)-Kartierung, alle Ebenen der
      Erweiterten Blockkarte (OGC-API-Collections L1262–L1268, "Bebauung" = L1267 hat Vorrang), dl-de/by-2-0

Ausgabe: data/raw/baujahre/years_grid.npz (alle Raster in EPSG:25833, Zeile 0 = Süden)
  years  (ny, nx, 10) uint8   Anteile der Baujahresklassen ×255 (YEAR_CLASSES), Zelle 50 m
  btype  (ny, nx, 6)  uint8   Anteile der Gebäudetypen ×255 (TYPE_CLASSES), Zelle 50 m
  n_bld  (ny, nx)     uint16  Gebäude mit Wohnraum in der zugehörigen 100-m-Zensuszelle
  src    (ny, nx)     uint8   Herkunft der Anteile (SOURCES)
  sst    (my, mx)     uint8   Index in meta["sst_codes"] (0 = kein Strukturtyp), Zelle 25 m
  meta                str     JSON: Ursprung, Zellgrößen, Klassen, Strukturtyp-Namen, Quellenvermerk

Aufruf:  .venv/bin/python tools/build_years.py          # baut years_grid.npz
         .venv/bin/python tools/build_years.py --test   # nur Prüforte abfragen
Import (Pipeline, UTM33):
         from build_years import lookup, lookup_many, sample_era
         info = lookup(e, n)    # dict, siehe lookup()
"""
import csv
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

try:
    from config import RAW
except ImportError:                       # Import von außerhalb von tools/
    RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

SRC_DIR = RAW / "baujahre"
OUT = SRC_DIR / "years_grid.npz"
Z_YEARS = SRC_DIR / "zensus2022" / "Gebaeude_nach_Baujahr_Jahrzehnte.zip"
Z_TYPES = SRC_DIR / "zensus2022" / "Gebaeude_mit_Wohnraum_nach_Gebaeudetyp_Groesse.zip"
SST_CSV = SRC_DIR / "dresden_strukturtypen" / "bebauung_L1267.csv"

# Raster (EPSG:25833): alle 117 Spielkacheln (E 400–428 km, N 5646–5672 km) + 2 km Rand
E0, N0 = 398000.0, 5644000.0
WIDTH, HEIGHT = 32000.0, 30000.0
CELL = 50.0          # Zensus-Anteile (Quelle 100 m, gedreht → 50 m Nachabtastung)
CELL_SST = 25.0      # Strukturtypen (Blockflächen)

YEAR_CLASSES = ["vor1919", "1919-1949", "1950-1959", "1960-1969", "1970-1979", "1980-1989",
                "1990-1999", "2000-2009", "2010-2015", "ab2016"]
YEAR_COLS = ["Vor1919", "a1919bis1949", "a1950bis1959", "a1960bis1969", "a1970bis1979", "a1980bis1989",
             "a1990bis1999", "a2000bis2009", "a2010bis2015", "a2016undspaeter"]
YEAR_BOUNDS = [(1880, 1919), (1919, 1950), (1950, 1960), (1960, 1970), (1970, 1980), (1980, 1990),
               (1990, 2000), (2000, 2010), (2010, 2016), (2016, 2023)]   # für die Medianschätzung

TYPE_CLASSES = ["efh_zfh_frei", "doppel_reihenhaus", "mfh_3_6", "mfh_7_12", "mfh_13plus", "andere"]
TYPE_COLS = {"efh_zfh_frei": ["FreiEFH", "Freist_ZFH"],
             "doppel_reihenhaus": ["EFH_DHH", "EFH_Reihenhaus", "ZFH_DHH", "ZFH_Reihenhaus"],
             "mfh_3_6": ["MFH_3bis6Wohnungen"], "mfh_7_12": ["MFH_7bis12Wohnungen"],
             "mfh_13plus": ["MFH_13undmehrWohnungen"], "andere": ["AndererGebaeudetyp"]}

# Epochen für die Stil-Zuordnung (Zensus trennt Barock/Gründerzeit und 20er/NS-Zeit nicht)
ERAS = {
    "vor1919": ["vor1919"],                              # Barock … Gründerzeit/Jugendstil
    "1919-1949": ["1919-1949"],                          # Reformstil/20er, NS-Zeit
    "wiederaufbau_50er": ["1950-1959"],
    "ddr_frueh_60er": ["1960-1969"],                     # frühe Plattenbauten (IW 64, P2, Q6), Zeilen
    "ddr_wbs70": ["1970-1979", "1980-1989"],             # WBS 70 (ab 1973), Großwohnsiedlungen
    "nachwende": ["1990-1999", "2000-2009", "2010-2015", "ab2016"],
}
SOURCES = ["keine", "zelle", "nachbarschaft", "1km"]

K_PRIOR = 4.0        # Gewicht (in Gebäuden) der Nachbarschaft je Zelle (Cell-Key-Rauschen, "–" = 0)
SIGMA = 1.5          # Nachbarschaft: Gauß, in 100-m-Zellen
CKM_THREE = 2.0      # Cell-Key-Methode: wahre 1 und 2 erscheinen als "–" oder 3 (in Dresden nie 1/2,
                     # 3 ist 4× häufiger als 4) → eine veröffentlichte 3 zählt als Erwartungswert ≈ 2

ATTRIBUTION = ("Zensus 2022: © Statistische Ämter des Bundes und der Länder, dl-de/by-2-0; "
               "Strukturtypen: Landeshauptstadt Dresden (Umweltamt), dl-de/by-2-0")


# ---------------------------------------------------------------------------
# Aufbau
# ---------------------------------------------------------------------------
def _utm_centers(cell):
    nx, ny = int(WIDTH / cell), int(HEIGHT / cell)
    e = E0 + (np.arange(nx) + 0.5) * cell
    n = N0 + (np.arange(ny) + 0.5) * cell
    return np.meshgrid(e, n)          # [i (Süd→Nord), j (West→Ost)]


def _laea_window():
    """Ausschnitt im INSPIRE-Gitter (EPSG:3035), der das UTM-Raster sicher abdeckt (1 km Rand)."""
    from pyproj import Transformer
    t = Transformer.from_crs(25833, 3035, always_xy=True)
    ee, nn = np.meshgrid(np.linspace(E0, E0 + WIDTH, 33), np.linspace(N0, N0 + HEIGHT, 31))
    x, y = t.transform(ee.ravel(), nn.ravel())
    x0, y0 = np.floor(x.min() / 1000) * 1000 - 1000, np.floor(y.min() / 1000) * 1000 - 1000
    x1, y1 = np.ceil(x.max() / 1000) * 1000 + 1000, np.ceil(y.max() / 1000) * 1000 + 1000
    return x0, y0, x1, y1


def _num(s):
    s = s.strip().strip('"')
    if not s or not s[0].isdigit():
        return 0                       # "–" = genau Null oder geheimgehalten (auf Null gesetzt)
    try:
        return int(s.replace(".", ""))
    except ValueError:
        return 0


def read_zensus(zpath, res, groups, win):
    """Liest eine Zensus-Gitter-CSV (res = '100m' oder '1km') aus dem ZIP; nur Zellen im Fenster.
    groups: Liste von Spaltenlisten (je Ausgabeklasse summiert). Rückgabe (counts[iy,ix,k], total[iy,ix])."""
    size = 100 if res == "100m" else 1000
    x0, y0, x1, y1 = win
    nx, ny = int((x1 - x0) / size), int((y1 - y0) / size)
    cnt = np.zeros((ny, nx, len(groups)), np.float32)
    tot = np.zeros((ny, nx), np.float32)
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.endswith(f"_{res}-Gitter.csv"))
        with z.open(name) as fb:
            f = io.TextIOWrapper(fb, encoding="utf-8", newline="")
            head = f.readline().strip().split(";")
            idx = [[head.index(c) for c in g] for g in groups]
            it = head.index("Insgesamt_Gebaeude")
            for line in f:
                p = line.rstrip("\r\n").split(";")
                x, y = int(p[1]), int(p[2])
                if not (x0 <= x < x1 and y0 <= y < y1):
                    continue
                ix, iy = int((x - x0) // size), int((y - y0) // size)
                tot[iy, ix] = _num(p[it])
                for k, g in enumerate(idx):
                    cnt[iy, ix, k] = sum(_num(p[c]) for c in g)
    return cnt, tot


def blend_shares(c100, c1k):
    """Anteile je 100-m-Zelle: Zelle + Nachbarschafts-Prior; leere Zellen aus Nachbarschaft bzw. 1 km."""
    from scipy.ndimage import gaussian_filter
    c100 = np.where(c100 == 3, CKM_THREE, c100)
    c1k = np.where(c1k == 3, CKM_THREE, c1k)
    s = c100.sum(-1)
    nb = np.stack([gaussian_filter(c100[..., k], SIGMA, mode="constant") for k in range(c100.shape[-1])], -1)
    g = nb.sum(-1)
    nb_sh = np.divide(nb, g[..., None], out=np.zeros_like(nb), where=g[..., None] > 1e-6)
    sh = np.zeros_like(c100)
    src = np.zeros(s.shape, np.uint8)
    m1 = s > 0
    sh[m1] = (c100[m1] + K_PRIOR * nb_sh[m1]) / (s[m1] + K_PRIOR * (g[m1] > 1e-6))[:, None]
    src[m1] = 1
    m2 = ~m1 & (g >= 0.3)
    sh[m2] = nb_sh[m2]
    src[m2] = 2
    # 1 km: Index der 100-m-Zelle → 1-km-Zelle
    k1 = c1k.sum(-1)
    km_sh = np.divide(c1k, k1[..., None], out=np.zeros_like(c1k), where=k1[..., None] > 0)
    iy, ix = np.nonzero(~m1 & ~m2)
    ky, kx = iy // 10, ix // 10
    ok = (ky < km_sh.shape[0]) & (kx < km_sh.shape[1])
    iy, ix, ky, kx = iy[ok], ix[ok], ky[ok], kx[ok]
    has = k1[ky, kx] > 0
    sh[iy[has], ix[has]] = km_sh[ky[has], kx[has]]
    src[iy[has], ix[has]] = 3
    return sh, src


def resample_to_utm(arrs, win, size, cell):
    """Nimmt je UTM-Zellmitte den Wert der LAEA-Zelle (nächster Nachbar)."""
    from pyproj import Transformer
    t = Transformer.from_crs(25833, 3035, always_xy=True)
    ee, nn = _utm_centers(cell)
    x, y = t.transform(ee.ravel(), nn.ravel())
    ix = ((x - win[0]) // size).astype(np.int64).reshape(ee.shape)
    iy = ((y - win[1]) // size).astype(np.int64).reshape(ee.shape)
    return [a[iy, ix] for a in arrs]


def build_sst():
    """Rastert die Blöcke der Strukturtypen-/Nutzungsarten-Kartierung (Ebene 3) auf 25 m.
    Alle Ebenen der Erweiterten Blockkarte (Kleingärten, Garagen, Wald …); "Bebauung" hat Vorrang."""
    import shapely
    from pyproj import Transformer
    csv.field_size_limit(1 << 30)
    t = Transformer.from_crs(4326, 25833, always_xy=True)
    nx, ny = int(WIDTH / CELL_SST), int(HEIGHT / CELL_SST)
    grid = np.zeros((ny, nx), np.uint8)
    codes, names, groups = [""], [""], [""]
    rows = []
    for fn in sorted(SST_CSV.parent.glob("*_L*.csv")):
        prio = 1 if fn == SST_CSV else 0
        with open(fn, encoding="utf-8", newline="") as f:
            rows += [dict(r, _prio=prio) for r in csv.DictReader(f, delimiter=";")]
    for r in rows:
        code = (r.get("desk3") or "").strip()
        if not code:
            continue
        if code not in codes:
            codes.append(code)
            names.append(re.sub(r"^\S+\s+", "", r["sst_lv_3_liste"].strip()))
            groups.append(re.sub(r"\s+", " ", r["sst_liste"].strip()))
    order = sorted(range(1, len(codes)), key=lambda i: codes[i])
    remap = {codes[i]: k + 1 for k, i in enumerate(order)}
    codes, names, groups = [""] + [codes[i] for i in order], [""] + [names[i] for i in order], \
        [""] + [groups[i] for i in order]
    assert len(codes) < 256
    # Bebauung zuletzt, darin kleine Blöcke zuletzt (überdecken große bei Überlappung)
    rows.sort(key=lambda r: (r["_prio"], -float(r.get("flaeche") or 0)))
    for r in rows:
        code = (r.get("desk3") or "").strip()
        wkt = r["shape"].split(";", 1)[-1]
        if not code or not wkt:
            continue
        g = shapely.from_wkt(wkt)
        g = shapely.transform(g, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))
        bx0, by0, bx1, by1 = g.bounds
        j0, j1 = max(int((bx0 - E0) // CELL_SST), 0), min(int((bx1 - E0) // CELL_SST) + 1, nx)
        i0, i1 = max(int((by0 - N0) // CELL_SST), 0), min(int((by1 - N0) // CELL_SST) + 1, ny)
        if j0 >= j1 or i0 >= i1:
            continue
        ex = E0 + (np.arange(j0, j1) + 0.5) * CELL_SST
        ny_ = N0 + (np.arange(i0, i1) + 0.5) * CELL_SST
        xx, yy = np.meshgrid(ex, ny_)
        inside = shapely.contains_xy(g, xx, yy)
        sub = grid[i0:i1, j0:j1]
        sub[inside] = remap[code]
    return grid, codes, names, groups


def build():
    t0 = time.time()
    win = _laea_window()
    print(f"LAEA-Fenster {win} …", flush=True)
    yg = [[c] for c in YEAR_COLS]
    tg = [TYPE_COLS[k] for k in TYPE_CLASSES]
    cy, ty = read_zensus(Z_YEARS, "100m", yg, win)
    cy1k, _ = read_zensus(Z_YEARS, "1km", yg, win)
    ct, _ = read_zensus(Z_TYPES, "100m", tg, win)
    ct1k, _ = read_zensus(Z_TYPES, "1km", tg, win)
    print(f"  Zensus gelesen: {int((ty > 0).sum())} bewohnte 100-m-Zellen, "
          f"{int(ty.sum())} Gebäude ({time.time() - t0:.0f} s)", flush=True)
    ysh, ysrc = blend_shares(cy, cy1k)
    tsh, _ = blend_shares(ct, ct1k)
    years, btype, n_bld, src = resample_to_utm([ysh, tsh, ty, ysrc], win, 100, CELL)
    print(f"  Nachabtastung auf {CELL:.0f} m: {years.shape[1]}×{years.shape[0]} ({time.time() - t0:.0f} s)", flush=True)
    sst, codes, names, groups = build_sst()
    print(f"  Strukturtypen gerastert ({CELL_SST:.0f} m): {int((sst > 0).sum())} Zellen, "
          f"{len(codes) - 1} Typen ({time.time() - t0:.0f} s)", flush=True)
    meta = {
        "crs": "EPSG:25833", "origin_e": E0, "origin_n": N0, "width": WIDTH, "height": HEIGHT,
        "cell": CELL, "cell_sst": CELL_SST, "row0": "sued",
        "index": "i = floor((n - origin_n) / cell), j = floor((e - origin_e) / cell); arr[i, j]",
        "year_classes": YEAR_CLASSES, "type_classes": TYPE_CLASSES, "sources": SOURCES, "eras": ERAS,
        "sst_codes": codes, "sst_names": names, "sst_groups": groups,
        "scale": "years/btype: Anteil * 255 (je Zelle auf Summe 1 normieren)",
        "note": "Zensus zählt nur Gebäude mit Wohnraum (Stichtag 15.05.2022); Baujahr = Bezugsfertigstellung, "
                "bei Wiederaufbau nach Totalzerstörung das Wiederaufbaujahr.",
        "attribution": ATTRIBUTION,
        "built": time.strftime("%Y-%m-%d"),
    }
    np.savez_compressed(
        OUT, meta=np.array(json.dumps(meta, ensure_ascii=False)),
        years=np.round(years * 255).astype(np.uint8), btype=np.round(btype * 255).astype(np.uint8),
        n_bld=np.minimum(n_bld, 65535).astype(np.uint16), src=src.astype(np.uint8), sst=sst)
    print(f"→ {OUT} ({OUT.stat().st_size / 1e6:.2f} MB, {time.time() - t0:.0f} s)")


# ---------------------------------------------------------------------------
# Abfrage
# ---------------------------------------------------------------------------
_G = None


def _grid(path=None):
    global _G
    if _G is None:
        z = np.load(path or OUT, allow_pickle=False)
        _G = {k: z[k] for k in z.files}
        _G["meta"] = json.loads(str(_G["meta"]))
    return _G


def lookup_many(e, n):
    """Vektorisiert: e, n (Arrays, UTM33) → dict von Arrays
    years (N,10) / btype (N,6) Anteile (Summe 1 oder 0), n_bld, src (Index in SOURCES), sst (Index), inside."""
    g = _grid()
    m = g["meta"]
    e, n = np.asarray(e, float), np.asarray(n, float)
    ny, nx = g["src"].shape
    i = np.floor((n - m["origin_n"]) / m["cell"]).astype(np.int64)
    j = np.floor((e - m["origin_e"]) / m["cell"]).astype(np.int64)
    inside = (i >= 0) & (i < ny) & (j >= 0) & (j < nx)
    i, j = np.clip(i, 0, ny - 1), np.clip(j, 0, nx - 1)
    my, mx = g["sst"].shape
    si = np.floor((n - m["origin_n"]) / m["cell_sst"]).astype(np.int64)
    sj = np.floor((e - m["origin_e"]) / m["cell_sst"]).astype(np.int64)
    sst = np.zeros(e.shape, np.uint8)
    # Mitte, dann 4er-, dann Diagonal-Nachbarn (25 m): Punkte knapp außerhalb eines Blocks (Straßenrand)
    for di, dj in ((0, 0), (0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        v = g["sst"][np.clip(si + di, 0, my - 1), np.clip(sj + dj, 0, mx - 1)]
        sst = np.where(sst == 0, v, sst)

    def norm(a):
        a = a.astype(np.float32)
        s = a.sum(-1, keepdims=True)
        return np.divide(a, s, out=np.zeros_like(a), where=s > 0)

    years = norm(g["years"][i, j])
    years[~inside] = 0
    btype = norm(g["btype"][i, j])
    btype[~inside] = 0
    src = np.where(inside, g["src"][i, j], 0)
    sst = np.where(inside, sst, 0)
    return {"years": years, "btype": btype, "n_bld": np.where(inside, g["n_bld"][i, j], 0),
            "src": src, "sst": sst, "inside": inside}


def _median_year(sh):
    if sh.sum() <= 0:
        return None
    c = np.cumsum(sh) / sh.sum()
    k = int(np.searchsorted(c, 0.5))
    lo, hi = YEAR_BOUNDS[k]
    prev = c[k - 1] if k > 0 else 0.0
    f = (0.5 - prev) / max(c[k] - prev, 1e-6)
    return int(round(lo + f * (hi - lo)))


def lookup(e, n):
    """Baualter/Strukturtyp am Punkt (e, n) in EPSG:25833. Rückgabe:
    years      {Klasse: Anteil}   Anteile der Baujahresklassen der Wohngebäude (Summe 1, leer = keine Daten)
    eras       {Epoche: Anteil}   zusammengefasst zu ERAS (für die Stil-Wahl)
    era        stärkste Epoche,  dominant: stärkste Klasse,
    year_median grobe Median-Schätzung (lineare Interpolation; "vor1919" als 1880–1918 angenommen)
    btype      {Gebäudetyp: Anteil} (EFH/Reihenhaus/MFH-Größen)
    n_bld      Wohngebäude in der 100-m-Zensuszelle,  source: zelle | nachbarschaft | 1km | keine
    sst, sst_name, sst_group   Stadtstrukturtyp (Dresdner Kartierung), "" wenn außerhalb bebauter Blöcke
    """
    r = lookup_many([e], [n])
    m = _grid()["meta"]
    sh = r["years"][0]
    years = {k: round(float(v), 3) for k, v in zip(YEAR_CLASSES, sh)} if sh.sum() > 0 else {}
    eras = {}
    if years:
        for name, cls in ERAS.items():
            eras[name] = round(sum(years[c] for c in cls), 3)
    bt = r["btype"][0]
    s = int(r["sst"][0])
    return {
        "e": float(e), "n": float(n), "inside": bool(r["inside"][0]),
        "years": years, "eras": eras,
        "era": max(eras, key=eras.get) if eras else None,
        "dominant": max(years, key=years.get) if years else None,
        "year_median": _median_year(sh),
        "btype": {k: round(float(v), 3) for k, v in zip(TYPE_CLASSES, bt)} if bt.sum() > 0 else {},
        "n_bld": int(r["n_bld"][0]), "source": SOURCES[int(r["src"][0])],
        "sst": m["sst_codes"][s], "sst_name": m["sst_names"][s], "sst_group": m["sst_groups"][s],
    }


def sample_era(info, u):
    """Deterministische Epochenwahl für ein Einzelgebäude: u ∈ [0,1) (z. B. stable_rand(id)) wird über
    die Verteilung info["eras"] abgebildet. None ohne Daten."""
    eras = info.get("eras") or {}
    acc = 0.0
    tot = sum(eras.values())
    for k, v in eras.items():
        acc += v / tot if tot else 0
        if u < acc:
            return k
    return next(reversed(eras), None) if eras else None


# Prüforte (UTM33). Erwartung laut Auftrag bzw. Ortskenntnis
TEST_POINTS = [
    ("Prohlis (Auftrag)", 415500, 5650500, "1976–1985"),
    ("Äußere Neustadt (Auftrag)", 412300, 5658000, "vor 1919"),
    ("Gorbitz (Auftrag)", 406000, 5655000, "1980er"),
    # Lage aus OSM-Straßenmitten (data/raw/tiles/*/osm/roads.json)
    ("Prohlis Jacob-Winter-Platz", 415593, 5651134, "1976–1985"),
    ("Prohlis Herzberger Str.", 415676, 5651290, "1976–1985"),
    ("Äußere Neustadt Alaunstr.", 412519, 5657987, "vor 1919"),
    ("Äuß. Neustadt Görlitzer Str.", 412753, 5658101, "vor 1919"),
    ("Gorbitz Leutewitzer Ring", 407184, 5655988, "1980er"),
    ("Gorbitz Omsewitzer Ring", 406471, 5656048, "1980er"),
    ("Gorbitz Wölfnitzer Ring", 406985, 5655351, "1980er"),
    ("Hechtviertel Hechtstr.", 412122, 5659583, "vor 1919"),
    ("Hellerau Am Grünen Zipfel", 413302, 5662453, "1909–1913"),
    ("Striesen Wittenberger Str.", 415315, 5655708, "vor 1919"),
    ("Altmarkt", 411531, 5656074, "1953–1958"),
    ("Prager Straße", 411425, 5655617, "1965–1969"),
    ("Neumarkt", 411720, 5656255, "2004–2020"),
    ("Zamenhofstr. (Gebäudekette)", 417147, 5651709, "DDR"),
]


def run_tests(extra=()):
    rows = []
    for name, e, n, exp in list(TEST_POINTS) + list(extra):
        r = lookup(e, n)
        top = sorted(r["years"].items(), key=lambda kv: -kv[1])[:3]
        rows.append((name, e, n, exp, r))
        print(f"{name:28s} E {e:.0f} N {n:.0f}  erwartet {exp:10s} → {r['dominant'] or '-':10s} "
              f"Median {r['year_median'] or '-'}  [{', '.join(f'{k} {v:.0%}' for k, v in top)}]  "
              f"n={r['n_bld']} ({r['source']})  SST {r['sst'] or '-'} {r['sst_name']}")
    return rows


if __name__ == "__main__":
    if "--test" not in sys.argv:
        build()
    run_tests()
