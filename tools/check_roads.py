"""Automatische Prüfung einer gebauten Kachel (ohne Spielstart): Fahrbahn, Brücken, geparkte Autos.

Aufruf:  python check_roads.py 408,5654 [410,5656 ...]   oder  python check_roads.py --all
Liest data/processed/tiles/<E>_<N>/city.json + terrain.f32 (genau die Daten, die Godot lädt) und meldet:
  - Schweben/Versinken: Fahrbahnprofil (pts, nutzt KI/Markierung) vs. tatsächlich befahrbare Oberfläche
    (LoD2-Deck, sonst Gelände, bilinear wie Terrain.height_at)
  - Kanten: Höhensprünge der Oberfläche entlang der Fahrbahn (0,5-m-Schritte) und quer (Fahrbahnrand)
  - Mauer auf der Fahrbahn: Brüstungsstücke, die eine Fahrbahn queren
  - Gelände stößt durch ein Brückendeck
  - geparkte Autos: schief (Höhendifferenz der Räder), unter/auf Brücken, außerhalb der Kachel
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ORIGIN_E, ORIGIN_N, PROCESSED  # noqa: E402
from road_surface import raster_tris  # noqa: E402

DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "road", "busway"}


def check_tile(name: str, verbose: bool = True) -> dict:
    d = (Path(__file__).resolve().parent.parent / "data" / "processed" / "tiles" / name)
    city = json.loads((d / "city.json").read_text())
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)
    e_km, n_km = (int(v) for v in name.split("_"))
    min_e, max_n = e_km * 1000.0, (n_km + 2) * 1000.0
    x0l, z0l = min_e - ORIGIN_E, -(max_n - ORIGIN_N)          # lokale Koordinaten der NW-Ecke

    # Tunnel (tools/tunnels.py): im Tunnelband ist die befahrbare Fläche die Fahrbahnplatte, nicht der Hang darüber
    if city.get("tunnels"):
        from PIL import Image, ImageDraw
        ter = ter.copy()
        for tn in city["tunnels"]:
            q = tn["pts"]
            hw = float(tn["w"]) * 0.5 + 1.2
            for i in range(len(q) - 1):
                ax, az, bx, bz = q[i][0] - x0l, q[i][1] - z0l, q[i + 1][0] - x0l, q[i + 1][1] - z0l
                dx, dz = bx - ax, bz - az
                L = (dx * dx + dz * dz) ** 0.5 or 1.0
                nx, nz = -dz / L * hw, dx / L * hw
                c0, c1 = int(max(min(ax, bx) - hw - 2, 0)), int(min(max(ax, bx) + hw + 2, 2000))
                r0, r1 = int(max(min(az, bz) - hw - 2, 0)), int(min(max(az, bz) + hw + 2, 2000))
                if c1 <= c0 or r1 <= r0:
                    continue
                im = Image.new("L", (c1 - c0, r1 - r0), 0)
                ImageDraw.Draw(im).polygon([(ax + nx - c0 - 0.5, az + nz - r0 - 0.5), (bx + nx - c0 - 0.5, bz + nz - r0 - 0.5),
                                            (bx - nx - c0 - 0.5, bz - nz - r0 - 0.5), (ax - nx - c0 - 0.5, az - nz - r0 - 0.5)], fill=255)
                m = np.asarray(im) > 0
                ter[r0:r1, c0:c1][m] = 0.5 * (q[i][2] + q[i + 1][2])

    def terrain_at(x, z):
        c = np.clip(np.asarray(x) - x0l - 0.5, 0.0, 1998.999)
        r = np.clip(np.asarray(z) - z0l - 0.5, 0.0, 1998.999)
        c0, r0 = c.astype(int), r.astype(int)
        fc, fr = c - c0, r - r0
        top = ter[r0, c0] * (1 - fc) + ter[r0, c0 + 1] * fc
        bot = ter[r0 + 1, c0] * (1 - fc) + ter[r0 + 1, c0 + 1] * fc
        return top * (1 - fr) + bot * fr

    # LoD2-Deck-Oberkante (Kollisionsfläche) aus bridge_meshes.top
    tris = []
    for m in city.get("bridge_meshes", []):
        t = m["top"]
        for k in range(0, len(t) - 8, 9):
            tris.append([(t[k] + ORIGIN_E, ORIGIN_N - t[k + 2], t[k + 1]), (t[k + 3] + ORIGIN_E, ORIGIN_N - t[k + 5], t[k + 4]),
                         (t[k + 6] + ORIGIN_E, ORIGIN_N - t[k + 8], t[k + 7])])
    # auch Decks der Nachbarkacheln, die in diese Kachel ragen
    for de in (-2, 0, 2):
        for dn in (-2, 0, 2):
            if de == dn == 0:
                continue
            nb = d.parent / f"{e_km + de}_{n_km + dn}" / "city.json"
            if not nb.exists():
                continue
            try:
                nbc = json.loads(nb.read_text())
            except Exception:
                continue
            for m in nbc.get("bridge_meshes", []):
                t = m["top"]
                if not t:
                    continue
                xs, zs = t[0::3], t[2::3]
                if max(xs) < x0l - 5 or min(xs) > x0l + 2005 or max(zs) < z0l - 5 or min(zs) > z0l + 2005:
                    continue
                for k in range(0, len(t) - 8, 9):
                    tris.append([(t[k] + ORIGIN_E, ORIGIN_N - t[k + 2], t[k + 1]), (t[k + 3] + ORIGIN_E, ORIGIN_N - t[k + 5], t[k + 4]),
                                 (t[k + 6] + ORIGIN_E, ORIGIN_N - t[k + 8], t[k + 7])])
    deck_hi, deck_lo = raster_tris(tris, min_e, max_n, 2000, 2000)

    def deck_at(x, z):
        c = np.floor(np.asarray(x) - x0l).astype(int)
        r = np.floor(np.asarray(z) - z0l).astype(int)
        ok = (c >= 0) & (c < 2000) & (r >= 0) & (r < 2000)
        hi = np.full(c.shape, np.nan, dtype=np.float32)
        lo = np.full(c.shape, np.nan, dtype=np.float32)
        hi[ok] = deck_hi[r[ok], c[ok]]
        lo[ok] = deck_lo[r[ok], c[ok]]
        return hi, lo

    # Gebäudegrundrisse: dort darf das Gelände (Durchfahrt, Tiefgarage) vom Profil abweichen
    from PIL import Image, ImageDraw
    im = Image.new("L", (2000, 2000), 0)
    dr = ImageDraw.Draw(im)
    for b in city["buildings"]:
        if b.get("elev"):
            continue
        for i, ring in enumerate(b.get("rings", [])):
            if len(ring) >= 3:
                dr.polygon([(q[0] - x0l, q[1] - z0l) for q in ring], fill=255 if i == 0 else 0)
    bmask = np.asarray(im) > 0

    def in_building(x, z):
        c = np.clip(np.floor(np.asarray(x) - x0l).astype(int), 0, 1999)
        r = np.clip(np.floor(np.asarray(z) - z0l).astype(int), 0, 1999)
        return bmask[r, c]

    slab_ids = set(b["id"] for b in city.get("bridges", []))      # Godot baut dort eine Platte genau aufs Profil
    issues = {"schweben": [], "kante": [], "quer": [], "mauer": [], "durchstoss": 0, "parken": [], "aussen": 0}
    stats = {"km": 0.0}
    for r in city["roads"]:
        if r["cls"] not in DRIVE:
            continue
        p = np.array(r["pts"], dtype=float)
        if len(p) < 2:
            continue
        seg = np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1]))
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        if cum[-1] < 1.0:
            continue
        stats["km"] += cum[-1] / 1000.0
        s = np.arange(0.0, cum[-1], 0.5)
        x, z, y = (np.interp(s, cum, p[:, k]) for k in (0, 1, 2))
        g = terrain_at(x, z)
        hi, lo = deck_at(x, z)
        dk = np.where(np.isfinite(lo) & (np.abs(lo - y) < np.abs(hi - y)), lo, hi)
        on_deck = np.isfinite(dk) & (np.abs(dk - y) < 0.6)
        surf = np.where(on_deck, dk, g)
        # OSM-Brücke ohne LoD2-Deck: Godot baut eine Platte genau auf dem Profil
        if r["bridge"]:
            if r["id"] in slab_ids:
                surf = np.where(on_deck, dk, np.maximum(y, g))    # Platte; Gelände darüber stößt durch
            else:
                surf = np.where(on_deck, dk, np.where(g < y - 0.3, y, g))
        inb = in_building(x, z)
        surf = np.where(inb, y, surf)
        dev = surf - y
        bad = np.abs(dev) > 0.12
        if bad.any():
            k = int(np.argmax(np.abs(dev)))
            issues["schweben"].append((float(abs(dev[k])), float(dev[k]), r["name"] or r["cls"], int(r["id"]), float(x[k]), float(z[k]),
                                       int(bad.sum()) * 0.5, bool(r["bridge"])))
        jump = np.abs(np.diff(surf))
        jb = jump > 0.10
        if jb.any():
            k = int(np.argmax(jump))
            issues["kante"].append((float(jump[k]), r["name"] or r["cls"], int(r["id"]), float(x[k]), float(z[k]), int(jb.sum()), bool(r["bridge"])))
        # quer: Fahrbahnrand gegenüber Mitte (nur bei Deck/Brücke relevant und an Brückenenden)
        tx = np.gradient(x)
        tz = np.gradient(z)
        tl = np.hypot(tx, tz) + 1e-9
        nx, nz = -tz / tl, tx / tl
        off = max(float(r["width"]) / 2 - 0.6, 0.8)
        worst = (0.0, 0, 0.0, 0.0)
        for sgn in (1, -1):
            xe, ze = x + nx * off * sgn, z + nz * off * sgn
            ge = terrain_at(xe, ze)
            he, le = deck_at(xe, ze)
            de_ = np.where(np.isfinite(le) & (np.abs(le - y) < np.abs(he - y)), le, he)
            se = np.where(np.isfinite(de_) & (np.abs(de_ - y) < 0.6), de_, ge)
            if r["bridge"]:
                se = np.where(np.isfinite(de_) & (np.abs(de_ - y) < 0.6), de_, np.where(ge < y - 0.3, y, ge))
            q = np.abs(se - surf)
            k = int(np.argmax(q))
            if q[k] > worst[0]:
                worst = (float(q[k]), k, float(xe[k]), float(ze[k]))
        if worst[0] > 0.25:
            issues["quer"].append((worst[0], r["name"] or r["cls"], int(r["id"]), worst[2], worst[3], bool(r["bridge"])))
    # Gelände durch Deck
    pen = np.isfinite(deck_lo) & (ter > deck_lo + 0.02)
    issues["durchstoss"] = int(pen.sum())
    # Brüstung quer über einer Fahrbahn
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    lines = []
    for r in city["roads"]:
        if r["cls"] in DRIVE and len(r["pts"]) >= 2:
            lines.append((LineString([(q[0], q[1]) for q in r["pts"]]), r, np.array(r["pts"])))
    tree = STRtree([l for l, _, _ in lines]) if lines else None
    for rl in city.get("bridge_rails", []):
        seg = LineString([(rl[0], rl[1]), (rl[2], rl[3])])
        if tree is None:
            break
        for i in tree.query(seg):
            l, r, pts = lines[int(i)]
            if not seg.intersects(l):
                continue
            ip = seg.intersection(l)
            if ip.geom_type != "Point":
                continue
            sp = l.project(ip)
            cum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1])))])
            yr = float(np.interp(sp, cum, pts[:, 2]))
            if abs(yr - rl[4]) < 2.0:
                issues["mauer"].append((r["name"] or r["cls"], int(r["id"]), ip.x, ip.y))
    # geparkte Autos
    for pk in city["parked"]:
        x, z, yaw = pk[0], pk[1], pk[2]
        if not (x0l <= x < x0l + 2000 and z0l <= z < z0l + 2000):
            issues["aussen"] += 1
            continue
        fx, fz = -math.sin(yaw), -math.cos(yaw)
        sx, sz = fz, -fx
        ws = [(x + fx * a + sx * b, z + fz * a + sz * b) for a in (1.3, -1.3) for b in (0.8, -0.8)]
        hs = terrain_at([w[0] for w in ws], [w[1] for w in ws])
        hc = float(terrain_at(x, z))
        hi, _ = deck_at(np.array([x]), np.array([z]))
        # ws: vorn-links, vorn-rechts, hinten-links, hinten-rechts
        twist = float(abs(hs[0] - hs[1] - hs[2] + hs[3]) / 2.0)          # steht auf 3 Rädern
        roll = float(abs((hs[0] + hs[2]) - (hs[1] + hs[3])) / 2.0 / 1.6)  # Querneigung (Bordstein)
        under = bool(np.isfinite(hi[0]) and hi[0] - hc < 2.5)
        if twist > 0.08 or roll > 0.12 or under:
            issues["parken"].append((max(twist, roll), x, z, "unter Brücke" if under else ("verwunden" if twist > 0.08 else "Querneigung"), hc))
    for k in ("manholes", "grates"):
        for q in city.get(k, []):
            if not (x0l <= q[0] < x0l + 2000 and z0l <= q[1] < z0l + 2000):
                issues["aussen"] += 1
    for r in city["roads"]:
        for q in r["pts"]:
            if not (x0l - 0.05 <= q[0] <= x0l + 2000.05 and z0l - 0.05 <= q[1] <= z0l + 2000.05):
                issues["aussen"] += 1
    if verbose:
        report(name, issues, stats)
    return issues


def report(name, iss, stats):
    print(f"== Kachel {name}: {stats['km']:.0f} km Fahrbahn")
    print(f"   Schweben/Versinken > 12 cm: {len(iss['schweben'])} Straßen, davon Brücken {sum(1 for i in iss['schweben'] if i[7])}")
    for i in sorted(iss["schweben"], reverse=True)[:6]:
        print(f"      {i[1]:+.2f} m  {i[2]} ({i[3]})  @ {i[4]:.0f},{i[5]:.0f}  ({i[6]:.0f} m){'  [Brücke]' if i[7] else ''}")
    print(f"   Kanten > 10 cm längs: {len(iss['kante'])} Straßen")
    for i in sorted(iss["kante"], reverse=True)[:6]:
        print(f"      {i[0]:.2f} m  {i[1]} ({i[2]})  @ {i[3]:.0f},{i[4]:.0f}  ({i[5]}x){'  [Brücke]' if i[6] else ''}")
    print(f"   Querkanten > 25 cm (Fahrbahnrand): {len(iss['quer'])} Straßen")
    for i in sorted(iss["quer"], reverse=True)[:6]:
        print(f"      {i[0]:.2f} m  {i[1]} ({i[2]})  @ {i[3]:.0f},{i[4]:.0f}{'  [Brücke]' if i[5] else ''}")
    print(f"   Brüstung quer über Fahrbahn: {len(iss['mauer'])}")
    for i in iss["mauer"][:6]:
        print(f"      {i[0]} ({i[1]}) @ {i[2]:.0f},{i[3]:.0f}")
    print(f"   Gelände stößt durch Deck: {iss['durchstoss']} m²")
    print(f"   Geparkte Autos auffällig: {len(iss['parken'])}  (verwunden {sum(1 for i in iss['parken'] if i[3] == 'verwunden')}, "
          f"Querneigung {sum(1 for i in iss['parken'] if i[3] == 'Querneigung')}, unter Brücke {sum(1 for i in iss['parken'] if i[3] == 'unter Brücke')})")
    for i in sorted(iss["parken"], reverse=True)[:4]:
        print(f"      {i[3]} {i[0]:.2f} m @ {i[1]:.0f},{i[2]:.0f}")
    print(f"   Objekte außerhalb der Kachel: {iss['aussen']}")


def main():
    args = sys.argv[1:]
    base = Path(__file__).resolve().parent.parent / "data" / "processed" / "tiles"
    if args == ["--all"]:
        names = sorted(p.name for p in base.iterdir() if (p / "city.json").exists())
        tot = {"schweben": 0, "kante": 0, "quer": 0, "mauer": 0, "durchstoss": 0, "parken": 0, "aussen": 0}
        for n in names:
            iss = check_tile(n, verbose=False)
            line = []
            for k in tot:
                v = iss[k] if isinstance(iss[k], int) else len(iss[k])
                tot[k] += v
                line.append(f"{k}={v}")
            print(n, " ".join(line), flush=True)
        print("GESAMT", " ".join(f"{k}={v}" for k, v in tot.items()))
        return
    for a in args:
        check_tile(a.replace(",", "_"))


if __name__ == "__main__":
    main()
