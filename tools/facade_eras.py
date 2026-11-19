"""Bauepoche je Gebäude für den Fassaden-Baukasten: city["buildings"][i]["era"] (Kennzahl) und ["yr"] (Baujahr,
belegt oder geschätzt). Nachbearbeitung ohne Neubau der Kachel.

  python tools/facade_eras.py [E,N ...]      (ohne Argument: alle Kacheln)

Grundlagen (in dieser Reihenfolge):
  * echtes Baujahr aus den Denkmallisten (Feld "dk", rund 9 900 Gebäude),
  * Baualtersklassen des Zensus 2022 im 100-m-Gitter und Strukturtypen der Stadt (tools/build_years.py): das Jahr
    wird je Gebäude deterministisch aus der Verteilung der Zelle gezogen,
  * Bautyp aus dem Grundriss: freistehend/angebaut (Feld "pw"), Grundfläche, Geschosse, bisheriger Stil.
Die Epochen entsprechen data/research/fassaden.json (Recherche mit Bildbelegen).
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_years as by  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
ERAS = ["", "barock", "klassizismus", "dresdner_schule", "gruenderzeit", "wuerfelhaus", "klinker", "jugendstil_reform",
        "weimar", "ns_heimatschutz", "wiederaufbau_50er", "ddr_typenbau", "nach_1990", "villen", "dorfkern",
        "industrie_kommunal"]
E_ = {n: i for i, n in enumerate(ERAS)}
ERA_FIX = json.loads((ROOT / "tools" / "overrides.json").read_text(encoding="utf-8")).get("era_by_gid", {})
BLOCK = {"C11", "C21", "C31", "C12"}
VILLAGE = {"A11", "A21"}
CUBE = {"A13"}
SINGLE = {"A12", "B11"}


def _u(bid, salt):
    h = hashlib.md5(f"{bid}:{salt}".encode()).digest()
    return int.from_bytes(h[:4], "little") / 4294967296.0


def _area(ring):
    a = 0.0
    for (x0, z0), (x1, z1) in zip(ring, ring[1:] + ring[:1]):
        a += x0 * z1 - x1 * z0
    return abs(a) * 0.5


def era_by_year(y):
    if y < 1770:
        return "barock"
    if y < 1845:
        return "klassizismus"
    if y < 1872:
        return "dresdner_schule"
    if y < 1898:
        return "gruenderzeit"
    if y < 1919:
        return "jugendstil_reform"
    if y < 1934:
        return "weimar"
    if y < 1946:
        return "ns_heimatschutz"
    if y < 1963:
        return "wiederaufbau_50er"
    if y < 1991:
        return "ddr_typenbau"
    return "nach_1990"


def tile_eras(name):
    cf = TILES / name / "city.json"
    if not cf.exists():
        return None
    city = json.loads(cf.read_text(encoding="utf-8"))
    bl = city.get("buildings", [])
    if not bl:
        return {}
    pos = np.array([b.get("pos") or (b["rings"][0][0] if b.get("rings") else [0, 0]) for b in bl], float)
    info = by.lookup_many(pos[:, 0] + ORIGIN_E, ORIGIN_N - pos[:, 1])
    codes = by._grid()["meta"]["sst_codes"]
    bounds = by.YEAR_BOUNDS
    stat = {}
    for i, b in enumerate(bl):
        bid = b.get("gid") or b["id"]
        style = int(b.get("style", 0))
        sst = codes[int(info["sst"][i])] if info["inside"][i] else ""
        detached = not b.get("pw")
        area = _area(b["rings"][0]) if b.get("rings") else 0.0
        lv = int(b.get("levels") or 1)
        dk = b.get("dk")
        year = int(dk[0]) if dk and dk[0] else None
        known = year is not None
        if year is None:
            sh = info["years"][i]
            if sh.sum() > 0:
                c = np.cumsum(sh) / sh.sum()
                k = int(np.searchsorted(c, _u(bid, "k"), side="right"))
                k = min(k, len(bounds) - 1)
                # Blockrand mit überwiegend Altbau: angebaute Häuser mit Steildach sind dort Altbau – Lückenschlüsse
                # nach 1945 haben meist ein Flachdach. (Zufallsziehung allein machte jedes dritte Gründerzeithaus
                # der Neustadt zum Siedlungsbau.)
                pitched = bool(b.get("roof")) and len(b.get("roof") or []) >= 9
                if sst in BLOCK and sh[0] / sh.sum() >= 0.40 and not detached and pitched and lv >= 3:
                    k = 0
                elif sst in BLOCK and sh[0] / sh.sum() >= 0.40 and not pitched and k == 0 and _u(bid, "f") < 0.6:
                    k = 6 if _u(bid, "g") < 0.6 else 4      # Flachdach im Altbaublock: eher Lückenschluss (Nachwende/DDR)
                lo, hi = bounds[k]
                if k == 0:
                    lo = 1872                               # „vor 1919“: in Dresden überwiegend 1872–1914
                year = int(lo + (hi - lo) * _u(bid, "y"))
        # Stil der Pipeline setzt harte Grenzen (Material, Typ, belegte Jahre)
        if style == 2:
            era = "ddr_typenbau"
        elif style == 5:
            era = "industrie_kommunal"
        elif style == 4:
            era = "nach_1990" if (year is None or year >= 1985 or not known) else era_by_year(year)
        elif style == 6:
            era = "klinker" if (year is None or year < 1919) else era_by_year(year)
        elif style == 1:
            # ohne belegtes Jahr: Barock nur im alten Stadtkern (Altstadt, Innere Neustadt), sonst reicher Historismus
            core = -300.0 <= pos[i, 0] <= 1600.0 and -2000.0 <= pos[i, 1] <= 700.0
            era = era_by_year(year) if known else ("barock" if core else "gruenderzeit")
            if era in ("gruenderzeit", "jugendstil_reform", "weimar", "ns_heimatschutz"):
                era = "dresdner_schule" if year and year < 1880 else era
        elif style == 3:
            y = year if year and 1915 <= year <= 1965 else 1925 + int(_u(bid, "z") * 14)
            era = era_by_year(y)
            year = y
        else:
            y = year if year is not None else 1895
            era = era_by_year(y)
            if era in ("gruenderzeit", "jugendstil_reform", "dresdner_schule"):
                if sst in VILLAGE and lv <= 2:
                    era = "dorfkern"
                elif detached and (sst in CUBE or (170.0 <= area <= 480.0 and 3 <= lv <= 4)):
                    era = "wuerfelhaus"
                elif detached and lv <= 3 and 90.0 <= area <= 420.0 and (sst in SINGLE or sst in CUBE or sst == "F22"):
                    era = "villen"
            elif era in ("barock", "klassizismus") and not known:
                era = "gruenderzeit"
            if sst in VILLAGE and lv <= 2 and y < 1919:
                era = "dorfkern"
        b["era"] = int(ERA_FIX.get(bid, E_[era]))
        b["yr"] = int(year) if year else 0
        stat[era] = stat.get(era, 0) + 1
    cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return stat


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = {}
    for nm in names:
        st = tile_eras(nm)
        for k, v in (st or {}).items():
            tot[k] = tot.get(k, 0) + v
    n = sum(tot.values()) or 1
    print("Epochen: " + ", ".join(f"{k} {v} ({100 * v / n:.0f} %)" for k, v in sorted(tot.items(), key=lambda t: -t[1])))


if __name__ == "__main__":
    main()
