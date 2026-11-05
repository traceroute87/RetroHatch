/* Phase 4B UI test: navigation + palette checks on the real 240x240 surface.
 *   ui_nav_test <repo_root> [shots_dir]
 * With shots_dir, also writes one BMP per screen. Uses SDL's dummy video. */
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <SDL/SDL.h>
#include "../ui/rh_ui.h"
#include "../platforms/nano/rh_install.h"

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

static void keys(const char *s)   /* u d l r a b; x = page up, y = page down */
{
	for (; *s; s++) rh_ui_key(*s == 'u' ? RH_K_UP : *s == 'd' ? RH_K_DOWN : *s == 'l' ? RH_K_LEFT : *s == 'r' ? RH_K_RIGHT : *s == 'a' ? RH_K_A : *s == 'x' ? RH_K_PGUP : *s == 'y' ? RH_K_PGDN : RH_K_B);
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
	CHECK(px(120, 66) == 0xE9A23B);                     /* first row (TaraFi) selected, below the category chip */
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

/* ---- first usable slice: Browse -> App Details -> Install Preview -> Back (read-only; DEV fixtures labeled) ---- */
static int count_px(int x0, int y0, int x1, int y1, unsigned c)
{
	int x, y, n = 0;
	for (y = y0; y < y1; y++) for (x = x0; x < x1; x++) n += px(x, y) == c;
	return n;
}

static void open_app(const rh_model *m, const char *id)   /* Home -> Discover -> Details of id */
{
	int want = app_idx(m, id), i;
	keys("a");
	for (i = 0; i < want; i++) keys("d");
	keys("a");
}

static void preview(const char *root, const char *assets)
{
	static rh_model m, real; char cat[512], st[512]; rh_ui_view v; int i;
	char t[96], why[64];
	/* the installer's own name checks decide the target; nothing is invented */
	CHECK(rh_plan_target("fx-app-1", "1.2.3", "fx1_funkey-s.opk", t, sizeof t, why, sizeof why) && !strcmp(t, "/mnt/Applications/fx1_funkey-s.opk"));
	CHECK(!rh_plan_target("fx-app-1", "1.2.3", "", t, sizeof t, why, sizeof why) && !strcmp(why, "No install file name in catalog"));
	CHECK(!rh_plan_target("fx-app-1", "1.2.3", "../x.opk", t, sizeof t, why, sizeof why) && !strcmp(why, "Install file name not allowed"));
	CHECK(!rh_plan_target("fx-app-1", "1.2.3", "retrohatch.opk", t, sizeof t, why, sizeof why));   /* protected name */
	CHECK(!rh_plan_target("Bad Id", "1.2.3", "a.opk", t, sizeof t, why, sizeof why) && !rh_plan_target("a", "1 2", "a.opk", t, sizeof t, why, sizeof why));

	/* the shipped catalog is never a fixture; the fixture catalog always says so */
	snprintf(cat, sizeof cat, "%s/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/nostate", root);
	rh_model_load(&real, cat, st);
	CHECK(!real.dev_fixture);
	for (i = 0; i < real.n_apps; i++) CHECK(strncmp(real.apps[i].id, "fx-", 3) != 0);
	snprintf(cat, sizeof cat, "%s/tests/ui_fixture/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/state", root);
	rh_model_load(&m, cat, st);
	CHECK(m.dev_fixture && !strcmp(m.apps[app_idx(&m, "fx-app-1")].category, "application"));
	CHECK(rh_ui_init(assets, &m) == 0);

	/* without a planner (DEV/ops tests) the bar stays inert, exactly as before */
	rh_ui_set_planner(NULL);
	open_app(&m, "fx-app-3"); v = V();
	CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_INSTALL_SOON); keys("a"); CHECK(V().screen == RH_S_DETAILS && V().depth == 2);
	keys("bb");
	rh_ui_set_planner(rh_plan_target);

	/* Browse: DEV title, installed status, long name */
	keys("a"); shot("slice_1_browse"); CHECK(V().screen == RH_S_DISCOVER);
	CHECK(count_px(156, 6, 190, 26, 0xFFF0D2) > 10);         /* "[DEV]" tag: title text reaches past where plain "Discover" ends (x 150) */
	keys("b");
	/* Details of an installed app with an update pending -> Update Preview */
	open_app(&m, "fx-app-1"); v = V();
	CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_UPDATE); shot("slice_2_details_update");
	CHECK(px(226, 195) == 0xE9A23B);                         /* the bar is focusable now */
	CHECK(count_px(10, 80, 230, 130, 0xE87555) > 20);        /* "DEV FIXTURE. Not an approved app." banner on the page */
	keys("a"); v = V(); CHECK(v.screen == RH_S_CONFIRM && v.depth == 3); shot("slice_3_update_preview");
	keys("d"); CHECK(V().screen == RH_S_CONFIRM);            /* no second action to take */
	keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.depth == 2 && v.action == RH_ACT_UPDATE);   /* Back */
	keys("bb");
	/* New install, long name */
	open_app(&m, "fx-app-3"); CHECK(V().action == RH_ACT_INSTALL_SOON); shot("slice_4_details_long_name");
	keys("a"); CHECK(V().screen == RH_S_CONFIRM); shot("slice_5_install_preview");
	keys("b"); CHECK(V().screen == RH_S_DETAILS); keys("bb");
	/* Missing install file name: preview says the target is unknown */
	open_app(&m, "fx-app-4"); keys("a"); CHECK(V().screen == RH_S_CONFIRM); shot("slice_6_preview_no_target");
	keys("bbb");
	/* Installed, current: nothing to preview */
	open_app(&m, "fx-app-2"); CHECK(V().action == RH_ACT_INSTALLED); keys("a"); CHECK(V().screen == RH_S_DETAILS);
	rh_ui_free();

	/* Empty catalog */
	snprintf(cat, sizeof cat, "%s/tests/ui_fixture/no-such-catalog", root);
	rh_model_load(&m, cat, st);
	CHECK(m.n_apps == 0 && !m.dev_fixture && rh_ui_init(assets, &m) == 0);
	keys("a"); CHECK(V().screen == RH_S_DISCOVER && V().count == 0); shot("slice_7_empty_catalog");
	keys("a"); CHECK(V().screen == RH_S_DISCOVER);
	CHECK(count_px(156, 6, 190, 26, 0xFFF0D2) == 0);          /* real (non-fixture) catalogs carry no DEV tag */
	rh_ui_free();
	rh_ui_set_planner(NULL);
}

/* ---- UNAPPROVED candidates: read-only, labeled, never installable ---- */
static void candidates(const char *root, const char *assets)
{
	static rh_model m; char cat[512], st[512], f[512]; rh_ui_view v; int i, n_apps;
	snprintf(st, sizeof st, "%s/tests/ui_fixture/nostate", root);
	/* the real snapshot beside the real (approved) catalog */
	snprintf(cat, sizeof cat, "%s/catalog", root); snprintf(f, sizeof f, "%s/candidates/rg-nano.json", root);
	rh_model_load(&m, cat, st); n_apps = m.n_apps; rh_model_load_candidates(&m, f);
	CHECK(m.n_cands > 12 && m.n_apps == n_apps);   /* the one inventory snapshot has no fixed limit; approved apps untouched */
	for (i = 0; i < m.n_cands; i++) CHECK(m.cands[i].name[0] && m.cands[i].id[0]);
	for (i = 0; i < 10; i++) CHECK(m.cands[i].repo[0] && m.cands[i].sig_ok && m.cands[i].size > 0 && m.cands[i].claim[0]);   /* the first ten are the original verified repository entries */
	for (i = 0; i < m.n_cands; i++) { int j; for (j = i + 1; j < m.n_cands; j++) CHECK(strcmp(m.cands[i].id, m.cands[j].id) != 0); }   /* one entry per application, not per repository */
	CHECK(rh_ui_init(assets, &m) == 0);
	rh_ui_set_planner(rh_plan_target);                      /* even with the preview planner, a candidate has no install path */
	keys("a"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.count == n_apps + m.n_cands); shot("cand_1_discover");
	for (i = 0; i < n_apps; i++) keys("d");
	CHECK(V().sel == n_apps && V().sel_visible);
	shot("cand_2_discover_first_candidate");
	keys("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.app == 0 && v.action == RH_ACT_NONE); shot("cand_3_details_top");
	keys("a"); keys("a"); CHECK(V().screen == RH_S_CAND && V().depth == 2);        /* A does nothing: no install, download or preview */
	for (i = 0; i < 40; i++) keys("d");
	CHECK(V().scroll > 0); shot("cand_4_details_bottom");
	for (i = 0; i < 40; i++) keys("u");
	CHECK(V().scroll == 0);
	keys("b"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.sel == n_apps);
	for (i = 1; i < m.n_cands; i++) { keys("d"); CHECK(V().sel_visible); }
	shot("cand_5_discover_last_candidate");
	keys("a"); CHECK(V().screen == RH_S_CAND && V().app == m.n_cands - 1); shot("cand_6_details_last");
	for (i = 0; i < 3; i++) { keys("a"); CHECK(V().screen == RH_S_CAND); }
	keys("bb"); CHECK(V().screen == RH_S_HOME);
	rh_ui_set_planner(NULL);
	rh_ui_free();

	/* odd metadata over the fixture catalog (which has an approved app whose source one entry repeats) */
	snprintf(cat, sizeof cat, "%s/tests/ui_fixture/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/state", root);
	snprintf(f, sizeof f, "%s/tests/ui_fixture/candidates-edge.json", root);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, f);
	CHECK(m.n_cands == 2 && !strcmp(m.cands[0].name, "Bare Minimum"));              /* dup repo, approved source, bad approval/hardware, no repo: all dropped */
	CHECK(m.cands[0].version[0] == 0 && m.cands[0].size == 0 && !m.cands[0].sig_ok && m.cands[0].claim[0] == 0);
	CHECK(strlen(m.cands[1].name) <= 47 && m.cands[1].more == 11 && m.cands[1].zipped);
	CHECK(m.cands[1].cat == RH_CAT_UTIL && m.cands[1].cat_basis[0]);                  /* reviewed category, with its basis */
	CHECK(m.cands[0].cat == RH_CAT_OTHER && !m.cands[0].cat_basis[0]);                /* unknown category id: ignored, derived instead */
	CHECK(rh_ui_init(assets, &m) == 0);
	keys("a"); for (i = 0; i < m.n_apps; i++) keys("d");
	keys("a"); CHECK(V().screen == RH_S_CAND); shot("cand_7_minimal_metadata");
	keys("bd"); CHECK(V().sel_visible); shot("cand_8_discover_long_name");
	keys("a"); CHECK(V().screen == RH_S_CAND); shot("cand_9_long_values");
	for (i = 0; i < 40; i++) keys("d");
	shot("cand_10_long_values_bottom");
	rh_ui_free();

	/* no approved apps at all: candidates alone fill Discover; a missing file adds nothing and keeps the old empty state */
	snprintf(cat, sizeof cat, "%s/tests/ui_fixture/no-such-catalog", root);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, f);
	CHECK(m.n_apps == 0 && m.n_cands == 3);   /* "Already Approved" is only a duplicate when its catalog entry exists */
	CHECK(rh_ui_init(assets, &m) == 0);
	keys("a"); v = V(); CHECK(v.count == 3 && v.sel == 0); shot("cand_11_only_candidates");
	keys("a"); CHECK(V().screen == RH_S_CAND && V().app == 0);
	rh_ui_free();
	snprintf(f, sizeof f, "%s/tests/ui_fixture/no-such-candidates.json", root);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, f);
	CHECK(m.n_cands == 0 && rh_ui_init(assets, &m) == 0);
	keys("a"); CHECK(V().count == 0); keys("a"); CHECK(V().screen == RH_S_DISCOVER);
	rh_ui_free();
}

/* ---- categories: derived from existing text, never guessed; Discover filter with LEFT/RIGHT ---- */
static int find_cand(const rh_model *m, const char *name)
{
	int i;
	for (i = 0; i < m->n_cands; i++) if (!strcmp(m->cands[i].name, name)) return i;
	return -1;
}

static int n_cat(const rh_model *m, int c)
{
	int i, n = 0;
	for (i = 0; i < m->n_apps; i++) n += m->apps[i].cat == (rh_cat)c;
	for (i = 0; i < m->n_cands; i++) n += m->cands[i].cat == (rh_cat)c;
	return n;
}

static void categories(const char *root, const char *assets)
{
	static rh_model m; char cat[512], st[512], f[512]; rh_ui_view v; int i, j, sudo, games;
	CHECK(rh_categorize("TaraFi", "Music player.", NULL) == RH_CAT_MEDIA);
	CHECK(rh_categorize("X", "A puzzle game", NULL) == RH_CAT_GAMES && rh_categorize("X", "GB emulator core", NULL) == RH_CAT_EMU);
	CHECK(rh_categorize("X", "ROM manager and viewer", NULL) == RH_CAT_UTIL && rh_categorize("X", "J2ME runtime", NULL) == RH_CAT_ENGINE);
	CHECK(rh_categorize("X", "Plays things", "arcade-game") == RH_CAT_GAMES);          /* topics count; hyphens split words */
	CHECK(rh_categorize("X", "A Sokoban engine", "2d-game") == RH_CAT_OTHER);          /* evidence for two categories: not enough */
	CHECK(rh_categorize("", "", "") == RH_CAT_OTHER && rh_categorize(NULL, NULL, NULL) == RH_CAT_OTHER);
	CHECK(rh_categorize("X", "gamecube gamer toolbox mediaplayer", NULL) == RH_CAT_OTHER);   /* whole words only */
	CHECK(rh_categorize("X", "supercalifragilisticexpialidocious game", NULL) == RH_CAT_GAMES);
	CHECK(!strcmp(rh_cat_name(RH_CAT_ENGINE), "Engines & Tools") && !strcmp(rh_cat_name(RH_CAT_ALL), "All") && !strcmp(rh_cat_name((rh_cat)99), "Other"));

	snprintf(cat, sizeof cat, "%s/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/nostate", root); snprintf(f, sizeof f, "%s/candidates/rg-nano.json", root);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, f);
	for (i = 0; i < m.n_apps; i++) {                                                   /* approved apps: derived from their own description */
		if (!strcmp(m.apps[i].id, "tarafi")) CHECK(m.apps[i].cat == RH_CAT_MEDIA);
		if (!strcmp(m.apps[i].id, "kishmish-nano")) CHECK(m.apps[i].cat == RH_CAT_GAMES);
	}
	CHECK(m.cands[find_cand(&m, "j2me-funkey-rgnano")].cat == RH_CAT_ENGINE && m.cands[find_cand(&m, "KeyCraft")].cat == RH_CAT_GAMES);
	CHECK(m.cands[find_cand(&m, "meleelight")].cat == RH_CAT_OTHER && m.cands[find_cand(&m, "XASH3DFS")].cat == RH_CAT_OTHER);   /* no evidence: Other */
	CHECK(m.cands[find_cand(&m, "Cglpsdl1")].cat == RH_CAT_OTHER && !m.cands[find_cand(&m, "Cglpsdl1")].cat_basis[0]);          /* games AND library: conflicting, Other */
	CHECK(m.cands[find_cand(&m, "NanoCraft")].cat == RH_CAT_GAMES && m.cands[find_cand(&m, "NanoCraft")].cat_basis[0]);          /* reviewed, evidence kept */
	CHECK(m.cands[find_cand(&m, "Funkoban")].cat == RH_CAT_GAMES && m.cands[find_cand(&m, "picoarch")].cat == RH_CAT_EMU && m.cands[find_cand(&m, "picoarch")].cat_basis[0]);
	CHECK(!m.cands[find_cand(&m, "KeyCraft")].cat_basis[0]);                           /* derived from its own words: no review entry */
	{ int k = 0; for (i = 0; i < m.n_cands; i++) if (m.cands[i].cat != RH_CAT_UTIL) m.cands[k++] = m.cands[i]; m.n_cands = k; }   /* the inventory has Utilities now: drop them so the empty-filter case stays covered */
	CHECK(n_cat(&m, RH_CAT_UTIL) == 0);                                                /* an empty category exists */
	games = n_cat(&m, RH_CAT_GAMES); sudo = find_cand(&m, "SuDokuL");
	CHECK(games >= 2 && sudo >= 0 && m.cands[sudo].cat == RH_CAT_GAMES);

	CHECK(rh_ui_init(assets, &m) == 0);
	keys("a"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.count == m.n_apps + m.n_cands); shot("cat_1_all");
	for (i = 0; i < m.n_apps + find_cand(&m, "SuDokuL"); i++) keys("d");               /* onto SuDokuL */
	keys("a"); CHECK(V().screen == RH_S_CAND && !strcmp(m.cands[V().app].name, "SuDokuL")); keys("b");
	keys("r"); v = V(); CHECK(v.count == games && v.screen == RH_S_DISCOVER && v.sel_visible); shot("cat_2_games");
	keys("a"); CHECK(V().screen == RH_S_CAND && !strcmp(m.cands[V().app].name, "SuDokuL"));   /* same entry kept its place under the filter */
	keys("b"); CHECK(V().count == games);                                              /* filter survives details and back */
	CHECK(V().sel > 0 || games == 1);
	keys("rrr"); v = V(); CHECK(v.count == n_cat(&m, RH_CAT_UTIL) && v.count == 0 && v.sel == 0); shot("cat_3_empty_utilities");   /* Emulators, Media, Utilities */
	keys("a"); keys("d"); keys("u"); CHECK(V().screen == RH_S_DISCOVER && V().count == 0);   /* nothing to open or move */
	keys("lll"); CHECK(V().count == games && V().sel == 0);                            /* entry not remembered while hidden: top of list */
	keys("l"); CHECK(V().count == m.n_apps + m.n_cands);                               /* back to All */
	keys("l"); CHECK(V().count == n_cat(&m, RH_CAT_OTHER)); shot("cat_4_other");        /* wraps to the last category */
	keys("r"); CHECK(V().count == m.n_apps + m.n_cands);
	for (j = 0; j < 7; j++) keys("r");
	CHECK(V().count == m.n_apps + m.n_cands);                                          /* a full cycle returns to All */
	for (i = 0, j = 0; i < RH_CAT_N; i++) j += n_cat(&m, i) * (i != RH_CAT_ALL);
	CHECK(j == m.n_apps + m.n_cands);                                                  /* every entry has exactly one category */
	/* category changes nothing else: approvals, actions and read-only pages stay as they were */
	keys("r"); keys("r"); keys("l"); keys("l");                                         /* All -> Games -> Emulators -> Games -> All */
	CHECK(V().count == m.n_apps + m.n_cands);
	for (i = 0; i < 30; i++) keys("u");
	keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_UNAVAILABLE);   /* approved catalog entry: still not installable */
	rh_ui_free();
}

/* ---- FunKey wiki listings: the whole inventory, no fixed limit, all UNAPPROVED and read-only ---- */
/* Page keys (x up, y down) and the Discover position counter, on the real catalog + the real candidate snapshot */
static unsigned chip_hash(void)   /* the category chip row: y 37..58 */
{
	unsigned h = 2166136261u; int x, y;
	for (y = 37; y < 59; y++) for (x = 8; x < 232; x++) h = (h ^ px(x, y)) * 16777619u;
	return h;
}

static void paging(const char *root, const char *assets)
{
	static rh_model m; char cat[512], st[512], f[512]; rh_ui_view v; int i, n, sc, max, last = 0, steps = 0; unsigned h0;
	snprintf(cat, sizeof cat, "%s/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/nostate", root); snprintf(f, sizeof f, "%s/candidates/rg-nano.json", root);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, f); n = m.n_apps + m.n_cands;
	CHECK(find_cand(&m, "TaraFi") < 0 && find_cand(&m, "Kishmish Nano") < 0 && n == 129);   /* with the catalog loaded, its TaraFi and Kishmish rows replace the candidates (same source URL) */
	{ int a, k = 0; for (a = 0; a < m.n_apps; a++) k += !strcmp(m.apps[a].name, "TaraFi") || !strcmp(m.apps[a].name, "Kishmish Nano"); CHECK(k == 2); }
	{ static rh_model b; snprintf(cat, sizeof cat, "%s/tests/ui_fixture/no-such-catalog", root); rh_model_load(&b, cat, st); rh_model_load_candidates(&b, f);   /* the Nano today: no signed catalog */
	  CHECK(b.n_apps == 0 && b.n_cands == 129 && find_cand(&b, "TaraFi") >= 0 && b.cands[find_cand(&b, "TaraFi")].cat == RH_CAT_MEDIA
	        && find_cand(&b, "Kishmish Nano") >= 0 && b.cands[find_cand(&b, "Kishmish Nano")].cat == RH_CAT_GAMES && !b.cands[find_cand(&b, "Kishmish Nano")].sig_ok); }
	snprintf(cat, sizeof cat, "%s/catalog", root);
	CHECK(n > 100 && rh_ui_init(assets, &m) == 0);
	keys("a"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.count == n && v.sel == 0);
	rh_ui_draw(scr); h0 = chip_hash(); shot("pg_1_discover_counter_1");
	keys("y"); v = V(); CHECK(v.sel == 3 && v.sel_visible);                    /* three visible rows per press */
	CHECK(chip_hash() != h0 || (rh_ui_draw(scr), chip_hash() != h0));         /* the counter text changed */
	keys("yy"); CHECK(V().sel == 9); keys("x"); CHECK(V().sel == 6); keys("xxxx"); CHECK(V().sel == 0 && V().scroll == 0);   /* clamped at the start */
	keys("x"); CHECK(V().sel == 0);
	for (i = 0; i < 15; i++) keys("y");
	keys("d"); v = V(); CHECK(v.sel == 46 && v.sel_visible); shot("pg_2_discover_counter_47");      /* "47/129" */
	keys("a"); CHECK(V().screen == RH_S_CAND); keys("b"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.sel == 46 && v.sel_visible);   /* Back keeps the selection */
	keys("y"); CHECK(V().sel == 49); keys("ll"); v = V(); CHECK(v.count < n);  /* category switch: counter now counts that category */
	keys("rr"); CHECK(V().count == n);
	for (; steps < 100 && V().sel != n - 1; steps++) keys("y");
	v = V(); CHECK(v.sel == n - 1 && v.sel_visible && steps <= (n + 2) / 3); shot("pg_3_discover_counter_end");   /* clamped at the end */
	keys("yy"); CHECK(V().sel == n - 1);
	keys("r"); v = V(); CHECK(v.count < n && v.sel < v.count); shot("pg_4_games_counter");        /* Willy is also in Games: the selection stays on it, now counted as 67/67 */
	for (i = 0; i < 100; i++) keys("y");
	v = V(); CHECK(v.sel == v.count - 1 && v.sel_visible); shot("pg_5_games_counter_end");
	for (i = 0; i < 100; i++) keys("x");
	CHECK(V().sel == 0);
	keys("yy"); keys("a"); v = V(); CHECK(v.screen == RH_S_CAND);   /* candidate page (Games starts with approved apps: skip them); one screen per press, clamped both ends */
	for (i = 0; i < 200; i++) keys("d");
	max = V().scroll; CHECK(max > 300); keys("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"); CHECK(V().scroll == 0);
	keys("y"); sc = V().scroll; CHECK(sc > 100 && sc < 177); shot("pg_6_details_page_1");
	keys("y"); CHECK(V().scroll > sc && V().scroll > 2 * 100); shot("pg_7_details_page_2");
	for (i = 0; i < 30; i++) { last = V().scroll; keys("y"); }
	CHECK(V().scroll == max && last <= max); keys("x"); CHECK(V().scroll < max); shot("pg_8_details_page_back");
	keys("b"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.sel == 6);
	keys("b"); CHECK(V().screen == RH_S_HOME); keys("yx"); CHECK(V().screen == RH_S_HOME && V().sel == 0);   /* Home ignores the page keys */
	rh_ui_free();
}

static void wiki_listings(const char *root, const char *assets)
{
	static rh_model m; char cat[512], st[512], f[512], tmp[] = "/tmp/rh_wiki_XXXXXX"; rh_ui_view v; int i, j, n_apps, n_wiki = 0, n_unver = 0, n_ver = 0, fd, last;
	static const char *const OLD[] = {"j2me-funkey-rgnano", "NanoCraft", "Funkoban", "Cglpsdl1", "picoarch", "XASH3DFS", "meleelight", "SuDokuL", "TriSpace", "KeyCraft"};
	FILE *fp;
	snprintf(cat, sizeof cat, "%s/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/nostate", root);
	snprintf(f, sizeof f, "%s/candidates/rg-nano.json", root);
	rh_model_load(&m, cat, st); n_apps = m.n_apps; rh_model_load_candidates(&m, f);
	CHECK(m.n_cands > 12 && m.n_apps == n_apps);                                        /* one file, past the old 12-row limit; approved apps untouched */
	for (i = 0; i < 10; i++) CHECK(find_cand(&m, OLD[i]) >= 0);                         /* nothing unique to the existing source was dropped */
	CHECK(m.cands[find_cand(&m, "Funkoban")].wiki && m.cands[find_cand(&m, "Cglpsdl1")].wiki);   /* matched, not duplicated */
	for (i = 0, j = 0; i < m.n_cands; i++) j += !strcmp(m.cands[i].name, "Funkoban") || !strcmp(m.cands[i].name, "Cglpsdl1");
	CHECK(j == 2);
	for (i = 0; i < m.n_cands; i++) {
		const rh_cand *c = &m.cands[i]; int k;
		CHECK(c->name[0] && c->id[0]);
		for (k = i + 1; k < m.n_cands; k++) CHECK(strcmp(c->id, m.cands[k].id) != 0);   /* every application keeps its own identity */
		if (!c->wiki) continue;
		n_wiki++;
		CHECK(c->cat >= RH_CAT_GAMES && c->cat <= RH_CAT_OTHER);
		if (c->sig_ok) n_ver++;
		else { n_unver++; CHECK(c->dl[0]); }                                             /* an unverified listing says why */
	}
	CHECK(n_wiki >= 46 && n_ver > 0 && n_unver > 0 && n_wiki == n_ver + n_unver);
	for (i = 0, j = 0; i < RH_CAT_N; i++) j += n_cat(&m, i) * (i != RH_CAT_ALL);
	CHECK(j == n_apps + m.n_cands);                                                      /* one category each */

	CHECK(rh_ui_init(assets, &m) == 0);
	rh_ui_set_planner(rh_plan_target);                                                  /* even with a planner, no install, download or preview */
	keys("a"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.count == n_apps + m.n_cands);
	for (i = 0; i < n_apps + 10; i++) keys("d");                                         /* first wiki-only row */
	CHECK(V().sel_visible); shot("wiki_1_browse");
	last = v.count - 1;
	for (i = n_apps + 10; i < last; i++) { keys("d"); CHECK(V().sel_visible); }          /* every row reachable and on screen */
	CHECK(V().sel == last); shot("wiki_2_browse_last");
	keys("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.app == m.n_cands - 1 && v.action == RH_ACT_NONE);
	keys("a"); keys("a"); CHECK(V().screen == RH_S_CAND && V().depth == 2);              /* A does nothing */
	keys("bb"); CHECK(V().screen == RH_S_HOME);
	rh_ui_free();

	{   /* a verified listing, an unverified one, a long name: details pages */
		const char *pick[][2] = {{"Gambatte", "wiki_3_details_verified"}, {"Clock App", "wiki_4_details_unverified"}, {"FinalBurn Alpha 2012", "wiki_5_details_long_name"}, {"KeyKalc", "wiki_6_details_no_file"}};
		for (j = 0; j < 4; j++) {
			int idx = find_cand(&m, pick[j][0]), k;
			CHECK(idx >= 0 && m.cands[idx].wiki);
			CHECK(rh_ui_init(assets, &m) == 0);
			keys("a"); for (k = 0; k < n_apps + idx; k++) keys("d");
			keys("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.app == idx); shot(pick[j][1]);
			if (j == 1) { for (k = 0; k < 8; k++) keys("d"); shot("wiki_4a_details_unverified_middle"); }
			for (k = 0; k < 40; k++) keys("d");
			CHECK(V().scroll > 0); if (j == 1) shot("wiki_4b_details_unverified_bottom");
			rh_ui_free();
		}
		CHECK(!m.cands[find_cand(&m, "Clock App")].sig_ok && m.cands[find_cand(&m, "Gambatte")].sig_ok);
	}
	{   /* inventory entries that are not wiki listings: a ZIP collection member, an uninspected package, a source-only entry, a core, a system add-on */
		const char *pick[] = {"Checkers", "Handheld Link", "FK-TD", "Gambatte (SDL Retro core)", "GMenu2X", "Match3", "Super Square Bros", "2048"}, *tag[] = {"zip_member", "unverified", "source_only", "core", "system", "blit_match3", "blit_longname", "blit_2048"}, *lead[] = {"", "Package not inspected", "Source only", "Emulator core", "System add-on", "32blit game", "32blit game", "32blit game"};
		for (j = 0; j < 8; j++) {
			int idx = find_cand(&m, pick[j]), k; char nm[64];
			CHECK(idx >= 0 && !strncmp(m.cands[idx].desc, lead[j], strlen(lead[j])));        /* the label is the first thing the description says */
			CHECK(rh_ui_init(assets, &m) == 0);
			keys("a"); for (k = 0; k < n_apps + idx; k++) keys("d");
			keys("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.app == idx && v.action == RH_ACT_NONE);
			snprintf(nm, sizeof nm, "inv_%d_%s_details", j + 1, tag[j]); shot(nm);
			for (k = 0; k < 40; k++) keys("d");
			snprintf(nm, sizeof nm, "inv_%d_%s_bottom", j + 1, tag[j]); shot(nm);
			rh_ui_free();
		}
		CHECK(m.cands[find_cand(&m, "Checkers")].sig_ok && m.cands[find_cand(&m, "Checkers")].zipped && !m.cands[find_cand(&m, "Checkers")].wiki);
		CHECK(m.cands[find_cand(&m, "Match3")].sig_ok && m.cands[find_cand(&m, "Match3")].zipped && !m.cands[find_cand(&m, "Match3")].wiki && m.cands[find_cand(&m, "Match3")].cat == RH_CAT_GAMES);   /* 32blit game: ZIP member, games, no approval */
		CHECK(!m.cands[find_cand(&m, "FK-TD")].sig_ok && !m.cands[find_cand(&m, "FK-TD")].pkg_name[0] && !m.cands[find_cand(&m, "Handheld Link")].sig_ok);
	}
	{   /* every candidate page opens, scrolls to its end and comes back under the sanitizers: row buffers and text wrapping stay in bounds */
		int idx, k;
		for (idx = 0; idx < m.n_cands; idx++) {
			CHECK(rh_ui_init(assets, &m) == 0);
			keys("a"); for (k = 0; k < n_apps + idx; k++) keys("d");
			keys("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.app == idx && v.action == RH_ACT_NONE);
			for (k = 0; k < 60; k++) keys("d");
			for (k = 0; k < 60; k++) keys("u");
			CHECK(V().scroll == 0); keys("b"); CHECK(V().screen == RH_S_DISCOVER);
			rh_ui_free();
		}
	}
	{   /* category filter over the combined list: Emulators holds the most wiki entries */
		CHECK(rh_ui_init(assets, &m) == 0);
		keys("a"); keys("rr"); v = V(); CHECK(v.count == n_cat(&m, RH_CAT_EMU) && v.count > 12); shot("wiki_7_filter_emulators");
		for (i = 1; i < v.count; i++) { keys("d"); CHECK(V().sel_visible); }
		shot("wiki_8_filter_emulators_last");
		rh_ui_free();
	}

	/* no arbitrary cap: 300 distinct ids load, a repeated id and an entry without id or repo do not */
	fd = mkstemp(tmp); CHECK(fd >= 0);
	fp = fdopen(fd, "w"); fprintf(fp, "{\"candidates\":[");
	for (i = 0; i < 300; i++) fprintf(fp, "%s{\"id\":\"t%d\",\"name\":\"Test %d\",\"approval\":\"unapproved\",\"hardware_test\":\"none\"}", i ? "," : "", i, i);
	fprintf(fp, ",{\"id\":\"t7\",\"name\":\"Repeat\",\"approval\":\"unapproved\",\"hardware_test\":\"none\"},{\"name\":\"Nameless\",\"approval\":\"unapproved\",\"hardware_test\":\"none\"}]}");
	fclose(fp);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, tmp);
	CHECK(m.n_cands == 300);
	rh_model_add_candidates(&m, tmp); CHECK(m.n_cands == 300);                           /* adding the same file again changes nothing */
	CHECK(rh_ui_init(assets, &m) == 0);
	keys("a"); CHECK(V().count == n_apps + 300);
	for (i = 0; i < n_apps + 299; i++) keys("d");
	CHECK(V().sel_visible); keys("a"); CHECK(V().screen == RH_S_CAND && V().app == 299);
	rh_ui_free();
	fp = fopen(tmp, "w"); fprintf(fp, "{\"candidates\":[{\"id\":\"big\",\"name\":\"Big\",\"description\":\"");   /* over 1 MB: refused whole, never half-read */
	for (i = 0; i < (1 << 20); i++) fputc('x', fp);
	fprintf(fp, "\",\"approval\":\"unapproved\",\"hardware_test\":\"none\"}]}"); fclose(fp);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, tmp); CHECK(m.n_cands == 0);
	remove(tmp);
	rh_ui_set_planner(NULL);
}

/* ---- candidate icons: shown when the file is there and 32x32, never anything else (synthetic icons; real ones need a recorded right to redistribute) ---- */
static unsigned long screen_hash(void)
{
	unsigned long h = 1469598103934665603UL; int x, y;
	rh_ui_draw(scr);
	for (y = 0; y < 240; y++) for (x = 0; x < 240; x++) h = (h ^ px(x, y)) * 1099511628211UL;
	return h;
}

static void icons(const char *root, const char *assets)
{
	static rh_model m; char cat[512], st[512], f[512], tmp[] = "/tmp/rh_icon_XXXXXX", tmp2[] = "/tmp/rh_iconj_XXXXXX", big_bmp[64], text_file[64], none[64]; int i, n_icon = 0, fd, k;
	unsigned long with, without, bogus; FILE *fp; SDL_Surface *s;
	snprintf(cat, sizeof cat, "%s/catalog", root); snprintf(st, sizeof st, "%s/tests/ui_fixture/nostate", root);
	/* the shipped snapshots: an icon is named only when its file is there (icons ship only with a recorded right to redistribute them) */
	rh_model_load(&m, cat, st);
	snprintf(f, sizeof f, "%s/candidates/rg-nano.json", root); rh_model_load_candidates(&m, f);
	CHECK(m.n_cands >= 84);   /* every inventory entry that is a browser entry */
	for (i = 0; i < m.n_cands; i++) if (m.cands[i].icon[0]) {
		n_icon++; fp = fopen(m.cands[i].icon, "rb"); CHECK(fp != NULL); if (fp) fclose(fp);
	}
	CHECK(n_icon == 2);                                                                          /* exactly the two cleared icons are named */
	CHECK(find_cand(&m, "Znax") >= 0 && find_cand(&m, "Rubido") >= 0 && m.cands[find_cand(&m, "Znax")].icon[0] && m.cands[find_cand(&m, "Rubido")].icon[0]);
	CHECK(!m.cands[find_cand(&m, "Blips")].icon[0] && !m.cands[find_cand(&m, "Funkoban")].icon[0]);   /* restricted and unclear icons keep the package glyph */
	CHECK(rh_ui_init(assets, &m) == 0);
	{
		static const char *const SHOW[] = {"Rubido", "Znax", "Blips"};
		for (k = 0; k < 3; k++) {
			char nm[64]; keys("a"); for (i = 0; i < m.n_apps + find_cand(&m, SHOW[k]); i++) keys("d");
			snprintf(nm, sizeof nm, "icon_real_%d_%s_row", k + 1, SHOW[k]); shot(nm);
			keys("a"); CHECK(V().screen == RH_S_CAND && V().action == RH_ACT_NONE); snprintf(nm, sizeof nm, "icon_real_%d_%s_details", k + 1, SHOW[k]); shot(nm);
			keys("bbb"); CHECK(V().screen == RH_S_HOME);
		}
	}
	rh_ui_free();

	/* the feature, on synthetic icons made for these tests */
	snprintf(f, sizeof f, "%s/tests/ui_fixture/candidates-icons.json", root);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, f);
	CHECK(m.n_cands == 4 && m.cands[0].icon[0] && m.cands[1].icon[0] && m.cands[2].icon[0] && !m.cands[3].icon[0]);
	CHECK(rh_ui_init(assets, &m) == 0);
	keys("a"); for (i = 0; i < m.n_apps; i++) keys("d");                                         /* first candidate: Icon Alpha */
	CHECK(V().sel_visible); shot("icon_1_browse_selected");
	with = screen_hash(); keys("a"); CHECK(V().screen == RH_S_CAND && V().app == 0 && V().action == RH_ACT_NONE); shot("icon_2_details_alpha"); keys("b");
	keys("d"); shot("icon_3_browse_beta"); keys("d"); shot("icon_4_browse_missing_file");         /* a named but missing file: glyph, no crash */
	keys("a"); shot("icon_5_details_missing_file"); keys("b"); keys("d"); keys("a"); CHECK(V().screen == RH_S_CAND && V().app == 3); shot("icon_6_details_no_icon"); keys("b"); rh_ui_free();
	/* the same screen with the icon names removed differs: the pictures really are drawn */
	for (i = 0; i < m.n_cands; i++) m.cands[i].icon[0] = 0;
	CHECK(rh_ui_init(assets, &m) == 0); keys("a"); for (i = 0; i < m.n_apps; i++) keys("d");
	without = screen_hash(); CHECK(with != without); rh_ui_free();
	/* missing file, wrong size and not-an-image all fall back to the glyph, which is exactly the no-icon screen */
	fd = mkstemp(tmp); CHECK(fd >= 0); close(fd); remove(tmp);
	snprintf(big_bmp, sizeof big_bmp, "%s.big", tmp); snprintf(text_file, sizeof text_file, "%s.txt", tmp); snprintf(none, sizeof none, "%s.none", tmp);
	s = SDL_CreateRGBSurface(SDL_SWSURFACE, 64, 64, 32, 0, 0, 0, 0); CHECK(s != NULL); SDL_FillRect(s, NULL, 0xff00ff); SDL_SaveBMP(s, big_bmp); SDL_FreeSurface(s);   /* a 64x64 picture */
	fp = fopen(text_file, "wb"); fputs("this is not an image", fp); fclose(fp);
	for (k = 0; k < 3; k++) {
		const char *p = k == 0 ? big_bmp : k == 1 ? text_file : none;
		for (i = 0; i < m.n_cands; i++) snprintf(m.cands[i].icon, sizeof m.cands[i].icon, "%s", p);
		CHECK(rh_ui_init(assets, &m) == 0); keys("a"); for (i = 0; i < m.n_apps; i++) keys("d");
		bogus = screen_hash(); CHECK(bogus == without); keys("a"); CHECK(V().screen == RH_S_CAND); screen_hash(); rh_ui_free();
	}
	remove(big_bmp); remove(text_file);
	/* the loader keeps only a plain relative .png name next to the candidate file */
	fd = mkstemp(tmp2); CHECK(fd >= 0);
	fp = fdopen(fd, "w");
	fprintf(fp, "{\"candidates\":[");
	{
		static const char *const NAMES[] = {"icons/ok.png", "../up.png", "/abs.png", "a b.png", "x.jpg", "icons/x.png.", "icons/..png", ""};
		for (i = 0; i < 8; i++) fprintf(fp, "%s{\"id\":\"i%d\",\"name\":\"I%d\",\"icon_file\":\"%s\",\"approval\":\"unapproved\",\"hardware_test\":\"none\"}", i ? "," : "", i, i, NAMES[i]);
	}
	fprintf(fp, "]}"); fclose(fp);
	rh_model_load(&m, cat, st); rh_model_load_candidates(&m, tmp2);
	CHECK(m.n_cands == 8 && !strncmp(m.cands[0].icon, "/tmp/icons/ok.png", 18) && m.cands[0].icon[17] == 0);
	for (i = 1; i < 8; i++) CHECK(m.cands[i].icon[0] == 0);
	remove(tmp2);
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
	preview(argv[1], assets);
	candidates(argv[1], assets);
	categories(argv[1], assets);
	paging(argv[1], assets);
	wiki_listings(argv[1], assets);
	icons(argv[1], assets);
	scenario(argv[1], assets, "populated"); scenario(argv[1], assets, "noupdates"); scenario(argv[1], assets, "empty");
	SDL_Quit();
	printf("%d checks, %d failed\n", checks, fails);
	return fails != 0;
}
