class_name Sports
extends Node3D
## Sportstätten einer Kachel (Pipeline tools/sports.py -> city["sports"]): Spielfelder mit Linien, Toren und Netzen,
## Rundbahnen, Stehstufen, Flutlichtmasten und große Stadien mit umlaufenden überdachten Tribünen.

const VIS := 900.0
const WHITE := Color(0.80, 0.80, 0.78)

var terrain: Terrain
var _st: SurfaceTool             # deckende Flächen (Vertexfarben)
var _net: SurfaceTool            # Netze und Zäune (halb durchsichtig)
var _col := PackedVector3Array()
var _used_net := false

static var _mats := {}


static func _mat(key: String) -> Material:
	if _mats.has(key):
		return _mats[key]
	var m := StandardMaterial3D.new()
	m.vertex_color_use_as_albedo = true
	m.roughness = 0.95
	if key == "net":
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
	_mats[key] = m
	return m


func build(t: Terrain, data: Dictionary) -> void:
	terrain = t
	if data.is_empty():
		return
	var any := false
	for p in data.get("pitches", []):
		_begin(float(p[1]), float(p[2]))
		_pitch(int(p[0]), Vector3(float(p[1]), 0, float(p[2])), float(p[3]), float(p[4]), float(p[5]))
		any = true
	for tr in data.get("tracks", []):
		_begin(float(tr[0]), float(tr[1]))
		_track(Vector3(float(tr[0]), 0, float(tr[1])), float(tr[2]), float(tr[3]), float(tr[4]))
		any = true
	for bl in data.get("bleachers", []):
		_begin(float(bl[0]), float(bl[1]))
		_bleachers(bl)
		any = true
	for sd in data.get("stadiums", []):
		_begin(float(sd["x"]), float(sd["z"]))
		_stadium(sd)
		any = true
	if not any:
		return
	if not _cur.is_empty():
		_cur[2] = bool(_cur[2]) or _used_net
	# je 300-m-Zelle ein Mesh: die Sichtweite gilt ab der Mitte des Meshes (ein Mesh für die ganze Kachel verschwand,
	# sobald die Kachelmitte weiter als die Sichtweite entfernt war)
	for key in _cells:
		var pair: Array = _cells[key]
		var mesh := (pair[0] as SurfaceTool).commit()
		if mesh != null and mesh.get_surface_count() > 0:
			mesh.surface_set_material(0, _mat("paint"))
			var mi := MeshInstance3D.new()
			mi.mesh = mesh
			mi.visibility_range_end = VIS
			add_child(mi)
		if bool(pair[2]):
			var nm := (pair[1] as SurfaceTool).commit()
			if nm != null and nm.get_surface_count() > 0:
				nm.surface_set_material(0, _mat("net"))
				var ni := MeshInstance3D.new()
				ni.mesh = nm
				ni.visibility_range_end = 700.0
				ni.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				add_child(ni)
	_cells.clear()
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


# --- Grundbausteine -------------------------------------------------------------------------------------
var _cells := {}                 # Vector2i -> [SurfaceTool deckend, SurfaceTool Netz, Netz benutzt]
var _cur: Array = []


func _begin(x: float, z: float) -> void:
	if not _cur.is_empty():
		_cur[2] = bool(_cur[2]) or _used_net
	var key := Vector2i(floori(x / 300.0), floori(z / 300.0))
	if not _cells.has(key):
		var a := SurfaceTool.new()
		a.begin(Mesh.PRIMITIVE_TRIANGLES)
		var b := SurfaceTool.new()
		b.begin(Mesh.PRIMITIVE_TRIANGLES)
		_cells[key] = [a, b, false]
	_cur = _cells[key]
	_st = _cur[0]
	_net = _cur[1]
	_used_net = bool(_cur[2])


func _quad_w(s: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, col: Color, want: Vector3, solid := false) -> void:
	## Viereck mit vorgegebener Sichtseite (want): Reihenfolge wird passend gewählt
	if (b - a).cross(c - a).dot(want) >= 0.0:
		_quad(s, a, b, c, d, col, solid)
	else:
		_quad(s, a, d, c, b, col, solid)

func _quad(s: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, col: Color, solid := false) -> void:
	var n := (b - a).cross(c - a).normalized()      # sichtbare Seite (Godot: im Uhrzeigersinn)
	for p in [a, c, b, a, d, c]:
		s.set_normal(n)
		s.set_color(col)
		s.add_vertex(p)
		if solid:
			_col.append(p)


func _flat(c: Vector3, ux: Vector3, uz: Vector3, hl: float, hw: float, col: Color) -> void:
	## liegendes Rechteck um c (Halbmaße hl entlang ux, hw entlang uz)
	_quad(_st, c - ux * hl - uz * hw, c - ux * hl + uz * hw, c + ux * hl + uz * hw, c + ux * hl - uz * hw, col)


func _line(a: Vector3, b: Vector3, w: float, col := WHITE) -> void:
	var d := (b - a)
	d.y = 0.0
	if d.length() < 0.01:
		return
	var n := Vector3(-d.z, 0, d.x).normalized() * w * 0.5
	var up := Vector3(0, 0.012, 0)
	_quad(_st, a - n + up, a + n + up, b + n + up, b - n + up, col)


func _circle(c: Vector3, r: float, w: float, a0 := 0.0, a1 := TAU, ux := Vector3.RIGHT, uz := Vector3.BACK) -> void:
	var n := maxi(8, int(absf(a1 - a0) * r / 1.2))
	var prev := c + ux * cos(a0) * r + uz * sin(a0) * r
	for i in range(1, n + 1):
		var a := a0 + (a1 - a0) * float(i) / float(n)
		var cur := c + ux * cos(a) * r + uz * sin(a) * r
		_line(prev, cur, w)
		prev = cur


func _box(c: Vector3, ux: Vector3, uz: Vector3, hx: float, hz: float, h: float, col: Color, solid := false) -> void:
	var p := [c - ux * hx - uz * hz, c + ux * hx - uz * hz, c + ux * hx + uz * hz, c - ux * hx + uz * hz]
	var up := Vector3(0, h, 0)
	for i in 4:
		var a: Vector3 = p[i]
		var b: Vector3 = p[(i + 1) % 4]
		_quad(_st, a, b, b + up, a + up, col, solid)
	_quad(_st, p[0] + up, p[1] + up, p[2] + up, p[3] + up, col, solid)


func _ground(c: Vector3, ux: Vector3, uz: Vector3, hl: float, hw: float) -> float:
	var y := terrain.height_at(c.x, c.z)
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var q: Vector3 = c + ux * hl * sx + uz * hw * sz
			y = maxf(y, terrain.height_at(q.x, q.z))
	return y + 0.05


func _net_quad(a: Vector3, b: Vector3, h: float, col: Color) -> void:
	_used_net = true
	var up := Vector3(0, h, 0)
	_quad(_net, a, b, b + up, a + up, col)


# --- Spielfelder ----------------------------------------------------------------------------------------
func _pitch(code: int, c: Vector3, ang: float, L: float, W: float) -> void:
	var ux := Vector3(cos(ang), 0, sin(ang))
	var uz := Vector3(-sin(ang), 0, cos(ang))
	c.y = _ground(c, ux, uz, L * 0.5, W * 0.5)
	var hsh := absf(fposmod(c.x * 12.9898 + c.z * 78.233, 1.0))
	match code:
		0:
			_soccer(c, ux, uz, L, W)
		1:
			# Tennis: Sandplätze nebeneinander, je Platz Linien, Netz; hoher Zaun außen
			_flat(c, ux, uz, L * 0.5, W * 0.5, Color(0.70, 0.36, 0.24))
			var n := maxi(1, int(round(W / 17.5)))
			for i in n:
				var cc := c + uz * ((float(i) + 0.5) / float(n) - 0.5) * W
				if L >= 24.0 and W / float(n) >= 11.0:
					_tennis_lines(cc, ux, uz)
			_fence(c, ux, uz, L * 0.5 + 0.2, W * 0.5 + 0.2, 3.0)
		2, 8:
			_flat(c, ux, uz, L * 0.5, W * 0.5, Color(0.85, 0.77, 0.56) if code == 2 else Color(0.62, 0.30, 0.24))
			var nc := maxi(1, int(round(W / 12.0))) if code == 2 else 1
			for i in nc:
				var cc2 := c + uz * ((float(i) + 0.5) / float(nc) - 0.5) * W
				var hw2 := minf(W / float(nc) * 0.5 - 1.0, 4.5)
				if hw2 > 2.0:
					for sgn in [-1.0, 1.0]:
						_box(cc2 + uz * (hw2 + 0.4) * sgn, ux, uz, 0.05, 0.05, 2.5, Color(0.25, 0.27, 0.3))
					_net_quad(cc2 - uz * (hw2 + 0.4) + Vector3(0, 1.45, 0), cc2 + uz * (hw2 + 0.4) + Vector3(0, 1.45, 0), 1.0, Color(0.1, 0.1, 0.1, 0.45))
		3, 4:
			var surf := Color(0.58, 0.28, 0.22) if hsh < 0.45 else (Color(0.22, 0.38, 0.52) if hsh < 0.7 else Color(0.36, 0.38, 0.40))
			_flat(c, ux, uz, L * 0.5, W * 0.5, surf)
			var a := L * 0.5 - 0.4
			var b := W * 0.5 - 0.4
			if a > 3.0 and b > 2.0:
				for sg in [-1.0, 1.0]:
					_line(c + ux * a * sg - uz * b, c + ux * a * sg + uz * b, 0.06)
					_line(c - ux * a + uz * b * sg, c + ux * a + uz * b * sg, 0.06)
				_line(c - uz * b, c + uz * b, 0.06)
				if code == 3:
					_circle(c, minf(1.8, b * 0.4), 0.06, 0.0, TAU, ux, uz)
					for sg in [-1.0, 1.0]:
						# Korb: Mast, Brett, Ring
						var pb: Vector3 = c + ux * (a + 0.3) * sg
						_box(pb, ux, uz, 0.06, 0.06, 3.3, Color(0.3, 0.32, 0.35), true)
						_box(pb - ux * 0.5 * sg + Vector3(0, 3.05, 0), ux, uz, 0.5, 0.05, 0.08, Color(0.3, 0.32, 0.35))
						_box(pb - ux * 1.0 * sg + Vector3(0, 2.9, 0), ux, uz, 0.03, 0.9, 1.05, Color(0.92, 0.92, 0.92))
						_box(pb - ux * 1.25 * sg + Vector3(0, 3.02, 0), ux, uz, 0.23, 0.23, 0.03, Color(0.85, 0.3, 0.1))
			if code == 3 and L > 18.0:
				_fence(c, ux, uz, L * 0.5 + 0.3, W * 0.5 + 0.3, 3.0)
		5:
			# Tischtennisplatte aus Beton
			_box(c + Vector3(0, 0.0, 0), ux, uz, 0.25, 0.5, 0.72, Color(0.55, 0.56, 0.55), true)
			_box(c + Vector3(0, 0.72, 0), ux, uz, 1.37, 0.76, 0.06, Color(0.20, 0.36, 0.30), true)
			_box(c + Vector3(0, 0.78, 0), ux, uz, 0.015, 0.80, 0.15, Color(0.5, 0.5, 0.5))
		6:
			_flat(c, ux, uz, L * 0.5, W * 0.5, Color(0.80, 0.73, 0.58))
			_fence(c, ux, uz, L * 0.5, W * 0.5, 1.2, Color(0.9, 0.9, 0.88, 0.75))
		7:
			_flat(c, ux, uz, L * 0.5, W * 0.5, Color(0.62, 0.25, 0.20) if L > W * 2.5 else Color(0.84, 0.76, 0.58))
		9:
			_flat(c, ux, uz, L * 0.5, W * 0.5, Color(0.62, 0.62, 0.60))
			if L > 12.0:
				_ramp(c + ux * (L * 0.5 - 2.0), ux, uz, 2.0, minf(W * 0.35, 5.0), 1.5)
				_ramp(c - ux * (L * 0.5 - 2.0), -ux, uz, 2.0, minf(W * 0.35, 5.0), 1.1)


func _ramp(c: Vector3, ux: Vector3, uz: Vector3, run: float, hw: float, h: float) -> void:
	var col := Color(0.55, 0.55, 0.54)
	var a := c - ux * run - uz * hw
	var b := c - ux * run + uz * hw
	var d := c + ux * 0.0 - uz * hw + Vector3(0, h, 0)
	var e := c + ux * 0.0 + uz * hw + Vector3(0, h, 0)
	_quad(_st, a, b, e, d, col, true)
	_quad(_st, c - uz * hw, c + uz * hw, e, d, col.darkened(0.2), true)


func _fence(c: Vector3, ux: Vector3, uz: Vector3, hl: float, hw: float, h: float, col := Color(0.20, 0.34, 0.26, 0.40)) -> void:
	var p := [c - ux * hl - uz * hw, c + ux * hl - uz * hw, c + ux * hl + uz * hw, c - ux * hl + uz * hw]
	for i in 4:
		var a: Vector3 = p[i]
		var b: Vector3 = p[(i + 1) % 4]
		_net_quad(a, b, h, col)
		_col.append_array(PackedVector3Array([a, b, b + Vector3(0, h, 0), a, b + Vector3(0, h, 0), a + Vector3(0, h, 0)]))
		var n := maxi(1, int(a.distance_to(b) / 3.0))
		for k in n + 1:
			var q := a.lerp(b, float(k) / float(n))
			_box(q, ux, uz, 0.03, 0.03, h, Color(col.r, col.g, col.b).darkened(0.2))


func _tennis_lines(c: Vector3, ux: Vector3, uz: Vector3) -> void:
	var hl := 11.885
	var hw := 5.485
	var hs := 4.115                      # Einzelfeld
	for sg in [-1.0, 1.0]:
		_line(c + ux * hl * sg - uz * hw, c + ux * hl * sg + uz * hw, 0.06)
		_line(c - ux * hl + uz * hw * sg, c + ux * hl + uz * hw * sg, 0.05)
		_line(c - ux * hl + uz * hs * sg, c + ux * hl + uz * hs * sg, 0.05)
		_line(c + ux * 6.4 * sg - uz * hs, c + ux * 6.4 * sg + uz * hs, 0.05)
	_line(c - ux * 6.4, c + ux * 6.4, 0.05)
	for sg in [-1.0, 1.0]:
		_box(c + uz * (hw + 0.9) * sg, ux, uz, 0.04, 0.04, 1.07, Color(0.2, 0.22, 0.2))
	_net_quad(c - uz * (hw + 0.9) + Vector3(0, 0.05, 0), c + uz * (hw + 0.9) + Vector3(0, 0.05, 0), 0.95, Color(0.08, 0.08, 0.08, 0.5))


func _soccer(c: Vector3, ux: Vector3, uz: Vector3, L: float, W: float) -> void:
	# Rasen in Mähstreifen
	var n := maxi(4, int(round(L / 5.5)))
	for i in n:
		var x0 := -L * 0.5 + L * float(i) / float(n)
		var x1 := -L * 0.5 + L * float(i + 1) / float(n)
		var col := Color(0.10, 0.25, 0.07) if i % 2 == 0 else Color(0.13, 0.30, 0.09)
		_quad(_st, c + ux * x0 - uz * W * 0.5, c + ux * x0 + uz * W * 0.5, c + ux * x1 + uz * W * 0.5, c + ux * x1 - uz * W * 0.5, col)
	var big := L > 85.0
	var m := 1.5 if L > 108.0 else 0.6               # OSM-Fläche reicht oft etwas über die Linien hinaus
	var hl := L * 0.5 - m
	var hw := W * 0.5 - m
	var lw := 0.12 if big else 0.08
	for sg in [-1.0, 1.0]:
		_line(c + ux * hl * sg - uz * hw, c + ux * hl * sg + uz * hw, lw)
		_line(c - ux * hl + uz * hw * sg, c + ux * hl + uz * hw * sg, lw)
	_line(c - uz * hw, c + uz * hw, lw)
	_circle(c, minf(9.15, hw * 0.3), lw, 0.0, TAU, ux, uz)
	var gw := 3.66 if hw > 22.0 else minf(2.5, hw * 0.3)      # halbe Torbreite
	var gh := 2.44 if hw > 22.0 else 2.0
	for sg in [-1.0, 1.0]:
		var gl: Vector3 = c + ux * hl * sg
		if hw > 25.0:
			# Strafraum 40,3 × 16,5 m, Torraum 18,3 × 5,5 m, Elfmeterpunkt, Teilkreis
			_line(gl - uz * 20.15, gl - uz * 20.15 - ux * 16.5 * sg, lw)
			_line(gl + uz * 20.15, gl + uz * 20.15 - ux * 16.5 * sg, lw)
			_line(gl - uz * 20.15 - ux * 16.5 * sg, gl + uz * 20.15 - ux * 16.5 * sg, lw)
			_line(gl - uz * 9.16, gl - uz * 9.16 - ux * 5.5 * sg, lw)
			_line(gl + uz * 9.16, gl + uz * 9.16 - ux * 5.5 * sg, lw)
			_line(gl - uz * 9.16 - ux * 5.5 * sg, gl + uz * 9.16 - ux * 5.5 * sg, lw)
			_circle(gl - ux * 11.0 * sg, 0.15, 0.3, 0.0, TAU, ux, uz)
			var a0 := acos(5.5 / 9.15)
			_circle(gl - ux * 11.0 * sg, 9.15, lw, (PI if sg > 0.0 else 0.0) - a0, (PI if sg > 0.0 else 0.0) + a0, ux, uz)
		# Tor: Pfosten, Latte, Netz
		var post := Color(0.95, 0.95, 0.95)
		for ps in [-1.0, 1.0]:
			_box(gl + uz * gw * ps, ux, uz, 0.06, 0.06, gh, post, true)
		_box(gl + Vector3(0, gh - 0.06, 0), ux, uz, 0.06, gw, 0.12, post)
		var back: Vector3 = gl + ux * 1.6 * sg
		_net_quad(back - uz * gw, back + uz * gw, gh * 0.75, Color(0.95, 0.95, 0.95, 0.35))
		for ps in [-1.0, 1.0]:
			_used_net = true
			_quad(_net, gl + uz * gw * ps, back + uz * gw * ps, back + uz * gw * ps + Vector3(0, gh * 0.75, 0), gl + uz * gw * ps + Vector3(0, gh, 0), Color(0.95, 0.95, 0.95, 0.3))
		_quad(_net, gl - uz * gw + Vector3(0, gh, 0), gl + uz * gw + Vector3(0, gh, 0), back + uz * gw + Vector3(0, gh * 0.75, 0), back - uz * gw + Vector3(0, gh * 0.75, 0), Color(0.95, 0.95, 0.95, 0.3))


# --- Rundbahn ---------------------------------------------------------------------------------------------
func _track(c: Vector3, ang: float, L: float, W: float) -> void:
	var ux := Vector3(cos(ang), 0, sin(ang))
	var uz := Vector3(-sin(ang), 0, cos(ang))
	c.y = _ground(c, ux, uz, L * 0.5, W * 0.5) + 0.01
	var lanes := 6 if W < 80.0 else 8
	var tw := float(lanes) * 1.22
	var ro := W * 0.5
	var ri := ro - tw
	var sl := maxf(L - W, 10.0) * 0.5                 # halbe Gerade
	var red := Color(0.62, 0.25, 0.20)
	var pts_o: Array = []
	var pts_i: Array = []
	var nseg := 20
	for side in [1.0, -1.0]:
		for i in nseg + 1:
			var a := -PI * 0.5 + PI * float(i) / float(nseg)
			var d: Vector3 = ux * cos(a) * side + uz * sin(a) * side
			var cc: Vector3 = c + ux * sl * side
			pts_o.append(cc + d * ro)
			pts_i.append(cc + d * ri)
	var n := pts_o.size()
	for i in n:
		var j := (i + 1) % n
		_quad(_st, pts_i[i], pts_o[i], pts_o[j], pts_i[j], red)
		for k in lanes + 1:
			var f := float(k) / float(lanes)
			_line((pts_i[i] as Vector3).lerp(pts_o[i], f), (pts_i[j] as Vector3).lerp(pts_o[j], f), 0.05)


# --- Stehstufen ---------------------------------------------------------------------------------------------
func _bleachers(bl: Array) -> void:
	var c := Vector3(float(bl[0]), 0, float(bl[1]))
	var ang := float(bl[2])
	var L := float(bl[3])
	var D := float(bl[4])
	var ux := Vector3(cos(ang), 0, sin(ang))
	var uz := Vector3(-sin(ang), 0, cos(ang))
	var tow := Vector3(float(bl[5]), 0, float(bl[6]))
	if tow.length() > 0.5 and tow.dot(uz) > 0.0:
		uz = -uz                                     # uz zeigt vom Spielfeld weg (aufwärts)
	c.y = _ground(c, ux, uz, L * 0.5, D * 0.5)
	var rows := clampi(int(D / 0.8), 2, 30)
	var run := D / float(rows)
	var seat: Color = [Color(0.15, 0.30, 0.55), Color(0.80, 0.68, 0.10), Color(0.55, 0.14, 0.12), Color(0.2, 0.42, 0.25)][int(absf(c.x + c.z)) % 4]
	for r in rows:
		var cc := c + uz * (-D * 0.5 + (float(r) + 0.5) * run)
		_box(cc, ux, uz, L * 0.5, run * 0.5, 0.38 * float(r + 1), Color(0.62, 0.62, 0.60), r == rows - 1)
		_box(cc + Vector3(0, 0.38 * float(r + 1), 0) + uz * run * 0.15, ux, uz, L * 0.5 - 0.3, run * 0.2, 0.06, seat)


# --- Stadien ------------------------------------------------------------------------------------------------
func _mast(p: Vector3, toward: Vector3) -> void:
	p.y = terrain.height_at(p.x, p.z)
	var ux := Vector3.RIGHT
	var uz := Vector3.BACK
	_box(p, ux, uz, 0.25, 0.25, 26.0, Color(0.55, 0.57, 0.6), true)
	var t := toward.normalized()
	var s := Vector3(-t.z, 0, t.x)
	_box(p + Vector3(0, 26.0, 0) + t * 0.4, s, t, 2.4, 0.25, 2.2, Color(0.75, 0.77, 0.8))
	_quad(_st, p + Vector3(0, 26.1, 0) + t * 0.67 - s * 2.3, p + Vector3(0, 26.1, 0) + t * 0.67 + s * 2.3,
		p + Vector3(0, 28.1, 0) + t * 0.67 + s * 2.3, p + Vector3(0, 28.1, 0) + t * 0.67 - s * 2.3, Color(0.98, 0.97, 0.9))


func _stadium(sd: Dictionary) -> void:
	var c := Vector3(float(sd["x"]), 0, float(sd["z"]))
	var ang := float(sd["ang"])
	var L := float(sd["len"])
	var W := float(sd["wid"])
	var ux := Vector3(cos(ang), 0, sin(ang))
	var uz := Vector3(-sin(ang), 0, cos(ang))
	if not bool(sd.get("big", false)):
		# Sportplatz/Stadion mit vorhandenen Tribünen: vier Flutlichtmasten in den Ecken
		if L > 90.0:
			for sx in [-1.0, 1.0]:
				for sz in [-1.0, 1.0]:
					var mp: Vector3 = c + ux * (L * 0.5 + 9.0) * sx + uz * (W * 0.5 + 9.0) * sz
					_mast(mp, c - mp)
		return
	c.y = _ground(c, ux, uz, L * 0.5, W * 0.5) - 0.04
	# Tribünenschüssel: innen 5 m neben dem Spielfeld, 31 m tief, 19 Doppelreihen bis 21 m Höhe; Ecken geschlossen
	var il := L * 0.5 + 4.0
	var iw := W * 0.5 + 4.0
	var depth := 31.0
	var rows := 19
	var run := depth / float(rows)
	var rise := 1.08
	var y0 := 1.4
	var seat := Color(0.80, 0.60, 0.02)             # Dynamo-Gelb
	var conc := Color(0.42, 0.42, 0.41)
	var ncorner := 5
	# Umriss als geschlossener Linienzug mit Normalen nach außen: 4 Geraden + 4 Viertelkreise (Radius 0 innen)
	var ring: Array = []                              # [Punkt innen (lokal x, z), Normale (x, z)]
	for q in 4:
		var sx := 1.0 if q in [0, 3] else -1.0
		var sz := 1.0 if q in [0, 1] else -1.0
		for k in ncorner + 1:
			var a := PI * 0.5 * float(k) / float(ncorner)
			var nx := cos(a) if q in [0, 2] else sin(a)
			var nz := sin(a) if q in [0, 2] else cos(a)
			ring.append([Vector2(il * sx, iw * sz), Vector2(nx * sx, nz * sz)])
	# Reihenfolge so, dass der Zug umläuft: Quadranten 0 (+,+), 1 (−,+), 2 (−,−), 3 (+,−)
	var loop: Array = []
	var qs := [[1.0, 1.0, false], [-1.0, 1.0, true], [-1.0, -1.0, false], [1.0, -1.0, true]]
	for q in 4:
		var sx2: float = qs[q][0]
		var sz2: float = qs[q][1]
		var rev: bool = qs[q][2]
		for k in ncorner + 1:
			var f := float(k) / float(ncorner)
			if rev:
				f = 1.0 - f
			var a2 := PI * 0.5 * f
			loop.append([Vector2(il * sx2, iw * sz2), Vector2(cos(a2) * sx2, sin(a2) * sz2)])
	var nl := loop.size()
	var world := func(p: Vector2, y: float) -> Vector3:
		return c + ux * p.x + uz * p.y + Vector3(0, y, 0)
	for i in nl:
		var j := (i + 1) % nl
		var p0: Vector2 = loop[i][0]
		var n0: Vector2 = loop[i][1]
		var p1: Vector2 = loop[j][0]
		var n1: Vector2 = loop[j][1]
		# Brüstung vor der ersten Reihe
		var inw: Vector3 = -(ux * n0.x + uz * n0.y)          # zum Spielfeld
		_quad_w(_st, world.call(p0, 0.0), world.call(p1, 0.0), world.call(p1, y0), world.call(p0, y0), conc.darkened(0.15), inw, true)
		for r in rows:
			var d0 := float(r) * run
			var d1 := float(r + 1) * run
			var ya := y0 + float(r) * rise
			var col := seat if r < rows - 2 else Color(0.12, 0.12, 0.13)
			if r % 6 == 5:
				col = conc                                 # Umgang
			_quad_w(_st, world.call(p0 + n0 * d0, ya), world.call(p1 + n1 * d0, ya), world.call(p1 + n1 * d1, ya), world.call(p0 + n0 * d1, ya), col, Vector3.UP)
			_quad_w(_st, world.call(p0 + n0 * d1, ya), world.call(p1 + n1 * d1, ya), world.call(p1 + n1 * d1, ya + rise), world.call(p0 + n0 * d1, ya + rise), col.darkened(0.18), inw)
		# Außenwand und Dach
		var top := y0 + float(rows) * rise
		var o0: Vector2 = p0 + n0 * (depth + 0.6)
		var o1: Vector2 = p1 + n1 * (depth + 0.6)
		_quad_w(_st, world.call(o1, 0.0), world.call(o0, 0.0), world.call(o0, top + 2.0), world.call(o1, top + 2.0), Color(0.80, 0.80, 0.78), -inw, true)
		_quad_w(_st, world.call(o1, top + 2.0), world.call(o0, top + 2.0), world.call(o0, top + 3.4), world.call(o1, top + 3.4), seat, -inw)
		# Rückseite der obersten Reihen (von außen/oben sichtbar)
		_quad_w(_st, world.call(p0 + n0 * depth, top), world.call(p1 + n1 * depth, top), world.call(o1, top), world.call(o0, top), conc, Vector3.UP)
		var r_in0: Vector2 = p0 + n0 * 2.0
		var r_in1: Vector2 = p1 + n1 * 2.0
		var r_out0: Vector2 = p0 + n0 * (depth + 3.5)
		var r_out1: Vector2 = p1 + n1 * (depth + 3.5)
		var ry_in := top + 6.5
		var ry_out := top + 4.0
		# Dach: lichtdurchlässige Eindeckung (wirft keinen Schatten auf die Ränge), Rand als heller Träger
		_used_net = true
		_quad(_net, world.call(r_in0, ry_in), world.call(r_in1, ry_in), world.call(r_out1, ry_out), world.call(r_out0, ry_out), Color(0.90, 0.92, 0.95, 0.80))
		_quad_w(_st, world.call(r_in0, ry_in - 0.3), world.call(r_in1, ry_in - 0.3), world.call(r_in1, ry_in), world.call(r_in0, ry_in), Color(0.95, 0.95, 0.9), inw)
		_quad_w(_st, world.call(r_out0, ry_out - 0.3), world.call(r_out1, ry_out - 0.3), world.call(r_out1, ry_out), world.call(r_out0, ry_out), Color(0.85, 0.86, 0.87), -inw)
		# Dachträger und Stütze je Abschnitt
		var mo: Vector2 = p0 + n0 * (depth + 2.2)
		var tdir := Vector3(n0.x, 0, n0.y)
		var wdir := ux * n0.x + uz * n0.y
		var sdir := Vector3(-wdir.z, 0, wdir.x)
		_box(world.call(mo, 0.0), sdir, wdir, 0.35, 0.35, top + 4.1, Color(0.42, 0.44, 0.47), true)
		var ta: Vector3 = world.call(r_in0, ry_in - 0.9)
		var tb: Vector3 = world.call(r_out0, ry_out - 0.9)
		var tn := sdir * 0.18
		_quad(_st, ta - tn, tb - tn, tb - tn + Vector3(0, 0.6, 0), ta - tn + Vector3(0, 0.6, 0), Color(0.42, 0.44, 0.47))
		_quad(_st, tb + tn, ta + tn, ta + tn + Vector3(0, 0.6, 0), tb + tn + Vector3(0, 0.6, 0), Color(0.42, 0.44, 0.47))
		if tdir.length() < 0.0:
			pass
	# Schriftzug auf den Längstribünen (schwarze Sitze): als Schrift auf der Tribünenschräge
	var slope := atan2(rise, run)
	for sg in [-1.0, 1.0]:
		var lb := Label3D.new()
		lb.text = "DYNAMO"
		lb.font_size = 96
		lb.pixel_size = 0.115
		lb.modulate = Color(0.06, 0.06, 0.07)
		lb.outline_size = 0
		lb.double_sided = false
		lb.shaded = true
		var mid_d := depth * 0.48
		var pos: Vector3 = c + uz * (iw + mid_d) * sg + Vector3(0, y0 + mid_d / run * rise + 0.75, 0)
		# Schriftfläche: X entlang der Tribüne, Y die Schräge hinauf, Normale zum Spielfeld und nach oben
		var up_dir: Vector3 = (uz * sg * cos(slope) + Vector3(0, sin(slope), 0)).normalized()
		var x_dir: Vector3 = -ux * sg
		var z_dir: Vector3 = x_dir.cross(up_dir).normalized()
		lb.transform = Transform3D(Basis(x_dir, up_dir, z_dir), pos)
		lb.visibility_range_end = 700.0
		add_child(lb)
