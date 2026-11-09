/* Headless driver for the EXPERIMENTAL test install (ui/rh_ops_exp.inc): the very same download / install / uninstall code the DEV program runs
 * on a button press, without the UI. Used by tools/batch_test.py (host build: classify and download; Nano build: install and uninstall).
 * It adds no install logic of its own: every action is rh_ops' cand_state / cand_do, so the installer's checks (squashfs magic, SHA-256,
 * denylist, "never overwrite what RetroHatch did not install", mount/busy check, journal) all apply.
 *
 *   rh_exp_cli --state DIR --apps DIR --cands FILE [--ca FILE] classify
 *   rh_exp_cli ... download|install|uninstall|facts ID
 *   rh_exp_cli ... recover
 * DIR must be named .retrohatch-dev (DEV state only; the ops gate refuses anything else). Output is one line per result:
 *   "RESULT <rc> <message>" (rc 0 ok, 1 failed, 2 failed and needs recovery), classify: "<id>\t<state>\t<why>\t<file>".
 * Exit status 0 only when the action succeeded. */
#define _XOPEN_SOURCE 700
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "../../../ui/rh_ops.h"

static rh_model m;

static int find(const char *id)
{
	int i;
	for (i = 0; i < m.n_cands; i++) if (!strcmp(m.cands[i].id, id)) return i;
	return -1;
}

int main(int argc, char **argv)
{
	const char *state = NULL, *apps = NULL, *cands = NULL, *ca = NULL, *cmd = NULL, *id = NULL;
	char cache[400], pkg[400], msg[200], why[80], f[80], h[48]; uint8_t key[1][32]; rh_ops_cfg oc; const rh_ui_ops *ops; int i, k, rc = 1;
	for (i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--state") && i + 1 < argc) state = argv[++i];
		else if (!strcmp(argv[i], "--apps") && i + 1 < argc) apps = argv[++i];
		else if (!strcmp(argv[i], "--cands") && i + 1 < argc) cands = argv[++i];
		else if (!strcmp(argv[i], "--ca") && i + 1 < argc) ca = argv[++i];
		else if (!cmd) cmd = argv[i];
		else if (!id) id = argv[i];
		else return 64;
	}
	if (!state || !apps || !cands || !cmd) { fprintf(stderr, "usage: rh_exp_cli --state DIR --apps DIR --cands FILE [--ca FILE] classify|download|install|uninstall|facts|recover [ID]\n"); return 64; }
	snprintf(cache, sizeof cache, "%s/cache", state); snprintf(pkg, sizeof pkg, "%s/catalog.pkg", state);
	mkdir(state, 0755); mkdir(cache, 0755);
	memset(&oc, 0, sizeof oc); memset(key, 0, sizeof key); key[0][0] = 1;   /* the catalog is never used here; a non-zero key only switches the network code on */
	oc.apps_dir = apps; oc.state_dir = state; oc.cache_dir = cache;
	oc.ca_bundle = ca; oc.base_url = "https://localhost/"; oc.cache_pkg = pkg; oc.bundled_pkg = pkg; oc.keys = (const uint8_t (*)[32])key; oc.nkeys = 1;
	if (!(ops = rh_ops_init(&oc))) { printf("RESULT 1 ops gate rejected the configuration (state dir must be named .retrohatch-dev)\n"); return 1; }
	rh_model_load_none(&m, "cli", state);
	rh_model_load_candidates(&m, cands);
	if (!strcmp(cmd, "recover")) { rc = rh_ops_recover(); printf("RESULT %d recovery\n", rc ? 2 : 0); return rc != 0; }
	if (!ops->cand_state) { printf("RESULT 1 build without RH_EXPERIMENTAL\n"); return 1; }
	if (!strcmp(cmd, "classify")) {
		for (i = 0; i < m.n_cands; i++) {
			k = ops->cand_state(&m.cands[i], 0, why, sizeof why);
			ops->cand_facts(&m.cands[i], RH_X_DOWNLOAD, f, sizeof f, h, sizeof h);
			printf("%s\t%s\t%s\t%s\n", m.cands[i].id, k == RH_X_DOWNLOAD ? "download" : k == RH_X_INSTALL ? "cached" : k == RH_X_UNINSTALL ? "installed" : "no", why, f);
		}
		return 0;
	}
	if (!id || (i = find(id)) < 0) { printf("RESULT 1 unknown candidate\n"); return 1; }
	if (!strcmp(cmd, "facts")) { ops->cand_facts(&m.cands[i], RH_X_INSTALL, f, sizeof f, h, sizeof h); printf("FILE %s\nHASH %s\n", f, h); return 0; }
	k = !strcmp(cmd, "download") ? RH_X_DOWNLOAD : !strcmp(cmd, "install") ? RH_X_INSTALL : !strcmp(cmd, "uninstall") ? RH_X_UNINSTALL : -1;
	if (k < 0) return 64;
	msg[0] = 0;
	rc = ops->cand_do(&m.cands[i], k, msg, sizeof msg);
	printf("RESULT %d %s\n", rc, msg);
	return rc != 0;
}
