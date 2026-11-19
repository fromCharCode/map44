class_name ServiceCar
extends AICar
## Andere Taxis und Einsatzfahrzeuge im Verkehr: Polizei (Funkstreifenwagen), Rettungswagen, Feuerwehr.
## Aufbau aus den vorhandenen Fahrzeugmodellen mit Lackierung, Streifen, Schriftzug und Blaulichtbalken – ohne
## Markenzeichen. Im Einsatz (mission): Blaulicht, Martinshorn (in Software erzeugt), schneller, fährt nach
## kurzem Abbremsen auch bei Rot; die übrigen Fahrzeuge machen Platz (AICar._emergency_yield).

enum Service { TAXI, POLICE, AMBULANCE, FIRE }

const MODEL := {Service.TAXI: "taxi_limousine.glb", Service.POLICE: "kombi_nord.glb", Service.AMBULANCE: "transporter_modern.glb",
	Service.FIRE: "transporter_modern.glb"}
const PAINT := {Service.TAXI: Color(0.93, 0.87, 0.62), Service.POLICE: Color(0.80, 0.82, 0.84), Service.AMBULANCE: Color(0.93, 0.93, 0.90),
	Service.FIRE: Color(0.70, 0.07, 0.06)}
const STRIPE := {Service.POLICE: Color(0.05, 0.22, 0.62), Service.AMBULANCE: Color(0.85, 0.12, 0.08), Service.FIRE: Color(0.95, 0.90, 0.20)}
const TEXT := {Service.POLICE: "POLIZEI", Service.AMBULANCE: "RETTUNGSDIENST", Service.FIRE: "FEUERWEHR"}

var service := Service.TAXI
var mission := false           # Einsatzfahrt mit Blaulicht und Martinshorn
var target := Vector2.INF      # Einsatzort
var on_scene := false          # steht am Einsatzort (Blaulicht an, Horn aus)
var scene_t := 0.0
var _beacons: Array = []       # [MeshInstance3D, Phase]
var _beacon_lights: Array = []
var _siren: AudioStreamPlayer3D
var _blink := 0.0

static var _siren_stream: AudioStreamWAV
static var _beacon_mats := {}


static func model_for(s: int) -> String:
	var f: String = MODEL[s]
	if not ResourceLoader.exists(CarModel.DIR + f):
		f = "limousine_ober.glb" if s == Service.TAXI else "kombi_nord.glb"
	return f


func setup_service(t: Traffic, s: int, edge: int, dir: int, s_edge: float, with_mission: bool, tgt := Vector2.INF) -> void:
	service = s as Service
	mission = with_mission and s != Service.TAXI
	target = tgt
	setup(t, model_for(s), PAINT[s], edge, dir, s_edge)
	if s != Service.TAXI:
		_livery()
	if mission:
		goal = target if target != Vector2.INF else goal
		goal_k = 9.0
		_start_siren()


func _make_driver() -> void:
	super()
	honker = false
	if service == Service.TAXI:
		drive_fac = clampf(drive_fac, 0.98, 1.10)      # Taxifahrer: zügig, aber regeltreu
		patience = minf(patience, 9.0)
	if mission:
		drive_fac = 1.45
		accel *= 1.35
		brake_comf = 3.4
		yellow_b = 2.0
		t_gap = 0.9
		react_t = 0.3
		patience = 3.0
		a_lat = 3.4
		v_free = 150.0 / 3.6
		v_max = 160.0 / 3.6


func _livery() -> void:
	## Streifen an den Flanken, Schriftzug, Blaulichtbalken auf dem Dach
	var half_w := width * 0.5 + 0.012
	var h := _box_size.y
	var stripe_mat := StandardMaterial3D.new()
	stripe_mat.albedo_color = STRIPE[service]
	stripe_mat.roughness = 0.45
	for sd in [-1.0, 1.0]:
		var mi := MeshInstance3D.new()
		var q := QuadMesh.new()
		q.size = Vector2(length * 0.74, h * (0.16 if service != Service.AMBULANCE else 0.12))
		mi.mesh = q
		mi.material_override = stripe_mat
		mi.position = Vector3(sd * half_w, h * 0.52, 0.05)
		mi.rotation.y = PI * 0.5 * sd
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		model_root.add_child(mi)
		var lb := Label3D.new()
		lb.text = TEXT[service]
		lb.font_size = 64
		lb.pixel_size = 0.0034 if service == Service.POLICE else 0.0030
		lb.modulate = Color(1, 1, 1) if service != Service.FIRE else Color(0.1, 0.1, 0.1)
		lb.outline_size = 0
		lb.position = Vector3(sd * (half_w + 0.006), h * 0.52, 0.05)
		lb.rotation.y = PI * 0.5 * sd
		lb.visibility_range_end = 60.0
		model_root.add_child(lb)
	# Dachbalken mit zwei Blaulichtern
	var bar := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(width * 0.62, 0.07, 0.26)
	bar.mesh = bm
	var bmat := StandardMaterial3D.new()
	bmat.albedo_color = Color(0.12, 0.12, 0.13)
	bar.material_override = bmat
	var roof_z := -length * 0.08 if service == Service.POLICE else -length * 0.30
	bar.position = Vector3(0, h + 0.035, roof_z)
	model_root.add_child(bar)
	for sd in [-1.0, 1.0]:
		var dome := MeshInstance3D.new()
		var dm := BoxMesh.new()
		dm.size = Vector3(width * 0.22, 0.11, 0.22)
		dome.mesh = dm
		dome.material_override = _beacon_mat(false)
		dome.position = Vector3(sd * width * 0.2, h + 0.12, roof_z)
		model_root.add_child(dome)
		_beacons.append([dome, 0.0 if sd < 0.0 else 0.5])
	if mission:
		for sd in [-1.0, 1.0]:
			var ol := OmniLight3D.new()
			ol.light_color = Color(0.15, 0.35, 1.0)
			ol.omni_range = 16.0
			ol.light_energy = 0.0
			ol.shadow_enabled = false
			ol.position = Vector3(sd * width * 0.2, h + 0.35, roof_z)
			ol.distance_fade_enabled = true
			ol.distance_fade_begin = 90.0
			ol.distance_fade_length = 30.0
			model_root.add_child(ol)
			_beacon_lights.append(ol)


static func _beacon_mat(on: bool) -> StandardMaterial3D:
	if not _beacon_mats.has(on):
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.10, 0.22, 0.75, 0.9)
		m.roughness = 0.15
		if on:
			m.emission_enabled = true
			m.emission = Color(0.2, 0.45, 1.0)
			m.emission_energy_multiplier = 9.0
		_beacon_mats[on] = m
	return _beacon_mats[on]


static func siren_stream() -> AudioStreamWAV:
	## Martinshorn als Folgetonhorn (Quarte, rund 440/585 Hz, Wechsel alle 0,75 s), mit Obertönen – selbst erzeugt
	if _siren_stream != null:
		return _siren_stream
	var rate := 22050
	var n := int(rate * 3.0)
	var data := PackedByteArray()
	data.resize(n * 2)
	var ph := 0.0
	for i in n:
		var t := float(i) / rate
		var f := 440.0 if fposmod(t, 1.5) < 0.75 else 585.0
		ph += TAU * f / rate
		var edge := minf(fposmod(t, 0.75), 0.75 - fposmod(t, 0.75))
		var env := clampf(edge / 0.02, 0.0, 1.0)
		var v := (sin(ph) * 0.55 + sin(ph * 2.0) * 0.28 + sin(ph * 3.0) * 0.14 + sin(ph * 4.0) * 0.06) * env
		data.encode_s16(i * 2, int(clampf(v, -1.0, 1.0) * 26000.0))
	var st := AudioStreamWAV.new()
	st.format = AudioStreamWAV.FORMAT_16_BITS
	st.mix_rate = rate
	st.stereo = false
	st.data = data
	st.loop_mode = AudioStreamWAV.LOOP_FORWARD
	st.loop_begin = 0
	st.loop_end = n
	_siren_stream = st
	return st


func _start_siren() -> void:
	if _siren != null or OS.has_feature("headless") or DisplayServer.get_name() == "headless":
		return
	_siren = AudioStreamPlayer3D.new()
	_siren.stream = siren_stream()
	_siren.unit_size = 22.0
	_siren.max_distance = 420.0
	_siren.volume_db = 2.0
	_siren.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_PHYSICS_STEP
	_siren.bus = "Master"
	add_child(_siren)
	_siren.play()


var _path: Array = []          # berechneter Weg zum Einsatzort: [[kante, richtung], …]
var _path_tries := 0


func _choose_next() -> Array:
	if mission and target != Vector2.INF:
		goal = target
		if _path.is_empty() and _path_tries < 6:
			_path_tries += 1
			_path = traffic.route_to(cur_node, target)
		while not _path.is_empty():
			var step: Array = _path.pop_front()
			for o in traffic.out_edges.get(cur_node, []):
				if int(o[0]) == int(step[0]) and int(o[1]) == int(step[1]):
					return [int(step[0]), int(step[1])]
			_path.clear()                             # vom Weg abgekommen: beim nächsten Knoten neu rechnen
		return traffic.pick_next(cur_node, cur_edge, last_tangent, goal, goal_k)
	return super()


func _junction_cap(m: Dictionary, d_node: float, delta: float) -> float:
	var c := super(m, d_node, delta)
	if mission and not on_scene:
		# Sonderrechte: Kreuzung bei Rot/Wartepflicht mit höchstens 25 km/h überqueren statt anzuhalten
		return maxf(c, 7.0)
	return c


var _pass_t := 0.0             # Zeit (s), in der noch links vorbeigefahren wird


func _obstacle_cap() -> float:
	## Einsatzfahrt: an stehenden oder langsam fahrenden Fahrzeugen links vorbeifahren (die anderen fahren rechts
	## heran). Erst ausscheren, dann mit mäßigem Tempo vorbei; danach zurück in die Spur.
	var c := super()
	if not mission or on_scene:
		return c
	if c < 5.0:
		_pass_t = 4.0
	if _pass_t > 0.0:
		_pass_t -= THINK
		_yield_shift = 3.0
		if lane_shift < 2.0:
			lane_shift = move_toward(lane_shift, 3.0, 0.5)     # auch im Stand zügig ausscheren
			return maxf(c, 1.5)
		return maxf(c, 6.5)
	_yield_shift = 0.0
	return c


func _special_limit(delta: float) -> float:
	if not mission:
		return INF
	if on_scene:
		scene_t += delta
		return 0.0
	if target != Vector2.INF:
		var d := Vector2(pos.x, pos.z).distance_to(target)
		if d < 34.0 and speed < 1.0:
			arrive()
			return 0.0
		if d < 22.0:
			return 0.0
		if d < 80.0:
			return maxf(3.0, d * 0.22)
	return INF


func arrive() -> void:
	on_scene = true
	speed = 0.0
	if _siren:
		_siren.stop()


func _physics_process(delta: float) -> void:
	if mission and on_scene:
		scene_t += delta                             # steht am Einsatzort
		return
	super(delta)


func end_mission() -> void:
	## Einsatz beendet: normal weiterfahren
	mission = false
	on_scene = false
	target = Vector2.INF
	goal = Vector2.INF
	goal_k = 1.2
	if _siren:
		_siren.stop()
	for b in _beacons:
		(b[0] as MeshInstance3D).material_override = _beacon_mat(false)
	for l in _beacon_lights:
		(l as OmniLight3D).light_energy = 0.0
	super._make_driver()


func _process(delta: float) -> void:
	if not mission or _beacons.is_empty():
		return
	_blink = fposmod(_blink + delta * 2.2, 1.0)
	for i in _beacons.size():
		var b: Array = _beacons[i]
		var on := fposmod(_blink + float(b[1]), 1.0) < 0.28 or (fposmod(_blink + float(b[1]), 1.0) > 0.38 and fposmod(_blink + float(b[1]), 1.0) < 0.5)
		(b[0] as MeshInstance3D).material_override = _beacon_mat(on)
		if i < _beacon_lights.size():
			(_beacon_lights[i] as OmniLight3D).light_energy = 5.0 if on else 0.0
