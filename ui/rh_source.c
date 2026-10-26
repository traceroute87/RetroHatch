#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "../core/rh_catalog_state.h"
#include "rh_source.h"

#define MAX_PKG (RH_CAT_MAX_INDEX + RH_CAT_MAX_SIG + 2)

static uint8_t *read_file(const char *path, size_t cap, size_t *n)
{
	struct stat st;
	FILE *f;
	uint8_t *b;

	*n = 0;
	if (!path || lstat(path, &st) || !S_ISREG(st.st_mode) || (unsigned long long)st.st_size > cap)
		return NULL;
	if (!(f = fopen(path, "rb")))
		return NULL;
	b = malloc((size_t)st.st_size + 1);
	if (b && (*n = fread(b, 1, (size_t)st.st_size, f)) != (size_t)st.st_size) { free(b); b = NULL; *n = 0; }
	fclose(f);
	return b;
}

/* pkg = sigdoc '\n' index */
static int split_pkg(const uint8_t *b, size_t n, const uint8_t **sig, size_t *sl, const uint8_t **idx, size_t *il)
{
	const uint8_t *nl = memchr(b, '\n', n < RH_CAT_MAX_SIG + 1 ? n : RH_CAT_MAX_SIG + 1);
	if (!nl)
		return -1;
	*sig = b; *sl = (size_t)(nl - b); *idx = nl + 1; *il = n - *sl - 1;
	return *sl && *il ? 0 : -1;
}

static int verify_pkg(const rh_src_cfg *c, const uint8_t *b, size_t n, rh_cat_info *ci, const char **why)
{
	const uint8_t *sig, *idx;
	size_t sl, il;
	if (split_pkg(b, n, &sig, &sl, &idx, &il)) { *why = "Catalog file is damaged"; return RH_CAT_E_PARSE; }
	return rh_catalog_verify_persist(c->state_dir, idx, il, sig, sl, c->keys, c->nkeys, RH_DEVICE_ID, RH_FIRMWARE_ID, ci, why, NULL);
}

static const char *reason_text(int rc, const char *why)
{
	switch (rc) {
	case RH_CAT_E_NOKEY: return "This build has no trusted catalog key";
	case RH_CAT_E_BADSIG: case RH_CAT_E_UNKNOWN_KEY: case RH_CAT_E_SIGDOC: return "Catalog signature check failed";
	case RH_CAT_E_ROLLBACK: case RH_CAT_E_FORK: return "Catalog is older than one already accepted";
	default: return why && *why ? why : "Catalog rejected";
	}
}

int rh_src_load(const rh_src_cfg *c, char **index, size_t *len, rh_src_info *info)
{
	char newp[600];
	const char *names[3], *srcs[3] = {"bundled", "cached", "cached"};
	int i, best = -1, state_bad = 0;
	uint8_t *keep = NULL;
	size_t keep_len = 0;
	unsigned best_serial = 0;
	char first_why[96] = "";

	memset(info, 0, sizeof *info);
	snprintf(newp, sizeof newp, "%s.new", c->cache_pkg);
	names[0] = c->bundled_pkg; names[1] = c->cache_pkg; names[2] = newp;
	for (i = 0; i < 3; i++) {
		size_t n;
		uint8_t *b = read_file(names[i], MAX_PKG, &n);
		rh_cat_info ci;
		const char *why = "";
		int rc;
		if (!b) continue;
		rc = verify_pkg(c, b, n, &ci, &why);
		if (rc == RH_CAT_E_STATE) { state_bad = 1; snprintf(info->why, sizeof info->why, "%s", why); }
		if (rc) {
			if (!first_why[0] && rc != RH_CAT_E_ROLLBACK && rc != RH_CAT_E_FORK) snprintf(first_why, sizeof first_why, "%s", reason_text(rc, why));
			if (!first_why[0]) snprintf(first_why, sizeof first_why, "%s", reason_text(rc, why));
		} else if (best < 0 || ci.serial >= best_serial) {
			const uint8_t *sig = NULL, *idx = NULL;
			size_t sl = 0, il = 0;
			free(keep);
			keep = split_pkg(b, n, &sig, &sl, &idx, &il) ? NULL : malloc(il + 1);
			if (keep) { memcpy(keep, idx, il); keep[il] = 0; keep_len = il; }
			best = keep ? i : -1; best_serial = ci.serial;
			snprintf(info->source, sizeof info->source, "%s", srcs[i]);
			info->serial = ci.serial;
			snprintf(info->expires, sizeof info->expires, "%s", ci.expires);
		}
		free(b);
	}
	if (best >= 0) {
		*index = (char *)keep; *len = keep_len; info->why[0] = 0;
		return 0;
	}
	free(keep);
	if (!state_bad)
		snprintf(info->why, sizeof info->why, "%s", first_why[0] ? first_why : "No signed catalog found on this device");
	info->source[0] = 0;
	return 1;
}

static int write_atomic(const char *path, const uint8_t *a, size_t an, const uint8_t *b, size_t bn)
{
	FILE *f = fopen(path, "wb");
	if (!f) return -1;
	if (fwrite(a, 1, an, f) != an || fputc('\n', f) == EOF || fwrite(b, 1, bn, f) != bn || fflush(f) || fsync(fileno(f)) < 0) { fclose(f); unlink(path); return -1; }
	return fclose(f) ? -1 : 0;
}

int rh_src_refresh(const rh_src_cfg *c, const rh_net_cfg *net, const char *base_url, char *msg, size_t n)
{
	char url[512], idxp[600], sigp[600], newp[600], emsg[120];
	uint8_t *ib = NULL, *sb = NULL, *old = NULL;
	size_t il = 0, sl = 0, on = 0;
	rh_cat_info ci;
	const char *why = "";
	int rc, ret = 1;

	snprintf(idxp, sizeof idxp, "%s.idx.dl", c->cache_pkg);
	snprintf(sigp, sizeof sigp, "%s.sig.dl", c->cache_pkg);
	snprintf(newp, sizeof newp, "%s.new", c->cache_pkg);
	if (!base_url || !*base_url || base_url[strlen(base_url) - 1] != '/' || strlen(base_url) > 400) { snprintf(msg, n, "No catalog address set"); return 1; }
	snprintf(url, sizeof url, "%sindex.json", base_url);
	rc = rh_net_get_file(net, url, idxp, RH_CAT_MAX_INDEX, 0, NULL, emsg, sizeof emsg);
	if (rc) { snprintf(msg, n, "%s", rc == RH_NET_E_OFFLINE ? "No internet connection" : emsg); goto out; }
	snprintf(url, sizeof url, "%sindex.json.sig", base_url);
	rc = rh_net_get_file(net, url, sigp, RH_CAT_MAX_SIG, 0, NULL, emsg, sizeof emsg);
	if (rc) { snprintf(msg, n, "%s", rc == RH_NET_E_OFFLINE ? "No internet connection" : emsg); goto out; }
	ib = read_file(idxp, RH_CAT_MAX_INDEX, &il);
	sb = read_file(sigp, RH_CAT_MAX_SIG, &sl);
	if (!ib || !sb || !il || !sl) { snprintf(msg, n, "Catalog download was empty"); goto out; }
	{
		uint8_t *pkg = malloc(sl + 1 + il);
		if (!pkg) { snprintf(msg, n, "Out of memory"); goto out; }
		memcpy(pkg, sb, sl); pkg[sl] = '\n'; memcpy(pkg + sl + 1, ib, il);
		if (write_atomic(newp, sb, sl, ib, il)) { free(pkg); snprintf(msg, n, "Cannot write to storage"); goto out; }
		rc = verify_pkg(c, pkg, sl + 1 + il, &ci, &why);     /* signature, policy and rollback; advances the saved serial only on success */
		old = read_file(c->cache_pkg, MAX_PKG, &on);
		if (rc) {
			unlink(newp);
			snprintf(msg, n, "%s", reason_text(rc, why));
		} else if (old && on == sl + 1 + il && !memcmp(old, pkg, on)) {
			unlink(newp);
			snprintf(msg, n, "Catalog is already up to date (serial %u)", ci.serial);
			ret = 0;
		} else if (rename(newp, c->cache_pkg)) {
			snprintf(msg, n, "Cannot write to storage");        /* rh_src_load still finds the verified .new copy */
		} else {
			snprintf(msg, n, "Catalog updated: serial %u, %u apps", ci.serial, ci.n_apps);
			ret = 0;
		}
		free(pkg);
	}
out:
	free(ib); free(sb); free(old);
	unlink(idxp); unlink(sigp);
	return ret;
}
