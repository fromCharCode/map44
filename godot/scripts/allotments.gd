class_name Allotments
extends Node3D
## Kleingartenanlagen einer Kachel (Pipeline tools/allotments.py -> city["allotments"]): Parzellen mit Hecke oder
## Zaun, Laube, Beeten, Gewächshaus und Kieswegen. Obstbäume laufen über die normale Baumdarstellung.

const WALLS := [Color(0.93, 0.91, 0.84), Color(0.55, 0.36, 0.22), Color(0.36, 0.25, 0.17), Color(0.86, 0.78, 0.52),
	Color(0.45, 0.55, 0.42), Color(0.62, 0.20, 0.16), Color(0.78, 0.80, 0.80), Color(0.42, 0.52, 0.62)]
const ROOFS := [Color(0.22, 0.22, 0.24), Color(0.48, 0.20, 0.15), Color(0.30, 0.34, 0.30), Color(0.42, 0.40, 0.38),
	Color(0.20, 0.27, 0.22)]
const VIS := 650.0

var terrain: Terrain
var _col := PackedVector3Array()

static var _mats := {}


static func _mat(key: String) -> Material:
	if _mats.has(key):
		return _mats[key]
	var m: Material
	match key:
		"hedge":
			var s := TexLib.tri_material("grass_wild", 0.62)
			s.albedo_color = Color(0.42, 0.56, 0.36)
			s.roughness = 1.0
			m = s
		"lane":
			m = TexLib.tri_material("gravel", 0.95)
		"glass":
			var g := StandardMaterial3D.new()
			g.albedo_color = Color(0.72, 0.84, 0.86, 0.32)
			g.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			g.roughness = 0.08
			g.metallic = 0.2
			g.cull_mode = BaseMaterial3D.CULL_DISABLED
			m = g
		"mesh":
			var f := StandardMaterial3D.new()
			f.albedo_color = Color(0.30, 0.42, 0.33, 0.45)
			f.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			f.cull_mode = BaseMaterial3D.CULL_DISABLED
			f.roughness = 0.8
			m = f
		_:
			var v := StandardMaterial3D.new()
			v.vertex_color_use_as_albedo = true
			v.roughness = 0.9
			m = v
	_mats[key] = m
	return m


func build(t: Terrain, data: Dictionary) -> void:
	terrain = t
	if data.is_empty():
		return
	var st := {}
	for k in ["paint", "hedge", "lane", "glass", "mesh"]:
		var s := SurfaceTool.new()
		s.begin(Mesh.PRIMITIVE_TRIANGLES)
		st[k] = s
	var used := {}
	for h in data.get("huts", []):
		_hut(st["paint"], h)
		used["paint"] = true
	for h in data.get("hedges", []):
		var kind := int(h[5])
		var key: String = ["hedge", "paint", "mesh"][kind]
		_wall(st[key], Vector2(h[0], h[1]), Vector2(h[2], h[3]), float(h[4]), [0.7, 0.06, 0.04][kind],
			Color(0.47, 0.34, 0.22) if kind == 1 else Color.WHITE, kind == 0)
		used[key] = true
	for b in data.get("beds", []):
		_bed(st["paint"], b)
		used["paint"] = true
	for g in data.get("glass", []):
		_glasshouse(st["glass"], st["paint"], g)
		used["glass"] = true
		used["paint"] = true
	for ln in data.get("lanes", []):
		_lane(st["lane"], ln)
		used["lane"] = true
	for k in used:
		var s: SurfaceTool = st[k]
		var mesh := s.commit()
		if mesh.get_surface_count() == 0:
			continue
		mesh.surface_set_material(0, _mat(k))
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.visibility_range_end = VIS if k != "lane" else 900.0
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if k in ["lane", "glass", "mesh"] else GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		add_child(mi)
	if _col.size() >= 3:
		var body := StaticBody3D.new()
		body.collision_layer = 1
		var cs := CollisionShape3D.new()
		var sh := ConcavePolygonShape3D.new()
		sh.backface_collision = true
		sh.set_faces(_col)
		cs.shape = sh
		body.add_child(cs)
		add_child(body)
		_col = PackedVector3Array()


func _quad(s: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, col: Color, solid := false) -> void:
	## Viereck a-b-c-d, Normale aus der Reihenfolge (von außen gegen den Uhrzeigersinn gesehen)
	var n := (c - a).cross(b - a).normalized()
	for p in [a, c, b, a, d, c]:
		s.set_normal(n)
		s.set_color(col)
		s.set_uv(Vector2(p.x + p.z, p.y) * 0.5)
		s.add_vertex(p)
		if solid:
			_col.append(p)


func _box(s: SurfaceTool, c: Vector3, ux: Vector3, uz: Vector3, hx: float, hz: float, h: float, col: Color, solid := false, top := true) -> void:
	var p := [c - ux * hx - uz * hz, c + ux * hx - uz * hz, c + ux * hx + uz * hz, c - ux * hx + uz * hz]
	var up := Vector3(0, h, 0)
	for i in 4:
		var a: Vector3 = p[i]
		var b: Vector3 = p[(i + 1) % 4]
		_quad(s, a, b, b + up, a + up, col, solid)
	if top:
		_quad(s, p[0] + up, p[1] + up, p[2] + up, p[3] + up, col, solid)


func _hut(s: SurfaceTool, h: Array) -> void:
	var rot := float(h[3])
	var ux := Vector3(cos(rot), 0, sin(rot))
	var uz := Vector3(-sin(rot), 0, cos(rot))
	var hw := float(h[4]) * 0.5
	var hd := float(h[5]) * 0.5
	var wh := float(h[6])
	var c := Vector3(float(h[0]), 0.0, float(h[1]))
	var y := 1e9
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var q: Vector3 = c + ux * hw * sx + uz * hd * sz
			y = minf(y, terrain.height_at(q.x, q.z))
	c.y = y - 0.1
	var wall: Color = WALLS[int(h[7]) % WALLS.size()]
	var roof: Color = ROOFS[int(h[8]) % ROOFS.size()]
	var form := int(h[9])
	_box(s, c, ux, uz, hw, hd, wh + 0.1, wall, true, form == 2)
	var top := c + Vector3(0, wh + 0.1, 0)
	var ov := 0.3
	if form == 2:
		# Flachdach mit Überstand
		_box(s, top, ux, uz, hw + ov, hd + ov, 0.12, roof)
	elif form == 1:
		# Pultdach: vorn hoch, hinten niedrig
		var a := top - ux * (hw + ov) - uz * (hd + ov) + Vector3(0, 0.7, 0)
		var b := top + ux * (hw + ov) - uz * (hd + ov) + Vector3(0, 0.7, 0)
		var cc := top + ux * (hw + ov) + uz * (hd + ov)
		var d := top - ux * (hw + ov) + uz * (hd + ov)
		_quad(s, a, b, cc, d, roof)
		_quad(s, d, cc, b, a, roof.darkened(0.3))
		_quad(s, top - ux * hw - uz * hd, top + ux * hw - uz * hd, b - ux * ov + uz * ov, a + ux * ov + uz * ov, wall)
		for sx in [-1.0, 1.0]:
			var p0: Vector3 = top + ux * hw * sx - uz * hd
			var p1: Vector3 = top + ux * hw * sx + uz * hd
			if sx > 0:
				_quad(s, p0, p1, p1, p0 + Vector3(0, 0.7, 0), wall)
			else:
				_quad(s, p1, p0, p0 + Vector3(0, 0.7, 0), p1, wall)
	else:
		# Satteldach, First entlang der Tiefe
		var rh := 0.55 + hw * 0.35
		var r0 := top - uz * (hd + ov) + Vector3(0, rh, 0)
		var r1 := top + uz * (hd + ov) + Vector3(0, rh, 0)
		for sx in [-1.0, 1.0]:
			var e0: Vector3 = top + ux * (hw + ov) * sx - uz * (hd + ov) - Vector3(0, ov * rh / hw, 0)
			var e1: Vector3 = top + ux * (hw + ov) * sx + uz * (hd + ov) - Vector3(0, ov * rh / hw, 0)
			if sx > 0:
				_quad(s, e0, e1, r1, r0, roof)
				_quad(s, r0, r1, e1, e0, roof.darkened(0.3))
			else:
				_quad(s, e1, e0, r0, r1, roof)
				_quad(s, r1, r0, e0, e1, roof.darkened(0.3))
		for sz in [-1.0, 1.0]:                           # Giebeldreiecke
			var g0: Vector3 = top - ux * hw + uz * hd * sz
			var g1: Vector3 = top + ux * hw + uz * hd * sz
			var gt: Vector3 = top + uz * hd * sz + Vector3(0, rh, 0)
			if sz > 0:
				_quad(s, g1, g0, gt, gt, wall)
			else:
				_quad(s, g0, g1, gt, gt, wall)
	# Tür und Fenster zur Wegseite (−uz)
	var f := c - uz * (hd + 0.02)
	var door := Color(0.25, 0.18, 0.12)
	var dx := -hw * 0.35
	_quad(s, f + ux * (dx + 0.42) + Vector3(0, 0.1, 0), f + ux * (dx - 0.42) + Vector3(0, 0.1, 0),
		f + ux * (dx - 0.42) + Vector3(0, 2.0, 0), f + ux * (dx + 0.42) + Vector3(0, 2.0, 0), door)
	var wx := hw * 0.45
	_quad(s, f + ux * (wx + 0.5) + Vector3(0, 1.0, 0), f + ux * (wx - 0.5) + Vector3(0, 1.0, 0),
		f + ux * (wx - 0.5) + Vector3(0, 1.9, 0), f + ux * (wx + 0.5) + Vector3(0, 1.9, 0), Color(0.30, 0.40, 0.48))


func _wall(s: SurfaceTool, a: Vector2, b: Vector2, h: float, th: float, col: Color, solid: bool) -> void:
	var d := b - a
	var L := d.length()
	if L < 0.3:
		return
	var n := maxi(1, int(ceil(L / 4.0)))
	var t := d / L
	var nn := Vector3(-t.y, 0, t.x) * th * 0.5
	var up := Vector3(0, h, 0)
	for i in n:
		var p := a + d * (float(i) / n)
		var q := a + d * (float(i + 1) / n)
		var p3 := Vector3(p.x, terrain.height_at(p.x, p.y) - 0.05, p.y)
		var q3 := Vector3(q.x, terrain.height_at(q.x, q.y) - 0.05, q.y)
		_quad(s, p3 + nn, q3 + nn, q3 + nn + up, p3 + nn + up, col, solid)
		_quad(s, q3 - nn, p3 - nn, p3 - nn + up, q3 - nn + up, col)
		if th > 0.2:
			_quad(s, p3 - nn + up, p3 + nn + up, q3 + nn + up, q3 - nn + up, col)
			if i == 0:
				_quad(s, p3 - nn, p3 + nn, p3 + nn + up, p3 - nn + up, col)
			if i == n - 1:
				_quad(s, q3 + nn, q3 - nn, q3 - nn + up, q3 + nn + up, col)


func _bed(s: SurfaceTool, b: Array) -> void:
	var rot := float(b[2])
	var ux := Vector3(cos(rot), 0, sin(rot))                # Längsrichtung
	var uz := Vector3(-sin(rot), 0, cos(rot))
	var hw := float(b[3]) * 0.5
	var hl := float(b[4]) * 0.5
	var c := Vector3(float(b[0]), 0, float(b[1]))
	var pts: Array = []
	for q in [c - ux * hl - uz * hw, c + ux * hl - uz * hw, c + ux * hl + uz * hw, c - ux * hl + uz * hw]:
		pts.append(Vector3(q.x, terrain.height_at(q.x, q.z) + 0.07, q.z))
	_quad(s, pts[0], pts[3], pts[2], pts[1], Color(0.24, 0.17, 0.11))
	var r := absf(fposmod(c.x * 12.9898 + c.z * 78.233, 1.0))
	var flowers := int(b[5]) == 1
	var greens := [Color(0.25, 0.48, 0.20), Color(0.33, 0.55, 0.22), Color(0.20, 0.40, 0.24), Color(0.45, 0.58, 0.25)]
	var blooms := [Color(0.85, 0.25, 0.30), Color(0.95, 0.80, 0.25), Color(0.80, 0.45, 0.85), Color(0.95, 0.95, 0.90)]
	for row in 3:
		var off := (float(row) - 1.0) * hw * 0.62
		var col: Color = (blooms if flowers else greens)[int(r * 97.0 + row) % 4]
		var hh := 0.22 + 0.25 * fposmod(r * 7.0 + row * 0.37, 1.0)
		var a := c - ux * (hl - 0.25) + uz * off
		var e := c + ux * (hl - 0.25) + uz * off
		a.y = terrain.height_at(a.x, a.z) + 0.05
		e.y = terrain.height_at(e.x, e.z) + 0.05
		var w := uz * 0.16
		var up := Vector3(0, hh, 0)
		_quad(s, a + w, e + w, e + up, a + up, col)
		_quad(s, e - w, a - w, a + up, e + up, col.darkened(0.15))


func _glasshouse(sg: SurfaceTool, sp: SurfaceTool, g: Array) -> void:
	var rot := float(g[2])
	var ux := Vector3(cos(rot), 0, sin(rot))
	var uz := Vector3(-sin(rot), 0, cos(rot))
	var c := Vector3(float(g[0]), 0, float(g[1]))
	c.y = terrain.height_at(c.x, c.z) - 0.05
	_box(sg, c, ux, uz, 1.0, 1.5, 1.7, Color.WHITE, false, false)
	var top := c + Vector3(0, 1.7, 0)
	var r0 := top - uz * 1.5 + Vector3(0, 0.55, 0)
	var r1 := top + uz * 1.5 + Vector3(0, 0.55, 0)
	_quad(sg, top + ux - uz * 1.5, top + ux + uz * 1.5, r1, r0, Color.WHITE)
	_quad(sg, top - ux + uz * 1.5, top - ux - uz * 1.5, r0, r1, Color.WHITE)
	# Sockel und Rahmen
	_box(sp, c, ux, uz, 1.03, 1.53, 0.25, Color(0.55, 0.55, 0.53), true)
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			_box(sp, c + ux * sx + uz * 1.5 * sz, ux, uz, 0.025, 0.025, 1.7, Color(0.82, 0.84, 0.84), false, false)


func _lane(s: SurfaceTool, ln: Array) -> void:
	for i in ln.size() - 1:
		var a := Vector2(ln[i][0], ln[i][1])
		var b := Vector2(ln[i + 1][0], ln[i + 1][1])
		var d := b - a
		var L := d.length()
		if L < 0.5:
			continue
		var t := d / L
		var nn := Vector2(-t.y, t.x) * 1.3
		var n := maxi(1, int(ceil(L / 3.0)))
		for k in n:
			var p := a + d * (float(k) / n)
			var q := a + d * (float(k + 1) / n)
			var pts: Array = []
			for v in [p - nn, q - nn, q + nn, p + nn]:
				pts.append(Vector3(v.x, terrain.height_at(v.x, v.y) + 0.05, v.y))
			for idx in [0, 2, 1, 0, 3, 2]:
				var v3: Vector3 = pts[idx]
				s.set_normal(Vector3.UP)
				s.set_color(Color.WHITE)
				s.set_uv(Vector2(v3.x, v3.z) * 0.4)
				s.add_vertex(v3)
