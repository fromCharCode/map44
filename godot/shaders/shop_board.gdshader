shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
// Ladenschild-Tafeln: Farbe aus der Vertexfarbe, Oberfläche je Kategorie aus COLOR.a (Index / 8):
// 0 Lack matt, 1 Holz, 2 gebürstetes Metall, 3 Emaille glänzend, 4 Leuchtkasten (nachts hell).
global uniform float night;
varying vec3 wp;
varying flat int kind;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

void vertex() {
	wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	kind = int(floor(COLOR.a * 8.0 + 0.5));
}

void fragment() {
	vec3 base = COLOR.rgb;
	float along = wp.x + wp.z;              // grob entlang der Tafel (Wände liegen in beliebiger Richtung)
	float rough = 0.8;
	float metal = 0.0;
	float spec = 0.4;
	vec3 em = vec3(0.0);
	if (kind == 1) {
		// Holz: waagerechte Maserung, leicht wellig, dazu Brettfugen
		float warp = vnoise(vec2(along * 1.2, wp.y * 6.0)) * 6.0;
		float grain = 0.5 + 0.5 * sin(wp.y * 140.0 + warp + vnoise(vec2(along * 4.0, wp.y * 30.0)) * 3.0);
		float joint = smoothstep(0.004, 0.0, abs(fract(wp.y / 0.13) - 0.5) - 0.49);
		base *= 0.82 + 0.22 * grain + 0.1 * vnoise(vec2(along * 9.0, wp.y * 90.0));
		base *= 1.0 - 0.35 * joint;
		rough = 0.72;
	} else if (kind == 2) {
		// gebürstetes Metall: feine waagerechte Striche
		float st = hash(vec2(floor(wp.y * 900.0), 0.0)) * 0.6 + vnoise(vec2(along * 3.0, wp.y * 900.0)) * 0.4;
		base *= 0.9 + 0.16 * st;
		metal = 0.65;
		rough = 0.32 + 0.1 * st;
		spec = 0.6;
	} else if (kind == 3) {
		base *= 0.97 + 0.03 * vnoise(wp.xz * 30.0 + wp.y * 30.0);
		rough = 0.14;
		spec = 0.7;
	} else if (kind == 4) {
		// Leuchtkasten: Kunststofffront, nachts von innen beleuchtet
		rough = 0.35;
		spec = 0.5;
		em = base * (0.08 + 1.3 * night);
	} else {
		base *= 0.95 + 0.06 * vnoise(wp.xz * 25.0 + wp.y * 25.0);
	}
	ALBEDO = base;
	ROUGHNESS = rough;
	METALLIC = metal;
	SPECULAR = spec;
	EMISSION = em;
}
