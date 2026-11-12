"""Brückenhöhen: linear von Ufer zu Ufer über zusammenhängende Brückenwege."""
import numpy as np


def bridge_chain_heights(ways, ground):
    """Brückenhöhen entlang zusammenhängender Brückenwege: linear zwischen den Höhen der beiden Enden der Kette.

    ways: {id: ndarray (n,2) UTM}. Gibt {id: [y,...]} zurück (relativ zu base_height)."""
    def key(p):
        return (round(p[0] / 1.0), round(p[1] / 1.0))
    ends = {}
    for wid, c in ways.items():
        for e in (0, -1):
            ends.setdefault(key(c[e]), []).append((wid, e))
    parent = {w: w for w in ways}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for lst in ends.values():
        for w, _ in lst[1:]:
            parent[find(w)] = find(lst[0][0])
    comps = {}
    for w in ways:
        comps.setdefault(find(w), []).append(w)
    out = {}
    for comp in comps.values():
        # Enden der Kette = Schlüssel mit nur einem Weg aus dieser Komponente
        cnt = {}
        for w in comp:
            for e in (0, -1):
                cnt.setdefault(key(ways[w][e]), []).append((w, e))
        free = [k for k, v in cnt.items() if len(v) == 1]
        if len(free) != 2:
            for w in comp:
                c = ways[w]
                gl = [ground(x, y) for x, y in c]
                d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(c, axis=0).T))])
                out[w] = [gl[0] + (gl[-1] - gl[0]) * (s / d[-1]) if d[-1] > 0 else gl[0] for s in d]
            continue
        # Reihenfolge der Wege vom ersten freien Ende aus
        order = []
        cur_key = free[0]
        used = set()
        while True:
            nxt = [(w, e) for (w, e) in cnt.get(cur_key, []) if w not in used]
            if not nxt:
                break
            w, e = nxt[0]
            used.add(w)
            c = ways[w] if e == 0 else ways[w][::-1]
            order.append((w, e == 0))
            cur_key = key(c[-1])
        if len(used) != len(comp):
            for w in comp:
                c = ways[w]
                gl = [ground(x, y) for x, y in c]
                d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(c, axis=0).T))])
                out[w] = [gl[0] + (gl[-1] - gl[0]) * (s / d[-1]) if d[-1] > 0 else gl[0] for s in d]
            continue
        pts_all = []
        for w, fwd in order:
            c = ways[w] if fwd else ways[w][::-1]
            pts_all.append(c)
        total = sum(float(np.hypot(*np.diff(c, axis=0).T).sum()) for c in pts_all)
        first, last = pts_all[0][0], pts_all[-1][-1]
        y0, y1 = ground(first[0], first[1]), ground(last[0], last[1])
        acc = 0.0
        for (w, fwd), c in zip(order, pts_all):
            d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(c, axis=0).T))])
            ys = [y0 + (y1 - y0) * ((acc + s) / max(total, 1e-6)) for s in d]
            acc += float(d[-1])
            out[w] = ys if fwd else ys[::-1]
    return out
