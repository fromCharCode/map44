class_name Trams
extends Node3D
## Straßenbahnen: fahren auf den OSM-Gleisen (Gleisgraph), Wagenabschnitte folgen der Spur des Kopfes.
## Dazu Oberleitung (Fahrdraht) und Masten.

const PROPS := "res://assets/models/props/"

var terrain: Terrain
var focus := Vector3.ZERO
var ways: Array = []                # {pts: Array[Vector3], a: Vector2i, b: Vector2i, len: float}
var node_ways := {}                 # Vector2i -> Array [way_idx, end(0|1)]
var trams: Array = []               # TramUnit
var rng := RandomNumberGenerator.new()
var target_count := 4
var section_offsets: Array[float] = [22.25]
var scene_path := PROPS + "tram.glb"
var multi := false
## Fuhrpark: [Datei, Anteil]. NGT D12DD (Bombardier Flexity Classic) und NGT DX DD (neue Generation ab 2022).
const FLEET := [["tram_sections.glb", 0.6], ["tram_dxdd.glb", 0.4]]
var models: Array = []              # {path, offsets, weight}
static var emit_mats: Array = []
var enabled := true
var _dbg := OS.has_environment("DRESDEN_TRAMDBG")
var routes: Array = []              # echte Linien (godot/data/tram_routes.json): {ref, to, pts, cum}
var _route_cells := {}              # Vector2i (100-m-Zelle) -> [[route, s], ...]


func init(count: int) -> void:
	target_count = count
	rng.seed = 1945
	for f in FLEET:
		if ResourceLoader.exists(PROPS + String(f[0])):
			scene_path = PROPS + String(f[0])
			multi = true
			_probe_sections()
			models.append({"path": scene_path, "offsets": section_offsets.duplicate(), "weight": float(f[1])})
	if models.is_empty():
		_probe_sections()
		models.append({"path": scene_path, "offsets": section_offsets.duplicate(), "weight": 1.0})
	_load_routes()


# --- Linien ------------------------------------------------------------------------------------------
func _load_routes() -> void:
	var p := DataPaths.file("tram_routes.json")
	if not FileAccess.file_exists(p):
		return
	var j = JSON.parse_string(FileAccess.get_file_as_string(p))
	if not (j is Dictionary):
		return
	for r in j.get("routes", []):
		var pts := PackedVector2Array()
		for q in r["pts"]:
			pts.append(Vector2(float(q[0]), float(q[1])))
		if pts.size() < 2 or String(r.get("ref", "")) == "":
			continue
		var cum := PackedFloat32Array([0.0])
		for i in range(1, pts.size()):
			cum.append(cum[i - 1] + pts[i].distance_to(pts[i - 1]))
		var to := String(r.get("to", ""))
		if to.begins_with("Dresden, "):
			to = to.substr(9)
		var ri := routes.size()
		routes.append({"ref": String(r["ref"]), "to": to, "pts": pts, "cum": cum, "stops": r.get("stops", [])})
		var s := 0.0
		while s < cum[cum.size() - 1]:
			var q := route_point(ri, s)
			var ck := Vector2i(floori(q.x / 100.0), floori(q.y / 100.0))
			if not _route_cells.has(ck):
				_route_cells[ck] = []
			_route_cells[ck].append([ri, s])
			s += 15.0


func route_point(ri: int, s: float) -> Vector2:
	var r: Dictionary = routes[ri]
	var pts: PackedVector2Array = r["pts"]
	var cum: PackedFloat32Array = r["cum"]
	s = clampf(s, 0.0, cum[cum.size() - 1])
	var lo := 0
	var hi := cum.size() - 1
	while hi - lo > 1:
		var mid := (lo + hi) >> 1
		if cum[mid] <= s:
			lo = mid
		else:
			hi = mid
	return pts[lo].lerp(pts[hi], (s - cum[lo]) / maxf(cum[hi] - cum[lo], 0.001))


func route_project(ri: int, p: Vector2, s0: float, s1: float) -> Array:
	## [s, Abstand] der Projektion von p auf Linie ri im Fenster [s0, s1]
	var r: Dictionary = routes[ri]
	var pts: PackedVector2Array = r["pts"]
	var cum: PackedFloat32Array = r["cum"]
	var best_d := 1e9
	var best_s := s0
	for i in pts.size() - 1:
		if cum[i + 1] < s0 or cum[i] > s1:
			continue
		var a := pts[i]
		var ab := pts[i + 1] - a
		var t := clampf((p - a).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
		var d := (a + ab * t).distance_to(p)
		if d < best_d:
			best_d = d
			best_s = cum[i] + (cum[i + 1] - cum[i]) * t
	return [best_s, best_d]


func route_for(p: Vector2, dirv: Vector2) -> Array:
	## Linien, die bei p in Richtung dirv verlaufen: [[route, s], ...]
	var res: Array = []
	var seen := {}
	var ck := Vector2i(floori(p.x / 100.0), floori(p.y / 100.0))
	for dx in range(-1, 2):
		for dz in range(-1, 2):
			for it in _route_cells.get(ck + Vector2i(dx, dz), []):
				var ri: int = it[0]
				if seen.has(ri):
					continue
				var pr := route_project(ri, p, float(it[1]) - 20.0, float(it[1]) + 20.0)
				if float(pr[1]) > 6.0:
					continue
				var t := (route_point(ri, float(pr[0]) + 3.0) - route_point(ri, float(pr[0]) - 3.0)).normalized()
				if t.dot(dirv) < 0.8:
					continue
				seen[ri] = true
				res.append([ri, float(pr[0])])
	return res


## Hängt die Gleise einer Kachel an; liefert den Container mit Oberleitung/Masten (zum Entladen).
## stops: Haltestellenmasten der Kachel (Vector2 x/z) – Bahnen halten dort statt zufällig auf der Strecke.
func add_rails(t: Terrain, rails: Array, container: Node3D, poles: Array = [], stops: Array = []) -> void:
	var first := ways.size()
	for rl in rails:
		if rl["kind"] != "tram" or rl["pts"].size() < 2:
			continue
		var pts: Array = []
		for p in rl["pts"]:
			pts.append(Vector3(p[0], p[2] + 0.06, p[1]))
		var L := 0.0
		for i in pts.size() - 1:
			L += Vector2(pts[i + 1].x - pts[i].x, pts[i + 1].z - pts[i].z).length()
		if L < 0.5:
			continue
		var idx := ways.size()
		var ka := _key(pts[0])
		var kb := _key(pts[pts.size() - 1])
		# Fahrtrichtung (Rechtsverkehr) und Haltepunkte berechnet die Pipeline (build_city.tram_rail_meta);
		# ältere Kacheldaten ohne diese Felder: beide Richtungen, Halt ohne Haltestellendaten
		ways.append({"pts": pts, "a": ka, "b": kb, "len": L, "bridge": rl["bridge"], "mid": pts[pts.size() / 2],
			"pref": int(rl.get("pref", 0)), "stops": rl.get("stops", [])})
		_link(ka, idx, 0)
		_link(kb, idx, 1)
	_build_wires_and_poles(t, first, container, poles)


# --- Fahrtrichtung je Gleis (Rechtsverkehr) ------------------------------------------------------------
# OSM erfasst jedes Gleis als eigenen Weg ohne Fahrtrichtung. Bei zweigleisigen Strecken liegt das Gegengleis
# links der Fahrtrichtung -> pref = +1 (entlang der Punkte) oder -1; eingleisig/unklar = 0 (beide Richtungen).
var _samples := {}                  # Vector2i (6-m-Zelle) -> Array [way, Vector2 p, Vector2 t]
const SAMPLE_CELL := 6.0


func _index_samples(first: int) -> void:
	for wi in range(first, ways.size()):
		var w: Dictionary = ways[wi]
		var L: float = w["len"]
		var s := 0.0
		while s <= L:
			var p := _way_point(w, s)
			var t := way_dir(wi, s, 1)
			var k := Vector2i(floori(p.x / SAMPLE_CELL), floori(p.z / SAMPLE_CELL))
			if not _samples.has(k):
				_samples[k] = []
			(_samples[k] as Array).append([wi, Vector2(p.x, p.z), t])
			s += 4.0


func _compute_pref(first: int) -> void:
	# auch bereits geladene Nachbargleise an der Kachelgrenze neu bewerten
	var todo := {}
	for wi in range(first, ways.size()):
		todo[wi] = true
	for wi in range(first, ways.size()):
		var w: Dictionary = ways[wi]
		for p in [w["pts"][0], w["pts"][w["pts"].size() - 1]]:
			for e in node_ways.get(_key(p), []):
				todo[e[0]] = true
	for wi in todo:
		var w: Dictionary = ways[wi]
		var L: float = w["len"]
		var left := 0
		var right := 0
		var s := minf(3.0, L * 0.5)
		while s <= L - 1.0:
			var p3 := _way_point(w, s)
			var p := Vector2(p3.x, p3.z)
			var t := way_dir(wi, s, 1)
			var best_d := 6.5
			var best_side := 0
			var cx := floori(p.x / SAMPLE_CELL)
			var cz := floori(p.y / SAMPLE_CELL)
			for dx in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					for smp in _samples.get(Vector2i(cx + dx, cz + dz), []):
						if smp[0] == wi:
							continue
						var t2: Vector2 = smp[2]
						if absf(t2.dot(t)) < 0.92:
							continue
						var rel: Vector2 = (smp[1] as Vector2) - p
						var lat := t.x * rel.y - t.y * rel.x      # > 0: rechts, < 0: links (x Ost, z Süd)
						var along := absf(rel.dot(t))
						if along > 5.0 or absf(lat) < 2.2:
							continue
						if absf(lat) < best_d:
							best_d = absf(lat)
							best_side = 1 if lat > 0.0 else -1
			if best_side < 0:
				left += 1
			elif best_side > 0:
				right += 1
			s += 6.0
		var n := left + right
		if n >= 2 and left >= right * 2:
			w["pref"] = 1
		elif n >= 2 and right >= left * 2:
			w["pref"] = -1
		else:
			w["pref"] = 0


func _assign_stops(first: int, stops: Array) -> void:
	for st in stops:
		var q: Vector2 = st
		var cx := floori(q.x / SAMPLE_CELL)
		var cz := floori(q.y / SAMPLE_CELL)
		var best_w := -1
		var best_d := 9.0
		for dx in [-2, -1, 0, 1, 2]:
			for dz in [-2, -1, 0, 1, 2]:
				for smp in _samples.get(Vector2i(cx + dx, cz + dz), []):
					if int(smp[0]) < first:
						continue
					var d := ((smp[1] as Vector2) - q).length()
					if d < best_d:
						best_d = d
						best_w = smp[0]
		if best_w < 0:
			continue
		# nächstes Gleis immer; weitere nur, wenn der Mast dicht daneben steht (Mittelbahnsteig zwischen beiden
		# Gleisen). Bei Seitenbahnsteigen hat das Gegengleis seinen eigenen Mast.
		var near := {best_w: true}
		for dx in [-1, 0, 1]:
			for dz in [-1, 0, 1]:
				for smp in _samples.get(Vector2i(cx + dx, cz + dz), []):
					if int(smp[0]) >= first and ((smp[1] as Vector2) - q).length() < 4.5:
						near[smp[0]] = true
		for wi in near:
			var w: Dictionary = ways[wi]
			(w["stops"] as Array).append(_project(wi, q))
			(w["stops"] as Array).sort()


func _project(wi: int, q: Vector2) -> float:
	var pts: Array = ways[wi]["pts"]
	var acc := 0.0
	var best := 0.0
	var best_d := 1e9
	for i in pts.size() - 1:
		var a := Vector2(pts[i].x, pts[i].z)
		var b := Vector2(pts[i + 1].x, pts[i + 1].z)
		var ab := b - a
		var l := ab.length()
		if l < 0.001:
			continue
		var tt := clampf((q - a).dot(ab) / (l * l), 0.0, 1.0)
		var d := (a + ab * tt).distance_to(q)
		if d < best_d:
			best_d = d
			best = acc + l * tt
		acc += l
	return best


func _key(p: Vector3) -> Vector2i:
	return Vector2i(roundi(p.x / 1.5), roundi(p.z / 1.5))


func _link(k: Vector2i, idx: int, end: int) -> void:
	# auch Nachbarzellen zulassen (Rundungsgrenzen)
	for dx in [-1, 0, 1]:
		for dz in [-1, 0, 1]:
			var kk := Vector2i(k.x + dx, k.y + dz)
			if not node_ways.has(kk):
				node_ways[kk] = []
			node_ways[kk].append([idx, end])


func _probe_sections() -> void:
	## Liest die Abschnittsmitten aus dem Modell (Abstand hinter der Front).
	var ps := load(scene_path) as PackedScene
	if ps == null:
		return
	var root := ps.instantiate()
	var zs: Array[float] = []
	var front := 0.0
	if multi:
		for i in 12:
			var n := root.find_child("Section_%d" % i, true, false) as Node3D
			if n == null:
				break
			zs.append(n.position.z)
		# Front = kleinstes z der Gesamt-AABB (aus allen Meshes)
		front = _min_z(root)
		section_offsets.clear()
		for z in zs:
			section_offsets.append(z - front)
	else:
		front = _min_z(root)
		section_offsets = [-front]
	root.free()


func _min_z(n: Node) -> float:
	var m := 1e9
	var stack: Array = [[n, Transform3D.IDENTITY]]
	while not stack.is_empty():
		var it: Array = stack.pop_back()
		var node: Node = it[0]
		var xf: Transform3D = it[1]
		if node is Node3D and node != n:
			xf = xf * (node as Node3D).transform
		if node is MeshInstance3D:
			var bb := xf * (node as MeshInstance3D).get_aabb()
			m = minf(m, bb.position.z)
		for c in node.get_children():
			stack.append([c, xf])
	return m


func _way_point(w: Dictionary, s: float) -> Vector3:
	var pts: Array = w["pts"]
	var acc := 0.0
	for i in pts.size() - 1:
		var a: Vector3 = pts[i]
		var b: Vector3 = pts[i + 1]
		var l := Vector2(b.x - a.x, b.z - a.z).length()
		if acc + l >= s or i == pts.size() - 2:
			return a.lerp(b, clampf((s - acc) / maxf(l, 0.001), 0.0, 1.0))
		acc += l
	return pts[pts.size() - 1]


func way_point(idx: int, s: float) -> Vector3:
	return _way_point(ways[idx], s)


func way_dir(idx: int, s: float, dir: int) -> Vector2:
	var a := _way_point(ways[idx], maxf(s - 1.0, 0.0))
	var b := _way_point(ways[idx], minf(s + 1.0, ways[idx]["len"]))
	var d := Vector2(b.x - a.x, b.z - a.z).normalized() * float(dir)
	return d


func next_way(idx: int, end: int, last_dir: Vector2, route := -1, route_s := 0.0) -> Array:
	## Folgegleis am Ende 'end' (0 = Anfang, 1 = Ende) des Gleises idx. Gibt [way, start_end] oder [].
	## Mit Linie: das Gleis, das dem Linienweg folgt, hat Vorrang.
	var w: Dictionary = ways[idx]
	var p: Vector3 = (w["pts"][0] if end == 0 else w["pts"][w["pts"].size() - 1])
	var cands: Array = []
	var dbg: Array = []
	for e in node_ways.get(_key(p), []):
		if e[0] == idx:
			continue
		var w2: Dictionary = ways[e[0]]
		var p2: Vector3 = (w2["pts"][0] if e[1] == 0 else w2["pts"][w2["pts"].size() - 1])
		if Vector2(p2.x - p.x, p2.z - p.z).length() > 4.0:
			continue
		var d2 := way_dir(e[0], 0.0 if e[1] == 0 else w2["len"], 1 if e[1] == 0 else -1)
		if d2.dot(last_dir) < 0.2:
			continue
		var travel := 1 if e[1] == 0 else -1
		var score := d2.dot(last_dir)
		var pref: int = w2.get("pref", 0)
		if pref != 0 and pref != travel:
			score -= 3.0                    # Gegengleis nur, wenn es gar nicht anders geht
		if route >= 0:
			# mittlerer Abstand des Kandidaten zum Linienweg (Punkte alle 4 m bis 32 m): direkt hinter einer Weiche
			# liegen beide Gleise noch dicht beieinander, erst der Verlauf trennt sie
			var lw := float(w2["len"])
			var dsum := 0.0
			var nsm := 0
			var sc := 4.0
			var pr: Array = [route_s, 99.0]
			while true:
				var sq := minf(sc, lw)
				var q := way_point(e[0], sq if e[1] == 0 else lw - sq)
				pr = route_project(route, Vector2(q.x, q.z), route_s - 5.0, route_s + 70.0)
				dsum += float(pr[1])
				nsm += 1
				if sq >= lw or sc >= 32.0:
					break
				sc += 4.0
			var davg := dsum / nsm
			score += 6.0 * clampf(1.0 - davg / 3.0, 0.0, 1.0)
			if _dbg:
				dbg.append("  Kandidat %d (L %.0f) mittlerer Abstand zur Linie %.1f m, Wertung %.2f" % [e[0], lw, davg, score])
		cands.append([e[0], e[1], score])
	if _dbg and route >= 0:
		var hp := Vector2(p.x, p.z)
		var pr0 := route_project(route, hp, route_s - 30.0, route_s + 30.0)
		print("WEICHE Linie %s bei (%.0f, %.0f) route_s %.0f (Projektion %.0f, %.1f m) Gleis %d Ende %d:\n%s" % [routes[route]["ref"], p.x, p.z, route_s, float(pr0[0]), float(pr0[1]), idx, end, "\n".join(dbg)])
	if cands.is_empty():
		return []
	cands.sort_custom(func(a, b): return a[2] > b[2])
	return [cands[0][0], cands[0][1]]


func _spawn() -> void:
	for attempt in 400:
		var wi := rng.randi_range(0, ways.size() - 1)
		var w: Dictionary = ways[wi]
		if w["len"] < 40.0 or w["bridge"]:
			continue
		var md: Vector3 = w["mid"]
		if Vector2(md.x - focus.x, md.z - focus.z).length() > 900.0:
			continue
		var dir := 1 if rng.randf() < 0.5 else -1
		if int(w.get("pref", 0)) != 0:
			dir = int(w["pref"])               # Rechtsverkehr: auf dem richtigen Gleis
		var s := rng.randf_range(w["len"] * 0.3, w["len"] * 0.7)
		var hp := way_point(wi, s)
		var lines := route_for(Vector2(hp.x, hp.z), way_dir(wi, s, dir))
		if lines.is_empty() and attempt < 300 and not routes.is_empty():
			continue                         # bevorzugt Gleise mit Linienverkehr (keine Betriebsstrecken)
		var tu := TramUnit.new()
		add_child(tu)
		if not lines.is_empty():
			var pick: Array = lines[rng.randi() % lines.size()]
			tu.route = int(pick[0])
			tu.route_s = float(pick[1])
		var mdl: Dictionary = models[0]
		var wsum := 0.0
		for m in models:
			wsum += float(m["weight"])
		var r := rng.randf() * wsum
		for m in models:
			r -= float(m["weight"])
			if r <= 0.0:
				mdl = m
				break
		var offs: Array[float] = []
		offs.assign(mdl["offsets"])
		tu.setup(self, String(mdl["path"]), multi, offs, wi, dir, s)
		trams.append(tu)
		return


func _process(_delta: float) -> void:
	for i in range(trams.size() - 1, -1, -1):
		var t: TramUnit = trams[i]
		if t.dead or (t.bodies.size() > 0 and (t.bodies[0] as Node3D).global_position.distance_to(focus) > 1500.0):
			t.queue_free()
			trams.remove_at(i)
	if enabled and trams.size() < target_count and ways.size() > 0:
		_spawn()


func set_night(n: float) -> void:
	for m in emit_mats:
		var sm: StandardMaterial3D = m
		match String(sm.resource_name):
			"HeadlightEmit": sm.emission_energy_multiplier = 2.5 * n + 0.4
			"TaillightEmit": sm.emission_energy_multiplier = 1.5 * n + 0.3
			"TramWindow": sm.emission_energy_multiplier = 0.045 * n
			_:
				var nm := String(sm.resource_name)
				if nm.begins_with("PosterEmit"):
					sm.emission_energy_multiplier = 0.15 + 0.9 * n      # City-Light-Vitrinen
				elif nm.begins_with("ShelterLightEmit"):
					sm.emission_energy_multiplier = 3.0 * n            # LED-Leiste unter dem Hallendach


func section_bodies() -> Array:
	var res: Array = []
	for t in trams:
		for b in (t as TramUnit).bodies:
			res.append(b)
	return res


func _build_wires_and_poles(terr: Terrain, first: int, container: Node3D, poles: Array = []) -> void:
	var wire_v := PackedVector3Array()
	var pole_xf: Array = []
	# Masten vom Datenaufbau (am Bordstein, nicht auf der Fahrbahn) mit Querdraht zur Fahrleitung
	for pl in poles:
		var px := float(pl[0])
		var pz := float(pl[1])
		var py := float(pl[7]) if pl.size() > 7 else terr.height_at(px, pz)     # Brückenmasten: Deckhöhe
		var yaw := float(pl[3])
		pole_xf.append(Transform3D(Basis(Vector3.UP, yaw), Vector3(px, py, pz)))
		var toward := Vector3(cos(yaw), 0, -sin(yaw))
		var tip := Vector3(px, py + 6.25, pz) + toward * 3.05
		var track := Vector3(float(pl[4]), float(pl[6]) + 5.75, float(pl[5]))
		var dist := Vector2(track.x - px, track.z - pz).length()
		if dist > 3.3:
			wire_v.append(tip)
			wire_v.append(track + (track - Vector3(px, track.y, pz)).normalized() * 1.6)
	for wi in range(first, ways.size()):
		var w: Dictionary = ways[wi]
		var pts: Array = w["pts"]
		# Fahrdraht auch über Brücken (Masten dort aus tools/bridge_decks.py am Deckrand)
		for i in pts.size() - 1:
			wire_v.append(Vector3(pts[i].x, pts[i].y + 5.7, pts[i].z))
			wire_v.append(Vector3(pts[i + 1].x, pts[i + 1].y + 5.7, pts[i + 1].z))
		if not poles.is_empty() or w["bridge"]:
			continue          # Masten kommen aus den Kacheldaten
		# Masten alle ~38 m, abwechselnd links/rechts
		var step := 38.0
		var s := 10.0
		var side := 1.0 if (int(w["len"]) % 2 == 0) else -1.0
		while s < w["len"] - 6.0:
			var p := _way_point(w, s)
			var d := Vector2(_way_point(w, s + 1.0).x - _way_point(w, s - 1.0).x, _way_point(w, s + 1.0).z - _way_point(w, s - 1.0).z).normalized()
			var n := Vector2(-d.y, d.x) * side
			var pos := Vector2(p.x, p.z) + n * 3.0
			var toward := -n
			var yaw := atan2(-toward.y, toward.x)
			pole_xf.append(Transform3D(Basis(Vector3.UP, yaw), Vector3(pos.x, terr.height_at(pos.x, pos.y), pos.y)))
			s += step
			side = -side
	if not wire_v.is_empty():
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = wire_v
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINES, arr)
		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.albedo_color = Color(0.06, 0.06, 0.07)
		mesh.surface_set_material(0, mat)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.visibility_range_end = 450.0
		container.add_child(mi)
	var ps := load(PROPS + "tram_pole.glb") as PackedScene
	if ps and not pole_xf.is_empty():
		var root := ps.instantiate()
		var parts: Array = []
		var stack: Array = [[root, Transform3D.IDENTITY]]
		while not stack.is_empty():
			var it: Array = stack.pop_back()
			var n: Node = it[0]
			var xf: Transform3D = it[1]
			if n is Node3D and n != root:
				xf = xf * (n as Node3D).transform
			if n is MeshInstance3D:
				parts.append({"mesh": (n as MeshInstance3D).mesh, "xf": xf})
			for c in n.get_children():
				stack.append([c, xf])
		root.free()
		for part in parts:
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = part["mesh"]
			RenderUtil.fill_multimesh(mm, pole_xf, part["xf"])
			var inst := MultiMeshInstance3D.new()
			inst.multimesh = mm
			inst.visibility_range_end = 350.0
			inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			container.add_child(inst)
