/* HOST-ONLY driver for the Nano install engine, called by tools/plan.py.
 * Never a default path: apps and state dirs are required, so it cannot touch
 * a device or /mnt/Applications by accident.
 *
 *   rh_host_cli --apps DIR --state DIR [--mounts FILE --sysblock DIR] \
 *       install <app_id> <version> <dest_name> <src> <size> <sha256>
 *   rh_host_cli --apps DIR --state DIR uninstall <app_id> <dest_name> | recover */
#include "../rh_install.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
	rh_cfg c;
	rh_err e;
	int i = 1;

	rh_cfg_nano(&c);
	c.apps_dir = c.state_dir = NULL;
	for (; i + 1 < argc && !strncmp(argv[i], "--", 2); i += 2) {
		if (!strcmp(argv[i], "--apps")) c.apps_dir = argv[i + 1];
		else if (!strcmp(argv[i], "--state")) c.state_dir = argv[i + 1];
		else if (!strcmp(argv[i], "--mounts")) c.proc_mounts = argv[i + 1];
		else if (!strcmp(argv[i], "--sysblock")) c.sys_block = argv[i + 1];
		else return 64;
	}
	if (!c.apps_dir || !c.state_dir || i >= argc)
		return 64;
	if (!strcmp(argv[i], "recover") && i + 1 == argc) {
		e = rh_recover(&c);
	} else if (!strcmp(argv[i], "uninstall") && i + 3 == argc) {
		e = rh_uninstall(&c, argv[i + 1], argv[i + 2]);
	} else if (!strcmp(argv[i], "install") && i + 7 == argc) {
		rh_pkg p = {argv[i + 1], argv[i + 2], argv[i + 3], argv[i + 4],
			    strtoull(argv[i + 5], NULL, 10), argv[i + 6]};
		e = rh_install(&c, &p);
	} else {
		return 64;
	}
	printf("result=%d (%s)\n", (int)e, rh_strerr(e));
	return e ? 1 : 0;
}
