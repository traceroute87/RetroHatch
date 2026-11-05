/* Production ops gates, on temp dirs only (never a device, never /mnt, no network): the production rules of ui/rh_ops.c, that DEV rules are
 * unchanged, and that every misconfiguration fails closed. Test-only key bytes; no key of any build is used here.
 *   ui_prod_test <repo_root> */
#define _XOPEN_SOURCE 700
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <SDL/SDL.h>
#include "../ui/rh_ops.h"
#include "../ui/rh_source.h"
#include "../core/sha256.h"
#include "../platforms/nano/rh_install.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static char root[256], apps[300], pstate[300], pcache[300], dstate[300], dcache[300], mounts[300], sysb[300], ca[300], src[300], sha[65];
static uint8_t key[1][32], zero[1][32];
static void refresh(void) {}
static void keys_(const char *s) { for (; *s; s++) rh_ui_key(*s == 'u' ? RH_K_UP : *s == 'd' ? RH_K_DOWN : *s == 'a' ? RH_K_A : RH_K_B); }
static rh_ui_view V(void) { rh_ui_view v; rh_ui_view_get(&v); return v; }
static rh_model model;
static void sh(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void sh(const char *fmt, ...)
{
	char c[800]; va_list ap;
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

static rh_ops_cfg cfg(int production, const char *state, const char *cache)
{
	rh_ops_cfg c; memset(&c, 0, sizeof c);
	c.production = production; c.apps_dir = apps; c.state_dir = state; c.cache_dir = cache; c.proc_mounts = mounts; c.sys_block = sysb; c.refresh = refresh;
	return c;
}
static rh_ops_cfg with_net(rh_ops_cfg c, const uint8_t (*k)[32], const char *cabundle, const char *base)
{
	c.ca_bundle = cabundle; c.keys = k; c.nkeys = 1; c.cache_pkg = "/tmp/rh_prod_test_catalog.pkg"; c.base_url = base;
	return c;
}
static rh_app app(const char *id, const char *dest, const char *ver, int signed_)
{
	rh_app a; memset(&a, 0, sizeof a);
	snprintf(a.id, sizeof a.id, "%s", id); snprintf(a.name, sizeof a.name, "%s", id); snprintf(a.dest_name, sizeof a.dest_name, "%s", dest);
	snprintf(a.version, sizeof a.version, "%s", ver); snprintf(a.sha256, sizeof a.sha256, "%s", sha); a.size = 4096; a.verified = 1; a.available = 1; a.signed_catalog = signed_;
	snprintf(a.url, sizeof a.url, "https://github.com/test/%s/releases/download/v1/%s", id, dest);
	return a;
}
static void cache_file(const char *cache, const char *h, int seed) { char p[500]; snprintf(p, sizeof p, "%s/%s.opk", cache, h); put(p, seed); }

int main(int argc, char **argv)
{
	(void)argv;
	rh_ops_cfg c; const rh_ui_ops *o; char why[80], msg[120]; rh_app a; char p[500];
	if (argc < 2) return 2;
	snprintf(root, sizeof root, "/tmp/rhprod.XXXXXX"); if (!mkdtemp(root)) return 2;
	snprintf(apps, sizeof apps, "%s/apps", root); snprintf(mounts, sizeof mounts, "%s/mounts", root); snprintf(sysb, sizeof sysb, "%s/sys", root);
	snprintf(pstate, sizeof pstate, "%s/.retrohatch", root); snprintf(pcache, sizeof pcache, "%s/cache", pstate);
	snprintf(dstate, sizeof dstate, "%s/.retrohatch-dev", root); snprintf(dcache, sizeof dcache, "%s/cache", dstate);
	snprintf(ca, sizeof ca, "%s/ca.crt", root); snprintf(src, sizeof src, "%s/probe.src", root);
	sh("mkdir -p %s %s/sys %s %s; echo x > %s", apps, root, dstate, dcache, ca);
	{ FILE *f = fopen(mounts, "w"); fputs("/dev/root / ext4 ro 0 0\n/dev/mmcblk0p4 /mnt vfat rw 0 0\n", f); fclose(f); }
	put(src, 7); rh_sha256_file(src, sha, NULL);
	memset(key[0], 0x5a, 32); memset(zero, 0, sizeof zero);        /* test-only key bytes */

	/* ---- state directories: each mode has its own and refuses the other's, and the production one must be a real directory ---- */
	c = cfg(1, dstate, dcache); CHECK(rh_ops_init(&c) == NULL);                           /* production on the DEV state dir */
	c = cfg(0, pstate, pcache); sh("mkdir -p %s %s", pstate, pcache); CHECK(rh_ops_init(&c) == NULL);   /* DEV on the production-named state dir */
	c = cfg(0, RH_NANO_STATE_DIR, RH_NANO_STATE_DIR "/cache"); CHECK(rh_ops_init(&c) == NULL);          /* DEV on the real production path */
	sh("rm -rf %s", pstate);
	{ char bad[300], badc[300]; snprintf(bad, sizeof bad, "%s/no/such/.retrohatch", root); snprintf(badc, sizeof badc, "%s/cache", bad);
	  c = cfg(1, bad, badc); CHECK(rh_ops_init(&c) == NULL); CHECK(!exists(bad)); }          /* parent missing: mkdir fails, nothing enabled */
	sh("echo f > %s", pstate); c = cfg(1, pstate, pcache); CHECK(rh_ops_init(&c) == NULL); sh("rm -f %s", pstate);   /* a file, not a directory */
	sh("mkdir -p %s/real; ln -s %s/real %s", root, root, pstate); c = cfg(1, pstate, pcache); CHECK(rh_ops_init(&c) == NULL); sh("rm -rf %s %s/real", pstate, root);   /* a link */
	{ char outside[300]; snprintf(outside, sizeof outside, "%s/elsewhere", root);
	  c = cfg(1, pstate, outside); CHECK(rh_ops_init(&c) == NULL); }                        /* cache outside the state dir */
	{ char dots[300]; snprintf(dots, sizeof dots, "%s/../cache", pstate); c = cfg(1, pstate, dots); CHECK(rh_ops_init(&c) == NULL); }

	/* ---- production, good configuration: directories created, label and mode set, network only when everything is usable ---- */
	c = cfg(1, pstate, pcache); o = rh_ops_init(&c);
	CHECK(o != NULL && o->production == 1 && strstr(o->build_label, "Production") && exists(pstate) && exists(pcache));
	CHECK(o->can_download == NULL && o->download == NULL && o->refresh_catalog == NULL);     /* no CA, no key, no catalog address: no network */
	c = with_net(cfg(1, pstate, pcache), key, ca, "https://catalog.invalid/"); o = rh_ops_init(&c);
	CHECK(o && o->can_download && o->download && o->refresh_catalog);                       /* a complete configuration enables it */
	c = with_net(cfg(1, pstate, pcache), zero, ca, "https://catalog.invalid/"); o = rh_ops_init(&c); CHECK(o && !o->can_download && !o->refresh_catalog);   /* all-zero key */
	c = with_net(cfg(1, pstate, pcache), key, "/nonexistent/ca.crt", "https://catalog.invalid/"); o = rh_ops_init(&c); CHECK(o && !o->can_download);   /* CA bundle missing */
	c = with_net(cfg(1, pstate, pcache), key, ca, "http://catalog.invalid/"); o = rh_ops_init(&c); CHECK(o && !o->can_download);                          /* not HTTPS */
	c = with_net(cfg(1, pstate, pcache), key, ca, "https://catalog.invalid/"); c.nkeys = 0; o = rh_ops_init(&c); CHECK(o && !o->can_download);            /* no keys */

	/* ---- eligibility: only an entry that came from a verified signed index, with complete verified data and the file in the cache ---- */
	c = with_net(cfg(1, pstate, pcache), key, ca, "https://catalog.invalid/"); o = rh_ops_init(&c); CHECK(o != NULL);
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1);                                  /* NOT RH Probe: no allowlist in production */
	CHECK(!o->can_install(&a, why, sizeof why) && !strcmp(why, "Local file missing"));
	cache_file(pcache, sha, 7); CHECK(o->can_install(&a, why, sizeof why));
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 0); CHECK(!o->can_install(&a, why, sizeof why) && !strcmp(why, "Not from a signed catalog"));    /* loose local file */
	CHECK(!o->can_uninstall(&a, why, sizeof why) && !o->can_download(&a, why, sizeof why));
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1); a.verified = 0; CHECK(!o->can_install(&a, why, sizeof why) && !strcmp(why, "Incomplete catalog data"));  /* not hardware-verified */
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1); a.sha256[3] = 'Z'; CHECK(!o->can_install(&a, why, sizeof why));                                   /* bad hash text */
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1); a.size = 4095; CHECK(!o->can_install(&a, why, sizeof why) && !strcmp(why, "Local file wrong size"));
	a = app("otherapp", "", "1.0.0", 1); CHECK(!o->can_install(&a, why, sizeof why) && !o->can_uninstall(&a, why, sizeof why));                                 /* no destination */
	a = app("otherapp", "otherapp_funkey-s.opk", "", 1); CHECK(!o->can_install(&a, why, sizeof why));
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1); snprintf(a.url, sizeof a.url, "http://github.com/x"); CHECK(!o->can_download(&a, why, sizeof why));   /* plain HTTP */
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1); CHECK(!o->can_download(&a, why, sizeof why) && !strcmp(why, "Already downloaded"));              /* cached */

	/* ---- the real engine, through production ops: install, update, uninstall of an app that is NOT RH Probe ---- */
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1);
	CHECK(o->install(&a, msg, sizeof msg) == 0);
	snprintf(p, sizeof p, "%s/otherapp_funkey-s.opk", apps); CHECK(exists(p));
	{ char h[65]; rh_sha256_file(p, h, NULL); CHECK(!strcmp(h, sha)); }                      /* the installed file is exactly the verified one */
	{ char sha2[65], f2[400]; rh_app b;
	  snprintf(f2, sizeof f2, "%s/probe2.src", root); put(f2, 9); rh_sha256_file(f2, sha2, NULL); cache_file(pcache, sha2, 9);
	  b = app("otherapp", "otherapp_funkey-s.opk", "1.1.0", 1); snprintf(b.sha256, sizeof b.sha256, "%s", sha2);
	  CHECK(o->can_update(&b, "1.0.0", why, sizeof why) && !o->can_update(&b, "1.1.0", why, sizeof why) && !o->can_update(&b, "2.0.0", why, sizeof why));   /* never a downgrade */
	  CHECK(o->update(&b, msg, sizeof msg) == 0);
	  { char h[65]; rh_sha256_file(p, h, NULL); CHECK(!strcmp(h, sha2)); } }
	a = app("otherapp", "otherapp_funkey-s.opk", "1.1.0", 1);
	CHECK(o->can_uninstall(&a, why, sizeof why) && o->uninstall(&a, msg, sizeof msg) == 0 && !exists(p));
	CHECK(o->uninstall(&a, msg, sizeof msg) == 1);                                           /* nothing installed by RetroHatch: the engine refuses */
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 0); CHECK(o->install(&a, msg, sizeof msg) == 1 && !strcmp(msg, "Not from a signed catalog"));   /* the last-moment re-check */
	a = app("notmine", "notmine_funkey-s.opk", "1.0.0", 1); snprintf(p, sizeof p, "%s/notmine_funkey-s.opk", apps); put(p, 3);
	CHECK(o->uninstall(&a, msg, sizeof msg) == 1 && exists(p));                              /* a file RetroHatch did not install is never removed */
	{ rh_app d = app("denied", "retrohatch_funkey-s.opk", "1.0.0", 1); cache_file(pcache, sha, 7); CHECK(o->install(&d, msg, sizeof msg) != 0); }          /* the engine's own denylist still applies */

	/* ---- DEV is unchanged: allowlist only, its own state dir, and nothing leaks from the production init ---- */
	c = with_net(cfg(0, dstate, dcache), key, ca, "https://catalog.invalid/"); o = rh_ops_init(&c);
	CHECK(o && o->production == 0 && strstr(o->build_label, "DEV"));
	a = app("otherapp", "otherapp_funkey-s.opk", "1.0.0", 1); cache_file(dcache, sha, 7);
	CHECK(!o->can_install(&a, why, sizeof why) && !strcmp(why, "Not allowed in DEV") && !o->can_download(&a, why, sizeof why));
	a = app("rhprobe", "rhprobe_funkey-s.opk", "1.0.0", 0); CHECK(o->can_install(&a, why, sizeof why));       /* DEV never needed the signed flag */
	c = cfg(0, dstate, dcache); o = rh_ops_init(&c); CHECK(o && !o->can_download && !o->refresh_catalog);       /* re-init without a network: the old hooks are gone */

	/* ---- production with NO published catalog: nothing verifies, nothing is installable, and the UNAPPROVED candidates stay read-only
	 * even with production ops enabled ---- */
	{
		rh_src_cfg sc; char *idx = NULL; size_t len = 0; rh_src_info si; char f[500], pkgp[400], bund[400], assets_dir[400]; rh_ui_view v; int n;
		sh("rm -rf %s/* %s/*; rm -f %s/installed.tsv %s/catalog.state", apps, pcache, pstate, pstate);
		memset(&sc, 0, sizeof sc); memset(&si, 0, sizeof si);
		snprintf(pkgp, sizeof pkgp, "%s/catalog.pkg", pstate); snprintf(bund, sizeof bund, "%s/no-bundled.pkg", root);
		sc.state_dir = pstate; sc.cache_pkg = pkgp; sc.bundled_pkg = bund; sc.keys = key; sc.nkeys = 1;
		CHECK(rh_src_load(&sc, &idx, &len, &si) != 0 && si.why[0] && !idx);                    /* no bundled and no downloaded catalog */
		sc.keys = zero; sc.nkeys = 0; memset(&si, 0, sizeof si); CHECK(rh_src_load(&sc, &idx, &len, &si) != 0 && !idx);   /* no usable key: nothing can verify */
		rh_model_load_none(&model, si.why, pstate);
		snprintf(f, sizeof f, "%s/candidates/rg-nano.json", argv[1]); rh_model_load_candidates(&model, f);
		CHECK(model.n_apps == 0 && model.n_cands >= 84 && !model.cat.ok && model.cat.status[0]);   /* only read-only candidate rows */
		c = with_net(cfg(1, pstate, pcache), key, ca, "https://catalog.invalid/"); o = rh_ops_init(&c); CHECK(o != NULL);
		setenv("SDL_VIDEODRIVER", "dummy", 0);
		CHECK(!SDL_Init(SDL_INIT_VIDEO) && SDL_SetVideoMode(240, 240, 32, SDL_SWSURFACE) != NULL);
		snprintf(assets_dir, sizeof assets_dir, "%s/ui/assets", argv[1]);
		CHECK(rh_ui_init(assets_dir, &model) == 0);
		rh_ui_set_ops(o);                                                                       /* production ops ARE enabled: candidates still cannot use them */
		keys_("a"); v = V(); CHECK(v.screen == RH_S_DISCOVER && v.count == model.n_cands);   /* every candidate row, whatever their number */
		for (n = 0; n < model.n_cands; n++) {
			keys_("a"); v = V(); CHECK(v.screen == RH_S_CAND && v.action == RH_ACT_NONE);
			keys_("aaaaa"); v = V(); CHECK(v.screen == RH_S_CAND && v.depth == 2 && !rh_ui_busy() && rh_ui_run_pending() == 0);   /* A does nothing: no install, download or preview */
			keys_("b"); CHECK(V().screen == RH_S_DISCOVER); keys_("d");
		}
		rh_ui_free(); SDL_Quit();
		snprintf(f, sizeof f, "%s/installed.tsv", pstate);
		CHECK(!exists(f));
		{ char c2[500]; snprintf(c2, sizeof c2, "test -z \"$(ls -A %s)\" && test -z \"$(ls -A %s)\"", apps, pcache); CHECK(system(c2) == 0); }   /* nothing installed, nothing downloaded */
	}

	sh("rm -rf %s", root);
	printf("%d checks, %d failed\n", checks, fails);
	return fails != 0;
}
