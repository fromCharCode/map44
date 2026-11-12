class_name BusCar
extends AICar
## Linienbus: folgt einer echten OSM-Buslinie (godot/data/bus_routes.json) über den Straßengraphen, hält an den
## Haltestellen (Türen auf/zu), zeigt Linie und Ziel. Gelenkbus: Nachläufer folgt kinematisch (Deichselmodell).

const DWELL_MIN := 8.0
const DWELL_MAX := 15.0

var line := -1                 # Index in traffic.bus_routes
var line_s := 0.0              # Bogenlänge der Busmitte auf der Linie
var route_line_s := 0.0        # Bogenlänge am Routenende (cur_node)
var stops: Array = []
var next_stop := 0
var at_stop := false
var dwell_t := 0.0
var door_open := 0.0           # 0 zu .. 1 offen
var doors: Array = []          # [Node3D, Transform3D zu, Seite]
var rear: Node3D
var rear_yaw := 0.0            # Knickwinkel (rad)
var rear_len := 5.6            # Gelenk -> Hinterachse des Nachläufers
var joint_z := 2.4             # Gelenk hinter dem Ursprung (lokales +Z)
var bellows: Node3D
var labels: Array = []


func setup_bus(t: Traffic, model: String, ri: int, s_line: float, ei: int, dir: int, s_edge: float) -> void:
	is_bus = true
	line = ri
	line_s = s_line
	route_line_s = s_line
	var r: Dictionary = t.bus_routes[ri]
	stops = r["stops"]
	next_stop = 0
	while next_stop < stops.size() and float(stops[next_stop][0]) < s_line + 20.0:
		next_stop += 1
	setup(t, model, Color(0.97, 0.76, 0.03), ei, dir, s_edge)
	accel = 1.25
	_find_parts()
	_make_labels(String(r["ref"]), String(r["to"]))


var _man := {}
var rear_shape: CollisionShape3D
var _rear_shape_xf := Transform3D.IDENTITY
var hold_t := 0.0


func _configure() -> void:
	_man = _manifest()
	if _man.is_empty():
		return
	length = float(_man.get("length", length))
	var bmin: Array = _man.get("bbox_min", [-1.3, 0.0, -length * 0.5])
	var bmax: Array = _man.get("bbox_max", [1.3, 3.0, length * 0.5])
	front_ext = -float(bmin[2])
	rear_ext = float(bmax[2])
	width = float(_man.get("width", 2.55))
	var ax: Dictionary = _man.get("axle_z", {})
	axle_f = -float(ax.get("front", -2.92))
	axle_r = float(ax.get("middle", ax.get("rear", 2.92)))
	if _man.has("joint_to_rear_axle"):
		rear_len = float(_man["joint_to_rear_axle"])
	if _man.has("joint_z"):
		joint_z = float(_man["joint_z"])
	_box_size = Vector3(width - 0.1, float(_man.get("height", 3.05)) - 0.45, length)


func _make_shapes() -> void:
	if not _man.has("joint_z"):
		super._make_shapes()
		return
	# Gelenkbus: Vorderwagen fest, Nachläufer-Box knickt im Gelenk mit
	var h := _box_size.y
	var front_len := joint_z + front_ext
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(_box_size.x, h, front_len)
	cs.shape = bs
	cs.position = Vector3(0, 0.35 + h * 0.5, (joint_z - front_ext) * 0.5)
	add_child(cs)
	var rl := rear_ext - joint_z
	rear_shape = CollisionShape3D.new()
	var rb := BoxShape3D.new()
	rb.size = Vector3(_box_size.x, h, rl - 0.2)
	rear_shape.shape = rb
	_rear_shape_xf = Transform3D(Basis(), Vector3(0, 0.35 + h * 0.5, rl * 0.5 + 0.1))
	rear_shape.transform = Transform3D(Basis(), Vector3(0, 0, joint_z)) * _rear_shape_xf
	add_child(rear_shape)


func player_impact(_dv: Vector3, _w_y: float) -> void:
	# 11 t: der Bus bleibt stehen (kein Wrack), Warnblinker, kurze Pause
	hold_t = 5.0
	speed = 0.0


func _cruise_for(e: Dictionary) -> float:
	var limit := float(e["speed"]) / 3.6
	if String(e["cls"]) == "service" or bool(e.get("bus", false)):
		limit = maxf(limit, 30.0 / 3.6)          # Busspuren/-schleusen sind oft als service mit 15 km/h erfasst
	return clampf(limit * 0.92, 3.5, 13.4)


func _find_parts() -> void:
	var stack: Array = [model_root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		var nm := String(n.name)
		if nm.begins_with("Door_") and n is Node3D:
			var side := 1.0 if nm.ends_with("_R") else -1.0
			var off := Vector3(0.1, 0.0, -0.64 if nm.ends_with("_R") else 0.64)
			for dd in _man.get("doors", []):
				var lv: Dictionary = dd.get("leaves", {})
				if lv.has(nm):
					var oo: Array = lv[nm].get("open_offset", [off.x, off.y, off.z])
					off = Vector3(float(oo[0]), float(oo[1]), float(oo[2]))
			doors.append([n, (n as Node3D).transform, side, off])
		elif nm == "Rear" and n is Node3D:
			rear = n
			joint_z = (n as Node3D).position.z
		elif nm == "Bellows" and n is Node3D:
			bellows = n
	var man := _manifest()
	if man.has("rear_axle_from_joint"):
		rear_len = float(man["rear_axle_from_joint"])


func _manifest() -> Dictionary:
	var p := CarModel.DIR + "MANIFEST.json"
	if not FileAccess.file_exists(p):
		return {}
	var j = JSON.parse_string(FileAccess.get_file_as_string(p))
	if j is Dictionary and j.has(model_file) and j[model_file] is Dictionary:
		return j[model_file]
	return {}


func _make_labels(ref: String, to: String) -> void:
	## LED-Zielanzeigen (LedSign): vorn und an der Seite Nummer + Ziel, hinten nur die Nummer. Die Texte schweben
	## 2 cm vor der Anzeigefläche (vorn zusätzlich um die Wölbung "bulge" aus dem Manifest).
	var dest := LedSign.clean_dest(to)
	if ref == "" and dest == "":
		return
	var disp: Array = _man.get("destination_displays", [])
	if disp.is_empty():
		disp = [{"name": "front", "center": [0.0, 2.55, -front_ext - 0.03], "width": 1.6, "height": 0.25, "normal": [0, 0, -1]}]
	for dsp in disp:
		var nm := String(dsp.get("name", ""))
		var c: Array = dsp.get("center_local", dsp.get("center", [0, 2.5, 0]))
		var nrm: Array = dsp.get("normal", [0, 0, -1])
		var nv := Vector3(float(nrm[0]), float(nrm[1]), float(nrm[2])).normalized()
		var basis := Basis(Vector3.UP, atan2(nv.x, nv.z))
		var center := Vector3(float(c[0]), float(c[1]), float(c[2])) + nv * (0.02 + float(dsp.get("bulge", 0.0)))
		var parent: Node3D = model_root
		var pn := String(dsp.get("parent", ""))
		if pn != "":
			var pnode := model_root.find_child(pn, true, false)
			if pnode is Node3D:
				parent = pnode
		labels.append_array(LedSign.make(parent, ref, dest, basis, center, float(dsp.get("width", 1.5)),
			float(dsp.get("height", 0.25)), nm == "rear"))


# --- Linienwahl an Knoten ------------------------------------------------------------------------
func _choose_next() -> Array:
	if line < 0:
		return super._choose_next()
	var opts: Array = traffic.out_edges.get(cur_node, [])
	var nd: Dictionary = traffic.nodes[cur_node]
	var np := Vector2(float(nd["pos"][0]), float(nd["pos"][2]))
	var best: Array = []
	var best_d := 14.0
	for o in opts:
		var ei: int = o[0]
		if ei == cur_edge and opts.size() > 1:
			continue
		var e: Dictionary = traffic.edges[ei]
		var pts := traffic.edge_points(ei, int(o[1]))
		var q := _along(pts, minf(14.0, float(e["len"])))
		var pr := traffic.route_project(line, q, route_line_s - 5.0, route_line_s + 60.0)
		if float(pr[1]) < best_d:
			best_d = float(pr[1])
			best = o
	if best.is_empty():
		line = -1                 # Linie verloren: als normales Fahrzeug weiter
		return super._choose_next()
	return best


func _on_edge_added(e: Dictionary) -> void:
	if line < 0:
		return
	var end := route[route.size() - 1] as Vector3
	var pr := traffic.route_project(line, Vector2(end.x, end.z), route_line_s - 5.0, route_line_s + float(e["len"]) + 40.0)
	route_line_s = float(pr[0])


# --- Haltestellen ---------------------------------------------------------------------------------
func _special_limit(delta: float) -> float:
	if hold_t > 0.0:
		hold_t -= delta
		_ind = 2
		return 0.0
	if line < 0:
		_animate_doors(delta, false)
		return INF
	var pr := traffic.route_project(line, Vector2(pos.x, pos.z), line_s - 6.0, line_s + 30.0)
	if float(pr[1]) < 12.0:
		line_s = float(pr[0])
	var cap := INF
	if at_stop:
		dwell_t -= delta
		var open := dwell_t > 1.2
		_animate_doors(delta, open)
		if dwell_t <= 0.0 and door_open < 0.02:
			at_stop = false
			next_stop += 1
		return 0.0
	_animate_doors(delta, false)
	if next_stop < stops.size():
		var st: Array = stops[next_stop]
		# Fahrzeugfront an den Haltestellenmast
		var ds := float(st[0]) - (line_s + length * 0.5) + 1.0
		if ds < -6.0:
			next_stop += 1
		elif ds < 70.0:
			cap = 0.0 if ds < 0.8 else sqrt(2.0 * 1.6 * maxf(ds - 0.8, 0.0))
			if ds < 1.5 and speed < 0.35:
				at_stop = true
				dwell_t = traffic.rng.randf_range(DWELL_MIN, DWELL_MAX)
	return cap


func _animate_doors(delta: float, open: bool) -> void:
	var target := 1.0 if open else 0.0
	var prev := door_open
	door_open = move_toward(door_open, target, delta / 1.6)
	if is_equal_approx(prev, door_open):
		return
	var k1 := clampf(door_open / 0.3, 0.0, 1.0)
	var k2 := clampf((door_open - 0.3) / 0.7, 0.0, 1.0)
	for d in doors:
		var n: Node3D = d[0]
		var xf0: Transform3D = d[1]
		var off: Vector3 = d[3]
		n.transform = xf0.translated(Vector3(off.x * k1, off.y * k1, off.z * k2))


func _drive(delta: float) -> void:
	var h0 := heading
	super._drive(delta)
	if rear == null or delta <= 0.0 or wrecked:
		return
	# Nachläufer (Anhängermodell): Knickwinkel phi = Gier hinten - Gier vorn,
	# Gierrate hinten = -(v/L) sin(phi) - (h * Gierrate vorn / L) cos(phi), h = Gelenk hinter dem Ursprung
	var yr := wrapf(heading - h0, -PI, PI) / delta
	var phi := rear_yaw
	var thr_dot := -(speed / maxf(rear_len, 1.0)) * sin(phi) - (joint_z * yr / maxf(rear_len, 1.0)) * cos(phi)
	rear_yaw = clampf(phi + (thr_dot - yr) * delta, -0.8, 0.8)
	rear.transform.basis = Basis(Vector3.UP, rear_yaw)
	if bellows:
		bellows.transform.basis = Basis(Vector3.UP, rear_yaw * 0.5)
	if rear_shape:
		rear_shape.transform = Transform3D(Basis(Vector3.UP, rear_yaw), Vector3(0, 0, joint_z)) * _rear_shape_xf
