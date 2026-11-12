shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

// Dächer: Farbe pro Gebäude (aus dem Luftbild) x Ziegel-/Schiefertextur, Weltkoordinaten-Mapping.

global uniform float wetness;

uniform sampler2D roof_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D roof_normal : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D roof_rough : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float tile_m = 1.6;

varying vec3 wpos;
varying vec3 wnorm;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnorm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	// Planar nach Dachneigung: Projektion entlang der dominanten horizontalen Achse
	vec3 n = normalize(wnorm);
	vec2 uv = wpos.xz / tile_m;
	if (n.y < 0.9) {
		// steiles Dach: Koordinate entlang der Neigung
		vec2 h = normalize(n.xz + vec2(0.0001));
		float along = dot(wpos.xz, vec2(-h.y, h.x));
		float up = wpos.y / max(n.y, 0.3);
		uv = vec2(along, up) / tile_m;
	}
	vec3 a = texture(roof_albedo, uv).rgb;
	float l = dot(a, vec3(0.3, 0.59, 0.11));
	vec3 col = COLOR.rgb * 0.72 * mix(0.65, 1.35, clamp(l * 1.6, 0.0, 1.0));
	ALBEDO = col;
	ROUGHNESS = mix(texture(roof_rough, uv).r, 0.25, wetness * 0.5);
	SPECULAR = 0.4;
	NORMAL_MAP = texture(roof_normal, uv).xyz;
	NORMAL_MAP_DEPTH = 1.0;
}
