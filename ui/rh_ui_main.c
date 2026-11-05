/* RetroHatch UI program (host and RG Nano).
 *   retrohatch [--assets dir] [--candidates file] [--shot out.bmp]                      production: signed catalog, install enabled
 *   retrohatch --catalog dir --state dir ...                                           preview/test data: unsigned, READ-ONLY, no install
 * Defaults are relative to the cwd: opkrun chdir()s into the mounted OPK.
 * --shot renders the Home screen once and exits (path/asset check); it never creates state or enables installing.
 *
 * Production (this file without RH_DEV): the catalog shown is the newest signed one that verified against the compiled-in
 * production key (trusted_keys_prod.h): bundled in the OPK or downloaded earlier, refreshed over HTTPS. Install, update and
 * uninstall go through rh_ops.c (production rules) and the same engine as DEV. Missing or invalid key, no catalog, or an
 * unusable state directory = nothing installable: the UI stays a read-only browser. The UNAPPROVED candidates are
 * rh_cand rows: the UI has no install path for them in any build.
 *
 * Keys: fkgpiod on FunKey OS delivers the buttons as the letters u d l r a b x y m n s q
 * (same map TaraFi ships and hardware-tests): A = 'a', B = 'b', q = MENU. Arrow keys,
 * Return and Backspace are accepted for desktop runs. Escape is the power key: ignored. */
#include <stdio.h>
#include <string.h>
#include <SDL/SDL.h>
#include "rh_ui.h"
#include "../platforms/nano/rh_install.h"
#ifdef RH_DEV                       /* RetroHatchDev.opk only: install flow for RH Probe, DEV state dir only */
#include <stdlib.h>
#include "rh_ops.h"
#include "rh_source.h"
#include "trusted_keys_dev.h"
#define STATE_DEFAULT RH_DEV_STATE_DIR
static rh_model m;
static SDL_Surface *g_scr;
static const rh_src_cfg src = {RH_DEV_STATE_DIR, RH_DEV_STATE_DIR "/catalog.pkg", "catalog/catalog.pkg", RH_TRUSTED_KEYS, RH_N_TRUSTED_KEYS};
/* DEV: only a catalog that verified (signature, policy, rollback state) ever reaches the UI */
static void refresh(void)
{
	char *idx; size_t len; rh_src_info si;
	if (!rh_src_load(&src, &idx, &len, &si)) {
		rh_model_load_signed(&m, idx, len, si.source, si.serial, si.expires, RH_DEVICE_ID, RH_DEV_STATE_DIR);
		free(idx);
	} else rh_model_load_none(&m, si.why, RH_DEV_STATE_DIR);
}
/* called by the downloader every ~100 ms: show progress, let B cancel */
static int net_poll(uint64_t done, uint64_t total)
{
	SDL_Event e; int cancel = 0;
	rh_ui_progress(done, total);
	while (SDL_PollEvent(&e))
		if (e.type == SDL_KEYDOWN && (e.key.keysym.sym == SDLK_b || e.key.keysym.sym == SDLK_BACKSPACE)) cancel = 1;
	rh_ui_draw(g_scr); SDL_Flip(g_scr);
	return cancel;
}
#else
#include <stdlib.h>
#include "rh_ops.h"
#include "rh_source.h"
#include "trusted_keys_prod.h"       /* the PRODUCTION key only; the DEV key header is never included here */
#define STATE_DEFAULT RH_NANO_STATE_DIR
#define PROD_CACHE_DIR RH_NANO_STATE_DIR "/cache"
static rh_model m;
static SDL_Surface *g_scr;
static const char *cands_path = "candidates/rg-nano.json";
/* nkeys is set at start: 0 when the compiled-in key is missing (placeholder) or invalid (all zero), so nothing can verify */
static rh_src_cfg src = {RH_NANO_STATE_DIR, RH_NANO_STATE_DIR "/catalog.pkg", "catalog/catalog.pkg", RH_TRUSTED_KEYS, 0};
static size_t usable_keys(void)
{
	size_t k, b, n = RH_N_TRUSTED_KEYS;   /* 0 in the placeholder header of a checkout without the production key */
	for (k = 0; k < n; k++) {
		for (b = 0; b < 32 && !RH_TRUSTED_KEYS[k][b]; b++) {}
		if (b == 32) return 0;   /* an all-zero key is not a key: refuse the whole list */
	}
	return n;
}
/* production: only a catalog that verified (signature, policy, rollback state) ever reaches the UI; the candidates are added after
 * it (they are read-only rows and never replace or join the approved apps) */
static void refresh(void)
{
	char *idx; size_t len; rh_src_info si;
	if (!rh_src_load(&src, &idx, &len, &si)) {
		rh_model_load_signed(&m, idx, len, si.source, si.serial, si.expires, RH_DEVICE_ID, RH_NANO_STATE_DIR);
		free(idx);
	} else rh_model_load_none(&m, si.why, RH_NANO_STATE_DIR);
	rh_model_load_candidates(&m, cands_path);   /* UNAPPROVED candidate inventory snapshot: read-only, never installable */
}
/* called by the downloader every ~100 ms: show progress, let B cancel */
static int net_poll(uint64_t done, uint64_t total)
{
	SDL_Event e; int cancel = 0;
	rh_ui_progress(done, total);
	while (SDL_PollEvent(&e))
		if (e.type == SDL_KEYDOWN && (e.key.keysym.sym == SDLK_b || e.key.keysym.sym == SDLK_BACKSPACE)) cancel = 1;
	rh_ui_draw(g_scr); SDL_Flip(g_scr);
	return cancel;
}
#endif

static int translate(SDLKey k, rh_key *o)
{
	switch (k) {
	case SDLK_u: case SDLK_UP: *o = RH_K_UP; return 1;
	case SDLK_d: case SDLK_DOWN: *o = RH_K_DOWN; return 1;
	case SDLK_l: case SDLK_LEFT: *o = RH_K_LEFT; return 1;
	case SDLK_r: case SDLK_RIGHT: *o = RH_K_RIGHT; return 1;
	case SDLK_a: case SDLK_RETURN: *o = RH_K_A; return 1;
	case SDLK_b: case SDLK_BACKSPACE: *o = RH_K_B; return 1;
	case SDLK_x: case SDLK_PAGEUP: *o = RH_K_PGUP; return 1;      /* X = page up, Y = page down (the x/y letters fkgpiod delivers) */
	case SDLK_y: case SDLK_PAGEDOWN: *o = RH_K_PGDN; return 1;
	default: return 0;
	}
}

int main(int argc, char **argv)
{
	const char *catalog = "catalog", *assets = "assets", *state = STATE_DEFAULT, *shot = NULL;
	SDL_Surface *scr; SDL_Event e; int run = 1, i;
	int preview = 0;   /* production program given --catalog/--state: unsigned local test data, read-only, never installs */

#ifdef RH_DEV
	if (argc != 1 && !(argc == 3 && !strcmp(argv[1], "--shot"))) { fprintf(stderr, "retrohatch DEV: no path options\n"); return 2; }
#endif
	for (i = 1; i + 1 < argc; i += 2) {
		if (!strcmp(argv[i], "--catalog")) { catalog = argv[i + 1]; preview = 1; }
		else if (!strcmp(argv[i], "--assets")) assets = argv[i + 1];
		else if (!strcmp(argv[i], "--state")) { state = argv[i + 1]; preview = 1; }
		else if (!strcmp(argv[i], "--shot")) shot = argv[i + 1];
#ifndef RH_DEV
		else if (!strcmp(argv[i], "--candidates")) cands_path = argv[i + 1];
#endif
		else { fprintf(stderr, "retrohatch: unknown option %s\n", argv[i]); return 2; }
	}
#ifdef RH_DEV
	(void)state; (void)preview;
	refresh();
#else
	if (preview) {   /* local unsigned catalog files: shown, never installable (no ops are set below) */
		rh_model_load(&m, catalog, state);
		rh_model_load_candidates(&m, cands_path);
	} else {
		src.nkeys = usable_keys();
		if (!src.nkeys) fprintf(stderr, "retrohatch: no usable production catalog key: nothing can be verified or installed\n");
		refresh();
	}
#endif
#ifdef RH_DEV
	{
		rh_ops_cfg oc = {RH_DEV_APPS_DIR, RH_DEV_STATE_DIR, RH_DEV_CACHE_DIR, NULL, NULL, NULL, refresh,
			"certs/ca-bundle.crt", RH_DEV_STATE_DIR "/extra-ca.crt", RH_DEV_STATE_DIR "/mirror.txt", RH_CATALOG_BASE_URL,
			RH_DEV_STATE_DIR "/catalog-url.txt", RH_DEV_STATE_DIR "/catalog.pkg", "catalog/catalog.pkg", RH_TRUSTED_KEYS,
			RH_N_TRUSTED_KEYS, net_poll, 0 /* DEV rules */};
		const rh_ui_ops *ops = rh_ops_init(&oc);
		if (!ops) { fprintf(stderr, "retrohatch DEV: ops gate rejected the configuration\n"); return 1; }
		if (!shot) { int rc = rh_ops_recover(); if (rc) fprintf(stderr, "retrohatch DEV: recovery failed (%d)\n", rc); }
		rh_ui_set_ops(ops);
	}
#else
	if (!preview && !shot) {   /* production install path; fails closed: any problem leaves the UI a read-only browser */
		rh_ops_cfg oc;
		const rh_ui_ops *ops;
		memset(&oc, 0, sizeof oc);
		oc.production = 1;
		oc.apps_dir = RH_NANO_APPS_DIR; oc.state_dir = RH_NANO_STATE_DIR; oc.cache_dir = PROD_CACHE_DIR; oc.refresh = refresh;
		oc.ca_bundle = "certs/ca-bundle.crt"; oc.base_url = RH_CATALOG_BASE_URL;   /* no extra CA, no mirror, no URL override: those are DEV test seams */
		oc.cache_pkg = src.cache_pkg; oc.bundled_pkg = src.bundled_pkg; oc.keys = RH_TRUSTED_KEYS; oc.nkeys = src.nkeys; oc.progress = net_poll;
		ops = rh_ops_init(&oc);
		if (!ops) fprintf(stderr, "retrohatch: install disabled (state or cache directory unusable); browsing only\n");
		else {
			int rc = rh_ops_recover();
			if (rc) fprintf(stderr, "retrohatch: recovery failed (%d); installing is disabled\n", rc);
			else rh_ui_set_ops(ops);
		}
	}
#endif
	if (SDL_Init(SDL_INIT_VIDEO)) { fprintf(stderr, "retrohatch: SDL_Init: %s\n", SDL_GetError()); return 1; }
	if (!(scr = SDL_SetVideoMode(240, 240, 16, SDL_SWSURFACE))) { fprintf(stderr, "retrohatch: SDL_SetVideoMode: %s\n", SDL_GetError()); return 1; }
	g_scr = scr;
	rh_ui_set_planner(rh_plan_target);   /* read-only Install Preview (production); DEV has real ops, which take precedence */
	SDL_ShowCursor(SDL_DISABLE);
	SDL_WM_SetCaption("RetroHatch", "RetroHatch");
	if (rh_ui_init(assets, &m)) { fprintf(stderr, "retrohatch: cannot load assets from '%s'\n", assets); SDL_Quit(); return 1; }
	if (m.n_apps == 0) fprintf(stderr, "retrohatch: no catalog entries (%s)\n", m.cat.status[0] ? m.cat.status : catalog);
	if (shot) {
		rh_ui_draw(scr);
		i = SDL_SaveBMP(scr, shot);
		rh_ui_free(); SDL_Quit();
		return i != 0;
	}
	SDL_EnableKeyRepeat(250, 80);   /* as TaraFi */
	while (run) {
		rh_key k;
		rh_ui_draw(scr); SDL_Flip(scr);
		if (rh_ui_run_pending()) continue;                         /* install ran: redraw the result */
		if (!SDL_WaitEvent(&e)) break;
		do {
			if (e.type == SDL_QUIT) { if (!rh_ui_busy()) run = 0; } /* SIGTERM: nothing to save; never mid-install */
			else if (e.type == SDL_KEYDOWN) {
				if (e.key.keysym.sym == SDLK_q) { if (!rh_ui_busy()) run = 0; }   /* MENU */
				else if (translate(e.key.keysym.sym, &k)) rh_ui_key(k);
			}
		} while (run && SDL_PollEvent(&e));
	}
	rh_ui_free(); SDL_Quit();
	return 0;
}
