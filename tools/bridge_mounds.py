"""Falsche Geländehügel unter Brückenfeldern entfernen (Nachbearbeitung vor bridge_arches/bridge_ramps).

  python tools/bridge_mounds.py [--dry] [E,N ...]      (ohne Argument: alle Kacheln)

Befund (Waldschlößchenbrücke, Südufer am Bogenfuß): die Geländeanpassung an die Fahrbahn (road_surface.conform) hob
das Gelände unter dem Deck stellenweise bis 12 m über das DGM an – sichtbar als grauer Erdkegel unter der Brücke.
Hier wird solches Gelände auf das DGM (terrain_raw.f32) zurückgesetzt, aber nur, wenn
  * ein LoD2-Deck darüber liegt (≥ 60 % des Hügels unter dem Deck, Deck ≥ 6 m über DGM),
  * das Gelände ≥ 2,5 m über dem DGM und ≥ 1 m unter dem Deck liegt,
  * kein Weg/Gleis (außer der Brücke selbst) darüber führt und
  * der Hügel ≥ 25 m von jedem Brückenende (Übergang Deck/Gelände der Fahrbahn oder Wegende auf dem Deck, z. B.
    Tunnelportal) entfernt ist – Widerlager-Rampen bleiben.
Schreibt terrain.f32 und terrain_col.f32.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, gaussian_filter, grey_dilation, label

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bridge_ramps as br  # noqa: E402

END_CLEAR = 25.0


def mounds_tile(name, dry=False):
    d = br.TILES / name
    cf = d / "city.json"
    if not cf.exists() or not (d / "terrain_raw.f32").exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    if not city.get("bridge_meshes"):
        return 0
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - br.ORIGIN_E, -((n_km + 2) * 1000.0 - br.ORIGIN_N)
    h = br._deck_heights(city, x0, z0)
    has = np.isfinite(h)
    if not has.any():
        return 0
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000).copy()
    raw = np.frombuffer((d / "terrain_raw.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)
    hd = grey_dilation(np.where(has, h, -1e9), size=(17, 17))
    # Wege (ohne Brückenwege) und Brückenenden als Sperrzonen
    rm = Image.new("L", (2000, 2000), 0)
    dr = ImageDraw.Draw(rm)
    ends = Image.new("L", (2000, 2000), 0)
    de = ImageDraw.Draw(ends)
    for r in city.get("roads", []) + city.get("rails", []):
        if len(r["pts"]) < 2:
            continue
        if not r.get("bridge"):
            w = float(r.get("width", 3.0)) * 0.5 + 2.0
            dr.line([(p[0] - x0, p[1] - z0) for p in r["pts"]], fill=255, width=max(1, int(w * 2)))
        samp = br._samples(r["pts"], 1.0)
        on = [br._deck_at(h, x - x0, z - z0) is not None for x, z, _y in samp]
        if r.get("bridge"):
            # Wegende auf dem Deck (z. B. Übergang in einen Tunnel, Kachelrand) zählt als Brückenende
            for j in (0, len(samp) - 1):
                if on[j]:
                    x, z = samp[j][0] - x0, samp[j][1] - z0
                    de.ellipse([x - END_CLEAR, z - END_CLEAR, x + END_CLEAR, z + END_CLEAR], fill=255)
        for i in range(1, len(samp)):
            if on[i] != on[i - 1]:
                x, z = samp[i][0] - x0, samp[i][1] - z0
                de.ellipse([x - END_CLEAR, z - END_CLEAR, x + END_CLEAR, z + END_CLEAR], fill=255)
    block = (np.asarray(rm) > 0) | (np.asarray(ends) > 0)
    bad = (hd > -1e8) & (hd - raw > 6.0) & (ter - raw > 2.5) & (hd - ter > 1.0) & ~block
    lab, n = label(bad)
    fix = np.zeros_like(bad)
    n_fix = 0
    for i in range(1, n + 1):
        m = lab == i
        cnt = int(m.sum())
        if cnt < 15 or has[m].mean() < 0.6:
            continue
        rr, cc = np.nonzero(m)
        print(f"  {name}: Hügel x {cc.mean() + x0:.0f} z {rr.mean() + z0:.0f}, {cnt} m², bis "
              f"{float((ter - raw)[m].max()):.1f} m über DGM -> DGM")
        fix |= m
        n_fix += 1
    if n_fix == 0 or dry:
        return n_fix
    # weich zurück aufs DGM: Kern voll, 3-m-Saum ausgeblendet (keine Kante zum Umfeld)
    core = binary_dilation(fix, iterations=2)
    wgt = np.clip(gaussian_filter(core.astype(np.float32), 1.5) * 1.6, 0.0, 1.0)
    wgt[block] = 0.0
    out = (ter + (raw - ter) * wgt * (ter > raw)).astype("<f4")
    (d / "terrain.f32").write_bytes(out.tobytes())
    mid = 0.5 * (out[:, :-1] + out[:, 1:])
    row = np.concatenate([out[:, :1], mid, out[:, -1:]], axis=1)
    midr = 0.5 * (row[:-1] + row[1:])
    pad = np.concatenate([row[:1], midr, row[-1:]], axis=0).astype("<f4")
    (d / "terrain_col.f32").write_bytes(pad.tobytes())
    return n_fix


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    names = [a.replace(",", "_") for a in args] or sorted(p.name for p in br.TILES.iterdir() if p.is_dir())
    tot = 0
    for nm in names:
        tot += mounds_tile(nm, dry)
    print(f"Brückenhügel: {tot} entfernt in {len(names)} Kacheln" + (" (Probelauf)" if dry else ""))


if __name__ == "__main__":
    main()
