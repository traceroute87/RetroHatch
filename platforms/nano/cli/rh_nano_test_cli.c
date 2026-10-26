/* HARDWARE TEST CLI -- not part of the product. Drives rh_install() on a real
 * RG Nano for the Phase 3B checks. It can only touch OPKs named rhprobe*.opk
 * in /mnt/Applications, so it cannot disturb real apps.
 *
 *   rh_nano_test_cli [--state-dir DIR] [--fail-at STEP | --crash-at STEP] \
 *       install <app_id> <version> <dest_name> <src> <size> <sha256>
 *   rh_nano_test_cli [--state-dir DIR] [--fail-at STEP | --crash-at STEP] uninstall <app_id> <dest_name>
 *   rh_nano_test_cli [--state-dir DIR] recover
 *
 * STEP: staged backed_up journaled renamed synced recorded (install)
 *       backed_up journaled removed recorded (uninstall; recorded is crash-only)
 * --fail-at   simulates an error at STEP (engine rolls back)
 * --crash-at  simulates a crash at STEP (process just exits; use `recover`)
 * Neither cuts power or touches anything outside the test files. */
#include "../rh_install.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *at;
static int mode;

static int hook(const char *step)
{
	if (at && !strcmp(step, at)) {
		fprintf(stderr, "hook: %s at '%s'\n", mode == 2 ? "CRASH" : "FAIL", step);
		return mode;
	}
	return 0;
}

static int probe_name(const char *n)
{
	size_t l = strlen(n);
	return !strncmp(n, "rhprobe", 7) && l > 11 && !strcmp(n + l - 4, ".opk");
}

int main(int argc, char **argv)
{
	rh_cfg c;
	rh_err e;
	int i = 1;

	rh_cfg_nano(&c);
	c.state_dir = "/mnt/FunKey/.retrohatch-test"; /* never the production state dir */
	c.hook = hook;
	for (; i < argc && !strncmp(argv[i], "--", 2); i += 2) {
		if (i + 1 >= argc)
			return 64;
		if (!strcmp(argv[i], "--state-dir") && !strncmp(argv[i + 1], "/mnt/FunKey/.retrohatch-test", 28))
			c.state_dir = argv[i + 1];
		else if (!strcmp(argv[i], "--fail-at")) { at = argv[i + 1]; mode = 1; }
		else if (!strcmp(argv[i], "--crash-at")) { at = argv[i + 1]; mode = 2; }
		else return 64;
	}
	if (i < argc && !strcmp(argv[i], "recover")) {
		e = rh_recover(&c);
	} else if (i + 7 == argc && !strcmp(argv[i], "install")) {
		rh_pkg p = {argv[i + 1], argv[i + 2], argv[i + 3], argv[i + 4],
			    strtoull(argv[i + 5], NULL, 10), argv[i + 6]};
		if (!probe_name(p.dest_name)) {
			fprintf(stderr, "refused: test CLI only handles rhprobe*.opk\n");
			return 65;
		}
		e = rh_install(&c, &p);
	} else if (i + 3 == argc && !strcmp(argv[i], "uninstall")) {
		if (!probe_name(argv[i + 2])) {
			fprintf(stderr, "refused: test CLI only handles rhprobe*.opk\n");
			return 65;
		}
		e = rh_uninstall(&c, argv[i + 1], argv[i + 2]);
	} else {
		fprintf(stderr, "usage: see source header\n");
		return 64;
	}
	printf("result=%d (%s)\n", (int)e, rh_strerr(e));
	return e ? 1 : 0;
}
