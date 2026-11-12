shader_type spatial;
// Regentropfen-Strich: blendet nahe der Kamera aus (sonst riesige Streifen direkt vor der Linse)
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled;
uniform vec4 color : source_color = vec4(0.75, 0.8, 0.88, 0.22);

void vertex() {
	// zylindrisches Billboard um die Y-Achse
	vec3 cam = (INV_VIEW_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	vec3 wpos = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	vec3 to_cam = normalize(vec3(cam.x - wpos.x, 0.0, cam.z - wpos.z));
	vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), to_cam));
	vec3 world = wpos + right * VERTEX.x + vec3(0.0, VERTEX.y, 0.0);
	VERTEX = (inverse(MODEL_MATRIX) * vec4(world, 1.0)).xyz;
}

void fragment() {
	float dist = -VERTEX.z;
	float fade = smoothstep(1.5, 4.0, dist) * (1.0 - smoothstep(25.0, 34.0, dist));
	float edge = 1.0 - abs(UV.x * 2.0 - 1.0);
	ALBEDO = color.rgb;
	ALPHA = color.a * fade * edge;
}
