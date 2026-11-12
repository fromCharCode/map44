class_name RoadIndex
extends RefCounted
## Räumlicher Index über Straßensegmente (Gitter), für "nächste Straße"-Abfragen.

const CELL := 24.0

var cells := {}
var roads: Array = []


func build(road_list: Array, drive_only: bool = true) -> void:
	roads = road_list
	for ri in roads.size():
		var r: Dictionary = roads[ri]
		if drive_only and r.get("cls", "") == "":
			continue
		var pts: Array = r["pts"]
		for i in pts.size() - 1:
			var a: Array = pts[i]
			var b: Array = pts[i + 1]
			var x0 := minf(a[0], b[0])
			var x1 := maxf(a[0], b[0])
			var z0 := minf(a[1], b[1])
			var z1 := maxf(a[1], b[1])
			for cx in range(floori(x0 / CELL), floori(x1 / CELL) + 1):
				for cz in range(floori(z0 / CELL), floori(z1 / CELL) + 1):
					var key := Vector2i(cx, cz)
					if not cells.has(key):
						cells[key] = []
					cells[key].append([a[0], a[1], b[0], b[1], ri, i])


func nearest(x: float, z: float, max_d: float, pref_name: String = "") -> Dictionary:
	var best := {}
	var best_d := max_d
	var r := ceili(max_d / CELL)
	var cx := floori(x / CELL)
	var cz := floori(z / CELL)
	for ix in range(cx - r, cx + r + 1):
		for iz in range(cz - r, cz + r + 1):
			var list = cells.get(Vector2i(ix, iz))
			if list == null:
				continue
			for s in list:
				var ax: float = s[0]
				var az: float = s[1]
				var dx: float = s[2] - ax
				var dz: float = s[3] - az
				var l2 := dx * dx + dz * dz
				var t := 0.0 if l2 < 1e-6 else clampf(((x - ax) * dx + (z - az) * dz) / l2, 0.0, 1.0)
				var px := ax + dx * t
				var pz := az + dz * t
				var d := Vector2(x - px, z - pz).length()
				if pref_name != "" and String(roads[s[4]].get("name", "")) != pref_name:
					d += 12.0
				if d < best_d:
					best_d = d
					var ln := sqrt(l2)
					var rp: Array = roads[s[4]]["pts"]
					var py: float = lerpf(float(rp[s[5]][2]), float(rp[s[5] + 1][2]), t)
					best = {"d": d, "px": px, "pz": pz, "py": py, "bridge": bool(roads[s[4]].get("bridge", false)), "tx": dx / maxf(ln, 1e-6), "tz": dz / maxf(ln, 1e-6), "road": roads[s[4]]}
	return best
