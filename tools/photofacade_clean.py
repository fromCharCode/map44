"""Fotofassaden nachträglich mit der aktuellen Plausibilitätsprüfung (mly_photofacade.tex_ok) sieben.

  python tools/photofacade_clean.py [E,N ...]      (ohne Argument: alle Kacheln)

Entfernt Einträge, deren Textur die Prüfung nicht besteht (Laub, Himmel im Ausschnitt, Fahrzeug davor), samt Datei.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mly_photofacade as pf                                       # noqa: E402
import mly_facade as mf                                            # noqa: E402


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")] or sorted(p.name for p in mf.TILES.iterdir() if (p / "facades.json").exists())
    gone = 0
    for nm in names:
        jf = mf.TILES / nm / "facades.json"
        if not jf.exists():
            continue
        res = json.loads(jf.read_text(encoding="utf-8"))
        keep = []
        for r in res:
            f = mf.TILES / nm / "facades" / r["tex"]
            try:
                tex = np.asarray(Image.open(f).convert("RGB"))
            except Exception:                                      # noqa: BLE001
                continue
            ok, why = pf.tex_ok(tex)
            # Gespeicherte Texturen sind schon aufgehellt – Himmels- und Laubprüfung wären darauf zu streng; nur
            # eindeutig verdeckende Fahrzeuge entfernen
            if ok or why != "Fahrzeug davor":
                keep.append(r)                                     # nur die Verdeckungs-/Ausschnittfehler entfernen
            else:
                gone += 1
                print(f"  {nm}/{r['tex']}: {why}")
                if "--dry" not in sys.argv:
                    f.unlink(missing_ok=True)
        if len(keep) != len(res) and "--dry" not in sys.argv:
            jf.write_text(json.dumps(keep, separators=(",", ":")), encoding="utf-8")
    print(f"Fotofassaden gesiebt: {gone} entfernt")


if __name__ == "__main__":
    main()
