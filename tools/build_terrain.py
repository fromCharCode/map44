"""Setzt die DGM1-Kacheln (1 m, GeoTIFF, GeoSN) zu einem Höhenraster für das Spielgebiet zusammen.

Ausgabe: data/processed/terrain.f32 (float32, little endian, Zeilen von Nord nach Süd,
Spalten von West nach Ost, Höhen relativ zu base_height) und terrain.json (Metadaten).

Quelle: Geodaten Sachsen (GeoSN), Datenlizenz Deutschland - Namensnennung 2.0.
"""
import json
import re

import numpy as np
from PIL import Image

from config import BASE_HEIGHT, BBOX_UTM, PROCESSED, RAW

Image.MAX_IMAGE_PIXELS = None
NODATA_LIMIT = -1000.0


def main() -> None:
    min_e, min_n, max_e, max_n = BBOX_UTM
    w = int(round(max_e - min_e))
    h = int(round(max_n - min_n))
    canvas = np.full((h, w), np.nan, dtype=np.float32)

    for tif in sorted((RAW / "dgm").glob("*/dgm1_*_sn.tif")):
        m = re.search(r"dgm1_(\d{3})(\d{2})_(\d{4})_2_sn", tif.name)
        if not m:
            continue
        # Dateiname dgm1_33410_5656: "33" = UTM-Zone, "410" = Ost in km, "5656" = Nord in km
        east_km = int(tif.name.split("_")[1][2:])
        north_km = int(tif.name.split("_")[2])
        x0 = east_km * 1000.0
        y_top = (north_km + 2) * 1000.0  # Oberkante der Kachel (2 km hoch)
        # Überschneidung mit dem Spielgebiet?
        if x0 + 2000 <= min_e or x0 >= max_e or y_top - 2000 >= max_n or y_top <= min_n:
            continue
        arr = np.array(Image.open(tif), dtype=np.float32)
        arr[arr < NODATA_LIMIT] = np.nan
        # Pixel (col,row) <-> E = x0 + col, N = y_top - row (Zellkante oben links)
        for_e0 = max(min_e, x0)
        for_e1 = min(max_e, x0 + 2000)
        for_n1 = min(max_n, y_top)
        for_n0 = max(min_n, y_top - 2000)
        src_c0, src_c1 = int(for_e0 - x0), int(for_e1 - x0)
        src_r0, src_r1 = int(y_top - for_n1), int(y_top - for_n0)
        dst_c0 = int(for_e0 - min_e)
        dst_r0 = int(max_n - for_n1)
        part = arr[src_r0:src_r1, src_c0:src_c1]
        canvas[dst_r0:dst_r0 + part.shape[0], dst_c0:dst_c0 + part.shape[1]] = part
        print(f"{tif.parent.name}: {part.shape[1]}x{part.shape[0]} m eingefügt")

    missing = int(np.isnan(canvas).sum())
    if missing == canvas.size:
        raise SystemExit("keine DGM-Kacheln im Spielgebiet gefunden")
    if missing:
        print(f"Warnung: {missing} Zellen ohne Daten, fülle mit Mittelwert")
        canvas[np.isnan(canvas)] = np.nanmean(canvas)

    # Mittlere Höhe um den Ursprung als Nullniveau (Altmarkt)
    cy, cx = h // 2, w // 2
    base = BASE_HEIGHT
    rel = (canvas - base).astype("<f4")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "terrain.f32").write_bytes(rel.tobytes())
    (PROCESSED / "terrain_raw.f32").write_bytes(rel.tobytes())
    meta = {
        "width": w, "height": h, "spacing": 1.0,
        "base_height": base,
        "min": float(rel.min()), "max": float(rel.max()),
        "bbox_utm": list(BBOX_UTM),
        "layout": "float32 LE, row 0 = Nordrand, col 0 = Westrand, Höhe relativ zu base_height",
    }
    (PROCESSED / "terrain.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Basishöhe {base:.2f} m ü. NHN, Bereich {rel.min():.1f} .. {rel.max():.1f} m relativ")

    # Vorschau als Graubild
    norm = (rel - rel.min()) / max(1e-6, rel.max() - rel.min())
    Image.fromarray((norm * 255).astype(np.uint8)).resize((800, 800)).save(PROCESSED / "terrain_preview.png")


if __name__ == "__main__":
    main()
