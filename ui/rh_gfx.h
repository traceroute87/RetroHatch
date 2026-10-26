/* SDL 1.2 drawing helpers: rects, RB12 bitmap fonts, tinted icon masks.
 * Every draw call is a no-op when the surface is NULL (text/measure calls
 * still return sizes), so layout code can run once to measure, once to draw. */
#ifndef RH_GFX_H
#define RH_GFX_H
#include <SDL/SDL.h>

typedef struct { Uint8 r, g, b; } rh_rgb;
typedef struct rh_font rh_font;

rh_font *gfx_font_load(const char *path);   /* Rockbox RB12 .fnt (1-bpp or 4-bpp) */
void gfx_font_free(rh_font *f);
int gfx_font_h(const rh_font *f);
int gfx_text_w(const rh_font *f, const char *s);
int gfx_text(SDL_Surface *d, const rh_font *f, const char *s, int x, int y, rh_rgb c);
void gfx_text_c(SDL_Surface *d, const rh_font *f, const char *s, int cx, int y, rh_rgb c); /* centred on cx */
const char *gfx_ellipsize(const rh_font *f, const char *s, int w, char *buf, int cap);
/* word-wrap s into lines of at most w px; fills starts/lens, returns line count (<= max) */
int gfx_wrap(const rh_font *f, const char *s, int w, const char **starts, int *lens, int max);

void gfx_fill(SDL_Surface *d, int x, int y, int w, int h, rh_rgb c);
void gfx_rfill(SDL_Surface *d, int x, int y, int w, int h, int r, rh_rgb c);
void gfx_rbox(SDL_Surface *d, int x, int y, int w, int h, int r, rh_rgb border, rh_rgb fill); /* 1px border */
void gfx_disc(SDL_Surface *d, int cx, int cy, int r, rh_rgb c);

SDL_Surface *gfx_img_load(const char *path);          /* display-format, alpha kept; NULL on failure */
void gfx_img(SDL_Surface *d, SDL_Surface *img, int x, int y);
void gfx_mask(SDL_Surface *d, SDL_Surface *img, int x, int y, rh_rgb tint); /* img alpha tinted; top-left at x,y */
#endif
