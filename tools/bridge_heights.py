"""Berechnet Brückenhöhen global (über Kachelgrenzen hinweg) aus allen OSM-Kacheln und dem DGM1.

Ausgabe: data/raw/bridge_heights.json  {"<way-id>": [y relativ zu BASE_HEIGHT, ...]} in OSM-Punktreihenfolge.
"""
import glob
import json
from functools import lru_cache

import numpy as np
from PIL import Image
from pyproj import Transformer

from bridge_chain import bridge_chain_heights
from config import BASE_HEIGHT, RAW

Image.MAX_IMAGE_PIXELS = None
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)


@lru_cache(maxsize=8)
def dgm(e_km, n_km):
    d = RAW / "dgm" / f"dgm1_33{e_km}_{n_km}_2_sn_tiff"
    f = list(d.glob("*_sn.tif"))
    if not f:
        return None
    a = np.array(Image.open(f[0]), dtype=np.float32)
    a[a < -1000] = np.nan
    return a


def ground(e, n):
    ek = int(e // 2000) * 2
    nk = int(n // 2000) * 2
    a = dgm(ek % 1000, nk)
    if a is None:
        return 0.0
    c = min(max(int(e - ek * 1000.0), 0), a.shape[1] - 1)
    r = min(max(int((nk + 2) * 1000.0 - n), 0), a.shape[0] - 1)
    v = a[r, c]
    return float(v - BASE_HEIGHT) if np.isfinite(v) else 0.0


def main():
    ways = {"r": {}, "t": {}}
    for f in sorted(glob.glob(str(RAW / "tiles" / "*" / "osm" / "roads.json"))):
        for el in json.load(open(f))["elements"]:
            t = el.get("tags", {})
            if el["type"] == "way" and t.get("bridge") not in (None, "no") and "bridge" in t and t.get("highway") and t.get("tunnel") != "yes":
                g = el["geometry"]
                e, n = TO_UTM.transform([p["lon"] for p in g], [p["lat"] for p in g])
                ways["r"][el["id"]] = np.column_stack([e, n])
    for f in sorted(glob.glob(str(RAW / "tiles" / "*" / "osm" / "rail.json"))):
        for el in json.load(open(f))["elements"]:
            t = el.get("tags", {})
            if el["type"] == "way" and "bridge" in t and t["bridge"] != "no" and t.get("railway") in ("tram", "rail", "light_rail"):
                g = el["geometry"]
                e, n = TO_UTM.transform([p["lon"] for p in g], [p["lat"] for p in g])
                ways["t"][el["id"]] = np.column_stack([e, n])
    out = {}
    for k, w in ways.items():
        print(k, len(w), "Brückenwege")
        ys = bridge_chain_heights(w, ground)
        for wid, y in ys.items():
            out[f"{k}{wid}"] = [round(float(v), 2) for v in y]
    (RAW / "bridge_heights.json").write_text(json.dumps(out), encoding="utf-8")
    print(len(out), "Einträge")


if __name__ == "__main__":
    main()
