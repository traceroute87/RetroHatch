/* Phase 4B UI test: navigation + palette checks on the real 240x240 surface.
 *   ui_nav_test <repo_root> [shots_dir]
 * With shots_dir, also writes one BMP per screen. Uses SDL's dummy video. */
#include <stdio.h>
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
	CHECK(m.n_cands >= 1 && m.n_cands <= 10 && m.n_apps == n_apps);   /* approved apps untouched */
	for (i = 0; i < m.n_cands; i++) CHECK(m.cands[i].name[0] && m.cands[i].repo[0] && m.cands[i].sig_ok && m.cands[i].size > 0 && m.cands[i].claim[0]);
	for (i = 0; i < m.n_cands; i++) { int j; for (j = i + 1; j < m.n_cands; j++) CHECK(strcmp(m.cands[i].repo, m.cands[j].repo) != 0); }   /* one entry per project */
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
	scenario(argv[1], assets, "populated"); scenario(argv[1], assets, "noupdates"); scenario(argv[1], assets, "empty");
	SDL_Quit();
	printf("%d checks, %d failed\n", checks, fails);
	return fails != 0;
}
