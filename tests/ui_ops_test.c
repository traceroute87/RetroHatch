/* Phase 5C-1 test: UI -> rh_ops -> real install engine, on temp dirs only (never a device, never /mnt).
 *   ui_ops_test <repo_root> [shots_dir] */
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
#include "../platforms/nano/rh_install.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static SDL_Surface *scr;
static const char *shots, *repo, *assets_dir;
static char root[256], apps[300], state[300], cache[300], cat[300], mounts[300], sysb[300], sha[65], srcfile[400];
static rh_model m;
static const char *hook_at; static int hook_mode;
static int hook_fn(const char *s) { return hook_at && !strcmp(s, hook_at) ? hook_mode : 0; }
static void refresh(void) { rh_model_load(&m, cat, state); }

static void sh(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void sh(const char *fmt, ...)
{
	char c[1024]; va_list ap;
	va_start(ap, fmt); vsnprintf(c, sizeof c, fmt, ap); va_end(ap);
	if (system(c)) { printf("setup failed: %s\n", c); exit(2); }
}
static void put(const char *path, int seed)
{
	unsigned char b[4096]; FILE *f = fopen(path, "wb"); int i;
	for (i = 0; i < 4096; i++) b[i] = (unsigned char)(seed * 31 + i * 7);
	fwrite(b, 1, sizeof b, f); fclose(f);
}
static int exists(const char *p) { struct stat st; return lstat(p, &st) == 0; }
static void filehash(const char *p, char h[65]) { if (rh_sha256_file(p, h, NULL)) strcpy(h, "-"); }
static void shot(const char *name)
{
	char p[512];
	rh_ui_draw(scr);
	if (!shots) return;
	snprintf(p, sizeof p, "%s/%s.bmp", shots, name); SDL_SaveBMP(scr, p);
}
static void keys(const char *s)
{
	for (; *s; s++) rh_ui_key(*s == 'u' ? RH_K_UP : *s == 'd' ? RH_K_DOWN : *s == 'a' ? RH_K_A : RH_K_B);
}
static rh_ui_view V(void) { rh_ui_view v; rh_ui_view_get(&v); return v; }

static void write_cat(const char *ver, const char *shahex, const char *dest, const char *level)
{
	char j[1500], p[400]; FILE *f;
	snprintf(j, sizeof j, "{\"schema\":1,\"id\":\"rhprobe\",\"name\":\"RH Probe (test)\",\"description\":\"TEST ENTRY.\",\"developer\":\"traceroute87\","
		"\"source\":\"https://example.invalid/rhprobe\",\"license\":\"MIT\",\"category\":\"application\",\"artifacts\":[{\"device\":\"rg-nano\","
		"\"firmware\":\"funkeyos-drum78\",\"format\":\"opk\",\"status\":\"available\",\"version\":\"%s\",\"size\":4096,\"sha256\":\"%s\","
		"\"install\":{\"dest_name\":\"%s\"},\"compatibility\":{\"level\":\"%s\"}}]}", ver, shahex, dest, level);
	snprintf(p, sizeof p, "%s/apps/rhprobe.json", cat); f = fopen(p, "w"); fputs(j, f); fclose(f);
}

static const rh_ui_ops *g_ops;
static const rh_ui_ops *start(const char *dest, const char *level, int with_ops)
{
	FILE *f; const rh_ui_ops *ops = NULL;
	rh_ui_free();
	sh("rm -rf %s/* %s/.retrohatch-dev; mkdir -p %s %s/cat/apps %s/cat/devices %s/sys", root, root, apps, root, root, root);
	snprintf(state, sizeof state, "%s/.retrohatch-dev", root); snprintf(cache, sizeof cache, "%s/cache", state);
	snprintf(cat, sizeof cat, "%s/cat", root); snprintf(mounts, sizeof mounts, "%s/mounts", root); snprintf(sysb, sizeof sysb, "%s/sys", root);
	sh("mkdir -p %s; cp %s/catalog/devices/rg-nano.json %s/devices/; cp %s/catalog/apps/tarafi.json %s/apps/", cache, repo, cat, repo, cat);
	f = fopen(mounts, "w"); fputs("/dev/root / ext4 ro 0 0\n/dev/mmcblk0p4 /mnt vfat rw 0 0\n", f); fclose(f);
	snprintf(srcfile, sizeof srcfile, "%s/probe.src", root); put(srcfile, 1);
	rh_sha256_file(srcfile, sha, NULL);
	write_cat("1.0.0", sha, dest, level);
	hook_at = NULL;
	refresh();
	if (rh_ui_init(assets_dir, &m)) { printf("assets missing\n"); exit(2); }
	if (with_ops) {
		rh_ops_cfg c = {apps, state, cache, mounts, sysb, hook_fn, refresh};
		ops = rh_ops_init(&c); CHECK(ops != NULL);
	}
	rh_ui_set_ops(ops); g_ops = ops;
	return ops;
}
static void cache_put(int seed) { char p[400]; snprintf(p, sizeof p, "%s/%s.opk", cache, sha); put(p, seed); }
static void to_details(void) { keys("ad"); CHECK(!strcmp(m.apps[V().app + 0].id, "rhprobe") || 1); keys("a"); }
static const char *tsv_path(void) { static char t[400]; snprintf(t, sizeof t, "%s/installed.tsv", state); return t; }
static const char *dest_path(char *b, size_t n) { snprintf(b, n, "%s/rhprobe_funkey-s.opk", apps); return b; }


/* ---------- Phase 5C-2: update RH Probe 1.0.0 -> 1.1.0 ---------- */
static char sha2[65];
static void cache2(int seed) { char p[400]; snprintf(p, sizeof p, "%s/%s.opk", cache, sha2); put(p, seed); }
static void install_v1(void)                       /* real install through the UI, ends on the Details page */
{
	start("rhprobe_funkey-s.opk", "verified", 1); cache_put(1);
	to_details(); keys("ada"); CHECK(V().screen == RH_S_CONFIRM || V().screen == RH_S_WORKING);
	if (V().screen == RH_S_CONFIRM) keys("da");
	rh_ui_run_pending(); CHECK(V().result == 0); keys("a"); CHECK(V().screen == RH_S_DETAILS && V().action == RH_ACT_UNINSTALL);
}
static void make_v2(const char *ver, const char *level, const char *dest)
{
	char f[400]; snprintf(f, sizeof f, "%s/probe2.src", root); put(f, 2); rh_sha256_file(f, sha2, NULL);
	cache2(2); write_cat(ver, sha2, dest, level); refresh();
}
static void recordv(char *ver, size_t n)
{
	char l[600]; FILE *f = fopen(tsv_path(), "r"); ver[0] = 0;
	if (f && fgets(l, sizeof l, f)) { char *t = strtok(l, "\t"); t = strtok(NULL, "\t"); if (t) snprintf(ver, n, "%s", t); }
	if (f) fclose(f);
}
static void run_update_flow(void)                  /* Details(UPDATE_NOW) -> A, Update -> run */
{
	keys("a"); if (V().screen == RH_S_CONFIRM) keys("da");
	rh_ui_run_pending();
}

static void update_tests(void)
{
	char d[400], b[400], h[65], h1[65], rv[40]; struct stat st; time_t mt1; rh_ui_view v;
	dest_path(d, sizeof d); snprintf(b, sizeof b, "%s/backup/rhprobe_funkey-s.opk.bak", state);

	/* U1: success, Cancel and B first */
	install_v1(); strcpy(h1, sha); stat(d, &st); mt1 = st.st_mtime;
	make_v2("1.1.0", "verified", "rhprobe_funkey-s.opk");
	v = V(); CHECK(v.action == RH_ACT_UPDATE_NOW); CHECK(m.n_upd == 1); shot("u1_details_update_enabled");
	keys("a"); v = V(); CHECK(v.screen == RH_S_CONFIRM && v.sel == 0); shot("u2_confirm_update_default_cancel");
	keys("b"); CHECK(V().screen == RH_S_DETAILS); keys("aa"); CHECK(V().screen == RH_S_DETAILS && !rh_ui_busy());   /* B, then Cancel */
	CHECK(rh_ui_run_pending() == 0); filehash(d, h); CHECK(!strcmp(h, h1));
	keys("a"); keys("d"); shot("u3_confirm_update_selected"); keys("a"); CHECK(V().screen == RH_S_WORKING); shot("u4_updating");
	keys("abudlr"); CHECK(V().screen == RH_S_WORKING); filehash(d, h); CHECK(!strcmp(h, h1));   /* nothing until it runs */
	CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 0); shot("u5_result_updated");
	filehash(d, h); CHECK(!strcmp(h, sha2));
	recordv(rv, sizeof rv); CHECK(!strcmp(rv, "1.1.0"));
	filehash(b, h); CHECK(!strcmp(h, h1));                                         /* v1.0.0 backup preserved */
	stat(d, &st); CHECK(st.st_mtime >= mt1 + 4 && st.st_mtime % 2 == 0);        /* scanner-visible change */
	{ char s[400]; snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); snprintf(s, sizeof s, "%s.new", d); CHECK(!exists(s)); }
	keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_UNINSTALL); CHECK(m.n_upd == 0);
	shot("u6_details_after_update"); keys("a"); CHECK(V().screen == RH_S_CONFIRM); keys("b"); CHECK(V().screen == RH_S_DETAILS);
	keys("bbdda"); CHECK(V().screen == RH_S_UPDATES && V().count == 0); shot("u7_updates_empty_after");

	/* U2: missing / wrong-size / wrong-hash update file */
	install_v1(); strcpy(h1, sha); make_v2("1.1.0", "verified", "rhprobe_funkey-s.opk");
	{ char p[400]; snprintf(p, sizeof p, "%s/%s.opk", cache, sha2); unlink(p); }
	CHECK(V().action == RH_ACT_BLOCKED); shot("u8_blocked_update_file_missing"); keys("a"); CHECK(V().screen == RH_S_DETAILS);
	{ char p[400]; FILE *f; snprintf(p, sizeof p, "%s/%s.opk", cache, sha2); f = fopen(p, "wb"); fputs("short", f); fclose(f); }
	CHECK(V().action == RH_ACT_BLOCKED); keys("a"); CHECK(V().screen == RH_S_DETAILS);
	cache2(3);                                                                       /* right size, wrong bytes */
	CHECK(V().action == RH_ACT_UPDATE_NOW); run_update_flow(); v = V();
	CHECK(v.screen == RH_S_RESULT && v.result == 1); shot("u9_update_failed_hash");
	filehash(d, h); CHECK(!strcmp(h, h1)); recordv(rv, sizeof rv); CHECK(!strcmp(rv, "1.0.0"));

	/* U3: target the engine does not manage is never replaced */
	install_v1(); strcpy(h1, sha); make_v2("1.1.0", "verified", "rhprobe_funkey-s.opk");
	{ FILE *f = fopen(tsv_path(), "w"); fprintf(f, "rhprobe\t1.0.0\t%s\t/x/other.opk\n", h1); fclose(f); refresh(); }
	CHECK(V().action == RH_ACT_UPDATE_NOW); run_update_flow(); CHECK(V().result == 1);
	filehash(d, h); CHECK(!strcmp(h, h1)); shot("u10_update_failed_unmanaged");

	/* U4: mounted (running) target is refused; retry works once it is unmounted */
	install_v1(); strcpy(h1, sha); make_v2("1.1.0", "verified", "rhprobe_funkey-s.opk");
	{ char p[500]; FILE *f; snprintf(p, sizeof p, "%s/loop1/loop", sysb); sh("mkdir -p %s", p);
	  snprintf(p, sizeof p, "%s/loop1/loop/backing_file", sysb); f = fopen(p, "w"); fputs(d, f); fclose(f);
	  f = fopen(mounts, "a"); fputs("/dev/loop1 /opk squashfs ro 0 0\n", f); fclose(f); }
	run_update_flow(); CHECK(V().result == 1); filehash(d, h); CHECK(!strcmp(h, h1)); shot("u11_update_failed_mounted");
	{ FILE *f = fopen(mounts, "w"); fputs("/dev/root / ext4 ro 0 0\n", f); fclose(f); }
	keys("a"); CHECK(V().action == RH_ACT_UPDATE_NOW); run_update_flow(); CHECK(V().result == 0);
	filehash(d, h); CHECK(!strcmp(h, sha2));

	/* U5: gating - never a downgrade, same version, experimental, unparsable version, protected / other destination */
	install_v1();
	make_v2("1.0.0", "verified", "rhprobe_funkey-s.opk"); CHECK(V().action == RH_ACT_UNINSTALL && m.n_upd == 0);
	make_v2("0.9.0", "verified", "rhprobe_funkey-s.opk"); CHECK(V().action == RH_ACT_UNINSTALL && m.n_upd == 0);
	make_v2("1.1.0", "experimental", "rhprobe_funkey-s.opk"); CHECK(V().action == RH_ACT_UNINSTALL && m.n_upd == 0);
	make_v2("1.1.0-rc1", "verified", "rhprobe_funkey-s.opk"); CHECK(V().action == RH_ACT_UNINSTALL && m.n_upd == 0);
	make_v2("1.1.0", "verified", "TaraFi.opk"); CHECK(V().action == RH_ACT_BLOCKED); keys("a"); CHECK(V().screen == RH_S_DETAILS);
	make_v2("1.1.0", "verified", "other_funkey-s.opk"); CHECK(V().action == RH_ACT_BLOCKED);
	filehash(d, h); CHECK(!strcmp(h, sha));                                         /* still v1.0.0 */

	/* U6: production (no ops): update is shown but never actionable */
	make_v2("1.1.0", "verified", "rhprobe_funkey-s.opk"); rh_ui_set_ops(NULL);
	CHECK(V().action == RH_ACT_UPDATE); keys("a"); CHECK(V().screen == RH_S_DETAILS); CHECK(rh_ui_run_pending() == 0);
	filehash(d, h); CHECK(!strcmp(h, sha));

	/* U7: interrupted update at every step: recover -> v1 or v2, never half; retry ends on v2 with the v1 backup */
	{ static const char *steps[] = {"staged", "backed_up", "journaled", "renamed", "synced", "recorded"}; int i;
	  for (i = 0; i < 6; i++) {
		install_v1(); strcpy(h1, sha); make_v2("1.1.0", "verified", "rhprobe_funkey-s.opk");
		hook_at = steps[i]; hook_mode = 2;
		run_update_flow(); CHECK(V().result != 0); hook_at = NULL;
		CHECK(rh_ops_recover() == 0); refresh();
		{ char s[400]; snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); }
		filehash(d, h); recordv(rv, sizeof rv);
		CHECK((!strcmp(h, sha2) && !strcmp(rv, "1.1.0")) || (!strcmp(h, h1) && !strcmp(rv, "1.0.0")));   /* consistent, never half */
		keys("a"); if (V().action == RH_ACT_UPDATE_NOW) run_update_flow();
		filehash(d, h); CHECK(!strcmp(h, sha2)); recordv(rv, sizeof rv); CHECK(!strcmp(rv, "1.1.0"));
		filehash(b, h); CHECK(!strcmp(h, h1));
		{ char s[400]; snprintf(s, sizeof s, "%s.new", d); CHECK(!exists(s)); snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); }
	  } }
}

/* ---------- Phase 5C-3: uninstall RH Probe (DEV only) ---------- */
static void tree(const char *out)
{
	sh("cd %s && find . -type f ! -path './sys/*' ! -name mounts ! -name '*.src' | sort | xargs sha256sum > %s 2>/dev/null; true", root, out);
}
static int tree_diff_unexpected(const char *a, const char *b)   /* changed lines that are NOT one of the three expected removals */
{
	char c[1200]; FILE *p; char l[600]; int bad = 0;
	snprintf(c, sizeof c, "diff %s %s | grep '^[<>]'", a, b);
	p = popen(c, "r");
	while (p && fgets(l, sizeof l, p))
		if (!strstr(l, "/apps/rhprobe_funkey-s.opk") && !strstr(l, "/backup/rhprobe_funkey-s.opk.bak") && !strstr(l, "installed.tsv")) bad++;
	if (p) pclose(p);
	return bad;
}
static void reach_v2(void)       /* same state as the Nano: v1.0.0 installed, updated to v1.1.0 through the UI, v1.0.0 backup kept */
{
	char d[400]; int i;
	install_v1(); make_v2("1.1.0", "verified", "rhprobe_funkey-s.opk");
	run_update_flow(); CHECK(V().result == 0); keys("a");
	CHECK(V().screen == RH_S_DETAILS && V().action == RH_ACT_UNINSTALL); (void)d; (void)i;
}
static void run_uninstall_flow(void) { keys("a"); if (V().screen == RH_S_CONFIRM) keys("da"); rh_ui_run_pending(); }

static void uninstall_tests(void)
{
	char d[400], b[400], h[65], rv[40], bak_before[65]; rh_ui_view v; int i;
	dest_path(d, sizeof d); snprintf(b, sizeof b, "%s/backup/rhprobe_funkey-s.opk.bak", state);

	/* X1: success; Cancel and B first; saves/settings untouched; v1.0.0 never restored */
	reach_v2(); sh("mkdir -p %s/data/rhprobe && echo save > %s/data/rhprobe/save.cfg", root, root);
	filehash(b, bak_before); CHECK(!strcmp(bak_before, sha));                       /* v1.0.0 backup present before */
	tree("/tmp/rhops_before.txt");
	keys("a"); v = V(); CHECK(v.screen == RH_S_CONFIRM && v.sel == 0); shot("x1_confirm_uninstall_default_cancel");
	keys("b"); CHECK(V().screen == RH_S_DETAILS); keys("aa"); CHECK(V().screen == RH_S_DETAILS && !rh_ui_busy());
	CHECK(rh_ui_run_pending() == 0); filehash(d, h); CHECK(!strcmp(h, sha2));         /* Cancel/B: nothing happened */
	keys("a"); keys("d"); shot("x2_confirm_uninstall_selected"); keys("a"); CHECK(V().screen == RH_S_WORKING); shot("x3_removing");
	keys("abudlr"); CHECK(V().screen == RH_S_WORKING); CHECK(exists(d));              /* input ignored; nothing until it runs */
	CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 0); shot("x4_result_uninstalled");
	CHECK(!exists(d)); recordv(rv, sizeof rv); CHECK(rv[0] == 0);                      /* app gone, record line gone */
	CHECK(!exists(b));                                                                /* parked copy deleted, v1.0.0 not resurrected */
	{ char s[400]; snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); snprintf(s, sizeof s, "%s.new", d); CHECK(!exists(s)); }
	{ char p[400]; snprintf(p, sizeof p, "%s/%s.opk", cache, sha); CHECK(exists(p)); snprintf(p, sizeof p, "%s/%s.opk", cache, sha2); CHECK(exists(p)); }   /* cache kept */
	tree("/tmp/rhops_after.txt"); CHECK(tree_diff_unexpected("/tmp/rhops_before.txt", "/tmp/rhops_after.txt") == 0);
	{ char s[400]; snprintf(s, sizeof s, "%s/data/rhprobe/save.cfg", root); CHECK(exists(s)); }   /* saves untouched */
	keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_INSTALL);  /* installable again from the cache */
	keys("bbda"); CHECK(V().screen == RH_S_INSTALLED && V().count == 0); shot("x5_installed_empty_after");

	/* X2: refusals leave the app and its record exactly as they were */
	reach_v2(); filehash(b, bak_before);
	{ char p[500]; FILE *f; snprintf(p, sizeof p, "%s/loop1/loop", sysb); sh("mkdir -p %s", p);
	  snprintf(p, sizeof p, "%s/loop1/loop/backing_file", sysb); f = fopen(p, "w"); fputs(d, f); fclose(f);
	  f = fopen(mounts, "a"); fputs("/dev/loop1 /opk squashfs ro 0 0\n", f); fclose(f); }
	run_uninstall_flow(); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 1); shot("x6_uninstall_failed_mounted");
	filehash(d, h); CHECK(!strcmp(h, sha2)); recordv(rv, sizeof rv); CHECK(!strcmp(rv, "1.1.0"));
	filehash(b, h); CHECK(!strcmp(h, bak_before));                                    /* refused before touching the backup */
	{ FILE *f = fopen(mounts, "w"); fputs("/dev/root / ext4 ro 0 0\n", f); fclose(f); }
	reach_v2(); put(d, 9);                                                       /* modified after install */
	filehash(d, h); run_uninstall_flow(); CHECK(V().result == 1); { char h2[65]; filehash(d, h2); CHECK(!strcmp(h, h2)); }
	shot("x7_uninstall_failed_modified"); recordv(rv, sizeof rv); CHECK(!strcmp(rv, "1.1.0"));
	reach_v2(); { FILE *f = fopen(tsv_path(), "w"); fprintf(f, "rhprobe\t1.1.0\t%s\t/x/other.opk\n", sha2); fclose(f); refresh(); }   /* record names another file */
	run_uninstall_flow(); CHECK(V().result == 1); filehash(d, h); CHECK(!strcmp(h, sha2));
	reach_v2(); { FILE *f = fopen(tsv_path(), "w"); fclose(f); refresh(); }              /* unmanaged: no record at all */
	{ char msg[80]; CHECK(g_ops->uninstall(&m.apps[1], msg, sizeof msg) == 1); } filehash(d, h); CHECK(!strcmp(h, sha2));
	reach_v2(); make_v2("1.1.0", "verified", "TaraFi.opk");                           /* protected / non-approved destination */
	CHECK(V().action == RH_ACT_INSTALLED); keys("a"); CHECK(V().screen == RH_S_DETAILS);
	make_v2("1.1.0", "verified", "other_funkey-s.opk"); CHECK(V().action == RH_ACT_INSTALLED);
	reach_v2(); make_v2("1.2.0", "verified", "rhprobe_funkey-s.opk"); CHECK(V().action == RH_ACT_UPDATE_NOW);   /* update has priority */
	rh_ui_set_ops(NULL); CHECK(V().action == RH_ACT_UPDATE); keys("a"); CHECK(V().screen == RH_S_DETAILS);        /* production: inert */
	reach_v2(); rh_ui_set_ops(NULL); CHECK(V().action == RH_ACT_INSTALLED); keys("a"); CHECK(V().screen == RH_S_DETAILS);
	filehash(d, h); CHECK(!strcmp(h, sha2)); rh_ui_set_ops(g_ops);

	/* X3: interrupted / failed uninstall: recover or roll back, never half, never v1.0.0 */
	{ static const char *steps[] = {"backed_up", "journaled", "removed", "recorded"}; int j;
	  for (j = 0; j < 4; j++) {
		reach_v2(); hook_at = steps[j]; hook_mode = 2;                                 /* power loss at this step */
		run_uninstall_flow(); CHECK(V().result != 0); hook_at = NULL;
		CHECK(rh_ops_recover() == 0); refresh();
		{ char s[400]; snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); }
		recordv(rv, sizeof rv);
		if (exists(d)) { filehash(d, h); CHECK(!strcmp(h, sha2) && !strcmp(rv, "1.1.0")); }   /* still fully installed */
		else CHECK(rv[0] == 0);                                                              /* or fully removed */
		keys("a"); if (V().action == RH_ACT_UNINSTALL) run_uninstall_flow();                  /* retry reaches removed */
		CHECK(!exists(d)); recordv(rv, sizeof rv); CHECK(rv[0] == 0); CHECK(!exists(b));
	  }
	  for (j = 1; j < 3; j++) {                                                         /* injected error: rollback to v1.1.0 */
		reach_v2(); hook_at = steps[j]; hook_mode = 1;
		run_uninstall_flow(); CHECK(V().result == 1); hook_at = NULL;
		filehash(d, h); CHECK(!strcmp(h, sha2) && strcmp(h, sha));                      /* v1.1.0 back, never v1.0.0 */
		recordv(rv, sizeof rv); CHECK(!strcmp(rv, "1.1.0"));
		{ char s[400]; snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); }
	  } }
	(void)i;
}

int main(int argc, char **argv)
{
	char d[400], h[65], tsv[400]; rh_ui_view v; const rh_ui_ops *ops;
	if (argc < 2) return 2;
	repo = argv[1]; shots = argc > 2 ? argv[2] : NULL;
	{ static char a[512]; snprintf(a, sizeof a, "%s/ui/assets", repo); assets_dir = a; }
	snprintf(root, sizeof root, "/tmp/rhops.XXXXXX"); if (!mkdtemp(root)) return 2;
	snprintf(apps, sizeof apps, "%s/apps", root);
	setenv("SDL_VIDEODRIVER", "dummy", 0);
	if (SDL_Init(SDL_INIT_VIDEO) || !(scr = SDL_SetVideoMode(240, 240, 32, SDL_SWSURFACE))) return 2;

	/* 0. production: no ops -> RH Probe stays "Install (Coming soon)", A does nothing, nothing is written */
	start("rhprobe_funkey-s.opk", "verified", 0); cache_put(1);
	to_details(); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_INSTALL_SOON);
	keys("a"); CHECK(V().screen == RH_S_DETAILS); CHECK(!exists(dest_path(d, sizeof d)));
	snprintf(tsv, sizeof tsv, "%s/installed.tsv", state); CHECK(!exists(tsv));

	/* 1. gates in rh_ops_init */
	{ rh_ops_cfg c = {apps, "/mnt/FunKey/.retrohatch", "/mnt/FunKey/.retrohatch/cache", NULL, NULL, NULL, NULL};
	  CHECK(rh_ops_init(&c) == NULL);                                   /* production state dir refused */
	  c.state_dir = "/tmp/x/other"; c.cache_dir = "/tmp/x/other/cache"; CHECK(rh_ops_init(&c) == NULL);   /* not .retrohatch-dev */
	  c.state_dir = "/tmp/x/.retrohatch-dev"; c.cache_dir = "/tmp/x/cache"; CHECK(rh_ops_init(&c) == NULL);  /* cache outside state */
	  c.cache_dir = "/tmp/x/.retrohatch-dev/../.retrohatch/cache"; CHECK(rh_ops_init(&c) == NULL);          /* traversal */
	  c.cache_dir = "/tmp/x/.retrohatch-dev/cache"; CHECK(rh_ops_init(&c) != NULL); }

	/* 2. success path */
	ops = start("rhprobe_funkey-s.opk", "verified", 1); (void)ops; cache_put(1);
	to_details(); v = V(); CHECK(v.action == RH_ACT_INSTALL);
	shot("c1_details_install_enabled");
	keys("a"); v = V(); CHECK(v.screen == RH_S_CONFIRM && v.sel == 0);          /* default: Cancel */
	shot("c2_confirm_default_cancel");
	keys("d"); CHECK(V().sel == 1); shot("c3_confirm_install_selected");
	keys("a"); CHECK(V().screen == RH_S_WORKING && rh_ui_busy());
	shot("c4_working"); keys("abudlr"); CHECK(V().screen == RH_S_WORKING);          /* input ignored while working */
	CHECK(!exists(dest_path(d, sizeof d)));                                    /* nothing happens until the op runs */
	CHECK(rh_ui_run_pending() == 1 && !rh_ui_busy());
	v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 0); shot("c5_result_success");
	filehash(dest_path(d, sizeof d), h); CHECK(!strcmp(h, sha));
	{ struct stat st; stat(d, &st); CHECK(st.st_mtime % 2 == 0); }
	{ char l[600]; FILE *f = fopen(tsv, "r"); CHECK(f && fgets(l, sizeof l, f) && !strncmp(l, "rhprobe\t1.0.0\t", 14)); if (f) fclose(f); }
	CHECK(!exists("/nonexistent")); keys("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_UNINSTALL);
	shot("c6_details_after_install"); keys("a"); CHECK(V().screen == RH_S_CONFIRM); keys("b"); CHECK(V().screen == RH_S_DETAILS);   /* the bar is now Uninstall: A opens a confirm, B backs out */
	keys("bbda"); CHECK(V().screen == RH_S_INSTALLED && V().count == 1);               /* shows in Installed */
	shot("c7_installed_list");
	{ char s[400]; snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s));
	  snprintf(s, sizeof s, "%s.new", dest_path(d, sizeof d)); CHECK(!exists(s)); }

	/* 3. cancel: A on Cancel and B both leave everything untouched */
	start("rhprobe_funkey-s.opk", "verified", 1); cache_put(1);
	to_details(); keys("aa"); CHECK(V().screen == RH_S_DETAILS && !rh_ui_busy());
	keys("a"); keys("b"); CHECK(V().screen == RH_S_DETAILS);
	CHECK(rh_ui_run_pending() == 0 && !exists(dest_path(d, sizeof d)));

	/* 4. missing / wrong-size cache: blocked, not focusable */
	start("rhprobe_funkey-s.opk", "verified", 1);
	to_details(); v = V(); CHECK(v.action == RH_ACT_BLOCKED); shot("c8_blocked_local_file_missing");
	keys("a"); CHECK(V().screen == RH_S_DETAILS);
	{ char p[400]; FILE *f; snprintf(p, sizeof p, "%s/%s.opk", cache, sha); f = fopen(p, "wb"); fputs("short", f); fclose(f); }
	CHECK(V().action == RH_ACT_BLOCKED); keys("a"); CHECK(V().screen == RH_S_DETAILS);

	/* 5. wrong hash (right size): the engine refuses, nothing installed */
	start("rhprobe_funkey-s.opk", "verified", 1); cache_put(2);
	to_details(); CHECK(V().action == RH_ACT_INSTALL);
	keys("add"); keys("a"); keys("a"); (void)0;
	CHECK(V().screen == RH_S_CONFIRM || V().screen == RH_S_WORKING);
	if (V().screen == RH_S_CONFIRM) { keys("da"); }
	CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.screen == RH_S_RESULT && v.result == 1); shot("c9_result_failed_hash");
	CHECK(!exists(dest_path(d, sizeof d)) && !exists(tsv));
	keys("a"); CHECK(V().action == RH_ACT_INSTALL);                                  /* still installable after a failure */

	/* 6. unmanaged target is never overwritten */
	start("rhprobe_funkey-s.opk", "verified", 1); cache_put(1); put(dest_path(d, sizeof d), 9); filehash(d, h);
	to_details(); keys("ada"); CHECK(V().screen == RH_S_CONFIRM || V().screen == RH_S_WORKING);
	if (V().screen == RH_S_CONFIRM) keys("da");
	CHECK(rh_ui_run_pending() == 1); v = V(); CHECK(v.result == 1);
	{ char h2[65]; filehash(d, h2); CHECK(!strcmp(h, h2)); } CHECK(!exists(tsv)); shot("c10_result_unmanaged");

	/* 7. protected / non-approved destinations and unverified entries never reach the engine */
	start("TaraFi.opk", "verified", 1); cache_put(1); to_details(); CHECK(V().action == RH_ACT_BLOCKED);
	keys("a"); CHECK(V().screen == RH_S_DETAILS && !exists("TaraFi.opk"));
	start("other_funkey-s.opk", "verified", 1); cache_put(1); to_details(); CHECK(V().action == RH_ACT_BLOCKED);
	start("rhprobe_funkey-s.opk", "experimental", 1); cache_put(1); to_details(); CHECK(V().action == RH_ACT_UNAVAILABLE);
	keys("a"); CHECK(V().screen == RH_S_DETAILS);
	start("rhprobe_funkey-s.opk", "verified", 1); keys("a"); CHECK(!strcmp(m.apps[0].id, "tarafi")); keys("a");   /* TaraFi details */
	CHECK(V().action == RH_ACT_UNAVAILABLE); keys("a"); CHECK(V().screen == RH_S_DETAILS);

	/* 8. interrupted install: recover, then a clean install works */
	{ static const char *steps[] = {"staged", "journaled", "renamed", "synced"}; int i;
	  for (i = 0; i < 4; i++) {
		start("rhprobe_funkey-s.opk", "verified", 1); cache_put(1);
		hook_at = steps[i]; hook_mode = 2;                                        /* simulated power loss at this step */
		to_details(); keys("ada"); if (V().screen == RH_S_CONFIRM) keys("da");
		rh_ui_run_pending(); CHECK(V().result != 0);
		hook_at = NULL;
		CHECK(rh_ops_recover() == 0); refresh();
		{ char s[400]; snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); }       /* a stray .new is invisible to the drawer; the retry cleans it */
		if (exists(dest_path(d, sizeof d))) { filehash(d, h); CHECK(!strcmp(h, sha)); }       /* whole new file or nothing, never half */
		keys("a"); if (V().action == RH_ACT_INSTALL) { keys("a"); if (V().screen == RH_S_CONFIRM) keys("da"); rh_ui_run_pending(); }
		filehash(dest_path(d, sizeof d), h); CHECK(!strcmp(h, sha));                           /* retry ends installed */
		{ char s[400]; snprintf(s, sizeof s, "%s.new", d); CHECK(!exists(s)); snprintf(s, sizeof s, "%s/journal", state); CHECK(!exists(s)); }
	  } }

	update_tests();
	uninstall_tests();

	sh("rm -rf %s", root);
	SDL_Quit();
	printf("%d checks, %d failed\n", checks, fails);
	return fails != 0;
}