shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
// Ampel-Leuchte: Zustand je Instanz aus dem Umlauf (INSTANCE_CUSTOM = Versatz, Phase, Grün0, Grün1) und der
// globalen Ampeluhr – identisch zu scripts/signal_ctl.gd (2 Phasen, 3 s Gelb, 2 s Alles-Rot, 1 s Rot-Gelb).
uniform int lamp = 0;            // 0 Rot, 1 Gelb, 2 Grün
uniform vec3 lamp_col = vec3(1.0, 0.1, 0.05);
global uniform float signal_clock;
varying vec4 ctl;

void vertex() {
	ctl = INSTANCE_CUSTOM;
}

void fragment() {
	float g0 = max(ctl.z, 1.0);
	float g1 = max(ctl.w, 1.0);
	float d0 = g0 + 5.0;
	float d1 = g1 + 5.0;
	float lt = mod(signal_clock + ctl.x, d0 + d1);
	float active = lt < d0 ? 0.0 : 1.0;
	float k = active < 0.5 ? lt : lt - d0;
	float g = active < 0.5 ? g0 : g1;
	int st = 0;                   // 0 Rot, 1 Rot-Gelb, 2 Grün, 3 Gelb
	if (abs(ctl.y - active) < 0.5) {
		st = k < g ? 2 : (k < g + 3.0 ? 3 : 0);
	} else {
		st = k >= g + 4.0 ? 1 : 0;
	}
	bool on = (lamp == 0 && st <= 1) || (lamp == 1 && (st == 1 || st == 3)) || (lamp == 2 && st == 2);
	ALBEDO = lamp_col * (on ? 0.3 : 0.035);
	EMISSION = on ? lamp_col * 5.0 : vec3(0.0);
	ROUGHNESS = 0.25;
	SPECULAR = 0.6;
}
