class_name SkidFX
extends Node3D
## Reifenspuren und Reifenqualm des Spielerautos.
## Spuren: Ring aus MAX_SEG flachen Streifen (ein MultiMesh, immer gezeichnet, ~0,1 ms), je Rad ein neues Segment
## alle 25 cm, solange das Rad deutlich rutscht (Längs- oder Querschlupf jenseits der Haftgrenze, Handbremse).
## Qualm: GPU-Partikel an den Hinterrädern bei starkem Schlupf (Burnout, Drift).

const MAX_SEG := 3000
const SEG_LEN := 0.25

var car: PlayerCar
var mm: MultiMesh
var _next := 0
var _last := {}                  # Rad -> Vector3 (letzter Spurpunkt) oder null
var _smoke := {}                 # Rad -> GPUParticles3D


func setup(c: PlayerCar) -> void:
	car = c
	physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	var pm := PlaneMesh.new()
	pm.size = Vector2(1.0, 1.0)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.025, 0.025, 0.025, 1.0)
	mat.vertex_color_use_as_albedo = true          # Instanzfarbe (Alpha = Deckkraft)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.roughness = 0.75
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.render_priority = 1
	pm.material = mat
	mm = MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = pm
	mm.instance_count = MAX_SEG                    # Puffer startet mit Nullen = unsichtbar (Skalierung 0)
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	mi.custom_aabb = AABB(Vector3(-30000, -600, -30000), Vector3(60000, 2000, 60000))
	add_child(mi)
	for k in ["RL", "RR"]:
		_smoke[k] = _make_smoke()


func _make_smoke() -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.amount = 48
	p.lifetime = 2.4
	p.local_coords = false
	p.emitting = false
	p.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	p.visibility_aabb = AABB(Vector3(-12, -2, -12), Vector3(24, 10, 24))
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, 1, 0)
	pm.spread = 70.0
	pm.initial_velocity_min = 0.4
	pm.initial_velocity_max = 1.6
	pm.gravity = Vector3(0, 0.35, 0)
	pm.damping_min = 0.6
	pm.damping_max = 1.2
	pm.scale_min = 0.8
	pm.scale_max = 1.4
	var sc := Curve.new()
	sc.add_point(Vector2(0.0, 0.35))
	sc.add_point(Vector2(1.0, 1.0))
	var sct := CurveTexture.new()
	sct.curve = sc
	pm.scale_curve = sct
	var g := Gradient.new()
	g.set_color(0, Color(0.85, 0.85, 0.85, 0.42))
	g.set_color(1, Color(0.8, 0.8, 0.82, 0.0))
	var gt := GradientTexture1D.new()
	gt.gradient = g
	pm.color_ramp = gt
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(1.6, 1.6)
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.vertex_color_use_as_albedo = true
	m.albedo_texture = _soft_dot()
	m.roughness = 1.0
	q.material = m
	p.draw_pass_1 = q
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(p)
	return p


static var _dot: ImageTexture


static func _soft_dot() -> ImageTexture:
	if _dot == null:
		var img := Image.create_empty(64, 64, false, Image.FORMAT_RGBA8)
		for y in 64:
			for x in 64:
				var d := Vector2(x - 31.5, y - 31.5).length() / 31.5
				var a := clampf(1.0 - d, 0.0, 1.0)
				img.set_pixel(x, y, Color(1, 1, 1, a * a))
		_dot = ImageTexture.create_from_image(img)
	return _dot


func _process(_delta: float) -> void:
	if car == null or not is_instance_valid(car):
		return
	var spd := absf(car.speed)
	for k in car.wheels:
		var w: Dictionary = car.wheels[k]
		var inten := 0.0
		if w.get("contact", false) and not w.get("broken", false):
			var kap := absf(float(w.get("kappa", 0.0)))
			var al := absf(float(w.get("alpha_f", 0.0)))
			inten = clampf((kap - 0.2) * 2.5, 0.0, 1.0) + clampf((al - 0.2) * 3.5, 0.0, 1.0)
			if car.in_handbrake and bool(w["rear"]) and spd > 3.0:
				inten = maxf(inten, 0.8)
			if spd < 0.8 and kap < 0.6:
				inten = 0.0
		inten = clampf(inten, 0.0, 1.0)
		var n: Vector3 = w.get("normal", Vector3.UP)
		var p: Vector3 = (w.get("pos", Vector3.ZERO) as Vector3) + n * 0.03
		if inten > 0.08:
			var a = _last.get(k)
			if a == null:
				_last[k] = p
			else:
				var L := (p - (a as Vector3)).length()
				if L > 3.0:
					_last[k] = p
				elif L >= SEG_LEN:
					_add_seg(a, p, n, inten)
					_last[k] = p
		else:
			_last[k] = null
		if _smoke.has(k):
			var sm: GPUParticles3D = _smoke[k]
			var burn := inten > 0.45 and (spd > 2.0 or absf(float(w.get("kappa", 0.0))) > 0.6)
			sm.emitting = burn
			if burn:
				sm.global_position = p + Vector3(0, 0.25, 0)
				sm.amount_ratio = clampf(inten, 0.3, 1.0)


func _add_seg(a: Vector3, b: Vector3, n: Vector3, inten: float) -> void:
	var d := b - a
	var L := d.length()
	if L < 0.01:
		return
	d /= L
	var side := n.cross(d).normalized()
	var basis := Basis(side * 0.23, n, d * (L + 0.04))
	mm.set_instance_transform(_next, Transform3D(basis, (a + b) * 0.5))
	mm.set_instance_color(_next, Color(1.0, 1.0, 1.0, 0.45 + 0.4 * inten))
	_next = (_next + 1) % MAX_SEG
