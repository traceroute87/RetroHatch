#define _XOPEN_SOURCE 700
#include "rh_install.h"
#include "../../core/sha256.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

#define MTIME_STEP 4 /* > FAT 2 s resolution + odd/even rounding slack */
#define DEFAULT_RESERVE (1u << 20)

typedef struct {
	const rh_cfg *c;
	char apps[PATH_MAX], state[PATH_MAX], bakdir[PATH_MAX];
	char journal[PATH_MAX], record[PATH_MAX];
	char dest[PATH_MAX], stage[PATH_MAX], bak[PATH_MAX], baktmp[PATH_MAX];
} ctx;

typedef struct {
	char app_id[80], version[40], dest[80], new_sha[65], old_sha[65];
	long long old_mtime;
	int rm; /* 1 = uninstall journal (new_sha is "-") */
} journal;

#define P(buf, ...) (snprintf((buf), sizeof(buf), __VA_ARGS__) >= (int)sizeof(buf))

const char *rh_strerr(rh_err e)
{
	static const char *m[] = {"ok", "bad argument", "destination not allowed", "source unreadable",
		"size mismatch", "sha256 mismatch", "not enough space", "package is mounted/running",
		"mount state unknown", "target not installed by RetroHatch", "I/O error",
		"cannot set scanner-visible mtime", "rollback failed; run recovery", "injected"};
	return (unsigned)e < sizeof m / sizeof *m ? m[e] : "?";
}

void rh_cfg_nano(rh_cfg *c)
{
	memset(c, 0, sizeof *c);
	c->apps_dir = RH_NANO_APPS_DIR;
	c->state_dir = RH_NANO_STATE_DIR;
	c->proc_mounts = "/proc/mounts";
	c->sys_block = "/sys/block";
}

/* ---- validation (all names come from untrusted catalog data) ---- */

static int ok_chars(const char *s, size_t max, const char *extra)
{
	size_t n = s ? strlen(s) : 0, i;

	if (n == 0 || n > max || !((s[0] >= 'a' && s[0] <= 'z') || (s[0] >= 'A' && s[0] <= 'Z') ||
				   (s[0] >= '0' && s[0] <= '9')))
		return 0;
	for (i = 0; i < n; i++)
		if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= 'A' && s[i] <= 'Z') ||
		      (s[i] >= '0' && s[i] <= '9') || strchr(extra, s[i])))
			return 0;
	return 1;
}

static int ok_id(const char *s) { return ok_chars(s, 64, "-"); }
static int ok_ver(const char *s) { return ok_chars(s, 32, ".+-_"); }

static int ok_hex(const char *s)
{
	size_t i;
	if (!s || strlen(s) != 64)
		return 0;
	for (i = 0; i < 64; i++)
		if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f')))
			return 0;
	return 1;
}

static int ok_dest(const char *s)
{
	static const char *deny[] = {"TaraFi.opk", "freewares_funkey-s.opk", "poweroff_funkey-s.opk",
		"reboot_funkey-s.opk", "InstallMusic.opk", "clock_funkey-s.opk",
		"connectivity_funkey-s.opk", "retrohatch.opk", "retrohatch_funkey-s.opk", NULL};
	size_t n = s ? strlen(s) : 0;
	int i;

	if (!ok_chars(s, 64, "._+-") || n < 5 || strcmp(s + n - 4, ".opk"))
		return 0;
	for (i = 0; deny[i]; i++)
		if (!strcmp(s, deny[i]))
			return 0;
	return 1;
}

/* ---- small file helpers ---- */

static void sync_dir(const char *dir)
{
	int fd = open(dir, O_RDONLY);
	if (fd >= 0) {
		fsync(fd);
		close(fd);
	}
	sync();
}

static int copy_file(const char *src, const char *dst)
{
	char buf[65536];
	int in = open(src, O_RDONLY), out;
	ssize_t n;

	if (in < 0)
		return -1;
	out = open(dst, O_WRONLY | O_CREAT | O_TRUNC, 0755);
	if (out < 0) {
		close(in);
		return -1;
	}
	while ((n = read(in, buf, sizeof buf)) > 0) {
		char *p = buf;
		while (n > 0) {
			ssize_t w = write(out, p, (size_t)n);
			if (w < 0) {
				close(in); close(out); unlink(dst);
				return -1;
			}
			p += w; n -= w;
		}
	}
	close(in);
	if (n < 0 || fsync(out) < 0) {
		close(out); unlink(dst);
		return -1;
	}
	return close(out) ? -1 : 0;
}

static int hash_is(const char *path, const char *want)
{
	char h[65];
	return rh_sha256_file(path, h, NULL) == 0 && strcmp(h, want) == 0;
}

static int set_mtime(const char *path, time_t t)
{
	struct timespec ts[2] = {{0, UTIME_OMIT}, {t, 0}};
	return utimensat(AT_FDCWD, path, ts, 0);
}

static int get_mtime(const char *path, time_t *t)
{
	struct stat st;
	if (stat(path, &st))
		return -1;
	*t = st.st_mtime;
	return 0;
}

/* New mtime must differ from the old one by more than the scanner can miss
 * (path|size|mtime fingerprint, FAT stores even seconds) even if the clock is
 * wrong: never earlier than old+MTIME_STEP, rounded up to an even second. */
static time_t pick_mtime(time_t now, int have_prev, time_t prev)
{
	time_t t = now;
	if (have_prev && t < prev + MTIME_STEP)
		t = prev + MTIME_STEP;
	return (t + 1) & ~(time_t)1;
}

/* ---- paths ---- */

static int init_base(const rh_cfg *c, ctx *x)
{
	memset(x, 0, sizeof *x);
	x->c = c;
	if (!c->apps_dir || !c->state_dir || !c->proc_mounts || !c->sys_block)
		return RH_E_ARG;
	if (!realpath(c->apps_dir, x->apps))
		return RH_E_DEST;
	if (mkdir(c->state_dir, 0755) && errno != EEXIST)
		return RH_E_DEST;
	if (!realpath(c->state_dir, x->state) || P(x->bakdir, "%s/backup", x->state))
		return RH_E_DEST;
	if (mkdir(x->bakdir, 0755) && errno != EEXIST)
		return RH_E_DEST;
	if (P(x->journal, "%s/journal", x->state) || P(x->record, "%s/installed.tsv", x->state))
		return RH_E_DEST;
	return RH_OK;
}

static int set_dest(ctx *x, const char *name)
{
	if (!ok_dest(name))
		return -1;
	return P(x->dest, "%s/%s", x->apps, name) || P(x->stage, "%s.new", x->dest) ||
	       P(x->bak, "%s/%s.bak", x->bakdir, name) || P(x->baktmp, "%s.tmp", x->bak);
}

/* ---- installed record: tab-separated app_id, version, sha256, dest ---- */

static int is_managed(const ctx *x)
{
	char line[512];
	FILE *f = fopen(x->record, "r");
	int found = 0;

	if (!f)
		return 0;
	while (fgets(line, sizeof line, f)) {
		char *p = strrchr(line, '\t');
		if (p) {
			p++;
			p[strcspn(p, "\r\n")] = 0;
			if (!strcmp(p, x->dest))
				found = 1;
		}
	}
	fclose(f);
	return found;
}

/* 1 if the record lists app_id with this dest; copies its sha256 to sha[65] */
static int record_find(const ctx *x, const char *id, char *sha)
{
	char line[512], *f[4];
	FILE *fp = fopen(x->record, "r");
	int found = 0, i;

	if (!fp)
		return 0;
	while (!found && fgets(line, sizeof line, fp)) {
		char *p = line;
		line[strcspn(line, "\r\n")] = 0;
		for (i = 0; i < 4; i++) {
			f[i] = p;
			if (i < 3 && !(p = strchr(p, '\t')))
				break;
			if (i < 3)
				*p++ = 0;
		}
		if (i == 4 && !strcmp(f[0], id) && !strcmp(f[3], x->dest) && ok_hex(f[2])) {
			snprintf(sha, 65, "%s", f[2]);
			found = 1;
		}
	}
	fclose(fp);
	return found;
}

/* ver == NULL removes the app's line instead of adding one */
static int record_upsert(const ctx *x, const char *id, const char *ver, const char *sha)
{
	char tmp[PATH_MAX], line[512], key[96];
	FILE *in = fopen(x->record, "r"), *out;
	int fd;

	if (P(tmp, "%s.tmp", x->record))
		return -1;
	out = fopen(tmp, "w");
	if (!out) {
		if (in) fclose(in);
		return -1;
	}
	snprintf(key, sizeof key, "%s\t", id);
	while (in && fgets(line, sizeof line, in))
		if (strncmp(line, key, strlen(key)))
			fputs(line, out);
	if (ver)
		fprintf(out, "%s\t%s\t%s\t%s\n", id, ver, sha, x->dest);
	if (in)
		fclose(in);
	fflush(out);
	fd = fileno(out);
	if (ferror(out) || fsync(fd) < 0) {
		fclose(out); unlink(tmp);
		return -1;
	}
	if (fclose(out) || rename(tmp, x->record)) {
		unlink(tmp);
		return -1;
	}
	sync_dir(x->state);
	return 0;
}

/* ---- journal: written before the replace, removed after the record ---- */

static int journal_write(const ctx *x, const journal *j)
{
	char tmp[PATH_MAX];
	FILE *f;

	if (P(tmp, "%s.tmp", x->journal))
		return -1;
	f = fopen(tmp, "w");
	if (!f)
		return -1;
	fprintf(f, "app_id=%s\nversion=%s\ndest=%s\nnew_sha=%s\nold_sha=%s\nold_mtime=%lld\nop=%s\nend=1\n",
		j->app_id, j->version, j->dest, j->new_sha, j->old_sha, j->old_mtime,
		j->rm ? "remove" : "install");
	fflush(f);
	if (ferror(f) || fsync(fileno(f)) < 0) {
		fclose(f); unlink(tmp);
		return -1;
	}
	if (fclose(f) || rename(tmp, x->journal)) {
		unlink(tmp);
		return -1;
	}
	sync_dir(x->state);
	return 0;
}

/* 0 ok, 1 absent, -1 corrupt/unreadable */
static int journal_read(const ctx *x, journal *j)
{
	char line[256];
	FILE *f = fopen(x->journal, "r");
	int seen = 0, complete = 0;

	if (!f)
		return errno == ENOENT ? 1 : -1;
	memset(j, 0, sizeof *j);
	while (fgets(line, sizeof line, f)) {
		char *v = strchr(line, '=');
		if (!v)
			continue;
		*v++ = 0;
		v[strcspn(v, "\r\n")] = 0;
		if (!strcmp(line, "app_id") && ok_id(v)) { snprintf(j->app_id, sizeof j->app_id, "%s", v); seen |= 1; }
		else if (!strcmp(line, "version") && ok_ver(v)) { snprintf(j->version, sizeof j->version, "%s", v); seen |= 2; }
		else if (!strcmp(line, "dest") && ok_dest(v)) { snprintf(j->dest, sizeof j->dest, "%s", v); seen |= 4; }
		else if (!strcmp(line, "op")) j->rm = !strcmp(v, "remove");
		else if (!strcmp(line, "new_sha") && (ok_hex(v) || !strcmp(v, "-"))) { snprintf(j->new_sha, sizeof j->new_sha, "%s", v); seen |= 8; }
		else if (!strcmp(line, "old_sha") && (ok_hex(v) || !strcmp(v, "-"))) { snprintf(j->old_sha, sizeof j->old_sha, "%s", v); seen |= 16; }
		else if (!strcmp(line, "old_mtime")) { j->old_mtime = atoll(v); seen |= 32; }
		else if (!strcmp(line, "end")) complete = 1;
	}
	fclose(f);
	return (seen == 63 && complete) ? 0 : -1;
}

/* ---- running / mounted detection (fail closed) ---- */

/* opkrun loop-mounts the OPK it runs as squashfs; the scanner does the same
 * briefly. Resolve each squashfs loop mount to its backing file. A mount whose
 * backing file is our target (including "(deleted)" stale mounts) = BUSY. Any
 * squashfs mount we cannot resolve, or an unreadable /proc/mounts = UNKNOWN. */
static rh_err opk_busy(const ctx *x)
{
	char line[1024], dev[256], mp[256], fs[64];
	rh_err r = RH_OK;
	FILE *f = fopen(x->c->proc_mounts, "r");

	if (!f)
		return RH_E_UNKNOWN_MOUNT;
	while (fgets(line, sizeof line, f)) {
		char path[PATH_MAX], bf[PATH_MAX];
		struct stat a, b;
		FILE *g;
		size_t n;

		if (sscanf(line, "%255s %255s %63s", dev, mp, fs) != 3) {
			r = RH_E_UNKNOWN_MOUNT;
			continue;
		}
		if (strcmp(fs, "squashfs"))
			continue;
		if (strncmp(dev, "/dev/loop", 9) || strchr(dev + 5, '/') ||
		    P(path, "%s/%s/loop/backing_file", x->c->sys_block, dev + 5) ||
		    !(g = fopen(path, "r"))) {
			r = RH_E_UNKNOWN_MOUNT;
			continue;
		}
		if (!fgets(bf, sizeof bf, g)) {
			fclose(g);
			r = RH_E_UNKNOWN_MOUNT;
			continue;
		}
		fclose(g);
		bf[strcspn(bf, "\r\n")] = 0;
		n = strlen(bf);
		if (n > 10 && !strcmp(bf + n - 10, " (deleted)"))
			bf[n - 10] = 0;
		if (!strcmp(bf, x->dest) ||
		    (!stat(bf, &a) && !stat(x->dest, &b) && a.st_dev == b.st_dev && a.st_ino == b.st_ino)) {
			fclose(f);
			return RH_E_BUSY;
		}
	}
	fclose(f);
	return r;
}

/* ---- rollback / recovery ---- */

static rh_err restore(const ctx *x, const journal *j)
{
	if (!strcmp(j->old_sha, "-")) {
		/* fresh install: our own half-written file goes away */
		if (unlink(x->dest) && errno != ENOENT)
			return RH_E_RECOVER;
	} else {
		if (!hash_is(x->bak, j->old_sha))
			return RH_E_RECOVER;
		unlink(x->stage);
		if (copy_file(x->bak, x->stage) || set_mtime(x->stage, (time_t)j->old_mtime) ||
		    rename(x->stage, x->dest) || !hash_is(x->dest, j->old_sha))
			return RH_E_RECOVER;
	}
	unlink(x->stage);
	sync_dir(x->apps);
	unlink(x->journal);
	sync_dir(x->state);
	return RH_OK;
}

rh_err rh_recover(const rh_cfg *c)
{
	ctx x;
	journal j;
	rh_err e;
	int r;

	if ((e = init_base(c, &x)))
		return e;
	r = journal_read(&x, &j);
	if (r == 1)
		return RH_OK;
	if (r < 0 || set_dest(&x, j.dest))
		return RH_E_RECOVER;
	if ((e = opk_busy(&x)))
		return e;
	if (j.rm) {
		struct stat st;
		if (lstat(x.dest, &st) == 0) { /* removal never happened: must still be ours */
			if (!hash_is(x.dest, j.old_sha))
				return RH_E_RECOVER;
		} else { /* file is gone: finish the removal */
			if (errno != ENOENT || record_upsert(&x, j.app_id, NULL, NULL))
				return RH_E_IO;
			unlink(x.bak);
		}
	} else if (hash_is(x.dest, j.new_sha)) { /* replace landed: finish the bookkeeping */
		if (record_upsert(&x, j.app_id, j.version, j.new_sha))
			return RH_E_IO;
	} else if (strcmp(j.old_sha, "-") && hash_is(x.dest, j.old_sha)) {
		/* replace never happened: old version intact */
	} else if ((e = restore(&x, &j))) {
		return e;
	}
	unlink(x.stage);
	unlink(x.journal);
	sync_dir(x.state);
	return RH_OK;
}

/* ---- install ---- */

#define STEP(name) do { \
	int h_ = c->hook ? c->hook(name) : 0; \
	if (h_ == 2) return RH_E_INJECTED; \
	if (h_) { e = RH_E_INJECTED; goto fail; } \
} while (0)

static rh_err check_space(const ctx *x, uint64_t need_apps, uint64_t need_state)
{
	struct statvfs va, vs;
	struct stat sa, ss;
	uint64_t fa, fs_, margin = x->c->reserve_bytes ? x->c->reserve_bytes : DEFAULT_RESERVE;

	if (statvfs(x->apps, &va) || statvfs(x->state, &vs) || stat(x->apps, &sa) || stat(x->state, &ss))
		return RH_E_IO;
	fa = (uint64_t)va.f_bavail * va.f_frsize;
	fs_ = (uint64_t)vs.f_bavail * vs.f_frsize;
	if (sa.st_dev == ss.st_dev)
		return fa >= need_apps + need_state + margin ? RH_OK : RH_E_SPACE;
	return (fa >= need_apps + margin && (need_state == 0 || fs_ >= need_state + margin)) ? RH_OK : RH_E_SPACE;
}

rh_err rh_install(const rh_cfg *c, const rh_pkg *p)
{
	ctx x;
	journal j;
	struct stat st;
	char sha[65], prev_sha[65] = "-";
	uint64_t sz, prev_size = 0;
	time_t now, prev_mtime = 0, nm, got;
	int have_prev = 0, renamed = 0, journaled = 0;
	rh_err e;

	if (!p || !ok_id(p->app_id) || !ok_ver(p->version) || !ok_hex(p->sha256) || !p->src_path)
		return RH_E_ARG;
	if (!ok_dest(p->dest_name))
		return RH_E_DEST;
	if ((e = init_base(c, &x)))
		return e;
	if ((e = rh_recover(c)))
		return e;
	if (set_dest(&x, p->dest_name))
		return RH_E_DEST;

	/* 1. source: regular file, expected size, expected hash */
	if (stat(p->src_path, &st) || !S_ISREG(st.st_mode))
		return RH_E_SRC;
	if (p->size == 0 || (uint64_t)st.st_size != p->size)
		return RH_E_SIZE;
	if (rh_sha256_file(p->src_path, sha, &sz))
		return RH_E_SRC;
	if (sz != p->size)
		return RH_E_SIZE;
	if (strcmp(sha, p->sha256))
		return RH_E_HASH;

	/* 2. target: only replace what RetroHatch installed */
	if (lstat(x.dest, &st) == 0) {
		if (!S_ISREG(st.st_mode))
			return RH_E_DEST;
		if (!is_managed(&x))
			return RH_E_UNMANAGED;
		have_prev = 1;
		prev_mtime = st.st_mtime;
		prev_size = (uint64_t)st.st_size;
		if (rh_sha256_file(x.dest, prev_sha, NULL))
			return RH_E_IO;
	} else if (errno != ENOENT) {
		return RH_E_IO;
	}
	if ((e = opk_busy(&x)))
		return e;
	if ((e = check_space(&x, p->size, have_prev ? prev_size : 0)))
		return e;

	/* 3. stage under a name the Apps scanner ignores, verify the staged copy */
	unlink(x.stage);
	if (copy_file(p->src_path, x.stage)) {
		e = RH_E_IO;
		goto fail;
	}
	if (!hash_is(x.stage, p->sha256)) {
		e = RH_E_HASH;
		goto fail;
	}
	STEP("staged");

	/* 4. keep the working version outside every scanned directory */
	if (have_prev) {
		if (copy_file(x.dest, x.baktmp) || !hash_is(x.baktmp, prev_sha) || rename(x.baktmp, x.bak)) {
			unlink(x.baktmp);
			e = RH_E_IO;
			goto fail;
		}
	}
	STEP("backed_up");

	/* 5. scanner-visible mtime, set and verified on the staged file */
	now = c->now ? c->now() : time(NULL);
	nm = pick_mtime(now, have_prev, prev_mtime);
	if (set_mtime(x.stage, nm) || get_mtime(x.stage, &got) || got != nm ||
	    (have_prev && got < prev_mtime + 2)) {
		e = RH_E_MTIME;
		goto fail;
	}

	/* 6. journal, then replace */
	memset(&j, 0, sizeof j);
	snprintf(j.app_id, sizeof j.app_id, "%s", p->app_id);
	snprintf(j.version, sizeof j.version, "%s", p->version);
	snprintf(j.dest, sizeof j.dest, "%s", p->dest_name);
	snprintf(j.new_sha, sizeof j.new_sha, "%s", p->sha256);
	snprintf(j.old_sha, sizeof j.old_sha, "%s", prev_sha);
	j.old_mtime = (long long)prev_mtime;
	journaled = 1;
	if (journal_write(&x, &j)) {
		e = RH_E_IO;
		goto fail;
	}
	STEP("journaled");
	if ((e = opk_busy(&x))) /* re-check: the copy took time */
		goto fail;
	if (rename(x.stage, x.dest)) {
		e = RH_E_IO;
		goto fail;
	}
	renamed = 1;
	STEP("renamed");
	sync_dir(x.apps);

	/* 7. verify what is actually on disk */
	if (!hash_is(x.dest, p->sha256)) {
		e = RH_E_HASH;
		goto fail;
	}
	if (get_mtime(x.dest, &got) || got != nm) {
		e = RH_E_MTIME;
		goto fail;
	}
	STEP("synced");

	/* 8. record, then clear the journal */
	if (record_upsert(&x, p->app_id, p->version, p->sha256)) {
		e = RH_E_IO;
		goto fail;
	}
	STEP("recorded");
	unlink(x.journal);
	sync_dir(x.state);
	return RH_OK;

fail:
	if (renamed) {
		rh_err r = restore(&x, &j);
		return r ? r : e;
	}
	unlink(x.stage);
	if (journaled)
		unlink(x.journal);
	return e;
}

/* ---- uninstall ---- */

/* Removes only an OPK the record lists for this app_id AND whose bytes still
 * match the recorded hash. App settings/saves live outside the OPK and are not
 * touched. The OPK is parked in <state>/backup (never scanned) until the
 * record is updated, then the parked copy is deleted: one backup per app. */
rh_err rh_uninstall(const rh_cfg *c, const char *app_id, const char *dest_name)
{
	ctx x;
	journal j;
	struct stat st;
	char sha[65], rec[65];
	rh_err e;
	int removed = 0, journaled = 0;

	if (!ok_id(app_id))
		return RH_E_ARG;
	if (!ok_dest(dest_name)) /* also the protected-name denylist */
		return RH_E_DEST;
	if ((e = init_base(c, &x)) || (e = rh_recover(c)))
		return e;
	if (set_dest(&x, dest_name))
		return RH_E_DEST;
	if (lstat(x.dest, &st) || !S_ISREG(st.st_mode) || !record_find(&x, app_id, rec))
		return RH_E_UNMANAGED;
	if (rh_sha256_file(x.dest, sha, NULL))
		return RH_E_IO;
	if (strcmp(sha, rec)) /* user replaced it: not ours to delete */
		return RH_E_UNMANAGED;
	if ((e = opk_busy(&x)) || (e = check_space(&x, 0, (uint64_t)st.st_size)))
		return e;

	if (copy_file(x.dest, x.baktmp) || !hash_is(x.baktmp, sha) || rename(x.baktmp, x.bak)) {
		unlink(x.baktmp);
		return RH_E_IO;
	}
	STEP("backed_up");
	memset(&j, 0, sizeof j);
	snprintf(j.app_id, sizeof j.app_id, "%s", app_id);
	snprintf(j.version, sizeof j.version, "0");
	snprintf(j.dest, sizeof j.dest, "%s", dest_name);
	snprintf(j.new_sha, sizeof j.new_sha, "-");
	snprintf(j.old_sha, sizeof j.old_sha, "%s", sha);
	j.old_mtime = (long long)st.st_mtime;
	j.rm = 1;
	journaled = 1;
	if (journal_write(&x, &j)) {
		e = RH_E_IO;
		goto fail;
	}
	STEP("journaled");
	if ((e = opk_busy(&x))) /* re-check right before deleting */
		goto fail;
	if (unlink(x.dest)) {
		e = RH_E_IO;
		goto fail;
	}
	removed = 1;
	STEP("removed");
	sync_dir(x.apps);
	if (record_upsert(&x, app_id, NULL, NULL)) {
		e = RH_E_IO;
		goto fail;
	}
	if (c->hook && c->hook("recorded") == 2) /* crash only: record is already final, never roll back */
		return RH_E_INJECTED;
	unlink(x.bak);
	unlink(x.journal);
	sync_dir(x.state);
	return RH_OK;

fail:
	if (removed) {
		rh_err r = restore(&x, &j);
		return r ? r : e;
	}
	if (journaled)
		unlink(x.journal);
	return e;
}
