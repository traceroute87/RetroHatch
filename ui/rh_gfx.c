#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <SDL/SDL_image.h>
#include "rh_gfx.h"

/* ---- RB12 bitmap font: layout as documented in TaraFi's src/font.c ---- */
struct rh_font {
	uint8_t *data;
	long len;
	int height, depth, long_off;
	uint32_t firstchar, defaultchar, size;
	const uint8_t *bitmap, *offtbl, *widthtbl;
};

static uint16_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

rh_font *gfx_font_load(const char *path)
{
	rh_font *f = calloc(1, sizeof *f);
	FILE *fp = f ? fopen(path, "rb") : NULL;
	uint32_t nbits, noffset, nwidth, otbl, wtbl;
	if (!fp) { free(f); return NULL; }
	fseek(fp, 0, SEEK_END); f->len = ftell(fp); fseek(fp, 0, SEEK_SET);
	if (f->len < 36 || !(f->data = malloc(f->len)) || fread(f->data, 1, f->len, fp) != (size_t)f->len ||
	    memcmp(f->data, "RB12", 4)) { fclose(fp); free(f->data); free(f); return NULL; }
	fclose(fp);
	f->height = rd16(f->data + 6); f->depth = rd16(f->data + 10);
	f->firstchar = rd32(f->data + 12); f->defaultchar = rd32(f->data + 16); f->size = rd32(f->data + 20);
	nbits = rd32(f->data + 24); noffset = rd32(f->data + 28); nwidth = rd32(f->data + 32);
	otbl = 36 + ((nbits + 1) & ~1u);
	f->long_off = nbits >= 0x10000;
	wtbl = otbl + noffset * (f->long_off ? 4u : 2u);
	if ((long)(wtbl + nwidth) > f->len || !f->height || f->height > 64) { free(f->data); free(f); return NULL; }
	f->bitmap = f->data + 36; f->offtbl = f->data + otbl; f->widthtbl = f->data + wtbl;
	if (f->depth && f->defaultchar >= f->firstchar) f->defaultchar -= f->firstchar;
	if (f->defaultchar >= f->size) f->defaultchar = 0;
	return f;
}

void gfx_font_free(rh_font *f) { if (f) free(f->data); free(f); }
int gfx_font_h(const rh_font *f) { return f ? f->height : 0; }

static int gidx(const rh_font *f, uint32_t cp)
{
	uint32_t i = cp < f->firstchar ? f->size : cp - f->firstchar;
	return i < f->size ? (int)i : (int)f->defaultchar;
}
static int gw(const rh_font *f, int i) { return f->widthtbl[i]; }

/* UTF-8 (1-3 bytes); typographic punctuation the font lacks is shown as ASCII */
static const char *u8(const char *s, uint32_t *cp)
{
	unsigned char c = (unsigned char)*s++;
	if (c < 0x80) { *cp = c; return s; }
	if ((c & 0xE0) == 0xC0 && (s[0] & 0xC0) == 0x80) { *cp = (c & 0x1F) << 6 | (s[0] & 0x3F); return s + 1; }
	if ((c & 0xF0) == 0xE0 && (s[0] & 0xC0) == 0x80 && (s[1] & 0xC0) == 0x80) {
		*cp = (c & 0x0F) << 12 | (s[0] & 0x3F) << 6 | (s[1] & 0x3F);
		if (*cp == 0x2018 || *cp == 0x2019) *cp = '\'';
		else if (*cp == 0x201C || *cp == 0x201D) *cp = '"';
		else if (*cp == 0x2013 || *cp == 0x2014) *cp = '-';
		return s + 2;
	}
	*cp = ' ';
	return s;
}

int gfx_text_w(const rh_font *f, const char *s)
{
	uint32_t cp; int w = 0;
	if (!f || !s) return 0;
	while (*s) { s = u8(s, &cp); w += gw(f, gidx(f, cp)); }
	return w;
}

static Uint32 getpx(SDL_Surface *s, int x, int y)
{
	Uint8 *p = (Uint8 *)s->pixels + y * s->pitch + x * s->format->BytesPerPixel;
	return s->format->BytesPerPixel == 2 ? *(Uint16 *)p : s->format->BytesPerPixel == 4 ? *(Uint32 *)p : (Uint32)(p[0] | p[1] << 8 | p[2] << 16);
}
static void putpx(SDL_Surface *s, int x, int y, Uint32 v)
{
	Uint8 *p = (Uint8 *)s->pixels + y * s->pitch + x * s->format->BytesPerPixel;
	if (s->format->BytesPerPixel == 2) *(Uint16 *)p = (Uint16)v;
	else if (s->format->BytesPerPixel == 4) *(Uint32 *)p = v;
	else { p[0] = v & 255; p[1] = v >> 8 & 255; p[2] = v >> 16 & 255; }
}
static int inclip(SDL_Surface *d, int x, int y)
{
	return x >= d->clip_rect.x && y >= d->clip_rect.y && x < d->clip_rect.x + d->clip_rect.w && y < d->clip_rect.y + d->clip_rect.h;
}
/* blend colour c over the pixel with coverage a/255 */
static void blendpx(SDL_Surface *d, int x, int y, rh_rgb c, int a)
{
	Uint8 br, bg, bb;
	if (a <= 0 || !inclip(d, x, y)) return;
	if (a >= 255) { putpx(d, x, y, SDL_MapRGB(d->format, c.r, c.g, c.b)); return; }
	SDL_GetRGB(getpx(d, x, y), d->format, &br, &bg, &bb);
	putpx(d, x, y, SDL_MapRGB(d->format, (c.r * a + br * (255 - a)) / 255, (c.g * a + bg * (255 - a)) / 255, (c.b * a + bb * (255 - a)) / 255));
}

int gfx_text(SDL_Surface *d, const rh_font *f, const char *s, int x, int y, rh_rgb c)
{
	uint32_t cp; int x0 = x;
	if (!f || !s) return 0;
	if (d && SDL_MUSTLOCK(d)) SDL_LockSurface(d);
	while (*s) {
		int gi, w, r, col;
		const uint8_t *g;
		s = u8(s, &cp);
		gi = gidx(f, cp); w = gw(f, gi);
		g = f->bitmap + (f->long_off ? rd32(f->offtbl + gi * 4) : rd16(f->offtbl + gi * 2));
		if (d) for (r = 0; r < f->height; r++)
			for (col = 0; col < w; col++) {
				if (f->depth) {      /* 4-bpp: 0 = full ink, 15 = none */
					int n = r * w + col, a = (n & 1) ? g[n / 2] >> 4 : g[n / 2] & 15;
					blendpx(d, x + col, y + r, c, (15 - a) * 255 / 15);
				} else if (g[(r >> 3) * w + col] & (1 << (r & 7)))
					blendpx(d, x + col, y + r, c, 255);
			}
		x += w;
	}
	if (d && SDL_MUSTLOCK(d)) SDL_UnlockSurface(d);
	return x - x0;
}

void gfx_text_c(SDL_Surface *d, const rh_font *f, const char *s, int cx, int y, rh_rgb c)
{
	gfx_text(d, f, s, cx - gfx_text_w(f, s) / 2, y, c);
}

const char *gfx_ellipsize(const rh_font *f, const char *s, int w, char *buf, int cap)
{
	int n = (int)strlen(s);
	if (gfx_text_w(f, s) <= w) return s;
	if (n > cap - 4) n = cap - 4;
	for (; n > 0; n--) {
		if (((unsigned char)s[n] & 0xC0) == 0x80) continue;   /* never cut inside a character */
		memcpy(buf, s, n); strcpy(buf + n, "...");
		if (gfx_text_w(f, buf) <= w) return buf;
	}
	buf[0] = 0;
	return buf;
}

int gfx_wrap(const rh_font *f, const char *s, int w, const char **starts, int *lens, int max)
{
	int n = 0;
	while (*s && n < max) {
		const char *p = s, *brk = NULL;
		int cw = 0;
		uint32_t cp;
		while (*s == ' ') s++;
		p = s;
		while (*p && *p != '\n') {
			const char *nx = u8(p, &cp);
			cw += gw(f, gidx(f, cp));
			if (cw > w && p > s) { if (!brk) brk = p; break; }
			if (cp == ' ') brk = p;
			p = nx;
		}
		if (!*p || *p == '\n') brk = p;       /* rest fits */
		starts[n] = s; lens[n] = (int)(brk - s);
		while (lens[n] > 0 && s[lens[n] - 1] == ' ') lens[n]--;
		n++;
		s = brk; if (*s == '\n') s++;
	}
	return n;
}

/* ---- primitives ---- */
void gfx_fill(SDL_Surface *d, int x, int y, int w, int h, rh_rgb c)
{
	SDL_Rect r = {(Sint16)x, (Sint16)y, (Uint16)w, (Uint16)h};
	if (d && w > 0 && h > 0) SDL_FillRect(d, &r, SDL_MapRGB(d->format, c.r, c.g, c.b));
}

void gfx_rfill(SDL_Surface *d, int x, int y, int w, int h, int r, rh_rgb c)
{
	int dy;
	if (!d) return;
	for (dy = 0; dy < r; dy++) {         /* corner inset per row: circle of radius r */
		double dd = r - dy - 0.5;
		int inset = r - (int)(__builtin_sqrt((double)r * r - dd * dd) + 0.5);
		gfx_fill(d, x + inset, y + dy, w - 2 * inset, 1, c);
		gfx_fill(d, x + inset, y + h - 1 - dy, w - 2 * inset, 1, c);
	}
	gfx_fill(d, x, y + r, w, h - 2 * r, c);
}

void gfx_rbox(SDL_Surface *d, int x, int y, int w, int h, int r, rh_rgb border, rh_rgb fill)
{
	gfx_rfill(d, x, y, w, h, r, border);
	gfx_rfill(d, x + 1, y + 1, w - 2, h - 2, r > 0 ? r - 1 : 0, fill);
}

void gfx_disc(SDL_Surface *d, int cx, int cy, int r, rh_rgb c)
{
	gfx_rfill(d, cx - r, cy - r, 2 * r + 1, 2 * r + 1, r, c);
}

SDL_Surface *gfx_img_load(const char *path)
{
	SDL_Surface *raw = IMG_Load(path), *o;
	if (!raw) return NULL;
	o = SDL_DisplayFormatAlpha(raw);
	SDL_FreeSurface(raw);
	return o;
}

void gfx_img(SDL_Surface *d, SDL_Surface *img, int x, int y)
{
	SDL_Rect r = {(Sint16)x, (Sint16)y, 0, 0};
	if (d && img) SDL_BlitSurface(img, NULL, d, &r);
}

void gfx_mask(SDL_Surface *d, SDL_Surface *img, int x, int y, rh_rgb tint)
{
	int ix, iy;
	if (!d || !img) return;
	if (SDL_MUSTLOCK(img)) SDL_LockSurface(img);
	if (SDL_MUSTLOCK(d)) SDL_LockSurface(d);
	for (iy = 0; iy < img->h; iy++)
		for (ix = 0; ix < img->w; ix++) {
			Uint8 r, g, b, a;
			SDL_GetRGBA(getpx(img, ix, iy), img->format, &r, &g, &b, &a);
			blendpx(d, x + ix, y + iy, tint, a);
		}
	if (SDL_MUSTLOCK(d)) SDL_UnlockSurface(d);
	if (SDL_MUSTLOCK(img)) SDL_UnlockSurface(img);
}
