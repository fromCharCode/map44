"""Brückendecks freihalten (Nachbearbeitung, ohne Neubau der Kachel).

  python tools/under_decks.py [E,N ...] [--dry]      (ohne Argument: alle Kacheln)

1. Laternen und Bäume, die unter einem Brückendeck (LoD2-Deck oder Plattenbrücke) stehen und höher sind als der
   Raum darunter, stießen durch das Deck (Laternen der unterquerenden Straße mitten auf dem Gleisbett); Bäume
   standen außerdem auf Decks im Gleis- oder Fahrbahnbereich. Sie entfallen.
   Laternen: Masthöhe 9,5 m angenommen; Bäume: Höhe aus den Baumdaten (Feld 5, sonst 8 m).
2. Wo das Gelände eine Brückenfahrbahn überdeckt (kurze Brücken, Widerlagerbereiche: Gelände nicht mehr als 0,35 m
   unter dem Straßenprofil), zeigte es dort Gehwegpflaster, Gras oder Waldboden statt Asphalt – die Fahrbahn schien
   vor dem Deck unterbrochen. In diesem Bereich wird die Bodenmaske (splat0.png, Kanal R) in Fahrbahnbreite auf
   Asphalt gesetzt und der Bewuchs (cover.png) gelöscht.
3. Bewuchs (cover.png) auf Decks, die weniger als 2,5 m über dem Gelände liegen, wird gelöscht (Büsche auf Fahrbahn
   und Kappe).
Wiederholbar.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
NO_VEH = {"footway", "path", "cycleway", "steps", "pedestrian", "track", "bridleway", "corridor", "platform"}
LAMP_H = 9.5


def tile_fix(name, dry=False):
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return {}
    city = json.loads(cf.read_text(encoding="utf-8"))
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    st = {}
    # --- 1. Laternen und Bäume unter Decks -------------------------------------------------------------------------
    tris, ys = [], []
    for bm in city.get("bridge_meshes") or []:
        v = bm.get("top0") or bm.get("bot") or []
        for t in np.array(v, dtype=float).reshape(-1, 3, 3):
            p = Polygon([(t[0][0], t[0][2]), (t[1][0], t[1][2]), (t[2][0], t[2][2])])
            if p.is_valid and p.area > 0.01:
                tris.append(p)
                ys.append(float(t[:, 1].min()))
    # Plattenbrücken (city["bridges"], auch die Bahnbrücken-Platten aus rail_slabs.py): Band in Plattenbreite
    for b in city.get("bridges") or []:
        bp = b.get("pts") or []
        if len(bp) < 2:
            continue
        hw = float(b.get("width", 4.0)) * 0.5 + (1.0 if b.get("kind") == "drive" else 0.0)
        for q0, q1 in zip(bp[:-1], bp[1:]):
            seg = LineString([(q0[0], q0[1]), (q1[0], q1[1])])
            if seg.length < 0.05:
                continue
            tris.append(seg.buffer(hw, cap_style="flat"))
            ys.append(min(float(q0[2]), float(q1[2])))
    changed = False
    if tris:
        tree = STRtree(tris)

        def deck_y(x, z):
            q = Point(x, z)
            best = None
            for i in tree.query(q):
                if tris[int(i)].contains(q):
                    best = ys[int(i)] if best is None else min(best, ys[int(i)])
            return best

        def pokes(x, z, y, h):
            dy = deck_y(x, z)
            return dy is not None and dy - y > 2.0 and y + h > dy - 0.4

        def tree_bad(x, z, y, h):
            """Baum stößt von unten durch das Deck oder steht auf dem Deck (Stamm im Gleis-/Fahrbahnbereich)"""
            dy = deck_y(x, z)
            return dy is not None and dy - y > -1.5 and y + h > dy - 0.4

        for key in ("lamps", "lamps0"):
            lst = city.get(key)
            if not lst:
                continue
            keep = [l for l in lst if not pokes(l[0], l[1], float(l[2]), LAMP_H)]
            if len(keep) != len(lst):
                if key == "lamps":
                    st["Laternen"] = len(lst) - len(keep)
                city[key] = keep
                changed = True
        trees = city.get("trees") or []
        keep = [t for t in trees if not tree_bad(t[0], t[1], float(t[2]), float(t[5]) if len(t) > 5 and t[5] else 8.0)]
        if len(keep) != len(trees):
            st["Bäume"] = len(trees) - len(keep)
            city["trees"] = keep
            changed = True
    # --- 1b. Bäume im Gleis (auch auf Bahnbrücken und Dämmen): Stamm näher als 1,6 m an einer Gleisachse ----------
    rl = [LineString([(q[0], q[1]) for q in r["pts"]]) for r in city.get("rails", [])
          if len(r.get("pts", [])) >= 2 and not r.get("tunnel")]
    if rl and city.get("trees"):
        rtree = STRtree(rl)

        def on_track(x, z):
            q = Point(x, z)
            return any(rl[int(i)].distance(q) < 1.6 for i in rtree.query(q.buffer(1.6)))
        keep = [t for t in city["trees"] if not on_track(t[0], t[1])]
        if len(keep) != len(city["trees"]):
            st["Bäume im Gleis"] = len(city["trees"]) - len(keep)
            city["trees"] = keep
            changed = True
    # --- 2. Gelände über der Brückenfahrbahn: Asphalt in die Bodenmaske --------------------------------------------
    sf, tf = d / "splat0.png", d / "terrain.f32"
    polys = []
    if sf.exists() and tf.exists():
        ter = np.frombuffer(tf.read_bytes(), dtype="<f4").reshape(2000, 2000)

        def h_at(x, z):
            c = int(round(min(max(x - x0 - 0.5, 0.0), 1999.0)))
            r = int(round(min(max(z - z0 - 0.5, 0.0), 1999.0)))
            return float(ter[r, c])

        for r in city.get("roads", []):
            if not r.get("bridge") or r.get("cls") in NO_VEH or len(r.get("pts", [])) < 2:
                continue
            pts = r["pts"]
            ln = LineString([(p[0], p[1]) for p in pts])
            if ln.length < 1.0:
                continue
            cum = np.concatenate([[0.0], np.cumsum([((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
                                                    for a, b in zip(pts[:-1], pts[1:])])])
            hw = max((float(r["width"]) - float(r.get("pl", 0.0)) - float(r.get("pr", 0.0))) * 0.5, 1.5)
            n = max(2, int(ln.length / 1.0) + 1)
            run = []
            for k in range(n + 1):
                s = min(k * ln.length / n, ln.length)
                q = ln.interpolate(s)
                y = float(np.interp(s, cum, [p[2] for p in pts]))
                inside = x0 <= q.x < x0 + 2000.0 and z0 <= q.y < z0 + 2000.0
                if inside and h_at(q.x, q.y) >= y - 0.35:
                    run.append((q.x, q.y))
                else:
                    if len(run) >= 2:
                        polys.append(LineString(run).buffer(hw, cap_style="flat"))
                    run = []
            if len(run) >= 2:
                polys.append(LineString(run).buffer(hw, cap_style="flat"))
    if polys:
        area = unary_union(polys)
        im = Image.open(sf)
        f = im.size[0] / 2000.0
        mask = Image.new("L", im.size, 0)
        dr = ImageDraw.Draw(mask)
        for g in getattr(area, "geoms", [area]):
            if g.geom_type == "Polygon" and g.area > 0.2:
                dr.polygon([((x - x0) * f, (z - z0) * f) for x, z in g.exterior.coords], fill=255)
        m = np.asarray(mask) > 0
        arr = np.array(im)
        todo = m & ((arr[:, :, 0] < 250) | (arr[:, :, 1] > 5) | (arr[:, :, 2] > 5))
        npx = int(np.count_nonzero(todo))
        if npx:
            st["m² Asphalt über Brückenfahrbahn"] = round(npx / (f * f))
            if not dry:
                arr[m, 0] = 255
                arr[m, 1] = 0
                arr[m, 2] = 0
                Image.fromarray(arr, im.mode).save(sf, optimize=False, compress_level=3)
                cp = d / "cover.png"
                if cp.exists():
                    cov = np.array(Image.open(cp).convert("RGB"))
                    cm = Image.new("L", (cov.shape[1], cov.shape[0]), 0)
                    cd = ImageDraw.Draw(cm)
                    fc = cov.shape[1] / 2000.0
                    for g in getattr(area, "geoms", [area]):
                        if g.geom_type == "Polygon" and g.area > 0.2:
                            cd.polygon([((x - x0) * fc, (z - z0) * fc) for x, z in g.buffer(1.0).exterior.coords], fill=255)
                    cmm = np.asarray(cm) > 0
                    if cmm.any() and cov[cmm].any():
                        cov[cmm] = 0
                        Image.fromarray(cov, "RGB").save(cp, optimize=False, compress_level=3)
    # --- 3. Bewuchs auf Decks: Büsche und Gras des Geländes wuchsen durch flach aufliegende Decks ------------------
    cp = d / "cover.png"
    if tris and cp.exists() and tf.exists():
        ter3 = np.frombuffer(tf.read_bytes(), dtype="<f4").reshape(2000, 2000)
        cov = np.array(Image.open(cp).convert("RGB"))
        fc = cov.shape[1] / 2000.0
        cm = Image.new("L", (cov.shape[1], cov.shape[0]), 0)
        cd = ImageDraw.Draw(cm)
        for pg, dy in zip(tris, ys):
            c0 = pg.centroid
            cc = int(round(min(max(c0.x - x0 - 0.5, 0.0), 1999.0)))
            rr = int(round(min(max(c0.y - z0 - 0.5, 0.0), 1999.0)))
            if dy - float(ter3[rr, cc]) < 2.5:            # Bewuchs (bis ~2 m hoch) würde das Deck erreichen
                cd.polygon([((x - x0) * fc, (z - z0) * fc) for x, z in pg.exterior.coords], fill=255)
        cmm = np.asarray(cm) > 0
        npx = int(np.count_nonzero(cmm & (cov.sum(axis=2) > 0)))
        if npx:
            st["m² Bewuchs auf Decks"] = round(npx / (fc * fc))
            if not dry:
                cov[cmm] = 0
                Image.fromarray(cov, "RGB").save(cp, optimize=False, compress_level=3)
    if changed and not dry:
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    if st:
        print(f"  {name}: " + ", ".join(f"{v} {k}" for k, v in st.items()), flush=True)
    return st


def main():
    dry = "--dry" in sys.argv
    args = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")]
    names = args or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = {}
    for nm in names:
        for k, v in tile_fix(nm, dry).items():
            tot[k] = tot.get(k, 0) + v
    print("Brückendecks freihalten: " + (", ".join(f"{v} {k}" for k, v in tot.items()) or "nichts zu tun")
          + (" (nur gezählt)" if dry else ""))


if __name__ == "__main__":
    main()
