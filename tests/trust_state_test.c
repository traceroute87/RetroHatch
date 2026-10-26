/* Rollback-state storage tests (core/rh_catalog_state.c): format, corruption, monotonic rule, interrupted writes,
 * failed renames. Temp dirs only. Build/run: make -C tests state-test */
#define _DEFAULT_SOURCE
#include "../core/rh_catalog_state.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)

static char dir[256], cur[512], tmp[512], bak[512];

static rh_cat_state mk(uint32_t serial, int tag)
{
	rh_cat_state s;
	memset(s.sha256, tag, 32);
	s.serial = serial;
	return s;
}

static int same(const rh_cat_state *a, const rh_cat_state *b) { return a->serial == b->serial && !memcmp(a->sha256, b->sha256, 32); }

static void fresh(void)
{
	char cmd[600];
	snprintf(cmd, sizeof cmd, "rm -rf '%s'", dir);
	if (system(cmd)) {}
	mkdir(dir, 0755);
}

static void put(const char *path, const void *data, size_t n)
{
	FILE *f = fopen(path, "wb");
	fwrite(data, 1, n, f);
	fclose(f);
}

static size_t slurp(const char *path, char *buf, size_t cap)
{
	FILE *f = fopen(path, "rb");
	size_t n;
	if (!f) return 0;
	n = fread(buf, 1, cap, f);
	fclose(f);
	return n;
}

static int exists(const char *p) { struct stat st; return lstat(p, &st) == 0; }

static const char *crash_at, *err_at;
static int hook(const char *step)
{
	if (crash_at && !strcmp(step, crash_at)) return 2;
	if (err_at && !strcmp(step, err_at)) return 1;
	return 0;
}

int main(void)
{
	rh_cat_state a = mk(3, 0xaa), b = mk(5, 0xbb), got;
	char buf[256], line[4200];
	size_t n, i;
	int bit;
	static const char *steps[] = {"tmp_open", "tmp_written", "bak_made", "renamed", "synced"};

	snprintf(dir, sizeof dir, "/tmp/rhstate-test-%d", (int)getpid());
	snprintf(cur, sizeof cur, "%s/catalog.state", dir);
	snprintf(tmp, sizeof tmp, "%s.tmp", cur);
	snprintf(bak, sizeof bak, "%s.bak", cur);

	/* first run, round trip, exact format */
	fresh();
	CHECK(rh_cstate_load(dir, &got) == RH_ST_NONE);
	CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &a));
	n = slurp(cur, line, sizeof line);
	CHECK(n > 20 && n < 110 && !memcmp(line, "RHCS1 3 ", 8) && line[n - 1] == '\n');
	CHECK(!exists(tmp) && !exists(bak));
	CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_OK && rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &b));
	CHECK(!exists(tmp) && !exists(bak));
	CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_OK);                          /* identical: no-op */

	/* monotonic: never lower, never fork */
	{
		rh_cat_state lower = mk(4, 0xcc), fork = mk(5, 0xdd);
		CHECK(rh_cstate_save(dir, &lower, NULL) == RH_ST_REJECTED);
		CHECK(rh_cstate_save(dir, &fork, NULL) == RH_ST_REJECTED);
		CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &b));
	}
	{
		rh_cat_state bad = mk(0, 1);
		CHECK(rh_cstate_save(dir, &bad, NULL) == RH_ST_ARG);
		bad.serial = 2147483648U;
		CHECK(rh_cstate_save(dir, &bad, NULL) == RH_ST_ARG);
		CHECK(rh_cstate_save(NULL, &a, NULL) == RH_ST_ARG && rh_cstate_load("", &got) == RH_ST_ARG);
	}

	/* every single-bit corruption of the stored file is refused (never accepted, never "first run") */
	fresh();
	CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_OK);
	n = slurp(cur, buf, sizeof buf);
	for (i = 0; i < n; i++)
		for (bit = 0; bit < 8; bit++) {
			char m[256];
			memcpy(m, buf, n);
			m[i] ^= (char)(1 << bit);
			put(cur, m, n);
			CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		}
	/* structural corruption */
	{
		put(cur, "", 0);
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		put(cur, "\n", 1);
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		put(cur, buf, n - 1);                                                  /* missing final newline */
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		put(cur, buf, n - 3);                                                  /* truncated */
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		memcpy(line, buf, n); line[n] = 'x';
		put(cur, line, n + 1);                                                 /* trailing garbage */
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		memcpy(line, buf, n); memcpy(line + n, buf, n);
		put(cur, line, 2 * n);                                                 /* two records */
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		memset(line, 'A', 4096);
		put(cur, line, 4096);                                                  /* oversized */
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
	}
	{
		const char *txt[] = {
			"RHCS1 05 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 0000000000000000\n",  /* leading zero */
			"RHCS1 0 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 0000000000000000\n",   /* serial 0 */
			"RHCS1 2147483648 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 0000000000000000\n",
			"RHCS1 -5 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 0000000000000000\n",
			"RHCS1 5 BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB 0000000000000000\n",  /* uppercase hex */
			"RHCS1 5 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 0000000000000000\n",  /* wrong check */
		};
		for (i = 0; i < sizeof txt / sizeof *txt; i++) {
			put(cur, txt[i], strlen(txt[i]));
			CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
			CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_CORRUPT);              /* never overwrites a bad record */
		}
		unlink(cur);
		mkdir(cur, 0755);                                                       /* a directory where the file should be */
		CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
		CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_CORRUPT);
		rmdir(cur);
	}
	/* corrupt current + valid .bak: still refused (no silent fallback to older trust) */
	fresh();
	CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK);
	n = slurp(cur, buf, sizeof buf);
	put(bak, buf, n);
	put(cur, "garbage\n", 8);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
	/* lone valid .bak (interrupted save) is recovered; corrupt lone .bak is refused */
	unlink(cur);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &a));
	put(bak, "garbage\n", 8);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_CORRUPT);
	/* deleting every state file looks like a first run: the documented limitation */
	unlink(bak);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_NONE);

	/* interrupted writes: crash at every step. Afterwards state is the old or the new record, never none or corrupt */
	for (i = 0; i < sizeof steps / sizeof *steps; i++) {
		fresh();
		CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK);
		crash_at = steps[i]; err_at = NULL;
		CHECK(rh_cstate_save(dir, &b, hook) == RH_ST_INJECTED);
		crash_at = NULL;
		CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && (same(&got, &a) || same(&got, &b)));
		if (!strcmp(steps[i], "renamed") || !strcmp(steps[i], "synced"))
			CHECK(same(&got, &b));
		if (!strcmp(steps[i], "tmp_open") || !strcmp(steps[i], "tmp_written") || !strcmp(steps[i], "bak_made"))
			CHECK(same(&got, &a));
		CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK || same(&got, &b));         /* may not go back once b landed */
		CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_OK);                          /* retry completes */
		CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &b));
		CHECK(!exists(tmp) && !exists(bak));
	}
	/* crash during the very first save: either nothing (first run) or the record, never corrupt */
	for (i = 0; i < sizeof steps / sizeof *steps; i++) {
		int r;
		fresh();
		crash_at = steps[i]; err_at = NULL;
		CHECK(rh_cstate_save(dir, &a, hook) == RH_ST_INJECTED);
		crash_at = NULL;
		r = rh_cstate_load(dir, &got);
		CHECK(r == RH_ST_NONE || (r == RH_ST_OK && same(&got, &a)));
		CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK && rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &a));
	}
	/* injected I/O errors: old record kept intact, no stray files */
	for (i = 0; i < sizeof steps / sizeof *steps; i++) {
		fresh();
		CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK);
		crash_at = NULL; err_at = steps[i];
		CHECK(rh_cstate_save(dir, &b, hook) == RH_ST_IO);
		err_at = NULL;
		CHECK(rh_cstate_load(dir, &got) == RH_ST_OK);
		if (!strcmp(steps[i], "renamed") || !strcmp(steps[i], "synced"))
			CHECK(same(&got, &b));
		else
			CHECK(same(&got, &a));
		CHECK(!exists(tmp));
		CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_OK && rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &b));
		CHECK(!exists(tmp) && !exists(bak));
	}
	/* real failed rename: a non-empty directory squats on the .bak name, so parking the old record fails */
	fresh();
	CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK);
	mkdir(bak, 0755);
	snprintf(line, sizeof line, "%s/x", bak);
	put(line, "x", 1);
	CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_IO);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &a) && !exists(tmp));
	/* real failed open: a directory squats on the .tmp name */
	fresh();
	CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK);
	mkdir(tmp, 0755);
	CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_IO);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &a));
	/* stale tmp from an earlier crash is ignored by load and replaced by save */
	fresh();
	CHECK(rh_cstate_save(dir, &a, NULL) == RH_ST_OK);
	put(tmp, "stale", 5);
	CHECK(rh_cstate_load(dir, &got) == RH_ST_OK && same(&got, &a));
	CHECK(rh_cstate_save(dir, &b, NULL) == RH_ST_OK && !exists(tmp));
	/* missing state dir is created (one level); a missing parent is an error, not a silent skip */
	{
		char sub[600];
		fresh();
		snprintf(sub, sizeof sub, "%s/new", dir);
		CHECK(rh_cstate_save(sub, &a, NULL) == RH_ST_OK && rh_cstate_load(sub, &got) == RH_ST_OK && same(&got, &a));
		snprintf(sub, sizeof sub, "%s/no/such/dir", dir);
		CHECK(rh_cstate_save(sub, &a, NULL) == RH_ST_IO);
		CHECK(rh_cstate_load(sub, &got) == RH_ST_NONE);
	}
	{
		char cmd[600];
		snprintf(cmd, sizeof cmd, "rm -rf '%s'", dir);
		if (system(cmd)) {}
	}
	if (fails) {
		printf("%d FAILED\n", fails);
		return 1;
	}
	printf("state tests OK\n");
	return 0;
}
