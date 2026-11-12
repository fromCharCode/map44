shader_type sky;

// Tageszeit-Himmel: Verlauf, Dämmerung, Sonne, Mond, Sterne, Wolken.

uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);
uniform vec3 moon_dir = vec3(0.0, -1.0, 0.0);
uniform float cloud_cover : hint_range(0.0, 1.0) = 0.42;
uniform float cloud_dark : hint_range(0.0, 1.0) = 0.0;
uniform sampler2D cloud_noise : filter_linear_mipmap, repeat_enable;

float hash13(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.zyx + 31.32);
	return fract((p.x + p.y) * p.z);
}

float fbm(vec2 uv) {
	float a = 0.5;
	float s = 0.0;
	for (int i = 0; i < 4; i++) {
		s += a * texture(cloud_noise, uv).r;
		uv = uv * 2.03 + vec2(0.17, 0.31);
		a *= 0.5;
	}
	return s;
}

void sky() {
	vec3 dir = normalize(EYEDIR);
	float sh = sun_dir.y;
	float day = smoothstep(-0.14, 0.12, sh);
	float twi = smoothstep(-0.22, -0.02, sh) * (1.0 - smoothstep(0.02, 0.32, sh));

	vec3 zen_day = vec3(0.10, 0.27, 0.62);
	vec3 hor_day = vec3(0.50, 0.66, 0.86);
	vec3 zen_night = vec3(0.002, 0.004, 0.014);
	vec3 hor_night = vec3(0.012, 0.018, 0.04);
	vec3 zen = mix(zen_night, zen_day, day);
	vec3 hor = mix(hor_night, hor_day, day);

	float up = clamp(dir.y, 0.0, 1.0);
	vec3 col = mix(hor, zen, pow(up, 0.42));

	// Dämmerung: warmer Horizont zur Sonne hin
	vec2 hdir = normalize(dir.xz + 1e-5);
	vec2 hsun = normalize(sun_dir.xz + 1e-5);
	float toward = max(dot(hdir, hsun), 0.0);
	float hglow = exp(-pow(max(dir.y, 0.0) * 3.2, 1.0)) * twi;
	col += vec3(1.0, 0.42, 0.14) * hglow * pow(toward, 2.5) * 1.3;
	col += vec3(0.55, 0.28, 0.4) * hglow * 0.35;

	// Unterhalb des Horizonts: dunkler Dunst (Reflexionen)
	if (dir.y < 0.0) {
		float g = smoothstep(0.0, -0.35, dir.y);
		col = mix(hor, hor * vec3(0.55, 0.52, 0.5), g);
	}

	// Sonnenscheibe + Halo
	float sd = dot(dir, sun_dir);
	float sun_disk = smoothstep(0.99970, 0.99985, sd);
	col += vec3(1.0, 0.92, 0.78) * sun_disk * 45.0 * smoothstep(-0.05, 0.05, sh);
	col += vec3(1.0, 0.8, 0.55) * pow(max(sd, 0.0), 24.0) * 0.55 * day;
	col += vec3(1.0, 0.7, 0.4) * pow(max(sd, 0.0), 400.0) * 1.5 * day;

	// Mond
	float md = dot(dir, moon_dir);
	float moon_disk = smoothstep(0.99955, 0.99975, md);
	col += vec3(0.75, 0.82, 0.95) * moon_disk * 3.0 * (1.0 - day) * smoothstep(-0.05, 0.05, moon_dir.y);
	col += vec3(0.4, 0.5, 0.75) * pow(max(md, 0.0), 60.0) * 0.25 * (1.0 - day) * smoothstep(-0.05, 0.05, moon_dir.y);

	// Sterne
	if (dir.y > 0.0) {
		vec3 sp = floor(dir * 260.0);
		float h = hash13(sp);
		float star = step(0.9965, h) * (0.4 + 0.6 * hash13(sp + 7.0));
		col += vec3(0.9, 0.95, 1.0) * star * (1.0 - day) * smoothstep(0.0, 0.15, dir.y) * 1.2;
	}

	// Wolken
	if (dir.y > 0.01) {
		vec2 cuv = dir.xz / (dir.y + 0.18) * 0.22 + vec2(TIME * 0.0025, TIME * 0.0011);
		float f = fbm(cuv);
		float dens = smoothstep(1.0 - cloud_cover - 0.12, 1.0 - cloud_cover + 0.18, f);
		float edge = smoothstep(0.0, 0.12, dir.y);
		dens *= edge;
		// Beleuchtung: heller zur Sonne, Unterseite dunkler
		float lit = clamp(0.55 + 0.6 * dot(vec3(0.0, 1.0, 0.0), sun_dir) + pow(max(sd, 0.0), 6.0) * 0.8, 0.0, 1.6);
		vec3 sun_col = mix(vec3(1.0, 0.55, 0.25), vec3(1.0, 0.97, 0.92), smoothstep(0.0, 0.35, sh));
		vec3 ccol = mix(vec3(0.42, 0.45, 0.52), sun_col * 1.05, clamp(lit - cloud_dark * 0.6, 0.0, 1.0));
		ccol = mix(ccol * 0.8, ccol, 1.0 - smoothstep(0.35, 0.85, f));
		ccol *= mix(0.04, 1.0, day);
		ccol = mix(ccol, vec3(0.28, 0.3, 0.34) * mix(0.05, 1.0, day), cloud_dark);
		col = mix(col, ccol, dens * 0.92);
	}
	COLOR = col;
}
