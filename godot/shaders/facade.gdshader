shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

// Prozedurale Fassaden in 7 Architekturstilen.
// Vertexdaten: UV = (Meter entlang der Wand, Meter über Erdgeschoss), UV2 = (Geschosse, Traufhöhe),
//              COLOR.rgb = Grundfarbe; CUSTOM0.x = Ladenkategorie, CUSTOM0.y = Stil, CUSTOM0.z = Zufallswert 0..1.
// Stile: 0 Gründerzeit, 1 Barock/Sandstein, 2 DDR-Platte, 3 Nachkriegs-Zeilenbau, 4 Glas/Büro,
//        5 Industrie, 6 Klinker, 7 Gaube.

global uniform float night;
global uniform float wetness;

uniform sampler2D plaster_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D plaster_normal : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D plaster_rough : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D brick_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D brick_normal : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D concrete_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D concrete_normal : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
uniform float plaster_tile = 2.0;
uniform float brick_tile = 2.0;
uniform float concrete_tile = 2.0;
uniform sampler2D graffiti_atlas : source_color, filter_linear_mipmap, repeat_disable;
uniform bool has_graffiti = false;
uniform float graffiti_density = 1.0;

// BC5-Normalen (TexLib) speichern nur XY -> Z rekonstruieren
vec3 unpack_nrm(vec4 t) {
	vec2 xy = t.xy * 2.0 - 1.0;
	return vec3(xy, sqrt(max(0.0, 1.0 - dot(xy, xy))));
}

float hash11(float p) {
	p = fract(p * 0.1031);
	p *= p + 33.33;
	p *= p + p;
	return fract(p);
}

float hash21(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

// Vorzeichenbehafteter Abstand zu einem Rechteck (negativ innen)
float sdbox(vec2 p, vec2 c, vec2 hs) {
	vec2 d = abs(p - c) - hs;
	return max(d.x, d.y);
}

// Rechteck mit halbkreisförmigem Abschluss oben
float sdarch(vec2 p, vec2 c, vec2 hs) {
	float r = hs.x;
	float rect = sdbox(p, vec2(c.x, c.y - r * 0.5), vec2(hs.x, hs.y - r * 0.5));
	float circ = length(p - vec2(c.x, c.y + hs.y - r)) - r;
	return min(rect, circ);
}

// Flach gewölbter Segmentbogen
float sdseg(vec2 p, vec2 c, vec2 hs) {
	float rise = hs.x * 0.35;
	float rect = sdbox(p, vec2(c.x, c.y - rise * 0.5), vec2(hs.x, hs.y - rise * 0.5));
	float R = (hs.x * hs.x + rise * rise) / (2.0 * rise);
	float circ = max(length(p - vec2(c.x, c.y + hs.y - rise - R + rise)) - R, sdbox(p, vec2(c.x, c.y + hs.y - rise * 0.5), vec2(hs.x, rise * 0.5)));
	return min(rect, circ);
}

const float GSZ[8] = float[8](1.2, 1.1, 1.0, 1.8, 1.7, 0.6, 0.8, 1.6);

// CUSTOM0.x = Ladenkategorie aus OSM (0 = kein Laden, 12 = leerstehend), gesetzt von buildings.gd
varying vec4 shopinfo;

void vertex() {
	shopinfo = CUSTOM0;
}

void fragment() {
	// Stil/Zufallswert aus CUSTOM0.y/.z (Float); COLOR.a ist nur 8 Bit und wurde bei Werten > 1 abgeschnitten
	float st = floor(shopinfo.y + 0.5);
	float seed = clamp(shopinfo.z, 0.0, 1.0);
	float levels = max(UV2.x, 1.0);
	float height = max(UV2.y, 3.0);
	float fh = clamp(height / levels, 2.7, 4.6);
	vec2 p = UV;
	float row = floor(p.y / fh);
	float vy = p.y - row * fh;
	float h1 = hash11(seed * 91.7);
	float h2 = hash11(seed * 13.1);
	float h3 = hash11(seed * 7.7);

	// ---- Stilparameter -------------------------------------------------
	float pitch = 2.6;
	float ww = 1.2;
	float wh = 1.7;
	float wy = 0.7;
	int shape = 0;           // 0 Rechteck, 1 Segmentbogen, 2 Rundbogen
	if (st < 0.5) {          // Gründerzeit
		pitch = mix(2.3, 3.1, h1);
		ww = pitch * mix(0.40, 0.46, h2);
		wh = fh * 0.66;
		wy = fh * 0.19;
		shape = 1;
	} else if (st < 1.5) {   // Barock
		pitch = mix(3.0, 4.2, h1);
		ww = pitch * 0.44;
		wh = fh * 0.72;
		wy = fh * 0.17;
		shape = (row < 0.5 || row > levels - 1.5) ? 2 : 0;
	} else if (st < 2.5) {   // DDR-Platte (WBS 70 Dresden: Plattenraster 6,0 m, zwei Fensterachsen je Platte)
		pitch = 3.0;
		ww = mix(1.25, 1.6, step(0.5, h1));
		wh = 1.4;
		wy = 0.85;
	} else if (st < 3.5) {   // Zeilenbau
		pitch = mix(2.2, 2.8, h1);
		ww = pitch * 0.40;
		wh = fh * 0.52;
		wy = fh * 0.27;
	} else if (st < 4.5) {   // Glas
		pitch = 1.5;
		ww = pitch - 0.07;
		wh = fh - 0.9;
		wy = 0.35;
	} else if (st < 5.5) {   // Industrie
		pitch = mix(5.0, 8.0, h1);
		ww = 1.7;
		wh = 1.0;
		wy = fh * 0.55;
		if (height < 3.4) {  // DDR-Garagenreihe: Tor an Tor
			pitch = 2.7;
			ww = 2.35;
			wh = min(2.05, height - 0.35);
			wy = 0.06;
		}
	} else if (st < 6.5) {   // Klinker
		pitch = mix(2.4, 3.0, h1);
		ww = pitch * 0.40;
		wh = fh * 0.62;
		wy = fh * 0.22;
		shape = 1;
	} else {                 // Gaube
		pitch = 100.0;
		ww = 0.55;
		wh = 0.95;
		wy = 0.25;
	}
	float col = floor(p.x / pitch);
	float ux = p.x - col * pitch;
	vec2 q = vec2(ux, vy);
	vec2 wc = vec2(pitch * 0.5, wy + wh * 0.5);
	vec2 whs = vec2(ww * 0.5, wh * 0.5);

	bool ground = row < 0.5 && p.y > -0.2;
	bool data_shop = shopinfo.x > 0.5;
	bool vacant = abs(shopinfo.x - 12.0) < 0.5;
	// echte Läden aus OSM; ohne Daten nur noch selten zufällig (Geschäftsstraßen-Stile)
	bool shop = ground && (data_shop || ((st < 0.5 || (st > 2.5 && st < 4.5) || st > 5.5 && st < 6.5) && hash11(seed * 3.3) > 0.88 && height > 6.0));
	bool door_col = ground && hash21(vec2(col, floor(seed * 50.0))) > 0.93 && st < 4.5 && st != 2.0;
	if (shop) {
		wy = 0.35;
		wh = min(2.7, fh - 0.75);
		ww = pitch * 0.84;
		wc = vec2(pitch * 0.5, wy + wh * 0.5);
		whs = vec2(ww * 0.5, wh * 0.5);
		shape = 0;
	}
	if (door_col) {
		wy = 0.05;
		wh = 2.25;
		ww = 1.15;
		wc = vec2(pitch * 0.5, wy + wh * 0.5);
		whs = vec2(ww * 0.5, wh * 0.5);
		shape = (st == 1.0 || st == 0.0) ? 2 : 0;
	}
	if (st > 1.5 && st < 2.5) {
		// Platte: zwei Fenster je Plattenbreite, jede zweite Platte Loggia
		wc.x = pitch * 0.5;
	}

	// Fenster vorhanden?
	float wid = hash21(vec2(col, row) + seed * 17.0);
	bool has_win = wid > 0.03 && p.y > 0.0 && p.y < height - 0.7;
	bool garage = st > 4.5 && st < 5.5 && height < 3.4;
	if (st > 4.5 && st < 5.5 && row < 0.5 && !garage) {
		has_win = false;     // Industrie: Tore im Erdgeschoss
	}
	if (p.y < 0.0) {
		has_win = false;
	}

	float d;
	if (shape == 2) {
		d = sdarch(q, wc, whs);
	} else if (shape == 1) {
		d = sdseg(q, wc, whs);
	} else {
		d = sdbox(q, wc, whs);
	}
	float aa = fwidth(d) * 1.2 + 0.0004;
	float glass_m = has_win ? 1.0 - smoothstep(-aa, aa, d) : 0.0;
	float frame_w = (st > 3.5 && st < 4.5) ? 0.03 : 0.085;
	float frame_m = has_win ? clamp((1.0 - smoothstep(-aa, aa, d - frame_w)) - glass_m, 0.0, 1.0) : 0.0;

	// ---- Laibung und Innenraum (Parallaxe, "Interior Mapping") ------------
	// Blickstrahl im Wandsystem: x entlang der Wand (UV.x), y nach oben, z aus der Wand heraus.
	vec3 up_v = (VIEW_MATRIX * vec4(0.0, 1.0, 0.0, 0.0)).xyz;
	vec3 tv = normalize(TANGENT);
	vec3 vt = vec3(dot(VIEW, tv), dot(VIEW, up_v), dot(VIEW, NORMAL));
	vec3 rd = -vt;                                  // in die Wand hinein (rd.z < 0)
	float recess = (st > 3.5 && st < 4.5) ? 0.03 : ((st > 1.5 && st < 2.5) ? 0.10 : 0.17);
	vec2 gq = q;                                    // Treffpunkt auf der zurückgesetzten Glasebene
	float reveal_m = 0.0;
	float d2 = d;
	if (glass_m > 0.0 && rd.z < -0.02) {
		gq = q + rd.xy * (recess / -rd.z);
		if (shape == 2) {
			d2 = sdarch(gq, wc, whs);
		} else if (shape == 1) {
			d2 = sdseg(gq, wc, whs);
		} else {
			d2 = sdbox(gq, wc, whs);
		}
		reveal_m = glass_m * smoothstep(-aa, aa, d2);
	}
	float pane_m = clamp(glass_m - reveal_m, 0.0, 1.0);
	// Fensterrahmen innen an der Glasebene
	float sash_w = (st > 3.5 && st < 4.5) ? 0.025 : 0.06;
	float sash_m = pane_m * smoothstep(-sash_w - aa, -sash_w + aa, d2);
	// Innenraum: Kasten so breit wie die Achse, so hoch wie das Geschoss
	vec3 room_col = vec3(0.0);
	float room_lit = 0.0;
	float room_id = hash21(vec2(col * 3.1 + 5.0, row * 1.7) + seed * 23.0);
	if (pane_m > 0.0 && rd.z < -0.02) {
		float depth = mix(3.0, 5.5, room_id);
		vec3 ro = vec3(gq.x, gq.y, -recess);
		vec3 rinv = 1.0 / rd;
		float tx = rd.x > 0.0 ? (pitch - ro.x) * rinv.x : (0.0 - ro.x) * rinv.x;
		float ty = rd.y > 0.0 ? (fh - 0.05 - ro.y) * rinv.y : (0.05 - ro.y) * rinv.y;
		float tz = (-recess - depth - ro.z) * rinv.z;
		float tt = min(min(tx, ty), tz);
		vec3 hp = ro + rd * tt;
		float dz = clamp((-hp.z - recess) / depth, 0.0, 1.0);    // 0 = Fenster, 1 = Rückwand
		vec3 wall_c = mix(vec3(0.78, 0.74, 0.66), vec3(0.62, 0.68, 0.70), step(0.5, hash11(room_id * 7.3)));
		wall_c = mix(wall_c, vec3(0.72, 0.58, 0.45), step(0.82, hash11(room_id * 3.9)));
		if (tt == tz) {
			room_col = wall_c * 0.85;
			if (shop) {
				// Ladenregale an der Rückwand: Fachböden alle ~45 cm, Ware in Farben passend zur Ladenart
				float lvl = fract(hp.y / 0.45);
				float goods = step(0.12, lvl) * step(lvl, 0.8) * step(0.25, hp.y) * step(hp.y, 2.3);
				float cat = shopinfo.x;
				float hx = hash11(room_id * 3.0 + floor(hp.x * 4.0) + floor(hp.y / 0.45) * 7.0);
				float hy = hash11(floor(hp.x * 4.0) * 1.3 + room_id + floor(hp.y / 0.45));
				// Grundpaletten: bunte Verpackungen (Lebensmittel/Supermarkt), Stoffe (Mode), Holz/Waren (Wohnen),
				// warme Töne (Gastro/Bäckerei), helle Flächen (Dienstleistung/Bank/Gesundheit)
				vec3 pa = vec3(0.85, 0.25, 0.18);
				vec3 pb = vec3(0.95, 0.78, 0.22);
				vec3 pc = vec3(0.2, 0.55, 0.3);
				if (abs(cat - 3.0) < 0.5) {            // Mode
					pa = vec3(0.12, 0.13, 0.18); pb = vec3(0.75, 0.68, 0.6); pc = vec3(0.55, 0.15, 0.25);
				} else if (abs(cat - 5.0) < 0.5) {     // Wohnen
					pa = vec3(0.55, 0.38, 0.22); pb = vec3(0.85, 0.82, 0.76); pc = vec3(0.3, 0.42, 0.5);
				} else if (abs(cat - 6.0) < 0.5) {     // Gastro
					pa = vec3(0.6, 0.35, 0.2); pb = vec3(0.92, 0.75, 0.5); pc = vec3(0.35, 0.22, 0.15);
				} else if (cat > 3.5 && cat < 4.5 || cat > 6.5 && cat < 8.5) {   // Dienstleistung, Bank, Gesundheit
					pa = vec3(0.85, 0.86, 0.88); pb = vec3(0.35, 0.5, 0.65); pc = vec3(0.7, 0.72, 0.7);
					goods *= 0.5;
				}
				vec3 gcol = hx < 0.33 ? pa : (hx < 0.66 ? pb : pc);
				gcol *= mix(0.7, 1.15, hy);
				room_col = mix(vec3(0.84, 0.82, 0.78), gcol, goods * 0.92);
			}
			// Möbel-/Regalsilhouette an der Rückwand (Wohnungen)
			float fx = hp.x / pitch;
			float home = shop ? 0.0 : 1.0;
			float furn = step(hp.y, mix(0.7, 1.9, hash11(room_id * 11.0))) * step(abs(fx - mix(0.3, 0.7, hash11(room_id * 5.0))), mix(0.15, 0.35, hash11(room_id * 2.0)));
			room_col = mix(room_col, vec3(0.16, 0.12, 0.09), furn * 0.85 * home);
			// Bild an der Wand
			float pic = step(abs(hp.y - fh * 0.62), 0.28) * step(abs(fx - 0.5 + (hash11(room_id) - 0.5) * 0.4), 0.12) * step(0.4, hash11(room_id * 9.1));
			room_col = mix(room_col, vec3(0.35, 0.3, 0.42), pic * 0.8 * home);
		} else if (tt == ty) {
			room_col = rd.y > 0.0 ? vec3(0.82, 0.81, 0.78) * 0.75 : mix(vec3(0.30, 0.20, 0.12), vec3(0.42, 0.40, 0.38), step(0.6, hash11(room_id * 4.4)));
		} else {
			room_col = wall_c * 0.7;
			if (shop) {
				// Seitenregale: gleiche Warenfarben wie an der Rückwand, Wechsel entlang der Raumtiefe
				float lvl2 = fract(hp.y / 0.45);
				float goods2 = step(0.12, lvl2) * step(lvl2, 0.8) * step(0.25, hp.y) * step(hp.y, 2.3);
				float h2 = hash11(room_id * 5.0 + floor(-hp.z * 3.0) + floor(hp.y / 0.45) * 3.0);
				vec3 g2 = h2 < 0.33 ? vec3(0.8, 0.3, 0.2) : (h2 < 0.66 ? vec3(0.9, 0.75, 0.3) : vec3(0.25, 0.5, 0.35));
				if (abs(shopinfo.x - 3.0) < 0.5) { g2 = h2 < 0.5 ? vec3(0.15, 0.15, 0.2) : vec3(0.7, 0.62, 0.55); }
				if (abs(shopinfo.x - 6.0) < 0.5) { g2 = h2 < 0.5 ? vec3(0.6, 0.38, 0.22) : vec3(0.9, 0.78, 0.55); }
				room_col = mix(vec3(0.8, 0.78, 0.74), g2 * mix(0.75, 1.1, hash11(h2 * 13.0)), goods2 * 0.88);
			}
		}
		// Tageslicht fällt durchs Fenster: vorn hell, hinten dunkel
		room_col *= mix(1.35, 0.22, sqrt(dz));
		room_lit = step(0.64, hash21(vec2(col * 0.37 + 11.0, row * 0.73) + seed * 53.0));
	}

	// ---- Grundmaterial --------------------------------------------------
	vec3 tint = COLOR.rgb;
	vec2 wuv = p;
	vec3 base;
	vec3 nmap;
	float rough_base = 0.88;
	if (st > 0.5 && st < 1.5) {
		// Dresdner Barock: Elbsandstein-Quader (regelmäßig, feine Fugen) mit dunkler Patina –
		// kein Bruchsteinmauerwerk. Feinstruktur aus der Putztextur, Quader prozedural.
		vec2 puv = wuv / plaster_tile;
		vec3 pa = texture(plaster_albedo, puv).rgb;
		float qh = 0.46;
		float qw = 1.15;
		float qr = floor(wuv.y / qh);
		float qxs = wuv.x / qw + mod(qr, 2.0) * 0.5;
		float qi = floor(qxs);
		vec2 qf = vec2(fract(qxs) * qw, fract(wuv.y / qh) * qh);
		float qj = min(min(qf.x, qw - qf.x), min(qf.y, qh - qf.y));
		float joint = 1.0 - smoothstep(0.008, 0.02 + aa * 2.0, qj);
		float qv = hash21(vec2(qi, qr) + seed * 7.0);
		vec3 sand = tint * 1.12 * mix(0.9, 1.08, qv) * mix(0.88, 1.08, dot(pa, vec3(0.333)));
		// Patina: großflächig dunkle Verwitterung mit senkrechten Schlieren (typisch Elbsandstein)
		float pat = texture(noise_tex, vec2(wuv.x * 0.16, wuv.y * 0.03)).r;
		float pat2 = texture(noise_tex, wuv * 0.05 + 0.37).r;
		float dark = smoothstep(0.5, 0.85, pat * 0.55 + pat2 * 0.6) * 0.75;
		sand = mix(sand, sand * vec3(0.34, 0.32, 0.30), dark);
		base = mix(sand, sand * 0.68, joint * 0.85);
		nmap = unpack_nrm(texture(plaster_normal, puv));
		nmap.xy *= 0.6;
		rough_base = 0.86;
	} else if (st > 5.5 && st < 6.5) {
		vec2 uv = wuv / brick_tile;
		base = texture(brick_albedo, uv).rgb * mix(vec3(1.0), tint / vec3(0.6), 0.25);
		nmap = unpack_nrm(texture(brick_normal, uv));
	} else if ((st > 1.5 && st < 2.5) || (st > 4.5 && st < 5.5)) {
		vec2 uv = wuv / concrete_tile;
		vec3 ct = texture(concrete_albedo, uv).rgb;
		base = ct * tint * 1.9;
		nmap = unpack_nrm(texture(concrete_normal, uv));
		if (st > 1.5 && st < 2.5 && h3 >= 0.22) {
			// sanierte Platte: gestrichene Oberfläche – Betonstruktur nur noch schwach; nach 1990 oft pastellfarben
			// (Recherche Prohlis/Reick/Gorbitz: creme, gelb, mint, rosa) statt weiß
			float cl = dot(ct, vec3(0.333));
			float pk = hash11(seed * 4.9);
			vec3 pastel = pk < 0.2 ? vec3(0.95, 0.9, 0.76) : (pk < 0.38 ? vec3(0.96, 0.88, 0.62) :
				(pk < 0.52 ? vec3(0.78, 0.9, 0.8) : (pk < 0.64 ? vec3(0.95, 0.82, 0.8) : tint)));
			base = pastel * mix(0.93, 1.05, clamp(cl * 1.6, 0.0, 1.0));
			nmap = mix(vec3(0.0, 0.0, 1.0), nmap, 0.35);
		}
	} else if (st > 3.5 && st < 4.5) {
		base = tint * 0.55;
		nmap = vec3(0.0, 0.0, 1.0);
		rough_base = 0.35;
	} else {
		vec2 uv = wuv / plaster_tile;
		vec3 pa = texture(plaster_albedo, uv).rgb;
		float pl = dot(pa, vec3(0.3, 0.59, 0.11));
		base = tint * mix(0.82, 1.12, pl);
		nmap = unpack_nrm(texture(plaster_normal, uv));
		rough_base = mix(0.9, texture(plaster_rough, uv).r, 0.6);
	}

	// ---- Sockel, Bänder, Gesimse ----------------------------------------
	float plinth = 0.0;
	if (st < 0.5 || (st > 2.5 && st < 3.5) || (st > 5.5 && st < 6.5)) {
		plinth = 1.0 - smoothstep(0.85, 1.0, p.y);         // Sockel bis 1 m
		vec2 cuv = wuv / concrete_tile;
		vec3 pc = texture(concrete_albedo, cuv).rgb * 1.8;
		base = mix(base, pc * vec3(0.9, 0.88, 0.84), plinth * 0.95);
	}
	float cornice = smoothstep(height - 0.95, height - 0.7, p.y);
	vec3 stone_tone = clamp(base * 1.1 + 0.05, 0.0, 1.0);
	float band = 0.0;
	if (st < 0.5 || st > 5.5 && st < 6.5) {
		// Gründerzeit: Geschossbänder
		band = (1.0 - smoothstep(0.0, 0.05 + aa, abs(vy - 0.04) - 0.09)) * step(0.5, row);
	} else if (st > 0.5 && st < 1.5) {
		band = (1.0 - smoothstep(0.0, 0.05 + aa, abs(vy - 0.04) - 0.13)) * step(0.5, row);
	}
	base = mix(base, stone_tone, max(band * 0.7, cornice * 0.55));

	// Barock: Pilaster zwischen den Achsen, Rustika im Erdgeschoss
	if (st > 0.5 && st < 1.5) {
		float pil = (1.0 - smoothstep(0.0, 0.04, ux - 0.26)) + smoothstep(pitch - 0.30, pitch - 0.26, ux);
		pil = clamp(pil, 0.0, 1.0);
		base = mix(base, base * 1.18, pil * 0.8);
		if (row < 0.5 && p.y > 0.0) {
			float rust = smoothstep(0.015, 0.0, abs(fract(p.y / 0.65) - 0.5) - 0.485);
			base *= mix(1.0, 0.82, rust);
		}
	}

	// DDR-Platte (WBS 70, Recherche Gorbitz/Prohlis): Fugenraster 6,0 m × Geschoss; saniert weiß/hell mit
	// Farbakzenten (Orange, Grün, Gelb) an Treppenhausachsen, unsaniert Waschbeton #9A968C mit Körnung
	bool unsan = h3 < 0.22;
	vec3 wbeton = vec3(0.60, 0.585, 0.55);
	vec3 p_acc = h2 < 0.33 ? vec3(0.88, 0.52, 0.22) : (h2 < 0.66 ? vec3(0.48, 0.63, 0.33) : vec3(0.90, 0.75, 0.27));
	if (st > 1.5 && st < 2.5) {
		float jx = 1.0 - smoothstep(0.0, 0.03 + aa, abs(fract(p.x / 6.0 + 0.5) - 0.5) * 6.0);
		float jy = 1.0 - smoothstep(0.0, 0.03 + aa, abs(fract(p.y / fh + 0.5) - 0.5) * fh);
		if (unsan) {
			float agg = texture(noise_tex, p * 3.7).r * 0.6 + texture(noise_tex, p * 13.0).r * 0.4;
			base = wbeton * mix(0.84, 1.12, agg);
		}
		base *= 1.0 - (unsan ? 0.36 : 0.2) * max(jx, jy);
		if (!unsan) {
			float panel = floor(p.x / 6.0);
			float stair = step(0.72, hash21(vec2(panel, floor(seed * 33.0))));
			base = mix(base, p_acc, stair * 0.8);
		}
	}

	// Glasfassade: Brüstungsfelder
	if (st > 3.5 && st < 4.5) {
		float spandrel = 1.0 - step(0.35, vy) * (1.0 - step(fh - 0.55, vy));
		base = mix(base, base * 0.7, spandrel);
	}

	// Industrie: Wellblech-Rillen
	if (st > 4.5 && st < 5.5) {
		float r = 0.5 + 0.5 * sin(p.x * 18.0);
		base *= mix(0.85, 1.08, r);
		nmap.x += (r - 0.5) * 0.5;
	}

	// ---- Fenstergestaltung ----------------------------------------------
	vec3 frame_col = (st > 3.5 && st < 4.5) ? vec3(0.1, 0.11, 0.12) : mix(vec3(0.86, 0.85, 0.8), vec3(0.3, 0.22, 0.16), step(0.84, hash11(seed * 5.5 + floor(p.y / fh))));
	if (st > 1.5 && st < 2.5) {
		frame_col = h3 >= 0.22 ? vec3(0.9, 0.9, 0.88) : vec3(0.62, 0.6, 0.56);   // Kunststofffenster weiß / alt grau
	}
	if (st < 0.5) {
		// Gründerzeit (Recherche): meist weiße Rahmen, je Haus auch dunkelgrün oder rotbraun
		float fc = hash11(seed * 8.3);
		frame_col = fc < 0.68 ? vec3(0.86, 0.85, 0.8) : (fc < 0.84 ? vec3(0.12, 0.22, 0.16) : vec3(0.36, 0.17, 0.12));
	}
	if (st > 4.5 && st < 5.5) {
		frame_col = vec3(0.35, 0.37, 0.38);
	}
	vec3 stone_deco = clamp(base * 1.18 + 0.03, 0.0, 1.0);
	// Sturz/Verdachung über dem Fenster (Gründerzeit, Barock, Klinker)
	float lintel = 0.0;
	if ((st < 1.5 || (st > 5.5 && st < 6.5)) && has_win && !shop) {
		float ly = wy + wh + 0.02;
		float dl = sdbox(q, vec2(pitch * 0.5, ly + 0.17), vec2(ww * 0.5 + 0.14, 0.15));
		lintel = 1.0 - smoothstep(-aa, aa, dl);
		// Dreiecksgiebel auf dem Piano nobile
		if (st < 0.5 && row > 0.5 && row < 1.5) {
			float tri = (ly + 0.32 + (ww * 0.5 + 0.1 - abs(q.x - pitch * 0.5)) * 0.45) - q.y;
			float in_tri = step(0.0, tri) * step(q.y, ly + 0.32 + (ww * 0.5 + 0.1) * 0.45) * step(ly + 0.28, q.y) * step(abs(q.x - pitch * 0.5), ww * 0.5 + 0.1);
			lintel = max(lintel, in_tri);
		}
	}
	// Fensterbank
	float sill = 0.0;
	if (has_win && !shop && !door_col) {
		float dy = q.y - (wy - 0.07);
		float dx = abs(q.x - pitch * 0.5) - (ww * 0.5 + 0.1);
		sill = (1.0 - smoothstep(0.0, 0.04 + aa, abs(dy) - 0.04)) * (1.0 - smoothstep(0.0, aa, dx));
	}
	base = mix(base, stone_deco, max(lintel, sill));
	base = mix(base, frame_col, frame_m);

	// Sprossen
	float mull = 0.0;
	if (has_win && !shop && st < 4.5 && st != 2.0) {
		float cx = abs(gq.x - wc.x);
		float cy = abs(gq.y - (wc.y + wh * 0.12));
		mull = (1.0 - smoothstep(0.022, 0.022 + aa, cx)) + (1.0 - smoothstep(0.022, 0.022 + aa, cy));
		mull = clamp(mull, 0.0, 1.0) * pane_m;
	}
	if (st > 3.5 && st < 4.5) {
		float cx = abs(fract((gq.x + p.x - q.x) / pitch + 0.5) - 0.5) * pitch;
		mull = (1.0 - smoothstep(0.015, 0.015 + aa, cx)) * pane_m;
	}
	mull = max(mull, sash_m);
	base = mix(base, frame_col, mull * 0.9);

	// Glas
	float curt = step(0.72, hash21(vec2(col * 1.7, row * 2.3) + seed * 31.0));
	vec3 glass_col = mix(vec3(0.016, 0.024, 0.032), vec3(0.34, 0.31, 0.26), curt * (shop ? 0.0 : 0.55));
	if (door_col) {
		glass_col = mix(vec3(0.07, 0.045, 0.03), vec3(0.02, 0.03, 0.04), step(0.5, h3));
	}
	// Glas selbst ist dunkel (Innenraum kommt als Emission, Spiegelung aus der Beleuchtung)
	vec3 glass_alb = mix(vec3(0.02, 0.025, 0.03), vec3(0.34, 0.31, 0.26), curt * (shop ? 0.0 : 0.55));
	if (door_col) {
		glass_alb = glass_col;
	}
	// Gardinen/Vorhänge: seitliche Stoffbahnen an der Glasebene (nicht bei Läden/Glasbauten)
	float drape = 0.0;
	if (!shop && st < 3.5 && hash11(room_id * 17.0) > 0.35) {
		float rx = (gq.x - (wc.x - whs.x)) / max(2.0 * whs.x, 0.01);
		float wdt = mix(0.12, 0.3, hash11(room_id * 21.0));
		drape = (1.0 - smoothstep(wdt - 0.02, wdt, rx)) + smoothstep(1.0 - wdt, 1.0 - wdt + 0.02, rx);
		drape = clamp(drape, 0.0, 1.0) * (0.85 + 0.15 * sin(gq.x * 40.0));
	}
	vec3 drape_col = mix(vec3(0.82, 0.78, 0.68), vec3(0.45, 0.18, 0.15), step(0.8, hash11(room_id * 13.0)));
	glass_alb = mix(glass_alb, drape_col * 0.7, clamp(drape, 0.0, 1.0));
	base = mix(base, glass_alb, pane_m * (1.0 - mull));
	if (garage && has_win) {
		// Garagentor statt Fenster: Blech mit senkrechten Sicken, jede Garage eigene Farbe (Recherche Gorbitz/Prohlis)
		float gi = hash21(vec2(col, floor(seed * 77.0)));
		vec3 gcol = gi < 0.18 ? vec3(0.22, 0.38, 0.24) : (gi < 0.34 ? vec3(0.2, 0.3, 0.5) : (gi < 0.48 ? vec3(0.55, 0.16, 0.12) :
			(gi < 0.6 ? vec3(0.42, 0.3, 0.18) : (gi < 0.72 ? vec3(0.78, 0.62, 0.2) : vec3(0.62, 0.62, 0.6)))));
		float rib = 0.85 + 0.15 * step(0.5, fract(q.x * 6.0));
		float rust = smoothstep(0.55, 0.9, texture(noise_tex, p * 0.9 + seed).r) * 0.35;
		vec3 door = mix(gcol * rib, vec3(0.35, 0.2, 0.1), rust);
		base = mix(base, door, glass_m);
		pane_m = 0.0;
		glass_m = 0.0;
	}
	// Laibung (seitliche/obere Leibungsfläche): Stein, oben dunkler (Sturz verschattet)
	vec3 reveal_col = stone_deco * mix(0.62, 0.85, step(0.0, rd.y));
	base = mix(base, reveal_col, reveal_m);

	// Schaufenster-Werbeband
	if (shop) {
		float sign_y = wy + wh + 0.05;
		float sign_m = step(sign_y, vy) * step(vy, sign_y + 0.55);
		vec3 sc = mix(vec3(0.12, 0.18, 0.32), vec3(0.45, 0.1, 0.1), step(0.33, h2));
		sc = mix(sc, vec3(0.9, 0.88, 0.8), step(0.66, h3));
		base = mix(base, sc, sign_m * 0.9 * step(0.1, abs(ux - pitch * 0.5) - 0.0) * 0.0 + sign_m * 0.9);
	}

	// Platte: Balkonbrücken (6 m, Waschbeton-Brüstung 1,0 m) auf der Balkonseite des Blocks, dahinter
	// verschattete Loggia-Nische; Brüstung verdeckt den unteren Fensterteil (Glas/Nachtlicht dort aus)
	if (st > 1.5 && st < 2.5 && row > 0.5 && p.y < height - 0.7) {
		vec3 wn = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz;
		vec2 bdir = vec2(cos(seed * 40.0), sin(seed * 40.0));
		float panel = floor(p.x / 6.0);
		bool bay = dot(wn.xz, bdir) > 0.25 && hash21(vec2(panel, floor(seed * 21.0))) > 0.3;
		if (bay) {
			float lx = fract(p.x / 6.0) * 6.0;
			float inside = step(0.18, lx) * step(lx, 5.82);
			float par = inside * step(0.06, vy) * step(vy, 1.06);
			float niche = inside * step(1.06, vy) * step(vy, fh - 0.22);
			vec3 parcol = wbeton * mix(0.82, 1.12, texture(noise_tex, p * 9.0).r);
			if (!unsan && h1 > 0.45) {
				parcol = mix(parcol, p_acc, 0.75);
			} else if (!unsan) {
				parcol = vec3(0.86, 0.85, 0.82) * mix(0.92, 1.04, texture(noise_tex, p * 5.0).r);
			}
			base = mix(base, base * 0.42, niche * 0.8 * (1.0 - pane_m));
			base = mix(base, parcol, par);
			base *= 1.0 - 0.4 * par * smoothstep(0.9, 1.06, vy);       // Schattenkante der Brüstungsoberseite
			base *= 1.0 - 0.3 * niche * smoothstep(fh - 0.6, fh - 0.22, vy); // Balkonplatte darüber
			pane_m *= 1.0 - par;
			glass_m *= 1.0 - par;
			frame_m *= 1.0 - par;
		}
	}

	// Verschmutzung, Regenstreifen
	float streak = texture(noise_tex, vec2(p.x * 0.4, p.y * 0.05)).r;
	bool clean_platte = st > 1.5 && st < 2.5 && h3 >= 0.22;     // sanierte, gestrichene Platte
	float grime = smoothstep(3.5, -0.2, p.y) * 0.22 + streak * (clean_platte ? 0.035 : 0.13);
	float under_win = has_win ? smoothstep(0.0, 1.8, 1.8 - clamp(q.y - wy, 0.0, 1.8)) * step(wy, q.y) * step(q.y, wy + wh + 0.0) * 0.0 : 0.0;
	base *= 1.0 - grime;
	base *= mix(1.0, 0.93, texture(noise_tex, p * 0.8).r);

	// ---- Graffiti (Erdgeschosszone, je 4,5-m-Abschnitt nach Baustil) ------------
	if (has_graffiti && p.y > 0.0 && p.y < 2.6) {
		float prob = 0.13;
		if (st > 4.5 && st < 5.5) { prob = 0.45; }
		else if (st > 1.5 && st < 3.5) { prob = 0.22; }
		else if ((st > 0.5 && st < 1.5) || (st > 3.5 && st < 4.5)) { prob = 0.03; }
		else if (st > 5.5 && st < 6.5) { prob = 0.25; }
		float blk = floor(p.x / 4.5);
		float hg = hash21(vec2(blk * 1.7, seed * 71.0));
		if (hg < prob * graffiti_density) {
			float gcell = floor(hash11(hg * 131.0 + blk) * 7.999);
			// empfohlene Kantenlänge je Motiv (graffiti.json): Tags ~1,1 m, Throw-ups ~1,75 m, Schablone 0,6 m ...
			float gsz = GSZ[int(gcell)] * mix(0.9, 1.15, hash11(hg * 17.0));
			float gx0 = blk * 4.5 + hash11(hg * 29.0) * (4.5 - gsz);
			float gy0 = max(mix(0.9, 1.5, hash11(hg * 41.0)) - gsz * 0.5, 0.3);
			vec2 g = vec2((p.x - gx0) / gsz, 1.0 - (p.y - gy0) / gsz);
			if (g.x > 0.0 && g.x < 1.0 && g.y > 0.0 && g.y < 1.0) {
				vec2 guv = (g + vec2(mod(gcell, 4.0), floor(gcell / 4.0))) / vec2(4.0, 2.0);
				vec4 gc = texture(graffiti_atlas, guv);
				base = mix(base, gc.rgb, gc.a * 0.92 * (1.0 - glass_m));
			}
		}
	}

	// ---- Nachtlicht -----------------------------------------------------
	float lit_p = hash21(vec2(col * 0.37 + 11.0, row * 0.73) + seed * 53.0);
	float lit = step(0.64, lit_p) * pane_m * (1.0 - mull);
	float warm = hash21(vec2(col, row) * 1.3 + seed * 7.0);
	vec3 emis = mix(vec3(1.0, 0.7, 0.38), vec3(0.85, 0.92, 1.0), step(0.78, warm)) * lit * (shop ? 1.5 : 1.0);
	if (st > 3.5 && st < 4.5) {
		emis = vec3(1.0, 0.95, 0.85) * glass_m * step(0.5, lit_p) * 0.8;
	}
	// Innenraum: tagsüber gedämpftes Tageslicht, nachts beleuchtete Räume warm; bei flachem Blick dominiert die Spiegelung
	float cos_v = clamp(abs(vt.z), 0.0, 1.0);
	float fres = 0.04 + 0.96 * pow(1.0 - cos_v, 5.0);
	float show = pane_m * (1.0 - mull) * (1.0 - fres) * (1.0 - curt * 0.75 * (shop ? 0.0 : 1.0)) * (1.0 - clamp(drape, 0.0, 1.0));
	vec3 lamp = mix(vec3(1.0, 0.72, 0.42), vec3(0.85, 0.92, 1.0), step(0.78, warm));
	vec3 interior = room_col * (0.16 * (1.0 - night) + room_lit * night * 1.6 * lamp) * (door_col ? 0.0 : 1.0);
	if (shop) {
		// Verkaufsraum: hell, tagsüber beleuchtet; leerstehend dunkel
		// Verkaufsraum: Regalreihen (dunkle Bänder) vor hellerem Hintergrund, tags gedämpft, nachts beleuchtet
		interior = vacant ? room_col * 0.04 : room_col * (0.3 * (1.0 - night) + 1.5 * night * lamp);
	}
	EMISSION = emis * 2.6 * night * curt + interior * show + emis * 0.6 * night * (1.0 - curt);

	// ---- Ausgabe --------------------------------------------------------
	ALBEDO = clamp(base, 0.0, 1.0);
	float rough = mix(rough_base, 0.04, pane_m * (1.0 - mull));
	rough = mix(rough, 0.3, frame_m * 0.5);
	rough = mix(rough, 0.45, wetness * 0.35);      // Fassaden werden bei Nässe nur leicht glänzend
	ROUGHNESS = rough;
	SPECULAR = mix(0.4, 0.5, pane_m * (1.0 - mull));   // Glas: F0 = 4 %
	METALLIC = 0.0;
	// Laibungs-Schrägen als Normalenkippung (Tangente = entlang Wand, Binormale = oben)
	vec2 tilt = vec2(0.0);
	if (has_win) {
		float edge = smoothstep(0.0, -0.1, d) * (1.0 - glass_m * 0.0);
		vec2 rel = q - wc;
		vec2 an = abs(rel) - whs;
		vec2 dirn = (an.x > an.y) ? vec2(sign(rel.x), 0.0) : vec2(0.0, sign(rel.y));
		float band_w = smoothstep(0.12, 0.0, abs(d + 0.0)) * (1.0 - glass_m) ;
		tilt = -dirn * band_w * 0.9;
	}
	vec3 nn = normalize(vec3(nmap.xy * 0.8 + tilt, max(nmap.z, 0.2)));
	NORMAL_MAP = mix(nn * 0.5 + 0.5, vec3(0.5, 0.5, 1.0), glass_m * 0.9);
	NORMAL_MAP_DEPTH = 0.8;
}
