class_name RenderUtil
extends RefCounted
## Kleine Render-Hilfen.


## Nimmt alle Geometrie unter root aus der globalen Beleuchtung (SDFGI) heraus.
## Godot behandelt jede GeometryInstance3D standardmäßig als GI_MODE_STATIC: bewegte Objekte (Autos, Fußgänger,
## Bahnen) zwingen SDFGI dann ständig zum Neu-Voxelisieren, und zehntausende Kleinteile (Schilder, Poller, Laub)
## werden in die GI-Felder gerastert, ohne sichtbar zum indirekten Licht beizutragen. In Gelände, Gebäuden,
## Straßen und Mauern bleibt GI an.
static func gi_off(root: Node) -> void:
	if root == null:
		return
	var stack: Array = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is GeometryInstance3D:
			(n as GeometryInstance3D).gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		for c in n.get_children():
			stack.append(c)


## Füllt ein MultiMesh mit EINEM RenderingServer-Aufruf (Puffer) statt je Instanz einem.
## Aufrufe aus dem Kachel-Thread landen in Godots Befehlswarteschlange und werden im Haupt-Thread abgearbeitet:
## 50 000–100 000 Einzelaufrufe je Kachel ergaben Ruckler von 100–200 ms.
## xfs: Array[Transform3D]; part_xf wird rechts angehängt (Teil-Versatz im Modell); colors/custom optional
## (nur wenn mm.use_colors / mm.use_custom_data vor dem Aufruf gesetzt sind).
static func fill_multimesh(mm: MultiMesh, xfs: Array, part_xf: Transform3D = Transform3D.IDENTITY, colors: Array = [], custom: Array = []) -> void:
	var n := xfs.size()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.instance_count = n
	if n == 0:
		return
	var uc := mm.use_colors
	var ud := mm.use_custom_data
	var stride := 12 + (4 if uc else 0) + (4 if ud else 0)
	var buf := PackedFloat32Array()
	buf.resize(n * stride)
	var has_part := part_xf != Transform3D.IDENTITY
	var j := 0
	for i in n:
		var t: Transform3D = xfs[i]
		if has_part:
			t = t * part_xf
		var b := t.basis
		buf[j] = b.x.x
		buf[j + 1] = b.y.x
		buf[j + 2] = b.z.x
		buf[j + 3] = t.origin.x
		buf[j + 4] = b.x.y
		buf[j + 5] = b.y.y
		buf[j + 6] = b.z.y
		buf[j + 7] = t.origin.y
		buf[j + 8] = b.x.z
		buf[j + 9] = b.y.z
		buf[j + 10] = b.z.z
		buf[j + 11] = t.origin.z
		j += 12
		if uc:
			var c: Color = colors[i] if i < colors.size() else Color.WHITE
			buf[j] = c.r
			buf[j + 1] = c.g
			buf[j + 2] = c.b
			buf[j + 3] = c.a
			j += 4
		if ud:
			var cd: Color = custom[i] if i < custom.size() else Color(0, 0, 0, 0)
			buf[j] = cd.r
			buf[j + 1] = cd.g
			buf[j + 2] = cd.b
			buf[j + 3] = cd.a
			j += 4
	mm.buffer = buf
