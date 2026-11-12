shader_type spatial;
// Lichtkegel einer Straßenlaterne auf dem Boden: additiv, weich, nur nachts (globale Variable "night").
render_mode blend_add, unshaded, depth_draw_never, cull_disabled, shadows_disabled;
global uniform float night;
global uniform float wetness;
uniform vec3 color : source_color = vec3(1.0, 0.72, 0.42);
uniform float strength = 0.3;

void fragment() {
	vec2 d = UV * 2.0 - 1.0;
	float r = length(d);
	float f = pow(clamp(1.0 - r, 0.0, 1.0), 1.8);
	// nasse Straße: stärkerer, glänzender Fleck
	ALBEDO = color * f * strength * night * (1.0 + wetness * 0.35);
	ALPHA = 1.0;
}
