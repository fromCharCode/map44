class_name Roads
extends Node3D
## Fahrbahnmarkierungen, Zebrastreifen, Brücken und Gleise.

const CELL := 250.0

var terrain: Terrain
var city: Dictionary
var index: RoadIndex
var mark_mat: StandardMaterial3D
var rail_mat: StandardMaterial3D
var deck_mat: StandardMaterial3D
var stone_mat: StandardMaterial3D
var concrete_mat: StandardMaterial3D
var concrete_dark_mat: StandardMaterial3D
var junctions: Dictionary = {}
var _gen_piers := true
var _slab_rails: Array = []      # Geländer der OSM-Plattenbrücken (gleiche Darstellung wie bridge_rails)

# Sammler je Zelle
var _mk: Dictionary = {}
var _rl: Dictionary = {}


func build(t: Terrain, c: Dictionary, idx: RoadIndex) -> void:
	terrain = t
	city = c
	index = idx
	_materials()
	_find_junctions()
	_tunnel_segs()
	for r in city["roads"]:
		_markings(r)
	_crossings()
	for rl in city["rails"]:
		_rail(rl)
	_flush(_mk, mark_mat, 230.0)
	if not _gr.is_empty():
		var gm := StandardMaterial3D.new()
		gm.albedo_color = Color(0.62, 0.64, 0.66)
		gm.metallic = 0.75
		gm.roughness = 0.42
		gm.cull_mode = BaseMaterial3D.CULL_DISABLED
		_flush3d(_gr, gm, 420.0, true)
	if not _gp.is_empty():
		var pm := StandardMaterial3D.new()
		pm.albedo_color = Color(0.93, 0.93, 0.91)
		pm.roughness = 0.6
		_flush3d(_gp, pm, 260.0, false)
	_flush(_rl, rail_mat, 260.0)
	for b in city["bridges"]:
		_bridge(b)
	var arches: Dictionary = city.get("bridge_arches", {})
	var stone_parts := {}
	for pid in arches.get("lod2", []):
		stone_parts[String(pid)] = true
	for bm in city.get("bridge_meshes", []):
		_lod2_bridge(bm, stone_parts.has(String(bm.get("id", ""))))
	var slab_ids := {}
	for b in city["bridges"]:
		slab_ids[int(b["id"])] = true
	for wid in arches.get("ways", []):
		slab_ids[int(wid)] = true                  # recherchierte Brücken: Pfeiler kommen aus bridge_arches/Modell
	# Standardpfeiler: aus der Pipeline (bridge_arches.py "gpiers", nie auf Straßen/Gleisen darunter); alte Daten: hier
	_gen_piers = not arches.has("gpiers")
	for r in city["roads"]:
		if _gen_piers and r["bridge"] and not slab_ids.has(int(r["id"])):    # JSON-Zahlen sind float -> int vergleichen
			_piers(r["pts"], float(r["width"]) + 2.0, 1.0, "road:%d" % int(r["id"]))
	_bridge_rails(city.get("bridge_rails", []) + _slab_rails)
	_curbs(city.get("curbs", []))
	_bridge_arches(city.get("bridge_arches", {}))


func _materials() -> void:
	mark_mat = StandardMaterial3D.new()
	mark_mat.albedo_color = Color(0.9, 0.9, 0.87)
	mark_mat.roughness = 0.5
	mark_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	mark_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	rail_mat = StandardMaterial3D.new()
	rail_mat.albedo_color = Color(0.42, 0.42, 0.44)
	rail_mat.metallic = 0.85
	rail_mat.roughness = 0.35
	deck_mat = _tri_mat("asphalt_new", 4.0, 1.4)
	stone_mat = _tri_mat("sandstone", 2.0, 1.0)
	concrete_mat = _tri_mat("concrete", 2.0, 1.1)
	concrete_dark_mat = _tri_mat("concrete", 2.0, 0.6)


func _tri_mat(name: String, _tile: float, boost: float) -> StandardMaterial3D:
	return TexLib.tri_material(name, boost)     # gemeinsam für alle Kacheln (komprimiert, einmal geladen)


func _find_junctions() -> void:
	var cnt := {}
	for e in city["graph"]["edges"]:
		cnt[e["a"]] = cnt.get(e["a"], 0) + 1
		cnt[e["b"]] = cnt.get(e["b"], 0) + 1
	for n in city["graph"]["nodes"]:
		if cnt.get(n["id"], 0) >= 3:
			junctions[n["id"]] = Vector2(n["pos"][0], n["pos"][2])


var _jgrid := {}                 # Rasterzelle (16 m) -> Kreuzungspunkte


func _near_junction(x: float, z: float, rad: float) -> bool:
	## Raster statt Schleife über alle Kreuzungen (vorher ~80 Mio. Vergleiche je Kachel, 4–5 s)
	if _jgrid.is_empty() and not junctions.is_empty():
		for j in junctions.values():
			var k := Vector2i(floori(j.x / 16.0), floori(j.y / 16.0))
			if not _jgrid.has(k):
				_jgrid[k] = []
			_jgrid[k].append(j)
	var p := Vector2(x, z)
	var r := int(ceil(rad / 16.0))
	var cx := floori(x / 16.0)
	var cz := floori(z / 16.0)
	for ix in range(cx - r, cx + r + 1):
		for iz in range(cz - r, cz + r + 1):
			var lst = _jgrid.get(Vector2i(ix, iz))
			if lst == null:
				continue
			for j in lst:
				if p.distance_squared_to(j) < rad * rad:
					return true
	return false


func _cell(x: float, z: float) -> Vector2i:
	return Vector2i(floori((x + 1000.0) / CELL), floori((z + 1000.0) / CELL))


func _bucket(d: Dictionary, key: Vector2i) -> Dictionary:
	if not d.has(key):
		d[key] = {"v": PackedVector3Array(), "i": PackedInt32Array()}
	return d[key]


func _quad(b: Dictionary, p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3) -> void:
	## Vier Punkte, gegen den Uhrzeigersinn von oben; Vorderseite nach oben.
	var k: int = b["v"].size()
	b["v"].append(p0)
	b["v"].append(p1)
	b["v"].append(p2)
	b["v"].append(p3)
	var n := (p1 - p0).cross(p3 - p0)
	if n.y > 0.0:
		b["i"].append_array([k, k + 2, k + 1, k, k + 3, k + 2])
	else:
		b["i"].append_array([k, k + 1, k + 2, k, k + 2, k + 3])


func _deck_mark_y(p: Vector2, t: Vector2, y: float) -> float:
	## Markierungshöhe auf einer Brücke: Profil + 5 cm. Liegt das Gelände dort auf dem Deck (kurze Brücken,
	## Widerlager – dann ist es asphaltiert und Plattenbrücken liegen 10 cm darüber), kommt die Linie darüber,
	## sonst verschwand die Mittellinie auf dem Deck.
	var g := -INF
	for off: float in [-2.5, -1.2, 0.0, 1.2, 2.5]:
		g = maxf(g, terrain.height_at(p.x - t.y * off, p.y + t.x * off))
	if g > y - 0.1 and g < y + 0.65:
		return g + 0.15
	return y + 0.05


func _gy(x: float, z: float) -> float:
	return terrain.height_at(x, z) + 0.05


var _tseg: Array = []    # Tunnelachsen der Kachel [Vector2 a, Vector2 b, halbe Breite, y_a, y_b]


var _tgrid := {}         # Vector2i (32-m-Zelle) -> Einträge aus _tseg


func _tunnel_segs() -> void:
	for tn in city.get("tunnels", []):
		var q: Array = tn["pts"]
		var hw := float(tn["w"]) * 0.5 + 0.5
		for i in q.size() - 1:
			var a := Vector2(float(q[i][0]), float(q[i][1]))
			var b := Vector2(float(q[i + 1][0]), float(q[i + 1][1]))
			var e := [a, b, hw, float(q[i][2]), float(q[i + 1][2])]
			_tseg.append(e)
			for cx in range(floori((minf(a.x, b.x) - hw) / 32.0), floori((maxf(a.x, b.x) + hw) / 32.0) + 1):
				for cz in range(floori((minf(a.y, b.y) - hw) / 32.0), floori((maxf(a.y, b.y) + hw) / 32.0) + 1):
					var k := Vector2i(cx, cz)
					if not _tgrid.has(k):
						_tgrid[k] = []
					(_tgrid[k] as Array).append(e)


func _in_tunnel(p: Vector2, y: float, extra := 0.0, above := 3.0) -> bool:
	## Liegt p (Fahrbahnhöhe y) in einer Tunnelröhre? Straßenstücke, die einige Meter ins Portal hineinreichen,
	## zogen ihre Markierung sonst quer durch die Öffnung (die Röhre hat eigene Linien)
	for s in _tgrid.get(Vector2i(floori(p.x / 32.0), floori(p.y / 32.0)), []):
		var a: Vector2 = s[0]
		var ab: Vector2 = (s[1] as Vector2) - a
		var l2 := ab.length_squared()
		if l2 < 1e-6:
			continue
		var t := (p - a).dot(ab) / l2
		if t < 0.0 or t > 1.0:
			continue
		var ty := lerpf(float(s[3]), float(s[4]), t)
		if p.distance_to(a + ab * t) < float(s[2]) + extra and y > ty - 3.0 and y < ty + above:
			return true
	return false


func _my(x: float, z: float, y_road: float) -> float:
	## Markierungshöhe: auf dem Gelände, außer es weicht stark vom Straßenprofil ab (Tunnelportal mit überschüttetem
	## Kasten, Trogwand, Stützmauer neben der Fahrbahn) – dann stieg die Linie senkrecht an der Kante hoch.
	var g := _gy(x, z)
	return g if absf(g - y_road) < 1.5 else y_road + 0.05


func _line_strip(bucket_map: Dictionary, pts: Array, offset: float, width: float, dash_on: float, dash_off: float, skip_junction: float, on_deck: bool = false) -> void:
	## Streifen entlang einer Polylinie (seitlich versetzt), optional gestrichelt.
	var samples: Array = []   # [x, z]
	var tan_list: Array = []
	var y_list: Array = []
	var total := 0.0
	for i in pts.size() - 1:
		total += Vector2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]).length()
	# kurze Brückenabschnitte (Durchlässe, 3–8 m) bekommen ihre Linie trotzdem – sonst setzte die Mittellinie
	# auf dem Deck aus
	if total < (2.0 if on_deck else 8.0):
		return
	var step := 1.0
	for i in pts.size() - 1:
		var a := Vector2(pts[i][0], pts[i][1])
		var b := Vector2(pts[i + 1][0], pts[i + 1][1])
		var l := a.distance_to(b)
		if l < 0.01:
			continue
		var t := (b - a) / l
		var n := Vector2(-t.y, t.x)
		var d := 0.0
		while d < l:
			var p := a + t * d + n * offset
			samples.append(p)
			tan_list.append(t)
			y_list.append(lerpf(float(pts[i][2]), float(pts[i + 1][2]), d / l))
			d += step
	if samples.size() < 3:
		return
	var period := dash_on + dash_off
	for i in samples.size() - 1:
		var p0: Vector2 = samples[i]
		var p1: Vector2 = samples[i + 1]
		if dash_off > 0.0:
			var ph := fposmod(float(i) * step, period)
			if ph > dash_on:
				continue
		if skip_junction > 0.0 and _near_junction(p0.x, p0.y, skip_junction):
			continue
		if not _tseg.is_empty() and _in_tunnel(p0, float(y_list[i])):
			continue
		var t0: Vector2 = tan_list[i]
		var t1: Vector2 = tan_list[i + 1]
		var n0 := Vector2(-t0.y, t0.x) * width * 0.5
		var n1 := Vector2(-t1.y, t1.x) * width * 0.5
		var b := _bucket(bucket_map, _cell(p0.x, p0.y))
		if on_deck:
			var y0 := _deck_mark_y(p0, t0, float(y_list[i]))
			var y1 := _deck_mark_y(p1, t1, float(y_list[i + 1]))
			_quad(b, Vector3(p0.x - n0.x, y0, p0.y - n0.y), Vector3(p1.x - n1.x, y1, p1.y - n1.y),
				Vector3(p1.x + n1.x, y1, p1.y + n1.y), Vector3(p0.x + n0.x, y0, p0.y + n0.y))
			continue
		var ya := float(y_list[i])
		var yb := float(y_list[i + 1])
		_quad(b,
			Vector3(p0.x - n0.x, _my(p0.x - n0.x, p0.y - n0.y, ya), p0.y - n0.y),
			Vector3(p1.x - n1.x, _my(p1.x - n1.x, p1.y - n1.y, yb), p1.y - n1.y),
			Vector3(p1.x + n1.x, _my(p1.x + n1.x, p1.y + n1.y, yb), p1.y + n1.y),
			Vector3(p0.x + n0.x, _my(p0.x + n0.x, p0.y + n0.y, ya), p0.y + n0.y))


func _markings(r: Dictionary) -> void:
	## Fahrstreifen nach StVO-Markierung: Leitlinien (3 m Strich / 6 m Lücke, Autobahn 6/12) zwischen gleichgerichteten
	## Streifen, Mittellinie zwischen den Richtungen (ab 4 Streifen durchgezogen), Randlinien an Hauptstraßen.
	## Fahrbahnband ohne Parkstreifen (pl/pr); Straßenbahn in der Mitte (tram_mid): keine Linie über den Gleisen,
	## sondern Begrenzung des Gleisbereichs.
	var cls: String = r["cls"]
	var w: float = r["width"]
	if cls in ["service", "living_street"] or w < 5.0:
		return
	var pts: Array = r["pts"]
	var deck: bool = bool(r["bridge"])
	var a := -w * 0.5 + float(r.get("pl", 0.0))         # linker Rand des Fahrbands (Versatz rechts positiv)
	var b := w * 0.5 - float(r.get("pr", 0.0))
	var dw := b - a
	var lanes := maxi(int(r.get("lanes", 1)), 1)
	var two_way := int(r["oneway"]) == 0
	var mw := cls in ["motorway", "trunk"]
	var dash_on := 6.0 if mw else 3.0
	var dash_off := 12.0 if mw else 6.0
	var skip := w * 0.5 + 3.0
	var tm := float(r.get("tram_mid", 0.0))
	if tm > 0.0 and (dw * 0.5 - tm) < 2.75:
		tm = 0.0                                        # Gleise liegen im Fahrstreifen (zu schmal für eigenen Bereich)
	var m := (a + b) * 0.5
	var mwl := Traffic.mw_layout(r)
	if mwl.y > 0.0:
		# Autobahn-Richtungsfahrbahn: Fahrstreifen 3,75 m, Leitlinie 6/12 m, Breitstriche (0,30 m) als Fahrbahn-
		# begrenzung; rechts davon der Standstreifen
		var l0 := a + mwl.x
		for k in range(1, lanes):
			_line_strip(_mk, pts, l0 + mwl.y * float(k), 0.15, 6.0, 12.0, skip, deck)
		_line_strip(_mk, pts, l0 - 0.15, 0.3, 0.0, 0.0, w * 0.5 + 2.5, deck)
		_line_strip(_mk, pts, l0 + mwl.y * float(lanes) + 0.15, 0.3, 0.0, 0.0, w * 0.5 + 2.5, deck)
		_motorway_furniture(r, a, b)
		return
	if mw and not two_way:
		_motorway_furniture(r, a, b)
	if two_way:
		var per := maxi(lanes / 2, 1)
		if dw < 5.4:
			pass                                        # zu schmal für Mittellinie
		elif tm > 0.0:
			_line_strip(_mk, pts, m - tm, 0.15, 0.0, 0.0, skip, deck)
			_line_strip(_mk, pts, m + tm, 0.15, 0.0, 0.0, skip, deck)
		elif lanes >= 4:
			_line_strip(_mk, pts, m - 0.1, 0.12, 0.0, 0.0, skip, deck)     # doppelte durchgezogene Mittellinie
			_line_strip(_mk, pts, m + 0.1, 0.12, 0.0, 0.0, skip, deck)
		else:
			_line_strip(_mk, pts, m, 0.12, dash_on, dash_off, skip, deck)
		if per >= 2:
			var inner := tm if tm > 0.0 else 0.0
			var half := (b - m) - inner
			for k in range(1, per):
				var off := inner + half * float(k) / float(per)
				_line_strip(_mk, pts, m + off, 0.12, dash_on, dash_off, skip, deck)
				_line_strip(_mk, pts, m - off, 0.12, dash_on, dash_off, skip, deck)
	else:
		for k in range(1, lanes):
			_line_strip(_mk, pts, a + dw * float(k) / float(lanes), 0.12, dash_on, dash_off, skip, deck)
	var edge := cls in ["primary", "secondary", "tertiary", "trunk", "motorway", "motorway_link", "trunk_link"] and dw >= 6.5
	if edge:
		_line_strip(_mk, pts, b - 0.3, 0.13 if not mw else 0.2, 0.0, 0.0, w * 0.5 + 2.5, deck)
		_line_strip(_mk, pts, a + 0.3, 0.13 if not mw else 0.2, 0.0, 0.0, w * 0.5 + 2.5, deck)


var _gr := {}        # Schutzplanken (Zellen)
var _gp := {}        # Leitpfosten


func _motorway_furniture(r: Dictionary, a: float, b: float) -> void:
	## Schutzplanken beidseits der Richtungsfahrbahn (Mittelstreifen und Außenrand) und Leitpfosten alle 50 m.
	## Nicht auf Brücken (dort stehen Geländer/Kappen) und nicht, wo eine andere Fahrbahn anschließt
	## (Ein-/Ausfädelstreifen, Rampen).
	if bool(r["bridge"]):
		return
	var pts: Array = r["pts"]
	var rid := int(r["id"])
	var s_tot := 0.0
	for side in [-1.0, 1.0]:
		var off: float = (a - 0.8) if side < 0.0 else (b + 0.8)
		var prev = null
		var s_run := 0.0
		var next_post := 25.0
		for i in pts.size() - 1:
			var p0 := Vector2(pts[i][0], pts[i][1])
			var p1 := Vector2(pts[i + 1][0], pts[i + 1][1])
			var l := p0.distance_to(p1)
			if l < 0.01:
				continue
			var t := (p1 - p0) / l
			var n := Vector2(-t.y, t.x)
			var steps := maxi(1, int(ceil(l / 4.0)))
			for k in steps + 1:
				var f := float(k) / float(steps)
				var q := p0 + t * (l * f) + n * off
				var y := lerpf(float(pts[i][2]), float(pts[i + 1][2]), f)
				var free := true
				var hit := index.nearest(q.x, q.y, 4.5)
				if not hit.is_empty():
					var hr: Dictionary = hit["road"]
					var hw := float(hr["width"]) * 0.5 + 0.5
					if int(hr["id"]) != rid and float(hit["d"]) < hw and absf(float(hit["py"]) - y) < 2.0 \
							and not (String(hr["cls"]) in ["footway", "path", "cycleway", "steps", "track"]):
						free = false
				var cur := Vector3(q.x, y, q.y)
				if free and prev != null and k > 0:
					_guard_seg(prev, cur, Vector3(n.x, 0, n.y) * side)
				if free and k > 0:
					s_run += l / float(steps)
					if s_run >= next_post:
						next_post += 50.0
						_post(cur + Vector3(n.x, 0, n.y) * side * 0.5, Vector3(t.x, 0, t.y))
				prev = cur if free else null
		s_tot += s_run


func _guard_seg(p0: Vector3, p1: Vector3, out: Vector3) -> void:
	## Stahlschutzplanke: Holm 0,31 m hoch (Oberkante 0,75 m), Pfosten alle 4 m
	var bk := _bucket(_gr, _cell(p0.x, p0.z))
	var th := out * 0.04
	var y0 := Vector3(0, 0.44, 0)
	var y1 := Vector3(0, 0.75, 0)
	var ym := Vector3(0, 0.595, 0)
	var dent := out * 0.035                                  # Mittelsicke des W-Profils
	# Fahrbahnseite: zwei Wulste mit Sicke
	_quad(bk, p0 - th + y0, p1 - th + y0, p1 - th + dent + ym, p0 - th + dent + ym)
	_quad(bk, p0 - th + dent + ym, p1 - th + dent + ym, p1 - th + y1, p0 - th + y1)
	# Rückseite und Oberkante
	_quad(bk, p1 + th + y0, p0 + th + y0, p0 + th + y1, p1 + th + y1)
	_quad(bk, p0 - th + y1, p1 - th + y1, p1 + th + y1, p0 + th + y1)
	# Pfosten am Segmentanfang
	var t := (p1 - p0).normalized() * 0.05
	var po := p0 + out * 0.09
	_quad(bk, po - t - out * 0.05, po + t - out * 0.05, po + t - out * 0.05 + y1, po - t - out * 0.05 + y1)
	_quad(bk, po + t + out * 0.05, po - t + out * 0.05, po - t + out * 0.05 + y1, po + t + out * 0.05 + y1)
	_quad(bk, po - t + out * 0.05, po - t - out * 0.05, po - t - out * 0.05 + y1, po - t + out * 0.05 + y1)
	_quad(bk, po + t - out * 0.05, po + t + out * 0.05, po + t + out * 0.05 + y1, po + t - out * 0.05 + y1)


func _post(p: Vector3, t: Vector3) -> void:
	## Leitpfosten (Zeichen 620): weiß, 1,0 m über Grund, mit schwarzem Band
	var bk := _bucket(_gp, _cell(p.x, p.z))
	var n := Vector3(-t.z, 0, t.x) * 0.06
	var tt := t * 0.04
	var up := Vector3(0, 1.0, 0)
	_quad(bk, p - n - tt, p + n - tt, p + n - tt + up, p - n - tt + up)
	_quad(bk, p + n + tt, p - n + tt, p - n + tt + up, p + n + tt + up)
	_quad(bk, p - n + tt, p - n - tt, p - n - tt + up, p - n + tt + up)
	_quad(bk, p + n - tt, p + n + tt, p + n + tt + up, p + n - tt + up)


func _crossings() -> void:
	for c in city["crossings"]:
		var hit := index.nearest(c[0], c[1], 2.0)
		if hit.is_empty():
			continue
		var r: Dictionary = hit["road"]
		if r["cls"] == "service" and r["width"] < 4.0:
			continue
		var w: float = r["width"]
		var t := Vector2(hit["tx"], hit["tz"])
		var n := Vector2(-t.y, t.x)
		var ctr := Vector2(hit["px"], hit["pz"])
		var s := -w * 0.5 + 0.5
		while s < w * 0.5 - 0.3:
			var q := ctr + n * s
			var h := t * 1.6
			var hw := n * 0.25
			var b := _bucket(_mk, _cell(q.x, q.y))
			var corners: Array = [q - h - hw, q + h - hw, q + h + hw, q - h + hw]
			var vs: Array[Vector3] = []
			for cc in corners:
				vs.append(Vector3(cc.x, _gy(cc.x, cc.y) + 0.005, cc.y))
			_quad(b, vs[0], vs[1], vs[2], vs[3])
			s += 1.0


func _rail(rl: Dictionary) -> void:
	## Schienen (Spurweite 1435 mm); auf Brücken in Deckhöhe (Schotterbett: Schienenkopf 0,17 m über Deck)
	var pts: Array = rl["pts"]
	var deck := bool(rl["bridge"])
	var lift: Array = pts
	if deck:
		var dy := 0.12 if String(rl.get("kind", "")) != "tram" else 0.0
		lift = []
		for p in pts:
			lift.append([p[0], p[1], float(p[2]) + dy])
	for off in [-0.7175, 0.7175]:
		_line_strip(_rl, lift, off, 0.075, 0.0, 0.0, 0.0, deck)


func _flush(buckets: Dictionary, mat: Material, range_end: float) -> void:
	for key in buckets:
		var b: Dictionary = buckets[key]
		if b["v"].is_empty():
			continue
		var norms := PackedVector3Array()
		norms.resize(b["v"].size())
		norms.fill(Vector3.UP)
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = b["v"]
		arr[Mesh.ARRAY_NORMAL] = norms
		arr[Mesh.ARRAY_INDEX] = b["i"]
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.visibility_range_end = range_end
		mi.visibility_range_end_margin = 30.0
		mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		add_child(mi)


func _flush3d(buckets: Dictionary, mat: Material, range_end: float, solid: bool) -> void:
	## wie _flush, aber mit Flächennormalen (aufrechte Bauteile) und wahlweise Kollision
	var faces := PackedVector3Array()
	for key in buckets:
		var b: Dictionary = buckets[key]
		if b["v"].is_empty():
			continue
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		var vv: PackedVector3Array = b["v"]
		for idx in b["i"]:
			st.add_vertex(vv[idx])
		st.generate_normals()
		var mesh := st.commit()
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = mat
		mi.visibility_range_end = range_end
		mi.visibility_range_end_margin = 30.0
		mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		add_child(mi)
		if solid:
			faces.append_array(mesh.get_faces())
	if solid:
		_static_faces(faces, "guard")


func _tris_to_surface(flat: Array, uv_mode: int) -> Dictionary:
	## flat: [x,y,z,...] je 3 Punkte = Dreieck. uv_mode 0: Draufsicht, 1: Seitenansicht.
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var uv := PackedVector2Array()
	var faces := PackedVector3Array()
	var cnt := flat.size() / 9
	for t in cnt:
		var a := Vector3(flat[t * 9], flat[t * 9 + 1], flat[t * 9 + 2])
		var b := Vector3(flat[t * 9 + 3], flat[t * 9 + 4], flat[t * 9 + 5])
		var c := Vector3(flat[t * 9 + 6], flat[t * 9 + 7], flat[t * 9 + 8])
		var fn := -(b - a).cross(c - a)
		if fn.length_squared() < 1e-10:
			continue
		fn = fn.normalized()
		for p in [a, b, c]:
			v.append(p)
			n.append(fn)
			faces.append(p)
			if uv_mode == 0:
				uv.append(Vector2(p.x, p.z) * 0.25)
			else:
				uv.append(Vector2(p.x + p.z, p.y) * 0.4)
	return {"v": v, "n": n, "uv": uv, "faces": faces}


static var _masonry: Material
static var _walk: Material
static var _ballast: Material
static var _kappe: Material


static func _walk_mat() -> Material:
	## Gehwegplatten auf Brücken (wie Gehwege der Stadt)
	if _walk == null:
		_walk = TexLib.tri_material("sidewalk", 0.84)
	return _walk


static func _ballast_mat() -> Material:
	## Schotterbett der Eisenbahnbrücken
	if _ballast == null:
		_ballast = TexLib.tri_material("gravel", 0.7)
	return _ballast


static func _kappe_mat() -> Material:
	## Betonkappe / Bordstein
	if _kappe == null:
		_kappe = TexLib.tri_material("concrete", 1.15)
	return _kappe


static func masonry_mat() -> Material:
	## patinierter Elbsandstein der historischen Brücken (#7a6a5c, dunkler als Fassaden-Sandstein)
	if _masonry == null:
		var sm := ShaderMaterial.new()
		sm.shader = load("res://shaders/bridge_stone.gdshader")
		sm.set_shader_parameter("stone_albedo", TexLib.texture("sandstone", "albedo"))
		sm.set_shader_parameter("stone_normal", TexLib.texture("sandstone", "normal"))
		sm.set_shader_parameter("stone_rough", TexLib.texture("sandstone", "rough"))
		sm.set_shader_parameter("tile_m", TexLib.tile_size("sandstone"))
		_masonry = TexLib.shared_material("bridge_stone", sm)
	return _masonry


func _lod2_bridge(bm: Dictionary, stone := false) -> void:
	var mesh := ArrayMesh.new()
	var all_faces := PackedVector3Array()
	var mats: Array = [deck_mat, concrete_mat, concrete_dark_mat, _walk_mat(), _ballast_mat(), _kappe_mat(), _kappe_mat()]
	if stone:
		mats = [deck_mat, masonry_mat(), masonry_mat(), _walk_mat(), _ballast_mat(), masonry_mat(), masonry_mat()]
	if String(bm.get("id", "")).begins_with("fill:"):
		# ergänzte Deckfläche unter einer Fahrbahn ohne LoD2-Deck (bridge_decks.py): das ist die Fahrbahn selbst –
		# als Betonfläche fehlten dort Asphalt und Fahrstreifen (A 17, zweite Richtungsfahrbahn)
		mats[5] = deck_mat
	# Deckaufbau (tools/bridge_decks.py): Asphalt nur in Fahrbahnbreite, Gehweg +15 cm, Schotterbett, Betonkappe
	var keys := ["top", "side", "bot", "top_walk", "top_ballast", "top_conc", "curb"]
	for i in keys.size():
		var flat: Array = bm.get(keys[i], [])
		if flat.size() < 9:
			continue
		var sf := _tris_to_surface(flat, 1 if i in [1, 2, 6] else 0)
		if (sf["v"] as PackedVector3Array).is_empty():
			continue
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = sf["v"]
		arr[Mesh.ARRAY_NORMAL] = sf["n"]
		arr[Mesh.ARRAY_TEX_UV] = sf["uv"]
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		mesh.surface_set_material(mesh.get_surface_count() - 1, mats[i])
		all_faces.append_array(sf["faces"])
	if mesh.get_surface_count() == 0:
		return
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	add_child(mi)
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.set_meta("kind", "lod2:" + String(bm.get("id", "")))
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(all_faces)
	cs.shape = sh
	body.add_child(cs)
	mi.add_child(body)


func _bridge_rails(rails: Array) -> void:
	## Brückengeländer entlang der Deckkanten, Bauart je Brücke (Pipeline tools/bridge_styles.py, Recherche
	## data/research/bruecken.json): [ax, az, bx, bz, y, art, farbe]
	##   stone = Sandsteinbrüstung (1,05 m), concrete = Betonschutzwand (0,9 m),
	##   steel = Betonkappe + Stahlgeländer (Pfosten alle 2 m, Handlauf, Füllstäbe) in der Farbe der Brücke.
	if rails.is_empty():
		return
	var walls := {"stone": [], "concrete": []}
	var steel: Array = []
	for r in rails:
		var art := String(r[5]) if r.size() > 5 else "stone"
		if art == "steel" or art == "glass":
			steel.append(r)
		else:
			walls["concrete" if art == "concrete" else "stone"].append(r)
	var faces := PackedVector3Array()
	for art in walls:
		if not (walls[art] as Array).is_empty():
			_rail_walls(walls[art], 1.05 if art == "stone" else 0.9, 0.18, masonry_mat() if art == "stone" else _concrete_mat(), faces)
	if not steel.is_empty():
		_rail_steel(steel, faces)
	if faces.is_empty():
		return
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.set_meta("kind", "rail")
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(faces)
	cs.shape = sh
	body.add_child(cs)
	add_child(body)


func _rail_walls(rails: Array, h: float, th: float, mat: Material, faces: PackedVector3Array) -> void:
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var uv := PackedVector2Array()
	for r in rails:
		var a := Vector2(r[0], r[1])
		var b := Vector2(r[2], r[3])
		var y: float = r[4]
		var d := b - a
		var L := d.length()
		if L < 0.5:
			continue
		var t := d / L
		var nn := Vector2(-t.y, t.x)
		var p0 := Vector3(a.x, y, a.y)
		var p1 := Vector3(b.x, y, b.y)
		var o := Vector3(nn.x, 0, nn.y) * th
		var up := Vector3(0, h, 0)
		var quads := [
			[p0 + o, p1 + o, p1 + o + up, p0 + o + up, Vector3(nn.x, 0, nn.y)],
			[p1 - o, p0 - o, p0 - o + up, p1 - o + up, Vector3(-nn.x, 0, -nn.y)],
			[p0 - o + up, p1 - o + up, p1 + o + up, p0 + o + up, Vector3.UP],
		]
		for q in quads:
			var qn: Vector3 = q[4]
			var pts := [q[0], q[1], q[2], q[3]]
			var order := [0, 1, 2, 0, 2, 3]
			if -(pts[1] - pts[0]).cross(pts[2] - pts[0]).dot(qn) < 0.0:
				order = [0, 2, 1, 0, 3, 2]
			for k in order:
				v.append(pts[k])
				n.append(qn)
				uv.append(Vector2(pts[k].x + pts[k].z, pts[k].y) * 0.4)
				faces.append(pts[k])
	if v.is_empty():
		return
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = v
	arr[Mesh.ARRAY_NORMAL] = n
	arr[Mesh.ARRAY_TEX_UV] = uv
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.surface_set_material(0, mat)
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	add_child(mi)


static var _rail_mats := {}
static var _bars_tex: ImageTexture


static func _concrete_mat() -> Material:
	if not _rail_mats.has("concrete"):
		_rail_mats["concrete"] = TexLib.tri_material("concrete", 0.92)
	return _rail_mats["concrete"]


static func _steel_mats(col: Color) -> Array:
	## [Rohre/Pfosten, Füllstäbe (Alpha-Schnitt)] in der Brückenfarbe, je Farbe geteilt
	var key := col.to_html(false)
	if _rail_mats.has(key):
		return _rail_mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.metallic = 0.55
	m.roughness = 0.45
	if _bars_tex == null:
		# senkrechte Füllstäbe: 16 mm Stab je 12 cm (Textur 64 px breit = 0,12 m)
		var img := Image.create_empty(64, 4, false, Image.FORMAT_RGBA8)
		for x in 64:
			var on := x < 10
			for yy in 4:
				img.set_pixel(x, yy, Color(1, 1, 1, 1.0 if on else 0.0))
		img.generate_mipmaps()
		_bars_tex = ImageTexture.create_from_image(img)
	var f := StandardMaterial3D.new()
	f.albedo_color = col
	f.albedo_texture = _bars_tex
	f.metallic = 0.5
	f.roughness = 0.5
	f.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	f.alpha_scissor_threshold = 0.5
	f.cull_mode = BaseMaterial3D.CULL_DISABLED
	f.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_rail_mats[key] = [m, f]
	return _rail_mats[key]


func _rail_steel(rails: Array, faces: PackedVector3Array) -> void:
	var by_col := {}
	for r in rails:
		var c := String(r[6]) if r.size() > 6 else "#6E7378"
		if not by_col.has(c):
			by_col[c] = []
		by_col[c].append(r)
	var kappe := SurfaceTool.new()
	kappe.begin(Mesh.PRIMITIVE_TRIANGLES)
	for c in by_col:
		var tube := SurfaceTool.new()
		tube.begin(Mesh.PRIMITIVE_TRIANGLES)
		var fill := SurfaceTool.new()
		fill.begin(Mesh.PRIMITIVE_TRIANGLES)
		var glass_st := SurfaceTool.new()
		glass_st.begin(Mesh.PRIMITIVE_TRIANGLES)
		for r in by_col[c]:
			var a := Vector2(r[0], r[1])
			var b := Vector2(r[2], r[3])
			var y: float = r[4]
			var d := b - a
			var L := d.length()
			if L < 0.3:
				continue
			var t := d / L
			var t3 := Vector3(t.x, 0, t.y)
			var nn := Vector3(-t.y, 0, t.x)
			var p0 := Vector3(a.x, y, a.y)
			var p1 := Vector3(b.x, y, b.y)
			var glass: bool = r.size() > 5 and String(r[5]) == "glass"
			var top: float = clampf(float(r[7]) if r.size() > 7 else 1.1, 0.9, 4.5) + 0.22
			# Betonkappe 0,22 m hoch, 0,30 m breit
			_box_between(kappe, p0, p1, nn, 0.30, 0.0, 0.22)
			var y0 := 0.22
			# Handlauf/Oberholm und Untergurt
			_box_between(tube, p0 + Vector3(0, top - 0.06, 0), p1 + Vector3(0, top - 0.06, 0), nn, 0.07, 0.0, 0.06)
			_box_between(tube, p0 + Vector3(0, y0 + 0.08, 0), p1 + Vector3(0, y0 + 0.08, 0), nn, 0.05, 0.0, 0.05)
			# Pfosten alle 2 m
			var k := 0.0
			while k <= L + 0.01:
				var pp := p0 + t3 * minf(k, L)
				_box_between(tube, pp - t3 * 0.035, pp + t3 * 0.035, nn, 0.06 if not glass else 0.10, y0, top - 0.06)
				k += 2.0
			# Füllung: Stäbe (Alpha-Schnitt, 0,12 m je Wiederholung) bzw. Glas
			var q := [p0 + Vector3(0, y0 + 0.13, 0), p1 + Vector3(0, y0 + 0.13, 0), p1 + Vector3(0, top - 0.06, 0), p0 + Vector3(0, top - 0.06, 0)]
			var u1 := L / 0.12
			var uvs := [Vector2(0, 1), Vector2(u1, 1), Vector2(u1, 0), Vector2(0, 0)]
			var target: SurfaceTool = glass_st if glass else fill
			for idx in [0, 1, 2, 0, 2, 3]:
				target.set_normal(nn)
				target.set_uv(uvs[idx])
				target.add_vertex(q[idx])
			# Kollision: dünne Wand bis Oberkante
			var hv := Vector3(0, top, 0)
			for w in [p0, p1, p1 + hv, p0, p1 + hv, p0 + hv]:
				faces.append(w)
		var mats := _steel_mats(Color(c))
		var m1 := tube.commit()
		if m1.get_surface_count() > 0:
			m1.surface_set_material(0, mats[0])
			var mi := MeshInstance3D.new()
			mi.mesh = m1
			mi.visibility_range_end = 450.0
			add_child(mi)
		var mg := glass_st.commit()
		if mg.get_surface_count() > 0:
			if not _rail_mats.has("glass"):
				var gm := StandardMaterial3D.new()
				gm.albedo_color = Color(0.78, 0.86, 0.88, 0.22)
				gm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
				gm.roughness = 0.05
				gm.metallic_specular = 0.8
				gm.cull_mode = BaseMaterial3D.CULL_DISABLED
				_rail_mats["glass"] = gm
			mg.surface_set_material(0, _rail_mats["glass"])
			var mig := MeshInstance3D.new()
			mig.mesh = mg
			mig.visibility_range_end = 450.0
			mig.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mig)
		var m2 := fill.commit()
		if m2.get_surface_count() > 0:
			m2.surface_set_material(0, mats[1])
			var mi2 := MeshInstance3D.new()
			mi2.mesh = m2
			mi2.visibility_range_end = 300.0
			mi2.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mi2)
	var mk := kappe.commit()
	if mk.get_surface_count() > 0:
		mk.surface_set_material(0, _concrete_mat())
		var mi3 := MeshInstance3D.new()
		mi3.mesh = mk
		add_child(mi3)


static func _box_between(st: SurfaceTool, a: Vector3, b: Vector3, side: Vector3, w: float, y0: float, y1: float) -> void:
	## Quader von a nach b (horizontal), Breite w quer (side), Höhe y0..y1 über a/b
	var o := side.normalized() * (w * 0.5)
	var c := [a - o + Vector3(0, y0, 0), b - o + Vector3(0, y0, 0), b + o + Vector3(0, y0, 0), a + o + Vector3(0, y0, 0)]
	var hv := Vector3(0, y1 - y0, 0)
	var u := [c[0] + hv, c[1] + hv, c[2] + hv, c[3] + hv]
	var quads := [[c[0], c[1], u[1], u[0]], [c[2], c[3], u[3], u[2]], [c[1], c[2], u[2], u[1]], [c[3], c[0], u[0], u[3]], [u[0], u[1], u[2], u[3]]]
	for q in quads:
		var nrm: Vector3 = (q[1] - q[0]).cross(q[2] - q[0]).normalized()
		for idx in [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]:
			st.set_normal(nrm)
			st.add_vertex(q[idx])


func _bridge(b: Dictionary) -> void:
	## OSM-Brücke ohne LoD2-Deck: Platte 0,9 m mit Betonstirn; Straßenbrücke: Asphalt in Fahrbahnbreite, beidseits
	## 1 m Kappe/Gehweg (+15 cm, Bordstein), Stahlgeländer; Fußgängerbrücke: Gehwegplatten, Stahlgeländer.
	var pts0: Array = b["pts"]
	if pts0.size() < 2:
		return
	# alle 2,5 m ein Querschnitt, damit das Deck dem aufliegenden Gelände folgen kann (s. u.)
	var pts: Array = []
	for i0 in pts0.size() - 1:
		var qa := Vector3(pts0[i0][0], pts0[i0][1], pts0[i0][2])
		var qb := Vector3(pts0[i0 + 1][0], pts0[i0 + 1][1], pts0[i0 + 1][2])
		var nseg := maxi(1, int(ceil(Vector2(qb.x - qa.x, qb.y - qa.y).length() / 2.5)))
		for k0 in nseg:
			var qq := qa.lerp(qb, float(k0) / float(nseg))
			pts.append([qq.x, qq.y, qq.z])
	pts.append(pts0[pts0.size() - 1])
	var drive: bool = b["kind"] == "drive"
	var is_rail: bool = b["kind"] == "rail"       # Bahnbrücke ohne LoD2-Deck (tools/rail_slabs.py): Schotterbett
	var wc: float = max(b["width"], 2.5)
	var w := wc + (2.0 if drive else 0.0)
	var raise := 0.15 if drive else 0.0
	var tops := {"road": [PackedVector3Array(), PackedVector3Array(), PackedVector2Array(), PackedInt32Array()],
		"walk": [PackedVector3Array(), PackedVector3Array(), PackedVector2Array(), PackedInt32Array()],
		"ballast": [PackedVector3Array(), PackedVector3Array(), PackedVector2Array(), PackedInt32Array()]}
	var sv := PackedVector3Array()
	var sn := PackedVector3Array()
	var si := PackedInt32Array()
	var faces := PackedVector3Array()
	var thick := 0.9
	var prev := []
	for i in pts.size():
		var p := Vector3(pts[i][0], pts[i][2], pts[i][1])
		var t2: Vector2
		if i == 0:
			t2 = Vector2(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
		elif i == pts.size() - 1:
			t2 = Vector2(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
		else:
			t2 = Vector2(pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1])
		t2 = t2.normalized()
		var n3 := Vector3(-t2.y, 0, t2.x)
		# Kurze Brücken über Gräben liegen im Geländemodell auf Straßenhöhe: Das Gelände (Gehwegpflaster) deckte
		# dort die Platte zu, die Fahrbahn auf der Brücke war nicht zu sehen. Liegt es bis 0,65 m über dem Deck,
		# kommt die Deckoberseite 5 cm darüber.
		var g_top := -INF
		for off: float in [-0.5, -0.25, 0.0, 0.25, 0.5]:
			g_top = maxf(g_top, terrain.height_at(p.x + n3.x * w * off, p.z + n3.z * w * off))
		if g_top > p.y - 0.1 and g_top < p.y + 0.65:
			p.y = g_top + 0.1
		# Querschnitt: Außenkante links, Bord links, Bord rechts, Außenkante rechts
		var cur := [p + n3 * (w * 0.5), p + n3 * (wc * 0.5), p - n3 * (wc * 0.5), p - n3 * (w * 0.5)]
		if i > 0:
			var up := Vector3(0, raise, 0)
			var d := Vector3(0, -thick, 0)
			if drive:
				var tw: Array = tops["walk"]
				var tr: Array = tops["road"]
				# Liegt direkt daneben eine zweite Fahrbahnplatte (getrennte Richtungsfahrbahnen einer Zufahrt), bleibt
				# die Seite dorthin Fahrbahn – sonst lag ein Kappenstreifen mitten zwischen den beiden Fahrbahnen
				var nb_l := _near_other_bridge((prev[0] + cur[0]) * 0.5, b, true)
				var nb_r := _near_other_bridge((prev[3] + cur[3]) * 0.5, b, true)
				if nb_l:
					_strip_quad(tr[0], tr[1], tr[2], tr[3], faces, prev[0], prev[1], cur[1], cur[0], Vector3.UP)
				else:
					_strip_quad(tw[0], tw[1], tw[2], tw[3], faces, prev[0] + up, prev[1] + up, cur[1] + up, cur[0] + up, Vector3.UP)
					_side_quad(sv, sn, si, faces, prev[1], cur[1], cur[1] + up, prev[1] + up, (prev[2] - prev[1]).normalized())
				_strip_quad(tr[0], tr[1], tr[2], tr[3], faces, prev[1], prev[2], cur[2], cur[1], Vector3.UP)
				if nb_r:
					_strip_quad(tr[0], tr[1], tr[2], tr[3], faces, prev[2], prev[3], cur[3], cur[2], Vector3.UP)
				else:
					_strip_quad(tw[0], tw[1], tw[2], tw[3], faces, prev[2] + up, prev[3] + up, cur[3] + up, cur[2] + up, Vector3.UP)
					_side_quad(sv, sn, si, faces, prev[2], cur[2], cur[2] + up, prev[2] + up, (prev[1] - prev[2]).normalized())
			else:
				var tw2: Array = tops["ballast" if is_rail else "walk"]
				_strip_quad(tw2[0], tw2[1], tw2[2], tw2[3], faces, prev[0], prev[3], cur[3], cur[0], Vector3.UP)
			# Unterseite
			_side_quad(sv, sn, si, faces, prev[3] + d, prev[0] + d, cur[0] + d, cur[3] + d, Vector3.DOWN)
			# Stirnseiten (Beton) bis Deckoberkante; Geländer darauf, außer wo eine Nachbarbrücke anschließt
			var ml: Vector3 = (prev[0] + cur[0]) * 0.5
			var mr: Vector3 = (prev[3] + cur[3]) * 0.5
			_side_quad(sv, sn, si, faces, prev[0] + d, cur[0] + d, cur[0] + up, prev[0] + up, (prev[0] - prev[3]).normalized())
			_side_quad(sv, sn, si, faces, prev[3] + up, cur[3] + up, cur[3] + d, prev[3] + d, (prev[3] - prev[0]).normalized())
			var inl: Vector3 = (prev[3] - prev[0]).normalized() * 0.15
			var upv := Vector3(0, raise, 0)
			if not _near_other_bridge(ml, b) and not _rail_on_road(ml + upv) and not _rail_on_road(prev[0] + upv) \
					and not _rail_on_road(cur[0] + upv):
				_slab_rails.append([prev[0].x + inl.x, prev[0].z + inl.z, cur[0].x + inl.x, cur[0].z + inl.z,
					(prev[0].y + cur[0].y) * 0.5 + raise, "steel", "#8c9294" if drive else "#7a7f84", 1.1])
			if not _near_other_bridge(mr, b) and not _rail_on_road(mr + upv) and not _rail_on_road(prev[3] + upv) \
					and not _rail_on_road(cur[3] + upv):
				_slab_rails.append([prev[3].x - inl.x, prev[3].z - inl.z, cur[3].x - inl.x, cur[3].z - inl.z,
					(prev[3].y + cur[3].y) * 0.5 + raise, "steel", "#8c9294" if drive else "#7a7f84", 1.1])
		prev = cur
	var mesh := ArrayMesh.new()
	for key in ["road", "walk", "ballast"]:
		var arrs: Array = tops[key]
		if (arrs[0] as PackedVector3Array).is_empty():
			continue
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = arrs[0]
		arr[Mesh.ARRAY_NORMAL] = arrs[1]
		arr[Mesh.ARRAY_TEX_UV] = arrs[2]
		arr[Mesh.ARRAY_INDEX] = arrs[3]
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		mesh.surface_set_material(mesh.get_surface_count() - 1,
			deck_mat if key == "road" else (_ballast_mat() if key == "ballast" else _walk_mat()))
	if not sv.is_empty():
		var arr2 := []
		arr2.resize(Mesh.ARRAY_MAX)
		arr2[Mesh.ARRAY_VERTEX] = sv
		arr2[Mesh.ARRAY_NORMAL] = sn
		arr2[Mesh.ARRAY_INDEX] = si
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr2)
		mesh.surface_set_material(mesh.get_surface_count() - 1, _kappe_mat())
	if mesh.get_surface_count() == 0:
		return
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	add_child(mi)
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.set_meta("kind", "slab:%d" % int(b["id"]))
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(faces)
	cs.shape = sh
	body.add_child(cs)
	mi.add_child(body)
	if _gen_piers and not city.get("bridge_arches", {}).has("gpiers"):
		_piers(pts, w, thick, "slab:%d" % int(b["id"]))


func _rail_on_road(p: Vector3) -> bool:
	## Geländer einer Plattenbrücke stünde in einer Fahrbahn auf gleicher Höhe (Fußgängersteg neben/auf der Straße,
	## Seitenstraße an der Brücke) -> weglassen
	if index == null:
		return false
	var hit: Dictionary = index.nearest(p.x, p.z, 12.0)
	if hit.is_empty() or bool(hit.get("bridge", false)):
		return false
	var rd: Dictionary = hit["road"]
	var d := Vector2(float(hit["px"]) - p.x, float(hit["pz"]) - p.z).length()
	return d < float(rd.get("width", 4.0)) * 0.5 - 0.1 and absf(float(hit["py"]) - p.y) < 1.5


func _near_other_bridge(p: Vector3, self_b: Dictionary, only_drive := false) -> bool:
	## Brüstung weglassen, wo eine andere Brücke (Nachbarfahrbahn, Gehweg) direkt anschließt.
	for ob in city["bridges"]:
		if ob == self_b or (only_drive and String(ob.get("kind", "")) != "drive"):
			continue
		var op: Array = ob["pts"]
		var hw: float = maxf(float(ob["width"]), 2.5) * 0.5 + 0.8
		for i in op.size() - 1:
			var ax: float = op[i][0]
			var az: float = op[i][1]
			var dx: float = op[i + 1][0] - ax
			var dz: float = op[i + 1][1] - az
			var l2 := dx * dx + dz * dz
			if l2 < 0.01:
				continue
			var t := clampf(((p.x - ax) * dx + (p.z - az) * dz) / l2, 0.0, 1.0)
			var qx := ax + dx * t
			var qz := az + dz * t
			if (p.x - qx) * (p.x - qx) + (p.z - qz) * (p.z - qz) < hw * hw:
				var qy: float = lerpf(float(op[i][2]), float(op[i + 1][2]), t)
				if absf(qy - p.y) < 3.0:
					return true
	return false


func _piers(pts: Array, w: float, thick: float, src := "") -> void:
	## Pfeiler alle ~30 m, wenn die Fahrbahn deutlich über dem Boden liegt.
	var total := 0.0
	for i in pts.size() - 1:
		total += Vector2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]).length()
	if total < 40.0:
		return
	var n := int(total / 30.0)
	var spacing := total / float(n + 1)
	for k in range(1, n + 1):
		var target := spacing * k
		var acc := 0.0
		for i in pts.size() - 1:
			var a := Vector3(pts[i][0], pts[i][2], pts[i][1])
			var b := Vector3(pts[i + 1][0], pts[i + 1][2], pts[i + 1][1])
			var l := Vector2(b.x - a.x, b.z - a.z).length()
			if acc + l >= target:
				var p := a.lerp(b, (target - acc) / maxf(l, 0.001))
				var gy := terrain.height_at(p.x, p.z)
				var deck_bot := p.y - thick
				if deck_bot - gy < 1.5:
					break
				var dir := Vector3(b.x - a.x, 0, b.z - a.z).normalized()
				var h := deck_bot - (gy - 2.5)
				var bm := BoxMesh.new()
				bm.size = Vector3(w * 0.55, h, 2.4)
				var inst := MeshInstance3D.new()
				inst.mesh = bm
				inst.material_override = stone_mat
				inst.transform = Transform3D(Basis.looking_at(dir, Vector3.UP), Vector3(p.x, gy - 2.5 + h * 0.5, p.z))
				add_child(inst)
				var pb := StaticBody3D.new()
				pb.collision_layer = 1
				pb.set_meta("kind", "pier:" + src)
				var pcs := CollisionShape3D.new()
				var bs := BoxShape3D.new()
				bs.size = bm.size
				pcs.shape = bs
				pb.add_child(pcs)
				inst.add_child(pb)
				break
			acc += l


func _strip_quad(verts: PackedVector3Array, norms: PackedVector3Array, uvs: PackedVector2Array, idx: PackedInt32Array, faces: PackedVector3Array, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	var k := verts.size()
	for p in [a, b, c, d]:
		verts.append(p)
		norms.append(n)
		uvs.append(Vector2(p.x, p.z) * 0.25)
	var front := -(b - a).cross(c - a)
	var tri1: Array = [k, k + 1, k + 2]
	var tri2: Array = [k, k + 2, k + 3]
	if front.dot(n) < 0.0:
		tri1 = [k, k + 2, k + 1]
		tri2 = [k, k + 3, k + 2]
	idx.append_array(tri1)
	idx.append_array(tri2)
	for ii in tri1 + tri2:
		faces.append(verts[ii])


func _side_quad(sv: PackedVector3Array, sn: PackedVector3Array, si: PackedInt32Array, faces: PackedVector3Array, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	var k := sv.size()
	for p in [a, b, c, d]:
		sv.append(p)
		sn.append(n)
	var front := -(b - a).cross(c - a)
	var tri1: Array = [k, k + 1, k + 2]
	var tri2: Array = [k, k + 2, k + 3]
	if front.dot(n) < 0.0:
		tri1 = [k, k + 2, k + 1]
		tri2 = [k, k + 3, k + 2]
	si.append_array(tri1)
	si.append_array(tri2)
	for ii in tri1 + tri2:
		faces.append(sv[ii])


func _curbs(curbs: Array) -> void:
	## Granit-Bordsteine (tools/curbs.py): Gehweg links der Laufrichtung; Stirnfläche 14 cm über Fahrbahn, Oberseite
	## 22 cm breit. Je 250-m-Zelle ein Mesh (Sichtweite 260 m), damit Entferntes nicht gezeichnet wird.
	if curbs.is_empty():
		return
	var cells := {}
	for c in curbs:
		if c.size() < 2:
			continue
		var p0: Array = c[0]
		var key := Vector2i(floori(float(p0[0]) / 250.0), floori(float(p0[1]) / 250.0))
		if not cells.has(key):
			var st := SurfaceTool.new()
			st.begin(Mesh.PRIMITIVE_TRIANGLES)
			cells[key] = st
		var st: SurfaceTool = cells[key]
		# Die Linien stammen aus einem Raster und schlängeln sich im Dezimeterbereich: glätten (Endpunkte bleiben),
		# sonst wirkt der Bordstein wie eine gewellte Schlange
		var sm: Array = []
		for q in c:
			sm.append(Vector3(float(q[0]), float(q[2]), float(q[1])))
		for _it in 12:
			var prev: Vector3 = sm[0]
			for i in range(1, sm.size() - 1):
				var cur: Vector3 = sm[i]
				sm[i] = cur.lerp((prev + (sm[i + 1] as Vector3)) * 0.5, 0.5)
				prev = cur
		for i in sm.size() - 1:
			var pa: Vector3 = sm[i]
			var pb: Vector3 = sm[i + 1]
			var d := Vector3(pb.x - pa.x, 0, pb.z - pa.z)
			var L := d.length()
			if L < 0.02 or L > 8.0 or absf(pb.y - pa.y) > 1.5:
				continue
			# Bordstein aus dem Geländeraster, der an einer Mauer/Portalkante hochklettert (Steigung > 30 %), oder im
			# Lichtraum von Portal/Röhre: weglassen
			if absf(pb.y - pa.y) > 0.3 * L:
				continue
			if not _tseg.is_empty() and (_in_tunnel(Vector2(pa.x, pa.z), pa.y, 1.2, 5.3) or _in_tunnel(Vector2(pb.x, pb.z), pb.y, 1.2, 5.3)):
				continue
			d /= L
			var lft := Vector3(-d.z, 0, d.x)            # Gehwegseite wie in tools/curbs.py: (−dz, dx)
			var lo := Vector3(0, -0.05, 0)
			var hi := Vector3(0, 0.14, 0)
			var w := lft * 0.22
			# Stirnfläche (zur Fahrbahn), Oberseite, Rückseite
			_curb_quad(st, pa + lo, pb + lo, pb + hi, pa + hi, -lft, L)
			_curb_quad(st, pa + hi, pb + hi, pb + hi + w, pa + hi + w, Vector3.UP, L)
			_curb_quad(st, pb + w + lo, pa + w + lo, pa + w + hi, pb + w + hi, lft, L)
	if not _rail_mats.has("curb"):
		var cm := (TexLib.tri_material("paving_sandstone", 0.72) as StandardMaterial3D).duplicate() as StandardMaterial3D
		cm.cull_mode = BaseMaterial3D.CULL_DISABLED          # Bordsteinflächen beidseitig
		_rail_mats["curb"] = cm
	var mat: Material = _rail_mats["curb"]
	for key in cells:
		var st: SurfaceTool = cells[key]
		var mesh := st.commit()
		if mesh.get_surface_count() == 0:
			continue
		mesh.surface_set_material(0, mat)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.visibility_range_end = 260.0
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		add_child(mi)


static func _curb_quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3, _L: float) -> void:
	# beide Umlaufrichtungen prüfen: Vorderseite muss zu n zeigen (Godot: Vorderseite im Uhrzeigersinn)
	var order := [0, 1, 2, 0, 2, 3]
	var q := [a, b, c, d]
	if (b - a).cross(c - a).dot(n) > 0.0:
		order = [0, 2, 1, 0, 3, 2]
	for k in order:
		st.set_normal(n)
		st.add_vertex(q[k])


func _bridge_arches(data: Dictionary) -> void:
	## Steinbögen historischer Brücken (tools/bridge_arches.py): Stirnwände mit Bogenöffnungen, Laibungen, Pfeiler.
	## Dazu Pfeiler der übrigen recherchierten Brücken an den echten Feldgrenzen ("piers").
	var pst := SurfaceTool.new()
	pst.begin(Mesh.PRIMITIVE_TRIANGLES)
	var npier := 0
	# piers: recherchierte Feldgrenzen; gpiers: Standardpfeiler. [x, z, yaw, breite, oben, unten, (dicke)]
	# Breite = sichtbare Breite (Pipeline spart Verkehrsbänder darunter aus; alte Daten: volle Brückenbreite × 0,85)
	var new_fmt := data.has("gpiers")
	for pr in data.get("piers", []) + data.get("gpiers", []):
		var w := float(pr[3]) if new_fmt else float(pr[3]) * 0.85
		var top := float(pr[4])
		var bot := float(pr[5])
		var th := float(pr[6]) * 0.5 if pr.size() > 6 else 1.1
		if top - bot < 1.0:
			continue
		var b := Basis(Vector3.UP, float(pr[2]))
		var c := Vector3(float(pr[0]), (top + bot) * 0.5, float(pr[1]))
		var ax := b * Vector3(1, 0, 0)
		var az := b * Vector3(0, 0, 1)
		# Pfeilerscheibe quer zur Achse (Breite w), 2,2 m stark
		_box_between(pst, c - az * th + Vector3(0, -(top - bot) * 0.5, 0), c + az * th + Vector3(0, -(top - bot) * 0.5, 0), ax, w, 0.0, top - bot)
		npier += 1
	if npier > 0:
		var pm := pst.commit()
		pm.surface_set_material(0, concrete_mat)
		var pmi := MeshInstance3D.new()
		pmi.mesh = pm
		pmi.visibility_range_end = 1800.0
		add_child(pmi)
		_static_faces(pm.get_faces(), "arch_pier")
	for gr in data.get("groups", []):
		# Blechträger/Gussstützen (Stahl, Farbe je Brücke) und Betonstirn erneuerter Überbauten
		if (gr.get("tris", []) as Array).size() < 9:
			continue
		var gm: Material
		if String(gr.get("mat", "")) == "concrete":
			# nach unten zeigende Flächen wie Deck-Unterseiten dunkel (sonst wirkten die Halbbögen der A17-Talbrücke
			# von unten hell gelbgrün – heller Beton + Umgebungslicht vom Gras – unter dem dunklen Überbau)
			var parts := _split_down(gr["tris"], gr.get("n", []))
			if (parts[2] as Array).size() >= 9:
				var dm := _tri_mesh(parts[2], parts[3], concrete_dark_mat, 1500.0)
				_static_faces(dm.get_faces(), "girder")
			if (parts[0] as Array).size() < 9:
				continue
			var cm := _tri_mesh(parts[0], parts[1], concrete_mat, 1500.0)
			_static_faces(cm.get_faces(), "girder")
			continue
		else:
			var smat := StandardMaterial3D.new()
			smat.albedo_color = Color(String(gr.get("color", "#4a4846")))
			smat.metallic = 0.55
			smat.roughness = 0.55
			if String(gr.get("mat", "")) == "steelbox":
				smat.metallic = 0.15                          # lackierter Stahlkasten/-trog (gevouteter Hauptträger)
				smat.roughness = 0.7
			gm = smat
		var gmesh := _tri_mesh(gr["tris"], gr.get("n", []), gm, 1500.0)
		_static_faces(gmesh.get_faces(), "girder")
	var steel: Dictionary = data.get("steel", {})
	if (steel.get("tris", []) as Array).size() >= 9:
		var sm := StandardMaterial3D.new()
		sm.albedo_color = Color(String(steel.get("color", "#c9ccd0")))
		sm.metallic = 0.45
		sm.roughness = 0.4
		var stm := _tri_mesh(steel["tris"], steel.get("n", []), sm, 2500.0)
		_static_faces(stm.get_faces(), "steel")
	var t: Array = data.get("tris", []) + data.get("kz_tris", [])      # kz: Böden der Pfeilerkanzeln
	var nn: Array = data.get("n", []) + data.get("kz_n", [])
	if t.size() < 9:
		return
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var uv := PackedVector2Array()
	var ntri := t.size() / 9
	for i in ntri:
		var a := Vector3(t[i * 9], t[i * 9 + 1], t[i * 9 + 2])
		var b := Vector3(t[i * 9 + 3], t[i * 9 + 4], t[i * 9 + 5])
		var c := Vector3(t[i * 9 + 6], t[i * 9 + 7], t[i * 9 + 8])
		var fn := Vector3(nn[i * 3], nn[i * 3 + 1], nn[i * 3 + 2]) if nn.size() >= (i + 1) * 3 else (b - a).cross(c - a).normalized()
		# Godot: Vorderseite im Uhrzeigersinn, von außen (Normale) gesehen
		var pts := [a, b, c] if (b - a).cross(c - a).dot(fn) < 0.0 else [a, c, b]
		for p in pts:
			v.append(p)
			n.append(fn)
			uv.append(Vector2(p.x + p.z, p.y) * 0.25)
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = v
	arr[Mesh.ARRAY_NORMAL] = n
	arr[Mesh.ARRAY_TEX_UV] = uv
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.surface_set_material(0, masonry_mat())
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.visibility_range_end = 1800.0
	add_child(mi)
	_static_faces(mesh.get_faces(), "arch")


func _static_faces(faces: PackedVector3Array, kind: String) -> void:
	## Kollision für Brückenbauteile, die bisher nur sichtbar waren (Bögen, Pfeiler, Stahlüberbau)
	if faces.size() < 3:
		return
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.set_meta("kind", kind)
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(faces)
	cs.shape = sh
	body.add_child(cs)
	add_child(body)


static func _split_down(t: Array, nn: Array) -> Array:
	## Dreiecksliste nach Normale teilen: [übrige, Normalen, nach unten zeigende (n.y < -0,35), Normalen]
	var up_t := []
	var up_n := []
	var dn_t := []
	var dn_n := []
	for i in t.size() / 9:
		var ny: float = float(nn[i * 3 + 1]) if nn.size() >= (i + 1) * 3 else 0.0
		var dst_t: Array = dn_t if ny < -0.35 else up_t
		var dst_n: Array = dn_n if ny < -0.35 else up_n
		for k in 9:
			dst_t.append(t[i * 9 + k])
		if nn.size() >= (i + 1) * 3:
			for k in 3:
				dst_n.append(nn[i * 3 + k])
	return [up_t, up_n, dn_t, dn_n]


func _tri_mesh(t: Array, nn: Array, mat: Material, vis: float) -> ArrayMesh:
	## Dreiecksliste [x, y, z, …] mit Normale je Dreieck -> Mesh (Umlaufsinn nach Normale korrigiert)
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	for i in t.size() / 9:
		var a := Vector3(t[i * 9], t[i * 9 + 1], t[i * 9 + 2])
		var b := Vector3(t[i * 9 + 3], t[i * 9 + 4], t[i * 9 + 5])
		var c := Vector3(t[i * 9 + 6], t[i * 9 + 7], t[i * 9 + 8])
		var fn := Vector3(nn[i * 3], nn[i * 3 + 1], nn[i * 3 + 2]) if nn.size() >= (i + 1) * 3 else (b - a).cross(c - a).normalized()
		var pts := [a, b, c] if (b - a).cross(c - a).dot(fn) < 0.0 else [a, c, b]
		for p in pts:
			v.append(p)
			n.append(fn)
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = v
	arr[Mesh.ARRAY_NORMAL] = n
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.surface_set_material(0, mat)
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.visibility_range_end = vis
	add_child(mi)
	return mesh
