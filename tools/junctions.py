"""Kreuzungen für die Verkehrs-KI: Zufahrten, Vorrang, Haltelinien, Ampelsteuerungen und Ampelmasten.

Ausgabe in den Graphen (build_city.build_graph):
  node["app"] = [[e, d, ang, pri, sign, ph, stop_d, ctl], ...]   je befahrbarer Zufahrt
      e      Kantenindex (lokal), d = Fahrtrichtung auf der Kante zum Knoten hin (1: a->b, -1: b->a)
      ang    Fahrtrichtung beim Einfahren (atan2(dz, dx), lokal)
      pri    2 = Vorfahrt (Vorfahrtstraße/Hauptstraße/Kreisverkehr), 1 = wartepflichtig, 0 = gleichrangig
      sign   0 keins, 1 Vorfahrt gewähren, 2 Stopp
      ph     Ampelphase (>= 0), -1 ohne Ampel, -2 innerhalb einer Ampelgruppe (nicht erneut halten)
      stop_d Abstand der Haltelinie vom Knoten (m, entlang der Kante)
      ctl    Index in graph["ctls"] oder -1
  node["rbl"] = 1, wenn unter gleichrangigen Zufahrten rechts vor links gilt
  node["jr"]  Kreuzungsradius (m)
  graph["ctls"] = [[off, g0, g1, ...], ...]  Ampelumlauf: je Phase Grünzeit g, danach 3 s Gelb + 2 s Alles-Rot
Signalgeber: heads = [[x, z, y, yaw, ph, ctl], ...] (Mast rechts der Zufahrt an der Haltelinie, Vorderseite = −Z
zeigt dem Verkehr entgegen, Ausleger entlang +X über die Fahrbahn).
"""
import math
from collections import defaultdict

RANK = {"motorway": 8, "trunk": 7, "primary": 6, "secondary": 5, "tertiary": 4, "motorway_link": 5, "trunk_link": 5,
        "primary_link": 4, "secondary_link": 4, "tertiary_link": 3, "unclassified": 3, "residential": 2, "road": 2,
        "living_street": 1, "service": 0, "busway": 3}
YELLOW, ALLRED = 3.0, 2.0


def _h(*vals):
    x = 0
    for v in vals:
        x = (x * 1000003) ^ (int(v * 1000) & 0xFFFFFFFF)
        x &= 0xFFFFFFFFFFFF
    x ^= x >> 17
    x = (x * 0x9E3779B1) & 0xFFFFFFFF
    x ^= x >> 15
    return (x & 0xFFFFFF) / float(0xFFFFFF)


def _pt_along(pts, s):
    """Punkt in Abstand s vom Anfang einer Polylinie [[x, z, ...], ...] und Richtung dort."""
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        l = math.hypot(b[0] - a[0], b[1] - a[1])
        if acc + l >= s and l > 1e-6:
            t = (s - acc) / l
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), ((b[0] - a[0]) / l, (b[1] - a[1]) / l)
        acc += l
    a, b = pts[-2], pts[-1]
    l = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return (b[0], b[1]), ((b[0] - a[0]) / l, (b[1] - a[1]) / l)


def _seg_dist(px, pz, pts, max_s=60.0):
    """(Abstand zur Polylinie, Bogenlänge des Lotpunkts) – nur die ersten max_s Meter."""
    best = (1e9, 0.0)
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        dx, dz = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dz * dz
        L = math.sqrt(L2)
        if L < 1e-6:
            continue
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (pz - a[1]) * dz) / L2))
        d = math.hypot(px - a[0] - dx * t, pz - a[1] - dz * t)
        if d < best[0]:
            best = (d, acc + L * t)
        acc += L
        if acc > max_s:
            break
    return best


def analyse(graph, edges_meta, signals, sign_nodes, curb=None, gy=None, log=print):
    """graph: {"nodes": [{"id", "pos": [x, y, z]}], "edges": [{"a", "b", "pts", "width", "cls", "oneway", ...}]}
    signals: [[x, z]], sign_nodes: [(x, z, 1|2)]; curb: curb.Curb (Masten vom Fahrbahnrand fernhalten)."""
    nodes = graph["nodes"]
    edges = graph["edges"]
    inc = defaultdict(list)          # node -> [(edge idx, d (zum Knoten), Punkte vom Knoten weg)]
    for ei, e in enumerate(edges):
        pts = e["pts"]
        if len(pts) < 2:
            continue
        inc[e["b"]].append((ei, 1, pts[::-1]))
        inc[e["a"]].append((ei, -1, pts))
    pos = {n["id"]: (n["pos"][0], n["pos"][2]) for n in nodes}
    sig_nodes = {n["id"] for n in nodes if n.get("signal")}

    # --- Ampelgruppen: Ampelknoten, die über kurze Kanten (< 40 m) zusammenhängen ----------------------------
    parent = {}

    def find(a):
        while parent.get(a, a) != a:
            parent[a] = parent.get(parent[a], parent[a])
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for nid in sig_nodes:
        parent.setdefault(nid, nid)
    # Ampel vor einer Kreuzung: nur die nächste Kreuzung (>= 3 Kanten, < 45 m) gehört zur Gruppe,
    # benachbarte Ampelknoten (< 45 m) ebenfalls
    for nid in list(sig_nodes):
        if len(inc[nid]) >= 3:
            continue
        best = None
        for ei, d, away in inc[nid]:
            e = edges[ei]
            if float(e["len"]) > 45.0:
                continue
            other = e["a"] if e["b"] == nid else e["b"]
            if other in sig_nodes:
                parent.setdefault(other, other)
                union(nid, other)
            elif len(inc[other]) >= 3 and (best is None or float(e["len"]) < best[0]):
                best = (float(e["len"]), other)
        if best is not None:
            parent.setdefault(best[1], best[1])
            union(nid, best[1])
    groups = defaultdict(set)
    for nid in parent:
        groups[find(nid)].add(nid)

    ctls = []
    node_ctl = {}
    node_phase_ref = {}
    for root, members in groups.items():
        if not members & sig_nodes:
            continue
        # Zufahrten von außen in die Gruppe
        apps = []
        for nid in members:
            for ei, d, away in inc[nid]:
                e = edges[ei]
                other = e["a"] if e["b"] == nid else e["b"]
                if other in members:
                    continue
                ow = int(e["oneway"])
                if (d == 1 and ow < 0) or (d == -1 and ow > 0):
                    continue
                apps.append((nid, ei, d, away))
        if not apps:
            continue
        # Phase je Achse: Bezugsachse = ranghöchste Zufahrt
        def app_ang(a):
            nid, ei, d, away = a
            q, t = _pt_along(away, min(10.0, float(edges[ei]["len"]) * 0.9))
            return math.atan2(pos[nid][1] - q[1], pos[nid][0] - q[0])
        best = max(apps, key=lambda a: RANK.get(edges[a[1]]["cls"], 2))
        ref = app_ang(best)
        phases = {}
        for a in apps:
            ph = 0 if abs(math.cos(app_ang(a) - ref)) >= 0.6 else 1
            phases[(a[1], a[2])] = ph
        nph = len(set(phases.values()))
        rank0 = max(RANK.get(edges[a[1]]["cls"], 2) for a in apps if phases[(a[1], a[2])] == 0)
        cx = sum(pos[n][0] for n in members) / len(members)
        cz = sum(pos[n][1] for n in members) / len(members)
        if nph == 1:
            g = [26.0 if rank0 >= 4 else 20.0, 9.0]         # zweite Phase: Fußgänger
        else:
            g = [24.0 if rank0 >= 4 else 18.0, 15.0]
        cycle = sum(x + YELLOW + ALLRED for x in g)
        ci = len(ctls)
        ctls.append([round(_h(cx, cz) * cycle, 1)] + g)
        for nid in members:
            node_ctl[nid] = ci
        node_phase_ref[ci] = phases

    # --- Zufahrten je Knoten -----------------------------------------------------------------------------
    heads = []
    n_junc = n_rbl = 0
    for n in nodes:
        nid = n["id"]
        lst = inc[nid]
        ci = node_ctl.get(nid, -1)
        sign_here = [(sx, sz, k) for sx, sz, k in sign_nodes if math.hypot(sx - pos[nid][0], sz - pos[nid][1]) < 40.0]
        if len(lst) < 3 and ci < 0 and not sign_here:
            continue
        widths = [float(edges[ei]["width"]) for ei, _, _ in lst]
        jr = max(widths) * 0.5 + 2.0
        apps = []
        for k, (ei, d, away) in enumerate(lst):
            e = edges[ei]
            ow = int(e["oneway"])
            if (d == 1 and ow < 0) or (d == -1 and ow > 0):
                continue           # Einbahnstraße vom Knoten weg
            q, t = _pt_along(away, min(8.0, float(e["len"]) * 0.9))
            ang = math.atan2(pos[nid][1] - q[1], pos[nid][0] - q[0])
            # Haltelinie: so weit zurück, dass ein wartendes Fahrzeug die querende Fahrbahn (auch bei schrägem
            # Winkel) nicht berührt; gleich gerichtete Fortsetzungen zählen nicht
            stop_d = 2.0
            for j, (ej, dj, away_j) in enumerate(lst):
                if j == k:
                    continue
                qj, _t = _pt_along(away_j, min(8.0, float(edges[ej]["len"]) * 0.9))
                ang_j = math.atan2(qj[1] - pos[nid][1], qj[0] - pos[nid][0])
                sn = abs(math.sin(ang_j - ang))
                if sn < 0.3:
                    continue
                stop_d = max(stop_d, (widths[j] * 0.5 + 1.2) / max(sn, 0.45) + float(e["width"]) * 0.5 * min(abs(math.cos(ang_j - ang)) / max(sn, 0.45), 1.5) * 0.5)
            stop_d = min(stop_d, 18.0, float(e["len"]) * 0.8)
            sign = 0
            for sx, sz, kind in sign_here:
                dd, s = _seg_dist(sx, sz, away, 30.0)
                if dd < 4.0:
                    sign = max(sign, kind)
            ph = -1
            if ci >= 0:
                other = e["a"] if e["b"] == nid else e["b"]
                if node_ctl.get(other, -2) == ci:
                    ph = -2                   # Kante innerhalb der Ampelgruppe
                else:
                    ph = node_phase_ref[ci].get((ei, d), 0)
                    if len(lst) <= 2:
                        stop_d = 1.5          # Ampel vor der Kreuzung / Fußgängerampel: Haltelinie am Mast
            apps.append([ei, d, round(ang, 3), 0, sign, ph, round(stop_d, 1), ci])
        if not apps:
            continue
        # Vorrang
        rk = [RANK.get(edges[a[0]]["cls"], 2) for a in apps]
        prio = [bool(edges[a[0]].get("prio")) for a in apps]
        rb = [bool(edges[a[0]].get("rb")) for a in apps]
        maxr = max(rk)
        for i, a in enumerate(apps):
            if any(rb):
                a[3] = 2 if rb[i] else 1
            elif any(prio):
                a[3] = 2 if prio[i] else 1
            elif maxr >= 4 and min(rk) < maxr:
                a[3] = 2 if rk[i] == maxr else 1
            else:
                a[3] = 1 if rk[i] <= 1 and maxr >= 2 else 0     # Ausfahrten/verkehrsberuhigt: warten
            if a[4] > 0:
                a[3] = 1
        n["app"] = apps
        n["jr"] = round(jr, 1)
        if sum(1 for a in apps if a[3] == 0) >= 2 and ci < 0:
            n["rbl"] = 1
            n_rbl += 1
        n_junc += 1
        # Signalgeber je Zufahrt mit Ampelphase
        for a in apps:
            ei, d, ang, pri, sign, ph, stop_d, c = a
            if ph < 0:
                continue
            e = edges[ei]
            away = e["pts"][::-1] if d == 1 else e["pts"]
            q, t = _pt_along(away, stop_d)
            tx, tz = -t[0], -t[1]                     # Fahrtrichtung zum Knoten
            rx, rz = -tz, tx                          # rechts davon
            w = float(e["width"])
            two_way = int(e["oneway"]) == 0
            u = w * 0.5 + 0.7
            px, pz = q[0] + rx * u, q[1] + rz * u
            if curb is not None:
                pp = curb.push(px, pz, 0.6, max_move=6.0)
                if pp is None:
                    continue
                px, pz = pp
            yaw = math.atan2(tx, tz)
            py = gy(px, pz) if gy else 0.0
            heads.append([round(px, 2), round(pz, 2), round(py, 2), round(yaw, 3), ph, c])
    graph["ctls"] = ctls
    log(f"  Kreuzungen: {n_junc} mit Vorrangregeln ({n_rbl} rechts vor links), {len(ctls)} Ampelsteuerungen, "
        f"{len(heads)} Signalgeber")
    return heads
