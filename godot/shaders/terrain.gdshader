shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx, cull_disabled;

// Gelände: Höhe aus Heightmap (Vertex-Shader), Material aus Splat-Karten + PBR-Texturarrays.
// Layer-Indizes: 0 asphalt_new, 1 asphalt_worn, 2 sidewalk, 3 cobble, 4 paving_sandstone, 5 gravel,
//                6 grass, 7 grass_wild, 8 forest_floor, 9 mud_bank, 10 concrete, 11 sandstone

global uniform float wetness;

uniform sampler2D heightmap : filter_linear, repeat_disable;
uniform sampler2D splat0 : filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D splat1 : filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D splat2 : filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D ortho : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
uniform sampler2DArray albedo_arr : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray normal_arr : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray rough_arr : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float world_size = 2000.0;
uniform vec2 tile_center = vec2(0.0);
uniform float tile_m[13];
// Tunnelband (scripts/tunnels.gd mask_image): R = Fahrbahnhöhe, G = 1 im Band
uniform sampler2D tunnel_tex : filter_linear, repeat_disable;
uniform bool has_tunnel = false;

varying vec3 wpos;

void vertex() {
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec2 huv = (wp.xz - tile_center + world_size * 0.5) / world_size;
	float px = 1.0 / world_size;
	float h = textureLod(heightmap, huv, 0.0).r;
	float hl = textureLod(heightmap, huv - vec2(px, 0.0), 0.0).r;
	float hr = textureLod(heightmap, huv + vec2(px, 0.0), 0.0).r;
	float hu = textureLod(heightmap, huv - vec2(0.0, px), 0.0).r;
	float hd = textureLod(heightmap, huv + vec2(0.0, px), 0.0).r;
	float wmask = textureLod(splat1, huv, 0.0).a;
	VERTEX.y = h - wmask * 2.4 - COLOR.r * 4.0;
	vec3 n = normalize(vec3(hl - hr, 2.0, hu - hd));
	NORMAL = n;
	TANGENT = normalize(vec3(1.0, 0.0, 0.0) - n * n.x);
	BINORMAL = normalize(cross(n, TANGENT));
	wpos = vec3(wp.x, h, wp.z);
}

struct Layer {
	vec3 a;
	vec3 n;
	float r;
};

const mat2 ROT = mat2(vec2(0.8, 0.6), vec2(-0.6, 0.8));

// BC5-Normalen (TexLib) speichern nur XY -> Z rekonstruieren
vec3 unpack_nrm(vec4 t) {
	vec2 xy = t.xy * 2.0 - 1.0;
	return vec3(xy, sqrt(max(0.0, 1.0 - dot(xy, xy))));
}

Layer layer(int i, vec2 wuv, float k) {
	float t = tile_m[i];
	vec2 uv1 = wuv / t;
	vec2 uv2 = ROT * uv1 * 0.43 + vec2(0.37, 0.11);
	if (i == 2 || i == 3 || i == 4) { k = 0.0; }
	Layer L;
	// Anti-Kachel-Mischung nur dort doppelt lesen, wo k wirklich zwischen 0 und 1 liegt (k ist großflächig 0 oder 1)
	if (k < 0.01) { uv2 = uv1; k = 0.0; }
	else if (k > 0.99) { uv1 = uv2; k = 1.0; }
	bool two = k > 0.0 && k < 1.0;
	vec3 a1 = texture(albedo_arr, vec3(uv1, float(i))).rgb;
	vec3 a2 = two ? texture(albedo_arr, vec3(uv2, float(i))).rgb : a1;
	L.a = mix(a1, a2, k);
	// Farbgrading pro Material (Quelltexturen sind teils zu bunt/hell)
	float g = dot(L.a, vec3(0.3, 0.59, 0.11));
	if (i == 2) { L.a = mix(vec3(g), L.a, 0.45) * 0.84; }
	else if (i == 6 || i == 7) { L.a = mix(vec3(g), L.a, 0.62) * vec3(0.78, 0.82, 0.7); }
	else if (i == 8) { L.a = mix(vec3(g), L.a, 0.5) * 0.55; }
	// Asphalt: gealterter Stadtasphalt ≈ 6–8 % Albedo (Quelltexturen 2 % bzw. 6 %; vorher 2,4-facher Kontrast = Flecken)
	else if (i == 0) { L.a *= 2.7; }
	else if (i == 1) { L.a *= 1.25; }
	else if (i == 10) { L.a *= 1.35; }
	else if (i == 4) { L.a = mix(vec3(g), L.a, 0.7); }
	vec3 n1 = unpack_nrm(texture(normal_arr, vec3(uv1, float(i))));
	vec3 n2 = two ? unpack_nrm(texture(normal_arr, vec3(uv2, float(i)))) : n1;
	if (k > 0.0) { n2.xy = transpose(ROT) * n2.xy; }
	if (k >= 1.0) { n1 = n2; }
	L.n = mix(n1, n2, k);
	float r1 = texture(rough_arr, vec3(uv1, float(i))).r;
	float r2 = two ? texture(rough_arr, vec3(uv2, float(i))).r : r1;
	L.r = mix(r1, r2, k);
	return L;
}

void fragment() {
	vec2 wuv = wpos.xz;
	vec2 huv = (wpos.xz - tile_center + world_size * 0.5) / world_size;
	//@TUNNEL_CUT
	vec4 s0 = texture(splat0, huv);
	vec4 s1 = texture(splat1, huv);
	vec4 s2 = texture(splat2, huv);
	vec3 oc = texture(ortho, huv).rgb;
	float nz = texture(noise_tex, wuv * 0.9).r - 0.5;
	float nlow = texture(noise_tex, wuv * 0.011).r;
	float k = smoothstep(0.35, 0.65, texture(noise_tex, wuv * 0.021 + 0.3).r);

	// Maskenkanten schärfen und aufbrechen
	vec4 m0 = smoothstep(vec4(0.38) + nz * 0.16, vec4(0.62) + nz * 0.16, s0);
	vec4 m1 = smoothstep(vec4(0.38) + nz * 0.16, vec4(0.62) + nz * 0.16, s1);

	// Wirksames Gewicht jeder Schicht (von oben nach unten aufmultipliert): komplett verdeckte Schichten und der
	// verdeckte Grundboden werden gar nicht erst gelesen (früher lief z. B. unter jeder Straße der ganze Wiesen-/
	// Gehweg-Grund mit). Reihenfolge wie unten: Grund -> Wiese -> Wald -> Parkplatz -> Platz -> Gehweg -> Straße -> Kies
	float wa = m0.a * 0.75;
	float cov = 1.0 - wa;
	float e_road = m0.r * cov;   cov *= 1.0 - m0.r;
	float e_walk = m0.g * cov;   cov *= 1.0 - m0.g;
	float e_cob = m0.b * cov;    cov *= 1.0 - m0.b;
	float e_park = m1.b * cov;   cov *= 1.0 - m1.b;
	float e_forest = m1.g * cov; cov *= 1.0 - m1.g;
	float e_grass = m1.r * cov;  cov *= 1.0 - m1.r;
	float e_base = cov;
	const float EPS = 0.004;

	// Standardboden: Wiese wenn das Luftbild grün ist, sonst Beton/Pflaster; Hang = Erde
	float veg = smoothstep(0.012, 0.075, oc.g - max(oc.r, oc.b));
	vec3 hn = normalize(NORMAL);
	float slope = 1.0 - hn.y;
	// Gemeinsam genutzte Schichten nur einmal lesen
	bool need67 = (e_base > EPS && veg > 0.01) || e_grass > EPS;
	bool need2 = e_base > EPS || e_walk > EPS;
	Layer L2 = Layer(vec3(0.4), vec3(0.0, 0.0, 1.0), 0.8);
	Layer L6 = L2;
	Layer L7 = L2;
	if (need2) { L2 = layer(2, wuv, k); }
	if (need67) { L6 = layer(6, wuv, k); L7 = layer(7, wuv, k); }
	Layer base = Layer(vec3(0.4), vec3(0.0, 0.0, 1.0), 0.8);
	if (e_base > EPS) {
		base = L2;   // Gehwegplatten als neutraler Stadtboden
		if (veg > 0.01) {
			float gmix = smoothstep(0.4, 0.6, nlow) * 0.6;
			base.a = mix(L2.a, mix(L6.a, L7.a, gmix), veg);
			base.n = mix(L2.n, mix(L6.n, L7.n, gmix), veg);
			base.r = mix(L2.r, mix(L6.r, L7.r, gmix), veg);
		}
		if (slope > 0.07 || wpos.y < -4.8) {
			Layer bm = layer(9, wuv, k);
			float ms = clamp(smoothstep(0.07, 0.16, slope) + step(wpos.y, -4.8) * 0.7, 0.0, 1.0);
			base.a = mix(base.a, bm.a, ms);
			base.n = mix(base.n, bm.n, ms);
			base.r = mix(base.r, bm.r, ms);
		}
		if (slope > 0.2) {
			// steile Wände (Terrassenmauern, Uferbefestigung): Sandsteinquader, senkrecht projiziert
			float ss = smoothstep(0.2, 0.32, slope);
			vec2 suv = vec2(wpos.x + wpos.z, wpos.y * 1.0);
			Layer bs = layer(11, suv, 0.0);
			base.a = mix(base.a, bs.a, ss);
			base.n = mix(base.n, bs.n, ss);
			base.r = mix(base.r, bs.r, ss);
		}
	}
	// Luftbild liefert nur großräumige Helligkeitsvariation (keine Farbe, keine Schatten)
	vec3 oc_blur = textureLod(ortho, huv, 3.0).rgb;
	vec3 oc_avg = textureLod(ortho, huv, 7.0).rgb;
	float l1 = dot(oc_blur, vec3(0.3, 0.59, 0.11));
	float l2 = dot(oc_avg, vec3(0.3, 0.59, 0.11)) + 0.001;
	float macro = clamp(l1 / l2, 0.88, 1.18);
	vec3 oc_tint = oc_blur / max(l1, 0.02);
	base.a *= mix(1.0, macro, 0.7 * (1.0 - veg));

	vec3 alb = base.a;
	vec3 nrm = base.n;
	float rgh = base.r;
	float road_mask = 0.0;

	// Schichten übereinander: Wiese -> Wald -> Parkplatz -> Platz -> Gehweg -> Straße -> Tram
	if (e_grass > EPS) {
		float gm = smoothstep(0.35, 0.65, nlow) * 0.65;
		vec3 la = mix(L6.a, L7.a, gm);
		// Grasfarbe leicht vom Luftbild (Bäume/Rasen)
		la = mix(la, la * (oc_tint * 0.55 + 0.45), 0.5);
		alb = mix(alb, la, m1.r); nrm = mix(nrm, mix(L6.n, L7.n, gm), m1.r); rgh = mix(rgh, mix(L6.r, L7.r, gm), m1.r);
	}
	if (e_forest > EPS) {
		Layer L = layer(8, wuv, k);
		// Waldboden: dunkler Nadel-/Laubboden mit Moosflecken (Textur allein ist helles Herbstlaub)
		float moss = smoothstep(0.42, 0.78, texture(noise_tex, wuv * 0.035 + 0.7).r) * smoothstep(0.3, 0.7, texture(noise_tex, wuv * 0.21).r);
		vec3 fa = L.a * vec3(0.52, 0.47, 0.42);
		fa = mix(fa, vec3(0.16, 0.2, 0.08), moss * 0.55);
		L.a = fa;
		alb = mix(alb, L.a, m1.g); nrm = mix(nrm, L.n, m1.g); rgh = mix(rgh, L.r, m1.g);
	}
	if (e_park > EPS) {
		Layer L = layer(1, wuv, k);
		alb = mix(alb, L.a, m1.b); nrm = mix(nrm, L.n, m1.b); rgh = mix(rgh, L.r, m1.b);
	}
	if (e_cob > EPS) {
		// Platzbelag (Großpflaster oder Sandsteinplatten) großräumig wählen (~400 m), damit ein Platz einen
		// durchgehenden Belag hat; vorher wechselte er im 90-m-Rauschen hart = Tarnflecken
		float psel = smoothstep(0.44, 0.56, texture(noise_tex, wuv * 0.0025 + vec2(0.31, 0.17)).r);
		Layer L = layer(psel > 0.5 ? 3 : 4, wuv, k);
		if (psel > 0.02 && psel < 0.98) {
			Layer Lb = layer(psel > 0.5 ? 4 : 3, wuv, k);
			float f = psel > 0.5 ? 1.0 - psel : psel;
			L.a = mix(L.a, Lb.a, f); L.n = mix(L.n, Lb.n, f); L.r = mix(L.r, Lb.r, f);
		}
		alb = mix(alb, L.a, m0.b); nrm = mix(nrm, L.n, m0.b); rgh = mix(rgh, L.r, m0.b);
	}
	if (e_walk > EPS) {
		// Gehwegbelag je Viertel (splat2.b, Pipeline sidewalk_style_img): Granitplatten (Gründerzeit/Altstadt),
		// Betonplatten 40×40 (DDR-Wohngebiete), Beton-Verbundpflaster (Nachwende/Einfamilienhaus/Gewerbe)
		Layer W = L2;
		float wsty = s2.b;
		if (wsty > 0.3 && wsty < 0.7) {
			W = layer(10, wuv, 0.0);
			float gw = dot(W.a, vec3(0.3, 0.59, 0.11));
			vec2 fq = fract(wuv / 0.4);
			vec2 dq = min(fq, 1.0 - fq) * 0.4;
			float jl = 1.0 - smoothstep(0.004, 0.012 + fwidth(wuv.x) * 0.7, min(dq.x, dq.y));
			vec2 cell = floor(wuv / 0.4);
			float tint = fract(sin(dot(cell, vec2(12.9898, 78.233))) * 43758.5453);
			W.a = vec3(gw) * vec3(1.02, 1.01, 0.98) * 1.25 * mix(0.9, 1.06, tint) * (1.0 - 0.45 * jl);
			W.r = mix(W.r, 0.95, jl);
		} else if (wsty >= 0.7) {
			W = layer(4, wuv * 1.25, 0.0);
			float gp = dot(W.a, vec3(0.3, 0.59, 0.11));
			W.a = mix(vec3(gp), W.a, 0.22) * vec3(0.95, 0.96, 0.98);
		}
		alb = mix(alb, W.a, m0.g); nrm = mix(nrm, W.n, m0.g); rgh = mix(rgh, W.r, m0.g);
	}
	if (e_road > EPS) {
		// neuer/abgefahrener Belag weich überblendet (nur im Übergangsband doppelt gelesen)
		float wsel = smoothstep(0.52, 0.78, nlow);
		Layer L = layer(wsel > 0.5 ? 1 : 0, wuv, k);
		if (wsel > 0.02 && wsel < 0.98) {
			Layer L2b = layer(wsel > 0.5 ? 0 : 1, wuv, k);
			float f = wsel > 0.5 ? 1.0 - wsel : wsel;
			L.a = mix(L.a, L2b.a, f); L.n = mix(L.n, L2b.n, f); L.r = mix(L.r, L2b.r, f);
		}
		float wear = clamp(nlow * 1.2, 0.0, 1.0);
		L.a *= mix(0.96, 1.04, wear);
		alb = mix(alb, L.a, m0.r); nrm = mix(nrm, L.n, m0.r); rgh = mix(rgh, L.r, m0.r);
		// Flicken (ausgebesserter Asphalt) und Randverschmutzung
		float patch_m = smoothstep(0.4, 0.6, s2.r);
		if (patch_m > 0.003) {
			Layer P = layer(0, wuv * 1.3 + vec2(7.0, 3.0), 0.0);
			alb = mix(alb, P.a * 0.62, patch_m * m0.r);
			rgh = mix(rgh, 0.55, patch_m * m0.r);
		}
		road_mask = m0.r;
	}
	{
		float edge = s2.g;
		float on_hard = clamp(m0.r + m0.g + m0.b, 0.0, 1.0);
		alb *= 1.0 - 0.34 * edge * on_hard;
	}
	if (m0.a > 0.003) {
		// Gleisbett: in der Fahrbahn bündig mit Granit-Kleinpflaster (Dresdner Straßenbahn-Achsen), abseits Schotter
		bool street_track = m0.r > 0.5;
		Layer L = layer(street_track ? 3 : 5, street_track ? wuv * 1.6 : wuv, k);
		vec3 la = street_track ? mix(vec3(dot(L.a, vec3(0.3, 0.59, 0.11))), L.a, 0.4) * vec3(0.74, 0.74, 0.77) : L.a * 0.8;
		alb = mix(alb, la, m0.a * 0.75); nrm = mix(nrm, L.n, m0.a * 0.75); rgh = mix(rgh, L.r, m0.a * 0.75);
	}

	// Nässe: befestigte Flächen dunkler und glänzend, Pfützen in Senken der Rauschkarte als Spiegel
	float hard = clamp(road_mask + m0.g + m0.b, 0.0, 1.0);
	float wet = wetness * (0.5 + 0.5 * hard);
	alb *= 1.0 - 0.38 * wet;
	rgh = mix(rgh, 0.1, wet * 0.8);
	float pud = smoothstep(0.6, 0.66, texture(noise_tex, wuv * 0.045 + 0.13).r) * smoothstep(0.35, 0.8, wetness) * hard;
	alb = mix(alb, alb * 0.45, pud);
	rgh = mix(rgh, 0.015, pud);
	nrm = mix(nrm, vec3(0.0, 0.0, 1.0), pud);

	ALBEDO = alb;
	float road_like = max(road_mask, wetness);
	ROUGHNESS = clamp(mix(max(rgh, 0.72), rgh, road_like), 0.04, 1.0);
	SPECULAR = 0.4;
	NORMAL_MAP = normalize(nrm) * 0.5 + 0.5;
	NORMAL_MAP_DEPTH = 1.0;
}
