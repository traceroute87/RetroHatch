#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <stdlib.h>
#include <sys/statvfs.h>
#include "../platforms/nano/rh_install.h"
#include "../core/rh_net.h"
#include "rh_ops.h"
#include "rh_source.h"

/* The only things DEV may install. Exact id + exact file name. */
static const struct { const char *id, *dest; } ALLOWED[] = {
	{"rhprobe", "rhprobe_funkey-s.opk"},
};

static rh_cfg eng;
static char cache[256];
static void (*refresh_fn)(void);
static rh_net_cfg net;
static rh_src_cfg srccfg;
static char base_url[512], last_net[96] = "None yet";
static struct { char from[200], to[200]; } mirror[4];
static int n_mirror, net_on;
static int (*prog_cb)(uint64_t, uint64_t);

static int is_hex64(const char *s)
{
	int i;
	if (strlen(s) != 64) return 0;
	for (i = 0; i < 64; i++) if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
	return 1;
}

/* shared gate for install and update: allowlist, complete verified metadata, local file present with the right size.
 * what = noun for the file in messages ("Local file" / "Update file"). */
static int gate(const rh_app *a, const char *what, char *why, size_t n)
{
	char path[320]; struct stat st; size_t i;
	for (i = 0; i < sizeof ALLOWED / sizeof *ALLOWED; i++)
		if (!strcmp(a->id, ALLOWED[i].id) && !strcmp(a->dest_name, ALLOWED[i].dest)) break;
	if (i == sizeof ALLOWED / sizeof *ALLOWED) { snprintf(why, n, "Not allowed in DEV"); return 0; }
	if (!a->verified || !is_hex64(a->sha256) || !a->size || !a->version[0]) { snprintf(why, n, "Incomplete catalog data"); return 0; }
	snprintf(path, sizeof path, "%s/%s.opk", cache, a->sha256);
	if (lstat(path, &st) || !S_ISREG(st.st_mode)) { snprintf(why, n, "%s missing", what); return 0; }
	if ((unsigned long long)st.st_size != a->size) { snprintf(why, n, "%s wrong size", what); return 0; }
	return 1;
}

static int can_install(const rh_app *a, char *why, size_t n) { return gate(a, "Local file", why, n); }

static int can_update(const rh_app *a, const char *installed_ver, char *why, size_t n)
{
	if (rh_ver_cmp(installed_ver, a->version) >= 0) { snprintf(why, n, "Not a newer version"); return 0; }   /* never a downgrade */
	return gate(a, "Update file", why, n);
}

static int run(const rh_app *a, int upd, char *msg, size_t n)
{
	char src[320], why[40]; rh_pkg p; rh_err e;
	if (!gate(a, upd ? "Update file" : "Local file", why, sizeof why)) { snprintf(msg, n, "%s", why); return 1; }   /* re-check at the last moment */
	snprintf(src, sizeof src, "%s/%s.opk", cache, a->sha256);
	p.app_id = a->id; p.version = a->version; p.dest_name = a->dest_name;
	p.src_path = src; p.size = a->size; p.sha256 = a->sha256;
	e = rh_install(&eng, &p);                       /* the engine does every real check and the file work */
	if (e == RH_OK) return 0;
	if (e == RH_E_HASH) snprintf(msg, n, "SHA-256 mismatch");
	else { const char *s = rh_strerr(e); snprintf(msg, n, "%c%s", s[0] >= 'a' && s[0] <= 'z' ? s[0] - 32 : s[0], s + 1); }
	return e == RH_E_RECOVER ? 2 : 1;
}

/* uninstall: only the approved (id, file) pair; the engine verifies record, hash, mount state and space */
static int approved(const rh_app *a)
{
	size_t i;
	for (i = 0; i < sizeof ALLOWED / sizeof *ALLOWED; i++)
		if (!strcmp(a->id, ALLOWED[i].id) && !strcmp(a->dest_name, ALLOWED[i].dest)) return 1;
	return 0;
}

static int can_uninstall(const rh_app *a, char *why, size_t n)
{
	if (approved(a)) return 1;
	snprintf(why, n, "Not allowed in DEV");
	return 0;
}

static int uninstall(const rh_app *a, char *msg, size_t n)
{
	rh_err e;
	if (!approved(a)) { snprintf(msg, n, "Not allowed in DEV"); return 1; }
	e = rh_uninstall(&eng, a->id, a->dest_name);
	if (e == RH_OK) return 0;
	if (e == RH_E_UNMANAGED) snprintf(msg, n, "Not installed by RetroHatch, or changed");
	else { const char *s = rh_strerr(e); snprintf(msg, n, "%c%s", s[0] >= 'a' && s[0] <= 'z' ? s[0] - 32 : s[0], s + 1); }
	return e == RH_E_RECOVER ? 2 : 1;
}

/* ---- network: download into the cache, refresh the signed catalog. Neither installs anything. ---- */
static int net_progress(uint64_t done, uint64_t total, void *ctx)
{
	(void)ctx;
	return prog_cb ? prog_cb(done, total) : 0;
}

static void map_url(const char *in, char *out, size_t n)   /* DEV test servers only: a mirror file maps URL prefixes */
{
	int i;
	for (i = 0; i < n_mirror; i++)
		if (!strncmp(in, mirror[i].from, strlen(mirror[i].from))) { snprintf(out, n, "%s%s", mirror[i].to, in + strlen(mirror[i].from)); return; }
	snprintf(out, n, "%s", in);
}

static int can_download(const rh_app *a, char *why, size_t n)
{
	char path[320]; struct stat st;
	if (!net_on) { snprintf(why, n, "Downloads are off"); return 0; }
	if (!approved(a)) { snprintf(why, n, "Not allowed in DEV"); return 0; }
	if (!a->verified || !is_hex64(a->sha256) || !a->size || !a->version[0] || strncmp(a->url, "https://", 8)) { snprintf(why, n, "Incomplete catalog data"); return 0; }
	snprintf(path, sizeof path, "%s/%s.opk", cache, a->sha256);
	if (!lstat(path, &st)) { snprintf(why, n, "Already downloaded"); return 0; }
	return 1;
}

static int download(const rh_app *a, char *msg, size_t n)
{
	char why[48], url[512], dest[320], em[120]; struct statvfs sv; int rc;
	if (!can_download(a, why, sizeof why)) { snprintf(msg, n, "%s", why); return 1; }
	if (!statvfs(cache, &sv) && (unsigned long long)sv.f_bavail * sv.f_frsize < a->size + (1u << 20)) { snprintf(msg, n, "Not enough free space"); return 1; }
	map_url(a->url, url, sizeof url);
	snprintf(dest, sizeof dest, "%s/%s.opk", cache, a->sha256);
	rc = rh_net_get_file(&net, url, dest, a->size, a->size, a->sha256, em, sizeof em);   /* size and SHA-256 from the signed catalog */
	if (rc == RH_NET_OK) { snprintf(last_net, sizeof last_net, "Downloaded %.40s", a->name); return 0; }
	snprintf(msg, n, "%s", rc == RH_NET_E_OFFLINE ? "No internet connection" : em);
	snprintf(last_net, sizeof last_net, "%s", msg);
	return rc == RH_NET_E_CANCEL ? 1 : 1;
}

static int refresh_catalog(char *msg, size_t n)
{
	char em[120]; int rc;
	if (!net_on) { snprintf(msg, n, "Downloads are off"); return 1; }
	rc = rh_src_refresh(&srccfg, &net, base_url, em, sizeof em);
	snprintf(msg, n, "%s", em);
	snprintf(last_net, sizeof last_net, "%s", em);
	return rc ? 1 : 0;
}

static const char *net_status(void) { return last_net; }

static int install(const rh_app *a, char *msg, size_t n) { return run(a, 0, msg, n); }
static int update(const rh_app *a, char *msg, size_t n) { return run(a, 1, msg, n); }

static rh_ui_ops ops = {can_install, can_update, update, can_uninstall, uninstall, install, NULL, "DEV (install/update/uninstall)",
	NULL, NULL, NULL, NULL};

static void read_mirror(const char *path)
{
	FILE *f = path ? fopen(path, "r") : NULL; char l[512];
	n_mirror = 0;
	if (!f) return;
	while (n_mirror < 4 && fgets(l, sizeof l, f))
		if (sscanf(l, "%199s %199s", mirror[n_mirror].from, mirror[n_mirror].to) == 2 && !strncmp(mirror[n_mirror].from, "https://", 8) && !strncmp(mirror[n_mirror].to, "https://", 8)) n_mirror++;
	fclose(f);
}

const rh_ui_ops *rh_ops_init(const rh_ops_cfg *c)
{
	const char *base; size_t n, sn;
	if (!c || !c->apps_dir || !c->state_dir || !c->cache_dir) return NULL;
	sn = strlen(c->state_dir);
	base = strrchr(c->state_dir, '/');
	if (!base || strcmp(base + 1, ".retrohatch-dev")) return NULL;       /* DEV state dir only */
	if (!strcmp(c->state_dir, RH_NANO_STATE_DIR)) return NULL;          /* belt and braces: never production */
	n = strlen(c->cache_dir);
	if (n <= sn + 1 || strncmp(c->cache_dir, c->state_dir, sn) || c->cache_dir[sn] != '/' || strstr(c->cache_dir, "..")) return NULL;
	if (n >= sizeof cache) return NULL;
	memset(&eng, 0, sizeof eng);
	eng.apps_dir = c->apps_dir; eng.state_dir = c->state_dir;
	eng.proc_mounts = c->proc_mounts ? c->proc_mounts : "/proc/mounts";
	eng.sys_block = c->sys_block ? c->sys_block : "/sys/block";
	eng.hook = c->hook;
	snprintf(cache, sizeof cache, "%s", c->cache_dir);
	refresh_fn = c->refresh; ops.refresh = refresh_fn;
	net_on = c->ca_bundle && c->keys && c->nkeys && c->cache_pkg && c->base_url;
	if (net_on) {
		FILE *f; size_t k;
		memset(&net, 0, sizeof net);
		net.ca_bundle = c->ca_bundle; net.extra_ca = c->extra_ca; net.progress = net_progress; prog_cb = c->progress;
		srccfg.state_dir = c->state_dir; srccfg.cache_pkg = c->cache_pkg; srccfg.bundled_pkg = c->bundled_pkg;
		srccfg.keys = c->keys; srccfg.nkeys = c->nkeys;
		snprintf(base_url, sizeof base_url, "%s", c->base_url);
		if (c->base_url_file && (f = fopen(c->base_url_file, "r"))) {   /* DEV: point the build at a test server */
			char l[512];
			if (fgets(l, sizeof l, f)) { l[strcspn(l, "\r\n ")] = 0; if (!strncmp(l, "https://", 8)) snprintf(base_url, sizeof base_url, "%s", l); }
			fclose(f);
		}
		k = strlen(base_url);
		if (k && base_url[k - 1] != '/' && k + 1 < sizeof base_url) { base_url[k] = '/'; base_url[k + 1] = 0; }
		read_mirror(c->mirror_file);
		ops.can_download = can_download; ops.download = download; ops.refresh_catalog = refresh_catalog; ops.net_status = net_status;
	}
	return &ops;
}

int rh_ops_recover(void) { return rh_recover(&eng); }
