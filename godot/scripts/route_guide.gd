class_name RouteGuide
extends Node3D
## Routenspur: zeichnet den schnellsten Weg zum aktuellen Fahrziel (TaxiGame.target) als durchscheinendes
## hellblaues Band auf den Fahrstreifen. Wegsuche auf dem Straßengraphen des Verkehrs (Traffic.nodes/edges,
## Einbahnstraßen beachtet, Kosten = Fahrzeit). Liegt das Ziel außerhalb der geladenen Kacheln, führt die Spur
## zum erreichbaren Punkt, der dem Ziel am nächsten ist, und wird beim Nachladen neu berechnet.
## Umschalten: F7 oder Pausenmenü; die Einstellung wird gespeichert (GameSettings.route_lane).

const WIDTH := 2.3            # Bandbreite (m)
const LIFT := 0.07            # Höhe über der Fahrbahn (m)
const SHOW_AHEAD := 700.0     # gezeichnete Länge ab dem Wagen (m)
const REPLAN_T := 2.5         # s zwischen Neuberechnungen
const OFF_ROUTE := 14.0       # m Abstand zur Spur, ab dem sofort neu geplant wird

var player: Node3D
var traffic: Traffic
var taxi: TaxiGame
var world                      # height_at(x, z)
var enabled := true
var fixed_target := Vector3.ZERO   # Prüfmodus (--routeguide=x,z): festes Ziel statt Taxiauftrag
var path: PackedVector3Array = PackedVector3Array()    # Spurpunkte ab Start (Fahrstreifenmitte)
var path_len := 0.0

var _astar := AStar3D.new()
var _n_nodes := 0
var _n_edges := 0
var _best := {}               # Vector2i(a, b) -> [Fahrzeit, Kante, Richtung] (schnellste Kante je Knotenpaar)
var _t := 0.0
var _mesh_t := 0.0
var _target := Vector3.ZERO
var _mi: MeshInstance3D
var _mat: StandardMaterial3D
var _seg := 0                 # Abschnitt der Spur, auf dem der Wagen zuletzt war


func setup(p: Node3D, t: Traffic, tx: TaxiGame, w) -> void:
	player = p
	traffic = t
	taxi = tx
	world = w
	enabled = GameSettings.route_lane
	_mat = StandardMaterial3D.new()
	_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_mat.albedo_color = Color(0.36, 0.76, 1.0, 0.36)
	_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_mat.render_priority = 2
	_mi = MeshInstance3D.new()
	_mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_mi.material_override = _mat
	_mi.top_level = true
	add_child(_mi)


func toggle() -> void:
	enabled = not enabled
	GameSettings.route_lane = enabled
	GameSettings.save_settings()
	_t = 0.0
	if not enabled:
		_clear()


func _unhandled_key_input(ev: InputEvent) -> void:
	var k := ev as InputEventKey
	if k and k.pressed and not k.echo and k.physical_keycode == KEY_F7:
		toggle()


func _clear() -> void:
	path = PackedVector3Array()
	path_len = 0.0
	_mi.mesh = null


func _goal() -> Vector3:
	if fixed_target != Vector3.ZERO:
		return fixed_target
	return taxi.target() if taxi and taxi.enabled else Vector3.ZERO


func _process(delta: float) -> void:
	if not enabled or player == null or traffic == null:
		return
	var tg := _goal()
	if tg == Vector3.ZERO:
		if not path.is_empty():
			_clear()
		_target = tg
		return
	_t -= delta
	_mesh_t -= delta
	var pp := player.global_position
	var replan := _t <= 0.0 or tg.distance_to(_target) > 1.0
	if not replan and not path.is_empty() and _mesh_t <= 0.0:
		if _project(pp)[1] > OFF_ROUTE:
			replan = true
	if replan:
		_target = tg
		_t = REPLAN_T
		_plan(pp, tg)
		_mesh_t = 0.0
	if _mesh_t <= 0.0:
		_mesh_t = 0.2
		_build_mesh(pp)


# --- Graph -------------------------------------------------------------------------------------------------

func _edge_time(e: Dictionary) -> float:
	var v := clampf(float(e.get("speed", 50.0)), 10.0, 130.0) / 3.6
	var c := float(e["len"]) / v
	var cls := String(e.get("cls", ""))
	if cls == "service" or cls == "living_street":
		c *= 1.6          # Höfe und Spielstraßen nur, wenn es sich lohnt
	return c + 2.0        # je Kante: Abbiegen/Kreuzung kostet Zeit


func _sync_graph() -> void:
	var nodes: Array = traffic.nodes
	var edges: Array = traffic.edges
	if nodes.size() == _n_nodes and edges.size() == _n_edges:
		return
	for i in range(_n_nodes, nodes.size()):
		var p: Array = nodes[i]["pos"]
		_astar.add_point(i, Vector3(float(p[0]), 0.0, float(p[2])))
	_n_nodes = nodes.size()
	for ei in range(_n_edges, edges.size()):
		var e: Dictionary = edges[ei]
		if String(e.get("cls", "")) in ["busway", "track"]:
			continue
		var a := int(e["a"])
		var b := int(e["b"])
		if a == b:
			continue
		var ow := int(e["oneway"])
		var c := _edge_time(e)
		if ow >= 0:
			_link(a, b, c, ei, 1)
		if ow <= 0:
			_link(b, a, c, ei, -1)
	_n_edges = edges.size()


func _link(a: int, b: int, c: float, ei: int, dir: int) -> void:
	var k := Vector2i(a, b)
	if _best.has(k) and float(_best[k][0]) <= c:
		return
	_best[k] = [c, ei, dir]
	if not _astar.are_points_connected(a, b, false):
		_astar.connect_points(a, b, false)


## nächste Kante zu p: [Kante, Bogenlänge ab Kantenanfang (Punkt a), Abstand]
func _nearest_edge(p: Vector2, maxd: float) -> Array:
	var ck := Vector2i(floori(p.x / 100.0), floori(p.y / 100.0))
	var best := []
	var best_d := maxd
	var rc := int(ceil(maxd / 100.0)) + 1      # Kanten sind nach ihrem Mittelpunkt einsortiert
	for dx in range(-rc, rc + 1):
		for dz in range(-rc, rc + 1):
			for ei in traffic.edge_cells.get(ck + Vector2i(dx, dz), []):
				var e: Dictionary = traffic.edges[ei]
				if String(e.get("cls", "")) in ["busway", "track"]:
					continue
				var pts: Array = e["pts"]
				var acc := 0.0
				for i in pts.size() - 1:
					var a := Vector2(pts[i][0], pts[i][1])
					var ab := Vector2(pts[i + 1][0], pts[i + 1][1]) - a
					var l := ab.length()
					if l < 0.01:
						continue
					var t := clampf((p - a).dot(ab) / (l * l), 0.0, 1.0)
					var d := (a + ab * t).distance_to(p)
					if d < best_d:
						best_d = d
						best = [ei, acc + l * t, d]
					acc += l
	return best


func _path_time(ids: PackedInt64Array) -> float:
	var c := 0.0
	for i in ids.size() - 1:
		c += float(_best[Vector2i(ids[i], ids[i + 1])][0])
	return c


func _plan(pp: Vector3, tg: Vector3) -> void:
	_sync_graph()
	var se := _nearest_edge(Vector2(pp.x, pp.z), 250.0)
	if se.is_empty():
		_clear()
		return
	var e0: Dictionary = traffic.edges[se[0]]
	var te := _nearest_edge(Vector2(tg.x, tg.z), 150.0)
	# Ziel außerhalb des geladenen Netzes: nächster Knoten zum Ziel
	var goal_nodes: Array = []      # [Knoten, Restzeit, Kante, Richtung, Ziel-Bogenlänge]
	if te.is_empty():
		var gid := _astar.get_closest_point(Vector3(tg.x, 0.0, tg.z))
		if gid < 0:
			_clear()
			return
		goal_nodes.append([gid, 0.0, -1, 0, 0.0])
	else:
		var e1: Dictionary = traffic.edges[te[0]]
		var l1 := maxf(float(e1["len"]), 0.1)
		var c1 := _edge_time(e1)
		var ow1 := int(e1["oneway"])
		if ow1 >= 0:
			goal_nodes.append([int(e1["a"]), c1 * float(te[1]) / l1, te[0], 1, float(te[1])])
		if ow1 <= 0:
			goal_nodes.append([int(e1["b"]), c1 * (1.0 - float(te[1]) / l1), te[0], -1, l1 - float(te[1])])
	# Start: in Fahrtrichtung des Wagens weiter (Wenden kostet Zeit)
	var fwd := -player.global_transform.basis.z
	var tan := _edge_tangent(e0, float(se[1]))
	var facing := 1 if Vector2(fwd.x, fwd.z).dot(tan) >= 0.0 else -1
	var l0 := maxf(float(e0["len"]), 0.1)
	var c0 := _edge_time(e0)
	var ow0 := int(e0["oneway"])
	var starts: Array = []          # [Knoten, Zeit bis dort, Richtung]
	if ow0 >= 0:
		starts.append([int(e0["b"]), c0 * (1.0 - float(se[1]) / l0) + (0.0 if facing == 1 else 12.0), 1])
	if ow0 <= 0:
		starts.append([int(e0["a"]), c0 * float(se[1]) / l0 + (0.0 if facing == -1 else 12.0), -1])
	var best_c := INF
	var best_ids := PackedInt64Array()
	var best_s: Array = []
	var best_g: Array = []
	# Start und Ziel auf derselben Kante, Ziel liegt voraus
	if not te.is_empty() and int(te[0]) == int(se[0]):
		for g in goal_nodes:
			var d := int(g[3])
			var ahead := (float(te[1]) - float(se[1])) * float(d)
			if ahead > 0.0 and (d == facing or ahead < 30.0):
				var pts0 := _edge_part(int(se[0]), d, float(se[1]) if d == 1 else l0 - float(se[1]), float(g[4]))
				_set_path(pts0)
				return
	for s in starts:
		for g in goal_nodes:
			var ids := _astar.get_id_path(int(s[0]), int(g[0]), true)
			if ids.is_empty():
				continue
			var c := float(s[1]) + _path_time(ids) + float(g[1])
			if ids[ids.size() - 1] != int(g[0]):
				c += 600.0          # nur Teilweg gefunden
			if c < best_c:
				best_c = c
				best_ids = ids
				best_s = s
				best_g = g
	if best_s.is_empty():
		_clear()
		return
	var out := PackedVector3Array()
	var d0 := int(best_s[2])
	out.append_array(_edge_part(int(se[0]), d0, float(se[1]) if d0 == 1 else l0 - float(se[1]), INF))
	for i in best_ids.size() - 1:
		var b: Array = _best[Vector2i(best_ids[i], best_ids[i + 1])]
		_join(out, _edge_part(int(b[1]), int(b[2]), 0.0, INF))
	if int(best_g[2]) >= 0 and best_ids[best_ids.size() - 1] == int(best_g[0]):
		_join(out, _edge_part(int(best_g[2]), int(best_g[3]), 0.0, float(best_g[4])))
	_set_path(out)
	if OS.has_environment("DRESDEN_ROUTEGUIDE"):
		print("ROUTEGUIDE %d Knoten, %d Punkte, %.0f m, %.0f s" % [best_ids.size(), path.size(), path_len, best_c])


func _edge_tangent(e: Dictionary, s: float) -> Vector2:
	var pts: Array = e["pts"]
	var acc := 0.0
	for i in pts.size() - 1:
		var ab := Vector2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
		var l := ab.length()
		if acc + l >= s and l > 0.01:
			return ab / l
		acc += l
	var n := pts.size()
	return Vector2(pts[n - 1][0] - pts[n - 2][0], pts[n - 1][1] - pts[n - 2][1]).normalized()


## Fahrstreifenpunkte der Kante in Fahrtrichtung zwischen den Bogenlängen s0 und s1 (in Fahrtrichtung gemessen)
func _edge_part(ei: int, dir: int, s0: float, s1: float) -> PackedVector3Array:
	var pts: Array = traffic.edge_points(ei, dir)
	var out := PackedVector3Array()
	var acc := 0.0
	for i in pts.size() - 1:
		var a: Vector3 = pts[i]
		var b: Vector3 = pts[i + 1]
		var l := Vector2(b.x - a.x, b.z - a.z).length()
		if l < 0.01:
			continue
		var lo := maxf(s0, acc)
		var hi := minf(s1, acc + l)
		if hi > lo:
			if out.is_empty():
				out.append(a.lerp(b, (lo - acc) / l))
			out.append(a.lerp(b, (hi - acc) / l))
		acc += l
		if acc >= s1:
			break
	return out


## hängt b an a an; an Kreuzungen wird die Ecke abgerundet (die Fahrstreifen zweier Kanten treffen sich nicht)
func _join(a: PackedVector3Array, b: PackedVector3Array) -> void:
	if b.is_empty():
		return
	if a.size() >= 2 and b.size() >= 2:
		var p1 := a[a.size() - 1]
		var p2 := b[0]
		if p1.distance_to(p2) > 0.5:
			# Bézierbogen zwischen den Enden, Tangenten aus den Nachbarpunkten; Enden um bis zu 6 m zurücknehmen
			var t1 := (p1 - a[a.size() - 2]).normalized()
			var t2 := (b[1] - p2).normalized()
			var k := minf(p1.distance_to(p2) * 0.45, 9.0)
			for i in range(1, 6):
				var u := float(i) / 6.0
				a.append(p1.bezier_interpolate(p1 + t1 * k, p2 - t2 * k, p2, u))
	a.append_array(b)


func _set_path(pts: PackedVector3Array) -> void:
	# Punkte auf höchstens 4 m verdichten und auf die Fahrbahnhöhe setzen
	var out := PackedVector3Array()
	path_len = 0.0
	for i in pts.size():
		if i > 0:
			var a := pts[i - 1]
			var b := pts[i]
			var l := Vector2(b.x - a.x, b.z - a.z).length()
			var n := int(ceil(l / 4.0))
			for j in range(1, n):
				out.append(_ground(a.lerp(b, float(j) / float(n))))
			path_len += l
		out.append(_ground(pts[i]))
	path = out
	_seg = 0


func _ground(p: Vector3) -> Vector3:
	var gy: float = world.height_at(p.x, p.z) if world else p.y
	var y := p.y
	if not (p.y < gy - 2.0):          # nicht im Tunnel: Gelände oder Brückendeck, je nachdem was höher liegt
		y = maxf(gy, p.y)
	return Vector3(p.x, y + LIFT, p.z)


## [Abschnitt, Abstand] des Wagens zur Spur (Suche ab dem letzten Abschnitt)
func _project(pp: Vector3) -> Array:
	var best_i := _seg
	var best_d := INF
	var p := Vector2(pp.x, pp.z)
	var i0 := maxi(_seg - 3, 0)
	var i1 := mini(_seg + 40, path.size() - 2)
	for i in range(i0, i1 + 1):
		var a := Vector2(path[i].x, path[i].z)
		var ab := Vector2(path[i + 1].x, path[i + 1].z) - a
		var l2 := ab.length_squared()
		var t := clampf((p - a).dot(ab) / l2, 0.0, 1.0) if l2 > 0.0001 else 0.0
		var d := (a + ab * t).distance_to(p)
		if d < best_d and absf(path[i].y - pp.y) < 6.0:
			best_d = d
			best_i = i
	return [best_i, best_d]


func _build_mesh(pp: Vector3) -> void:
	if path.size() < 2:
		_mi.mesh = null
		return
	var pr := _project(pp)
	_seg = int(pr[0])
	var verts := PackedVector3Array()
	var cols := PackedColorArray()
	var idx := PackedInt32Array()
	var acc := 0.0
	var i := _seg
	var n := path.size()
	while i < n and acc < SHOW_AHEAD:
		var p := path[i]
		var t: Vector3
		if i == 0:
			t = path[1] - p
		elif i == n - 1:
			t = p - path[i - 1]
		else:
			t = path[i + 1] - path[i - 1]
		t.y = 0.0
		t = t.normalized()
		var r := Vector3(-t.z, 0.0, t.x) * (WIDTH * 0.5)
		# am Wagen und am Ende der Sichtweite weich ausblenden
		var a := clampf((acc - 2.0) / 8.0, 0.0, 1.0) * clampf((SHOW_AHEAD - acc) / 120.0, 0.0, 1.0)
		verts.append(p - r)
		verts.append(p + r)
		cols.append(Color(1, 1, 1, a))
		cols.append(Color(1, 1, 1, a))
		if i + 1 < n:
			acc += p.distance_to(path[i + 1])
		i += 1
	var nv := verts.size() / 2
	if nv < 2:
		_mi.mesh = null
		return
	for k in nv - 1:
		var b := k * 2
		idx.append_array(PackedInt32Array([b, b + 1, b + 2, b + 1, b + 3, b + 2]))
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_INDEX] = idx
	var m := ArrayMesh.new()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	_mi.mesh = m
	_mat.vertex_color_use_as_albedo = true
