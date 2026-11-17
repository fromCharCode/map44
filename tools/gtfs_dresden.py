"""Schneidet den Dresdner Nahverkehr aus dem deutschlandweiten GTFS-Sollfahrplan (gtfs.de / DELFI e.V.).

  python tools/gtfs_dresden.py
Eingabe:  data/raw/gtfs/de_nv/*.txt
Ausgabe:  data/raw/gtfs/dresden/{stops,routes,trips,stop_times,calendar,calendar_dates}.csv
          (alle Fahrten, die mindestens zwei Halte im Stadtgebiet haben; deren Halte nur im Gebiet + 3 km Rand)
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "gtfs" / "de_nv"
OUT = ROOT / "data" / "raw" / "gtfs" / "dresden"
LAT0, LAT1, LON0, LON1 = 50.93, 51.20, 13.50, 13.98      # Kachelgebiet + Rand

csv.field_size_limit(10 ** 7)


def rows(name):
    with open(SRC / name, newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stops = {}
    for r in rows("stops.txt"):
        try:
            la, lo = float(r["stop_lat"]), float(r["stop_lon"])
        except ValueError:
            continue
        if LAT0 < la < LAT1 and LON0 < lo < LON1:
            stops[r["stop_id"]] = r
    print(len(stops), "Halte im Gebiet", flush=True)
    # 1. Durchlauf: Fahrten mit ≥ 2 Halten im Gebiet
    cnt = {}
    with open(SRC / "stop_times.txt", newline="", encoding="utf-8-sig") as f:
        rd = csv.reader(f)
        head = next(rd)
        i_trip, i_stop = head.index("trip_id"), head.index("stop_id")
        for row in rd:
            if row[i_stop] in stops:
                cnt[row[i_trip]] = cnt.get(row[i_trip], 0) + 1
    trips_ok = {t for t, n in cnt.items() if n >= 2}
    print(len(trips_ok), "Fahrten", flush=True)
    # 2. Durchlauf: deren Haltezeiten im Gebiet
    n = 0
    with open(SRC / "stop_times.txt", newline="", encoding="utf-8-sig") as f, \
            open(OUT / "stop_times.csv", "w", newline="", encoding="utf-8") as g:
        rd = csv.reader(f)
        wr = csv.writer(g)
        head = next(rd)
        wr.writerow(head)
        for row in rd:
            if row[i_trip] in trips_ok and row[i_stop] in stops:
                wr.writerow(row)
                n += 1
    print(n, "Haltezeiten", flush=True)
    routes_ok, services = set(), set()
    with open(OUT / "trips.csv", "w", newline="", encoding="utf-8") as g:
        wr = None
        for r in rows("trips.txt"):
            if r["trip_id"] in trips_ok:
                if wr is None:
                    wr = csv.DictWriter(g, fieldnames=list(r.keys()))
                    wr.writeheader()
                wr.writerow(r)
                routes_ok.add(r["route_id"])
                services.add(r["service_id"])
    for name, key, keep in (("routes", "route_id", routes_ok), ("calendar", "service_id", services),
                            ("calendar_dates", "service_id", services)):
        with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as g:
            wr = None
            k = 0
            for r in rows(f"{name}.txt"):
                if r[key] in keep:
                    if wr is None:
                        wr = csv.DictWriter(g, fieldnames=list(r.keys()))
                        wr.writeheader()
                    wr.writerow(r)
                    k += 1
        print(k, name, flush=True)
    with open(OUT / "stops.csv", "w", newline="", encoding="utf-8") as g:
        wr = csv.DictWriter(g, fieldnames=list(next(iter(stops.values())).keys()))
        wr.writeheader()
        for r in stops.values():
            wr.writerow(r)


if __name__ == "__main__":
    main()
