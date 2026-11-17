"""Straßenoberfläche: durchgehender Höhenverlauf (Längsprofil) aller Wege und Anpassung des Geländes daran.

Vorbild sind Straßen-Editoren wie RoadRunner, CityEngine oder Cities: Skylines: Die Straße ist primär, das
Gelände folgt ihr (nicht umgekehrt).

1. Alle Wege (Straßen, Fußwege, Gleise) im Fenster Kachel ± PAD werden im Abstand <= STEP abgetastet.
   Gemeinsame OSM-Knoten sind gemeinsame Unbekannte -> Kreuzungen und Wegübergänge sind automatisch stetig.
2. Längsprofil  y = argmin  Σ w·h·(y − Ziel)²  +  Σ ℓ⁴·h·(y'')²     (dünnbesetztes LGS, scipy)
   Ziel: DGM-Gelände (Gewicht 1, robust per Huber-Gewichtung) bzw. LoD2-Brückendeck (fest).
   Frei (nur Glättung): unter Brücken (DGM dort unzuverlässig) und Brückenwege ohne Deck.
   Krümmungsterme laufen auch über Wegstöße (Knoten mit 2 Wegen bzw. geradeaus durch Kreuzungen),
   dadurch gibt es am Brückenende keinen Knick. Steigungen, die nur das Verfahren erzeugt (nicht das Gelände),
   werden per Nachiteration (größeres ℓ, kleineres Datengewicht) auf G_MAX begrenzt.
3. conform(): Gelände entlang jeder Fahrbahn exakt auf das Profil (quer eben), Böschung ~1:1.5 zum Umland,
   mehrere Wege werden distanzgewichtet gemischt; unter Brückendecks bleibt das Gelände unter der Deckunterkante.

Fenster-Lösung: Weil jede Kachel ihr Fenster mit 320 m Rand löst und der Einfluss eines Datenpunkts mit
≈ e^(−x/ℓ) abklingt, stimmen die Profile benachbarter Kacheln an der Grenze praktisch exakt überein.
"""
import math
import time

import numpy as np
from scipy import sparse
from scipy.ndimage import map_coordinates
from scipy.sparse.linalg import spsolve
from shapely.geometry import LineString, box

STEP = 2.0          # m, maximaler Abstand der Profilpunkte
PAD = 320.0         # m, Fensterrand um die Kachel
W_DECK = 300.0      # Gewicht eines Brückendeck-Punkts im Löser (weich); exakt aufs Deck setzt danach _pin_decks.
#                     Ein festes Gewicht (20000) zog über gemeinsame Knoten falsch zugeordnete Nachbarwege mit
#                     (Leisniger Platz 7 m hoch, Autobahn-Dellen 2 m) – die Korrektur bleibt deshalb örtlich.
PIN_R = 12.0        # m, Länge der Angleichrampe auf der Zufahrt
PIN_MAX = 1.0       # m, größere Abweichungen vom Deck gelten als Zuordnungsfehler und werden nicht übertragen
# Unterführungen: Mindest-Durchfahrtshöhe unter der Deckunterkante (LoD2-Deck 1 m dick). Das DGM ist unter Brücken
# interpoliert (Laserscan sieht nicht unter das Deck) und kennt kurze Senken der Unterführung nicht.
W_CLR = 60.0
CLR_UNDER = {"motorway": 4.7, "trunk": 4.5, "primary": 4.5, "secondary": 4.5, "tertiary": 4.2, "motorway_link": 4.5,
             "trunk_link": 4.5, "primary_link": 4.5, "secondary_link": 4.5, "tertiary_link": 4.2, "unclassified": 4.0,
             "residential": 4.0, "living_street": 3.6, "service": 3.6, "track": 3.6, "pedestrian": 2.6,
             "footway": 2.6, "path": 2.6, "cycleway": 2.6, "steps": 2.6, "bridleway": 2.6,
             "tram": 4.7, "rail": 5.5, "light_rail": 5.0, "narrow_gauge": 4.0}
EPS = 1e-6          # Regularisierung freier Punkte
HUBER = 0.25        # m, ab dieser Abweichung vom DGM wird ein Punkt herabgewichtet

# Glättungslänge ℓ je Wegart (m) und maximal erzeugte Steigung
ELL = {"major": 14.0, "minor": 9.0, "walk": 4.0, "steps": 1.2, "rail": 24.0, "tram": 14.0}
G_MAX = {"major": 0.09, "minor": 0.13, "rail": 0.04, "tram": 0.07}
MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link", "primary_link",
         "secondary_link", "tertiary_link"}
MINOR = {"unclassified", "residential", "living_street", "service", "road", "busway"}
SKIP = {"corridor", "elevator", "construction", "proposed", "planned", "platform", "bus_stop", "abandoned", "razed",
        "disused", "no"}


def lclass(kind: str, cls: str) -> str:
    if kind == "rail":
        return "rail" if cls != "tram" else "tram"
    if cls in MAJOR:
        return "major"
    if cls in MINOR:
        return "minor"
    if cls == "steps":
        return "steps"
    return "walk"


# ---------------------------------------------------------------------------
class Mosaic:
    """Rohes DGM (terrain_raw.f32) der Kachel und ihrer 8 Nachbarn, 1 m, relativ zu base_height."""

    def __init__(self, tiles_dir, e_km: int, n_km: int):
        self.x0 = (e_km - 2) * 1000.0
        self.ytop = (n_km + 4) * 1000.0
        self.a = np.full((6000, 6000), np.nan, dtype=np.float32)
        for de in (-2, 0, 2):
            for dn in (-2, 0, 2):
                p = tiles_dir / f"{e_km + de}_{n_km + dn}" / "terrain_raw.f32"
                if not p.exists():
                    continue
                arr = np.frombuffer(p.read_bytes(), dtype="<f4").reshape(2000, 2000)
                r0, c0 = (1 - dn // 2) * 2000, (de // 2 + 1) * 2000      # Zeile 0 = Nordrand
                self.a[r0:r0 + 2000, c0:c0 + 2000] = arr

    def sample(self, e, n):
        c = np.asarray(e) - self.x0 - 0.5
        r = self.ytop - np.asarray(n) - 0.5
        return map_coordinates(self.a, [r, c], order=1, mode="constant", cval=np.nan)


def raster_tris(tris, x0: float, ytop: float, w: int, h: int):
    """Dreiecke [(e,n,z)x3] (z relativ base) -> (hi, lo) Raster (1 m, NaN = frei)."""
    hi = np.full((h, w), np.nan, dtype=np.float32)
    lo = np.full((h, w), np.nan, dtype=np.float32)
    for tri in tris:
        xs = [q[0] - x0 for q in tri]
        ys = [ytop - q[1] for q in tri]
        zs = [q[2] for q in tri]
        cx0, cx1 = int(max(min(xs), 0)), int(min(max(xs) + 1, w - 1))
        cy0, cy1 = int(max(min(ys), 0)), int(min(max(ys) + 1, h - 1))
        if cx1 < cx0 or cy1 < cy0:
            continue
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(cx0, cx1 + 1) + 0.5, np.arange(cy0, cy1 + 1) + 0.5)
        l1 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        l2 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        l3 = 1 - l1 - l2
        m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not m.any():
            continue
        z = (l1 * zs[0] + l2 * zs[1] + l3 * zs[2]).astype(np.float32)
        sh = hi[cy0:cy1 + 1, cx0:cx1 + 1]
        sl = lo[cy0:cy1 + 1, cx0:cx1 + 1]
        sh[m] = np.where(np.isnan(sh[m]), z[m], np.maximum(sh[m], z[m]))
        sl[m] = np.where(np.isnan(sl[m]), z[m], np.minimum(sl[m], z[m]))
    return hi, lo


def _smoothstep(a, b, x):
    u = np.clip((x - a) / np.maximum(b - a, 1e-6), 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


# ---------------------------------------------------------------------------
class RoadSurface:
    """ways: Liste {"id", "kind" ('road'|'rail'), "cls", "hw" (halbe Breite), "bridge", "coords" (n,2 UTM)}.
    tile_bbox: (minE, minN, maxE, maxN). deck: (hi, lo, x0, ytop) Fenster-Raster der Brückendecks."""

    def __init__(self, ways, mosaic: Mosaic, deck, tile_bbox, dom=None, log=print):
        t0 = time.time()
        self.log = log
        self.mosaic = mosaic
        self.dom_fn = dom
        self.deck_hi, self.deck_lo, self.dx0, self.dytop = deck
        mn_e, mn_n, mx_e, mx_n = tile_bbox
        self.win = box(mn_e - PAD, mn_n - PAD, mx_e + PAD, mx_n + PAD)
        self._sample(ways)
        self._classify()
        self._joins()
        self._solve()
        self.log(f"  Straßenprofil: {len(self.pieces)} Wegstücke, {self.n} Punkte, {time.time() - t0:.1f} s")

    # --- Abtastung ---------------------------------------------------------
    def _sample(self, ways):
        key2idx = {}
        E, N = [], []

        def vertex(p):
            k = (round(p[0] * 100), round(p[1] * 100))
            i = key2idx.get(k)
            if i is None:
                i = len(E)
                key2idx[k] = i
                E.append(p[0])
                N.append(p[1])
            return i

        def free(p):
            E.append(p[0])
            N.append(p[1])
            return len(E) - 1

        self.pieces = []
        for w in ways:
            c = np.asarray(w["coords"], dtype=float)
            if len(c) < 2:
                continue
            line = LineString(c)
            if line.length < 0.5 or not line.intersects(self.win):
                continue
            if self.win.contains(line):
                geoms = [c]
            else:
                inter = line.intersection(self.win)
                geoms = [np.asarray(g.coords) for g in getattr(inter, "geoms", [inter])
                         if g.geom_type == "LineString" and g.length > 0.5]
            for g in geoms:
                idx, ss, vt = [vertex(g[0])], [0.0], [True]
                s = 0.0
                for i in range(1, len(g)):
                    seg = g[i] - g[i - 1]
                    L = math.hypot(seg[0], seg[1])
                    if L < 1e-3:
                        continue
                    k = int(math.ceil(L / STEP))
                    for j in range(1, k):
                        idx.append(free(g[i - 1] + seg * (j / k)))
                        ss.append(s + L * j / k)
                        vt.append(False)
                    s += L
                    vi = vertex(g[i])
                    if vi == idx[-1]:
                        continue
                    idx.append(vi)
                    ss.append(s)
                    vt.append(True)
                if len(idx) < 2:
                    continue
                self.pieces.append({**{k: v for k, v in w.items() if k != "coords"},
                                    "lc": lclass(w["kind"], w["cls"]),
                                    "idx": np.array(idx, dtype=np.int64), "s": np.array(ss),
                                    "vtx": np.array(vt, dtype=bool)})
        self.E = np.array(E)
        self.N = np.array(N)
        self.n = len(E)

    def _deck_at(self, e, n):
        c = np.floor(np.asarray(e) - self.dx0).astype(np.int64)
        r = np.floor(self.dytop - np.asarray(n)).astype(np.int64)
        h, w = self.deck_hi.shape
        ok = (c >= 0) & (c < w) & (r >= 0) & (r < h)
        hi = np.full(len(c), np.nan, dtype=np.float32)
        lo = np.full(len(c), np.nan, dtype=np.float32)
        hi[ok] = self.deck_hi[r[ok], c[ok]]
        lo[ok] = self.deck_lo[r[ok], c[ok]]
        return hi, lo

    # --- Einordnung der Punkte --------------------------------------------
    def _classify(self):
        self.terr = self.mosaic.sample(self.E, self.N).astype(float)
        self.hi, self.lo = self._deck_at(self.E, self.N)
        # DOM (Oberfläche): Kandidat, wo das DGM Bauwerke nicht enthält (Rampen, Brücken ohne LoD2-Deck)
        if self.dom_fn is not None:
            self.dom = np.asarray(self.dom_fn(self.E, self.N), dtype=float)
        else:
            self.dom = np.full(self.n, np.nan)
        self.dom_ok = np.isfinite(self.dom) & (~np.isfinite(self.terr) | ((self.dom > self.terr + 0.5) & (self.dom < self.terr + 15.0)))
        bridge_nodes = np.zeros(self.n, dtype=bool)
        bridge_lv = {}
        for p in self.pieces:
            if p["bridge"]:
                bridge_nodes[p["idx"]] = True
        # Brückenwege zuerst (ihre Deckhöhen – ohne fremde tiefere Decks – braucht die Zufahrtsregel)
        lv_done = False
        for p in sorted(self.pieces, key=lambda q: not q["bridge"]):
            if not p["bridge"] and not lv_done:
                for q in self.pieces:
                    if q["bridge"]:
                        self._bridge_levels(q, bridge_lv)
                lv_done = True
            idx = p["idx"]
            m = len(idx)
            hi, lo, ext = self._band_deck(p)
            p["hi"], p["lo"], p["ext"] = hi, lo, ext
            ter = self.terr[idx]
            has = np.isfinite(hi)
            # mode: 0 Gelände (oder DOM), 1 Deck (eindeutig), 2 Deck (gestapelt, später entschieden), 3 frei,
            #       4 Brückenweg ohne Deck (DOM, falls zum Verlauf passend, sonst frei)
            mode = np.zeros(m, dtype=np.int8)
            if p["bridge"]:
                mode[:] = 4
                mode[has] = np.where((hi[has] - lo[has]) < 1.5, 1, 2)
                self._foreign_low_decks(p, mode, hi, lo)
            elif has.any() and p.get("under"):
                mode[has] = 3          # OSM-"Tunnel" unter einer Brücke: liegt nie auf einem Deck (Coswiger Straße)
            elif has.any():
                # Läufe mit Deck: Zufahrt (berührt Brückenknoten) -> Deck, sonst Unterführung -> frei
                k = 0
                while k < m:
                    if not has[k]:
                        k += 1
                        continue
                    j = k
                    # ein Lauf = EIN Deck: bei Höhensprung > 1,5 m beginnt ein neuer (Parkweg unter der Löbtauer
                    # Brücke lief erst über eine niedrige Parkrampe, dann unter das 8 m höhere Deck – als ein Lauf
                    # "niedriges Deck" kletterte er am Ende auf die Brücke)
                    while j + 1 < m and has[j + 1] and abs(float(hi[j + 1]) - float(hi[j])) < 1.5:
                        j += 1
                    a, b = max(k - 1, 0), min(j + 1, m - 1)
                    # Deck kaum über dem Gelände (Bachbrücke auf Straßenhöhe, Rampe auf die Brücke): darunter passt
                    # kein Fahrzeug durch -> der Weg liegt AUF dem Deck, auch ohne Brückenkennzeichnung in OSM
                    dd = (hi[k:j + 1] - ter[k:j + 1])[np.isfinite(ter[k:j + 1])]
                    thr = 2.4 if p["lc"] in ("walk", "steps") else 3.2
                    low_deck = len(dd) > 0 and float(np.median(dd)) < thr
                    if low_deck:
                        # das DGM ist unter Brücken interpoliert (Damm durchgezogen): niedrig nur, wenn auch das
                        # Gelände VOR dem Deck entlang des Wegs nahe der Deckhöhe liegt (Wirtschaftsweg unter der
                        # EÜ in 410_5656 lag sonst auf dem Bahndeck)
                        ga, gb = self._outside_ground(idx, k, j)
                        if k > 0 and np.isfinite(ter[k - 1]):
                            ga = float(ter[k - 1])            # direkter Nachbarpunkt vor dem Deck
                        if j < m - 1 and np.isfinite(ter[j + 1]):
                            gb = float(ter[j + 1])
                        for g_, e_ in ((ga, k), (gb, j)):
                            if g_ is not None and abs(float(hi[e_]) - g_) >= thr:
                                low_deck = False
                    # Deckauffahrt-Regel nur für Fahrwege/Gleise: Fußwege am Bahnhof Pieschen hielt das Bahnsteigniveau
                    # (Plattform-Raster) für "Gelände auf Deckhöhe" – sie zogen dann über ihren Knoten die Straße hoch
                    on_top = p["lc"] not in ("walk", "steps") and self._enters_on_deck(idx, k, j, hi)
                    if low_deck or on_top:
                        mode[k:j + 1] = np.where((hi[k:j + 1] - lo[k:j + 1]) < 1.5, 1, 2)
                    else:
                        mode[k:j + 1] = self._approach_modes(p, a, b, k, j, hi, lo, bridge_nodes, bridge_lv)
                    k = j + 1
                # Weg auf einem tieferen Deck, das unter einem höheren weiterläuft (gestapelt): bleibt auf dem tieferen,
                # wenn dessen Höhe nahtlos an den Nachbarpunkt auf Deck anschließt (Parkrampe unter der Löbtauer Brücke)
                for rng, step in ((range(1, m), 1), (range(m - 2, -1, -1), -1)):
                    for q in rng:
                        pq = q - step
                        if mode[q] != 3 or not np.isfinite(lo[q]) or (hi[q] - lo[q]) < 1.5 or mode[pq] not in (1, 2):
                            continue
                        lv = (float(hi[pq]), float(lo[pq])) if mode[pq] == 2 else (float(hi[pq]),)
                        if min(abs(float(lo[q]) - v) for v in lv) < 1.5:
                            mode[q] = 2
            mode[(mode == 0) & ~np.isfinite(ter) & ~np.isfinite(self.dom[idx])] = 3
            p["mode"] = mode
            p["deck"] = (mode == 1) | (mode == 2)
            p["has_deck"] = bool(has.any())
            p["wmul"] = np.ones(m)
            p["amul"] = np.ones(m)

    def _foreign_low_decks(self, p, mode, hi, lo):
        """Brückenweg über einem FREMDEN, tieferen LoD2-Teil (eigener Überbau fehlt in LoD2): das Oberflächenmodell
        liegt über dem ganzen Lauf gleichmäßig 3–12 m über diesem Deck (glatter Verlauf – kein Fachwerk, keine
        Bäume) und schließt an mindestens einem Ende an die Höhe des Wegs daneben an. Dann gilt der Lauf als Brücke
        ohne Deck (Modus 4: Oberflächenmodell). Westliche Rampe der Löbtauer Brücke lag sonst 6 m zu tief auf einem
        Teil darunter."""
        if p["kind"] != "road":
            return                 # Gleise sind zu steif geglättet, um Modus 4 (DOM) zu folgen – sie sanken eher ab
        idx, s = p["idx"], p["s"]
        dom = self.dom[idx]
        m = len(idx)
        k = 0
        while k < m:
            if mode[k] != 1:
                k += 1
                continue
            j = k
            while j + 1 < m and mode[j + 1] == 1:
                j += 1
            n = j - k + 1
            dm = dom[k:j + 1] - hi[k:j + 1]
            fin = np.isfinite(dm)
            if n >= 5 and fin.sum() >= 5 and float(np.mean((dm[fin] > 3.0) & (dm[fin] < 12.0))) > 0.8:
                sv, dv = s[k:j + 1][fin], dom[k:j + 1][fin]
                A = np.vstack([sv, np.ones_like(sv)]).T
                coef, *_ = np.linalg.lstsq(A, dv, rcond=None)
                smooth = float(np.percentile(np.abs(dv - A @ coef), 80)) < 0.6
                sup = False
                for q, e in ((k - 1, k), (j + 1, j)):
                    if not (0 <= q < m) or not np.isfinite(dom[e]):
                        continue
                    if mode[q] in (1, 2):
                        sup |= min(abs(float(hi[q]) - float(dom[e])), abs(float(lo[q]) - float(dom[e]))) < 1.5
                    elif mode[q] == 4 and np.isfinite(dom[q]):
                        sup |= abs(float(dom[q]) - float(dom[e])) < 1.0
                if smooth and sup:
                    mode[k:j + 1] = 4
                    self.log(f"  Brückenweg {p['id']}: {n} Punkte über fremdem tieferem Deck (DOM +{float(np.median(dm[fin])):.1f} m) "
                             f"-> Brücke ohne Deck")
            k = j + 1

    def _band_deck(self, p):
        """Deckhöhe je Punkt (hi, lo) und Maske ext: Straßen, deren Band ein Deck SCHRÄG erreicht (Deckkante nicht
        quer zur Straße), berühren es an einer Seite schon vor der Mitte. Dort gilt die Deckhöhe der Seite (höchste),
        sonst entstand an der äußeren Spur eine Stufe bis 0,4 m (Meißner Landstraße). Nur bis 12 m vor/nach einem
        Punkt mit Deck in der Mitte – Straßen bloß NEBEN einem Deck bleiben unberührt."""
        idx, s = p["idx"], p["s"]
        hi = self.hi[idx].astype(float)
        lo = self.lo[idx].astype(float)
        ext = np.zeros(len(idx), dtype=bool)
        cen = np.isfinite(hi)
        if p["kind"] != "road" or p["lc"] in ("walk", "steps") or p["bridge"] or p.get("under") or cen.all() \
                or len(idx) < 2:
            return hi, lo, ext
        E, N = self.E[idx], self.N[idx]
        dE, dN = np.gradient(E), np.gradient(N)
        L = np.maximum(np.hypot(dE, dN), 1e-6)
        nE, nN = -dN / L, dE / L
        off = 0.8 * float(p["hw"])
        hL, lL = self._deck_at(E + nE * off, N + nN * off)
        hR, lR = self._deck_at(E - nE * off, N - nN * off)
        side = ~cen & (np.isfinite(hL) | np.isfinite(hR))
        if not side.any():
            return hi, lo, ext
        if cen.any():
            cs = s[cen]
            near = np.array([float(np.min(np.abs(cs - sv))) <= 12.0 for sv in s])
            ext = side & near
        # niedriges Deck auf Geländehöhe, das seitlich in die Fahrbahn ragt (Brückenecke in einer Einmündung,
        # Heidemühlweg an der Radeberger Landstraße): auch ohne Deck in der Mitte auf Deckhöhe heben
        with np.errstate(invalid="ignore"):
            hs = np.fmax(hL, hR)
            ext |= side & (np.abs(hs - self.terr[idx]) < 1.0)
        with np.errstate(invalid="ignore"):
            hi[ext] = np.fmax(hL[ext], hR[ext])
            lo[ext] = np.fmin(lL[ext], lR[ext])
        return hi, lo, ext

    def _bridge_levels(self, p, out):
        """Deckhöhe eines Brückenwegs an jedem seiner Punkte: nächster Punkt mit EINEM Deck (≤ 30 m entlang des Wegs).
        Ohne LoD2-Deck: NaN (unbekannt)."""
        idx, s = p["idx"], p["s"]
        hi = p["hi"]
        single = p["mode"] == 1
        pos = np.nonzero(single)[0]
        for q in range(len(idx)):
            lv = np.nan
            if len(pos):
                nq = pos[np.argmin(np.abs(s[pos] - s[q]))]
                if abs(s[nq] - s[q]) <= 30.0:
                    lv = float(hi[nq])
            out.setdefault(int(idx[q]), []).append(lv)

    def _approach_modes(self, p, a, b, k, j, hi, lo, bridge_nodes, bridge_lv):
        """Zufahrt: Punkte des Laufs k..j, die auf DEMSELBEN Deck liegen wie ein berührter Brückenweg (Höhe passt,
        Toleranz wächst mit dem Abstand: Decks steigen), werden Deck (1 eindeutig, 2 gestapelt); übrige frei (3).
        Ein Brückenweg auf einem anderen, tieferen Bauwerk (Weißeritzbrücke der Freiberger Straße unter der
        Löbtauer Brücke) macht aus der Unterführung keine Zufahrt – sonst wurden Straße und Gleis aufs obere Deck
        gezogen und das Gelände darunter mit aufgeschüttet. Brückenweg ohne LoD2-Deck (Höhe unbekannt): kein Beleg
        für eine Zufahrt – ein Deck unter dem anschließenden Weg gehört dann zu einem anderen Bauwerk."""
        idx, s = p["idx"], p["s"]
        n = j - k + 1
        out = np.full(n, 3, dtype=np.int8)
        touch = []
        for q in range(a, b + 1):
            if bridge_nodes[idx[q]]:
                touch += [(q, lv) for lv in bridge_lv.get(int(idx[q]), [np.nan])]
        touch = [(q, lv) for q, lv in touch if np.isfinite(lv)]
        if not touch:
            return out
        for t in range(n):
            q = k + t
            on_hi = on_lo = False
            for qt, lv in touch:
                tol = 2.0 + 0.06 * abs(float(s[q] - s[qt]))
                on_hi |= abs(float(hi[q]) - lv) < tol
                on_lo |= abs(float(lo[q]) - lv) < tol
            if on_hi and (hi[q] - lo[q]) < 1.5:
                out[t] = 1
            elif on_hi or on_lo:
                out[t] = 2
        return out

    def _outside_ground(self, idx, k, j):
        """Gelände 2–6 m jenseits des Deckrands entlang der Wegrichtung an beiden Laufenden (None = keins)."""
        E, N = self.E[idx], self.N[idx]
        m = len(idx)

        def side(i0, i1):
            dx, dn = E[i0] - E[i1], N[i0] - N[i1]
            L = math.hypot(dx, dn)
            if L < 1e-3:
                return None
            dx, dn = dx / L, dn / L
            d = np.arange(1.0, 40.0)
            h, _ = self._deck_at(E[i0] + dx * d, N[i0] + dn * d)
            out = np.nonzero(~np.isfinite(h))[0]
            if not len(out):
                return None
            d0 = d[out[0]]
            g = self.mosaic.sample(E[i0] + dx * (d0 + np.array([2.0, 4.0, 6.0])),
                                   N[i0] + dn * (d0 + np.array([2.0, 4.0, 6.0])))
            g = g[np.isfinite(g)]
            return float(g.max()) if len(g) else None

        return side(k, min(k + 1, m - 1)), side(j, max(j - 1, 0))

    def _enters_on_deck(self, idx, k, j, hi):
        """Weg ohne Brückenkennzeichnung, der ÜBER ein LoD2-Deck führt: Gelände kurz vor und kurz hinter dem Deck
        (entlang der Wegrichtung) liegt auf Höhe der Deckkante (Damm/Widerlager) – darunter liegt nur eine Senke,
        ein Bach oder ein als tunnel=yes erfasster Durchlass (A4 über den Kirchenweg, Autobahnäste über einen
        Bach). Eine echte Unterführung verläuft dagegen auch vor/hinter der Brücke tief unter dem Deck."""
        if j - k < 3:
            return False
        E, N = self.E[idx], self.N[idx]

        def side(i0, i1):
            dx, dn = E[i0] - E[i1], N[i0] - N[i1]
            L = math.hypot(dx, dn)
            if L < 1e-3:
                return None
            dx, dn = dx / L, dn / L
            d = np.arange(1.0, 40.0)
            h, _ = self._deck_at(E[i0] + dx * d, N[i0] + dn * d)
            out = np.nonzero(~np.isfinite(h))[0]
            if not len(out):
                return None
            d0 = d[out[0]]
            g = self.mosaic.sample(E[i0] + dx * (d0 + np.array([2.0, 4.0, 6.0])),
                                   N[i0] + dn * (d0 + np.array([2.0, 4.0, 6.0])))
            g = g[np.isfinite(g)]
            return float(g.max()) if len(g) else None

        m = len(idx)
        ga = side(k, min(k + 1, m - 1))
        gb = side(j, max(j - 1, 0))
        return ga is not None and gb is not None and abs(ga - float(hi[k])) < 1.5 and abs(gb - float(hi[j])) < 1.5

    # --- Krümmungsterme über Wegstöße --------------------------------------
    def _joins(self):
        ends = {}
        for pi, p in enumerate(self.pieces):
            idx = p["idx"]
            for end, nb in ((0, 1), (-1, -2)):
                ends.setdefault(int(idx[end]), []).append((pi, int(idx[nb])))
        joins = []
        for node, lst in ends.items():
            if len(lst) < 2:
                continue
            dirs = []
            for pi, nb in lst:
                v = np.array([self.E[nb] - self.E[node], self.N[nb] - self.N[node]])
                dirs.append(v / (np.linalg.norm(v) + 1e-9))
            used = set()
            cand = []
            for a in range(len(lst)):
                for b in range(a + 1, len(lst)):
                    pa, pb = self.pieces[lst[a][0]], self.pieces[lst[b][0]]
                    if (pa["kind"] == "rail") != (pb["kind"] == "rail"):
                        continue
                    cos = float(dirs[a] @ dirs[b])
                    if cos < -0.8:                     # nahezu geradeaus (> ~143°)
                        cand.append((cos, a, b))
            for cos, a, b in sorted(cand):
                if a in used or b in used:
                    continue
                used.update((a, b))
                ell = min(ELL[self.pieces[lst[a][0]]["lc"]], ELL[self.pieces[lst[b][0]]["lc"]])
                joins.append((lst[a][1], node, lst[b][1], ell))
        self.joins = joins

    # --- Gleichungssystem ----------------------------------------------------
    def _assemble(self, it):
        rows, cols, vals = [], [], []
        diag = np.full(self.n, EPS)
        rhs = np.zeros(self.n)
        fallback = np.where(np.isfinite(self.terr), self.terr, np.nanmean(self.terr) if np.isfinite(self.terr).any() else 0.0)
        rhs += EPS * fallback
        y = getattr(self, "y", None)

        def add_curv(a, b, c, h1, h2, alpha):
            ca = 2.0 / (h1 * (h1 + h2))
            cb = -2.0 / (h1 * h2)
            cc = 2.0 / (h2 * (h1 + h2))
            co = np.stack([ca, cb, cc], axis=1)
            ix = np.stack([a, b, c], axis=1)
            for u in range(3):
                for v in range(3):
                    rows.append(ix[:, u])
                    cols.append(ix[:, v])
                    vals.append(alpha * co[:, u] * co[:, v])

        for p in self.pieces:
            idx, s, mode = p["idx"], p["s"], p["mode"]
            m = len(idx)
            h = np.empty(m)
            ds = np.diff(s)
            h[0], h[-1] = ds[0] / 2, ds[-1] / 2
            h[1:-1] = (ds[:-1] + ds[1:]) / 2
            ter, hi, lo = self.terr[idx], p["hi"], p["lo"]
            wdeck = W_DECK
            tgt = np.where(mode == 1, hi, ter)
            w = np.where(mode == 0, 1.0, np.where(mode == 1, wdeck, 0.0))
            if it == 0:
                # Brückenweg ohne LoD2-Deck: DOM (Fahrbahn von oben gemessen) als erste Schätzung, wenn es klar
                # über dem Gelände liegt (Talbrücken zwischen Tunneln haben sonst keinen Anker)
                b4 = (mode == 4) & np.isfinite(self.dom[idx])
                b4 &= ~np.isfinite(ter) | (self.dom[idx] > ter + 1.5)
                tgt = np.where(b4, self.dom[idx], tgt)
                w = np.where(b4, 0.3, w)
            if it >= 1 and y is not None:
                st = mode == 2
                if st.any():
                    yy = y[idx][st]
                    tgt[st] = np.where(np.abs(hi[st] - yy) <= np.abs(lo[st] - yy), hi[st], lo[st])
                    w[st] = wdeck
                g = mode == 0
                if g.any():
                    yg = y[idx][g]
                    dm = self.dom[idx][g]
                    dter = np.where(np.isfinite(ter[g]), np.abs(ter[g] - yg), np.inf)
                    use = self.dom_ok[idx][g] & (np.abs(dm - yg) < dter)
                    tgt[g] = np.where(use, dm, ter[g])
                    r = np.abs(yg - tgt[g])
                    w[g] = 1.0 / np.maximum(1.0, r / HUBER)
                fr = mode == 3
                if fr.any():
                    # Unterführung: Fahrbahn höchstens Deckunterkante − Lichtraum (max. 2,5 m unter das DGM)
                    clr = CLR_UNDER.get(str(p.get("cls", "")), 4.0)
                    lim = lo[fr] - 1.0 - clr
                    yy = y[idx][fr]
                    tf = ter[fr]
                    ok2 = np.isfinite(lim) & (yy > lim + 0.05) & (lim > np.where(np.isfinite(tf), tf, lim) - 2.5)
                    if ok2.any():
                        tg_, ww_ = tgt[fr], w[fr]
                        tg_[ok2] = lim[ok2]
                        ww_[ok2] = W_CLR
                        tgt[fr], w[fr] = tg_, ww_
                b4 = mode == 4
                if b4.any():
                    dm = self.dom[idx][b4]
                    r = np.abs(dm - y[idx][b4])
                    okd = np.isfinite(dm) & (r < 2.0)
                    tgt[b4] = np.where(okd, dm, 0.0)
                    w[b4] = np.where(okd, 0.7 / np.maximum(1.0, np.nan_to_num(r) / HUBER), 0.0)
            w = np.where(np.isfinite(tgt), w * p["wmul"], 0.0)
            tgt = np.nan_to_num(tgt)
            ok = w > 0
            np.add.at(diag, idx[ok], w[ok] * h[ok])
            np.add.at(rhs, idx[ok], w[ok] * h[ok] * tgt[ok])
            if m >= 3:
                h1, h2 = ds[:-1], ds[1:]
                ell = ELL[p["lc"]]
                alpha = ell ** 4 * (h1 + h2) / 2 * p["amul"][1:-1]
                add_curv(idx[:-2], idx[1:-1], idx[2:], h1, h2, alpha)
        if self.joins:
            j = np.array([(a, b, c) for a, b, c, _ in self.joins], dtype=np.int64)
            ell = np.array([e for *_, e in self.joins])
            h1 = np.hypot(self.E[j[:, 0]] - self.E[j[:, 1]], self.N[j[:, 0]] - self.N[j[:, 1]]) + 1e-3
            h2 = np.hypot(self.E[j[:, 2]] - self.E[j[:, 1]], self.N[j[:, 2]] - self.N[j[:, 1]]) + 1e-3
            add_curv(j[:, 0], j[:, 1], j[:, 2], h1, h2, ell ** 4 * (h1 + h2) / 2)
        rows.append(np.arange(self.n))
        cols.append(np.arange(self.n))
        vals.append(diag)
        A = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(self.n, self.n))
        return A, rhs

    def _limit_grades(self) -> int:
        """Nur vom Verfahren erzeugte Steilstellen (Gelände dort flacher) aufweiten. Gibt Anzahl zurück."""
        bad = 0
        for p in self.pieces:
            gmax = G_MAX.get(p["lc"])
            if gmax is None:
                continue
            idx, s = p["idx"], p["s"]
            ds = np.maximum(np.diff(s), 1e-3)
            g = np.abs(np.diff(self.y[idx])) / ds
            gt = np.abs(np.diff(self.terr[idx])) / ds
            gt = np.where(np.isfinite(gt), gt, 0.0)
            v = (g > gmax) & (g > gt + 0.02)
            if not v.any():
                continue
            bad += int(v.sum())
            mark = np.zeros(len(idx), dtype=bool)
            for k in np.nonzero(v)[0]:
                mark[max(k - 10, 0):k + 12] = True
            p["amul"][mark] = np.minimum(p["amul"][mark] * 3.0, 200.0)
            # Deckpunkte bleiben fest (sie sind das befahrene Mesh); nachgeben darf nur die Zufahrt
            soft = mark & ~p["deck"]
            p["wmul"][soft] = np.maximum(p["wmul"][soft] * 0.4, 0.02)
        return bad

    def _solve(self):
        self.y = None
        bad = 0
        for it in range(6):
            A, b = self._assemble(it)
            self.y = spsolve(A.tocsc(), b)
            if it >= 1:
                bad = self._limit_grades()
                if bad == 0 and it >= 2:
                    break
        self.log(f"  Straßenprofil: Restliche Steilstellen {bad}")
        self._pin_decks()

    def _pin_decks(self):
        """Fahrbahn auf jedem Deck exakt auf Deckhöhe (der weiche Löser ließ sie an Deckenden bis 0,4 m durchhängen
        -> Stufe an der Deckkante, Auto blieb hängen); die Differenz läuft auf der Zufahrt über PIN_R m aus.
        Nur bis PIN_MAX: größere Abweichungen sind Zuordnungsfehler und bleiben dem Löser überlassen."""
        adj = np.zeros(self.n)
        cnt = np.zeros(self.n)
        n_pin = 0
        for p in self.pieces:
            mode = p["mode"]
            dk = (mode == 1) | (mode == 2)
            if not dk.any():
                continue
            idx, s = p["idx"], p["s"]
            hi, lo = p["hi"], p["lo"]
            yy = self.y[idx]
            with np.errstate(invalid="ignore"):
                tgt = np.where(mode == 1, hi, np.where(np.abs(hi - yy) <= np.abs(lo - yy), hi, lo))
                delta = tgt - yy
                ok = dk & np.isfinite(delta) & (np.abs(delta) <= PIN_MAX)
            if not ok.any():
                continue
            sd, dd = s[ok], delta[ok]
            order = np.argsort(sd)
            sd, dd = sd[order], dd[order]
            pos = np.clip(np.searchsorted(sd, s), 1, len(sd) - 1) if len(sd) > 1 else np.zeros(len(s), dtype=int)
            if len(sd) > 1:
                left, right = sd[pos - 1], sd[pos]
                near = np.where(np.abs(s - left) <= np.abs(s - right), pos - 1, pos)
            else:
                near = np.zeros(len(s), dtype=int)
            dist = np.abs(s - sd[near])
            corr = dd[near] * 0.5 * (1.0 + np.cos(np.pi * np.clip(dist / PIN_R, 0.0, 1.0)))
            use = (ok | (~dk & (dist <= PIN_R)))
            corr = np.where(ok, delta, corr)
            np.add.at(adj, idx[use], corr[use])
            np.add.at(cnt, idx[use], 1.0)
            n_pin += int(ok.sum())
        m = cnt > 0
        self.y[m] += adj[m] / cnt[m]
        self.log(f"  Straßenprofil: {n_pin} Deckpunkte exakt aufs Deck gesetzt")

    # --- Ausgabe ---------------------------------------------------------
    def crossing_filter(self, segs, to_local, tol_y=2.5):
        """Entfernt Brüstungsstücke [x0,z0,x1,z1,y] (lokal), die einen Weg auf ähnlicher Höhe queren."""
        from shapely.geometry import LineString as LS
        from shapely.strtree import STRtree
        lines, ys = [], []
        for p in self.pieces:
            idx = p["idx"]
            loc = [to_local(float(e), float(n)) for e, n in zip(self.E[idx], self.N[idx])]
            lines.append(LS(loc))
            ys.append((p["s"], self.y[idx]))
        tree = STRtree(lines)
        keep = []
        for sg in segs:
            g = LS([(sg[0], sg[1]), (sg[2], sg[3])])
            hit = False
            for i in tree.query(g):
                ln = lines[int(i)]
                if not g.intersects(ln):
                    continue
                ip = g.intersection(ln)
                pts = [ip] if ip.geom_type == "Point" else list(getattr(ip, "geoms", []))
                for q in pts:
                    if q.geom_type != "Point":
                        continue
                    s_, y_ = ys[int(i)]
                    yy = float(np.interp(ln.project(q), s_, y_))
                    if abs(yy - sg[4]) < tol_y:
                        hit = True
                        break
                if hit:
                    break
            if not hit:
                keep.append(sg)
        return keep

    def way_pieces(self, way_id, kind="road", tol=0.025):
        """Stücke eines Weges (Fenster-geclippt) als dict(E, N, y, deck, has_deck, deck_frac).
        Ausgedünnt: OSM-Knoten und Deck-Wechsel bleiben, Zwischenpunkte nur wo die lineare Interpolation der
        Höhe sonst mehr als tol abweicht."""
        out = []
        for p in self._by_id().get((kind, way_id), []):
            idx, s = p["idx"], p["s"]
            y = self.y[idx]
            keep = p["vtx"].copy()
            keep[0] = keep[-1] = True
            dk = p["deck"]
            keep[1:] |= dk[1:] != dk[:-1]
            keep[:-1] |= dk[1:] != dk[:-1]
            ks = np.nonzero(keep)[0]
            extra = []
            for a, b in zip(ks[:-1], ks[1:]):
                stack = [(a, b)]
                while stack:
                    u, v = stack.pop()
                    if v - u < 2:
                        continue
                    t = (s[u + 1:v] - s[u]) / max(s[v] - s[u], 1e-6)
                    err = np.abs(y[u + 1:v] - (y[u] + t * (y[v] - y[u])))
                    k = int(np.argmax(err))
                    if err[k] > tol:
                        mid = u + 1 + k
                        extra.append(mid)
                        stack += [(u, mid), (mid, v)]
            keep[extra] = True
            sel = np.nonzero(keep)[0]
            out.append({"E": self.E[idx][sel], "N": self.N[idx][sel], "y": y[sel], "deck": dk[sel],
                        "has_deck": p["has_deck"], "deck_frac": float(dk.mean())})
        return out

    def _by_id(self):
        if not hasattr(self, "_idmap"):
            self._idmap = {}
            for p in self.pieces:
                self._idmap.setdefault((p["kind"], p["id"]), []).append(p)
        return self._idmap

    # --- Gelände anpassen --------------------------------------------------
    def conform(self, terrain, min_e: float, max_n: float, protect=None, deck_lo_tile=None) -> int:
        """Setzt terrain (H×W, 1 m, Zeile 0 = Nordrand bei max_n) entlang der Wege auf das Profil.
        protect: bool-Maske (Gebäude), dort keine Änderung. Gibt Anzahl geänderter Pixel zurück."""
        H, W = terrain.shape
        orig = terrain.copy()
        num = np.zeros_like(terrain, dtype=np.float64)
        den = np.zeros_like(terrain, dtype=np.float64)
        cov_max = np.zeros_like(terrain, dtype=np.float32)
        S0, SMAX = 2.0, 14.0
        for p in self.pieces:
            if p["lc"] == "steps":
                continue
            idx = p["idx"]
            m = len(idx)
            mode = p["mode"]
            conf = ~p["deck"] | p["ext"]       # schräge Deckenden: Gelände unter dem Rest des Bandes anheben
            if p["bridge"]:
                # Brückenweg: nur die Enden ohne Deck (Zufahrt/Widerlager), und nur wenn es ein Deck gibt
                conf = np.zeros(m, dtype=bool)
                if p["has_deck"]:
                    nd = ~p["deck"]
                    k = 0
                    while k < m and nd[k]:
                        conf[k] = True
                        k += 1
                    k = m - 1
                    while k >= 0 and nd[k]:
                        conf[k] = True
                        k -= 1
                    # nur Widerlager/Rampe (≤ 2,5 m über dem Gelände): ein Brückenende ohne LoD2-Deck hoch in der Luft
                    # wurde sonst zum Damm – unter der A4 stand so eine 14 m hohe Wand quer über dem Zubringer
                    with np.errstate(invalid="ignore"):
                        conf &= np.abs(self.y[idx] - self.terr[idx]) <= 2.5
            hw = float(p["hw"]) + (0.3 if p["kind"] == "road" else 0.6)
            wgt_kind = 0.35 if p["lc"] == "tram" else 1.0
            if p["bridge"]:
                wgt_kind = 50.0      # Vorfeld vor dem Deck: Gelände schließt bündig an die Deckkante an
            ex = self.E[idx] - min_e
            ny = max_n - self.N[idx]
            yy = self.y[idx]
            CH = 6
            k = 0
            while k < m - 1:
                j = min(k + CH, m - 1)
                segs = [q for q in range(k, j) if conf[q] and conf[q + 1]]
                if segs:
                    xs = np.concatenate([ex[k:j + 1]])
                    ys = np.concatenate([ny[k:j + 1]])
                    pad = hw + SMAX + 1
                    c0 = int(max(math.floor(xs.min() - pad), 0))
                    c1 = int(min(math.ceil(xs.max() + pad), W - 1))
                    r0 = int(max(math.floor(ys.min() - pad), 0))
                    r1 = int(min(math.ceil(ys.max() + pad), H - 1))
                    if c1 > c0 and r1 > r0:
                        gx, gy = np.meshgrid(np.arange(c0, c1 + 1) + 0.5, np.arange(r0, r1 + 1) + 0.5)
                        best_d = np.full(gx.shape, np.inf)
                        best_y = np.zeros(gx.shape)
                        for q in segs:
                            ax, ay, bx, by = ex[q], ny[q], ex[q + 1], ny[q + 1]
                            dx, dy = bx - ax, by - ay
                            l2 = dx * dx + dy * dy
                            if l2 < 1e-8:
                                continue
                            t = np.clip(((gx - ax) * dx + (gy - ay) * dy) / l2, 0.0, 1.0)
                            d = np.hypot(gx - (ax + t * dx), gy - (ay + t * dy))
                            better = d < best_d
                            best_d = np.where(better, d, best_d)
                            best_y = np.where(better, yy[q] + t * (yy[q + 1] - yy[q]), best_y)
                        sub_o = orig[r0:r1 + 1, c0:c1 + 1]
                        S = np.clip(S0 + 1.5 * np.abs(best_y - sub_o), S0, SMAX)
                        cov = 1.0 - _smoothstep(hw, hw + S, best_d)
                        cov = np.where(np.isfinite(best_d), cov, 0.0)
                        # Vorrang der eigenen Fahrbahn: im Kern (d <= hw) 10-fach, sonst nach normierter Distanz;
                        # so hebt die Böschung eines Nachbarwegs nicht den Rand einer Hauptstraße an.
                        dn = best_d / hw
                        wb = wgt_kind * cov ** 4 * np.where(best_d <= hw, 10.0, 1.0) / (0.02 + dn * dn) ** 3
                        num[r0:r1 + 1, c0:c1 + 1] += wb * best_y
                        den[r0:r1 + 1, c0:c1 + 1] += wb
                        sc = cov_max[r0:r1 + 1, c0:c1 + 1]
                        np.maximum(sc, cov.astype(np.float32), out=sc)
                k = j
        ok = (den > 1e-9) & (cov_max > 0.0)
        if protect is not None:
            ok &= ~protect
        target = np.where(ok, num / np.maximum(den, 1e-12), orig)
        out = orig + cov_max * (target - orig)
        terrain[ok] = out[ok]
        # Brückenwege: Gelände im Fahrbahnband nie über der Fahrbahn (nur absenken, Böschung 1:1,5) –
        # Helfenberger Grund: OSM-Weg neben dem kleinen LoD2-Deck, auf Deckhöhe gezogen, Waldboden stand 0,5–0,9 m in
        # der Fahrbahn; die abgesenkte Fläche bekommt danach ein Füllstück (bridge_decks.fill_decks)
        n_cut = 0
        for p in self.pieces:
            if not p["bridge"] or p["kind"] != "road":
                continue
            idx = p["idx"]
            m = len(idx)
            # alle Punkte des Brückenwegs (auch ohne Deck, Modus 4: dort trägt die OSM-Brückenplatte die Fahrbahn –
            # Helfenberger Grund: OSM-Brücke 10 m neben dem LoD2-Deck, Profil zum Deck hin abgesenkt)
            # nur knapp durchstoßendes Gelände (≤ 2,5 m): höher liegt ein Hang/Portal (A17 Coschütz: sonst 20 m tiefer
            # Einschnitt vor dem Tunnelportal) – das regeln Anschluss und tunnels.py
            with np.errstate(invalid="ignore"):
                above = (self.terr[idx] > self.y[idx] + 0.1) & (self.terr[idx] < self.y[idx] + 2.5)
            if not above.any():
                continue
            hw = float(p["hw"]) + 0.3
            ex = self.E[idx] - min_e
            ny = max_n - self.N[idx]
            yy = self.y[idx]
            for q in range(m - 1):
                if not (above[q] or above[q + 1]):
                    continue
                ax, ay, bx, by = ex[q], ny[q], ex[q + 1], ny[q + 1]
                pad = hw + 4.0
                c0 = int(max(math.floor(min(ax, bx) - pad), 0))
                c1 = int(min(math.ceil(max(ax, bx) + pad), W - 1))
                r0 = int(max(math.floor(min(ay, by) - pad), 0))
                r1 = int(min(math.ceil(max(ay, by) + pad), H - 1))
                if c1 <= c0 or r1 <= r0:
                    continue
                gx, gy = np.meshgrid(np.arange(c0, c1 + 1) + 0.5, np.arange(r0, r1 + 1) + 0.5)
                dx, dy = bx - ax, by - ay
                l2 = dx * dx + dy * dy
                if l2 < 1e-8:
                    continue
                t = np.clip(((gx - ax) * dx + (gy - ay) * dy) / l2, 0.0, 1.0)
                d = np.hypot(gx - (ax + t * dx), gy - (ay + t * dy))
                tgt = yy[q] + t * (yy[q + 1] - yy[q]) - 0.2 + np.maximum(d - hw, 0.0) / 1.5
                sub = terrain[r0:r1 + 1, c0:c1 + 1]
                cut = (d <= pad) & (sub > tgt) & (sub < tgt + 2.7)      # je Pixel höchstens ~2,7 m absenken
                if protect is not None:
                    cut &= ~protect[r0:r1 + 1, c0:c1 + 1]
                sub[cut] = tgt[cut]
                n_cut += int(cut.sum())
        if n_cut:
            print(f"  Gelände unter {n_cut} Pixeln von Brückenfahrbahnen abgesenkt", flush=True)
        if deck_lo_tile is not None:
            # Gelände darf nirgends durch ein Deck stoßen; nur knapp unter die Oberkante (nicht 1 m), sonst
            # entsteht an Brückenenden durch die Pixel-Interpolation eine Mulde mit sichtbarer Deckstirn.
            under = np.isfinite(deck_lo_tile) & (terrain > deck_lo_tile - 0.12)
            terrain[under] = deck_lo_tile[under] - 0.12
        return int(ok.sum())
