class_name SpeedCams
extends Node3D
## Blitzer (Pipeline tools/blitzer.py -> city["speedcams"], Standorte aus OpenStreetMap):
## [x, z, limit_kmh, dx, dz, bauart, rotlicht]. Säule bzw. Mast am Straßenrand; wer in der überwachten Richtung
## mehr als Limit + Toleranz fährt, wird mit rotem Blitz erfasst und zahlt nach dem Bußgeldkatalog (innerorts).

const RANGE := 16.0            # Messabstand (m)
const TOLERANCE := 3.0         # Abzug km/h wie bei der echten Messung
const COOLDOWN := 25.0

var player: PlayerCar
var hud: Hud
var taxi: TaxiGame
var _cams: Array = []          # {key, pos, limit, dir, cool, light, red}
var _flash: Array = []         # [light, t]
var _test_t := 0.0
var count := 0                 # ausgelöste Blitze (Diagnose)

static var _mats := {}


func setup(p: PlayerCar, h: Hud, t: TaxiGame, world: Node) -> void:
	player = p
	hud = h
	taxi = t
	world.connect("tile_added", add_tile)
	world.connect("tile_removed", remove_tile)
	for k in world.tiles:                                # schon geladene Kacheln
		add_tile(world.tiles[k])


static func _mat(col: Color, rough: float, metal := 0.0, emit := Color.BLACK) -> StandardMaterial3D:
	var k := col.to_html() + str(rough) + emit.to_html()
	if not _mats.has(k):
		var m := StandardMaterial3D.new()
		m.albedo_color = col
		m.roughness = rough
		m.metallic = metal
		if emit != Color.BLACK:
			m.emission_enabled = true
			m.emission = emit
		_mats[k] = m
	return _mats[k]


func add_tile(tile: Tile) -> void:
	for c in tile.city.get("speedcams", []):
		var x := float(c[0])
		var z := float(c[1])
		var pos := Vector3(x, float(c[7]) if c.size() > 7 else tile.terrain.height_at(x, z), z)
		var dir := Vector3(float(c[3]), 0.0, float(c[4]))
		var root := Node3D.new()
		root.position = pos
		# Blick der Anlage dem überwachten Verkehr entgegen
		if dir.length() > 0.5:
			root.rotation.y = atan2(-dir.x, -dir.z)
		add_child(root)
		var light := _model(root, int(c[5]) == 0)
		_cams.append({"key": tile.key, "pos": pos, "limit": float(c[2]), "dir": dir, "cool": 0.0, "light": light,
			"red": int(c[6]) == 1, "root": root})   # 1 = nur Rotlicht


func remove_tile(tile: Tile) -> void:
	var keep: Array = []
	for c in _cams:
		if c["key"] == tile.key:
			(c["root"] as Node3D).queue_free()
		else:
			keep.append(c)
	_cams = keep
	_flash.clear()


func _model(root: Node3D, stele: bool) -> OmniLight3D:
	var dark := _mat(Color(0.10, 0.11, 0.12), 0.45, 0.3)
	var grey := _mat(Color(0.62, 0.64, 0.65), 0.5, 0.4)
	var glass := _mat(Color(0.02, 0.02, 0.03), 0.08, 0.6)
	var h := 3.5 if stele else 3.0
	if stele:
		# Messsäule: anthrazitfarbener Zylinder mit umlaufenden dunklen Glasringen
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.2
		cyl.bottom_radius = 0.2
		cyl.height = h
		cyl.radial_segments = 20
		var mi := MeshInstance3D.new()
		mi.mesh = cyl
		mi.material_override = dark
		mi.position.y = h * 0.5
		root.add_child(mi)
		for ry in [1.15, 1.75, 2.35, 2.95]:
			var ring := CylinderMesh.new()
			ring.top_radius = 0.205
			ring.bottom_radius = 0.205
			ring.height = 0.32
			ring.radial_segments = 20
			var ri := MeshInstance3D.new()
			ri.mesh = ring
			ri.material_override = glass
			ri.position.y = ry
			root.add_child(ri)
	else:
		# Mast mit Kamerakasten (Starenkasten)
		var pole := CylinderMesh.new()
		pole.top_radius = 0.06
		pole.bottom_radius = 0.07
		pole.height = h - 0.5
		var pm := MeshInstance3D.new()
		pm.mesh = pole
		pm.material_override = grey
		pm.position.y = (h - 0.5) * 0.5
		root.add_child(pm)
		var box := BoxMesh.new()
		box.size = Vector3(0.42, 0.52, 0.5)
		var bi := MeshInstance3D.new()
		bi.mesh = box
		bi.material_override = grey
		bi.position.y = h - 0.26
		root.add_child(bi)
		for lx in [-0.09, 0.09]:
			var lens := CylinderMesh.new()
			lens.top_radius = 0.07
			lens.bottom_radius = 0.07
			lens.height = 0.03
			var li := MeshInstance3D.new()
			li.mesh = lens
			li.material_override = glass
			li.rotation.x = PI * 0.5
			li.position = Vector3(lx, h - 0.2, -0.26)
			root.add_child(li)
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := CylinderShape3D.new()
	sh.radius = 0.22 if stele else 0.09
	sh.height = h
	cs.shape = sh
	cs.position.y = h * 0.5
	body.add_child(cs)
	root.add_child(body)
	var l := OmniLight3D.new()
	l.light_color = Color(1.0, 0.08, 0.05)
	l.omni_range = 30.0
	l.light_energy = 0.0
	l.shadow_enabled = false
	l.position = Vector3(0, h - 0.6, -0.4)
	l.visible = false
	root.add_child(l)
	return l


static func fine(over: int) -> int:
	## Bußgeldkatalog innerorts (Pkw), Überschreitung nach Toleranzabzug
	for row in [[10, 30], [15, 50], [20, 70], [25, 115], [30, 180], [40, 260], [50, 400], [60, 560], [70, 700]]:
		if over <= row[0]:
			return row[1]
	return 800


func _physics_process(delta: float) -> void:
	for i in range(_flash.size() - 1, -1, -1):
		var f: Array = _flash[i]
		f[1] += delta
		var l: OmniLight3D = f[0]
		if not is_instance_valid(l):
			_flash.remove_at(i)
			continue
		# Doppelblitz
		var t: float = f[1]
		l.light_energy = 60.0 if (t < 0.07 or (t > 0.16 and t < 0.23)) else 0.0
		if t > 0.3:
			l.visible = false
			_flash.remove_at(i)
	if player == null or _cams.is_empty():
		return
	if OS.has_environment("DRESDEN_BLITZER_TEST"):       # Selbsttest: mit 70 km/h am ersten Blitzer vorbei
		_test_t += delta
		for c in _cams:
			if not c["red"] and _test_t > 4.0 and _test_t < 7.0:
				var dd: Vector3 = c["dir"] if (c["dir"] as Vector3).length() > 0.5 else Vector3(1, 0, 0)
				var s := (_test_t - 4.0) / 3.0
				player.global_position = c["pos"] + dd * lerpf(-30.0, 30.0, s) + Vector3(0, 1.5, 0)
				player.linear_velocity = dd * 19.4
				break
		if _test_t > 8.0:
			print("BLITZER TEST: %d ausgelöst, %d Anlagen geladen" % [count, _cams.size()])
			get_tree().quit()
	var pp := player.global_position
	var v := player.linear_velocity
	v.y = 0.0
	var kmh := v.length() * 3.6
	for c in _cams:
		if c["red"]:
			continue                                      # reiner Rotlichtblitzer: steht nur da (noch ohne Auswertung)
		if c["cool"] > 0.0:
			c["cool"] -= delta
			continue
		var d: Vector3 = pp - c["pos"]
		d.y = 0.0
		if d.length() > RANGE or kmh < 8.0:
			continue
		var dir: Vector3 = c["dir"]
		if dir.length() > 0.5 and v.normalized().dot(dir) < 0.6:
			continue
		var measured := kmh - TOLERANCE
		var lim: float = c["limit"]
		if measured <= lim + 0.5:
			c["cool"] = 2.0
			continue
		c["cool"] = COOLDOWN
		count += 1
		var l: OmniLight3D = c["light"]
		l.visible = true
		_flash.append([l, 0.0])
		var over := int(ceil(measured - lim))
		var eur := fine(over)
		if taxi:
			taxi.money -= eur
		if hud:
			hud.message("Geblitzt! %d km/h bei erlaubten %d – %d € %s" % [int(measured), int(lim), eur,
				"Verwarngeld" if eur < 60 else "Bußgeld"], 6.0)
		if OS.has_environment("DRESDEN_BLITZER"):
			print("BLITZER %d km/h bei %d -> %d EUR an (%.0f, %.0f)" % [int(measured), int(lim), eur, c["pos"].x, c["pos"].z])
