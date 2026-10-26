/* Host-side tests for the Nano install adapter. Temp dirs only; never touches
 * a device. Build/run: make -C tests test   (needs gcc; run under Linux/WSL) */
#define _XOPEN_SOURCE 700
#include "../platforms/nano/rh_install.h"
#include "../core/sha256.h"
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define EQ(got, want) do { rh_err g_ = (got); checks++; if (g_ != (want)) { fails++; \
	printf("FAIL %s:%d: got '%s' want '%s'\n", __FILE__, __LINE__, rh_strerr(g_), rh_strerr(want)); } } while (0)

static char root[256], apps[300], state[300], mounts[300], sysb[300], srcdir[300];
static rh_cfg cfg;
static time_t fake_now;
static time_t clock_fn(void) { return fake_now; }
static const char *hook_at;
static int hook_mode;
static int hook_fn(const char *s) { return hook_at && !strcmp(s, hook_at) ? hook_mode : 0; }

static void sh(const char *fmt, const char *a)
{
	char cmd[1024];
	snprintf(cmd, sizeof cmd, fmt, a);
	if (system(cmd)) { printf("setup failed: %s\n", cmd); exit(2); }
}

static void wr(const char *path, const char *text)
{
	FILE *f = fopen(path, "w");
	fputs(text, f);
	fclose(f);
}

static int exists(const char *p) { struct stat st; return stat(p, &st) == 0; }

static void fresh(void)
{
	char b[400];
	snprintf(b, sizeof b, "rm -rf %s/*; mkdir -p %s/apps %s/src %s/sys", root, root, root, root);
	sh("%s", b);
	snprintf(apps, sizeof apps, "%s/apps", root);
	snprintf(state, sizeof state, "%s/state", root);
	snprintf(mounts, sizeof mounts, "%s/mounts", root);
	snprintf(sysb, sizeof sysb, "%s/sys", root);
	snprintf(srcdir, sizeof srcdir, "%s/src", root);
	wr(mounts, "/dev/root / ext4 ro 0 0\n/dev/mmcblk0p4 /mnt vfat rw 0 0\n/dev/loop0 /mnt/x ext4 rw 0 0\n");
	memset(&cfg, 0, sizeof cfg);
	cfg.apps_dir = apps; cfg.state_dir = state; cfg.proc_mounts = mounts; cfg.sys_block = sysb;
	cfg.now = clock_fn; cfg.hook = hook_fn;
	fake_now = 1800000000;
	hook_at = NULL;
}

/* 4096-byte package whose content depends on seed; fills in sha. */
static char shabuf[2][65];
static rh_pkg mkpkg(const char *name, char seed, int slot)
{
	char path[400];
	static char paths[2][400];
	unsigned char buf[4096];
	FILE *f;
	rh_pkg p;

	memset(buf, seed, sizeof buf);
	snprintf(paths[slot], 400, "%s/%s.%c", srcdir, name, seed);
	f = fopen(paths[slot], "wb");
	fwrite(buf, 1, sizeof buf, f);
	fclose(f);
	snprintf(path, sizeof path, "%s", paths[slot]);
	rh_sha256_file(path, shabuf[slot], NULL);
	p.app_id = "probe"; p.version = slot ? "2" : "1"; p.dest_name = name;
	p.src_path = paths[slot]; p.size = 4096; p.sha256 = shabuf[slot];
	return p;
}

static void dest_path(char *out, const char *name) { snprintf(out, 400, "%s/%s", apps, name); }
static int dest_is(const char *name, const char *sha)
{
	char p[400], h[65];
	dest_path(p, name);
	return rh_sha256_file(p, h, NULL) == 0 && !strcmp(h, sha);
}
static time_t mtime_of(const char *name)
{
	char p[400]; struct stat st;
	dest_path(p, name);
	return stat(p, &st) ? -1 : st.st_mtime;
}
static int file_has(const char *path, const char *needle)
{
	char buf[4096] = {0};
	FILE *f = fopen(path, "r");
	if (!f) return 0;
	fread(buf, 1, sizeof buf - 1, f);
	fclose(f);
	return strstr(buf, needle) != NULL;
}
static void mount_of(const char *loop, const char *backing)
{
	char p[400], line[400];
	snprintf(p, sizeof p, "%s/%s/loop", sysb, loop);
	sh("mkdir -p %s", p);
	snprintf(p, sizeof p, "%s/%s/loop/backing_file", sysb, loop);
	if (backing) wr(p, backing);
	snprintf(line, sizeof line, "/dev/%s /opk squashfs ro,relatime 0 0\n", loop);
	FILE *f = fopen(mounts, "a"); fputs(line, f); fclose(f);
}
static int stray_files(void) /* anything in apps that is not a .opk we expect */
{
	char cmd[500];
	snprintf(cmd, sizeof cmd, "ls %s | grep -v -E '\\.opk$' > /dev/null", apps);
	return system(cmd) == 0;
}

static void test_sha(void)
{
	char p[400], h[65];
	snprintf(p, sizeof p, "%s/v", root);
	wr(p, "abc");
	rh_sha256_file(p, h, NULL);
	CHECK(!strcmp(h, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
	wr(p, "");
	rh_sha256_file(p, h, NULL);
	CHECK(!strcmp(h, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
	wr(p, "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq");
	rh_sha256_file(p, h, NULL);
	CHECK(!strcmp(h, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"));
}

static void test_validation(void)
{
	rh_pkg p;
	char big[400];
	fresh();
	p = mkpkg("a.opk", 'A', 0);
	p.dest_name = "../a.opk";        EQ(rh_install(&cfg, &p), RH_E_DEST);
	p.dest_name = "sub/a.opk";       EQ(rh_install(&cfg, &p), RH_E_DEST);
	p.dest_name = "TaraFi.opk";      EQ(rh_install(&cfg, &p), RH_E_DEST);
	p.dest_name = "a.opk.new";       EQ(rh_install(&cfg, &p), RH_E_DEST);
	p.dest_name = ".hidden.opk";     EQ(rh_install(&cfg, &p), RH_E_DEST);
	p.dest_name = "a.opk"; p.app_id = "../x"; EQ(rh_install(&cfg, &p), RH_E_ARG);
	p.app_id = "probe"; p.sha256 = "ABC"; EQ(rh_install(&cfg, &p), RH_E_ARG);
	p = mkpkg("a.opk", 'A', 0);
	p.size = 4095;                   EQ(rh_install(&cfg, &p), RH_E_SIZE);
	p.size = 4096; p.sha256 = "0000000000000000000000000000000000000000000000000000000000000000";
	EQ(rh_install(&cfg, &p), RH_E_HASH);
	p = mkpkg("a.opk", 'A', 0);
	p.src_path = "/nonexistent/file"; EQ(rh_install(&cfg, &p), RH_E_SRC);
	p = mkpkg("a.opk", 'A', 0);
	cfg.reserve_bytes = (uint64_t)1 << 60; EQ(rh_install(&cfg, &p), RH_E_SPACE);
	dest_path(big, "a.opk");
	CHECK(!exists(big) && !stray_files());   /* nothing left behind by any refusal */
}

/* A bad source must be rejected before anything is written: with the apps dir
 * read-only, a copy attempt would give RH_E_IO, so RH_E_HASH proves the
 * source itself was checked first. (Skipped as root: perms are ignored.) */
static void test_source_hash_first(void)
{
	rh_pkg p;
	char cmd[400];
	fresh();
	if (geteuid() == 0) { printf("skip: running as root\n"); return; }
	p = mkpkg("a.opk", 'A', 0);
	p.sha256 = "1111111111111111111111111111111111111111111111111111111111111111";
	snprintf(cmd, sizeof cmd, "chmod 555 %s", apps);
	sh("%s", cmd);
	EQ(rh_install(&cfg, &p), RH_E_HASH);
	p = mkpkg("a.opk", 'A', 0);      /* control: right hash, same dir -> write fails */
	EQ(rh_install(&cfg, &p), RH_E_IO);
	snprintf(cmd, sizeof cmd, "chmod 755 %s", apps);
	sh("%s", cmd);
	CHECK(!stray_files());
}

static void test_install_update(void)
{
	rh_pkg v1, v2;
	char st[400], bak[400];
	time_t m1;
	fresh();
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	v2 = mkpkg("probe_funkey-s.opk", '2', 1);

	EQ(rh_install(&cfg, &v1), RH_OK);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[0]));
	CHECK(mtime_of("probe_funkey-s.opk") % 2 == 0);
	snprintf(st, sizeof st, "%s/installed.tsv", state);
	CHECK(file_has(st, "probe\t1\t") && file_has(st, shabuf[0]));
	snprintf(st, sizeof st, "%s/journal", state);
	CHECK(!exists(st) && !stray_files());
	m1 = mtime_of("probe_funkey-s.opk");

	/* update with a clock stuck in the past: mtime must still move forward */
	fake_now = 1000;
	EQ(rh_install(&cfg, &v2), RH_OK);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[1]));
	CHECK(mtime_of("probe_funkey-s.opk") >= m1 + 4 && mtime_of("probe_funkey-s.opk") % 2 == 0);
	snprintf(bak, sizeof bak, "%s/backup/probe_funkey-s.opk.bak", state);
	{ char h[65]; CHECK(rh_sha256_file(bak, h, NULL) == 0 && !strcmp(h, shabuf[0])); }
	snprintf(st, sizeof st, "%s/installed.tsv", state);
	CHECK(file_has(st, "probe\t2\t") && !file_has(st, "probe\t1\t"));
	CHECK(!stray_files());

	/* same content again with a normal clock: still gets a fresh mtime */
	fake_now = 1900000000;
	m1 = mtime_of("probe_funkey-s.opk");
	EQ(rh_install(&cfg, &v2), RH_OK);
	CHECK(mtime_of("probe_funkey-s.opk") >= m1 + 4);
}

static void test_unmanaged(void)
{
	rh_pkg v1;
	char p[400];
	fresh();
	v1 = mkpkg("commander_funkey-s.opk", '1', 0);
	dest_path(p, "commander_funkey-s.opk");
	wr(p, "firmware app");
	EQ(rh_install(&cfg, &v1), RH_E_UNMANAGED);
	CHECK(file_has(p, "firmware app"));
}

static void test_busy(void)
{
	rh_pkg v1, v2;
	char p[400], b[400];
	fresh();
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	v2 = mkpkg("probe_funkey-s.opk", '2', 1);
	EQ(rh_install(&cfg, &v1), RH_OK);
	dest_path(p, "probe_funkey-s.opk");

	mount_of("loop1", p);                              /* running */
	EQ(rh_install(&cfg, &v2), RH_E_BUSY);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[0]));

	fresh();                                           /* stale mount on deleted inode */
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	v2 = mkpkg("probe_funkey-s.opk", '2', 1);
	EQ(rh_install(&cfg, &v1), RH_OK);
	snprintf(b, sizeof b, "%s (deleted)", p);
	mount_of("loop1", b);
	EQ(rh_install(&cfg, &v2), RH_E_BUSY);

	fresh();                                           /* another app running: allowed */
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	v2 = mkpkg("probe_funkey-s.opk", '2', 1);
	EQ(rh_install(&cfg, &v1), RH_OK);
	mount_of("loop1", "/mnt/Music/TaraFi.opk");
	EQ(rh_install(&cfg, &v2), RH_OK);

	fresh();                                           /* cannot resolve backing file */
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	mount_of("loop1", NULL);
	EQ(rh_install(&cfg, &v1), RH_E_UNKNOWN_MOUNT);
	dest_path(p, "probe_funkey-s.opk");
	CHECK(!exists(p));

	fresh();                                           /* no /proc/mounts */
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	cfg.proc_mounts = "/nonexistent/mounts";
	EQ(rh_install(&cfg, &v1), RH_E_UNKNOWN_MOUNT);
}

static void test_failures_and_recovery(void)
{
	rh_pkg v1, v2;
	char p[400], j[400];
	time_t m1;

	/* error after the replace -> rolled back to V1 with its old mtime */
	fresh();
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	v2 = mkpkg("probe_funkey-s.opk", '2', 1);
	EQ(rh_install(&cfg, &v1), RH_OK);
	m1 = mtime_of("probe_funkey-s.opk");
	hook_at = "synced"; hook_mode = 1;
	EQ(rh_install(&cfg, &v2), RH_E_INJECTED);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[0]) && mtime_of("probe_funkey-s.opk") == m1);
	snprintf(j, sizeof j, "%s/journal", state);
	CHECK(!exists(j) && !stray_files());

	/* error before the replace -> V1 untouched, no stage left */
	hook_at = "backed_up";
	EQ(rh_install(&cfg, &v2), RH_E_INJECTED);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[0]) && !stray_files());

	/* crash after journal, before rename -> recover keeps V1 */
	hook_at = "journaled"; hook_mode = 2;
	EQ(rh_install(&cfg, &v2), RH_E_INJECTED);
	CHECK(exists(j));
	hook_at = NULL;
	EQ(rh_recover(&cfg), RH_OK);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[0]) && !exists(j) && !stray_files());

	/* crash right after rename -> recover completes V2 and the record */
	hook_at = "renamed"; hook_mode = 2;
	EQ(rh_install(&cfg, &v2), RH_E_INJECTED);
	hook_at = NULL;
	EQ(rh_recover(&cfg), RH_OK);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[1]) && !exists(j));
	snprintf(p, sizeof p, "%s/installed.tsv", state);
	CHECK(file_has(p, "probe\t2\t"));

	/* crash, then the replaced file is found corrupt (non-atomic FAT) -> V2's predecessor restored */
	hook_at = "renamed"; hook_mode = 2;
	{
		rh_pkg v3 = mkpkg("probe_funkey-s.opk", '3', 0);
		m1 = mtime_of("probe_funkey-s.opk");
		EQ(rh_install(&cfg, &v3), RH_E_INJECTED);
		dest_path(p, "probe_funkey-s.opk");
		wr(p, "torn write");
		hook_at = NULL;
		EQ(rh_recover(&cfg), RH_OK);
		CHECK(dest_is("probe_funkey-s.opk", shabuf[1]) && mtime_of("probe_funkey-s.opk") == m1);
	}

	/* a pending journal blocks nothing: next install recovers first, then succeeds */
	fresh();
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	hook_at = "renamed"; hook_mode = 2;
	EQ(rh_install(&cfg, &v1), RH_E_INJECTED);      /* fresh install, crashed after rename */
	hook_at = NULL;
	v2 = mkpkg("probe_funkey-s.opk", '2', 1);
	EQ(rh_install(&cfg, &v2), RH_OK);
	CHECK(dest_is("probe_funkey-s.opk", shabuf[1]));

	/* fresh install, crash leaves a torn file -> recover removes it */
	fresh();
	v1 = mkpkg("probe_funkey-s.opk", '1', 0);
	hook_at = "renamed"; hook_mode = 2;
	EQ(rh_install(&cfg, &v1), RH_E_INJECTED);
	dest_path(p, "probe_funkey-s.opk");
	wr(p, "torn write");
	hook_at = NULL;
	EQ(rh_recover(&cfg), RH_OK);
	CHECK(!exists(p));
}

static int stray_new(void) /* leftover staged *.new in apps */
{
	char cmd[500];
	snprintf(cmd, sizeof cmd, "ls %s/*.new > /dev/null 2>&1", apps);
	return system(cmd) == 0;
}

static int dir_empty(const char *d)
{
	char cmd[500];
	snprintf(cmd, sizeof cmd, "[ -z \"$(ls -A %s)\" ]", d);
	return system(cmd) == 0;
}

/* state of the world around a probe install: bystanders must never change */
static void bystanders(void)
{
	char p[400];
	dest_path(p, "other_funkey-s.opk"); wr(p, "someone else's app");
	dest_path(p, "README"); wr(p, "readme");
	snprintf(p, sizeof p, "%s/saves", root); sh("mkdir -p %s", p);
	snprintf(p, sizeof p, "%s/saves/probe.sav", root); wr(p, "my save");
}
static int bystanders_ok(void)
{
	char p[400];
	dest_path(p, "other_funkey-s.opk");
	if (!file_has(p, "someone else's app")) return 0;
	dest_path(p, "README");
	if (!file_has(p, "readme")) return 0;
	snprintf(p, sizeof p, "%s/saves/probe.sav", root);
	return file_has(p, "my save");
}

static void test_uninstall(void)
{
	rh_pkg v1, v2;
	char p[400], j[400], rec[400], bk[400];
	const char *N = "probe_funkey-s.opk";

	fresh();
	snprintf(j, sizeof j, "%s/journal", state);
	snprintf(rec, sizeof rec, "%s/installed.tsv", state);
	snprintf(bk, sizeof bk, "%s/backup", state);
	v1 = mkpkg(N, '1', 0);
	v2 = mkpkg(N, '2', 1);
	bystanders();

	/* success; update first so a backup exists, which must be gone afterwards */
	EQ(rh_install(&cfg, &v1), RH_OK);
	EQ(rh_install(&cfg, &v2), RH_OK);
	EQ(rh_uninstall(&cfg, "probe", N), RH_OK);
	dest_path(p, N);
	CHECK(!exists(p) && !exists(j) && !file_has(rec, "probe	") && dir_empty(bk));
	CHECK(bystanders_ok());
	{ char q[400]; snprintf(q, sizeof q, "%s.new", p); CHECK(!exists(q)); }
	EQ(rh_uninstall(&cfg, "probe", N), RH_E_UNMANAGED);   /* already gone */
	EQ(rh_install(&cfg, &v1), RH_OK);                      /* can reinstall afterwards */

	/* other apps' record lines survive */
	{ rh_pkg o = mkpkg("other2_funkey-s.opk", '3', 0); o.app_id = "other2";
	  EQ(rh_install(&cfg, &o), RH_OK);
	  EQ(rh_uninstall(&cfg, "probe", N), RH_OK);
	  CHECK(file_has(rec, "other2	") && dest_is("other2_funkey-s.opk", shabuf[0])); }

	/* unmanaged: present, not in the record */
	fresh(); bystanders();
	dest_path(p, "ghost_funkey-s.opk"); wr(p, "firmware app");
	EQ(rh_uninstall(&cfg, "ghost", "ghost_funkey-s.opk"), RH_E_UNMANAGED);
	CHECK(file_has(p, "firmware app") && bystanders_ok());

	/* wrong app_id for a managed file, and a file edited since install */
	fresh(); v1 = mkpkg(N, '1', 0);
	snprintf(j, sizeof j, "%s/journal", state);
	snprintf(rec, sizeof rec, "%s/installed.tsv", state);
	EQ(rh_install(&cfg, &v1), RH_OK);
	EQ(rh_uninstall(&cfg, "different", N), RH_E_UNMANAGED);
	CHECK(dest_is(N, shabuf[0]));
	dest_path(p, N); wr(p, "user replaced this");
	EQ(rh_uninstall(&cfg, "probe", N), RH_E_UNMANAGED);
	CHECK(file_has(p, "user replaced this") && file_has(rec, "probe	"));

	/* protected names, even if a record claims them */
	fresh(); bystanders();
	{ static const char *prot[] = {"TaraFi.opk", "retrohatch.opk", "retrohatch_funkey-s.opk",
		"freewares_funkey-s.opk", "poweroff_funkey-s.opk", "reboot_funkey-s.opk", NULL};
	  int i;
	  snprintf(rec, sizeof rec, "%s/installed.tsv", state);
	  sh("mkdir -p %s", state);
	  for (i = 0; prot[i]; i++) {
		char line[400];
		snprintf(line, sizeof line, "x\t1\t%s\t%s\n", shabuf[0], prot[i]);
		dest_path(p, prot[i]); wr(p, "protected");
		FILE *f = fopen(rec, "a"); fputs(line, f); fclose(f);
		EQ(rh_uninstall(&cfg, "x", prot[i]), RH_E_DEST);
		CHECK(file_has(p, "protected"));
	  }
	  EQ(rh_uninstall(&cfg, "x", "../escape.opk"), RH_E_DEST);
	  EQ(rh_uninstall(&cfg, "Bad Id", N), RH_E_ARG); }

	/* mounted / unknown mount state: refuse, nothing changes */
	fresh(); v1 = mkpkg(N, '1', 0);
	snprintf(rec, sizeof rec, "%s/installed.tsv", state);
	EQ(rh_install(&cfg, &v1), RH_OK);
	dest_path(p, N);
	mount_of("loop1", p);
	EQ(rh_uninstall(&cfg, "probe", N), RH_E_BUSY);
	CHECK(dest_is(N, shabuf[0]) && file_has(rec, "probe	"));
	fresh(); v1 = mkpkg(N, '1', 0);
	snprintf(rec, sizeof rec, "%s/installed.tsv", state);
	EQ(rh_install(&cfg, &v1), RH_OK);
	mount_of("loop1", NULL);
	EQ(rh_uninstall(&cfg, "probe", N), RH_E_UNKNOWN_MOUNT);
	CHECK(dest_is(N, shabuf[0]));
	cfg.proc_mounts = "/nonexistent/mounts";
	EQ(rh_uninstall(&cfg, "probe", N), RH_E_UNKNOWN_MOUNT);
	CHECK(dest_is(N, shabuf[0]) && file_has(rec, "probe	"));

	/* injected errors: file back, record intact, no journal, nothing stray */
	{ static const char *steps[] = {"backed_up", "journaled", "removed", NULL};
	  int i;
	  for (i = 0; steps[i]; i++) {
		time_t m;
		fresh(); bystanders(); v1 = mkpkg(N, '1', 0);
		snprintf(j, sizeof j, "%s/journal", state);
		snprintf(rec, sizeof rec, "%s/installed.tsv", state);
		EQ(rh_install(&cfg, &v1), RH_OK);
		m = mtime_of(N);
		hook_at = steps[i]; hook_mode = 1;
		EQ(rh_uninstall(&cfg, "probe", N), RH_E_INJECTED);
		hook_at = NULL;
		CHECK(dest_is(N, shabuf[0]) && mtime_of(N) == m && !exists(j));
		CHECK(file_has(rec, "probe	1	") && bystanders_ok() && !stray_new());
		EQ(rh_uninstall(&cfg, "probe", N), RH_OK);         /* and a retry works */
		dest_path(p, N);
		CHECK(!exists(p) && dir_empty(bk));
	  } }

	/* simulated crashes + recover */
	{ static const char *steps[] = {"backed_up", "journaled", "removed", "recorded", NULL};
	  int i;
	  for (i = 0; steps[i]; i++) {
		int gone = i >= 2;
		fresh(); bystanders(); v1 = mkpkg(N, '1', 0);
		snprintf(j, sizeof j, "%s/journal", state);
		snprintf(rec, sizeof rec, "%s/installed.tsv", state);
		snprintf(bk, sizeof bk, "%s/backup", state);
		EQ(rh_install(&cfg, &v1), RH_OK);
		hook_at = steps[i]; hook_mode = 2;
		EQ(rh_uninstall(&cfg, "probe", N), RH_E_INJECTED);
		hook_at = NULL;
		EQ(rh_recover(&cfg), RH_OK);
		dest_path(p, N);
		CHECK(!exists(j) && bystanders_ok() && !stray_new());
		if (gone) {
			CHECK(!exists(p) && !file_has(rec, "probe	") && dir_empty(bk));
		} else {
			CHECK(dest_is(N, shabuf[0]) && file_has(rec, "probe	1	"));
			EQ(rh_uninstall(&cfg, "probe", N), RH_OK);
			CHECK(!exists(p) && !file_has(rec, "probe	") && dir_empty(bk));
		}
	  } }

	/* crash after unlink, then the next uninstall/install call recovers first */
	fresh(); v1 = mkpkg(N, '1', 0);
	snprintf(rec, sizeof rec, "%s/installed.tsv", state);
	EQ(rh_install(&cfg, &v1), RH_OK);
	hook_at = "removed"; hook_mode = 2;
	EQ(rh_uninstall(&cfg, "probe", N), RH_E_INJECTED);
	hook_at = NULL;
	EQ(rh_install(&cfg, &v1), RH_OK);
	CHECK(dest_is(N, shabuf[0]) && file_has(rec, "probe	1	"));
}

int main(void)
{
	snprintf(root, sizeof root, "/tmp/rhtest.%d", (int)getpid());
	mkdir(root, 0755);
	test_sha();
	test_validation();
	test_source_hash_first();
	test_install_update();
	test_unmanaged();
	test_busy();
	test_failures_and_recovery();
	test_uninstall();
	{ char b[300]; snprintf(b, sizeof b, "rm -rf %s", root); sh("%s", b); }
	printf("%d checks, %d failed\n", checks, fails);
	return fails ? 1 : 0;
}
