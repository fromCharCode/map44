shader_type canvas_item;
// Leichte Nachbearbeitung im Stil eines "gritty" Stadtspiels: Vignette, Filmkorn, minimale Farbsäume.
uniform sampler2D screen_tex : hint_screen_texture, filter_linear, repeat_disable;
uniform float vignette : hint_range(0.0, 1.0) = 0.32;
uniform float grain : hint_range(0.0, 0.2) = 0.035;
uniform float aberration : hint_range(0.0, 0.01) = 0.0006;

float hash(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 c = uv - 0.5;
	float r2 = dot(c, c);
	vec2 off = c * r2 * aberration * 12.0;
	vec3 col;
	col.r = texture(screen_tex, uv + off).r;
	col.g = texture(screen_tex, uv).g;
	col.b = texture(screen_tex, uv - off).b;
	float v = 1.0 - vignette * smoothstep(0.12, 0.62, r2 * 1.9);
	col *= v;
	float g = hash(floor(FRAGCOORD.xy) + fract(TIME) * 61.0) - 0.5;
	col += g * grain * (1.0 - dot(col, vec3(0.33)) * 0.6);
	COLOR = vec4(col, 1.0);
}
