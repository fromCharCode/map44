shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

// Quadermauerwerk der historischen Sandsteinbrücken (Augustus-, Marien-, Albertbrücke, Viadukte), Weltkoordinaten.
// Elbsandstein dunkelt ungleichmäßig nach: jeder Quader hat seinen eigenen Ton, erneuerte Steine sind hell
// gelblich, unter Gesimsen und an Pfeilern laufen dunkle Fahnen. Ohne das wirkte die Schattenseite der Brücken
// als eine einzige dunkle Fläche.

global uniform float wetness;

uniform sampler2D stone_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D stone_normal : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D stone_rough : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float tile_m = 2.0;
uniform vec3 tint : source_color = vec3(0.94, 0.90, 0.82);
uniform vec2 block_m = vec2(1.15, 0.52);     // Quaderlänge, Schichthöhe
uniform float fresh = 0.1;                   // Anteil erneuerter (heller) Quader

varying vec3 wpos;
varying vec3 wnorm;

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 345.45));
	p += dot(p, p + 34.345);
	return fract(p.x * p.y);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x), mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), f.x), f.y);
}

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnorm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 n = normalize(wnorm);
	// Wandflächen: Länge entlang der Wand, Höhe; Laibungen und Abdeckungen: Grundriss
	vec2 uv;
	float wall = step(abs(n.y), 0.6);
	if (wall > 0.5) {
		vec2 h = normalize(n.xz + vec2(0.0001));
		uv = vec2(dot(wpos.xz, vec2(-h.y, h.x)), wpos.y);
	} else {
		uv = wpos.xz;
	}
	vec3 tex = texture(stone_albedo, uv / tile_m).rgb;
	vec3 nrm = texture(stone_normal, uv / tile_m).rgb;
	float rough = texture(stone_rough, uv / tile_m).r;
	// Läuferverband: jede zweite Schicht um eine halbe Quaderlänge versetzt
	float row = floor(uv.y / block_m.y);
	vec2 cell = vec2(floor(uv.x / block_m.x + 0.5 * mod(row, 2.0)), row);
	vec2 f = vec2(fract(uv.x / block_m.x + 0.5 * mod(row, 2.0)), fract(uv.y / block_m.y));
	float h1 = hash21(cell);
	float h2 = hash21(cell + 17.3);
	float tone = mix(0.78, 1.18, h1);
	vec3 col = tex * tint * tone;
	// erneuerte Quader: hell und gelblich
	float is_new = step(1.0 - fresh, h2);
	col = mix(col, tex * vec3(0.86, 0.76, 0.56), is_new * 0.85);
	// Fugen (ab etwa 60 m verschwinden sie im Mip-Rauschen, daher weich ausblenden)
	float dist = length(wpos - CAMERA_POSITION_WORLD);
	vec2 jw = vec2(0.018 / block_m.x, 0.018 / block_m.y) * (1.0 + dist * 0.02);
	float joint = 1.0 - min(smoothstep(0.0, jw.x, min(f.x, 1.0 - f.x)), smoothstep(0.0, jw.y, min(f.y, 1.0 - f.y)));
	col *= 1.0 - 0.45 * joint * clamp(1.6 - dist / 90.0, 0.25, 1.0);
	// Verwitterung: große Flecken und senkrechte Ablauffahnen (nur an Wänden)
	float blot = vnoise(uv * vec2(0.11, 0.17));
	float streak = vnoise(vec2(uv.x * 0.9, uv.y * 0.07)) * wall;
	col *= mix(0.78, 1.08, blot) * (1.0 - 0.28 * smoothstep(0.55, 0.9, streak));
	ALBEDO = col * mix(1.0, 0.72, wetness);
	ROUGHNESS = clamp(rough * mix(1.0, 0.55, wetness), 0.3, 1.0);
	// Normalenkarte im Weltraum auswerten: die Brückennetze haben keine Tangenten – NORMAL_MAP ergab damit
	// falsche Beleuchtung (Brüstungen fast schwarz). Tangente = entlang der Wand bzw. x, Bitangente = oben bzw. z.
	vec3 tw;
	vec3 bw;
	if (wall > 0.5) {
		vec2 hh = normalize(n.xz + vec2(0.0001));
		tw = vec3(-hh.y, 0.0, hh.x);
		bw = vec3(0.0, 1.0, 0.0);
	} else {
		tw = vec3(1.0, 0.0, 0.0);
		bw = vec3(0.0, 0.0, 1.0);
	}
	vec2 d = (nrm.xy * 2.0 - 1.0) * 0.9;
	vec3 wn = normalize(n + tw * d.x + bw * d.y);
	NORMAL = normalize((VIEW_MATRIX * vec4(wn, 0.0)).xyz);
}
