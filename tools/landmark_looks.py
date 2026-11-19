"""Dach- und Wandfarben benannter historischer Bauten setzen (Nachbearbeitung, ohne Neubau).

  python tools/landmark_looks.py [E,N ...]      (ohne Argument: alle Kacheln)

Liest tools/overrides.json "look_by_name": {Gebäudename: {"roof": "#rrggbb", "wall": "#rrggbb", "era": n, "style": n, "order_h": Meter}} und trägt die
Farben bei allen Gebäudeteilen mit genau diesem Namen ein. Wiederholbar.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
LOOKS = json.loads((ROOT / "tools" / "overrides.json").read_text(encoding="utf-8")).get("look_by_name", {})


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    n = 0
    for nm in names:
        cf = TILES / nm / "city.json"
        if not cf.exists():
            continue
        city = json.loads(cf.read_text(encoding="utf-8"))
        ch = 0
        for b in city.get("buildings", []):
            lk = LOOKS.get(b.get("name") or "")
            if not lk and b.get("kind") in ("church", "cathedral", "chapel") and b.get("style") == 1 \
                    and int(b.get("era") or 0) in (0, 1, 2, 3, 4, 5, 6, 7, 17):
                # historische Kirchen: hohe Rundbogenfenster in ein bis mehreren Zonen (Epoche 17)
                lk = {"era": 17, "order_h": 11.0}
            elif lk and "era" not in lk and b.get("kind") in ("church", "cathedral", "chapel") and b.get("style") == 1:
                lk = dict(lk, era=17, order_h=11.0)
            if not lk:
                continue
            if lk.get("roof") and b.get("roof_col") != lk["roof"]:
                b["roof_col"] = lk["roof"]
                ch += 1
            if lk.get("wall") and b.get("wall") != lk["wall"]:
                b["wall"] = lk["wall"]
                ch += 1
            if lk.get("era") and b.get("era") != lk["era"]:
                b["era"] = lk["era"]
                ch += 1
            if lk.get("style") is not None and b.get("style") != lk["style"]:
                b["style"] = lk["style"]
                ch += 1
            if lk.get("order_h"):
                # eine Ordnung je order_h Meter Traufhöhe (barocke Galerien: ein hohes Geschoss)
                lv = max(1, int(round(float(b.get("eave", 0.0)) / float(lk["order_h"]))))
                if b.get("levels") != lv:
                    b["levels"] = lv
                    ch += 1
        if ch:
            cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
            n += ch
    print(f"Wahrzeichen-Farben: {n} Änderungen in {len(names)} Kacheln")


if __name__ == "__main__":
    main()
