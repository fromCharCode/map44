"""Lädt die Orthofotos (20 cm) als 500-m-Kacheln vom GeoSN-WMS.

Quelle: Geodaten Sachsen (GeoSN), Datenlizenz Deutschland - Namensnennung 2.0.
Kacheln: dop_<ix>_<iy>.jpg, ix von West nach Ost, iy von Süd nach Nord.
"""
import sys
import time

import requests

from config import BBOX_UTM, DOP_DIR, DOP_LAYER, DOP_WMS, RAW, USER_AGENT

TILE = 500.0
PX = 2500  # 20 cm pro Pixel


def main() -> None:
    out = DOP_DIR
    out.mkdir(parents=True, exist_ok=True)
    min_e, min_n, max_e, max_n = BBOX_UTM
    nx = int(round((max_e - min_e) / TILE))
    ny = int(round((max_n - min_n) / TILE))
    for ix in range(nx):
        for iy in range(ny):
            f = out / f"dop_{ix}_{iy}.jpg"
            if f.exists() and f.stat().st_size > 100_000:
                continue
            e0 = min_e + ix * TILE
            n0 = min_n + iy * TILE
            params = {
                "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
                "LAYERS": DOP_LAYER, "STYLES": "", "CRS": "EPSG:25833",
                "BBOX": f"{e0},{n0},{e0 + TILE},{n0 + TILE}",
                "WIDTH": PX, "HEIGHT": PX, "FORMAT": "image/jpeg",
            }
            for attempt in range(4):
                try:
                    r = requests.get(DOP_WMS, params=params, timeout=120,
                                     headers={"User-Agent": USER_AGENT})
                    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                        f.write_bytes(r.content)
                        print(f"ok {f.name} {len(r.content) // 1024} kB", flush=True)
                        break
                    print(f"fehler {f.name}: HTTP {r.status_code}", file=sys.stderr)
                except requests.RequestException as exc:
                    print(f"fehler {f.name}: {exc}", file=sys.stderr)
                time.sleep(3 * (attempt + 1))
            else:
                sys.exit(f"Kachel {f.name} nicht ladbar")
            time.sleep(0.5)  # Server schonen


if __name__ == "__main__":
    main()
