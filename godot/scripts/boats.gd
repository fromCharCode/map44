class_name Boats
extends Node3D
## Elbdampfer: fahren auf der Elbe-Mittellinie hin und her (Raddampfer der Weißen Flotte).
## Alle Schiffe laufen immer mit (nur ein Zahlenwert); sichtbar/instanziiert nur in der Nähe des Fokus.

const MODEL := "res://assets/models/props/dampfer.glb"
const SHOW_R := 2600.0

var pts: Array = []          # Vector2 (x, z)
var cum: Array = []          # kumulierte Länge
var total := 0.0
var plane := [0.0, 0.0, -8.4]
var boats: Array = []        # {s, dir, v, node, wheel}
var focus := Vector3.ZERO
var scene: PackedScene
var rng := RandomNumberGenerator.new()
var enabled := true


func setup(count: int) -> void:
	count = clampi(count, 0, 14)
	rng.seed = 1913
	var d = JSON.parse_string(FileAccess.get_file_as_string(DataPaths.file("elbe.json")))
	if d == null:
		return
	for p in d["pts"]:
		pts.append(Vector2(p[0], p[1]))
	plane = d["plane"]
	var acc := 0.0
	cum.append(0.0)
	for i in pts.size() - 1:
		acc += (pts[i + 1] - pts[i]).length()
		cum.append(acc)
	total = acc
	if ResourceLoader.exists(MODEL):
		scene = load(MODEL) as PackedScene
	# Fahrstrecke: Mitte der Stadt (ca. 9 km Elbabschnitt um den Altmarkt)
	var s_alt := _nearest_s(Vector2(494.0, -260.0))
	for i in count:
		var b := {"s": s_alt + rng.randf_range(-4200.0, 4200.0), "dir": 1 if i % 2 == 0 else -1,
				"v": rng.randf_range(3.6, 5.2), "node": null, "wheel": 0.0}
		boats.append(b)


func _nearest_s(p: Vector2) -> float:
	var best := 1e18
	var bs := 0.0
	for i in pts.size() - 1:
		var a: Vector2 = pts[i]
		var ab: Vector2 = pts[i + 1] - a
		var t := clampf((p - a).dot(ab) / maxf(ab.length_squared(), 0.01), 0.0, 1.0)
		var d := (a + ab * t).distance_to(p)
		if d < best:
			best = d
			bs = cum[i] + ab.length() * t
	return bs


func point_at(s: float) -> Vector2:
	s = clampf(s, 0.0, total)
	var lo := 0
	var hi := cum.size() - 1
	while hi - lo > 1:
		var mid := (lo + hi) / 2
		if cum[mid] <= s:
			lo = mid
		else:
			hi = mid
	var seg := float(cum[hi]) - float(cum[lo])
	return (pts[lo] as Vector2).lerp(pts[hi], (s - cum[lo]) / maxf(seg, 0.001))


func water_y(x: float, z: float) -> float:
	return plane[0] * x + plane[1] * z + plane[2]


func _process(delta: float) -> void:
	if not enabled or pts.is_empty():
		return
	for b in boats:
		var v: float = b["v"]
		b["s"] = float(b["s"]) + float(b["dir"]) * v * delta
		var turn_lo := 0.0
		if b["s"] < 200.0:
			b["dir"] = 1
		elif b["s"] > total - 200.0:
			b["dir"] = -1
		var p := point_at(b["s"])
		var near := Vector2(p.x - focus.x, p.y - focus.z).length() < SHOW_R
		if near and b["node"] == null and scene != null:
			var n := scene.instantiate() as Node3D
			RenderUtil.gi_off(n)
			add_child(n)
			b["node"] = n
			_setup_effects(b)
		elif not near and b["node"] != null:
			(b["node"] as Node).queue_free()
			b["node"] = null
		if b["node"] != null:
			_update_boat(b, delta)


func _setup_effects(b: Dictionary) -> void:
	var n: Node3D = b["node"]
	for nm in ["SmokeFront", "SmokeBack"]:
		var e := n.find_child(nm, true, false) as Node3D
		if e == null:
			continue
		var ps := GPUParticles3D.new()
		ps.amount = 40
		ps.lifetime = 7.0
		ps.local_coords = false
		ps.visibility_aabb = AABB(Vector3(-60, -10, -60), Vector3(120, 80, 120))
		var pm := ParticleProcessMaterial.new()
		pm.direction = Vector3(0, 1, 0)
		pm.spread = 12.0
		pm.initial_velocity_min = 2.0
		pm.initial_velocity_max = 3.5
		pm.gravity = Vector3(0.6, 0.4, 0)
		pm.scale_min = 1.2
		pm.scale_max = 3.2
		pm.color = Color(0.22, 0.22, 0.24, 0.55)
		var curve := Curve.new()
		curve.add_point(Vector2(0, 0.3))
		curve.add_point(Vector2(1, 2.2))
		var ct := CurveTexture.new()
		ct.curve = curve
		pm.scale_curve = ct
		ps.process_material = pm
		var q := QuadMesh.new()
		q.size = Vector2(1.6, 1.6)
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		m.vertex_color_use_as_albedo = true
		m.albedo_color = Color(0.25, 0.25, 0.27, 0.5)
		m.albedo_texture = _puff_tex()
		q.material = m
		ps.draw_pass_1 = q
		e.add_child(ps)


static var _puff: GradientTexture2D


static func _puff_tex() -> GradientTexture2D:
	if _puff == null:
		var g := Gradient.new()
		g.set_color(0, Color(1, 1, 1, 1))
		g.set_color(1, Color(1, 1, 1, 0))
		_puff = GradientTexture2D.new()
		_puff.gradient = g
		_puff.fill = GradientTexture2D.FILL_RADIAL
		_puff.fill_from = Vector2(0.5, 0.5)
		_puff.fill_to = Vector2(1.0, 0.5)
		_puff.width = 64
		_puff.height = 64
	return _puff


func _update_boat(b: Dictionary, delta: float) -> void:
	var n: Node3D = b["node"]
	var s: float = b["s"]
	var dir: int = b["dir"]
	var p := point_at(s)
	var ahead := point_at(s + 14.0 * dir)
	var behind := point_at(s - 14.0 * dir)
	var tang := (ahead - behind)
	if tang.length() < 0.01:
		return
	tang = tang.normalized()
	var yaw := atan2(-tang.x, -tang.y)
	# leichtes Rollen/Stampfen
	var t := Time.get_ticks_msec() * 0.001
	var roll := sin(t * 0.7 + s * 0.01) * 0.012
	var pitch := sin(t * 0.5 + 1.3) * 0.006
	n.global_transform = Transform3D(Basis(Vector3.UP, yaw) * Basis(Vector3.FORWARD, roll) * Basis(Vector3.RIGHT, pitch), Vector3(p.x, water_y(p.x, p.y) + 0.1, p.y))
	# Schaufelräder
	b["wheel"] = float(b["wheel"]) + float(b["v"]) / 2.6 * delta
	for nm in ["PaddleL", "PaddleR"]:
		var w := n.find_child(nm, true, false) as Node3D
		if w:
			w.rotation.x = -float(b["wheel"])
