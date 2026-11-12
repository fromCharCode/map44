class_name Departures
extends RefCounted
## Abfahrten für Haltestellenanzeiger (DFI): je Haltestelle die nächsten Fahrten aller Linien mit Ziel und Minuten.
## Grundlage sind die echten Linienwege mit Haltestellen (godot/data/tram_routes.json, bus_routes.json, OSM).
## Takt nach Tageszeit wie bei der DVB (Straßenbahn tagsüber 10 min, abends 15, spät 30; Stadtbus 10–20,
## Regionalbus 30–60), Lage im Takt je Linie fest. Fährt eine echte Bahn der Linie auf die Haltestelle zu, zeigt die
## Tafel deren Ankunft (Restweg / Reisegeschwindigkeit) – Anzeige und Straßenbahnen passen dann zusammen.

const V_TRAM := 5.3          # m/s Reisegeschwindigkeit inkl. Halte (≈ 19 km/h)
const V_BUS := 4.9

static var trams: Trams
static var traffic: Traffic
static var hours := 12.0     # Spielzeit (main.gd setzt sie laufend)
static var _idx := {}        # Haltestellenname -> [[art, route, s, Vector2]]
static var _built := false


static func _index() -> void:
	if _built or trams == null or traffic == null or trams.routes.is_empty():
		return                                   # erst wenn Bahnen und Busse samt Linien geladen sind
	_built = true
	if trams:
		for ri in trams.routes.size():
			for st in trams.routes[ri].get("stops", []):
				_add(String(st[3]), ["tram", ri, float(st[0]), Vector2(float(st[1]), float(st[2]))])
	if traffic:
		for ri in traffic.bus_routes.size():
			for st in traffic.bus_routes[ri].get("stops", []):
				if st.size() >= 4:
					_add(String(st[3]), ["bus", ri, float(st[0]), Vector2(float(st[1]), float(st[2]))])


static func _add(name: String, e: Array) -> void:
	var k := name.strip_edges().to_lower()
	if k == "":
		return
	if not _idx.has(k):
		_idx[k] = []
	_idx[k].append(e)


static func headway(kind: String, ref: String, h: float) -> float:
	var hh := fposmod(h, 24.0)
	if kind == "tram":
		if hh >= 6.0 and hh < 19.0:
			return 10.0
		if (hh >= 5.0 and hh < 6.0) or (hh >= 19.0 and hh < 22.0):
			return 15.0
		if hh >= 22.0 or hh < 1.0:
			return 30.0
		return 60.0
	var n := ref.to_int()
	var city := n > 0 and n < 100 and ref.is_valid_int()
	if hh >= 6.0 and hh < 19.0:
		return (10.0 if n <= 66 else 20.0) if city else 30.0
	if hh >= 19.0 or hh < 1.0:
		return 30.0 if city else 60.0
	return 60.0


static func _route(kind: String, ri: int) -> Dictionary:
	return trams.routes[ri] if kind == "tram" else traffic.bus_routes[ri]


## Nächste Abfahrten an der Haltestelle name bei pos in Fahrtrichtung dir (Vector2.ZERO = beide), nur Linien in lines:
## [[linie, ziel, min]]. Linienvarianten (z. B. 4 nach Weinböhla/Radebeul West/Radebeul Ost) teilen sich einen Takt
## und wechseln das Ziel.
static func board(name: String, pos: Vector2, lines: PackedStringArray, max_rows := 4, dir := Vector2.ZERO) -> Array:
	_index()
	var now := hours * 60.0
	var groups := {}          # ref -> [[art, route, s_stop, ziel], …]
	for e in _idx.get(name.strip_edges().to_lower(), []):
		var kind: String = e[0]
		var ri: int = e[1]
		var s_stop: float = e[2]
		if (e[3] as Vector2).distance_to(pos) > 90.0:
			continue
		var r := _route(kind, ri)
		var ref := String(r.get("ref", ""))
		if not lines.is_empty() and not lines.has(ref):
			continue
		var cum: PackedFloat32Array = r["cum"]
		if s_stop > cum[cum.size() - 1] - 30.0:
			continue                                 # Endhaltestelle dieser Richtung: keine Abfahrt
		if dir != Vector2.ZERO:
			var pts: PackedVector2Array = r["pts"]
			var t := _tangent(pts, cum, s_stop)
			if t.dot(dir) < 0.3:
				continue                             # Gegenrichtung
		if not groups.has(ref):
			groups[ref] = []
		groups[ref].append([kind, ri, s_stop, LedSign.clean_dest(String(r.get("to", "")))])
	var rows: Array = []
	for ref in groups:
		var vs: Array = groups[ref]
		vs.sort_custom(func(a, b): return String(a[3]) < String(b[3]))
		var kind: String = vs[0][0]
		var s_stop: float = vs[0][2]
		var v := V_TRAM if kind == "tram" else V_BUS
		var hw := headway(kind, String(ref), hours)
		var phase := float(posmod(hash(String(ref) + kind), 9973)) / 9973.0 * hw
		var m0 := fposmod(phase + s_stop / v / 60.0 - now, hw)
		var dep: Array = []
		for k in 3:
			var t := m0 + hw * k
			var slot := int(floor((now + t) / hw))
			dep.append([t, String(vs[posmod(slot, vs.size())][3])])
		# echte Bahnen dieser Linie auf dem Weg hierher
		if kind == "tram" and trams:
			for vv in vs:
				for u in trams.trams:
					var tu := u as TramUnit
					if tu.dead or tu.route != int(vv[1]) or tu.route_s > float(vv[2]) + 5.0 or float(vv[2]) - tu.route_s > 3500.0:
						continue
					var eta := maxf(float(vv[2]) - tu.route_s - 20.0, 0.0) / v / 60.0
					dep = dep.filter(func(d): return absf(float(d[0]) - eta) > 3.0)
					dep.append([eta, String(vv[3])])
		for d in dep:
			rows.append([String(ref), String(d[1]), float(d[0])])
	rows.sort_custom(func(a, b): return float(a[2]) < float(b[2]))
	return rows.slice(0, max_rows)


static func _tangent(pts: PackedVector2Array, cum: PackedFloat32Array, s: float) -> Vector2:
	var i := 0
	while i < cum.size() - 2 and cum[i + 1] < s:
		i += 1
	return (pts[i + 1] - pts[i]).normalized()


static func fmt_min(m: float) -> String:
	if m < 0.75:
		return "sofort"
	return "%d min" % int(round(m))
