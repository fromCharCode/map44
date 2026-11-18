extends SceneTree
## Cockpit-Prüfbilder ohne Stadt (schnell):
##   godot --path . --resolution 1920x1080 -s res://scripts/dev/cockpit_shot.gd -- --out=<ordner> [--night]
## Stellt das Spielerauto auf eine Ebene mit Himmel, Sonne und ein paar Quadern und speichert die Fahrerperspektive
## aus mehreren Blickrichtungen (vorn, links, rechts, hinten, unten, Lenkeinschlag).

var car: PlayerCar
var rig: CamRig
var out_dir := "user://cockpit"
var frame := 0
var shots := [
	["vorn", 0.0, 0.0, 0.0],
	["lenk_links", 0.0, 0.0, -0.6],
	["links", 1.2, 0.0, 0.0],
	["rechts", -1.0, 0.0, 0.0],
	["hinten", PI, 0.0, 0.0],
	["unten", 0.0, -0.45, 0.25],
]
var si := 0
var night := false


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--out="):
			out_dir = a.substr(6)
		if a == "--night":
			night = true
	Controls.setup()
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var psm := ProceduralSkyMaterial.new()
	if night:
		psm.sky_top_color = Color(0.01, 0.012, 0.03)
		psm.sky_horizon_color = Color(0.03, 0.035, 0.06)
		psm.ground_horizon_color = Color(0.03, 0.035, 0.06)
		psm.ground_bottom_color = Color(0.01, 0.01, 0.015)
	sky.sky_material = psm
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	e.ssao_enabled = true
	env.environment = e
	root.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-38, -140, 0)
	sun.shadow_enabled = true
	sun.light_energy = 0.02 if night else 1.2
	root.add_child(sun)
	var ground := StaticBody3D.new()
	ground.collision_layer = 1
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(400, 2, 400)
	cs.shape = bs
	ground.add_child(cs)
	ground.position = Vector3(0, -1, 0)
	var gm := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 400)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.22, 0.22, 0.23)
	pm.material = mat
	gm.mesh = pm
	gm.position = Vector3(0, 1.0, 0)
	ground.add_child(gm)
	root.add_child(ground)
	for i in 24:
		var b := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(10, 8 + (i * 7) % 12, 14)
		var m2 := StandardMaterial3D.new()
		m2.albedo_color = Color.from_hsv(0.08 + 0.02 * (i % 4), 0.18, 0.75)
		bm.material = m2
		b.mesh = bm
		b.position = Vector3(-14.0 if i % 2 == 0 else 14.0, bm.size.y * 0.5, -10.0 - 18.0 * (i / 2) + 60.0)
		root.add_child(b)
	for i in 30:
		var l := MeshInstance3D.new()
		var lm := BoxMesh.new()
		lm.size = Vector3(0.14, 0.01, 3.0)
		var m3 := StandardMaterial3D.new()
		m3.albedo_color = Color(0.9, 0.9, 0.88)
		lm.material = m3
		l.mesh = lm
		l.position = Vector3(1.6, 0.005, 60.0 - i * 9.0)
		root.add_child(l)
	car = PlayerCar.new()
	root.add_child(car)
	car.setup()
	car.override_input = true
	car.damage_enabled = false
	car.lights_on = night
	car.global_transform = Transform3D(Basis.IDENTITY, Vector3(0, 0.0, 30.0))
	car.linear_velocity = Vector3(0, 0, -12.0)
	for k in car.wheels:
		car.wheels[k]["omega"] = 12.0 / PlayerCar.WHEEL_R
	car.gear = 3
	car.in_throttle = 0.25
	rig = CamRig.new()
	root.add_child(rig)
	rig.setup(car)
	rig.mode = 2
	DirAccess.make_dir_recursive_absolute(out_dir)
	process_frame.connect(_frame)


func _frame() -> void:
	frame += 1
	if si >= shots.size():
		return
	var s: Array = shots[si]
	rig.look_yaw = s[1]
	rig.look_pitch = s[2]
	rig._mouse_t = 0.0
	car.in_steer = s[3]
	if frame % 45 == 0:
		var img := root.get_texture().get_image()
		var path := out_dir.path_join("cockpit_%s%s.png" % [s[0], "_nacht" if night else ""])
		img.save_png(path)
		print("Bild: ", path, "  v=%.0f km/h Lenkwinkel %.1f°" % [car.get_speed_kmh(), rad_to_deg(car.steer_angle)])
		si += 1
		if si >= shots.size():
			quit()
