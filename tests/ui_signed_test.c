/* DEV flow with a SIGNED catalog over real TLS: bundled catalog -> Download -> Install -> catalog refresh -> Download -> Update,
 * plus the failure modes (tampered / stale / forked catalog, offline, hash mismatch, truncated, cancel, corrupt state).
 * The server and fixtures come from tests/test_signed_flow.py. Temp dirs only.
 *   ui_signed_test <repo_root> <fixture_dir> <port> <ca.pem> <pubkey_hex> */
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
#include "../ui/rh_source.h"
#include "../core/sha256.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static const char *fx, *port, *ca, *assets_dir, *repo;
static char root[256], apps[300], state[300], cache[300], pkg[300], mounts[300], sysb[300], mirror[300], extra[300], urlf[300];
static uint8_t key[2][32];
static rh_model m;
static rh_src_cfg src;
static const rh_ui_ops *g_ops;
static const char *shots;
static int cancel_at;     /* progress callback: cancel when done >= this (0 = never) */
static SDL_Surface *scr;
static void shot(const char *name)
{
	char p[500];
	if (!shots) return;
	rh_ui_draw(scr); snprintf(p, sizeof p, "%s/%s.bmp", shots, name); SDL_SaveBMP(scr, p);
}

static void sh(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void sh(const char *fmt, ...)
{
	char c[1200]; va_list ap;
	va_start(ap, fmt); vsnprintf(c, sizeof c, fmt, ap); va_end(ap);
	if (system(c)) { printf("setup failed: %s\n", c); exit(2); }
}
static int exists(const char *p) { struct stat st; return lstat(p, &st) == 0; }
static long fsize(const char *p) { struct stat st; return lstat(p, &st) ? -1 : (long)st.st_size; }
static void hash(const char *p, char h[65]) { if (rh_sha256_file(p, h, NULL)) strcpy(h, "-"); }
static void variant(const char *v) { char p[400]; FILE *f; snprintf(p, sizeof p, "%s/variant.txt", fx); f = fopen(p, "w"); fputs(v, f); fclose(f); }
static void keys_(const char *s) { for (; *s; s++) rh_ui_key(*s == 'u' ? RH_K_UP : *s == 'd' ? RH_K_DOWN : *s == 'a' ? RH_K_A : RH_K_B); }
static rh_ui_view V(void) { rh_ui_view v; rh_ui_view_get(&v); return v; }
static int unhex(const char *s, uint8_t *o, int n) { int i; for (i = 0; i < 2 * n; i++) { int c = s[i], v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1; if (v < 0) return -1; o[i / 2] = (uint8_t)(o[i / 2] << 4 | v); } return 0; }

static char last_why[120];
static void reload(void)             /* as ui/rh_ui_main.c does */
{
	char *idx; size_t len; rh_src_info si;
	if (!rh_src_load(&src, &idx, &len, &si)) { rh_model_load_signed(&m, idx, len, si.source, si.serial, si.expires, RH_DEVICE_ID, state); free(idx); last_why[0] = 0; }
	else { rh_model_load_none(&m, si.why, state); snprintf(last_why, sizeof last_why, "%s", si.why); }
}
static int poll(uint64_t done, uint64_t total) { (void)total; rh_ui_progress(done, total); return cancel_at && done >= (uint64_t)cancel_at; }

static const rh_ui_ops *ops_with(const char *host_port, int fresh_dirs)
{
	char c[400]; static char bundled[400]; FILE *f; rh_ops_cfg oc; const rh_ui_ops *ops;
	if (fresh_dirs) {
		sh("rm -rf %s/* %s/.retrohatch-dev; mkdir -p %s %s/sys %s %s/.retrohatch-dev/cache", root, root, apps, root, state, root);
		f = fopen(mounts, "w"); fputs("/dev/root / ext4 ro 0 0\n/dev/mmcblk0p4 /mnt vfat rw 0 0\n", f); fclose(f);
	}
	snprintf(c, sizeof c, "%s/bundled.pkg", fx); snprintf(bundled, sizeof bundled, "%s", c);
	f = fopen(mirror, "w"); fprintf(f, "https://github.com/ https://%s/gh/\n", host_port); fclose(f);
	memset(&oc, 0, sizeof oc);
	oc.apps_dir = apps; oc.state_dir = state; oc.cache_dir = cache; oc.proc_mounts = mounts; oc.sys_block = sysb; oc.refresh = reload;
	oc.ca_bundle = ca; oc.mirror_file = mirror; oc.extra_ca = extra;
	{ static char base[200]; snprintf(base, sizeof base, "https://%s/catalog/", host_port); oc.base_url = base; }
	oc.base_url_file = urlf; oc.cache_pkg = pkg; oc.bundled_pkg = bundled; oc.keys = key; oc.nkeys = 1; oc.progress = poll;
	src.state_dir = state; src.cache_pkg = pkg; src.bundled_pkg = oc.bundled_pkg; src.keys = key; src.nkeys = 1;
	ops = rh_ops_init(&oc); CHECK(ops != NULL);
	rh_ui_set_ops(ops); g_ops = ops;
	return ops;
}
static char hp[64];
static void begin(const char *host_port)
{
	rh_ui_free();
	snprintf(hp, sizeof hp, "%s", host_port);
	ops_with(hp, 1);
	reload();
	if (rh_ui_init(assets_dir, &m)) { printf("assets missing\n"); exit(2); }
}
static void reinit(const char *host_port)    /* new process, same disk: reload everything */
{
	rh_ui_free();
	snprintf(hp, sizeof hp, "%s", host_port);
	ops_with(hp, 0);
	reload();
	if (rh_ui_init(assets_dir, &m)) { printf("assets missing\n"); exit(2); }
}
static void home(void) { int i; for (i = 0; i < 8; i++) keys_("b"); keys_("uuuu"); }   /* back to Home with the first row selected */
static void to_app(int home_sel)   /* Home -> list (Discover/Updates) -> first app details */
{
	int i; home();
	for (i = 0; i < home_sel; i++) keys_("d");
	keys_("aa");
}
static void run_op(void) { CHECK(rh_ui_run_pending() == 1); }
static int refresh_catalog_ui(void)   /* Home -> Settings -> Catalog Status -> A */
{
	home(); keys_("dddad"); keys_("a");   /* Settings, row 1 = Catalog Status */
	CHECK(V().screen == RH_S_INFO && V().info == RH_I_CATALOG);
	shot("s5_catalog_status");
	keys_("a"); CHECK(V().screen == RH_S_WORKING); shot("s6_refreshing");
	run_op(); CHECK(V().screen == RH_S_RESULT); shot(V().result ? "s7_refresh_failed" : "s7_refreshed");
	return V().result;
}
static int download_ui(void)         /* on Details with a DOWNLOAD bar */
{
	CHECK(V().action == RH_ACT_DOWNLOAD); shot("s1_details_download");
	keys_("a"); CHECK(V().screen == RH_S_CONFIRM && V().sel == 0); shot("s2_confirm_download");
	keys_("da"); CHECK(V().screen == RH_S_WORKING); rh_ui_progress(1024 * 3, 4096); shot("s3_downloading");
	run_op(); CHECK(V().screen == RH_S_RESULT); shot(V().result ? "s4_download_failed" : "s4_downloaded");
	return V().result;
}
static void cpath(const char *sha, char *o, size_t n) { snprintf(o, n, "%s/%s.opk", cache, sha); }
static void tsv_ver(char *o, size_t n)
{
	char p[400], l[300]; FILE *f; o[0] = 0;
	snprintf(p, sizeof p, "%s/installed.tsv", state);
	if ((f = fopen(p, "r"))) { if (fgets(l, sizeof l, f)) { char *t = strtok(l, "\t"); t = strtok(NULL, "\t"); if (t) snprintf(o, n, "%s", t); } fclose(f); }
}
static int leftovers(void)           /* any temp file from a failed download / refresh */
{
	char c[500]; snprintf(c, sizeof c, "ls %s %s 2>/dev/null | grep -E '\\.(part|dl|new)$' >/dev/null", cache, state);
	return system(c) == 0;
}

int main(int argc, char **argv)
{
	char sha1[65], sha2[65], p[400], h[65], ver[40], before[65], after[65], hpbuf[64], dead[64];
	long sz1, sz2; FILE *f; rh_ui_view v;
	if (argc < 6) return 2;
	repo = argv[1]; fx = argv[2]; port = argv[3]; ca = argv[4]; shots = argc > 6 ? argv[6] : NULL;
	unhex(argv[5], key[0], 32); key[1][0] = 0;
	{ static char a[512]; snprintf(a, sizeof a, "%s/ui/assets", repo); assets_dir = a; }
	snprintf(root, sizeof root, "/tmp/rhsig.XXXXXX"); if (!mkdtemp(root)) return 2;
	snprintf(apps, sizeof apps, "%s/apps", root); snprintf(state, sizeof state, "%s/.retrohatch-dev", root);
	snprintf(cache, sizeof cache, "%s/cache", state); snprintf(pkg, sizeof pkg, "%s/catalog.pkg", state);
	snprintf(mounts, sizeof mounts, "%s/mounts", root); snprintf(sysb, sizeof sysb, "%s/sys", root);
	snprintf(mirror, sizeof mirror, "%s/mirror.txt", state); snprintf(extra, sizeof extra, "%s/extra-ca.crt", state);
	snprintf(urlf, sizeof urlf, "%s/catalog-url.txt", state);
	setenv("SDL_VIDEODRIVER", "dummy", 0);
	if (SDL_Init(SDL_INIT_VIDEO) || !(scr = SDL_SetVideoMode(240, 240, 32, SDL_SWSURFACE))) return 2;
	snprintf(hpbuf, sizeof hpbuf, "localhost:%s", port); snprintf(dead, sizeof dead, "localhost:1");
	snprintf(p, sizeof p, "%s/sha.txt", fx); f = fopen(p, "r");
	{ char v1[20], v2[20]; if (fscanf(f, "%19s %64s %ld %19s %64s %ld", v1, sha1, &sz1, v2, sha2, &sz2) != 6) return 2; } fclose(f);
	variant("ok");

	/* 1. first start: bundled signed catalog, nothing downloaded yet */
	begin(hpbuf);
	CHECK(m.cat.ok && !strcmp(m.cat.source, "bundled") && m.cat.serial == 1 && m.n_apps == 1);
	CHECK(!strcmp(m.apps[0].id, "rhprobe") && !strcmp(m.apps[0].version, "1.0.0") && m.apps[0].verified && !strncmp(m.apps[0].url, "https://github.com/", 19));
	to_app(0); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_DOWNLOAD);
	/* Cancel on the confirm screen downloads nothing */
	keys_("a"); CHECK(V().screen == RH_S_CONFIRM); keys_("a"); CHECK(V().screen == RH_S_DETAILS && !rh_ui_busy()); CHECK(rh_ui_run_pending() == 0);
	cpath(sha1, p, sizeof p); CHECK(!exists(p));
	/* download -> install */
	CHECK(download_ui() == 0); CHECK(fsize(p) == sz1); hash(p, h); CHECK(!strcmp(h, sha1)); CHECK(!leftovers());
	keys_("a"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_INSTALL);
	keys_("a"); keys_("da"); run_op(); CHECK(V().result == 0);
	tsv_ver(ver, sizeof ver); CHECK(!strcmp(ver, "1.0.0"));
	snprintf(p, sizeof p, "%s/rhprobe_funkey-s.opk", apps); hash(p, h); CHECK(!strcmp(h, sha1));

	/* 2. refresh: newer signed catalog (serial 2) -> update available -> download -> update */
	CHECK(refresh_catalog_ui() == 0); CHECK(exists(pkg) && !leftovers());
	CHECK(m.cat.ok && !strcmp(m.cat.source, "cached") && m.cat.serial == 2 && m.n_apps == 2 && m.n_upd == 1);
	home(); keys_("ddaa"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_DOWNLOAD);   /* Updates -> RH Probe: 1.1.0 not on the device */
	CHECK(download_ui() == 0); cpath(sha2, p, sizeof p); hash(p, h); CHECK(!strcmp(h, sha2));
	keys_("a"); CHECK(V().action == RH_ACT_UPDATE_NOW); keys_("a"); keys_("da"); run_op(); CHECK(V().result == 0);
	tsv_ver(ver, sizeof ver); CHECK(!strcmp(ver, "1.1.0"));
	/* the second signed app is not on the DEV allowlist: no download, no install */
	home(); keys_("aa"); v = V(); CHECK(v.screen == RH_S_DETAILS && v.action == RH_ACT_BLOCKED);   /* Discover is sorted by name: Other Pad first */
	CHECK(m.n_apps == 2 && strcmp(m.apps[V().app].id, "rhprobe"));
	hash(pkg, before);

	/* 3. bad catalogs from the server never replace the good one or move the rollback state */
	{ static const char *bad[] = {"tampered", "stale", "fork", "junk", "reset", "404"}; static const char *need[] = {"signature", "older", "older", "", "", "Not found"};
	  int i;
	  for (i = 0; i < 6; i++) {
		char st[400], b1[65], b2[65];
		variant(bad[i]); snprintf(st, sizeof st, "%s/catalog.state", state); hash(st, b1);
		CHECK(refresh_catalog_ui() == 1);
		CHECK(!leftovers()); hash(pkg, after); CHECK(!strcmp(before, after)); hash(st, b2); CHECK(!strcmp(b1, b2));
		CHECK(m.cat.serial == 2 && m.n_apps == 2);
		if (need[i][0]) CHECK(strstr(g_ops->net_status(), need[i]) != NULL);
		keys_("a"); CHECK(V().screen == RH_S_INFO);
	  } }
	variant("ok");
	/* identical catalog again: reported as up to date */
	CHECK(refresh_catalog_ui() == 0);
	/* offline: refresh and download say so; browsing, Installed and cached installs keep working */
	reinit(dead);
	CHECK(m.cat.ok && m.cat.serial == 2);
	keys_("a"); home(); CHECK(refresh_catalog_ui() == 1); CHECK(m.cat.serial == 2 && !leftovers());
	reinit(hpbuf);

	/* 4. artifact failures: wrong bytes, truncated, offline, cancelled. Nothing reaches the cache. */
	begin(hpbuf); to_app(0);
	variant("wrong"); CHECK(download_ui() == 1); cpath(sha1, p, sizeof p); CHECK(!exists(p) && !leftovers());
	keys_("a"); CHECK(V().screen == RH_S_DETAILS && V().action == RH_ACT_DOWNLOAD);
	variant("trunc"); CHECK(download_ui() == 1); CHECK(!exists(p) && !leftovers()); keys_("a");
	variant("reset"); CHECK(download_ui() == 1); CHECK(!exists(p) && !leftovers()); keys_("a");
	variant("ok"); cancel_at = 100; CHECK(download_ui() == 1); cancel_at = 0; CHECK(!exists(p) && !leftovers()); keys_("a");
	reinit(dead); to_app(0); CHECK(V().action == RH_ACT_DOWNLOAD); CHECK(download_ui() == 1); CHECK(!exists(p) && !leftovers()); keys_("a");
	reinit(hpbuf); to_app(0); CHECK(download_ui() == 0); CHECK(exists(p)); keys_("a");

	/* 5. offline restart: the cached signed catalog and the cached file still work */
	begin(hpbuf); CHECK(refresh_catalog_ui() == 0);                  /* now cached at serial 2 */
	reinit(dead);
	CHECK(m.cat.ok && !strcmp(m.cat.source, "cached") && m.cat.serial == 2);
	home(); keys_("ada"); cpath(sha2, p, sizeof p);                  /* Discover -> RH Probe */
	CHECK(V().screen == RH_S_DETAILS && !strcmp(m.apps[V().app].id, "rhprobe") && V().action == RH_ACT_DOWNLOAD);   /* 1.1.0 not cached here, offline */
	CHECK(download_ui() == 1); CHECK(!exists(p) && !leftovers());
	keys_("b"); home();

	/* 6. a catalog that does not verify is never shown */
	reinit(hpbuf);
	sh("cp %s %s.bak && head -c 200 %s.bak > %s", pkg, pkg, pkg, pkg);           /* damaged cache: bundled (serial 1) is now older than the saved state */
	reinit(hpbuf); CHECK(!m.cat.ok && m.n_apps == 0 && m.cat.status[0]);
	sh("cp %s.bak %s && rm %s.bak", pkg, pkg, pkg);
	reinit(hpbuf); CHECK(m.cat.ok && m.cat.serial == 2 && m.n_apps == 2);
	{ uint8_t save = key[0][5]; key[0][5] ^= 1; reinit(hpbuf); CHECK(!m.cat.ok && m.n_apps == 0); key[0][5] = save; }       /* wrong key */
	{ char st[400]; snprintf(st, sizeof st, "%s/catalog.state", state); sh("cp %s %s.bak && echo garbage > %s", st, st, st);
	  reinit(hpbuf); CHECK(!m.cat.ok && m.n_apps == 0 && strstr(m.cat.status, "corrupt"));                                 /* corrupt state: refused, not reset */
	  sh("mv %s.bak %s", st, st); reinit(hpbuf); CHECK(m.cat.ok && m.n_apps == 2); }

	sh("rm -rf %s", root);
	SDL_Quit();
	printf("%d checks, %d failed\n", checks, fails);
	return fails != 0;
}
