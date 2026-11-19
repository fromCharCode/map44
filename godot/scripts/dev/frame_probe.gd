class_name FrameProbe
extends Node
## Diagnose (--attachtrace): zerlegt lange Bilder in Abschnitte der Hauptschleife:
##   Render+Leerlauf (Ende Process des Vorbilds bis erster Physikschritt), Physik-Skripte, Physik-Engine + Signale
##   (letztes _physics_process bis erstes _process), Process-Skripte.

static var t_first := 0
static var t_last := 0
static var ph_first := 0
static var ph_last := 0
static var ph_sum := 0
static var ph_n := 0
static var t_prev_last := 0
var is_last := false


static func install(root: Node) -> void:
	var a := FrameProbe.new()
	a.process_priority = -100000
	a.process_physics_priority = -100000
	root.add_child(a)
	var b := FrameProbe.new()
	b.is_last = true
	b.process_priority = 100000
	b.process_physics_priority = 100000
	root.add_child(b)


func _physics_process(_d: float) -> void:
	var now := Time.get_ticks_usec()
	if is_last:
		ph_last = now
		ph_sum += now - ph_first
	else:
		if ph_n == 0:
			FrameProbe.ph0 = now
		ph_first = now
		ph_n += 1

static var ph0 := 0


func _process(_d: float) -> void:
	var now := Time.get_ticks_usec()
	if is_last:
		t_prev_last = t_last
		t_last = now
		if t_prev_last > 0 and now - t_prev_last > 80000:
			var p0 := ph0 if ph_n > 0 else t_first
			print("FRAME %d ms: Render/Leerlauf %d, Physik-Skripte %d (%d Schritte), Physik-Engine+Signale %d, Process-Skripte %d" % [
				(now - t_prev_last) / 1000, (p0 - t_prev_last) / 1000, ph_sum / 1000, ph_n,
				(t_first - p0 - ph_sum) / 1000 if ph_n > 0 else 0, (now - t_first) / 1000])
			var fr := Engine.get_process_frames()
			var evs: Array = []
			for e in World.ev:
				if fr - int(e[0]) <= 3:
					evs.append("%s (-%d)" % [e[1], fr - int(e[0])])
			if not evs.is_empty():
				print("   Ereignisse: " + ", ".join(evs))
			if (p0 - t_prev_last) > 60000:
				print("   davor angehängt (%d): %s" % [World.att2.size(), ", ".join(World.att2.slice(0, 40))])
		ph_n = 0
		ph_sum = 0
		return
	t_first = now
