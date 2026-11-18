class_name SteamerModel
extends RefCounted
## Raddampfer der Dresdner Flotte, im Spiel erzeugt – nach Fotos der heutigen Schiffe: weißer Rumpf mit grünem
## Wasserpass und grünem Zierstreifen, cremefarbener Radkasten mit Fächerornament und Schiffsname, ein schlanker
## Schornstein mit grünem Band und schwarzer Kappe, Salons mit Fensterreihe, Oberdeck mit Reling und langem
## Sonnendach, Steuerhaus, Mast, Flaggen, Rettungsringe. Jedes Schiff hat seinen Namen, sein Baujahr und seine Länge.
##
## Modellraum: Ursprung in der Wasserlinie mittschiffs, Bug = −Z, +Y oben.

const FLEET := [
	{"name": "DRESDEN", "year": 1926, "len": 68.7, "big": true},
	{"name": "LEIPZIG", "year": 1929, "len": 69.7, "big": true},
	{"name": "MEISSEN", "year": 1885, "len": 65.7, "big": false},
	{"name": "PILLNITZ", "year": 1886, "len": 65.7, "big": false},
	{"name": "STADT WEHLEN", "year": 1879, "len": 59.2, "big": false},
	{"name": "KURORT RATHEN", "year": 1896, "len": 57.1, "big": false},
	{"name": "KRIPPEN", "year": 1892, "len": 56.1, "big": false},
	{"name": "PIRNA", "year": 1898, "len": 56.1, "big": false},
	{"name": "DIESBAR", "year": 1884, "len": 53.5, "big": false},
]
const WHITE := Color(0.90, 0.90, 0.87)
const GREEN := Color(0.07, 0.30, 0.17)
const CREAM := Color(0.82, 0.74, 0.52)
const WOOD := Color(0.42, 0.30, 0.18)
const ROOF := Color(0.78, 0.79, 0.78)
const GLASS := Color(0.07, 0.10, 0.13)
const BLACK := Color(0.04, 0.04, 0.05)

static var _mat: StandardMaterial3D


static func _material() -> StandardMaterial3D:
	if _mat == null:
		_mat = StandardMaterial3D.new()
		_mat.vertex_color_use_as_albedo = true
		_mat.roughness = 0.7
	return _mat


static func _q(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, col: Color, want: Vector3) -> void:
	## Viereck, sichtbare Seite in Richtung want
	var n := (b - a).cross(c - a)
	var pts := [a, c, b, a, d, c] if n.dot(want) >= 0.0 else [a, b, c, a, c, d]
	var nn := n.normalized() if n.dot(want) >= 0.0 else -n.normalized()
	for p in pts:
		st.set_normal(nn)
		st.set_color(col)
		st.add_vertex(p)


static func _box(st: SurfaceTool, c: Vector3, hx: float, hy: float, hz: float, col: Color, top_col := Color(-1, 0, 0)) -> void:
	## Quader um c (c.y = Unterkante), Halbmaße hx/hz, Höhe hy
	var x0 := c.x - hx
	var x1 := c.x + hx
	var z0 := c.z - hz
	var z1 := c.z + hz
	var y0 := c.y
	var y1 := c.y + hy
	_q(st, Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y1, z0), Vector3(x0, y1, z0), col, Vector3(0, 0, -1))
	_q(st, Vector3(x0, y0, z1), Vector3(x1, y0, z1), Vector3(x1, y1, z1), Vector3(x0, y1, z1), col, Vector3(0, 0, 1))
	_q(st, Vector3(x0, y0, z0), Vector3(x0, y0, z1), Vector3(x0, y1, z1), Vector3(x0, y1, z0), col, Vector3(-1, 0, 0))
	_q(st, Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x1, y1, z1), Vector3(x1, y1, z0), col, Vector3(1, 0, 0))
	_q(st, Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x0, y1, z1), col if top_col.r < 0.0 else top_col, Vector3.UP)
	_q(st, Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x0, y0, z1), col.darkened(0.3), Vector3.DOWN)


static func _hull_w(t: float, bw: float) -> float:
	## halbe Rumpfbreite entlang der Länge (t = 0 Bug … 1 Heck)
	if t < 0.22:
		return bw * pow(t / 0.22, 0.62)
	if t > 0.86:
		return bw * (0.45 + 0.55 * sqrt(maxf(1.0 - pow((t - 0.86) / 0.14, 2.0), 0.0)))
	return bw


static func _label(root: Node3D, text: String, pos: Vector3, yaw: float, px: float, col: Color) -> void:
	var lb := Label3D.new()
	lb.text = text
	lb.font_size = 64
	lb.pixel_size = px
	lb.modulate = col
	lb.outline_size = 0
	lb.double_sided = false
	lb.position = pos
	lb.rotation.y = yaw
	lb.visibility_range_end = 420.0
	root.add_child(lb)


static func build(spec: Dictionary) -> Node3D:
	var root := Node3D.new()
	var L: float = spec["len"]
	var big: bool = spec["big"]
	var hl := L * 0.5
	var bw := 3.4 if big else 3.1                     # halbe Rumpfbreite
	var deck := 1.45
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	# --- Rumpf: Spanten von Bug bis Heck, Wasserpass und Zierstreifen grün ---
	var n := 40
	var prev: Array = []
	for i in n + 1:
		var t := float(i) / float(n)
		var z := -hl + L * t
		var w := _hull_w(t, bw)
		var sheer := deck + 0.55 * pow(maxf(0.25 - t, 0.0) / 0.25, 2.0) + 0.15 * pow(maxf(t - 0.8, 0.0) / 0.2, 2.0)
		var cur := [z, w, sheer]
		if i > 0:
			for sd: float in [-1.0, 1.0]:
				var a0 := Vector3(float(prev[1]) * sd, -0.5, float(prev[0]))
				var b0 := Vector3(w * sd, -0.5, z)
				var outv := Vector3(sd, 0, 0)
				# Wasserpass (grün), Bordwand (weiß), Zierstreifen (grün), Schanzkleid (weiß)
				var ya := [-0.5, 0.22, float(prev[2]) - 0.42, float(prev[2]) - 0.30, float(prev[2]) + 0.05]
				var yb := [-0.5, 0.22, sheer - 0.42, sheer - 0.30, sheer + 0.05]
				var cols := [GREEN, WHITE, GREEN, WHITE]
				for k in 4:
					_q(st, Vector3(a0.x, ya[k], a0.z), Vector3(b0.x, yb[k], b0.z), Vector3(b0.x, yb[k + 1], b0.z), Vector3(a0.x, ya[k + 1], a0.z), cols[k], outv)
			# Deck
			_q(st, Vector3(-float(prev[1]), float(prev[2]), float(prev[0])), Vector3(float(prev[1]), float(prev[2]), float(prev[0])),
				Vector3(w, sheer, z), Vector3(-w, sheer, z), WOOD, Vector3.UP)
		prev = cur
	# --- Salons auf dem Hauptdeck (vorn und achtern), Fensterreihe ---
	var sal_h := 2.25
	var sal_w := bw - 0.75
	var sal := [[-hl * 0.62, -hl * 0.13], [hl * 0.13, hl * (0.80 if big else 0.72)]]
	for sr in sal:
		var z0: float = sr[0]
		var z1: float = sr[1]
		_box(st, Vector3(0, deck, (z0 + z1) * 0.5), sal_w, sal_h, (z1 - z0) * 0.5, WHITE, WOOD)
		var nw := int((z1 - z0 - 1.0) / 1.55)
		for k in nw:
			var wz := z0 + 0.9 + (z1 - z0 - 1.8) * (float(k) + 0.5) / float(nw)
			for sd: float in [-1.0, 1.0]:
				_q(st, Vector3(sal_w * sd + 0.02 * sd, deck + 0.95, wz - 0.48), Vector3(sal_w * sd + 0.02 * sd, deck + 0.95, wz + 0.48),
					Vector3(sal_w * sd + 0.02 * sd, deck + 1.85, wz + 0.48), Vector3(sal_w * sd + 0.02 * sd, deck + 1.85, wz - 0.48), GLASS, Vector3(sd, 0, 0))
	# Mittelteil (Maschinenraum-Überbau) zwischen den Salons
	_box(st, Vector3(0, deck, 0), sal_w, sal_h, hl * 0.13, WHITE, WOOD)
	# --- Oberdeck: Reling, Bänke, Sonnendach auf Stützen ---
	var up := deck + sal_h
	var ud0: float = sal[0][0]
	var ud1: float = sal[1][1]
	for sd: float in [-1.0, 1.0]:
		_box(st, Vector3(sal_w * sd, up + 0.95, (ud0 + ud1) * 0.5), 0.03, 0.05, (ud1 - ud0) * 0.5, WHITE)
		_box(st, Vector3(sal_w * sd, up + 0.50, (ud0 + ud1) * 0.5), 0.02, 0.03, (ud1 - ud0) * 0.5, WHITE)
		var np := int((ud1 - ud0) / 1.6)
		for k in np + 1:
			var pz := ud0 + (ud1 - ud0) * float(k) / float(np)
			_box(st, Vector3(sal_w * sd, up, pz), 0.03, 1.0, 0.03, WHITE)
			if k % 3 == 0:
				_box(st, Vector3(sal_w * sd, up + 1.0, pz), 0.04, 1.35, 0.04, WHITE)      # Dachstütze
			if k % 6 == 3:
				_box(st, Vector3((sal_w + 0.06) * sd, up + 0.35, pz), 0.05, 0.5, 0.25, Color(0.75, 0.10, 0.08))   # Rettungsring
		# Sitzbänke
		for k in int((ud1 - ud0) / 2.4):
			_box(st, Vector3((sal_w - 0.9) * sd, up, ud0 + 1.4 + float(k) * 2.4), 0.5, 0.45, 0.22, WOOD.lightened(0.15))
	for end_z: float in [ud0, ud1]:
		_box(st, Vector3(0, up + 0.95, end_z), sal_w, 0.05, 0.03, WHITE)
	var roof_y := up + 2.35
	var rz0 := ud0 + (ud1 - ud0) * 0.10
	var rz1 := ud1 - 1.0
	_box(st, Vector3(0, roof_y, (rz0 + rz1) * 0.5), sal_w + 0.25, 0.09, (rz1 - rz0) * 0.5, ROOF)
	# --- Steuerhaus vor dem Schornstein ---
	var wh_z := -hl * 0.20
	_box(st, Vector3(0, roof_y + 0.09, wh_z), 1.3, 2.1, 1.2, WHITE, ROOF)
	_q(st, Vector3(-1.1, roof_y + 1.05, wh_z - 1.22), Vector3(1.1, roof_y + 1.05, wh_z - 1.22), Vector3(1.1, roof_y + 1.85, wh_z - 1.22), Vector3(-1.1, roof_y + 1.85, wh_z - 1.22), GLASS, Vector3(0, 0, -1))
	for sd: float in [-1.0, 1.0]:
		_q(st, Vector3(1.32 * sd, roof_y + 1.05, wh_z - 0.9), Vector3(1.32 * sd, roof_y + 1.05, wh_z + 0.9), Vector3(1.32 * sd, roof_y + 1.85, wh_z + 0.9), Vector3(1.32 * sd, roof_y + 1.85, wh_z - 0.9), GLASS, Vector3(sd, 0, 0))
	# --- Schornstein: schlank, leicht nach hinten geneigt, grünes Band, schwarze Kappe ---
	var fz := -hl * 0.04
	var fr := 0.62 if big else 0.52
	var fh := 7.2 if big else 6.4
	var seg := 14
	for i in seg:
		var a0 := TAU * float(i) / float(seg)
		var a1 := TAU * float(i + 1) / float(seg)
		var bands := [[0.0, 0.62, CREAM.lightened(0.25)], [0.62, 0.72, GREEN], [0.72, 0.84, CREAM.lightened(0.25)], [0.84, 1.0, BLACK]]
		for bd in bands:
			var y0f := roof_y + fh * float(bd[0])
			var y1f := roof_y + fh * float(bd[1])
			var r0 := fr
			var zo0 := fz + (y0f - roof_y) * 0.07
			var zo1 := fz + (y1f - roof_y) * 0.07
			var p0 := Vector3(cos(a0) * r0, y0f, zo0 + sin(a0) * r0)
			var p1 := Vector3(cos(a1) * r0, y0f, zo0 + sin(a1) * r0)
			var p2 := Vector3(cos(a1) * r0, y1f, zo1 + sin(a1) * r0)
			var p3 := Vector3(cos(a0) * r0, y1f, zo1 + sin(a0) * r0)
			_q(st, p0, p1, p2, p3, bd[2], Vector3(cos((a0 + a1) * 0.5), 0, sin((a0 + a1) * 0.5)))
	# --- Radkästen: Halbrund, cremefarben, Fächerornament in Weiß ---
	var pr := 2.75 if big else 2.5
	var pw := 2.4
	for sd: float in [-1.0, 1.0]:
		var xi := bw * sd
		var xo := (bw + pw) * sd
		var ns := 12
		for i in ns:
			var a0 := PI * float(i) / float(ns)
			var a1 := PI * float(i + 1) / float(ns)
			var q0 := Vector3(0, 1.15 + sin(a0) * pr, -cos(a0) * pr)
			var q1 := Vector3(0, 1.15 + sin(a1) * pr, -cos(a1) * pr)
			# Mantel
			_q(st, Vector3(xi, q0.y, q0.z), Vector3(xo, q0.y, q0.z), Vector3(xo, q1.y, q1.z), Vector3(xi, q1.y, q1.z), CREAM, Vector3(0, sin((a0 + a1) * 0.5), -cos((a0 + a1) * 0.5)))
			# Stirnfläche außen (Fächer aus Segmenten, jedes zweite heller)
			_q(st, Vector3(xo, 1.15, 0), Vector3(xo, q0.y, q0.z), Vector3(xo, q1.y, q1.z), Vector3(xo, q1.y, q1.z), CREAM if i % 2 == 0 else CREAM.lightened(0.45), Vector3(sd, 0, 0))
		# Unterkante/Schürze bis knapp über das Wasser
		_q(st, Vector3(xo, 0.55, -pr), Vector3(xo, 0.55, pr), Vector3(xo, 1.15, pr), Vector3(xo, 1.15, -pr), CREAM, Vector3(sd, 0, 0))
		_q(st, Vector3(xi, 0.55, -pr), Vector3(xo, 0.55, -pr), Vector3(xo, 1.15, -pr), Vector3(xi, 1.15, -pr), CREAM, Vector3(0, 0, -1))
		_q(st, Vector3(xi, 0.55, pr), Vector3(xo, 0.55, pr), Vector3(xo, 1.15, pr), Vector3(xi, 1.15, pr), CREAM, Vector3(0, 0, 1))
		# grüner Streifen am Radkasten
		_q(st, Vector3(xo + 0.01 * sd, 1.02, -pr), Vector3(xo + 0.01 * sd, 1.02, pr), Vector3(xo + 0.01 * sd, 1.15, pr), Vector3(xo + 0.01 * sd, 1.15, -pr), GREEN, Vector3(sd, 0, 0))
		_label(root, String(spec["name"]), Vector3(xo + 0.03 * sd, 1.75, 0), PI * 0.5 * sd, 0.0105, BLACK)
		_label(root, str(int(spec["year"])), Vector3(xo + 0.03 * sd, 2.55, 0), PI * 0.5 * sd, 0.0075, BLACK)
		# Name am Bug
		var bz := -hl * 0.80
		var bx := _hull_w(0.10, bw)
		_label(root, String(spec["name"]), Vector3((bx + 0.03) * sd, 0.95, bz), PI * 0.5 * sd + (0.16 if sd > 0.0 else -0.16), 0.0085, BLACK)
	# --- Mast und Flaggenstöcke ---
	_box(st, Vector3(0, deck, -hl * 0.50), 0.07, 9.0, 0.07, WHITE)
	_box(st, Vector3(0, deck + 0.4, hl * 0.93), 0.035, 3.2, 0.035, WHITE)
	_box(st, Vector3(0, deck + 0.6, -hl * 0.94), 0.03, 2.4, 0.03, WHITE)
	var mesh := st.commit()
	mesh.surface_set_material(0, _material())
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.name = "Hull"
	root.add_child(mi)
	# Flaggen: Deutschland am Heck, Sachsen (weiß-grün) am Bug
	root.add_child(_flag(Vector3(0, deck + 2.6, hl * 0.93), [Color(0.05, 0.05, 0.05), Color(0.75, 0.08, 0.08), Color(0.95, 0.78, 0.1)], 1.6))
	root.add_child(_flag(Vector3(0, deck + 2.2, -hl * 0.94), [Color(0.93, 0.93, 0.93), Color(0.10, 0.45, 0.22)], 1.2))
	# Schaufelräder (drehen sich, unter dem Radkasten sichtbar) und Rauchpunkt
	for sd: float in [-1.0, 1.0]:
		var wheel := _wheel(pr - 0.35, pw - 0.5)
		wheel.name = "PaddleL" if sd < 0.0 else "PaddleR"
		wheel.position = Vector3((bw + pw * 0.5) * sd, 1.05, 0)
		root.add_child(wheel)
	var smoke := Node3D.new()
	smoke.name = "SmokeFront"
	smoke.position = Vector3(0, roof_y + fh + 0.3, fz + fh * 0.07)
	root.add_child(smoke)
	return root


static func _flag(pos: Vector3, stripes: Array, w: float) -> MeshInstance3D:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var h := w * 0.6
	var n := stripes.size()
	for i in n:
		var y1 := h * (1.0 - float(i) / float(n))
		var y0 := h * (1.0 - float(i + 1) / float(n))
		for face: float in [1.0, -1.0]:
			_q(st, Vector3(0, y0, 0), Vector3(0, y0, w), Vector3(0, y1, w), Vector3(0, y1, 0), stripes[i], Vector3(face, 0, 0))
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.mesh.surface_set_material(0, _material())
	mi.position = pos
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi


static func _wheel(r: float, hw: float) -> Node3D:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var red := Color(0.45, 0.10, 0.08)
	for i in 10:
		var a := TAU * float(i) / 10.0
		var d := Vector3(0, sin(a), cos(a))
		var s := Vector3(0, cos(a), -sin(a)) * 0.05
		for sd: float in [-1.0, 1.0]:
			var x := hw * 0.5 * sd
			_q(st, Vector3(x, 0, 0) - s, Vector3(x, 0, 0) + s, Vector3(x, 0, 0) + d * r + s, Vector3(x, 0, 0) + d * r - s, red, Vector3(sd, 0, 0))
		# Schaufelbrett
		var o := d * (r - 0.25)
		_q(st, Vector3(-hw * 0.5, 0, 0) + o - d * 0.3, Vector3(hw * 0.5, 0, 0) + o - d * 0.3, Vector3(hw * 0.5, 0, 0) + o + d * 0.25, Vector3(-hw * 0.5, 0, 0) + o + d * 0.25, red.lightened(0.1), s.normalized())
		_q(st, Vector3(-hw * 0.5, 0, 0) + o - d * 0.3, Vector3(hw * 0.5, 0, 0) + o - d * 0.3, Vector3(hw * 0.5, 0, 0) + o + d * 0.25, Vector3(-hw * 0.5, 0, 0) + o + d * 0.25, red.lightened(0.1), -s.normalized())
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.mesh.surface_set_material(0, _material())
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var n := Node3D.new()
	n.add_child(mi)
	return n
