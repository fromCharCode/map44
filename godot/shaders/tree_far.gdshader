shader_type spatial;
// Fernkronen (Dressing._blob_for, ab ~150 m): Laubklumpen mit dunklen Lücken statt glatter Kugel.
// Rauschen in Weltkoordinaten (je Baum anders), Lichtkante oben heller, etwas Durchscheinen.
render_mode cull_back, diffuse_burley;

varying vec3 wpos;
varying float crown;

float hash3(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float vnoise(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(hash3(i + vec3(0, 0, 0)), hash3(i + vec3(1, 0, 0)), f.x),
	               mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
	           mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x),
	               mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	crown = COLOR.a;                       // 1 = Krone, 0 = Stamm
}

void fragment() {
	vec3 base = COLOR.rgb;
	if (crown > 0.5) {
		float n1 = vnoise(wpos * 0.9);
		float n2 = vnoise(wpos * 2.3 + vec3(5.1, 1.7, 3.3));
		float clump = smoothstep(0.3, 0.72, n1 * 0.6 + n2 * 0.4);
		// Lücken zwischen den Laubballen dunkel, Ballen oben heller (Himmelslicht)
		float up = clamp((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).y, 0.0, 1.0);
		base *= mix(0.5, 1.12, clump) * mix(0.9, 1.08, up);
		// unruhige Normale (Blattmasse) – nur leicht, sonst flimmert es in der Ferne
		vec3 g = vec3(vnoise(wpos * 2.3 + vec3(1.7, 0.0, 0.0)), vnoise(wpos * 2.3 + vec3(0.0, 2.9, 0.0)),
				vnoise(wpos * 2.3 + vec3(0.0, 0.0, 4.1))) - 0.5;
		NORMAL = normalize(NORMAL + (VIEW_MATRIX * vec4(g * 0.9, 0.0)).xyz);
		BACKLIGHT = base * 0.35;
		ROUGHNESS = 0.92;
		SPECULAR = 0.25;
	} else {
		ROUGHNESS = 0.95;
	}
	ALBEDO = base;
}
