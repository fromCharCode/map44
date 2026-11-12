class_name MiniMap
extends Control
## Minimap (Luftbild, nach Fahrtrichtung gedreht) oder große Karte (M).

var car: PlayerCar
var traffic: Traffic
var world: World
var big := false

const SMALL := 220.0
const RANGE_SMALL := 260.0     # Meter Kantenlänge
const PX_PER_M := 2.048


func _ready() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(_delta: float) -> void:
	var vp := get_viewport_rect().size
	if big:
		var s := minf(vp.x, vp.y) * 0.82
		size = Vector2(s, s)
		position = (vp - size) * 0.5
	else:
		size = Vector2(SMALL, SMALL)
		position = Vector2(24.0, vp.y - SMALL - 24.0)
	queue_redraw()


func _draw() -> void:
	if car == null or world == null:
		return
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.05, 0.06, 0.08, 1.0))
	var range_m := 3500.0 if big else RANGE_SMALL
	var sc := size.x / range_m
	var cp := car.global_position
	var yaw := atan2(car.global_transform.basis.z.x, car.global_transform.basis.z.z)
	var rot := 0.0 if big else yaw
	var center := size * 0.5
	for t in world.tiles.values():
		var tl: Tile = t
		if tl.terrain == null or tl.terrain.ortho_tex == null:
			continue
		var org := Vector2(tl.terrain.center.x - 1000.0, tl.terrain.center.y - 1000.0)
		var tx := Transform2D()
		tx = tx.scaled(Vector2(2000.0 / 4096.0, 2000.0 / 4096.0))
		tx = tx.translated(org - Vector2(cp.x, cp.z))
		tx = tx.scaled(Vector2(sc, sc))
		tx = Transform2D(rot, Vector2.ZERO) * tx
		tx = tx.translated(center)
		draw_set_transform_matrix(tx)
		draw_texture_rect(tl.terrain.ortho_tex, Rect2(0, 0, 4096, 4096), false, Color(1, 1, 1, 0.96))
	draw_set_transform_matrix(Transform2D.IDENTITY)
	var me := center
	if traffic:
		for ac in traffic.cars:
			var q: Vector3 = (ac as AICar).global_position
			var v := center + (Vector2(q.x - cp.x, q.z - cp.z) * sc).rotated(rot)
			draw_circle(v, 2.0, Color(1.0, 0.8, 0.2))
	var h := 0.0 if not big else yaw
	var pts := PackedVector2Array([me + Vector2(0, -10).rotated(h), me + Vector2(7, 8).rotated(h), me + Vector2(0, 3).rotated(h), me + Vector2(-7, 8).rotated(h)])
	draw_colored_polygon(pts, Color(0.2, 0.7, 1.0))
	pts.append(pts[0])
	draw_polyline(pts, Color.WHITE, 1.5)
	draw_rect(Rect2(Vector2.ZERO, size), Color(1, 1, 1, 0.35), false, 2.0)
