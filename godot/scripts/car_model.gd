class_name CarModel
extends RefCounted
## Lädt ein Fahrzeug-Modell und setzt die Spiel-Materialien (Lack, Glas, Leuchten).

const DIR := "res://assets/models/cars/"
static var _glass: StandardMaterial3D
static var shared_emit := {}   # Name -> Array[StandardMaterial3D] (nur für KI-Autos)


static func glass_material() -> StandardMaterial3D:
	if _glass == null:
		_glass = StandardMaterial3D.new()
		_glass.albedo_color = Color(0.05, 0.07, 0.09, 0.32)
		_glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_glass.roughness = 0.03
		_glass.metallic = 0.0
		_glass.metallic_specular = 1.0
		_glass.cull_mode = BaseMaterial3D.CULL_BACK
	return _glass


static func paint_material(color: Color, metallic: float = 0.55) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.resource_name = "CarPaint"
	m.albedo_color = color
	m.metallic = metallic
	m.metallic_specular = 0.6
	m.roughness = 0.3
	m.clearcoat_enabled = true
	m.clearcoat = 1.0
	m.clearcoat_roughness = 0.04
	return m


## Gibt {"root": Node3D, "wheels": {"FL": Node3D, ...}, "emit": {name: material}, "paint": material} zurück.
static func make(file: String, paint: Color, own_emit: bool, metallic: float = 0.55) -> Dictionary:
	var ps := load(DIR + file) as PackedScene
	var root := ps.instantiate() as Node3D
	var paint_mat := paint_material(paint, metallic)
	var emit := {}
	var stack: Array = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		if n is MeshInstance3D:
			var mi := n as MeshInstance3D
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			for i in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(i)
				if m == null:
					continue
				var nm := String(m.resource_name)
				match nm:
					"CarPaint", "TramPaint":
						mi.set_surface_override_material(i, paint_mat)
					"Glass":
						mi.set_surface_override_material(i, glass_material())
					"HeadlightEmit", "TaillightEmit", "BrakeLightEmit", "IndicatorEmit", "TaxiSignEmit":
						var mm: StandardMaterial3D = m
						if own_emit:
							mm = (m as StandardMaterial3D).duplicate()
							mi.set_surface_override_material(i, mm)
						mm.emission_enabled = true
						mm.emission = {
							"HeadlightEmit": Color(1.0, 0.95, 0.85),
							"TaillightEmit": Color(1.0, 0.05, 0.02),
							"BrakeLightEmit": Color(1.0, 0.05, 0.02),
							"IndicatorEmit": Color(1.0, 0.55, 0.05),
							"TaxiSignEmit": Color(1.0, 0.9, 0.55),
						}[nm]
						mm.emission_energy_multiplier = 0.0
						emit[nm] = mm
						if not own_emit:
							if not shared_emit.has(nm):
								shared_emit[nm] = []
							if not shared_emit[nm].has(mm):
								shared_emit[nm].append(mm)
	var wheels := {}
	for k in ["FL", "FR", "RL", "RR"]:
		var w := root.find_child("Wheel_" + k, true, false)
		if w:
			wheels[k] = w
	RenderUtil.gi_off(root)          # Spielerauto bewegt sich -> nicht in SDFGI
	return {"root": root, "wheels": wheels, "emit": emit, "paint": paint_mat}


# --- KI-Fahrzeuge: gemeinsame Materialien, Leuchten über Instanz-Uniforms ---------------------------
static var _ai_paint := {}       # Farbe (html) -> Material
static var _ai_light := {}       # Art -> ShaderMaterial (car_lights.gdshader)
static var ai_emit := {}         # "InteriorEmit"/"DestinationEmit" -> StandardMaterial3D (Bus)


static func _light_mat(kind: int) -> ShaderMaterial:
	if not _ai_light.has(kind):
		var m := ShaderMaterial.new()
		m.shader = load("res://shaders/car_lights.gdshader")
		m.set_shader_parameter("kind", kind)
		var base := [Color(0.92, 0.92, 0.9), Color(0.9, 0.5, 0.1), Color(0.45, 0.04, 0.03), Color(0.5, 0.04, 0.03)][kind] as Color
		var glow := [Color(1.0, 0.95, 0.85), Color(1.0, 0.55, 0.05), Color(1.0, 0.05, 0.02), Color(1.0, 0.04, 0.02)][kind] as Color
		m.set_shader_parameter("base_col", Vector3(base.r, base.g, base.b))
		m.set_shader_parameter("glow_col", Vector3(glow.r, glow.g, glow.b))
		_ai_light[kind] = m
	return _ai_light[kind]


## Wie make(), aber für KI-Verkehr: Lack je Farbe geteilt, Leuchten als ein Shader je Art (Zustand je Auto über
## MeshInstance3D.set_instance_shader_parameter: lights_on, brake_on, ind_l, ind_r).
## Rückgabe: {"root", "wheels", "lights": [MeshInstance3D], "size": Vector3 (Kollisionsbox) }
static func make_ai(file: String, paint: Color) -> Dictionary:
	var ps := load(DIR + file) as PackedScene
	var root := ps.instantiate() as Node3D
	var key := paint.to_html(false)
	if not _ai_paint.has(key):
		_ai_paint[key] = paint_material(paint, 0.35)
	var paint_mat: Material = _ai_paint[key]
	var lights: Array = []
	var aabb := AABB()
	var first := true
	var stack: Array = [[root, Transform3D.IDENTITY]]
	while not stack.is_empty():
		var it: Array = stack.pop_back()
		var n: Node = it[0]
		var xf: Transform3D = it[1]
		if n is Node3D and n != root:
			xf = xf * (n as Node3D).transform
		for c in n.get_children():
			stack.append([c, xf])
		if not (n is MeshInstance3D):
			continue
		var mi := n as MeshInstance3D
		var nm0 := String(mi.name)
		# Schatten nur von der Karosserie; Räder/Innenraum/Glas/Leuchten nicht (spart viele Schatten-Draws)
		var body_like := nm0.begins_with("Body") or nm0.begins_with("Front_Body") or nm0.begins_with("Rear_Body") or nm0 == "Car" or nm0 == "Bus"
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if body_like else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if nm0.contains("Interior"):
			mi.visibility_range_end = 45.0
		elif nm0.contains("Lights") or nm0.contains("Glass"):
			mi.visibility_range_end = 160.0
		if not String(mi.name).begins_with("Wheel"):
			var a := xf * mi.mesh.get_aabb()
			aabb = a if first else aabb.merge(a)
			first = false
		var has_light := false
		for i in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(i)
			if m == null:
				continue
			match String(m.resource_name):
				"CarPaint", "TramPaint":
					mi.set_surface_override_material(i, paint_mat)
				"Glass":
					mi.set_surface_override_material(i, glass_material())
				"HeadlightEmit":
					mi.set_surface_override_material(i, _light_mat(0))
					has_light = true
				"IndicatorEmit":
					mi.set_surface_override_material(i, _light_mat(1))
					has_light = true
				"TaillightEmit":
					mi.set_surface_override_material(i, _light_mat(2))
					has_light = true
				"BrakeLightEmit":
					mi.set_surface_override_material(i, _light_mat(3))
					has_light = true
				"InteriorEmit", "DestinationEmit":
					var nm := String(m.resource_name)
					if not ai_emit.has(nm):
						var em := (m as StandardMaterial3D).duplicate() as StandardMaterial3D if m is StandardMaterial3D else StandardMaterial3D.new()
						em.emission_enabled = true
						em.emission = Color(1.0, 0.95, 0.85) if nm == "InteriorEmit" else Color(1.0, 0.62, 0.1)
						em.emission_energy_multiplier = 0.0 if nm == "InteriorEmit" else 1.6
						ai_emit[nm] = em
					mi.set_surface_override_material(i, ai_emit[nm])
		if has_light:
			lights.append(mi)
	RenderUtil.gi_off(root)          # bewegt -> nicht in SDFGI
	var wheels := {}
	for k in ["FL", "FR", "RL", "RR", "ML", "MR"]:
		var w := root.find_child("Wheel_" + k, true, false)
		if w:
			wheels[k] = w
	var size := Vector3(1.8, 1.3, 4.4)
	if not first:
		size = Vector3(maxf(aabb.size.x - 0.25, 1.4), maxf(aabb.size.y - 0.4, 0.9), maxf(aabb.size.z - 0.1, 3.0))
	return {"root": root, "wheels": wheels, "lights": lights, "size": size}
