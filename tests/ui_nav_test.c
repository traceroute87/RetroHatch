/* Phase 4B UI test: navigation + palette checks on the real 240x240 surface.
 *   ui_nav_test <repo_root> [shots_dir]
 * With shots_dir, also writes one BMP per screen. Uses SDL's dummy video. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <SDL/SDL.h>
#include "../ui/rh_ui.h"

#define HOME_ROW_SEL_Y 128   /* inside the first home row (y 123..143) */
static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static SDL_Surface *scr;
static const char *shots;

static unsigned px(int x, int y)
{
	Uint8 r, g, b;
	SDL_GetRGB(*(Uint32 *)((Uint8 *)scr->pixels + y * scr->pitch + x * 4), scr->format, &r, &g, &b);
	return r << 16 | g << 8 | b;
}

static void shot(const char *name)
{
	char p[512];
	rh_ui_draw(scr);
	if (!shots) return;
	snprintf(p, sizeof p, "%s/%s.bmp", shots, name);
	SDL_SaveBMP(scr, p);
}

static void keys(const char *s)   /* u d l r a b */
{
	for (; *s; s++) rh_ui_key(*s == 'u' ? RH_K_UP : *s == 'd' ? RH_K_DOWN : *s == 'l' ? RH_K_LEFT : *s == 'r' ? RH_K_RIGHT : *s == 'a' ? RH_K_A : RH_K_B);
}

static int app_idx(const rh_model *m, const char *id)
{
	int i;
	for (i = 0; i < m->n_apps; i++) if (!strcmp(m->apps[i].id, id)) return i;
	return -1;
}

static void versions(void)
{
	CHECK(rh_ver_cmp("1.0.0", "1.1.0") == -1);
	CHECK(rh_ver_cmp("1.9", "1.10") == -1);          /* numeric, not textual */
	CHECK(rh_ver_cmp("1.1", "1.1.0") == 0);
	CHECK(rh_ver_cmp("2.0.0", "1.9.9") == 1);        /* installed newer than catalog: not an update */
	CHECK(rh_ver_cmp("1.0.0", "1.1.0-rc1") == 2);    /* suffix anywhere: incomparable, even when an earlier part differs */
	CHECK(rh_ver_cmp("1.0.0", "1.0.0-rc1") == 2);    /* not plain numbers: incomparable, never "newer" */
	CHECK(rh_ver_cmp("", "1.0") == 2 && rh_ver_cmp("1.0", "") == 2 && rh_ver_cmp("abc", "1") == 2);
}

static rh_ui_view V(void) { rh_ui_view v; rh_ui_view_get(&v); return v; }

static void real_catalog(const char *root, const char *assets)
{
	static rh_model m; char cat[512], st[512]; rh_ui_view v;
	snprintf(cat, sizeof cat, "%s/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/nostate", root);
	rh_model_load(&m, cat, st);
	CHECK(m.n_apps >= 1 && !strcmp(m.apps[0].id, "tarafi"));
	CHECK(!m.apps[0].available);                 /* TaraFi stays non-installable */
	CHECK(m.n_inst == 0 && m.n_upd == 0);
	CHECK(rh_ui_init(assets, &m) == 0);

	shot("1_home");
	CHECK(px(120, HOME_ROW_SEL_Y) == 0xE9A23B);         /* selected row: solid amber */
	CHECK(px(120, HOME_ROW_SEL_Y + 25) == 0x35352B);    /* inactive row: dark olive */
	CHECK(px(2, 215) == 0x171B19);                      /* main background */
	keys("uu"); CHECK(V().sel == 0);
	keys("dddd"); CHECK(V().sel == 3);
	keys("uuu"); CHECK(V().sel == 0);

	keys("a"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.depth == 1 && v.count == m.n_apps);
	shot("2_discover");
	CHECK(px(120, 40) == 0xE9A23B);                     /* first row (TaraFi) selected */
	keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && !strcmp(m.apps[v.app].id, "tarafi"));
	shot("3_details_tarafi");
	CHECK(V().action == RH_ACT_UNAVAILABLE);            /* TaraFi: "Not available", never installable */
	CHECK(px(226, 195) != 0xE9A23B && px(226, 195) == 0x272721);   /* action bar is a plain card, not an amber (focusable-looking) row */
	keys("dddddddddddddddddddddddddddddd"); CHECK(V().scroll > 0); shot("3b_details_tarafi_bottom"); keys("uuuuuuuuuuuuuuuuuuuuuuuuuuuuuu"); CHECK(V().scroll == 0);
	keys("a"); CHECK(V().screen == RH_S_DETAILS);       /* A does nothing here */
	keys("b"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.sel == 0);
	keys("b"); CHECK(V().screen == RH_S_HOME && V().depth == 0);
	keys("b"); CHECK(V().screen == RH_S_HOME);          /* B at home: stay */

	keys("da"); CHECK(V().screen == RH_S_INSTALLED && V().count == 0);
	shot("5_installed_empty"); keys("a"); CHECK(V().screen == RH_S_INSTALLED); keys("b");
	keys("da"); CHECK(V().screen == RH_S_UPDATES && V().count == 0);
	shot("6_updates_empty"); keys("b");
	keys("da"); CHECK(V().screen == RH_S_SETTINGS);
	shot("7_settings");
	{ int i; static const char *n[] = {"8_device_info", "9_catalog_status", "10_network_status", "11_about"};
	  for (i = 0; i < 4; i++) {
		keys("a"); v = V(); CHECK(v.screen == RH_S_INFO && (int)v.info == i && v.depth == 2);
		shot(n[i]); keys("b"); CHECK(V().screen == RH_S_SETTINGS && V().sel == i); keys("d");
	  } }
	rh_ui_free();
}

static void fixture(const char *root, const char *assets)
{
	static rh_model m; char cat[512], st[512]; rh_ui_view v; int i;
	snprintf(cat, sizeof cat, "%s/tests/ui_fixture/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/state", root);
	rh_model_load(&m, cat, st);
	CHECK(m.n_apps == 5 && m.n_inst == 3 && m.n_upd == 1);
	CHECK(m.inst[2].app == -1);                        /* installed but not in catalog */
	CHECK(rh_ui_init(assets, &m) == 0);

	keys("a"); shot("fixture_discover");
	for (i = 0; i < 4; i++) { keys("d"); CHECK(V().sel_visible); }   /* selection always on screen */
	CHECK(V().sel == 4 && V().scroll > 0 && V().scroll % 44 == 0);   /* whole rows only */
	shot("fixture_discover_scrolled");
	for (i = 0; i < 4; i++) { keys("u"); CHECK(V().sel_visible); }
	CHECK(V().sel == 0 && V().scroll == 0);
	keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS);
	shot("fixture_details_available");
	CHECK(V().action == RH_ACT_INSTALL_SOON);          /* verified, not installed */
	CHECK(px(226, 195) == 0x272721);
	keys("a"); CHECK(V().screen == RH_S_DETAILS && V().depth == 2 && V().action == RH_ACT_INSTALL_SOON);   /* A does nothing */
	shot("fixture_details_install_soon");
	keys("bb");

	keys("da"); CHECK(V().screen == RH_S_INSTALLED && V().count == 3);
	shot("fixture_installed");
	keys("dd"); CHECK(V().sel == 2); keys("a"); CHECK(V().screen == RH_S_INSTALLED);   /* orphan: no details */
	keys("b"); keys("da"); CHECK(V().screen == RH_S_UPDATES && V().count == 1);
	shot("fixture_updates");
	rh_ui_free();
}


/* Phase 5A: isolated test records (tests/ui_test_data) through the same loader the Nano test build uses */
static void scenario(const char *root, const char *assets, const char *name)
{
	static rh_model m; char cat[512], st[512]; rh_ui_view v; int i;
	snprintf(cat, sizeof cat, "%s/tests/ui_test_data/catalog", root);
	snprintf(st, sizeof st, "%s/tests/ui_test_data/scenarios/%s", root, name);
	rh_model_load(&m, cat, st);
	CHECK(m.n_apps == 6 && !m.apps[0].available && !strcmp(m.apps[0].id, "tarafi"));   /* TaraFi still first + unavailable */
	CHECK(rh_ui_init(assets, &m) == 0);
	if (!strcmp(name, "populated")) {
		CHECK(m.n_inst == 6 && m.n_upd == 1 && m.inst[5].app == -1);
		CHECK(m.inst[0].app >= 0 && !strcmp(m.apps[m.inst[0].app].name, "RH Probe (test)") && !strcmp(m.inst[0].version, "1.0.0"));
		CHECK(m.upd[0] == 0 && !strcmp(m.apps[m.inst[0].app].version, "1.1.0"));   /* 1.0.0 -> 1.1.0 */
		keys("dar"); /* Home -> Installed (right = no-op) */
		v = V(); CHECK(v.screen == RH_S_INSTALLED && v.count == 6);
		shot("5a_installed_populated");
		for (i = 0; i < 5; i++) { keys("d"); CHECK(V().sel_visible); }
		CHECK(V().sel == 5 && V().scroll > 0 && V().scroll % 44 == 0);
		shot("5b_installed_scrolled_orphan");
		keys("a"); CHECK(V().screen == RH_S_INSTALLED);                         /* removed-from-catalog entry: no details, no crash */
		for (i = 0; i < 5; i++) keys("u");
		CHECK(V().sel == 0 && V().scroll == 0);
		keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && !strcmp(m.apps[v.app].id, "rhprobe"));
		CHECK(v.action == RH_ACT_UPDATE);                                      /* installed 1.0.0, verified 1.1.0 */
		shot("5c_installed_details_update");
		keys("a"); CHECK(V().screen == RH_S_DETAILS && V().depth == 2);        /* A: nothing */
		keys("bd"); keys("a"); v = V();                                        /* RH Probe B: same version */
		CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_INSTALLED);
		shot("5f_details_installed");
		keys("bd"); keys("a"); CHECK(V().action == RH_ACT_INSTALLED);          /* C: installed 1.2.0 > catalog 1.0.0 -> no downgrade offer */
		keys("bd"); keys("a"); v = V();                                        /* D: catalog 1.1.0 but only "experimental" */
		CHECK(!strcmp(m.apps[v.app].id, "rhprobe-d") && v.action == RH_ACT_INSTALLED);
		keys("bu"); keys("u"); keys("u"); keys("u"); CHECK(V().sel == 0);
		keys("b"); CHECK(V().screen == RH_S_HOME);
		keys("da"); v = V(); CHECK(v.screen == RH_S_UPDATES && v.count == 1);
		shot("6a_updates_populated");
		keys("a"); CHECK(V().screen == RH_S_DETAILS && !strcmp(m.apps[V().app].id, "rhprobe"));
		keys("b"); CHECK(V().screen == RH_S_UPDATES);
	} else if (!strcmp(name, "noupdates")) {
		CHECK(m.n_inst == 2 && m.n_upd == 0);
		keys("da"); CHECK(V().screen == RH_S_INSTALLED && V().count == 2);
		shot("5e_installed_two_rows");
		keys("bda"); v = V(); CHECK(v.screen == RH_S_UPDATES && v.count == 0);
		shot("6b_updates_empty_with_installed");
		keys("buu"); keys("a"); v = V(); CHECK(v.screen == RH_S_DISCOVER);       /* Discover: TaraFi, RH Probe, B..E */
		keys("a"); CHECK(V().action == RH_ACT_UNAVAILABLE); keys("b");
		keys("d"); keys("a"); v = V();
		CHECK(!strcmp(m.apps[v.app].id, "rhprobe") && v.action == RH_ACT_INSTALL_SOON);   /* verified, not installed */
		shot("5g_details_install_soon"); keys("b");
		CHECK(app_idx(&m, "rhprobe-d") >= 0);
		keys("ddd"); keys("a"); v = V();
		CHECK(!strcmp(m.apps[v.app].id, "rhprobe-d") && v.action == RH_ACT_UNAVAILABLE);   /* experimental: not offered */
		shot("5h_details_unverified_not_available");
	} else {
		CHECK(m.n_inst == 0 && m.n_upd == 0);
		keys("da"); CHECK(V().screen == RH_S_INSTALLED && V().count == 0);
		shot("5d_installed_empty_file");
	}
	rh_ui_free();
}

int main(int argc, char **argv)
{
	char assets[512];
	if (argc < 2) { fprintf(stderr, "usage: %s repo_root [shots_dir]\n", argv[0]); return 2; }
	shots = argc > 2 ? argv[2] : NULL;
	snprintf(assets, sizeof assets, "%s/ui/assets", argv[1]);
	setenv("SDL_VIDEODRIVER", "dummy", 0);
	if (SDL_Init(SDL_INIT_VIDEO) || !(scr = SDL_SetVideoMode(240, 240, 32, SDL_SWSURFACE))) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 2; }
	versions();
	real_catalog(argv[1], assets);
	fixture(argv[1], assets);
	scenario(argv[1], assets, "populated"); scenario(argv[1], assets, "noupdates"); scenario(argv[1], assets, "empty");
	SDL_Quit();
	printf("%d checks, %d failed\n", checks, fails);
	return fails != 0;
}
