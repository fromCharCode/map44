shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// Elbe / Teiche: dunkles Wasser, Wellen aus Rauschtextur, Ufertransparenz über Tiefenpuffer.

uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;
uniform vec3 deep_color : source_color = vec3(0.035, 0.065, 0.06);
uniform vec3 shallow_color : source_color = vec3(0.16, 0.24, 0.2);
uniform float flow_speed = 0.35;
uniform vec2 flow_dir = vec2(0.8, 0.6);

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

vec2 wave_grad(vec2 p, float t) {
	vec2 uv1 = p * 0.045 + flow_dir * t * 0.02;
	vec2 uv2 = p * 0.13 - flow_dir.yx * t * 0.035;
	vec2 uv3 = p * 0.5 + flow_dir * t * 0.1;
	float e = 0.004;
	vec2 g = vec2(0.0);
	g += vec2(texture(noise_tex, uv1 + vec2(e, 0.0)).r - texture(noise_tex, uv1 - vec2(e, 0.0)).r,
			texture(noise_tex, uv1 + vec2(0.0, e)).r - texture(noise_tex, uv1 - vec2(0.0, e)).r) * 0.9;
	g += vec2(texture(noise_tex, uv2 + vec2(e, 0.0)).r - texture(noise_tex, uv2 - vec2(e, 0.0)).r,
			texture(noise_tex, uv2 + vec2(0.0, e)).r - texture(noise_tex, uv2 - vec2(0.0, e)).r) * 0.6;
	g += vec2(texture(noise_tex, uv3 + vec2(e, 0.0)).r - texture(noise_tex, uv3 - vec2(e, 0.0)).r,
			texture(noise_tex, uv3 + vec2(0.0, e)).r - texture(noise_tex, uv3 - vec2(0.0, e)).r) * 0.25;
	return g / (2.0 * e);
}

void fragment() {
	float t = TIME * flow_speed;
	vec2 g = wave_grad(wpos.xz, t) * 0.011;
	vec3 n = normalize(vec3(-g.x, 1.0, -g.y));
	// Normale im Tangentenraum (Tangent = +x, Binormal = -z)
	NORMAL_MAP = vec3(n.x, -n.z, n.y) * 0.5 + 0.5;
	NORMAL_MAP_DEPTH = 1.0;

	float depth = texture(depth_tex, SCREEN_UV).r;
	vec3 ndc = vec3(SCREEN_UV * 2.0 - 1.0, depth);
	vec4 view = INV_PROJECTION_MATRIX * vec4(ndc, 1.0);
	view.xyz /= view.w;
	float thick = max(-view.z + VERTEX.z, 0.0);

	float fade = clamp(thick * 0.55, 0.0, 1.0);
	vec3 col = mix(shallow_color, deep_color, smoothstep(0.0, 3.5, thick));
	ALBEDO = col;
	ROUGHNESS = 0.09;
	SPECULAR = 0.6;
	METALLIC = 0.0;
	ALPHA = mix(0.0, 0.93, smoothstep(0.0, 1.2, thick));
	ALPHA = max(ALPHA, 0.0);
}
