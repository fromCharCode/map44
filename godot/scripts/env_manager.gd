class_name EnvManager
extends Node3D
## Umgebung: Himmel, Sonne/Mond, Tageszeit, Nebel, Nachbearbeitung.

const LATITUDE := 51.05
var day_of_year := 150.0       # Ende Mai
var hours := 15.0
var time_scale := 0.0          # Spielstunden pro Sekunde (0 = Zeit steht)

var sun: DirectionalLight3D
var moon: DirectionalLight3D
var world_env: WorldEnvironment
var env: Environment
var sky_mat: ShaderMaterial
var cam_attr: CameraAttributesPractical
var night_value := 0.0
var quality := 2               # 0 niedrig, 1 mittel, 2 hoch
var render_scale := -1.0       # 3D-Auflösung; < 1 = FSR2-Hochskalierung (ersetzt TAA); -1 = automatisch
const WEATHER_NAMES := ["Klar", "Bewölkt", "Regen", "Nach dem Regen"]
# je Wetter: [Nässe, Wolkendecke, Wolkendunkel, Sonne, Umgebungslicht, Dunst]
const WEATHER := [[0.0, 0.42, 0.0, 1.0, 1.0, 1.0], [0.0, 0.82, 0.35, 0.45, 0.9, 1.6],
	[1.0, 0.96, 0.78, 0.18, 0.75, 3.2], [0.75, 0.6, 0.25, 0.75, 0.95, 1.8]]
var weather := 0
var _wet := 0.0                # aktuelle Nässe (blendet weich)
var rain: GPUParticles3D


static func register_globals() -> void:
	RenderingServer.global_shader_parameter_add("night", RenderingServer.GLOBAL_VAR_TYPE_FLOAT, 0.0)
	RenderingServer.global_shader_parameter_add("wetness", RenderingServer.GLOBAL_VAR_TYPE_FLOAT, 0.0)
	RenderingServer.global_shader_parameter_add("signal_clock", RenderingServer.GLOBAL_VAR_TYPE_FLOAT, 0.0)


func setup(noise: ImageTexture) -> void:
	sky_mat = ShaderMaterial.new()
	sky_mat.shader = load("res://shaders/sky.gdshader")
	sky_mat.set_shader_parameter("cloud_noise", noise)
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_256

	env = Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 1.0
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_white = 6.0
	env.glow_enabled = true
	env.glow_intensity = 0.8
	env.glow_strength = 1.0
	env.glow_bloom = 0.14
	env.glow_hdr_threshold = 0.95
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.14
	env.adjustment_saturation = 0.9
	env.adjustment_color_correction = _grade_lut()
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_EXPONENTIAL
	env.fog_density = 0.0005
	env.fog_aerial_perspective = 0.55
	env.fog_sky_affect = 0.12
	env.fog_sun_scatter = 0.25
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.0009
	env.volumetric_fog_length = 120.0
	env.volumetric_fog_gi_inject = 0.5
	env.volumetric_fog_anisotropy = 0.55
	env.ssao_enabled = true
	env.ssao_radius = 1.6
	env.ssao_intensity = 2.2
	env.ssao_power = 1.6
	env.ssil_enabled = true
	env.ssil_intensity = 0.8
	env.ssr_enabled = true
	env.ssr_max_steps = 96
	env.ssr_fade_in = 0.15
	env.ssr_fade_out = 2.0
	env.ssr_depth_tolerance = 0.3
	env.sdfgi_enabled = true
	env.sdfgi_cascades = 4
	env.sdfgi_min_cell_size = 0.3
	env.sdfgi_use_occlusion = true
	env.sdfgi_bounce_feedback = 0.5
	env.sdfgi_energy = 1.0
	env.sdfgi_read_sky_light = true

	cam_attr = CameraAttributesPractical.new()
	cam_attr.auto_exposure_enabled = true
	cam_attr.auto_exposure_scale = 0.35
	cam_attr.auto_exposure_speed = 0.8
	cam_attr.auto_exposure_min_sensitivity = 50.0
	cam_attr.auto_exposure_max_sensitivity = 2500.0

	world_env = WorldEnvironment.new()
	world_env.environment = env
	world_env.camera_attributes = cam_attr
	add_child(world_env)

	sun = DirectionalLight3D.new()
	sun.name = "Sun"
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	# Messung (perf_run): Sonnenschatten sind der größte Einzelposten (2,3–4,5 ms bei 1080p), weil jede Kaskade
	# alle Werfer erneut zeichnet. Über 450 m fallen Schatten kaum auf -> kürzere Reichweite, feinere Nahstufen.
	sun.directional_shadow_max_distance = 450.0
	sun.directional_shadow_blend_splits = true
	sun.directional_shadow_split_1 = 0.07
	sun.directional_shadow_split_2 = 0.2
	sun.directional_shadow_split_3 = 0.48
	sun.shadow_bias = 0.04
	sun.shadow_normal_bias = 1.6
	sun.shadow_blur = 1.2
	sun.light_angular_distance = 0.45
	sun.light_specular = 1.0
	add_child(sun)

	moon = DirectionalLight3D.new()
	moon.name = "Moon"
	moon.light_color = Color(0.55, 0.68, 1.0)
	moon.light_energy = 0.0
	moon.shadow_enabled = false
	add_child(moon)
	_add_post_fx()
	apply_quality(quality)
	set_time(hours)


static func _grade_lut() -> GradientTexture1D:
	## Farbkorrektur: kühlere Schatten, warme Lichter (nach Luminanz)
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.35, 0.7, 1.0])
	g.colors = PackedColorArray([Color(0.02, 0.03, 0.06), Color(0.30, 0.33, 0.37), Color(0.74, 0.72, 0.68), Color(1.0, 0.97, 0.90)])
	var t := GradientTexture1D.new()
	t.gradient = g
	t.width = 256
	return t


func _add_post_fx() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 1
	layer.name = "PostFX"
	var rect := ColorRect.new()
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/post_fx.gdshader")
	rect.material = m
	layer.add_child(rect)
	add_child(layer)


func apply_quality(q: int) -> void:
	quality = q
	env.sdfgi_enabled = q >= 2
	env.ssao_enabled = q >= 1
	env.ssil_enabled = q >= 2
	env.ssr_enabled = q >= 1
	env.volumetric_fog_enabled = q >= 2
	_apply_viewport()
	RenderingServer.directional_shadow_atlas_set_size(4096 if q >= 2 else 2048, true)
	RenderingServer.directional_soft_shadow_filter_set_quality(
		RenderingServer.SHADOW_QUALITY_SOFT_MEDIUM if q >= 2 else (RenderingServer.SHADOW_QUALITY_SOFT_VERY_LOW if q == 1 else RenderingServer.SHADOW_QUALITY_HARD))
	sun.directional_shadow_max_distance = [220.0, 330.0, 450.0][q]
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS if q >= 1 else DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	sun.shadow_enabled = true


func set_render_scale(sc: float) -> void:
	render_scale = -1.0 if sc <= 0.0 else clampf(sc, 0.5, 1.0)
	_apply_viewport()


static func auto_scale_for(out_h: float) -> float:
	## Automatische 3D-Auflösung: intern etwa 1300 Zeilen, Rest skaliert FSR2 hoch
	## (4K: 60 % ≈ 2300×1300, 1440p: 85 %, bis 1200 Zeilen nativ). 4K nativ kostete ~10 ms GPU je Bild mehr.
	if out_h >= 2000.0:
		return 0.6
	if out_h >= 1350.0:
		return 0.85
	return 1.0


func effective_scale() -> float:
	if render_scale > 0.0:
		return render_scale
	var vp := get_viewport()
	var h := vp.get_visible_rect().size.y if vp else 1080.0
	return auto_scale_for(h)


var _size_hooked := false


func _apply_viewport() -> void:
	var vp := get_viewport()
	if vp == null:
		return
	if not _size_hooked:
		_size_hooked = true
		vp.size_changed.connect(func(): if render_scale <= 0.0: _apply_viewport())
	var sc := effective_scale()
	var fsr := sc < 0.99
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR2 if fsr else Viewport.SCALING_3D_MODE_BILINEAR
	vp.scaling_3d_scale = sc
	vp.msaa_3d = Viewport.MSAA_2X if quality == 1 and not fsr else Viewport.MSAA_DISABLED
	vp.use_taa = quality >= 2 and not fsr
	# GI (SDFGI/Voxel) in halber Auflösung, sobald intern mehr als ~1300 Zeilen gerechnet werden
	RenderingServer.gi_set_use_half_resolution(vp.get_visible_rect().size.y * sc > 1300.0)


func sun_vector(h: float) -> Vector3:
	## Richtung ZUR Sonne (Spielkoordinaten: +x Ost, -z Nord).
	var dec := deg_to_rad(23.44) * sin(TAU * (day_of_year - 81.0) / 365.0)
	var lat := deg_to_rad(LATITUDE)
	var ha := deg_to_rad((h - 12.0) * 15.0)
	var sin_el := sin(lat) * sin(dec) + cos(lat) * cos(dec) * cos(ha)
	var el := asin(clampf(sin_el, -1.0, 1.0))
	var cos_az := (sin(dec) - sin(el) * sin(lat)) / maxf(cos(el) * cos(lat), 1e-4)
	var az := acos(clampf(cos_az, -1.0, 1.0))
	if ha > 0.0:
		az = TAU - az   # Nachmittag: westlich
	# Azimut von Nord im Uhrzeigersinn -> x = Ost, z = -Nord
	return Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el))


func set_time(h: float) -> void:
	hours = fposmod(h, 24.0)
	var sv := sun_vector(hours)
	var mv := sun_vector(hours + 12.0 + 4.0)
	mv.y = -sv.y * 0.9 + 0.05
	mv = mv.normalized()
	var elev := sv.y

	sun.look_at_from_position(Vector3.ZERO, -sv, Vector3.UP if absf(sv.y) < 0.99 else Vector3.RIGHT)
	moon.look_at_from_position(Vector3.ZERO, -mv, Vector3.UP if absf(mv.y) < 0.99 else Vector3.RIGHT)
	var day := smoothstep(-0.06, 0.12, elev)
	var warm := 1.0 - smoothstep(0.0, 0.42, elev)
	sun.light_color = Color(1.0, 0.97, 0.92).lerp(Color(1.0, 0.55, 0.28), warm)
	var wcfg: Array = WEATHER[weather]
	sun.light_energy = lerpf(0.0, 4.4, day) * lerpf(0.55, 1.0, smoothstep(0.0, 0.3, elev)) * float(wcfg[3])
	sun.visible = elev > -0.08
	moon.light_energy = lerpf(0.35, 0.0, day) * (1.0 if mv.y > 0.0 else 0.0)
	moon.visible = mv.y > 0.0
	var night := 1.0 - smoothstep(-0.12, 0.08, elev)
	night_value = night
	RenderingServer.global_shader_parameter_set("night", night)
	sky_mat.set_shader_parameter("sun_dir", sv)
	sky_mat.set_shader_parameter("moon_dir", mv)
	env.ambient_light_energy = lerpf(0.5, 1.1, day) * float(wcfg[4])
	env.fog_light_color = Color(0.70, 0.74, 0.80).lerp(Color(0.02, 0.03, 0.06), night)
	env.fog_density = lerpf(0.0007, 0.0005, day) * float(wcfg[5])
	sky_mat.set_shader_parameter("cloud_cover", float(wcfg[1]))
	sky_mat.set_shader_parameter("cloud_dark", float(wcfg[2]))
	env.volumetric_fog_albedo = Color(0.85, 0.9, 1.0).lerp(Color(0.12, 0.16, 0.3), night)
	env.volumetric_fog_emission = Color(0, 0, 0)


func set_weather(w: int) -> void:
	weather = posmod(w, WEATHER.size())
	if rain == null:
		_make_rain()
	rain.emitting = weather == 2
	set_time(hours)


func _make_rain() -> void:
	rain = GPUParticles3D.new()
	rain.name = "Rain"
	rain.amount = 9000
	rain.lifetime = 1.6
	rain.preprocess = 1.0
	rain.local_coords = false
	rain.emitting = false
	rain.visibility_aabb = AABB(Vector3(-40, -40, -40), Vector3(80, 80, 80))
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(28, 2, 28)
	pm.direction = Vector3(0.08, -1, 0.04)
	pm.spread = 3.0
	pm.initial_velocity_min = 11.0
	pm.initial_velocity_max = 14.0
	pm.gravity = Vector3(0, -2, 0)
	rain.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.01, 0.5)
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/rain_drop.gdshader")
	q.material = m
	rain.draw_pass_1 = q
	rain.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(rain)


func _process(delta: float) -> void:
	# Nässe weich nachführen (Straßen trocknen langsam ab), Regen folgt der Kamera
	var target_wet := float(WEATHER[weather][0])
	_wet = move_toward(_wet, target_wet, delta * (0.25 if target_wet > _wet else 0.04))
	RenderingServer.global_shader_parameter_set("wetness", _wet)
	if rain != null and rain.emitting:
		var cam := get_viewport().get_camera_3d()
		if cam:
			rain.global_position = cam.global_position + Vector3(0, 12, 0) - cam.global_transform.basis.z * 10.0
	if time_scale != 0.0:
		set_time(hours + delta * time_scale)
