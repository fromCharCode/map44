class_name AICar
extends AnimatableBody3D
## Verkehrsteilnehmer: folgt einer Route entlang des Straßengraphen (kinematisch), hält Abstand, beachtet
## Ampeln, Vorfahrt/rechts vor links und Stoppschilder (Kreuzungsdaten aus tools/junctions.py), blinkt,
## bremst sichtbar. Bei einem Zusammenstoß mit dem Spieler wird das Auto zu einem echten Physikkörper
## (Wrack-Modus) und fährt danach – wenn es wieder ordentlich steht – weiter.

enum Move { STRAIGHT, LEFT, RIGHT, UTURN }
const MASS := 1300.0

var traffic: Traffic
var uid := 0
var model_file := "hatchback.glb"
var length := 4.3
var width := 1.8
var is_bus := false
var front_ext := 2.2          # Ursprung -> Frontstoßfänger (m)
var rear_ext := 2.2           # Ursprung -> Heckstoßfänger (m)
var axle_f := 1.4             # Ursprung -> Vorderachse (Neigungsabtastung)
var axle_r := 1.4
var route: Array = []         # Vector3
var route_i := 0              # aktuelles Segment
var markers: Array = []       # Kreuzungsmarken (Dictionary)
var cur_edge := 0
var cur_dir := 1
var cur_node := -1            # Zielknoten der zuletzt angehängten Kante
var last_tangent := Vector2(0, -1)
var heading := 0.0            # Gier: Vorwärtsvektor = (-sin, 0, -cos)
var speed := 0.0
var v_cruise := 11.0
var route_v: Array = []       # Tempolimit (m/s) je Routenpunkt (gilt ab diesem Punkt)
var route_ln: Array = []      # Vector2(Fahrstreifenbreite, Zahl der Streifen links von mir) je Routenpunkt; 0 = einstreifig
# Fahrerprofil (fest je Fahrzeug, siehe _make_driver)
enum Kind { CAR, VAN, TRUCK, BUS }
const LANE_CHANGE := true     # Überholen/Fahrstreifenwechsel auf mehrstreifigen Richtungsfahrbahnen (Schalter)
var kind := Kind.CAR
var drive_fac := 1.0          # Wunschgeschwindigkeit als Faktor aufs Tempolimit (0,80 .. 1,20)
var v_free := 36.0            # Wunschtempo ohne Limit (Autobahn-Richtgeschwindigkeit), m/s
var v_max := 50.0             # Obergrenze des Fahrzeugs bzw. der Fahrzeugart, m/s
var accel := 2.4              # größte Beschleunigung, m/s²
var brake_comf := 2.6         # angenehme Bremsverzögerung, m/s²
var t_gap := 1.5              # Zeitlücke zum Vordermann, s
var s0 := 2.0                 # Abstand im Stand, m
var a_lat := 2.6              # hingenommene Querbeschleunigung in Kurven, m/s²
var react_t := 1.0            # Reaktionszeit beim Anfahren (Ampel, Kolonne), s
var patience := 10.0          # Geduld hinter einem stehenden Hindernis, bis gehupt/umfahren wird, s
var yellow_b := 3.5           # Verzögerung, die der Fahrer bei Gelb noch in Kauf nimmt (klein = fährt eher durch), m/s²
var honker := false           # hupt, wenn er aufgehalten wird
var goal := Vector2.INF       # Fahrtziel (x, z): Abbiegen bevorzugt in diese Richtung
var goal_k := 1.0             # Zielstrebigkeit (0 = fährt ziellos)
# Umfahren eines stehenden Hindernisses (Spieler, Wrack): Versatz nach links, solange _evade_o voraus ist
var _evade := 0.0
var _evade_o: Object = null
var _evade_t := 0.0           # Standzeit während des Umfahrens (Abbruch, wenn es klemmt)
var _back_d := 0.0            # noch zurückzusetzende Strecke vor dem Umfahren (m)
var _honk_t := 0.0
var _honk: AudioStreamPlayer3D
# Folgefahren (Intelligent-Driver-Modell): Vordermann aus dem letzten Denkschritt, dazwischen fortgeschrieben
var _lead_ok := false
var _lead_gap := 0.0
var _lead_v := 0.0
var _acc := 0.0               # aktuelle Längsbeschleunigung (geglättet)
var _still_t := 0.0           # Standzeit
var _go_t := 0.0              # verstrichene Reaktionszeit beim Anfahren
var _stop_sig := false        # stand vor Ampel/in der Kolonne (volle Reaktionszeit), sonst Vorfahrt achten (kurz)
var _v_ahead := INF           # vorausschauende Grenze (Tempolimit, Kurven) aus dem Denkschritt
var _ahead := PackedVector2Array()   # Route voraus, gleichmäßig abgetastet (ab Lotpunkt)
var _ahead_step := 6.0
var _ext_t := 0.0
# Fahrstreifen (nur Richtungsfahrbahnen mit mehreren Streifen): 0 = rechts
var lane_tgt := 0
var lane_shift := 0.0         # tatsächlicher Versatz nach links (m)
var lane_w := 0.0             # Breite des Fahrstreifens, in den gewechselt wurde
var _lane_t := 0.0            # Zeit seit dem letzten Wechsel
var _lane_chk := 0.0
var _lane_must := false       # muss zurück nach rechts (Abbiegen, Streifen endet)
var _lane_zone := 0.0
var _lane_ind := 0            # Blinker für den Spurwechsel
var _lf_gap := INF            # letzte Prüfung: Abstand/Tempo des Vordermanns im Zielstreifen
var _lf_v := INF
var wheels := {}
var wheel_roll := 0.0
var wheel_r := 0.32
var lights: Array = []        # MeshInstance3D mit Instanz-Uniforms (car_lights.gdshader)
var model_root: Node3D
var dead := false
var death := ""               # Grund fürs Entfernen (Statistik)
var pos := Vector3.ZERO
var on_bridge := false
var ghost_t := 0.0
var blocked_t := 0.0
var _chk_t := 0.0
var _turn_acc := 0.0             # Kreisfahrt-Erkennung: Summe der Kursänderung seit _turn_pos
var _turn_pos := Vector3.ZERO
var circles := 0
var _ends_here := false          # Route endet in einer Sackgasse (kein Wenden)
var _chk_pos := Vector3.ZERO
var _limit := ""              # was die Geschwindigkeit zuletzt begrenzt hat ("", "junction", "obstacle")
var _brake := false
var _ind := 0                 # -1 links, 1 rechts, 2 Warnblinker
var _light_t := 0.0
const THINK := 0.1
var _think_t := -1.0
var _since_think := 0.0
var _vt_c := INF
var _limit_c := ""
# Wrack-Modus
var wreck: RigidBody3D
var wreck_t := 0.0
var wrecked := false
var _box_size := Vector3(1.8, 1.3, 4.3)


func setup(t: Traffic, model: String, color: Color, edge: int, dir: int, s: float) -> void:
	traffic = t
	uid = t.next_id()
	model_file = model
	length = Traffic.LENGTHS.get(model, 4.4)
	collision_layer = 4
	collision_mask = 0
	sync_to_physics = sync_phys
	var made := CarModel.make_ai(model, color)
	model_root = made["root"]
	add_child(model_root)
	wheels = made["wheels"]
	lights = made["lights"]
	if made.has("size"):
		_box_size = made["size"]
	else:
		var box_h := 1.3
		if model == "van.glb":
			box_h = 2.2
		elif model.contains("transporter"):
			box_h = 1.9
		elif model.contains("suv"):
			box_h = 1.65
		_box_size = Vector3(1.8, box_h, length)
	width = _box_size.x
	front_ext = length * 0.5
	rear_ext = length * 0.5
	axle_f = length * 0.32
	axle_r = length * 0.32
	_configure()
	_make_shapes()
	_make_driver()
	_think_t = float(uid % 6) * THINK / 6.0
	_start_route(edge, dir, s)


func _configure() -> void:
	pass                           # Busse: Maße aus dem Manifest


func _make_shapes() -> void:
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = _box_size
	cs.shape = bs
	cs.position = Vector3(0, 0.35 + _box_size.y * 0.5, (rear_ext - front_ext) * 0.5)
	add_child(cs)


func _start_route(edge: int, dir: int, s: float) -> void:
	cur_edge = edge
	cur_dir = dir
	var pts := traffic.edge_points(edge, dir)
	var acc := 0.0
	var start_i := 0
	for i in pts.size() - 1:
		var l := Vector2(pts[i + 1].x - pts[i].x, pts[i + 1].z - pts[i].z).length()
		if acc + l >= s:
			start_i = i
			break
		acc += l
	var seg := maxf(Vector2(pts[start_i + 1].x - pts[start_i].x, pts[start_i + 1].z - pts[start_i].z).length(), 0.001)
	var p0 := (pts[start_i] as Vector3).lerp(pts[start_i + 1], clampf((s - acc) / seg, 0.0, 1.0))
	var e: Dictionary = traffic.edges[edge]
	var vl := _cruise_for(e)
	var ln := _lane_info(e)
	route = [p0]
	route_v = [vl]
	route_ln = [ln]
	for i in range(start_i + 1, pts.size()):
		route.append(pts[i])
		route_v.append(vl)
		route_ln.append(ln)
	if route.size() < 2:
		route.append(pts[pts.size() - 1] + Vector3(0.01, 0, 0.01))
		route_v.append(vl)
		route_ln.append(ln)
	cur_node = int(e["b"]) if dir == 1 else int(e["a"])
	_add_marker(edge, dir)
	var d := Vector2(route[1].x - route[0].x, route[1].z - route[0].z)
	last_tangent = d.normalized()
	heading = atan2(-d.x, -d.y)
	pos = p0
	v_cruise = _cruise_for(e)
	speed = v_cruise * (0.7 if v_cruise < 17.0 else 0.9)     # auf Schnellstraßen im Fluss erscheinen
	_apply_transform()
	_extend_route()


func _make_driver() -> void:
	## Feste Eigenart des Fahrers. Wunschgeschwindigkeit als Faktor aufs Limit: 12 % Schleicher (0,80–0,90),
	## 79 % Normalfahrer (um 1,01, Streuung 0,035, begrenzt auf 0,95–1,08), 9 % Raser (1,08–1,20).
	## Das Temperament (aus dem Faktor, mit Streuung) bestimmt Zeitlücke 2,2–1,0 s, Beschleunigung, angenehme
	## Bremsverzögerung 2,0–3,4 m/s² und Querbeschleunigung in Kurven 2,0–3,5 m/s². Transporter, Lkw und Busse
	## sind träger und langsamer.
	var r := traffic.rng
	var mf := model_file.to_lower()
	if is_bus:
		kind = Kind.BUS
	elif mf.contains("truck") or mf.contains("lkw") or mf.contains("lorry"):
		kind = Kind.TRUCK
	elif mf.contains("van") or mf.contains("transporter"):
		kind = Kind.VAN
	else:
		kind = Kind.CAR
	var u := r.randf()
	if u < 0.12:
		drive_fac = r.randf_range(0.80, 0.90)
	elif u < 0.91:
		drive_fac = clampf(r.randfn(1.01, 0.035), 0.95, 1.08)
	else:
		drive_fac = r.randf_range(1.08, 1.20)
	var temper := clampf((drive_fac - 0.85) / 0.3 + r.randf_range(-0.3, 0.3), 0.0, 1.0)
	var brisk := mf.contains("limo")                # Limousine/Elektro-Limousine: eher zügig unterwegs
	if brisk:
		temper = minf(temper + 0.12, 1.0)
		if drive_fac >= 0.95:
			drive_fac = minf(drive_fac + 0.02, 1.20)
	react_t = r.randf_range(0.6, 1.4)
	if r.randf() < 0.05:
		react_t = r.randf_range(2.0, 3.2)             # Träumer: merkt spät, dass es weitergeht
	# Geduld 5–22 s (Eilige kürzer), Gelb: Vorsichtige bremsen noch bei 4,6 m/s², Eilige nur bis 3,0 m/s² (so reicht die Gelbzeit noch bis zur Haltelinie)
	patience = lerpf(22.0, 5.0, temper) * r.randf_range(0.8, 1.25)
	yellow_b = lerpf(4.6, 3.0, temper)
	honker = r.randf() < lerpf(0.15, 0.75, temper)
	goal_k = r.randf_range(0.6, 2.4)
	s0 = r.randf_range(1.8, 2.5)
	t_gap = lerpf(2.2, 1.0, temper)
	brake_comf = lerpf(2.0, 3.4, temper)
	match kind:
		Kind.CAR:
			var small := mf.contains("citycar") or mf.contains("kleinwagen")
			accel = lerpf(1.7, 3.0, temper) * (0.88 if small else 1.0)
			if mf.contains("elektro"):
				accel *= 1.15                              # E-Antrieb: kräftiger Antritt
			elif mf.contains("suv_gross"):
				accel *= 0.95
			a_lat = lerpf(2.0, 3.5, temper)
			v_free = lerpf(110.0, 170.0, temper) / 3.6
			v_max = (150.0 if small else 190.0) / 3.6
			if brisk:
				v_free = minf(v_free + 10.0 / 3.6, v_max)
		Kind.VAN:
			drive_fac = minf(drive_fac, 1.10) * 0.98
			accel = lerpf(1.3, 1.9, temper)
			a_lat = lerpf(2.0, 2.8, temper)
			v_free = lerpf(100.0, 140.0, temper) / 3.6
			v_max = 150.0 / 3.6
			t_gap = minf(t_gap + 0.15, 2.2)
		Kind.TRUCK:
			drive_fac = minf(drive_fac, 1.03)
			accel = lerpf(0.7, 1.1, temper)
			a_lat = lerpf(2.0, 2.4, temper)
			v_free = lerpf(80.0, 89.0, temper) / 3.6     # Lkw-Limit 80 (Tacho-Toleranz)
			v_max = v_free
			t_gap = maxf(t_gap, 1.6)
			brake_comf = minf(brake_comf, 2.6)
		Kind.BUS:
			drive_fac = r.randf_range(0.90, 0.98)
			accel = r.randf_range(1.1, 1.3)
			a_lat = 2.0
			v_free = 80.0 / 3.6
			v_max = v_free
			t_gap = maxf(t_gap, 1.6)
			brake_comf = minf(brake_comf, 2.4)             # stehende Fahrgäste
	v_free = minf(v_free, v_max)


func _cruise_for(e: Dictionary) -> float:
	## Wunschgeschwindigkeit auf Kante e (m/s): Tempolimit × persönlicher Faktor. Autobahn mit 130 in den Daten
	## (= nur Richtgeschwindigkeit): persönliches Wunschtempo v_free. Schmale Gegenverkehrsfahrbahnen langsamer
	## (in den Daten stehen dort oft 100 als Außerorts-Vorgabe). Fahrzeugart begrenzt über v_max.
	var kmh := float(e["speed"])
	var v := kmh / 3.6 * drive_fac
	if kmh >= 129.0 and String(e["cls"]) == "motorway":
		v = v_free
	if int(e["oneway"]) == 0:
		var fw := float(e["width"]) - float(e.get("pl", 0.0)) - float(e.get("pr", 0.0))
		if fw < 4.6:
			v = minf(v, 40.0 / 3.6 * drive_fac)
		elif fw < 5.6:
			v = minf(v, 70.0 / 3.6 * drive_fac)
	return clampf(v, 2.8, v_max)


func _lane_info(e: Dictionary) -> Vector2:
	## Fahrstreifen für Spurwechsel: nur Richtungsfahrbahnen (Einbahn) mit mindestens zwei Streifen. Die Breite
	## entspricht der Markierung (roads.gd: Fahrband gleichmäßig geteilt). Rückgabe (Breite, Streifen links von
	## der Grundspur) oder (0, 0).
	if not LANE_CHANGE or is_bus or int(e["oneway"]) == 0:
		return Vector2.ZERO
	var n := int(e.get("lanes", 1))
	if n < 2 or not (String(e["cls"]) in ["motorway", "trunk", "primary", "secondary", "tertiary"]):
		return Vector2.ZERO
	var lw := (float(e["width"]) - float(e.get("pl", 0.0)) - float(e.get("pr", 0.0))) / float(n)
	var mwl := Traffic.mw_layout(e)
	if mwl.y > 0.0:
		lw = mwl.y                                       # Autobahn: 3,75 m neben dem Standstreifen
	if lw < 2.9:
		return Vector2.ZERO
	return Vector2(lw, float(mini(n - 1, 2)))


func release() -> void:
	## Beim Entfernen: Kreuzungsanmeldungen lösen, Wrack-Körper aufräumen.
	for m in markers:
		traffic.unregister(int(m["node"]), self)
	markers.clear()
	if wreck != null and is_instance_valid(wreck):
		wreck.queue_free()
	wreck = null


# --- Route und Kreuzungsmarken ---------------------------------------------------------------------
func _add_marker(edge: int, dir: int) -> void:
	var nd: Dictionary = traffic.nodes[cur_node]
	if (nd["app"] as Array).is_empty() and traffic.degree(cur_node) < 3 and not nd.get("signal", false):
		return
	var last: Vector3 = route[route.size() - 1]
	markers.append({
		"node": cur_node, "ridx": route.size() - 1, "np": Vector2(last.x, last.z), "in_e": edge, "in_d": dir,
		"app": traffic.approach(cur_node, edge, dir), "ang_in": traffic.entry_angle(edge, dir),
		"jr": float(nd["jr"]), "exit_e": -1, "exit_d": 0, "ang_out": 0.0, "move": Move.STRAIGHT,
		"path": PackedVector2Array(), "entered": false, "passed": false, "eta": 99.0, "d_stop": 99.0,
		"waiting": false, "wait_t": 0.0, "stop_t": 0.0, "stop_done": false, "sig": -1, "uid": uid,
	})


func marker_for(node_id: int) -> Dictionary:
	for m in markers:
		if int(m["node"]) == node_id:
			return m
	return {}


func _set_exit(m: Dictionary, ei: int, dir: int) -> void:
	m["exit_e"] = ei
	m["exit_d"] = dir
	var ang_out := traffic.exit_angle(ei, dir)
	m["ang_out"] = ang_out
	var dlt := wrapf(ang_out - float(m["ang_in"]), -PI, PI)
	if absf(dlt) < 0.55:
		m["move"] = Move.STRAIGHT
	elif absf(dlt) > 2.6:
		m["move"] = Move.UTURN
	elif dlt > 0.0:
		m["move"] = Move.RIGHT      # (x Ost, z Süd: positiver Winkel = im Uhrzeigersinn = rechts)
	else:
		m["move"] = Move.LEFT
	m["path"] = _conflict_path(m, ei, dir)


func _conflict_path(m: Dictionary, ei: int, dir: int) -> PackedVector2Array:
	## Fahrlinie durch die Kreuzung: Haltelinie -> Ausfahrt (quadratische Bézier über den Schnittpunkt der Spuren)
	var app: Array = m["app"]
	var stop_d: float = float(app[6]) if not app.is_empty() else minf(float(m["jr"]) * 0.8, 6.0)
	var pin := traffic.edge_points(int(m["in_e"]), int(m["in_d"]))
	var pout := traffic.edge_points(ei, dir)
	var a := _along_back(pin, stop_d)
	var b := _along(pout, float(m["jr"]) + 1.5)
	var da := Vector2(cos(float(m["ang_in"])), sin(float(m["ang_in"])))
	var db := Vector2(cos(float(m["ang_out"])), sin(float(m["ang_out"])))
	var c := (a + b) * 0.5
	var den := da.cross(db)
	if absf(den) > 0.15:
		var t := (b - a).cross(db) / den
		if t > 0.0 and t < 40.0:
			c = a + da * t
	var path := PackedVector2Array()
	for k in 7:
		var u := float(k) / 6.0
		path.append(a * (1.0 - u) * (1.0 - u) + c * 2.0 * u * (1.0 - u) + b * u * u)
	return path


func _along(pts: Array, s: float) -> Vector2:
	var acc := 0.0
	for i in pts.size() - 1:
		var p: Vector3 = pts[i]
		var q: Vector3 = pts[i + 1]
		var l := Vector2(q.x - p.x, q.z - p.z).length()
		if acc + l >= s and l > 0.001:
			var t := (s - acc) / l
			return Vector2(lerpf(p.x, q.x, t), lerpf(p.z, q.z, t))
		acc += l
	var e: Vector3 = pts[pts.size() - 1]
	return Vector2(e.x, e.z)


func _along_back(pts: Array, s: float) -> Vector2:
	var rev: Array = pts.duplicate()
	rev.reverse()
	return _along(rev, s)


func _choose_next() -> Array:
	# Fahrtziel: ein Punkt 1,5–4 km entfernt; ist er erreicht, kommt das nächste
	if goal == Vector2.INF or Vector2(pos.x, pos.z).distance_to(goal) < 300.0:
		goal = Vector2(pos.x, pos.z) + Vector2.from_angle(traffic.rng.randf() * TAU) * traffic.rng.randf_range(1500.0, 4000.0)
	return traffic.pick_next(cur_node, cur_edge, last_tangent, goal, goal_k)


func _extend_route() -> void:
	# Hängt Kanten an, bis die Route weit genug voraus reicht: mindestens 100 m, bei höherem Tempo Bremsweg plus
	# Reserve (Tempolimits, Kurven und Vorausfahrende müssen rechtzeitig sichtbar sein), auf mehrstreifigen
	# Richtungsfahrbahnen zusätzlich die Strecke für einen Überholvorgang
	var need := maxf(100.0, speed * t_gap + speed * speed / 4.0 + 45.0)
	if lane_tgt > 0 or (route_i < route_ln.size() and (route_ln[route_i] as Vector2).x > 0.0):
		need = maxf(need, speed * 9.0 + 90.0)
	need = minf(need, 420.0)
	var guard := 0
	while _route_remaining() < need and guard < 5:
		guard += 1
		var nxt := _choose_next()
		if nxt.is_empty():
			break
		var ei: int = nxt[0]
		var dir: int = nxt[1]
		var pts := traffic.edge_points(ei, dir)
		var last: Vector3 = route[route.size() - 1]
		var uturn := ei == cur_edge          # Wende (Sackgasse): Rückwärtspunkte zulassen
		if uturn and not is_bus and pos.distance_to(traffic.player.global_position) > 90.0:
			# Sackgasse außer Sichtweite: Fahrt endet dort (wie Parken) statt zu wenden – das Wenden auf engem
			# Raum war die Hauptquelle der Kreisfahrten
			_ends_here = true
			break
		var added := 0
		var vl := _cruise_for(traffic.edges[ei])
		var ln := _lane_info(traffic.edges[ei])
		var tan := last_tangent
		for i in pts.size():
			var p: Vector3 = pts[i]
			var dd := Vector2(p.x - last.x, p.z - last.z)
			if dd.length() < 1.5 or (not uturn and dd.dot(tan) < 0.3):
				continue
			route.append(p)
			route_v.append(vl)
			route_ln.append(ln)
			tan = dd.normalized()
			last = p
			added += 1
		if added == 0:
			break                             # Kante bringt keinen Fortschritt: nicht als befahren werten
		var m := marker_for(cur_node)
		if not m.is_empty() and int(m["exit_e"]) < 0:
			_set_exit(m, ei, dir)
		cur_edge = ei
		cur_dir = dir
		var e: Dictionary = traffic.edges[ei]
		cur_node = int(e["b"]) if dir == 1 else int(e["a"])
		var n := route.size()
		if n >= 2:
			last_tangent = Vector2(route[n - 1].x - route[n - 2].x, route[n - 1].z - route[n - 2].z).normalized()
		_add_marker(ei, dir)
		_on_edge_added(e)


func _on_edge_added(_e: Dictionary) -> void:
	pass


func _route_remaining() -> float:
	var tot := 0.0
	for i in range(route_i, route.size() - 1):
		tot += Vector2(route[i + 1].x - route[i].x, route[i + 1].z - route[i].z).length()
	return tot


func _lookahead_point(dist: float) -> Vector3:
	var acc := 0.0
	var i := route_i
	var prev := Vector3(pos.x, 0, pos.z)
	while i < route.size() - 1:
		var b: Vector3 = route[i + 1]
		var l := Vector2(b.x - prev.x, b.z - prev.z).length()
		if acc + l >= dist:
			return prev.lerp(Vector3(b.x, b.y, b.z), (dist - acc) / maxf(l, 0.001))
		acc += l
		prev = Vector3(b.x, b.y, b.z)
		i += 1
	return route[route.size() - 1]


func _marker_dist(m: Dictionary) -> float:
	## Routenentfernung bis zum Knotenpunkt der Marke (negativ = schon vorbei)
	var idx := int(m["ridx"])
	if idx > route_i:
		return _dist_to_index(idx)
	var np: Vector2 = m["np"]
	var fwd := Vector2(-sin(heading), -cos(heading))
	return -(Vector2(pos.x, pos.z) - np).dot(fwd)


## Logische Position (die Knotenposition hinkt bei sync_to_physics einen Physikschritt nach)
func world_pos() -> Vector3:
	if wrecked and wreck != null and is_instance_valid(wreck):
		return wreck.global_position
	return pos


func mass_kg() -> float:
	return 11000.0 if is_bus else MASS


func _dist_to_index(idx: int) -> float:
	## Routenentfernung bis Routenpunkt idx (negativ, wenn schon vorbei)
	if idx <= route_i:
		var p := Vector2(route[maxi(idx, 0)].x, route[maxi(idx, 0)].z)
		var seg := Vector2(route[mini(idx + 1, route.size() - 1)].x, route[mini(idx + 1, route.size() - 1)].z) - p
		var me := Vector2(pos.x, pos.z) - p
		return -me.dot(seg.normalized()) if seg.length() > 0.01 else -me.length()
	var tot := 0.0
	var prev := Vector2(pos.x, pos.z)
	for i in range(route_i + 1, mini(idx + 1, route.size())):
		var p := Vector2(route[i].x, route[i].z)
		tot += prev.distance_to(p)
		prev = p
	return tot


# --- Fahren ----------------------------------------------------------------------------------------
static var prof_us := 0
static var sync_phys := true
static var prof_parts := {}


static func _pp(k: String, us: int) -> void:
	prof_parts[k] = int(prof_parts.get(k, 0)) + us
static var prof_think_us := 0


var _lod_acc := 0.0
var _lod_phase := false


func _physics_process(delta: float) -> void:
	var _t0 := Time.get_ticks_usec()
	# Detailstufe: fern der Kamera (> 120 m) nur jeden zweiten Schritt rechnen (mit doppeltem Zeitschritt)
	var far := false
	var cam := traffic.cam if traffic else null
	if cam != null and not wrecked:
		far = pos.distance_squared_to(cam.global_position) > 120.0 * 120.0
	if far:
		_lod_acc += delta
		_lod_phase = not _lod_phase
		if _lod_phase:
			prof_us += Time.get_ticks_usec() - _t0
			return
		_drive(_lod_acc)
		_lod_acc = 0.0
	else:
		if _lod_acc > 0.0:
			delta += _lod_acc
			_lod_acc = 0.0
		_drive(delta)
	prof_us += Time.get_ticks_usec() - _t0


func _drive(delta: float) -> void:
	if traffic == null or dead:
		return
	if wrecked:
		_wreck_process(delta)
		return
	if _back_d > 0.0:
		# Zurücksetzen vor dem Umfahren: gerade rückwärts im Schritttempo
		var st := minf(1.3 * delta, _back_d)
		_back_d -= st
		pos.x += sin(heading) * st
		pos.z += cos(heading) * st
		speed = 0.0
		_brake = false
		wheel_roll -= st / wheel_r
		_apply_transform()
		return
	# Segmentfortschritt
	while route_i < route.size() - 2:
		var a: Vector3 = route[route_i]
		var b: Vector3 = route[route_i + 1]
		var ab := Vector2(b.x - a.x, b.z - a.z)
		var ap := Vector2(pos.x - a.x, pos.z - a.z)
		if ap.dot(ab) / maxf(ab.length_squared(), 0.0001) >= 1.0:
			route_i += 1
		else:
			break
	# Kurve geschnitten: liegt das Fahrzeug schon neben einem der nächsten Segmente, dort weitermachen
	for k in range(route_i + 1, mini(route_i + 4, route.size() - 1)):
		var sa: Vector3 = route[k]
		var sb: Vector3 = route[k + 1]
		var sab := Vector2(sb.x - sa.x, sb.z - sa.z)
		var sap := Vector2(pos.x - sa.x, pos.z - sa.z)
		var st := sap.dot(sab) / maxf(sab.length_squared(), 0.0001)
		if st > 0.0 and st < 1.0 and (sap - sab * st).length() < 3.0:
			route_i = k
	if route_i > 6:
		route = route.slice(route_i)
		route_v = route_v.slice(route_i)
		route_ln = route_ln.slice(route_i)
		for m in markers:
			m["ridx"] = int(m["ridx"]) - route_i
		route_i = 0
	var _te := Time.get_ticks_usec()
	_ext_t -= delta
	if _ext_t <= 0.0 or route.size() - route_i < 4:
		_ext_t = 0.1
		_extend_route()
	_pp("extend", Time.get_ticks_usec() - _te)
	if route.size() - route_i < 2:
		dead = true
		death = "routenende"
		return

	# Schutz: zu weit von der Route entfernt -> entfernen
	var ra: Vector3 = route[route_i]
	var rb: Vector3 = route[route_i + 1]
	var rab := Vector2(rb.x - ra.x, rb.z - ra.z)
	var rap := Vector2(pos.x - ra.x, pos.z - ra.z)
	var rt := clampf(rap.dot(rab) / maxf(rab.length_squared(), 0.0001), 0.0, 1.0)
	var off_lim := 7.0 + lane_shift
	if absf(wrapf(atan2(-rab.x, -rab.y) - heading, -PI, PI)) > 1.4:
		off_lim = 14.0                       # mitten im Wenden
	if (rap - rab * rt).length() > off_lim:
		dead = true
		death = "abseits"
		if traffic.ignore_player and int(traffic.stats.get("abseits", 0)) < 6:
			var want_h := atan2(-rab.x, -rab.y)
			print("DBG abseits uid %d pos %s v %.1f dh %.2f seg %.1f route_i %d/%d ghost %.1f bus %s" % [uid, str(pos), speed, wrapf(want_h - heading, -PI, PI), rab.length(), route_i, route.size(), ghost_t, str(is_bus)])
		return
	_chk_t += delta
	if _chk_t > 14.0:
		if Vector2(pos.x - _chk_pos.x, pos.z - _chk_pos.z).length() < 6.0 and _limit == "obstacle" and ghost_t <= 0.0 and not _queued() \
				and pos.distance_to(traffic.player.global_position) > 80.0:
			dead = true
			death = "festgefahren"
			return
		_chk_t = 0.0
		_chk_pos = pos

	# Zielgeschwindigkeit: Wunschtempo des Fahrers auf dieser Straße (Tempolimit × Eigenart); vorausschauend
	# (niedrigeres Limit, Kurven auf Bremsweg-Entfernung) aus dem Denkschritt (_scan_ahead)
	v_cruise = float(route_v[mini(route_i, route_v.size() - 1)])
	var vt := minf(v_cruise, _v_ahead)
	_limit = ""
	# Fahrstreifenwechsel: Versatz weich nachführen (erst blinken, dann ziehen)
	_lane_t += delta
	var tgt_shift := float(lane_tgt) * lane_w + _evade + _yield_shift
	if lane_shift != tgt_shift:
		if _lane_hold > 0.0 and _evade <= 0.0:
			_lane_hold -= delta
		else:
			var lrate := clampf(absf(tgt_shift - lane_shift) * 1.3, 0.3, maxf(lane_w, 3.0) / 2.8) * clampf(speed / 8.0, 0.15, 1.0)
			if _evade > 0.0:
				lrate = maxf(lrate, 1.1)                 # Umfahren: schon im Stand voll einschlagen
			lane_shift = move_toward(lane_shift, tgt_shift, lrate * delta)
	# Vorausschaupunkt der Lenkung: wächst oberhalb des Stadttempos mit (ruhiger Geradeauslauf bei 100+)
	var look := clampf(speed * 0.9, 4.5 + length * 0.15, maxf(14.0 + length * 0.2, speed * 0.7))
	if _evade > 0.0:
		look = minf(look, 4.2)                          # Umfahren: früh und deutlich ausscheren
	var tp := _aim(look)
	var d := Vector2(tp.x - pos.x, tp.z - pos.z)
	var fwd0 := Vector2(-sin(heading), -cos(heading))
	if d.dot(fwd0) < 0.0 and d.length() > 0.5:
		tp = _aim(look + 10.0)
		d = Vector2(tp.x - pos.x, tp.z - pos.z)
	# Kurvenradius aus drei Routenpunkten (unabhängig vom seitlichen Versatz des Fahrzeugs)
	# (auf einem linken Fahrstreifen parallel zur Route gemessen, sonst täuschte der Versatz eine Kurve vor)
	var c0 := _aim(minf(look * 0.5, 6.0))
	var c1 := _aim(look + 6.0)
	var c2 := _aim(look + 18.0)
	var u1 := Vector2(c1.x - c0.x, c1.z - c0.z)
	var u2 := Vector2(c2.x - c1.x, c2.z - c1.z)
	if u1.length() > 1.0 and u2.length() > 1.0:
		var turn := absf(u1.angle_to(u2))
		if turn > 0.08:
			var radius := (u1.length() + u2.length()) * 0.5 / turn
			vt = minf(vt, maxf(sqrt(a_lat * radius), 3.6))   # Querbeschleunigung je Fahrer 2,0–3,5 m/s²

	# Kreuzungen, Haltestellen, Hindernisse: alle THINK s neu bewerten (versetzt je Fahrzeug)
	_since_think += delta
	_think_t -= delta
	if _think_t <= 0.0:
		var _tt := Time.get_ticks_usec()
		var dt := _since_think
		_since_think = 0.0
		_think_t += THINK
		var lim := INF
		_limit_c = ""
		_scan_ahead()
		var jcap := _junctions(dt)
		if jcap < lim:
			lim = jcap
			_limit_c = "junction"
		lim = minf(lim, _special_limit(dt))
		if ghost_t <= 0.0:
			var ocap := _obstacle_cap()
			if ocap < lim:
				lim = ocap
				_limit_c = "obstacle"
		else:
			_lead_ok = false
		# Fahrstreifen: alle 0,4 s prüfen (nur auf mehrstreifigen Richtungsfahrbahnen oder wenn links unterwegs)
		_lane_chk -= dt
		if _lane_chk <= 0.0:
			_lane_chk = 0.4
			if lane_tgt > 0 or lane_shift > 0.0 or (route_ln[mini(route_i, route_ln.size() - 1)] as Vector2).x > 0.0:
				_lane_think()
		if _lane_must and lane_shift > 0.5:
			# kommt nicht nach rechts: vor dem Ende des Streifens verzögern, bis sich eine Lücke findet
			lim = minf(lim, sqrt(2.0 * 2.0 * maxf(_lane_zone - 25.0, 0.0)))
		_vt_c = lim
		prof_think_us += Time.get_ticks_usec() - _tt
	if _vt_c < vt:
		vt = _vt_c
		_limit = _limit_c

	# Längsregelung nach dem Intelligent-Driver-Modell: a = a_max · (1 − (v/v0)⁴ − (s*/s)²) mit Wunschabstand
	# s* = s0 + v·T + v·Δv / (2·√(a_max·b)). v0 ist die gerade zulässige Geschwindigkeit (Limit, Kurve, Kreuzung);
	# liegt sie unter der gefahrenen, wird zügig, aber stetig auf sie verzögert. Der Abstand zum Vordermann
	# stammt aus dem Denkschritt und wird dazwischen fortgeschrieben.
	var prev_speed := speed
	var z2 := 0.0
	if _lead_ok:
		_lead_gap += (_lead_v - speed) * delta
		var s_star := s0 + maxf(0.0, speed * t_gap + speed * (speed - _lead_v) / (2.0 * sqrt(accel * brake_comf)))
		var z := s_star / maxf(_lead_gap, 0.3)
		z2 = z * z
	var a_cmd: float
	var lead_binds := false
	if speed > vt:
		var over := speed - vt
		a_cmd = -clampf(over * 4.0, 0.6, 7.5 if over > 4.0 else 4.5)
		var a_idm := accel * (1.0 - z2)
		if a_idm < a_cmd:
			a_cmd = a_idm
			lead_binds = true
	else:
		var q := speed / maxf(vt, 0.1)
		var q4 := q * q * q * q
		a_cmd = accel * (1.0 - q4 - z2)
		lead_binds = z2 > 0.5 and z2 > q4
	a_cmd = maxf(a_cmd, -8.0)
	if lead_binds and not (_limit == "junction" and vt <= 0.3):
		_limit = "obstacle"
	# Anfahren: erst wenn der Vordermann Platz gemacht hat, und nach der Reaktionszeit des Fahrers (an der Ampel
	# und in der Kolonne voll, beim Einbiegen nach Vorfahrt-Achten verkürzt) -> Kolonnen fahren gestaffelt an
	if speed < 0.15:
		_still_t += delta
		var go := a_cmd > 0.0 and vt > 0.2
		if go and _lead_ok and _lead_gap < s0 + 0.45:
			go = false
		if not go:
			_go_t = 0.0
			a_cmd = minf(a_cmd, 0.0)
			_stop_sig = _limit == "obstacle" or _sig_red()
		elif _still_t > 1.5:
			_go_t += delta
			if _go_t < (react_t if _stop_sig else react_t * 0.3):
				a_cmd = 0.0
	else:
		_still_t = 0.0
	# Gas weich aufbauen (Ruckbegrenzung), Bremse sofort
	if speed <= 0.0 and a_cmd <= 0.0:
		_acc = 0.0
	elif a_cmd > _acc:
		_acc = minf(a_cmd, _acc + (15.0 if _acc < 0.0 else 5.0) * delta)
	else:
		_acc = a_cmd
	speed += _acc * delta
	if _acc > 0.0:
		speed = minf(speed, maxf(vt, prev_speed))
	elif not lead_binds:
		speed = maxf(speed, minf(vt, prev_speed))
	speed = maxf(speed, 0.0)
	# Bremslicht mit Hysterese (leichtes Verzögern = Gas wegnehmen, kein Licht)
	_brake = _acc < -0.9 or (_brake and _acc < -0.3) or (speed < 0.2 and vt < 0.5)
	# Steckenbleiben hinter Hindernissen (nicht an Ampeln/Kreuzungen) -> kurz Geistmodus
	if speed < 0.25 and _limit == "obstacle" and not _queued():
		blocked_t += delta
		if blocked_t > 25.0 and pos.distance_to(traffic.player.global_position) > 90.0 \
				and (traffic.cam == null or not _in_view()):
			dead = true
			death = "festgefahren"
	else:
		blocked_t = maxf(blocked_t - delta, 0.0)
	_evade_think(delta)
	ghost_t = maxf(ghost_t - delta, 0.0)
	# Kreuzungs-Patt/Stau auflösen: sehr lange an einer Kreuzung wartend, Spieler sieht es nicht -> entfernen
	if speed < 0.3 and _limit == "junction":
		_jwait_t += delta
		if _jwait_t > 50.0 and pos.distance_to(traffic.player.global_position) > 40.0 and (traffic.cam == null or not _in_view()):
			dead = true
			death = "patt"
			return
	else:
		_jwait_t = 0.0

	# Lenkung (Pure Pursuit, kinematisch)
	# Zielpunkt innerhalb des Wendekreises (Kurve geschnitten/überschossen): er ist durch Lenken nicht erreichbar,
	# das Fahrzeug umkreiste ihn endlos. Dann weiter voraus zielen; hilft das nicht, im Schritttempo eng einlenken.
	var r_min := 4.2 + length * 0.08
	var tight := false
	for k in 6:
		var fw := Vector2(-sin(heading), -cos(heading))
		var lat := absf(fw.x * d.y - fw.y * d.x)
		if lat < 0.3 or d.length_squared() / (2.0 * lat) >= r_min:
			tight = false
			break
		tight = true
		if k == 5:
			break
		tp = _aim(look + 5.0 * float(k + 1))
		d = Vector2(tp.x - pos.x, tp.z - pos.z)
	# Routenende: das letzte Segment wird vom Fortschrittszähler nie abgeschlossen -> Abstand zum Endpunkt prüfen
	var end_p: Vector3 = route[route.size() - 1]
	var at_end := route_i >= route.size() - 2 and Vector2(end_p.x - pos.x, end_p.z - pos.z).length() < (6.0 if _ends_here else 3.5)
	if at_end or (tight and _route_remaining() < 8.0):
		# Routenende erreicht und keine Fortsetzung (Sackgasse ohne Wendemöglichkeit, Kachelrand): das Fahrzeug
		# umkreiste sonst den letzten Routenpunkt
		dead = true
		death = "routenende"
		return
	if d.length() > 0.2:
		var want := atan2(-d.x, -d.y)
		var diff := wrapf(want - heading, -PI, PI)
		var max_rate := maxf(speed, 1.0) / r_min
		if tight:
			# fast auf der Stelle drehen (Rangieren): Wendekreis 0,4 m statt den Punkt zu umkreisen
			speed = minf(speed, 0.5)
			max_rate = 1.2
		if absf(diff) > 2.0:
			# Wenden (Sackgasse): Schrittgeschwindigkeit, enger Bogen; liegt das Ziel im Wendekreis, rangieren
			speed = minf(speed, 1.6 if d.length() > 4.0 else 0.5)
			max_rate = 1.1
		var dh := clampf(diff * 3.2, -max_rate, max_rate) * delta
		heading += dh
		# Kreisfahrt: mehr als eine volle Drehung, ohne 40 m vom Fleck zu kommen
		_turn_acc += dh
		if Vector2(pos.x - _turn_pos.x, pos.z - _turn_pos.z).length() > 40.0:
			_turn_acc = 0.0
			_turn_pos = pos
		elif absf(_turn_acc) > TAU * 1.05:
			circles += 1
			traffic.stats["kreis"] = int(traffic.stats.get("kreis", 0)) + 1
			if int(traffic.stats["kreis"]) <= 8:
				print("DBG kreis uid %d bus %s pos (%.0f,%.0f) v %.1f Länge %.1f look %.1f Ziel-d %.1f" % [uid, str(is_bus), pos.x, pos.z, speed, length, look, d.length()])
			_turn_acc = 0.0
			_turn_pos = pos
			if circles >= 2:
				dead = true                  # Sicherheitsnetz: kreist trotzdem weiter -> entfernen
				death = "kreis_entfernt"
				return
	pos.x += -sin(heading) * speed * delta
	pos.z += -cos(heading) * speed * delta
	wheel_roll += speed / wheel_r * delta
	var _ta := Time.get_ticks_usec()
	_apply_transform()
	var _tb := Time.get_ticks_usec()
	_update_lights(delta)
	_pp("transform", _tb - _ta)
	_pp("lights", Time.get_ticks_usec() - _tb)


func _standing(o) -> bool:
	## Steht das Hindernis dauerhaft (Spieler hält, Wrack)? Wartende Fahrzeuge im Verkehr zählen nicht.
	if o == null or not is_instance_valid(o):
		return false
	if o is AICar:
		var oc := o as AICar
		return oc.wrecked and (oc.wreck == null or oc.wreck.linear_velocity.length() < 0.4)
	if o is RigidBody3D:
		return (o as RigidBody3D).linear_velocity.length() < 0.4
	return false


func _evade_think(delta: float) -> void:
	## Hupen und Umfahren: steht ein Hindernis länger als die Geduld des Fahrers im Weg, wird gehupt und –
	## wenn links genug Platz und kein Gegenverkehr ist – langsam links vorbeigefahren.
	_honk_t = maxf(_honk_t - delta, 0.0)
	if blocker != null and not is_instance_valid(blocker):
		blocker = null
	if _evade_o != null and not is_instance_valid(_evade_o):
		_evade_o = null
	var fwd := Vector3(-sin(heading), 0, -cos(heading))
	var right := Vector3(-fwd.z, 0, fwd.x)
	if _evade > 0.0:
		var gone := not _standing(_evade_o)
		if not gone:
			var rel: Vector3 = ((_evade_o as AICar).world_pos() if _evade_o is AICar else (_evade_o as Node3D).global_position) - pos
			gone = rel.dot(fwd) < -(rear_ext + 3.5)
		_evade_t = _evade_t + delta if speed < 0.2 else 0.0
		if gone or _evade_t > 12.0:
			# vorbei – oder es klemmt (zu wenig Platz): zurück in die Spur, später neu versuchen
			_evade = 0.0
			_evade_o = null
			blocked_t = 0.0
		return
	if is_bus or speed > 0.3 or _limit != "obstacle" or not _standing(blocker):
		return
	if honker and _honk_t <= 0.0 and blocked_t > patience * 0.5 and blocker == traffic.player:
		_honk_now()
	if blocked_t < patience:
		return
	var op: Vector3 = (blocker as AICar).world_pos() if blocker is AICar else (blocker as Node3D).global_position
	var ow := (blocker as AICar).width if blocker is AICar else 1.9
	var need := (width + ow) * 0.5 + 0.55 - (op - pos).dot(right)       # so weit nach links, dass ich vorbeipasse
	if need > 3.8:
		return
	need = maxf(need, 0.4)
	# Platz links und kein Gegenverkehr? (Fahrschlauch um den Versatz verschoben, 45 m voraus)
	for o in traffic.nearby_obstacles(pos + fwd * 20.0, 48.0):
		if o == self or o == blocker:
			continue
		var q: Vector3 = (o as AICar).world_pos() if o is AICar else (o as Node3D).global_position
		var f := (q - pos).dot(fwd)
		var lat := (q - pos).dot(right) + need
		if f > -6.0 and f < 45.0 and absf(lat) < width + 0.9:
			return
	if not traffic.ignore_player and blocker != traffic.player:
		var pq: Vector3 = traffic.player.global_position - pos
		if pq.dot(fwd) > -6.0 and pq.dot(fwd) < 45.0 and absf(pq.dot(right) + need) < width + 0.9:
			return
	_evade = need
	_evade_o = blocker
	blocked_t = 0.0
	# zu dicht aufgefahren, um auszuscheren: erst ein Stück zurücksetzen (wenn hinten frei ist)
	# (für den seitlichen Versatz y braucht ein Wagen mit Wendekreisradius R etwa 2·√(R·y) Anlauf)
	var gap := (op - pos).dot(fwd) - front_ext - 2.3
	_back_d = clampf(2.0 * sqrt(6.0 * need) + 0.8 - gap, 0.0, 7.5)
	_evade_t = 0.0
	if _back_d > 0.0:
		for o in traffic.nearby_obstacles(pos, 16.0):
			if o == self or o == blocker:
				continue
			var q2: Vector3 = (o as AICar).world_pos() if o is AICar else (o as Node3D).global_position
			var fb := (q2 - pos).dot(fwd)
			if fb < 0.0 and fb > -(rear_ext + _back_d + 5.0) and absf((q2 - pos).dot(right)) < width + 0.6:
				_back_d = clampf(-fb - rear_ext - 3.2, 0.0, _back_d)
	if OS.has_environment("DRESDEN_EVADE"):
		print("EVADE uid %d umfährt %s, Versatz %.1f m, Geduld %.0f s" % [uid, "Spieler" if blocker == traffic.player else "Wrack", need, patience])


func _honk_now() -> void:
	_honk_t = traffic.rng.randf_range(5.0, 14.0)
	if OS.has_environment("DRESDEN_EVADE"):
		print("EVADE uid %d hupt" % uid)
	if _honk == null:
		var st: AudioStream = load("res://assets/audio/car/horn_ext_loop.ogg")
		if st == null:
			return
		_honk = AudioStreamPlayer3D.new()
		_honk.stream = st
		_honk.unit_size = 14.0
		_honk.max_distance = 120.0
		_honk.pitch_scale = traffic.rng.randf_range(0.88, 1.14)
		if AudioServer.get_bus_index(GameSettings.VEHICLE_BUS) >= 0:
			_honk.bus = GameSettings.VEHICLE_BUS
		add_child(_honk)
	_honk.play()
	var dur := traffic.rng.randf_range(0.35, 1.1)
	get_tree().create_timer(dur).timeout.connect(func(): if is_instance_valid(_honk): _honk.stop())


var _yield_shift := 0.0       # Versatz nach rechts, um einem Einsatzfahrzeug Platz zu machen (negativ = rechts)


func _special_limit(_delta: float) -> float:
	return _emergency_yield()      # Busse: Haltestellen (eigene Fassung)


func _emergency_yield() -> float:
	## Nähert sich von hinten ein Einsatzfahrzeug mit Blaulicht (≤ 75 m, gleiche Richtung, gleiche Fahrbahn):
	## rechts heranfahren und fast anhalten, bis es vorbei ist.
	_yield_shift = 0.0
	if traffic == null or traffic.emergency.is_empty():
		return INF
	var fwd := Vector3(-sin(heading), 0.0, -cos(heading))
	for e in traffic.emergency:
		if e == self or not is_instance_valid(e):
			continue
		var ec: AICar = e
		var d := pos - ec.pos
		d.y = 0.0
		var dist := d.length()
		if dist > 75.0 or dist < 0.5:
			continue
		var ef := Vector3(-sin(ec.heading), 0.0, -cos(ec.heading))
		if d.dot(ef) < 0.0 or absf(d.cross(ef).y) > 7.0 or fwd.dot(ef) < 0.3:
			continue
		_yield_shift = -1.3
		_ind = 1
		return 1.5 if dist < 45.0 else 5.0
	return INF


func _aim(dist: float) -> Vector3:
	## Zielpunkt der Lenkung: Routenpunkt in dist voraus; beim Fahren auf einem linken Fahrstreifen vom Lotpunkt
	## auf der Route aus gemessen und um den Versatz nach links verschoben.
	if lane_shift < 0.02:
		return _lookahead_point(dist)
	var a: Vector3 = route[route_i]
	var b: Vector3 = route[mini(route_i + 1, route.size() - 1)]
	var ab := Vector2(b.x - a.x, b.z - a.z)
	var t := clampf(Vector2(pos.x - a.x, pos.z - a.z).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
	var prev := a.lerp(b, t)
	var res := prev
	var dir := ab
	var acc := 0.0
	var i := route_i
	while i < route.size() - 1:
		var q: Vector3 = route[i + 1]
		var seg := Vector2(q.x - prev.x, q.z - prev.z)
		var l := seg.length()
		if l > 0.01:
			dir = seg
		if acc + l >= dist:
			res = prev.lerp(q, (dist - acc) / maxf(l, 0.001))
			break
		acc += l
		prev = q
		res = q
		i += 1
	if dir.length() < 0.01:
		return res
	dir = dir.normalized()
	return Vector3(res.x + dir.y * lane_shift, res.y, res.z - dir.x * lane_shift)


func _sig_red() -> bool:
	## Zeigt die nächste Ampel auf meinem Weg Rot?
	for m in markers:
		if not bool(m["entered"]):
			var sg := int(m["sig"])
			return sg == SignalCtl.RED or sg == SignalCtl.RED_YELLOW
	return false


func _scan_ahead() -> void:
	## Vorausschau (je Denkschritt): tastet die Route ab dem Lotpunkt gleichmäßig ab – Reichweite = Bremsweg aus
	## der aktuellen Geschwindigkeit plus Reserve – und bestimmt daraus die Grenze _v_ahead: vor einem niedrigeren
	## Tempolimit und vor Kurven wird so früh verzögert, dass die angenehme Bremsverzögerung des Fahrers genügt
	## (v² = v_ziel² + 2·b·s). Die Abtastpunkte dienen auch der Erkennung Vorausfahrender in Kurven.
	var reach := clampf(speed * t_gap + speed * speed / 4.0 + 25.0, 45.0, 240.0)
	var step := clampf(reach / 20.0, 5.0, 12.0)
	_ahead_step = step
	_reach = reach
	_ahead.clear()
	if route_i + 1 >= route.size():
		_v_ahead = INF
		return
	var a := Vector2(route[route_i].x, route[route_i].z)
	var b := Vector2(route[route_i + 1].x, route[route_i + 1].z)
	var ab := b - a
	var t0 := clampf((Vector2(pos.x, pos.z) - a).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
	var prev := a + ab * t0
	_ahead.append(prev)
	var cap := INF
	var b_lim := brake_comf * 0.8
	var s := 0.0
	var need := step
	var i := route_i + 1
	var n := route.size()
	while i < n and s < reach:
		var q := Vector2(route[i].x, route[i].z)
		var l := prev.distance_to(q)
		if l <= need:
			s += l
			need -= l
			prev = q
			var va: float = route_v[i]
			if va < v_cruise:
				cap = minf(cap, sqrt(va * va + 2.0 * b_lim * maxf(s - 3.0, 0.0)))
			i += 1
		else:
			prev += (q - prev) * (need / l)
			s += need
			need = step
			_ahead.append(prev)
	if need < step - 0.5:
		_ahead.append(prev)
	# Kurven: Richtungsänderung über je zwei Abtastschritte (glättet Knicke der Kartendaten)
	var m := _ahead.size()
	for k in range(2, m - 2):
		var u1 := _ahead[k] - _ahead[k - 2]
		var u2 := _ahead[k + 2] - _ahead[k]
		var turn := absf(u1.angle_to(u2))
		if turn > 0.05:
			var vc2 := maxf(a_lat * (u1.length() + u2.length()) * 0.5 / turn, 12.96)
			if vc2 < speed * speed:
				cap = minf(cap, sqrt(vc2 + 2.0 * brake_comf * float(k - 2) * step))
	_v_ahead = cap


var _reach := 45.0
var _rp_dir := Vector2.ZERO
var _lane_hold := 0.0


func _route_project(p: Vector2) -> Vector2:
	## Lage von p zur abgetasteten Route voraus: x = Bogenlänge ab meinem Lotpunkt (−1: nicht an der Route),
	## y = Querversatz (links positiv). _rp_dir = Routenrichtung an dieser Stelle.
	var lim := 5.0 + lane_shift
	var best := lim * lim
	var res := Vector2(-1.0, 0.0)
	var s := 0.0
	for k in _ahead.size() - 1:
		var a := _ahead[k]
		var ab := _ahead[k + 1] - a
		var l2 := ab.length_squared()
		if l2 < 0.01:
			continue
		var l := sqrt(l2)
		var t := (p - a).dot(ab) / l2
		if t >= -0.05 and t <= 1.05:
			var off := p - a - ab * t
			var d2 := off.length_squared()
			if d2 < best:
				best = d2
				_rp_dir = ab / l
				res = Vector2(s + t * l, off.dot(Vector2(_rp_dir.y, -_rp_dir.x)))
		s += l
	return res


# --- Fahrstreifenwechsel ---------------------------------------------------------------------------
func _lane_think() -> void:
	## Rechtsfahrgebot und Überholen auf mehrstreifigen Richtungsfahrbahnen. Grundspur ist der rechte Streifen
	## (dort liegt die Route); überholt wird mit seitlichem Versatz um eine Streifenbreite nach links, wenn der
	## Vordermann deutlich langsamer ist als gewünscht, links Platz ist und bis zur nächsten Stelle, an der man
	## rechts sein muss (Abbiegen, Ampel, Ende des Streifens), genug Strecke bleibt. Danach zurück nach rechts.
	var here: Vector2 = route_ln[mini(route_i, route_ln.size() - 1)]
	_lane_must = false
	if lane_tgt > 0:
		if here.x > 0.0:
			lane_w = here.x
		_lane_zone = _free_zone(lane_tgt)
		_lane_must = _lane_zone < speed * 5.0 + 60.0
		if (_lane_must or _lane_t > 3.0) and _lane_hold <= 0.0 and _lane_free(lane_tgt - 1, 2 if _lane_must else 1):
			lane_tgt -= 1
			_lane_t = 0.0
			_lane_hold = 0.7
			return
		if _lane_must:
			return
	if here.x <= 0.0 or lane_tgt >= int(here.y) or _lane_t < 2.5 or speed < 8.0 or kind == Kind.BUS:
		return
	if not _lead_ok or not (blocker is AICar):
		return
	var want_v := minf(v_cruise, _v_ahead)
	if _lead_v > want_v - 2.5 or _lead_v < 3.0 or _lead_gap > speed * t_gap * 2.0 + 15.0:
		return                                   # Vordermann schnell genug, steht (Stau/Ampel) oder noch weit weg
	if _free_zone(lane_tgt + 1) < speed * 8.0 + 70.0:
		return
	lane_w = here.x
	if not _lane_free(lane_tgt + 1, 0):
		return
	if _lf_gap < speed * 3.0 and _lf_v < _lead_v + 1.5:
		return                                   # links geht es auch nicht schneller
	lane_tgt += 1
	_lane_t = 0.0
	_lane_hold = 0.8


func _free_zone(lane: int) -> float:
	## Strecke voraus (m), auf der Fahrstreifen lane vorhanden ist und keine Kreuzung das Einordnen rechts verlangt
	var d := 0.0
	var prev := Vector2(pos.x, pos.z)
	for i in range(route_i + 1, route.size()):
		if (route_ln[i] as Vector2).y < float(lane):
			break
		var q := Vector2(route[i].x, route[i].z)
		d += prev.distance_to(q)
		prev = q
	for m in markers:
		var dm := _marker_dist(m)
		if dm < 0.0:
			continue
		if dm > d:
			break
		var app: Array = m["app"]
		if int(m["exit_e"]) < 0 or int(m["move"]) != Move.STRAIGHT \
				or (not app.is_empty() and (int(app[5]) != -1 or int(app[3]) != 2 or int(app[4]) != 0)):
			d = minf(d, dm - float(m["jr"]) - 8.0)
			break
	return d


func _lane_free(lane: int, mode: int) -> bool:
	## Ist auf Fahrstreifen lane neben mir Platz? mode 0: Ausscheren zum Überholen, 1: freiwillig zurück nach
	## rechts (nur wenn ich dort nicht gleich wieder aufliefe), 2: muss nach rechts (knappere Lücken).
	## Merkt Abstand und Tempo des nächsten Vorausfahrenden im Zielstreifen (_lf_gap, _lf_v).
	_lf_gap = INF
	_lf_v = INF
	var fwd := Vector2(-sin(heading), -cos(heading))
	var right := Vector2(-fwd.y, fwd.x)
	var me := Vector2(pos.x, pos.z)
	var tgt := float(lane) * lane_w
	var obs: Array = traffic.nearby_obstacles(pos, clampf(speed * 3.0 + 50.0, 60.0, 170.0))
	if not traffic.ignore_player:
		obs.append(traffic.player)
	for o in obs:
		if o == self:
			continue
		var op: Vector3
		var ov2: Vector2
		var o_fe := 2.25
		var o_re := 2.25
		var in_lane := false
		var known := false
		if o is AICar:
			var oc := o as AICar
			op = oc.world_pos()
			o_fe = oc.front_ext
			o_re = oc.rear_ext
			if not oc.wrecked:
				known = true
				var of := Vector2(-sin(oc.heading), -cos(oc.heading))
				ov2 = of * oc.speed
				if of.dot(fwd) < 0.5:
					continue                      # Gegen-/Querverkehr
				var rel0 := Vector2(op.x, op.z) - me
				# gleiche Fahrbahn? (grob geometrisch; den Streifen gibt der andere selbst an)
				if absf(rel0.dot(right) + (oc.lane_shift - lane_shift)) > 3.0 + absf(rel0.dot(fwd)) * 0.07:
					continue
				in_lane = absf(oc.lane_shift - tgt) < 0.8 * lane_w or absf(float(oc.lane_tgt) * oc.lane_w - tgt) < 0.5 * lane_w
			elif oc.wreck != null:
				var wv := oc.wreck.linear_velocity
				ov2 = Vector2(wv.x, wv.z)
		elif o is RigidBody3D:
			op = (o as Node3D).global_position
			var pv := (o as RigidBody3D).linear_velocity
			ov2 = Vector2(pv.x, pv.z)
		else:
			continue
		var rel := Vector2(op.x, op.z) - me
		var f := rel.dot(fwd)
		if not known:
			in_lane = absf(rel.dot(right) + (tgt - lane_shift)) < 2.4 + absf(f) * 0.03
		if not in_lane:
			continue
		var ov := ov2.dot(fwd)
		if f >= 0.0:
			var gap := f - (o_re + front_ext)
			var need := s0 + speed * t_gap * 0.5 + maxf(speed - ov, 0.0) * 2.5
			if mode == 1:
				need = s0 + speed * t_gap * 1.5 + maxf(speed - ov, 0.0) * 6.0
			elif mode == 2:
				need = s0 + 1.0 + maxf(speed - ov, 0.0) * 1.5
			if gap < need:
				return false
			if gap < _lf_gap:
				_lf_gap = gap
				_lf_v = ov
		else:
			var gap_b := -f - (o_fe + rear_ext)
			var need_b := 3.0 + ov * 0.4 + maxf(ov - speed, 0.0) * 3.0
			if mode == 2:
				need_b = 2.0 + ov * 0.2 + maxf(ov - speed, 0.0) * 2.0
			if gap_b < need_b:
				return false
	return true


# --- Kreuzungslogik --------------------------------------------------------------------------------
func _junctions(delta: float) -> float:
	var cap := INF
	var drop: Array = []
	for m in markers:
		var d_node := _marker_dist(m)
		if d_node < -(float(m["jr"]) + 4.0):
			drop.append(m)
			continue
		if d_node > maxf(95.0, speed * speed / 4.8 + 30.0):
			break
		traffic.register(int(m["node"]), self)
		var c := _junction_cap(m, d_node, delta)
		cap = minf(cap, c)
		if not bool(m["entered"]):
			break
	for m in drop:
		traffic.unregister(int(m["node"]), self)
		markers.erase(m)
	return cap


func _junction_cap(m: Dictionary, d_node: float, delta: float) -> float:
	var app: Array = m["app"]
	var stop_d: float = float(app[6]) if not app.is_empty() else minf(float(m["jr"]) * 0.8, 6.0)
	var d_stop := d_node - stop_d
	m["d_stop"] = d_stop
	m["eta"] = 0.0 if (d_stop < 3.0 and speed < 0.5) else maxf(d_stop, 0.0) / maxf(speed, 1.0)
	if d_stop < -0.6 and not bool(m["entered"]):
		m["entered"] = true
		var ap0: Array = m["app"]
		m["enter_st"] = SignalCtl.state(ap0[7], int(ap0[5])) if not ap0.is_empty() and int(ap0[5]) >= 0 else -1
	if bool(m["entered"]):
		m["waiting"] = false
		return INF
	var cap := INF
	var ph: int = int(app[5]) if not app.is_empty() else -1
	var must := false
	if ph >= 0:
		var st := SignalCtl.state(app[7], ph)
		m["sig"] = st
		if st == SignalCtl.RED or st == SignalCtl.RED_YELLOW:
			must = true
		elif st == SignalCtl.YELLOW and d_stop > speed * speed / (2.0 * yellow_b) + 1.5:
			must = true
	else:
		var lvl: int = Traffic.LVL[int(app[3])] if not app.is_empty() else 2
		if lvl <= 2 and ph == -1:
			# gleichrangig/wartepflichtig: langsam heranfahren und schauen
			cap = maxf(4.2, sqrt(2.0 * 1.6 * maxf(d_stop, 0.0)) + 3.6)
		if not app.is_empty() and int(app[4]) == 2 and not bool(m["stop_done"]):
			must = true                          # Stoppschild: einmal ganz anhalten
			if speed < 0.3 and d_stop < 2.5:
				m["stop_t"] = float(m["stop_t"]) + delta
				if float(m["stop_t"]) > 1.0:
					m["stop_done"] = true
					must = false
	if not must and int(m["exit_e"]) >= 0:
		must = _must_yield(m, ph >= 0 or ph == -2)
	if not must and d_stop < 30.0 and _exit_blocked(m, d_node):
		must = true                              # Kreuzung nicht blockieren
	if must:
		cap = minf(cap, _stop_speed(d_stop - (1.0 if ph < 0 else 0.0)))
		var waiting := speed < 0.5 and d_stop < 5.0
		m["waiting"] = waiting
		if waiting:
			m["wait_t"] = float(m["wait_t"]) + delta
	else:
		m["waiting"] = false
		m["wait_t"] = 0.0
	return cap


func _exit_blocked(m: Dictionary, d_node: float) -> bool:
	## Ist hinter der Kreuzung Platz für dieses Fahrzeug? (stehendes Fahrzeug auf der Ausfahrt)
	var need := float(m["jr"]) + length + 2.5
	var dn := maxf(d_node, 0.0)
	var a3 := _lookahead_point(dn)
	var m3 := _lookahead_point(dn + need * 0.5)
	var b3 := _lookahead_point(dn + need)
	var a := Vector2(a3.x, a3.z)
	var mm := Vector2(m3.x, m3.z)
	var b := Vector2(b3.x, b3.z)
	for o in traffic.nearby_obstacles(pos, dn + need + 12.0):
		if o == self or not (o is AICar):
			continue
		var oc := o as AICar
		if oc.speed > 1.5 or oc.wrecked:
			continue
		var op3 := oc.world_pos()
		var op := Vector2(op3.x, op3.z)
		var d1 := op.distance_to(Geometry2D.get_closest_point_to_segment(op, a, mm))
		var d2 := op.distance_to(Geometry2D.get_closest_point_to_segment(op, mm, b))
		if minf(d1, d2) < 1.8:
			# nur Fahrzeuge in meiner Fahrtrichtung (nicht Querverkehr, der gerade die Kreuzung räumt)
			var of := Vector2(-sin(oc.heading), -cos(oc.heading))
			var my_dir := (b - mm).normalized() if b.distance_to(mm) > 0.5 else (mm - a).normalized()
			if of.dot(my_dir) > 0.5:
				return true
	return false


func _in_view() -> bool:
	var c := traffic.cam
	var to_p := (pos - c.global_position)
	return to_p.length() < 200.0 and to_p.normalized().dot(-c.global_transform.basis.z) > 0.4


func _stop_speed(d_stop: float) -> float:
	## Zulässige Geschwindigkeit, um an der Haltelinie zu stehen (Verzögerung je Fahrer 2,6–3,4 m/s²)
	if d_stop < 0.6:
		return 0.0
	return sqrt(2.0 * clampf(brake_comf + 0.3, 2.6, 3.4) * (d_stop - 0.6))


func _lvl(m: Dictionary) -> int:
	var app: Array = m["app"]
	return Traffic.LVL[int(app[3])] if not app.is_empty() else 2


func _must_yield(m: Dictionary, signalized: bool) -> bool:
	## Muss ich an Kreuzung m warten? Sammelt alle Fahrzeuge mit Vorrang, die vor meinem Räumen ankommen
	## (oder schon in der Kreuzung sind). Patt: stehen alle diese selbst und warte ich > 5 s, fährt die
	## kleinere Nummer.
	var node := int(m["node"])
	var blockers: Array = []
	var clear_d := maxf(float(m["d_stop"]), 0.0) + float(m["jr"]) * 2.0 + length
	var my_clear := float(m["eta"]) + sqrt(2.0 * clear_d / maxf(accel, 1.0)) + 1.0
	for o in traffic.jreg.get(node, []):
		if o == self or not is_instance_valid(o) or (o as AICar).dead or (o as AICar).wrecked:
			continue
		var oc := o as AICar
		var om := oc.marker_for(node)
		if om.is_empty() or int(om["exit_e"]) < 0:
			continue
		if int(om["in_e"]) == int(m["in_e"]) and int(om["in_d"]) == int(m["in_d"]):
			continue                              # gleiche Zufahrt: Folgefahren regelt das
		if not _paths_conflict(m, om):
			continue
		if bool(om["entered"]):
			blockers.append(oc)                   # steht/fährt schon in der Kreuzung
			continue
		var inner := not (m["app"] as Array).is_empty() and int((m["app"] as Array)[5]) == -2
		if inner:
			# innerhalb einer Ampelgruppe: wer zuerst ankommt, fährt zuerst
			if float(om["eta"]) < float(m["eta"]) or (is_equal_approx(float(om["eta"]), float(m["eta"])) and oc.uid < uid):
				blockers.append(oc)
			continue
		if not _has_priority(om, m, signalized):
			continue
		if float(om["eta"]) < my_clear and float(om["eta"]) < 10.0:
			blockers.append(oc)
	# Spieler
	var pl := traffic.player_at(node)
	if not pl.is_empty():
		var a: Vector2 = pl["a"]
		var b: Vector2 = pl["b"]
		if bool(pl["inside"]):
			if _path_near_segment(m["path"], a, b, 2.4):
				return true
		elif float(pl["eta"]) < my_clear and float(pl["eta"]) < 7.0:
			var rel := wrapf(float(pl["ang"]) - float(m["ang_in"]), -PI, PI)
			var pri := false
			if signalized:
				pri = absf(rel) > 2.4 and int(m["move"]) == Move.LEFT
			elif int(pl["lvl"]) != _lvl(m):
				pri = int(pl["lvl"]) > _lvl(m)
			else:
				pri = (rel < -0.6 and rel > -2.4) or (absf(rel) > 2.4 and int(m["move"]) == Move.LEFT)
			if pri and _path_near_segment(m["path"], a, b, 2.4):
				return true
	if blockers.is_empty():
		return false
	if float(m["wait_t"]) > 5.0:
		# Patt? Nur wenn alle Vorrang-Fahrzeuge selbst stehen; dann fährt die kleinste Nummer
		var all_stuck := true
		var smallest := true
		for oc in blockers:
			var c := oc as AICar
			if c.speed > 0.3:
				all_stuck = false
				break
			if c.uid < uid:
				smallest = false
		if all_stuck and smallest:
			return false
	return true


func _has_priority(om: Dictionary, m: Dictionary, signalized: bool) -> bool:
	## Hat das andere Fahrzeug (om) Vorrang vor mir (m)?
	var rel := wrapf(float(om["ang_in"]) - float(m["ang_in"]), -PI, PI)
	var oncoming := absf(rel) > 2.4
	var from_right := rel < -0.6 and rel > -2.4
	var same_exit := int(m["exit_e"]) == int(om["exit_e"]) and int(m["exit_d"]) == int(om["exit_d"])
	var mv := int(m["move"])
	var omv := int(om["move"])
	if same_exit:
		# Einmünden in dieselbe Fahrbahn: wer stärker abbiegt, wartet; gleich: rechts vor links
		var tm := absf(wrapf(float(m["ang_out"]) - float(m["ang_in"]), -PI, PI))
		var to := absf(wrapf(float(om["ang_out"]) - float(om["ang_in"]), -PI, PI))
		if not signalized and _lvl(om) != _lvl(m):
			return _lvl(om) > _lvl(m)
		if absf(tm - to) > 0.25:
			return tm > to
		return from_right or (not (rel > 0.6 and rel < 2.4) and om.get("uid", 0) < uid)
	if signalized:
		if oncoming and mv == Move.LEFT and omv != Move.LEFT:
			return true
		return false
	var lm := _lvl(m)
	var lo := _lvl(om)
	if lo != lm:
		return lo > lm
	if oncoming:
		return mv == Move.LEFT and omv != Move.LEFT
	if same_exit and mv != Move.STRAIGHT and omv == Move.STRAIGHT and not from_right:
		return true
	return from_right


func _paths_conflict(m: Dictionary, om: Dictionary) -> bool:
	if int(m["exit_e"]) == int(om["exit_e"]) and int(m["exit_d"]) == int(om["exit_d"]):
		return true
	var p: PackedVector2Array = m["path"]
	var q: PackedVector2Array = om["path"]
	for i in p.size() - 1:
		for j in q.size() - 1:
			if Geometry2D.segment_intersects_segment(p[i], p[i + 1], q[j], q[j + 1]) != null:
				return true
	return false


func _path_near_segment(path: PackedVector2Array, a: Vector2, b: Vector2, r: float) -> bool:
	for i in path.size() - 1:
		if Geometry2D.segment_intersects_segment(path[i], path[i + 1], a, b) != null:
			return true
		var c := Geometry2D.get_closest_points_between_segments(path[i], path[i + 1], a, b)
		if (c[0] as Vector2).distance_to(c[1]) < r:
			return true
	return false


# --- Hindernisse ------------------------------------------------------------------------------------
var blocker: Object = null     # Fahrzeug, das mich zuletzt begrenzt hat
var _jwait_t := 0.0


func _queued() -> bool:
	## Stehe ich in einem Rückstau vor einer Kreuzung/Ampel? (Kette der Vordermänner endet an einer Haltelinie)
	var b: Object = blocker
	for i in 12:
		if b == null or not is_instance_valid(b) or not (b is AICar):
			return false
		var ac := b as AICar
		if ac._limit == "junction" or (ac is BusCar and (ac as BusCar).at_stop):
			return true
		if ac.speed > 0.5:
			return true                # Vordermann rollt: zähfließend, nicht festgefahren
		b = ac.blocker
	return false


func _note_leader(gap: float, ov: float, o: Object) -> void:
	## Merkt den Vorausfahrenden, der nach dem Folgemodell am stärksten bremst (größtes s*/s)
	var s_star := s0 + maxf(0.0, speed * t_gap + speed * (speed - ov) / (2.0 * sqrt(accel * brake_comf)))
	var z := s_star / maxf(gap, 0.3)
	if z > _lead_z:
		_lead_z = z
		_lead_ok = true
		_lead_gap = gap
		_lead_v = ov
		blocker = o


var _lead_z := 0.0


func _obstacle_cap() -> float:
	## Vorausfahrende und Hindernisse. Im Nahbereich (bis 40 m) geradlinig in Fahrtrichtung, weiter voraus
	## entlang der Route (Kurven). Der maßgebliche Vordermann geht ins Folgemodell (_lead_*); zurückgegeben wird
	## nur die harte Grenze für Notfälle (zu dicht, Reißverschluss, Querverkehr).
	var vt := INF
	blocker = null
	_lead_ok = false
	_lead_z = 0.0
	var fwd := Vector3(-sin(heading), 0, -cos(heading))
	var right := Vector3(-fwd.z, 0, fwd.x)
	var here_lw: float = (route_ln[mini(route_i, route_ln.size() - 1)] as Vector2).x
	var tgt_shift := float(lane_tgt) * lane_w
	var obstacles: Array
	if _reach > 46.0:
		# Sichtweite über 42 m: Suchkreis nach vorn verschoben (deckt 22 m nach hinten bis Sichtweite nach vorn)
		obstacles = traffic.nearby_obstacles(pos + fwd * (_reach * 0.5 - 8.0), _reach * 0.5 + 14.0)
	else:
		obstacles = traffic.nearby_obstacles(pos, 42.0)
	if not traffic.ignore_player:
		obstacles.append(traffic.player)
	for o in obstacles:
		if o == self:
			continue
		var op: Vector3 = (o as AICar).world_pos() if o is AICar else (o as Node3D).global_position
		var ovel := Vector3.ZERO
		var olen := 4.5
		var ow := 1.9
		var o_rear := 2.25
		if o is AICar:
			var oc := o as AICar
			olen = oc.length
			ow = oc.width
			o_rear = oc.rear_ext
			if oc.wrecked and oc.wreck != null:
				ovel = oc.wreck.linear_velocity
			else:
				ovel = Vector3(-sin(oc.heading), 0, -cos(oc.heading)) * oc.speed
		elif o is RigidBody3D:
			ovel = (o as RigidBody3D).linear_velocity
		var rel := op - pos
		var f := rel.dot(fwd)
		if f < -olen:
			continue
		var along := ovel.dot(fwd)
		if f <= 40.0:
			var lat_v := ovel.dot(right)
			var corridor := (width + ow) * 0.5 + 0.35 + clampf(f * 0.04, 0.0, 0.8)
			if here_lw > 0.0:
				# mehrstreifig: der Nachbarstreifen gehört nicht zu meinem Fahrschlauch
				corridor = minf(corridor, maxf(here_lw - 0.3, (width + ow) * 0.5 + 0.1))
			var lat := rel.dot(right)
			if _evade > 0.0 and o == _evade_o:
				# wird gerade umfahren: nur die tatsächliche Überdeckung zählt, langsam vorbeiziehen
				if absf(lat) < (width + ow) * 0.5 + 0.12 and f > 0.3:
					var net_e := f - (o_rear + front_ext)
					vt = minf(vt, (1.5 if net_e > 2.0 else 0.9) if net_e > 0.45 else 0.0)
				else:
					vt = minf(vt, 4.5)
				continue
			# Gegenverkehr auf eigener Spur ignorieren, wenn er seitlich deutlich versetzt ist
			if absf(lat) < corridor and f > 0.3:
				if along < -1.0 and absf(lat) > corridor * 0.55:
					continue
				var net := f - (o_rear + front_ext)        # lichter Abstand Stoßfänger–Stoßfänger
				var ov := maxf(along, 0.0)
				_note_leader(net, ov, o)
				# harte Grenze: zu dicht -> halten bzw. deutlich langsamer als der Vordermann; sonst die
				# Geschwindigkeit, aus der mit 6,5 m/s² noch hinter ihm zum Stehen zu kommen ist
				var allowed := sqrt(ov * ov + 2.0 * 6.5 * maxf(net - 1.2, 0.0))
				if net < 1.2:
					allowed = 0.0
				elif net < 2.2:
					allowed = minf(allowed, ov * 0.6)
				if allowed < vt:
					vt = allowed
					if allowed < speed:
						blocker = o
				continue
			# nebeneinander (zusammenlaufende Spuren): Reißverschluss – wer weiter hinten ist (bzw. größere Nummer), lässt vor
			if absf(f) < (olen + length) * 0.5 and absf(lat) < (width + ow) * 0.5 + 0.25 and along > -1.0:
				if f > 0.0 or (absf(f) < 0.5 and o is AICar and (o as AICar).uid < uid):
					vt = minf(vt, maxf(along - 1.0, 0.0))
				continue
			# Querverkehr: wo ist das Hindernis in 0,4 / 0,8 / 1,6 s?
			if absf(lat_v) > 0.5:
				for t in [0.4, 0.8, 1.6]:
					var lt: float = lat + lat_v * t
					var ft: float = f + along * t
					var mine: float = speed * t
					if absf(lt) < corridor and ft > 0.0 and ft - mine < (olen + length) * 0.5 + 2.5:
						var gap2: float = ft - (olen + length) * 0.5 - 2.0
						vt = minf(vt, sqrt(2.0 * 4.5 * maxf(gap2, 0.0)))
						break
		# Fernbereich und Kurven: Lage entlang der Route (nur Fahrzeuge, keine Bahnen)
		if f > 18.0 and (o is AICar or o is RigidBody3D):
			var pr := _route_project(Vector2(op.x, op.z))
			if pr.x <= 0.0:
				continue
			var o2 := Vector2(ovel.x, ovel.z)
			var al := o2.dot(_rp_dir)
			if o2.length() > 1.0 and al < 0.5 * o2.length():
				continue                              # quert oder kommt entgegen
			var band := (width + ow) * 0.5 + 0.2
			var lo := pr.y - lane_shift               # Querlage relativ zu meinem Fahrstreifen (links positiv)
			if absf(lo) < band or (lane_shift != tgt_shift and absf(pr.y - tgt_shift) < band):
				_note_leader(pr.x - (o_rear + front_ext), maxf(al, 0.0), o)
			elif here_lw > 0.0 and lo > band and lo < here_lw * 1.3 and speed > 16.0 and al > 16.0 \
					and pr.x - olen < speed * 2.5:
				vt = minf(vt, al + 1.0)               # rechts wird nicht überholt (außer im zähen Verkehr)
	return minf(vt, _ped_cap())


var _ped_t := 0.0              # Standzeit vor Fußgängern (Geduld)


func _ped_cap() -> float:
	## Fußgänger auf der Fahrbahn (Peds.on_road_pts, alle 0,1 s neu): liegt einer voraus in meinem Fahrschlauch,
	## davor anhalten. Nach 15 s Stehen fährt der Fahrer vorsichtig an (kein Dauerstau vor Stehengebliebenen).
	if (Peds.on_road_pts.is_empty() and Peds.zebra_waits.is_empty()) or _ahead.size() < 2:
		_ped_t = 0.0
		return INF
	var cap := INF
	var me := Vector2(pos.x, pos.z)
	var r2 := (_reach + 4.0) * (_reach + 4.0)
	for q in Peds.on_road_pts:
		var p := Vector2(q.x, q.z)
		if p.distance_squared_to(me) > r2 or absf(q.y - pos.y) > 4.0:
			continue
		var pr := _route_project(p)
		if pr.x <= 0.0 or absf(pr.y - lane_shift) > width * 0.5 + 1.5:
			continue
		cap = minf(cap, _stop_speed(pr.x - front_ext - 2.0))
	# Wartende am Zebrastreifen (Peds.zebra_waits, Punkt auf der Straßenmitte): anhalten, wenn das mit der
	# angenehmen Verzögerung noch geht – sonst durchfahren. Stehe ich, gehen sie los (dann in on_road_pts).
	for q in Peds.zebra_waits:
		var p := Vector2(q.x, q.z)
		if p.distance_squared_to(me) > r2 or absf(q.y - pos.y) > 4.0:
			continue
		var pr := _route_project(p)
		if pr.x <= 0.0 or absf(pr.y - lane_shift) > 4.5:
			continue
		var ds := pr.x - front_ext - 2.5
		if ds < 0.5 or speed * speed > 2.0 * (brake_comf + 0.6) * ds:
			continue
		cap = minf(cap, _stop_speed(ds))
	if cap < 0.5 and speed < 0.3:
		_ped_t += THINK
		if _ped_t > 15.0:
			cap = 1.5
			if _ped_t > 19.0:
				_ped_t = 0.0
	elif cap == INF:
		_ped_t = 0.0
	return cap


# --- Licht -----------------------------------------------------------------------------------------
static var no_light_params := OS.has_environment("DRESDEN_NOLIGHTPARAMS")


func _update_lights(delta: float) -> void:
	_light_t -= delta
	if _light_t > 0.0 or no_light_params:
		return
	_light_t = 0.12
	var ind := 0
	if wrecked:
		ind = 2
	else:
		for m in markers:
			if bool(m["passed"]):
				continue
			var d_node := _marker_dist(m)
			if d_node < 42.0 and d_node > -float(m["jr"]):
				var mv := int(m["move"])
				ind = -1 if mv == Move.LEFT or mv == Move.UTURN else (1 if mv == Move.RIGHT else 0)
			break
		# Fahrstreifenwechsel anzeigen
		if ind == 0:
			var dl := float(lane_tgt) * lane_w - lane_shift
			if dl > 0.25:
				ind = -1
			elif dl < -0.25:
				ind = 1
	_ind = ind
	var on := 1.0 if traffic.night > 0.3 or traffic.rain > 0.5 else 0.0
	for li in lights:
		var mi := li as MeshInstance3D
		mi.set_instance_shader_parameter("lights_on", on)
		mi.set_instance_shader_parameter("brake_on", 1.0 if _brake else 0.0)
		mi.set_instance_shader_parameter("ind_l", 1.0 if ind == -1 or ind == 2 else 0.0)
		mi.set_instance_shader_parameter("ind_r", 1.0 if ind == 1 or ind == 2 else 0.0)


func _apply_transform() -> void:
	var gy: float = traffic.terrain.height_at(pos.x, pos.z)
	# Fahrbahnprofil (Route) und Gelände stimmen abseits von Brücken überein (build_city: Längsprofil + conform).
	# Auf Brücken liegt die Route über dem Gelände -> immer die höhere Fläche nehmen.
	var ry := _route_y()
	# im Tunnel liegt die Route tief unter dem Gelände -> Routenhöhe (Vorprüfung billig, inside() nur dann)
	var in_tunnel := ry < gy - 2.0 and Tunnels.inside(Vector3(pos.x, ry, pos.z))
	var on_deck := in_tunnel or ry > gy + 0.08
	var y := ry if in_tunnel else maxf(gy, ry)
	pos.y = y
	var fwd := Vector3(-sin(heading), 0, -cos(heading))
	var front_y: float
	var rear_y: float
	if on_deck:
		front_y = _route_y_at(pos + fwd * axle_f)
		rear_y = _route_y_at(pos - fwd * axle_r)
	else:
		var fp := pos + fwd * axle_f
		var rp := pos - fwd * axle_r
		front_y = float(traffic.terrain.height_at(fp.x, fp.z))
		rear_y = float(traffic.terrain.height_at(rp.x, rp.z))
	var pitch := atan2(front_y - rear_y, axle_f + axle_r)
	var basis := Basis(Vector3.UP, heading) * Basis(Vector3.RIGHT, pitch)
	global_transform = Transform3D(basis, Vector3(pos.x, pos.y, pos.z))
	for k in wheels:
		var w: Node3D = wheels[k]
		w.transform.basis = Basis(Vector3.RIGHT, -wheel_roll)


func _route_y_at(p: Vector3) -> float:
	## Höhe der Route am Lotpunkt von p (aktuelles und nächstes Teilstück).
	if route_i + 1 >= route.size():
		return pos.y
	var best_d := INF
	var best_y := pos.y
	for i in range(maxi(route_i - 1, 0), mini(route_i + 2, route.size() - 1)):
		var a: Vector3 = route[i]
		var b: Vector3 = route[i + 1]
		var ab := Vector2(b.x - a.x, b.z - a.z)
		var t := clampf(Vector2(p.x - a.x, p.z - a.z).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
		var q := Vector2(a.x, a.z) + ab * t
		var d := q.distance_squared_to(Vector2(p.x, p.z))
		if d < best_d:
			best_d = d
			best_y = lerpf(a.y, b.y, t)
	return best_y


func _route_y() -> float:
	if route_i + 1 >= route.size():
		return pos.y
	var a: Vector3 = route[route_i]
	var b: Vector3 = route[route_i + 1]
	var ab := Vector2(b.x - a.x, b.z - a.z)
	var t := clampf(Vector2(pos.x - a.x, pos.z - a.z).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
	return lerpf(a.y, b.y, t)


# --- Zusammenstoß / Wrack-Modus -------------------------------------------------------------------
func velocity() -> Vector3:
	if wrecked and wreck != null:
		return wreck.linear_velocity
	return Vector3(-sin(heading), 0, -cos(heading)) * speed


## Vom Spieler gemeldeter Stoß: dv = Geschwindigkeitsänderung dieses Autos, w_y = Drehimpuls-Anteil (rad/s).
var damage: CarDamage             # Verformung (erst beim ersten Treffer angelegt)
var crash_sev := 0.0              # aufsummierte Stoßstärke (m/s Geschwindigkeitsänderung)
var disabled := false             # nicht mehr fahrbereit: bleibt mit Warnblinker liegen
var _shock_t := 0.0               # Schrecksekunden nach einem Unfall, bevor es weitergeht
var _wreck_smoke: CPUParticles3D


func player_impact(dv: Vector3, w_y: float, at: Vector3 = Vector3.INF, n: Vector3 = Vector3.ZERO) -> void:
	var sev := dv.length()
	crash_sev += sev
	_dent(at, n, sev)
	# leichter Rempler: kurzer Schreck; mittlerer Unfall: 8–25 s stehen; schwer (ab 5 m/s oder mehrfach getroffen):
	# nicht mehr fahrbereit
	_shock_t = maxf(_shock_t, 1.0 + sev * traffic.rng.randf_range(2.0, 4.5))
	if sev > 5.0 or crash_sev > 9.0:
		disabled = true
		_smoke_on()
	if honker and sev < 3.0 and _honk_t <= 0.0:
		_honk_now()
	if wrecked:
		if wreck != null:
			wreck.apply_central_impulse(dv * MASS)
		return
	_make_wreck(velocity() + dv, w_y)


func _dent(at: Vector3, n: Vector3, sev: float) -> void:
	## Beule an der Aufprallstelle (at: Weltpunkt, n: Stoßrichtung von mir zum Spieler)
	if at == Vector3.INF or sev < 0.8 or model_root == null or is_bus:
		return
	if damage == null:
		damage = CarDamage.new()
		damage.setup(self, model_root, {})
	var inv := model_root.global_transform.affine_inverse()
	var lp := inv * at
	var ldir := inv.basis * (-n)
	ldir.y *= 0.3
	if ldir.length() < 0.01:
		ldir = -lp
	damage.impact(lp, ldir, clampf(sev * 2.6, 2.0, 30.0))
	if OS.has_environment("DRESDEN_EVADE"):
		print("DENT uid %d sev %.1f bei %s, Summe %.1f, liegengeblieben %s, Schreck %.0f s" % [uid, sev, str(lp), crash_sev, str(disabled), _shock_t])


func _smoke_on() -> void:
	if _wreck_smoke != null or model_root == null:
		return
	_wreck_smoke = CPUParticles3D.new()
	_wreck_smoke.amount = 18
	_wreck_smoke.lifetime = 2.2
	_wreck_smoke.direction = Vector3.UP
	_wreck_smoke.spread = 20.0
	_wreck_smoke.initial_velocity_min = 0.8
	_wreck_smoke.initial_velocity_max = 1.8
	_wreck_smoke.gravity = Vector3(0, 0.4, 0)
	_wreck_smoke.scale_amount_min = 0.5
	_wreck_smoke.scale_amount_max = 1.5
	var q := QuadMesh.new()
	q.size = Vector2(1.0, 1.0)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	m.albedo_color = Color(0.75, 0.76, 0.78, 0.4)
	m.albedo_texture = Boats._puff_tex()
	q.material = m
	_wreck_smoke.mesh = q
	_wreck_smoke.position = Vector3(0, 0.9, -front_ext * 0.75)
	model_root.add_child(_wreck_smoke)


func _make_wreck(v: Vector3, w_y: float) -> void:
	for m in markers:
		traffic.unregister(int(m["node"]), self)
	wreck = RigidBody3D.new()
	wreck.name = "Wrack"
	wreck.mass = mass_kg()
	wreck.collision_layer = 4
	wreck.collision_mask = 1 | 2 | 4
	wreck.linear_damp = 0.12
	wreck.angular_damp = 1.6
	wreck.center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	wreck.center_of_mass = Vector3(0, 0.55, 0)
	var pm := PhysicsMaterial.new()
	pm.friction = 0.8
	pm.bounce = 0.05
	wreck.physics_material_override = pm
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = _box_size
	cs.shape = bs
	cs.position = Vector3(0, 0.35 + _box_size.y * 0.5, (rear_ext - front_ext) * 0.5)
	wreck.add_child(cs)
	traffic.add_child(wreck)
	wreck.global_transform = global_transform.translated(Vector3(0, 0.03, 0))
	model_root.reparent(wreck, true)
	wreck.linear_velocity = v
	wreck.angular_velocity = Vector3(0, w_y, 0)
	collision_layer = 0
	wrecked = true
	wreck_t = 0.0
	speed = 0.0
	_brake = false


func _wreck_process(delta: float) -> void:
	if wreck == null or not is_instance_valid(wreck):
		dead = true
		death = "wrack"
		return
	wreck_t += delta
	global_transform = wreck.global_transform
	_update_lights(delta)
	if wreck_t < 2.5:
		return
	if wreck.linear_velocity.length() > 0.6 or wreck.angular_velocity.length() > 0.35:
		return
	var b := wreck.global_transform.basis
	var upright := b.y.y > 0.85
	var h := atan2(b.z.x, b.z.z)
	var wp := wreck.global_position
	# zurück auf die Route?
	var best := INF
	var best_t := Vector2.ZERO
	for i in range(route_i, mini(route_i + 6, route.size() - 1)):
		var a: Vector3 = route[i]
		var c: Vector3 = route[i + 1]
		var ab := Vector2(c.x - a.x, c.z - a.z)
		var t := clampf(Vector2(wp.x - a.x, wp.z - a.z).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
		var dd := (Vector2(a.x, a.z) + ab * t).distance_to(Vector2(wp.x, wp.z))
		if dd < best:
			best = dd
			best_t = ab.normalized()
	var want := atan2(-best_t.x, -best_t.y)
	_shock_t = maxf(_shock_t - delta, 0.0)
	if upright and not disabled and _shock_t <= 0.0 and best < 2.6 and absf(wrapf(want - h, -PI, PI)) < 0.8 and wreck_t > 3.0:
		# weiterfahren
		model_root.reparent(self, true)
		global_transform = Transform3D(Basis(Vector3.UP, h), wp)
		model_root.transform = Transform3D.IDENTITY
		pos = Vector3(wp.x, wp.y, wp.z)
		heading = h
		speed = 0.0
		_acc = 0.0
		_lead_ok = false
		lane_tgt = 0
		lane_shift = 0.0
		_evade = 0.0
		_evade_o = null
		wreck.queue_free()
		wreck = null
		wrecked = false
		collision_layer = 4
		blocked_t = 0.0
		_chk_t = 0.0
		return
	# bleibt liegen (Warnblinker), verschwindet, wenn der Spieler weit weg ist
	if wreck_t > 90.0 and global_position.distance_to(traffic.player.global_position) > 140.0:
		dead = true
		death = "wrack"
