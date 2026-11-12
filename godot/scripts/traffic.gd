class_name Traffic
extends Node3D
## Verkehr: KI-Fahrzeuge (AICar) und Busse (BusCar) auf dem Straßengraphen.
## Kreuzungen (tools/junctions.py): Zufahrten mit Vorrang, Haltelinien, Ampelsteuerungen (SignalCtl).
## Fahrzeuge melden sich an ihrer nächsten Kreuzung an (jreg) und prüfen dort Konflikte mit anderen Fahrzeugen
## und dem Spieler.

const MODELS := ["hatchback.glb", "sedan.glb", "van.glb", "citycar.glb"]
const LENGTHS := {"hatchback.glb": 4.3, "sedan.glb": 4.7, "van.glb": 5.9, "citycar.glb": 3.6,
	"bus_solo.glb": 12.0, "bus_articulated.glb": 18.1}
const COLORS := [
	Color(0.92, 0.92, 0.9), Color(0.75, 0.76, 0.78), Color(0.12, 0.12, 0.13), Color(0.18, 0.22, 0.34),
	Color(0.55, 0.08, 0.1), Color(0.35, 0.36, 0.38), Color(0.16, 0.3, 0.22), Color(0.85, 0.82, 0.7),
	Color(0.9, 0.55, 0.1), Color(0.5, 0.52, 0.55),
]
const LVL := [2, 1, 3]       # pri aus junctions.py (0 gleichrangig, 1 wartepflichtig, 2 Vorfahrt) -> Rang

var terrain                # World oder Terrain (height_at)
var dressing: Dressing
var player: Node3D
var cam: Camera3D
var nodes: Array = []
var edges: Array = []
var _node_keys := {}
var _graph_keys := {}
var edge_cells := {}
var out_edges := {}        # node_id -> [[edge_idx, dir], ...]
var cars: Array = []       # AICar (inkl. Busse)
var target_count := 60
var bus_target := 7
var spawn_timer := 0.0
var bus_timer := 2.0
var rng := RandomNumberGenerator.new()
var _total_len := 0.0
var enabled := true
var trams: Trams
var jreg := {}             # node_id -> Array[AICar] (nähern sich / sind in der Kreuzung)
var night := 0.0
var rain := 0.0
var bus_routes: Array = []
var _bus_cells := {}       # Vector2i (200 m) -> Array[[route_idx, s]]
var _next_id := 1
var _player_cache := {}    # node_id -> Dictionary (je Physik-Frame)
var _player_frame := -1
var ignore_player := false     # Prüfstand: Spieler zählt nicht als Verkehrsteilnehmer
var stats := {"spawn": 0, "bus_spawn": 0}


func setup(t, dress: Dressing, player_node: Node3D, camera: Camera3D) -> void:
	terrain = t
	dressing = dress
	player = player_node
	cam = camera
	rng.seed = 20261109
	_load_bus_routes()


func next_id() -> int:
	_next_id += 1
	return _next_id


## Hängt den Graphen einer geladenen Kachel an (Knoten gleicher Position werden verschmolzen).
func add_graph(graph: Dictionary, key: String = "") -> void:
	if key != "":
		if _graph_keys.has(key):
			return          # Kachel erneut geladen: Graph ist schon da
		_graph_keys[key] = true
	_dead_cache.clear()
	var remap := {}
	var ctls: Array = graph.get("ctls", [])
	var base := edges.size()
	for n in graph["nodes"]:
		var p: Array = n["pos"]
		var k := Vector2i(roundi(p[0] * 2.0), roundi(p[2] * 2.0))
		var gid: int
		if _node_keys.has(k):
			gid = _node_keys[k]
			if n.get("signal", false):
				nodes[gid]["signal"] = true
		else:
			gid = nodes.size()
			_node_keys[k] = gid
			nodes.append({"id": gid, "pos": p, "signal": n.get("signal", false), "app": [], "rbl": 0, "jr": 6.0})
		remap[int(n["id"])] = gid
		var nd: Dictionary = nodes[gid]
		if n.has("app"):
			for a in n["app"]:
				var ci := int(a[7])
				var ctl: Array = ctls[ci] if ci >= 0 and ci < ctls.size() else []
				# [globale Kante, d, ang, pri, sign, ph, stop_d, ctl-Array]
				(nd["app"] as Array).append([base + int(a[0]), int(a[1]), float(a[2]), int(a[3]), int(a[4]), int(a[5]), float(a[6]), ctl])
			nd["rbl"] = int(n.get("rbl", 0))
			nd["jr"] = float(n.get("jr", 6.0))
	var no_tun := OS.has_environment("DRESDEN_NOTUNEDGES")
	for e in graph["edges"]:
		if no_tun and e.get("tunnel", false):
			continue
		var ge: Dictionary = e
		ge["a"] = remap[int(e["a"])]
		ge["b"] = remap[int(e["b"])]
		var ei := edges.size()
		edges.append(ge)
		var ow := int(ge["oneway"])
		if ow >= 0:
			_add_out(int(ge["a"]), ei, 1)
		if ow <= 0:
			_add_out(int(ge["b"]), ei, -1)
		_total_len += float(ge["len"])
		var pts: Array = ge["pts"]
		var mid: Array = pts[pts.size() / 2]
		var ck := Vector2i(floori(mid[0] / 100.0), floori(mid[1] / 100.0))
		if not edge_cells.has(ck):
			edge_cells[ck] = []
		edge_cells[ck].append(ei)


func _add_out(n: int, ei: int, dir: int) -> void:
	if not out_edges.has(n):
		out_edges[n] = []
	out_edges[n].append([ei, dir])


func degree(n: int) -> int:
	var c := 0
	for o in out_edges.get(n, []):
		c += 1
	return c


## Zufahrt-Eintrag am Knoten für Kante ei in Richtung dir (oder leeres Array)
func approach(node_id: int, ei: int, dir: int) -> Array:
	for a in nodes[node_id]["app"]:
		if int(a[0]) == ei and int(a[1]) == dir:
			return a
	return []


## Seitlicher Versatz der Fahrspur (rechts der Fahrtrichtung) für Kante e in Richtung dir.
## Berücksichtigt Parkstreifen (pl/pr) und mehrstreifige Straßen (rechte Spur).
func lane_offset(e: Dictionary, dir: int) -> float:
	var w: float = e["width"]
	var pl: float = e.get("pl", 0.0)
	var pr: float = e.get("pr", 0.0)
	# Fahrbahnband in Wegrichtung: [a, b] (positiv = rechts der Wegrichtung)
	var a := -w * 0.5 + pl
	var b := w * 0.5 - pr
	if dir == -1:
		var t := a
		a = -b
		b = -t
	var two_way := int(e["oneway"]) == 0
	if two_way and b - a < 4.6:
		return (a + b) * 0.5          # Gasse: in der Mitte (KI fährt sie nur in einer Richtung)
	if two_way:
		var m := (a + b) * 0.5
		var half := b - m
		if half > 3.6:
			return b - 1.75            # mehrere Spuren: rechte Spur
		return m + half * 0.5
	var width_d := b - a
	if width_d > 4.6:
		return b - 1.75
	return (a + b) * 0.5


## Punkte einer Kante in Fahrtrichtung, auf die Fahrspur versetzt. Rückgabe: Array von Vector3 (x, y, z).
func edge_points(ei: int, dir: int) -> Array:
	var e: Dictionary = edges[ei]
	var pts: Array = e["pts"]
	var seq: Array = []
	if dir == 1:
		seq = pts.duplicate()
	else:
		for i in range(pts.size() - 1, -1, -1):
			seq.append(pts[i])
	var off := lane_offset(e, dir)
	var res: Array = []
	for i in seq.size():
		var t: Vector2
		if i == 0:
			t = Vector2(seq[1][0] - seq[0][0], seq[1][1] - seq[0][1])
		elif i == seq.size() - 1:
			t = Vector2(seq[i][0] - seq[i - 1][0], seq[i][1] - seq[i - 1][1])
		else:
			t = Vector2(seq[i + 1][0] - seq[i - 1][0], seq[i + 1][1] - seq[i - 1][1])
		t = t.normalized()
		var r := Vector2(-t.y, t.x)
		res.append(Vector3(seq[i][0] + r.x * off, seq[i][2], seq[i][1] + r.y * off))
	return res


## Fahrtrichtung beim Verlassen des Knotens entlang Kante ei/dir (Winkel atan2(dz, dx))
func exit_angle(ei: int, dir: int) -> float:
	var pts: Array = edges[ei]["pts"]
	var n := pts.size()
	var p0: Array = pts[0] if dir == 1 else pts[n - 1]
	var acc := 0.0
	var q: Array = p0
	if dir == 1:
		for i in range(1, n):
			acc += Vector2(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]).length()
			q = pts[i]
			if acc > 8.0:
				break
	else:
		for i in range(n - 2, -1, -1):
			acc += Vector2(pts[i][0] - pts[i + 1][0], pts[i][1] - pts[i + 1][1]).length()
			q = pts[i]
			if acc > 8.0:
				break
	return atan2(float(q[1]) - float(p0[1]), float(q[0]) - float(p0[0]))


## Fahrtrichtung beim Einfahren in den Knoten über Kante ei/dir
func entry_angle(ei: int, dir: int) -> float:
	return wrapf(exit_angle(ei, -dir) + PI, -PI, PI)


func _process(delta: float) -> void:
	if not enabled:
		return
	spawn_timer -= delta
	bus_timer -= delta
	var ppos := player.global_position
	# Entfernen weit entfernter oder blockierter Fahrzeuge
	for i in range(cars.size() - 1, -1, -1):
		var c: AICar = cars[i]
		var cp := c.world_pos()
		var far := cp.distance_to(ppos) > (520.0 if c.is_bus else 460.0)
		if c.dead or far or (terrain.has_method("has_ground") and not terrain.has_ground(cp.x, cp.z)):
			var why := c.death if c.dead else ("weit" if far else "kein_boden")
			stats[why] = int(stats.get(why, 0)) + 1
			c.release()
			c.queue_free()
			cars.remove_at(i)
	var n_bus := 0
	for c in cars:
		if (c as AICar).is_bus:
			n_bus += 1
	if cars.size() - n_bus < target_count and spawn_timer <= 0.0:
		spawn_timer = 0.25
		_try_spawn(ppos)
	if n_bus < bus_target and bus_timer <= 0.0 and not bus_routes.is_empty():
		bus_timer = 1.5
		_try_spawn_bus(ppos)


func _try_spawn(ppos: Vector3) -> void:
	for attempt in 24:
		var ang := rng.randf() * TAU
		var rad := rng.randf_range(80.0, 320.0)
		var ck := Vector2i(floori((ppos.x + cos(ang) * rad) / 100.0), floori((ppos.z + sin(ang) * rad) / 100.0))
		var cell: Array = edge_cells.get(ck, [])
		if cell.is_empty():
			continue
		var ei: int = cell[rng.randi_range(0, cell.size() - 1)]
		var e: Dictionary = edges[ei]
		if float(e["len"]) < 24.0 or String(e["cls"]) in ["footway", "path"]:
			continue
		if String(e["cls"]) == "service" and rng.randf() < 0.7:
			continue
		if _narrow(e):
			continue
		var dirs := []
		var ow := int(e["oneway"])
		if ow >= 0:
			dirs.append(1)
		if ow <= 0:
			dirs.append(-1)
		var dir: int = dirs[rng.randi_range(0, dirs.size() - 1)]
		var pts := edge_points(ei, dir)
		# nicht in Kreuzungsbereichen: 12 m Abstand zu beiden Enden
		var s := rng.randf_range(12.0, maxf(12.5, float(e["len"]) - 12.0))
		var p := _point_at(pts, s)
		var pos := Vector3(p.x, p.y, p.z)
		if not _spawn_ok(pos, ppos, 14.0):
			continue
		var car := AICar.new()
		add_child(car)
		var model: String = MODELS[rng.randi() % MODELS.size()]
		car.setup(self, model, COLORS[rng.randi() % COLORS.size()], ei, dir, s)
		cars.append(car)
		stats["spawn"] = int(stats["spawn"]) + 1
		return


func _spawn_ok(pos: Vector3, ppos: Vector3, clear: float) -> bool:
	var d := pos.distance_to(ppos)
	if d < 70.0 or d > 340.0:
		return false
	if cam and d < 220.0:
		var to_p := (pos - cam.global_position).normalized()
		if to_p.dot(-cam.global_transform.basis.z) > 0.45:
			return false
	for c in cars:
		if (c as AICar).world_pos().distance_to(pos) < clear:
			return false
	return true


func _point_at(pts: Array, s: float) -> Vector3:
	var acc := 0.0
	for i in pts.size() - 1:
		var a: Vector3 = pts[i]
		var b: Vector3 = pts[i + 1]
		var l := Vector2(b.x - a.x, b.z - a.z).length()
		if acc + l >= s:
			return a.lerp(b, (s - acc) / maxf(l, 0.001))
		acc += l
	return pts[pts.size() - 1]


func pick_next(node_id: int, from_edge: int, last_tangent: Vector2) -> Array:
	## Wählt eine ausgehende Kante (ohne Wende, bevorzugt geradeaus, größere Straßen), Rückgabe [edge, dir] oder [].
	var opts: Array = out_edges.get(node_id, [])
	var cand: Array = []
	var weights: Array = []
	for o in opts:
		var ei: int = o[0]
		if ei == from_edge and opts.size() > 1:
			continue
		var e: Dictionary = edges[ei]
		var pts: Array = e["pts"]
		var t: Vector2
		if o[1] == 1:
			t = Vector2(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]).normalized()
		else:
			var n := pts.size()
			t = Vector2(pts[n - 2][0] - pts[n - 1][0], pts[n - 2][1] - pts[n - 1][1]).normalized()
		var dotv := t.dot(last_tangent)
		if dotv < -0.75 and opts.size() > 1:
			continue                        # keine Wende auf der Kreuzung
		var wgt := 1.0
		if dotv > 0.8:
			wgt = 3.0
		elif dotv > 0.0:
			wgt = 1.4
		else:
			wgt = 0.7
		if String(e["cls"]) in ["primary", "secondary", "tertiary"]:
			wgt *= 1.6
		if String(e["cls"]) == "service":
			wgt *= 0.25
		if _narrow(e):
			# Gasse: Gegenverkehr passt nicht aneinander vorbei -> KI nutzt sie nur in einer festen Richtung
			if int(o[1]) != narrow_dir(ei):
				continue
			wgt *= 0.3
		if _dead_end(ei, int(o[1])):
			wgt *= 0.03                     # Sackgasse (auch über mehrere Kanten)
		cand.append(o)
		weights.append(wgt)
	if cand.is_empty():
		for o in opts:
			cand.append(o)
			weights.append(1.0)
	if cand.is_empty():
		return []
	var tot := 0.0
	for w in weights:
		tot += w
	var r := rng.randf() * tot
	for i in cand.size():
		r -= weights[i]
		if r <= 0.0:
			return cand[i]
	return cand[cand.size() - 1]


var _dead_cache := {}


func _dead_end(ei: int, dir: int) -> bool:
	## Führt die Kante (über Ketten von Knoten mit nur einer Fortsetzung) in eine Sackgasse?
	var key := ei * 2 + (1 if dir == 1 else 0)
	if _dead_cache.has(key):
		return _dead_cache[key]
	var res := false
	var e_cur := ei
	var d_cur := dir
	for step in 4:
		var e: Dictionary = edges[e_cur]
		var n := int(e["b"]) if d_cur == 1 else int(e["a"])
		var outs: Array = []
		for o in out_edges.get(n, []):
			if int(o[0]) != e_cur:
				outs.append(o)
		if outs.is_empty():
			res = true
			break
		if outs.size() > 1:
			break
		e_cur = int(outs[0][0])
		d_cur = int(outs[0][1])
	_dead_cache[key] = res
	return res


func narrow_dir(ei: int) -> int:
	return 1 if ei % 2 == 0 else -1


func _narrow(e: Dictionary) -> bool:
	return int(e["oneway"]) == 0 and float(e["width"]) - float(e.get("pl", 0.0)) - float(e.get("pr", 0.0)) < 4.6


const GRID := 25.0
var _grid := {}            # Vector2i -> Array[AICar], je Physikschritt neu
var _grid_frame := -1


func _rebuild_grid() -> void:
	var f := Engine.get_physics_frames()
	if f == _grid_frame:
		return
	_grid_frame = f
	_grid.clear()
	for c in cars:
		var p: Vector3 = (c as AICar).world_pos()
		var k := Vector2i(floori(p.x / GRID), floori(p.z / GRID))
		if not _grid.has(k):
			_grid[k] = []
		(_grid[k] as Array).append(c)


func nearby_obstacles(pos: Vector3, radius: float) -> Array:
	_rebuild_grid()
	var res: Array = []
	var r2 := radius * radius
	var c0 := Vector2i(floori((pos.x - radius) / GRID), floori((pos.z - radius) / GRID))
	var c1 := Vector2i(floori((pos.x + radius) / GRID), floori((pos.z + radius) / GRID))
	for gx in range(c0.x, c1.x + 1):
		for gz in range(c0.y, c1.y + 1):
			for c in _grid.get(Vector2i(gx, gz), []):
				var cc: AICar = c
				if cc.world_pos().distance_squared_to(pos) < r2:
					res.append(cc)
	if trams:
		for b in trams.section_bodies():
			if (b as Node3D).global_position.distance_squared_to(pos) < r2:
				res.append(b)
	return res


# --- Kreuzungsregister ---------------------------------------------------------------------------
func register(node_id: int, car: AICar) -> void:
	if not jreg.has(node_id):
		jreg[node_id] = []
	var lst: Array = jreg[node_id]
	if not lst.has(car):
		lst.append(car)


func unregister(node_id: int, car: AICar) -> void:
	if jreg.has(node_id):
		(jreg[node_id] as Array).erase(car)
		if (jreg[node_id] as Array).is_empty():
			jreg.erase(node_id)


## Spieler an Kreuzung node_id: {near, inside, eta, ang, lvl, a, b} (a->b: voraussichtlicher Weg) oder {}
func player_at(node_id: int) -> Dictionary:
	var f := Engine.get_physics_frames()
	if f != _player_frame:
		_player_frame = f
		_player_cache.clear()
	if _player_cache.has(node_id):
		return _player_cache[node_id]
	var res := {}
	if player != null and player is RigidBody3D and not ignore_player:
		var nd: Dictionary = nodes[node_id]
		var np := Vector2(float(nd["pos"][0]), float(nd["pos"][2]))
		var pp := Vector2(player.global_position.x, player.global_position.z)
		var v3: Vector3 = (player as RigidBody3D).linear_velocity
		var v := Vector2(v3.x, v3.z)
		var d := pp.distance_to(np)
		var jr: float = nd["jr"]
		if d < jr + 45.0:
			var inside := d < jr + 1.0
			var toward := v.dot(np - pp) > 0.0
			if inside or (toward and v.length() > 1.0):
				var ang := atan2(v.y, v.x) if v.length() > 0.5 else 0.0
				var lvl := 2
				var best := 0.7
				for a in nd["app"]:
					var dd := absf(wrapf(float(a[2]) - ang, -PI, PI))
					if dd < best:
						best = dd
						lvl = LVL[int(a[3])]
				var dir := v.normalized() if v.length() > 0.5 else Vector2(cos(ang), sin(ang))
				var eta := maxf(d - jr, 0.0) / maxf(v.length(), 0.5)
				res = {"inside": inside, "eta": 0.0 if inside else eta, "ang": ang, "lvl": lvl,
					"a": pp, "b": pp + dir * (d + jr + 6.0), "speed": v.length()}
	_player_cache[node_id] = res
	return res


func set_night(n: float) -> void:
	night = n
	# Altbestand (geteilte Leuchtmaterialien): nur noch für Fahrzeuge ohne eigenes Licht-Material
	for nm in CarModel.shared_emit:
		var v := 0.0
		match nm:
			"HeadlightEmit": v = 3.0 * n
			"TaillightEmit": v = 1.0 * n
			"BrakeLightEmit": v = 0.5 * n
		for m in CarModel.shared_emit[nm]:
			(m as StandardMaterial3D).emission_energy_multiplier = v
	if CarModel.ai_emit.has("InteriorEmit"):
		(CarModel.ai_emit["InteriorEmit"] as StandardMaterial3D).emission_energy_multiplier = 1.8 * n


# --- Busse ---------------------------------------------------------------------------------------
func _load_bus_routes() -> void:
	var p := DataPaths.file("bus_routes.json")
	if not FileAccess.file_exists(p):
		return
	var j = JSON.parse_string(FileAccess.get_file_as_string(p))
	if not (j is Dictionary):
		return
	for r in j.get("routes", []):
		var pts := PackedVector2Array()
		for q in r["pts"]:
			pts.append(Vector2(float(q[0]), float(q[1])))
		if pts.size() < 2:
			continue
		var cum := PackedFloat32Array()
		cum.append(0.0)
		for i in range(1, pts.size()):
			cum.append(cum[i - 1] + pts[i].distance_to(pts[i - 1]))
		var ref := String(r.get("ref", "")).strip_edges()
		if ref == "":
			continue                 # ohne Liniennummer (z. B. Stadtrundfahrt mit Doppeldeckern): nicht als Linienbus
		var to := String(r.get("to", "")).strip_edges()
		var nm := String(r.get("name", ""))
		if to == "":
			# Ziel fehlt in OSM: aus dem Namen ("Bus 209: Pirna ZOB/Bahnhof => Ottendorf Bahre")
			for sep in ["=>", "->", "→", " - "]:
				if nm.contains(sep):
					to = nm.get_slice(sep, nm.count(sep)).strip_edges()
					break
		var ri := bus_routes.size()
		bus_routes.append({"ref": ref, "to": to, "name": nm,
			"pts": pts, "cum": cum, "stops": r.get("stops", []), "dvb": String(r.get("operator", "")).contains("DVB")})
		# Zellindex für die Suche nach Linien nahe dem Spieler
		var s := 0.0
		var L := cum[cum.size() - 1]
		while s < L:
			var q := route_point(ri, s)
			var ck := Vector2i(floori(q.x / 200.0), floori(q.y / 200.0))
			if not _bus_cells.has(ck):
				_bus_cells[ck] = []
			_bus_cells[ck].append([ri, s])
			s += 60.0
	print("Traffic: %d Buslinien geladen" % bus_routes.size())


## Punkt auf Linie ri bei Bogenlänge s
func route_point(ri: int, s: float) -> Vector2:
	var r: Dictionary = bus_routes[ri]
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
	var seg := maxf(cum[hi] - cum[lo], 0.001)
	return pts[lo].lerp(pts[hi], (s - cum[lo]) / seg)


## Bogenlänge der Projektion von p auf Linie ri im Fenster [s0, s1]
func route_project(ri: int, p: Vector2, s0: float, s1: float) -> Array:
	var r: Dictionary = bus_routes[ri]
	var pts: PackedVector2Array = r["pts"]
	var cum: PackedFloat32Array = r["cum"]
	var best_d := INF
	var best_s := s0
	for i in pts.size() - 1:
		if cum[i + 1] < s0 or cum[i] > s1:
			continue
		var a := pts[i]
		var b := pts[i + 1]
		var ab := b - a
		var t := clampf((p - a).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
		var q := a + ab * t
		var d := q.distance_to(p)
		if d < best_d:
			best_d = d
			best_s = cum[i] + (cum[i + 1] - cum[i]) * t
	return [best_s, best_d]


func _try_spawn_bus(ppos: Vector3) -> void:
	if not ResourceLoader.exists(CarModel.DIR + "bus_solo.glb"):
		return
	var pc := Vector2i(floori(ppos.x / 200.0), floori(ppos.z / 200.0))
	var cand: Array = []
	for dx in range(-2, 3):
		for dz in range(-2, 3):
			for it in _bus_cells.get(pc + Vector2i(dx, dz), []):
				cand.append(it)
	if cand.is_empty():
		return
	for attempt in 10:
		var it: Array = cand[rng.randi() % cand.size()]
		var ri: int = it[0]
		var s: float = float(it[1]) + rng.randf_range(0.0, 60.0)
		var q := route_point(ri, s)
		var q2 := route_point(ri, s + 6.0)
		var dir2 := (q2 - q).normalized()
		# passende Graphkante in Linienrichtung suchen
		var hit := _edge_near(q, dir2, 6.0)
		if hit.is_empty():
			continue
		var pts := edge_points(hit[0], hit[1])
		var p := _point_at(pts, hit[2])
		var pos := Vector3(p.x, p.y, p.z)
		if not _spawn_ok(pos, ppos, 22.0):
			continue
		var art := ResourceLoader.exists(CarModel.DIR + "bus_articulated.glb") and rng.randf() < 0.45
		var bus := BusCar.new()
		add_child(bus)
		bus.setup_bus(self, "bus_articulated.glb" if art else "bus_solo.glb", ri, s, hit[0], hit[1], hit[2])
		cars.append(bus)
		stats["bus_spawn"] = int(stats["bus_spawn"]) + 1
		return


## Nächste befahrbare Kante zu p mit Richtung dirv: [ei, dir, s auf der Kante] oder []
func _edge_near(p: Vector2, dirv: Vector2, maxd: float) -> Array:
	var ck := Vector2i(floori(p.x / 100.0), floori(p.y / 100.0))
	var best := []
	var best_d := maxd
	for dx in range(-1, 2):
		for dz in range(-1, 2):
			for ei in edge_cells.get(ck + Vector2i(dx, dz), []):
				var e: Dictionary = edges[ei]
				var pts: Array = e["pts"]
				var acc := 0.0
				for i in pts.size() - 1:
					var a := Vector2(pts[i][0], pts[i][1])
					var b := Vector2(pts[i + 1][0], pts[i + 1][1])
					var ab := b - a
					var l := ab.length()
					if l < 0.01:
						continue
					var t := clampf((p - a).dot(ab) / (l * l), 0.0, 1.0)
					var d := (a + ab * t).distance_to(p)
					if d < best_d:
						var dd := ab.normalized().dot(dirv)
						var ow := int(e["oneway"])
						if dd > 0.6 and ow >= 0:
							best_d = d
							best = [ei, 1, acc + l * t]
						elif dd < -0.6 and ow <= 0:
							best_d = d
							best = [ei, -1, float(e["len"]) - (acc + l * t)]
					acc += l
	return best
