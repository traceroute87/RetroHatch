/* EXPERIMENTAL test install of UNAPPROVED candidates (DEV only): classification of the real 130-candidate snapshot, then the whole flow
 * (download, ZIP extraction, install, uninstall, refusals, cancel, offline, UI screens) against a local TLS server with throwaway CA.
 * Built with -DRH_EXPERIMENTAL like the DEV OPK; the production ops must still expose none of it. Temp dirs only.
 *   ui_exp_test <repo_root> <fixture_dir> <port> <ca.pem> [shots_dir]      (driven by tests/test_experimental.py, inside WSL) */
#define _XOPEN_SOURCE 700
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <SDL/SDL.h>
#include "../ui/rh_ui.h"
#include "../ui/rh_ops.h"
#include "../core/sha256.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static const char *fx, *port, *ca, *assets_dir, *repo, *shots;
static char root[256], apps[300], state[300], cache[300], mounts[300], sysb[300], mirror[300], extra[300], cands_path[400];
static uint8_t key[2][32];
static rh_model m;
static const rh_ui_ops *g_ops;
static int cancel_at;
static SDL_Surface *scr;

static void sh(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void sh(const char *fmt, ...)
{
	char c[1200]; va_list ap;
	va_start(ap, fmt); vsnprintf(c, sizeof c, fmt, ap); va_end(ap);
	if (system(c)) { printf("setup failed: %s\n", c); exit(2); }
}
static int exists(const char *p) { struct stat st; return lstat(p, &st) == 0; }
static void hash(const char *p, char h[65]) { if (rh_sha256_file(p, h, NULL)) strcpy(h, "-"); }
static void keys_(const char *s) { for (; *s; s++) rh_ui_key(*s == 'u' ? RH_K_UP : *s == 'd' ? RH_K_DOWN : *s == 'a' ? RH_K_A : RH_K_B); }
static rh_ui_view V(void) { rh_ui_view v; rh_ui_view_get(&v); return v; }
static void shot(const char *name)
{
	char p[500];
	rh_ui_draw(scr);
	if (!shots) return;
	snprintf(p, sizeof p, "%s/%s.bmp", shots, name); SDL_SaveBMP(scr, p);
}
static int poll(uint64_t done, uint64_t total) { rh_ui_progress(done, total); return cancel_at && done >= (uint64_t)cancel_at; }

static void reload(void)             /* as ui/rh_ui_main.c (DEV) does: no signed catalog needed here, then the candidates */
{
	rh_model_load_none(&m, "test", state);
	rh_model_load_candidates(&m, cands_path);
}
static const rh_ui_ops *ops_with(const char *host_port, int fresh, int production, const char *cpath)
{
	static char base[200]; FILE *f; rh_ops_cfg oc; const rh_ui_ops *ops; const char *sd = production ? ".retrohatch" : ".retrohatch-dev";
	snprintf(state, sizeof state, "%s/%s", root, sd); snprintf(cache, sizeof cache, "%s/cache", state);
	snprintf(mirror, sizeof mirror, "%s/mirror.txt", state); snprintf(extra, sizeof extra, "%s/extra-ca.crt", state);
	if (cpath != cands_path) snprintf(cands_path, sizeof cands_path, "%s", cpath);
	if (fresh) {
		sh("rm -rf %s/* %s/.retrohatch* ; mkdir -p %s %s/sys %s %s/cache", root, root, apps, root, state, state);
		f = fopen(mounts, "w"); fputs("/dev/root / ext4 ro 0 0\n/dev/mmcblk0p4 /mnt vfat rw 0 0\n", f); fclose(f);
	}
	f = fopen(mirror, "w"); fprintf(f, "https://github.com/ https://%s/gh/\nhttps://gitlab.com/ https://%s/gl/\n", host_port, host_port); fclose(f);
	memset(&oc, 0, sizeof oc);
	oc.production = production;
	oc.apps_dir = apps; oc.state_dir = state; oc.cache_dir = cache; oc.proc_mounts = mounts; oc.sys_block = sysb; oc.refresh = reload;
	oc.ca_bundle = ca; oc.mirror_file = mirror; oc.extra_ca = extra;
	snprintf(base, sizeof base, "https://%s/catalog/", host_port); oc.base_url = base;
	oc.cache_pkg = "/nonexistent/catalog.pkg"; oc.bundled_pkg = "/nonexistent/bundled.pkg"; oc.keys = key; oc.nkeys = 1; oc.progress = poll;
	ops = rh_ops_init(&oc); CHECK(ops != NULL);
	rh_ui_set_ops(ops); g_ops = ops;
	return ops;
}
static void begin(const char *hp, int fresh, int production, const char *cpath)
{
	rh_ui_free();
	ops_with(hp, fresh, production, cpath);
	reload();
	if (rh_ui_init(assets_dir, &m)) { printf("assets missing\n"); exit(2); }
}
static int cidx(const char *id) { int i; for (i = 0; i < m.n_cands; i++) if (!strcmp(m.cands[i].id, id)) return i; { int k; printf("no candidate %s; model has %d:", id, m.n_cands); for (k = 0; k < m.n_cands; k++) printf(" %s", m.cands[k].id); printf("\n"); exit(2); } }
static int inst_of(int i) { int k; char id[60]; snprintf(id, sizeof id, "x-%s", m.cands[i].id); for (k = 0; k < m.n_inst; k++) if (!strcmp(m.inst[k].id, id)) return 1; return 0; }
static int st(const char *id, char *why) { int i = cidx(id); why[0] = 0; return g_ops->cand_state(&m.cands[i], inst_of(i), why, 80); }
static int op(const char *id, int o, char *msg) { int i = cidx(id), rc; msg[0] = 0; rc = g_ops->cand_do(&m.cands[i], o, msg, 120); reload(); return rc; }
static int has(const char *hay, const char *needle) { return strstr(hay, needle) != NULL; }
static void cpath(const char *id, const char *ext, char *o, size_t n) { snprintf(o, n, "%s/x-%s.%s", cache, id, ext); }
static int leftovers(void) { char c[500]; snprintf(c, sizeof c, "ls %s 2>/dev/null | grep -E '\\.(part|zip|dl|new|tmp)$' >/dev/null", cache); return system(c) == 0; }
static int tsv_has(const char *id) { char c[600]; snprintf(c, sizeof c, "grep -q '^x-%s\t' %s/installed.tsv 2>/dev/null", id, state); return system(c) == 0; }
static void variant(const char *v) { char p[400]; FILE *f; snprintf(p, sizeof p, "%s/variant.txt", fx); f = fopen(p, "w"); fputs(v, f); fclose(f); }

/* the real snapshot: how many of the 130 may be offered, and why not the rest */
static void classify_snapshot(const char *hp)
{
	char why[80]; int i, n_dl = 0, n_no = 0; static char snap[400];
	int c_src = 0, c_fmt = 0, c_sys = 0, c_stub = 0, c_other = 0;
	snprintf(snap, sizeof snap, "%s/candidates/rg-nano.json", repo);
	begin(hp, 1, 0, snap);
	printf("snapshot: %d candidates\n", m.n_cands);
	CHECK(m.n_cands == 123);
	for (i = 0; i < m.n_cands; i++) {
		int s = g_ops->cand_state(&m.cands[i], 0, why, sizeof why);
		CHECK(s == RH_X_NO || s == RH_X_DOWNLOAD);     /* nothing is cached or installed in a fresh state */
		if (s == RH_X_DOWNLOAD) { n_dl++; CHECK(m.cands[i].url[0] && !strncmp(m.cands[i].url, "https://", 8) && !strcmp(m.cands[i].fmt, "opk")); }
		else {
			n_no++;
			if (has(why, "ource only")) c_src++; else if (has(why, "Not an OPK")) c_fmt++;
			else if (has(why, "firmware") || has(why, "USB") || has(why, "kernel")) c_sys++; else if (has(why, "stub")) c_stub++; else { c_other++; printf("  other reason: %s: %s\n", m.cands[i].id, why); }
		}
	}
	printf("snapshot: test-installable %d, not installable %d (source only %d, not an OPK %d, firmware/system %d, launcher stub %d, other %d)\n", n_dl, n_no, c_src, c_fmt, c_sys, c_stub, c_other);
	CHECK(n_dl + n_no == 123 && n_dl == 95 && c_other == 0);
	for (i = 0; i < m.n_cands; i++) CHECK(!strcmp(m.cands[i].id, "gmenu2x") ? g_ops->cand_state(&m.cands[i], 0, why, sizeof why) == RH_X_NO : 1);
}

int main(int argc, char **argv)
{
	char p[400], p2[400], h[65], h2[65], msg[160], why[80], hp[64], dead[64]; int i, rc; rh_ui_view v;
	if (argc < 5) return 2;
	repo = argv[1]; fx = argv[2]; port = argv[3]; ca = argv[4]; shots = argc > 5 ? argv[5] : NULL;
	key[0][0] = 1;                                           /* any non-zero key: the catalog is not used here, only the network switch */
	{ static char a[512]; snprintf(a, sizeof a, "%s/ui/assets", repo); assets_dir = a; }
	snprintf(root, sizeof root, "/tmp/rhexp.XXXXXX"); if (!mkdtemp(root)) return 2;
	snprintf(apps, sizeof apps, "%s/apps", root); snprintf(mounts, sizeof mounts, "%s/mounts", root); snprintf(sysb, sizeof sysb, "%s/sys", root);
	setenv("SDL_VIDEODRIVER", "dummy", 0);
	if (SDL_Init(SDL_INIT_VIDEO) || !(scr = SDL_SetVideoMode(240, 240, 32, SDL_SWSURFACE))) return 2;
	snprintf(hp, sizeof hp, "localhost:%s", port); snprintf(dead, sizeof dead, "localhost:1");
	variant("ok");

	classify_snapshot(hp);

	/* ---- fixture candidates ---- */
	snprintf(p, sizeof p, "%s/candidates.json", fx);
	begin(hp, 1, 0, p);
	printf("fixture file %s exists=%d n=%d\n", cands_path, exists(cands_path), m.n_cands);
	sh("echo 'unrelated app' > %s/unrelated.opk; echo 'keep' > %s/collide.opk; mkdir -p %s/savedata; echo save > %s/savedata/slot1", apps, apps, root, root);
	hash("/dev/null", h);
	CHECK(g_ops->cand_state && g_ops->cand_do && g_ops->cand_facts);
	CHECK(m.n_cands >= 15);
	for (i = 0; i < m.n_cands; i++) CHECK(!strcmp(m.cands[i].id, "") == 0);

	/* classification */
	CHECK(st("direct", why) == RH_X_DOWNLOAD && st("hashed", why) == RH_X_DOWNLOAD && st("zipped", why) == RH_X_DOWNLOAD && st("paren", why) == RH_X_DOWNLOAD);
	CHECK(st("source", why) == RH_X_NO && has(why, "ource only"));
	CHECK(st("gmenu2x", why) == RH_X_NO && has(why, "firmware menu"));
	CHECK(st("core", why) == RH_X_NO && has(why, "Not an OPK"));
	CHECK(st("huge", why) == RH_X_NO && has(why, "too large"));
	CHECK(st("denied", why) == RH_X_NO && has(why, "not allowed"));
	CHECK(st("plainhttp", why) == RH_X_NO && has(why, "not HTTPS"));
	CHECK(m.cands[cidx("hashed")].sha256[0] && !m.cands[cidx("direct")].sha256[0]);
	{   /* what the confirm screens will say */
		char f[80], hs[48];
		g_ops->cand_facts(&m.cands[cidx("direct")], RH_X_DOWNLOAD, f, sizeof f, hs, sizeof hs); CHECK(!strcmp(f, "direct_funkey-s.opk") && has(hs, "UNVERIFIED"));
		g_ops->cand_facts(&m.cands[cidx("hashed")], RH_X_DOWNLOAD, f, sizeof f, hs, sizeof hs); CHECK(has(hs, "inventory"));
		g_ops->cand_facts(&m.cands[cidx("paren")], RH_X_DOWNLOAD, f, sizeof f, hs, sizeof hs); CHECK(!strcmp(f, "Foo__NES_.opk"));
	}

	/* nothing is installed by downloading */
	CHECK(op("direct", RH_X_DOWNLOAD, msg) == 0);
	cpath("direct", "opk", p, sizeof p); CHECK(exists(p) && !leftovers());
	snprintf(p2, sizeof p2, "%s/direct_funkey-s.opk", apps); CHECK(!exists(p2) && !tsv_has("direct"));
	CHECK(st("direct", why) == RH_X_INSTALL);
	CHECK(op("direct", RH_X_DOWNLOAD, msg) == 1);               /* already downloaded: not repeated */

	/* hash: right one accepted, wrong one rejected and nothing kept */
	CHECK(op("hashed", RH_X_DOWNLOAD, msg) == 0);
	CHECK(op("badhash", RH_X_DOWNLOAD, msg) == 1 && has(msg, "SHA-256")); cpath("badhash", "opk", p, sizeof p); CHECK(!exists(p) && !leftovers());

	/* ZIP: member extracted; every ZIP refusal reaches the user as a message and leaves nothing */
	CHECK(op("zipped", RH_X_DOWNLOAD, msg) == 0); cpath("zipped", "opk", p, sizeof p); CHECK(exists(p) && !leftovers());
	snprintf(p2, sizeof p2, "%s/zipped.expect", fx); hash(p, h); hash(p2, h2); CHECK(!strcmp(h, h2));
	CHECK(op("zipmissing", RH_X_DOWNLOAD, msg) == 1 && has(msg, "not found in ZIP")); cpath("zipmissing", "opk", p, sizeof p); CHECK(!exists(p) && !leftovers());
	CHECK(op("zipsym", RH_X_DOWNLOAD, msg) == 1 && has(msg, "regular file")); cpath("zipsym", "opk", p, sizeof p); CHECK(!exists(p) && !leftovers());
	CHECK(op("zipbad", RH_X_DOWNLOAD, msg) == 1 && msg[0]); CHECK(!leftovers());
	CHECK(op("notzip", RH_X_DOWNLOAD, msg) == 1 && has(msg, "ZIP")); CHECK(!leftovers());

	/* not an OPK / missing / GitLab file page */
	CHECK(op("html", RH_X_DOWNLOAD, msg) == 1 && has(msg, "bad file header")); cpath("html", "opk", p, sizeof p); CHECK(!exists(p) && !leftovers());
	CHECK(op("notfound", RH_X_DOWNLOAD, msg) == 1 && msg[0]); CHECK(!leftovers());
	CHECK(op("gitlab", RH_X_DOWNLOAD, msg) == 0); cpath("gitlab", "opk", p, sizeof p); CHECK(exists(p));

	/* cancel, then retry */
	cancel_at = 100; CHECK(op("cancel", RH_X_DOWNLOAD, msg) == 1); cancel_at = 0; cpath("cancel", "opk", p, sizeof p); CHECK(!exists(p) && !leftovers());
	CHECK(op("cancel", RH_X_DOWNLOAD, msg) == 0 && exists(p));

	/* offline */
	begin(dead, 0, 0, cands_path);
	CHECK(op("paren", RH_X_DOWNLOAD, msg) == 1 && has(msg, "No internet")); cpath("paren", "opk", p, sizeof p); CHECK(!exists(p) && !leftovers());
	begin(hp, 0, 0, cands_path);
	CHECK(op("paren", RH_X_DOWNLOAD, msg) == 0 && op("collide", RH_X_DOWNLOAD, msg) == 0 && op("denied", RH_X_DOWNLOAD, msg) == 1);

	/* install: engine records it; a second install, a clash with a file we did not install, and the denylist are refused */
	CHECK(op("direct", RH_X_INSTALL, msg) == 0);
	snprintf(p2, sizeof p2, "%s/direct_funkey-s.opk", apps); cpath("direct", "opk", p, sizeof p); hash(p, h); hash(p2, h2); CHECK(!strcmp(h, h2));
	CHECK(tsv_has("direct") && st("direct", why) == RH_X_UNINSTALL);
	CHECK(op("direct", RH_X_INSTALL, msg) == 1);
	CHECK(op("collide", RH_X_INSTALL, msg) == 1 && has(msg, "already exists") && !tsv_has("collide"));
	snprintf(p2, sizeof p2, "%s/collide.opk", apps); sh("test \"$(cat %s)\" = keep", p2);
	CHECK(op("paren", RH_X_INSTALL, msg) == 0); snprintf(p2, sizeof p2, "%s/Foo__NES_.opk", apps); CHECK(exists(p2) && tsv_has("paren"));
	CHECK(op("zipped", RH_X_INSTALL, msg) == 0 && op("gitlab", RH_X_INSTALL, msg) == 0 && op("hashed", RH_X_INSTALL, msg) == 0);
	CHECK(!leftovers());
	{ char c[600]; snprintf(c, sizeof c, "ls %s/state-journal* %s/%s/journal* 2>/dev/null", root, root, ".retrohatch-dev"); (void)c; }

	/* uninstall: the engine refuses a file that changed; otherwise it is removed, the cache and everything else stay */
	sh("echo tampered >> %s/Foo__NES_.opk", apps);
	CHECK(op("paren", RH_X_UNINSTALL, msg) == 1 && has(msg, "changed") && exists(p2) && tsv_has("paren"));
	CHECK(op("direct", RH_X_UNINSTALL, msg) == 0); snprintf(p2, sizeof p2, "%s/direct_funkey-s.opk", apps); CHECK(!exists(p2) && !tsv_has("direct"));
	cpath("direct", "opk", p, sizeof p); CHECK(exists(p) && st("direct", why) == RH_X_INSTALL);
	snprintf(p2, sizeof p2, "%s/unrelated.opk", apps); sh("test \"$(cat %s)\" = 'unrelated app'", p2);
	sh("test \"$(cat %s/savedata/slot1)\" = save", root);

	/* ---- the UI: candidate page -> Test Install -> Download anyway -> (nothing installed) -> Install -> Installed list -> Uninstall ---- */
	begin(hp, 1, 0, snprintf(p, sizeof p, "%s/candidates.json", fx) ? p : p);
	sh("echo 'unrelated app' > %s/unrelated.opk", apps);
	{
		int ci = cidx("zipped"); char b[40];
		keys_("bbbbbbbb"); keys_("uuuu"); keys_("a");                       /* Home -> Discover */
		CHECK(V().screen == RH_S_DISCOVER);
		for (i = 0; i < ci; i++) keys_("d");
		keys_("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.app == ci); shot("x1_page_download");
		keys_("a"); v = V(); CHECK(v.screen == RH_S_CONFIRM && v.sel == 0); shot("x2_confirm_download");
		keys_("a"); CHECK(V().screen == RH_S_CAND);                         /* Cancel: nothing happens */
		cpath("zipped", "opk", p, sizeof p); CHECK(!exists(p) && rh_ui_run_pending() == 0);
		keys_("a"); keys_("da"); CHECK(V().screen == RH_S_WORKING); rh_ui_progress(2048, 4096); shot("x3_downloading");
		CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 0); shot("x4_downloaded");
		CHECK(exists(p)); snprintf(p2, sizeof p2, "%s/zipped_funkey-s.opk", apps); CHECK(!exists(p2) && !tsv_has("zipped"));   /* downloaded, NOT installed */
		keys_("a"); CHECK(V().screen == RH_S_CAND); shot("x5_page_install");
		keys_("a"); CHECK(V().screen == RH_S_CONFIRM); shot("x6_confirm_install");
		keys_("da"); CHECK(V().screen == RH_S_WORKING); CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 0); shot("x7_installed");
		CHECK(exists(p2) && tsv_has("zipped"));
		keys_("bbbbbbbb"); keys_("uuuu"); keys_("da");                        /* Home -> Installed */
		v = V(); CHECK(v.screen == RH_S_INSTALLED && v.count >= 1); shot("x8_installed_list");
		keys_("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.app == ci); shot("x9_page_uninstall");
		keys_("a"); CHECK(V().screen == RH_S_CONFIRM); shot("x10_confirm_uninstall");
		keys_("da"); CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 0); shot("x11_uninstalled");
		CHECK(!exists(p2) && !tsv_has("zipped"));
		/* a failure reaches the screen as a message; B/A go back */
		keys_("bbbbbbbb"); keys_("uuuu"); keys_("a");
		ci = cidx("html"); for (i = 0; i < ci; i++) keys_("d");
		keys_("a"); keys_("a"); keys_("da"); CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 1); shot("x12_download_failed");
		keys_("a"); CHECK(V().screen == RH_S_CAND);
		ci = cidx("source"); keys_("bb"); keys_("a"); for (i = 0; i < ci; i++) keys_("d");
		keys_("a"); CHECK(V().screen == RH_S_CAND); shot("x13_not_installable"); keys_("a"); CHECK(V().screen == RH_S_CAND);   /* A does nothing */
		(void)b;
	}

	/* ---- production: the same build must not offer any of it ---- */
	begin(hp, 1, 1, snprintf(p, sizeof p, "%s/candidates.json", fx) ? p : p);
	CHECK(g_ops->production == 1 && !g_ops->cand_state && !g_ops->cand_do && !g_ops->cand_facts);
	keys_("bbbbbbbb"); keys_("uuuu"); keys_("a"); keys_("a"); CHECK(V().screen == RH_S_CAND); keys_("a"); CHECK(V().screen == RH_S_CAND);
	/* and a DEV init after a production init does not inherit it the other way round */
	begin(hp, 1, 0, p); CHECK(g_ops->cand_state != NULL);

	sh("rm -rf %s", root);
	SDL_Quit();
	printf("%d checks, %d failed\n", checks, fails);
	return fails != 0;
}
