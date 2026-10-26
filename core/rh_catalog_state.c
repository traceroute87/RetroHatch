/* See rh_catalog_state.h. */
#define _POSIX_C_SOURCE 200809L
#include "rh_catalog_state.h"
#include "sha256.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define MAGIC "RHCS1"
#define MAXLINE 128   /* longest legal record is 99 bytes */
#define LINEBUF 256

typedef struct {
	char cur[PATH_MAX], tmp[PATH_MAX], bak[PATH_MAX];
} paths;

static int mkpaths(const char *dir, paths *p)
{
	size_t n;
	if (!dir || !*dir)
		return -1;
	n = strlen(dir);
	if (n + sizeof RH_CSTATE_FILE + 8 >= PATH_MAX)
		return -1;
	if (snprintf(p->cur, sizeof p->cur, "%s/%s", dir, RH_CSTATE_FILE) >= (int)sizeof p->cur ||
	    snprintf(p->tmp, sizeof p->tmp, "%s.tmp", p->cur) >= (int)sizeof p->tmp ||
	    snprintf(p->bak, sizeof p->bak, "%s.bak", p->cur) >= (int)sizeof p->bak)
		return -1;
	return 0;
}

static void sync_dir(const char *dir)
{
	int fd = open(dir, O_RDONLY);
	if (fd >= 0) {
		fsync(fd);
		close(fd);
	}
}

static void hex(const uint8_t *b, size_t n, char *out)
{
	size_t i;
	for (i = 0; i < n; i++) {
		out[2 * i] = "0123456789abcdef"[b[i] >> 4];
		out[2 * i + 1] = "0123456789abcdef"[b[i] & 15];
	}
	out[2 * n] = 0;
}

/* "RHCS1 <serial> <sha256> " + first 16 hex of sha256 over that text: catches accidental corruption */
static void format(const rh_cat_state *s, char *line)
{
	char h[65], body[128], chk[65];
	uint8_t d[32];
	rh_sha256 c;

	hex(s->sha256, 32, h);
	if (snprintf(body, sizeof body, MAGIC " %u %s", (unsigned)s->serial, h) >= (int)sizeof body)
		body[0] = 0;
	rh_sha256_init(&c);
	rh_sha256_update(&c, body, strlen(body));
	rh_sha256_final(&c, d);
	hex(d, 8, chk);
	if (snprintf(line, LINEBUF, "%s %s\n", body, chk) >= LINEBUF)
		line[0] = 0;
}

/* strict: the file must be byte-identical to what format() would write for the values it contains */
static int parse(const char *buf, size_t n, rh_cat_state *out)
{
	char *end, line[LINEBUF];
	unsigned long long v;
	rh_cat_state s;
	size_t i;
	const char *p;

	if (n < 20 || n >= MAXLINE || buf[n - 1] != '\n' || memcmp(buf, MAGIC " ", 6))
		return -1;
	p = buf + 6;
	if (*p < '1' || *p > '9')
		return -1;
	v = strtoull(p, &end, 10);
	if (v < 1 || v > 2147483647ULL || *end != ' ' || end - p > 10)
		return -1;
	s.serial = (uint32_t)v;
	p = end + 1;
	if ((size_t)(p - buf) + 64 + 1 >= n)
		return -1;
	for (i = 0; i < 32; i++) {
		int a = p[2 * i], b = p[2 * i + 1];
		a = a >= '0' && a <= '9' ? a - '0' : a >= 'a' && a <= 'f' ? a - 'a' + 10 : -1;
		b = b >= '0' && b <= '9' ? b - '0' : b >= 'a' && b <= 'f' ? b - 'a' + 10 : -1;
		if (a < 0 || b < 0)
			return -1;
		s.sha256[i] = (uint8_t)(a << 4 | b);
	}
	format(&s, line);
	if (strlen(line) != n || memcmp(line, buf, n))
		return -1;
	*out = s;
	return 0;
}

/* RH_ST_OK / RH_ST_NONE (file absent) / RH_ST_CORRUPT / RH_ST_IO */
static int read_one(const char *path, rh_cat_state *out)
{
	char buf[MAXLINE + 2];
	struct stat st;
	FILE *f;
	size_t n;

	if (lstat(path, &st)) {
		if (errno == ENOENT)
			return RH_ST_NONE;
		return RH_ST_IO;
	}
	if (!S_ISREG(st.st_mode))
		return RH_ST_CORRUPT;
	f = fopen(path, "rb");
	if (!f)
		return RH_ST_IO;
	n = fread(buf, 1, sizeof buf, f);
	if (ferror(f)) {
		fclose(f);
		return RH_ST_IO;
	}
	fclose(f);
	return n <= MAXLINE && !parse(buf, n, out) ? RH_ST_OK : RH_ST_CORRUPT;
}

int rh_cstate_load(const char *dir, rh_cat_state *out)
{
	paths p;
	int r;

	if (!out || mkpaths(dir, &p))
		return RH_ST_ARG;
	r = read_one(p.cur, out);
	if (r != RH_ST_NONE)
		return r;                         /* present but bad: never fall back to older data or to "first run" */
	return read_one(p.bak, out);              /* current missing, parked record present: an interrupted save */
}

#define STEP(name) do { \
	int h_ = hook ? hook(name) : 0; \
	if (h_ == 2) return RH_ST_INJECTED; \
	if (h_) { r = RH_ST_IO; goto fail; } \
} while (0)

int rh_cstate_save(const char *dir, const rh_cat_state *s, rh_cstate_hook hook)
{
	paths p;
	rh_cat_state old;
	char line[LINEBUF];
	struct stat st;
	FILE *f;
	int r, have_cur, parked = 0;

	if (!s || s->serial < 1 || s->serial > 2147483647U || mkpaths(dir, &p))
		return RH_ST_ARG;
	if (mkdir(dir, 0755) && errno != EEXIST)
		return RH_ST_IO;
	r = rh_cstate_load(dir, &old);
	if (r == RH_ST_OK) {
		if (s->serial < old.serial || (s->serial == old.serial && memcmp(s->sha256, old.sha256, 32)))
			return RH_ST_REJECTED;
		if (s->serial == old.serial && lstat(p.cur, &st) == 0) {
			unlink(p.bak);            /* identical record already stored; drop any parked leftover */
			return RH_ST_OK;
		}
	} else if (r != RH_ST_NONE) {
		return r;                         /* corrupt or unreadable: overwrite nothing */
	}
	format(s, line);

	STEP("tmp_open");
	f = fopen(p.tmp, "wb");
	if (!f)
		return RH_ST_IO;
	fputs(line, f);
	fflush(f);
	if (ferror(f) || fsync(fileno(f)) < 0) {
		fclose(f);
		unlink(p.tmp);
		return RH_ST_IO;
	}
	if (fclose(f)) {
		unlink(p.tmp);
		return RH_ST_IO;
	}
	STEP("tmp_written");
	have_cur = lstat(p.cur, &st) == 0;
	if (have_cur) {
		unlink(p.bak);                    /* stale parked record from an earlier interrupted save */
		if (rename(p.cur, p.bak)) {
			r = RH_ST_IO;
			goto fail;
		}
		parked = 1;
	}
	STEP("bak_made");
	if (rename(p.tmp, p.cur)) {
		r = RH_ST_IO;
		goto fail;
	}
	parked = 0;
	STEP("renamed");
	sync_dir(dir);
	STEP("synced");
	unlink(p.bak);
	sync_dir(dir);
	return RH_ST_OK;
fail:
	if (parked && rename(p.bak, p.cur) == 0)   /* put the old record back */
		parked = 0;
	unlink(p.tmp);
	return r;
}

int rh_catalog_verify_persist(const char *state_dir, const uint8_t *index, size_t index_len, const uint8_t *sig,
			      size_t sig_len, const uint8_t (*keys)[32], size_t nkeys, const char *device,
			      const char *firmware, rh_cat_info *info, const char **why, rh_cstate_hook hook)
{
	rh_cat_state prev, next;
	const char *w = "";
	int have = 0, rc, r;

	r = rh_cstate_load(state_dir, &prev);
	if (r == RH_ST_OK) {
		have = 1;
	} else if (r != RH_ST_NONE) {
		if (why)
			*why = r == RH_ST_CORRUPT ? "stored rollback state is corrupt; refusing (not resetting trust)"
						  : "cannot read stored rollback state; refusing";
		return RH_CAT_E_STATE;
	}
	rc = rh_catalog_verify(index, index_len, sig, sig_len, keys, nkeys, device, firmware, have ? &prev : NULL, &next, info, &w);
	if (rc) {
		if (why)
			*why = w;
		return rc;                        /* nothing is written unless the catalog verified completely */
	}
	r = rh_cstate_save(state_dir, &next, hook); /* identical record: no rewrite, only drops a parked leftover */
	if (r != RH_ST_OK) {
		if (why)
			*why = "catalog verified but rollback state could not be saved; not trusting it";
		return RH_CAT_E_STATE;
	}
	if (why)
		*why = "";
	return RH_CAT_OK;
}
