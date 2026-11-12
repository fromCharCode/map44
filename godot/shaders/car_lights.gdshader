shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
// Fahrzeugleuchten der KI-Autos: ein gemeinsames Material je Leuchtenart, Zustand je Fahrzeug über
// Instanz-Uniforms (MeshInstance3D.set_instance_shader_parameter). Blinker links/rechts über das Vorzeichen
// der Modell-x-Koordinate (Fahrzeug schaut nach −Z, rechts = +X).
uniform int kind = 0;            // 0 Scheinwerfer, 1 Blinker, 2 Rücklicht, 3 Bremslicht
uniform vec3 base_col = vec3(0.9);
uniform vec3 glow_col = vec3(1.0, 0.95, 0.85);
instance uniform float lights_on = 0.0;
instance uniform float brake_on = 0.0;
instance uniform float ind_l = 0.0;
instance uniform float ind_r = 0.0;
varying float side;

void vertex() {
	side = VERTEX.x;
}

void fragment() {
	float e = 0.0;
	if (kind == 0) {
		e = lights_on * 3.0;
	} else if (kind == 1) {
		float blink = step(0.5, fract(TIME * 1.45 + 0.13));
		e = (side < 0.0 ? ind_l : ind_r) * blink * 4.0;
	} else if (kind == 2) {
		e = lights_on * 1.1 + brake_on * 0.4;
	} else {
		e = brake_on * 3.2 + lights_on * 0.25;
	}
	ALBEDO = base_col * (0.25 + 0.75 * clamp(e, 0.0, 1.0));
	EMISSION = glow_col * e;
	ROUGHNESS = 0.2;
	SPECULAR = 0.7;
}
