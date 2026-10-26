/* Host/ARM driver for the signed-catalog verifier (core/rh_catalog.c). Read-only: opens the files named on the
 * command line and nothing else; never writes, never touches a network. Used by tests/test_trust_native.py.
 *
 *   rh_verify --index F --sig F --pubkey HEX... --device ID --firmware ID [--state F] [--stats] [--repeat N]
 *   rh_verify ... --state-dir DIR [--inject STEP:err|crash]   (persistent rollback state; the only mode that writes, only DIR)
 *   rh_verify --batch LIST ...   (LIST lines: "<index> <sig>"; one result line per case; --state is read, never written)
 * Exit 0 only for RH_CAT_OK. State file: "<serial> <sha256 hex>\n" (host tests only; the Nano side persists its own). */
#define _POSIX_C_SOURCE 200809L /* clock_gettime under -std=c99 */
#include "../../../core/rh_catalog_state.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef __linux__
#include <sys/resource.h>
#endif

#define MAXKEYS 8

static const char *inject_step, *inject_mode; /* test seam: --inject STEP:err|crash (crash = power loss at that step) */
static int inject_hook(const char *step)
{
	if (inject_step && !strcmp(step, inject_step))
		return !strcmp(inject_mode, "crash") ? 2 : 1;
	return 0;
}

static uint8_t *slurp(const char *path, size_t cap, size_t *n)
{
	FILE *f = fopen(path, "rb");
	uint8_t *b;

	*n = 0;
	if (!f)
		return NULL;
	b = malloc(cap + 2);
	if (b) {
		*n = fread(b, 1, cap + 1, f); /* one byte over the cap is enough to make the verifier refuse */
		if (*n > cap + 1)
			*n = cap + 1;
	}
	fclose(f);
	return b;
}

static int unhex(const char *s, uint8_t *out, size_t n)
{
	size_t i;

	if (strlen(s) != 2 * n)
		return -1;
	for (i = 0; i < 2 * n; i++) {
		int c = s[i], v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
		if (v < 0)
			return -1;
		out[i / 2] = (uint8_t)(out[i / 2] << 4 | v);
	}
	return 0;
}

static int one(const char *ipath, const char *spath, uint8_t (*keys)[32], size_t nk, const char *dev, const char *fw,
	       const rh_cat_state *prev, const char *state_dir, int quiet)
{
	size_t il, sl;
	uint8_t *ib = slurp(ipath, RH_CAT_MAX_INDEX, &il), *sb = slurp(spath, RH_CAT_MAX_SIG, &sl);
	rh_cat_state next;
	rh_cat_info info;
	const char *why = "";
	static const uint8_t none = 0;
	int rc;

	if (state_dir) {
		memset(&next, 0, sizeof next);
		rc = rh_catalog_verify_persist(state_dir, ib ? ib : &none, il, sb ? sb : &none, sl, keys, nk, dev, fw, &info, &why,
					       inject_step ? inject_hook : NULL);
	} else {
		rc = rh_catalog_verify(ib ? ib : &none, il, sb ? sb : &none, sl, keys, nk, dev, fw, prev, &next, &info, &why);
	}
	if (quiet) {
		free(ib);
		free(sb);
		return rc;
	}
	if (rc == RH_CAT_OK) {
		int i;
		printf("OK serial=%u apps=%u artifacts=%u", info.serial, info.n_apps, info.n_artifacts);
		if (!state_dir) { /* persist mode keeps its own state and never fills `next` */
			printf(" sha256=");
			for (i = 0; i < 32; i++)
				printf("%02x", next.sha256[i]);
		}
		printf("%s%s\n", info.expires[0] ? " expires=" : "", info.expires);
	} else {
		printf("FAIL %d %s\n", rc, why);
	}
	free(ib);
	free(sb);
	return rc;
}

int main(int argc, char **argv)
{
	uint8_t keys[MAXKEYS][32];
	size_t nk = 0;
	const char *idx = NULL, *sig = NULL, *dev = NULL, *fw = NULL, *state = NULL, *batch = NULL, *state_dir = NULL;
	rh_cat_state prev;
	int have_prev = 0, stats = 0, rc = 64, i, rep = 0;

	memset(keys, 0, sizeof keys);
	for (i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--stats")) stats = 1;
		else if (i + 1 >= argc) return 64;
		else if (!strcmp(argv[i], "--index")) idx = argv[++i];
		else if (!strcmp(argv[i], "--sig")) sig = argv[++i];
		else if (!strcmp(argv[i], "--device")) dev = argv[++i];
		else if (!strcmp(argv[i], "--firmware")) fw = argv[++i];
		else if (!strcmp(argv[i], "--state")) state = argv[++i];
		else if (!strcmp(argv[i], "--state-dir")) state_dir = argv[++i];
		else if (!strcmp(argv[i], "--inject")) {
			static char spec[64];
			char *c;
			snprintf(spec, sizeof spec, "%s", argv[++i]);
			c = strchr(spec, ':');
			if (!c) return 64;
			*c = 0;
			inject_step = spec;
			inject_mode = c + 1;
		}
		else if (!strcmp(argv[i], "--repeat")) rep = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--batch")) batch = argv[++i];
		else if (!strcmp(argv[i], "--pubkey")) {
			if (nk >= MAXKEYS || unhex(argv[++i], keys[nk], 32)) { printf("FAIL %d bad --pubkey\n", RH_CAT_E_ARG); return 64; }
			nk++;
		} else return 64;
	}
	if (!dev || !fw || (!batch && (!idx || !sig)))
		return 64;
	if (state) {
		FILE *f = fopen(state, "r");
		char hex[80];
		unsigned long s;
		if (f && fscanf(f, "%lu %64s", &s, hex) == 2 && !unhex(hex, prev.sha256, 32)) {
			prev.serial = (uint32_t)s;
			have_prev = 1;
		}
		if (f) fclose(f);
	}
	if (batch) {
		FILE *l = fopen(batch, "r");
		char a[1024], b[1024];
		int n = 0;
		if (!l) return 64;
		while (fscanf(l, "%1023s %1023s", a, b) == 2) {
			printf("%d ", n++);
			one(a, b, keys, nk, dev, fw, have_prev ? &prev : NULL, state_dir, 0);
		}
		fclose(l);
		rc = 0;
	} else {
		rc = one(idx, sig, keys, nk, dev, fw, have_prev ? &prev : NULL, state_dir, 0);
		if (rep > 1) { /* timing: whole call incl. reading both files, parse, policy, SHA-256 and Ed25519 */
			struct timespec a, b;
			double ms, tot = 0, mn = 1e9, mx = 0;
			int k;
			for (k = 0; k < rep; k++) {
				clock_gettime(CLOCK_MONOTONIC, &a);
				one(idx, sig, keys, nk, dev, fw, have_prev ? &prev : NULL, state_dir, 1);
				clock_gettime(CLOCK_MONOTONIC, &b);
				ms = (b.tv_sec - a.tv_sec) * 1000.0 + (b.tv_nsec - a.tv_nsec) / 1e6;
				tot += ms;
				if (ms < mn) mn = ms;
				if (ms > mx) mx = ms;
			}
			printf("timing: %d runs avg %.2f ms min %.2f max %.2f\n", rep, tot / rep, mn, mx);
		}
	}
#ifdef __linux__
	if (stats) {
		struct rusage ru;
		getrusage(RUSAGE_SELF, &ru);
		fprintf(stderr, "maxrss_kb=%ld\n", ru.ru_maxrss);
	}
#else
	(void)stats;
#endif
	return rc;
}
