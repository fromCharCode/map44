"""Fahrplan fürs Spiel aus dem Dresdner GTFS-Ausschnitt (tools/gtfs_dresden.py).

  python tools/gtfs_timetable.py
Ausgabe: godot/data/timetable.json
  {"source": ..., "days": {"wt": "JJJJMMTT", "sa": ..., "so": ...},
   "stops": [[name, x, z], ...],                       Spielkoordinaten (x = E − 411000, z = −(N − 5656200))
   "lines": [{"ref": "3", "kind": "tram|bus|sbahn|ferry|cable", "agency": ..., "head": Zielhaltestelle,
              "stops": [Halte-Index ...], "t": [Sekunden ab Abfahrt am ersten Halt ...],
              "dep": {"wt": [Sekunden seit Mitternacht ...], "sa": [...], "so": [...]}} ...]}
Eine "line" ist ein Fahrweg (Linie + Haltefolge); Abfahrten je Tagesart: Werktag (Mittwoch), Samstag, Sonntag der
laufenden Fahrplanwoche. Quelle: gtfs.de, Daten DELFI e.V. (im Spiel nennen).
"""
import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "gtfs" / "dresden"
OUT = ROOT / "godot" / "data" / "timetable.json"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
KIND = {"0": "tram", "3": "bus", "4": "ferry", "6": "cable", "7": "cable", "2": "sbahn", "1": "sbahn"}
DOW = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def rd(name):
    with open(SRC / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def secs(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def main():
    cal = rd("calendar.csv")
    exc = rd("calendar_dates.csv")
    start = min(dt.datetime.strptime(c["start_date"], "%Y%m%d").date() for c in cal)
    # erste volle Woche nach Fahrplanbeginn: Mittwoch, Samstag, Sonntag
    d0 = start + dt.timedelta(days=(7 - start.weekday()) % 7)
    days = {"wt": d0 + dt.timedelta(days=2), "sa": d0 + dt.timedelta(days=5), "so": d0 + dt.timedelta(days=6)}

    def active(day):
        ds = day.strftime("%Y%m%d")
        on = {c["service_id"] for c in cal if c[DOW[day.weekday()]] == "1" and c["start_date"] <= ds <= c["end_date"]}
        for e in exc:
            if e["date"] == ds:
                (on.add if e["exception_type"] == "1" else on.discard)(e["service_id"])
        return on
    act = {k: active(v) for k, v in days.items()}
    routes = {r["route_id"]: r for r in rd("routes.csv")}
    agency = {}
    af = ROOT / "data" / "raw" / "gtfs" / "de_nv" / "agency.txt"
    with open(af, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            agency[r["agency_id"]] = r["agency_name"]
    trips = {r["trip_id"]: r for r in rd("trips.csv")}
    stops_src = {r["stop_id"]: r for r in rd("stops.csv")}
    st = defaultdict(list)
    with open(SRC / "stop_times.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            st[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"], secs(r["departure_time"] or r["arrival_time"])))
    stop_idx, stops_out = {}, []

    def sidx(sid):
        if sid not in stop_idx:
            s = stops_src[sid]
            e, n = TO_UTM.transform(float(s["stop_lon"]), float(s["stop_lat"]))
            stop_idx[sid] = len(stops_out)
            stops_out.append([s["stop_name"], round(e - 411000.0, 1), round(-(n - 5656200.0), 1)])
        return stop_idx[sid]
    pat = {}
    for tid, lst in st.items():
        tr = trips.get(tid)
        if tr is None or len(lst) < 2:
            continue
        lst.sort()
        r = routes[tr["route_id"]]
        key = (tr["route_id"], tuple(s for _, s, _ in lst))
        t0 = lst[0][2]
        p = pat.get(key)
        if p is None:
            p = pat[key] = {"ref": r["route_short_name"].replace("F ", "F"), "kind": KIND.get(r["route_type"], "bus"),
                            "agency": agency.get(r["agency_id"], ""), "head": stops_src[lst[-1][1]]["stop_name"],
                            "stops": [sidx(s) for _, s, _ in lst], "t": [t - t0 for _, _, t in lst],
                            "dep": {"wt": [], "sa": [], "so": []}}
        for k in act:
            if tr["service_id"] in act[k]:
                p["dep"][k].append(t0)
    lines = []
    for p in pat.values():
        if not any(p["dep"].values()):
            continue
        for k in p["dep"]:
            p["dep"][k] = sorted(set(p["dep"][k]))
        lines.append(p)
    lines.sort(key=lambda p: (p["kind"], len(p["ref"]), p["ref"], -len(p["dep"]["wt"])))
    out = {"source": "gtfs.de – Soll-Fahrplandaten, bereitgestellt von DELFI e.V.",
           "days": {k: v.strftime("%Y%m%d") for k, v in days.items()}, "stops": stops_out, "lines": lines}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = defaultdict(lambda: [0, 0])
    for p in lines:
        n[p["kind"]][0] += 1
        n[p["kind"]][1] += len(p["dep"]["wt"])
    print(f"{len(lines)} Fahrwege, {len(stops_out)} Halte, {OUT.stat().st_size / 1e6:.1f} MB; Tage {out['days']}")
    for k, (a, b) in sorted(n.items()):
        print(f"  {k}: {a} Fahrwege, {b} Fahrten am Werktag")
    for ref in ("3", "11", "62"):
        ps = [p for p in lines if p["ref"] == ref][:2]
        for p in ps:
            d = p["dep"]["wt"]
            gaps = sorted(b - a for a, b in zip(d[:-1], d[1:]))
            print(f"  Linie {ref} -> {p['head']}: {len(p['stops'])} Halte, Fahrzeit {p['t'][-1] // 60} min, {len(d)} Fahrten, "
                  f"Takt (Median) {gaps[len(gaps) // 2] // 60 if gaps else '-'} min, erste {d[0] // 3600}:{d[0] % 3600 // 60:02d}" if d else f"  Linie {ref}: nur Wochenende")


if __name__ == "__main__":
    main()
