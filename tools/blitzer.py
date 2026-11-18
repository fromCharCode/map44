"""Blitzer (stationäre Geschwindigkeits- und Rotlichtüberwachung) je Kachel: city["speedcams"].

  python tools/blitzer.py [E,N ...]  (ohne Argument: alle Kacheln; ohne Neubau)
  python tools/blitzer.py --fetch    (Daten neu von Overpass holen)

Quelle: OpenStreetMap (© OpenStreetMap-Mitwirkende, ODbL): Knoten highway=speed_camera und Relationen
type=enforcement (from -> device -> to: überwachte Fahrtrichtung, maxspeed). Abgelegt in
data/raw/blitzer/osm_enforcement.json.
Zeile: [x, z, limit_kmh, dx, dz, bauart, rotlicht]   dx/dz = überwachte Fahrtrichtung (0,0 = beide),
bauart 0 = Säule, 1 = Mast mit Kasten; rotlicht 1 = reiner Ampelblitzer (kein Tempo), 2 = Ampel und Tempo.
"""
import json
import math
import sys
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
SRC = ROOT / "data" / "raw" / "blitzer" / "osm_enforcement.json"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
QUERY = ('[out:json][timeout:120];(node["highway"="speed_camera"](50.94,13.50,51.20,13.98);'
         'relation["type"="enforcement"](50.94,13.50,51.20,13.98););out body;>;out skel qt;')


def fetch():
    import requests
    r = requests.post("https://overpass-api.de/api/interpreter", data={"data": QUERY}, timeout=180,
                      headers={"User-Agent": "map-data-research/1.0"})
    r.raise_for_status()
    SRC.parent.mkdir(parents=True, exist_ok=True)
    SRC.write_text(r.text, encoding="utf-8")


def _local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def _num(v, d):
    try:
        return float(str(v).split(";")[0].split()[0])
    except (ValueError, IndexError):
        return d


def cameras():
    els = json.loads(SRC.read_text(encoding="utf-8"))["elements"]
    nodes = {}
    for e in els:                                            # Knoten kommen doppelt (mit und ohne Tags)
        if e["type"] == "node" and (e["id"] not in nodes or e.get("tags")):
            nodes[e["id"]] = e
    cams = {}                                                # Knoten-ID -> Eintrag
    for e in nodes.values():
        t = e.get("tags") or {}
        if t.get("highway") == "speed_camera":
            cams[e["id"]] = {"p": _local(e["lon"], e["lat"]), "limit": _num(t.get("maxspeed"), 50.0), "dirs": [],
                             "kind": 0 if (t.get("man_made") == "stele" or t.get("mast:type") == "column") else 1, "red": 0, "spd": 1}
    for r in els:
        if r["type"] != "relation":
            continue
        t = r.get("tags") or {}
        enf = t.get("enforcement")
        if enf not in ("maxspeed", "traffic_signals"):
            continue
        dev = [m["ref"] for m in r["members"] if m["type"] == "node" and m["role"] == "device" and m["ref"] in nodes]
        frm = [m["ref"] for m in r["members"] if m["type"] == "node" and m["role"] == "from" and m["ref"] in nodes]
        to = [m["ref"] for m in r["members"] if m["type"] == "node" and m["role"] == "to" and m["ref"] in nodes]
        if not dev:
            continue
        d = None
        if frm and to:
            a, b = _local(nodes[frm[0]]["lon"], nodes[frm[0]]["lat"]), _local(nodes[to[0]]["lon"], nodes[to[0]]["lat"])
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            if ln > 1.0:
                d = ((b[0] - a[0]) / ln, (b[1] - a[1]) / ln)
        for nid in dev:
            c = cams.get(nid)
            if c is None:
                n = nodes[nid]
                c = cams[nid] = {"p": _local(n["lon"], n["lat"]), "limit": 50.0, "dirs": [], "kind": 1, "red": 0, "spd": 0}
            if enf == "traffic_signals":
                c["red"] = 1
            else:
                c["spd"] = 1
                if t.get("maxspeed"):
                    c["limit"] = _num(t.get("maxspeed"), c["limit"])
            if d is not None and d not in c["dirs"]:
                c["dirs"].append(d)
    out = []
    for c in cams.values():
        for d in (c["dirs"] if len(c["dirs"]) == 1 else [(0.0, 0.0)]):      # zwei Richtungen = beide
            out.append([round(c["p"][0], 2), round(c["p"][1], 2), int(c["limit"]), round(d[0], 3), round(d[1], 3),
                        c["kind"], (2 if c["spd"] else 1) if c["red"] else 0])
    return out


def main():
    if "--fetch" in sys.argv or not SRC.exists():
        fetch()
    cams = cameras()
    n = 0
    only = {a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")}
    for d in sorted(p for p in TILES.iterdir() if p.is_dir()):
        if only and d.name not in only:
            continue
        cf = d / "city.json"
        if not cf.exists():
            continue
        e_km, n_km = (int(v) for v in d.name.split("_"))
        x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
        mine = [c for c in cams if x0 <= c[0] < x0 + 2000.0 and z0 <= c[1] < z0 + 2000.0]
        city = json.loads(cf.read_text(encoding="utf-8"))
        if mine or city.get("speedcams"):
            city["speedcams"] = mine
            cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
            n += len(mine)
    print(f"Blitzer: {n} von {len(cams)} Standorten in den Kacheln")


if __name__ == "__main__":
    main()
