class_name SignalCtl
extends RefCounted
## Ampelumlauf (identisch zu shaders/signal_lamp.gdshader und tools/junctions.py):
## ctl = [Versatz, Grünzeit Phase 0, Grünzeit Phase 1, ...]; je Phase Grün g, dann 3 s Gelb, 2 s Alles-Rot,
## in der letzten Sekunde davon zeigt die nächste Phase Rot-Gelb.

enum { RED, RED_YELLOW, GREEN, YELLOW }
const YELLOW_T := 3.0
const ALLRED_T := 2.0

## Gemeinsame Uhr für Ampeln (Shader-Global "signal_clock" wird von Dressing gesetzt)
static var clock := 0.0


static func state(ctl: Array, ph: int, t: float = -1.0) -> int:
	if ctl.is_empty() or ph < 0:
		return GREEN
	if t < 0.0:
		t = clock
	var n := ctl.size() - 1
	var cycle := 0.0
	for i in n:
		cycle += float(ctl[1 + i]) + YELLOW_T + ALLRED_T
	var lt := fposmod(t + float(ctl[0]), cycle)
	var start := 0.0
	for i in n:
		var g := float(ctl[1 + i])
		var dur := g + YELLOW_T + ALLRED_T
		if lt < start + dur:
			var k := lt - start
			if ph == i:
				if k < g:
					return GREEN
				if k < g + YELLOW_T:
					return YELLOW
				return RED
			if ph == (i + 1) % n and k >= g + YELLOW_T + ALLRED_T - 1.0:
				return RED_YELLOW
			return RED
		start += dur
	return RED


## Restzeit (s) bis die Phase ph wieder Grün zeigt (0 = jetzt Grün)
static func time_to_green(ctl: Array, ph: int, t: float = -1.0) -> float:
	if state(ctl, ph, t) == GREEN:
		return 0.0
	if t < 0.0:
		t = clock
	for k in range(1, 120):
		if state(ctl, ph, t + float(k) * 0.5) == GREEN:
			return float(k) * 0.5
	return 60.0
