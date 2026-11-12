shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
// Wählt je Instanz eine Zelle eines Texturatlas (INSTANCE_CUSTOM.x = Zellindex, zeilenweise von oben links).
// Für Verkehrszeichen, Plakate (Litfaßsäule, Plakatwand, Aufsteller) und Müll-Decals.
uniform sampler2D atlas : source_color, filter_linear_mipmap_anisotropic;
uniform vec2 grid = vec2(8.0, 4.0);
uniform bool alpha_cut = true;
uniform float u_repeat = 1.0;        // mehrere Felder um den Umfang
uniform bool litfass = false;        // Litfaßsäule: unten (2/3) 3 Felder, oben (1/3) 6 Felder, je A-Format
uniform bool v_from_bottom = false;  // Mantel-UV der Modelle: v = 0 an der OBERKANTE (gemessen, MANIFEST)
varying float cell;

void vertex() {
	cell = INSTANCE_CUSTOM.x;
}

void fragment() {
	float c = floor(cell + 0.5);
	vec2 u = vec2(fract(UV.x * u_repeat), UV.y);
	if (litfass) {
		float vb = v_from_bottom ? UV.y : 1.0 - UV.y;          // 0 unten .. 1 oben
		float field;
		if (vb < 2.0 / 3.0) {
			field = floor(UV.x * 3.0);
			u = vec2(fract(UV.x * 3.0), 1.0 - vb * 1.5);
		} else {
			field = 3.0 + floor(UV.x * 6.0);
			u = vec2(fract(UV.x * 6.0), 1.0 - (vb - 2.0 / 3.0) * 3.0);
		}
		c = mod(c + field * 3.0, grid.x * grid.y);
	}
	vec2 cxy = vec2(mod(c, grid.x), floor(c / grid.x));
	vec2 uv = (clamp(u, vec2(0.002), vec2(0.998)) + cxy) / grid;
	vec4 t = texture(atlas, uv);
	if (alpha_cut && t.a < 0.45) {
		discard;
	}
	ALBEDO = t.rgb;
	ROUGHNESS = 0.55;
	SPECULAR = 0.4;
}
