extends SceneTree
## Vorbacken BC-komprimierter Texturen für das exportierte Spiel (die Exportvorlagen haben keinen BC-Kompressor).
##   godot --headless --path godot -s res://scripts/dev/bake_textures.gd -- --texcache
##       -> res://texcache/*.res (TexLib-Materialsätze, landen im .pck)
##   godot --headless --path godot -s res://scripts/dev/bake_textures.gd -- --tiles_src=<dir> --tiles_out=<dir> [--part=i/n]
##       -> <tiles_out>/<kachel>/tex_splat1.res, tex_splat2.res, tex_ortho.res (für das Datenpaket)
## Aufgerufen von tools/package_release.sh.


func _init() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else ""
	if args.has("texcache"):
		_bake_texcache()
	if args.has("tiles_src"):
		_bake_tiles(String(args["tiles_src"]), String(args.get("tiles_out", args["tiles_src"])), String(args.get("part", "0/1")))
	quit()


func _bake_texcache() -> void:
	TexLib.bake_dir = "res://texcache/"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(TexLib.bake_dir))
	var n := 0
	var d := DirAccess.open(TexLib.ROOT)
	for sub in d.get_directories():
		if not FileAccess.file_exists(TexLib.ROOT + sub + "/albedo.jpg"):
			continue
		for kind in ["albedo", "normal", "rough"]:
			TexLib.image(sub, kind, 1024)
			n += 1
	TexLib.bake_dir = ""
	print("BAKE texcache: %d Bilder -> res://texcache/" % n)


func _bake_tiles(src: String, out: String, part: String) -> void:
	var pi := int(part.get_slice("/", 0))
	var pn := maxi(int(part.get_slice("/", 1)), 1)
	var d := DirAccess.open(src)
	if d == null:
		push_error("Kein Kachelordner: " + src)
		return
	var keys := Array(d.get_directories())
	keys.sort()
	var n := 0
	var t0 := Time.get_ticks_msec()
	for i in keys.size():
		if i % pn != pi:
			continue
		var k: String = keys[i]
		var sd := src.path_join(k) + "/"
		if not FileAccess.file_exists(sd + "ortho.jpg"):
			continue
		var od := out.path_join(k) + "/"
		DirAccess.make_dir_recursive_absolute(od)
		var imgs := Terrain.prepare_images(sd)
		for key in Terrain.BAKED:
			ResourceSaver.save(imgs[key], od + String(Terrain.BAKED[key]), ResourceSaver.FLAG_COMPRESS)
		n += 1
	print("BAKE Kacheln Teil %d/%d: %d Kacheln in %.0f s" % [pi, pn, n, (Time.get_ticks_msec() - t0) / 1000.0])
