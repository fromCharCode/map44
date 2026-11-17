extends Node
## Entwickler: Strahl senkrecht an (x, z) – alle Treffer mit Besitzer (Kachel 3×3 wird geladen).
##   godot --headless --path . -- --cam=0,0,0,-30,80 --proberay=<kachel>:<x>:<z>:<y_oben>
func run(main: Node, spec: String) -> void:
	var p := spec.split(":")
	var k := p[0]
	var x := float(p[1])
	var z := float(p[2])
	var y0 := float(p[3])
	main.world.enabled = false
	await main.world.load_now(k)
	for i in 6:
		await get_tree().physics_frame
	var space := get_viewport().world_3d.direct_space_state
	var excl: Array[RID] = []
	for i in 8:
		var q := PhysicsRayQueryParameters3D.create(Vector3(x, y0, z), Vector3(x, y0 - 12.0, z), 1)
		q.hit_back_faces = true
		q.exclude = excl
		var h := space.intersect_ray(q)
		if h.is_empty():
			break
		print("PROBE y=%.2f n=%s %s" % [h["position"].y, str(h["normal"]), BridgeAudit.owner_of(h["collider"])])
		excl.append(h["rid"])
	main.get_tree().quit()
