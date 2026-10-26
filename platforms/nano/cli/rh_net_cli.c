/* Test driver for core/rh_net.c (host and ARM). Writes only DEST and DEST.part.
 *   rh_get --ca FILE [--extra-ca FILE] [--max N] [--size N] [--sha HEX] [--read-ms N] [--total-ms N] [--cancel-after N] URL DEST
 * Prints "OK <bytes>" or "FAIL <code> <message>"; exit 0 only on OK. */
#include "../../../core/rh_net.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static uint64_t cancel_after;
static int progress(uint64_t done, uint64_t total, void *ctx)
{
	(void)total; (void)ctx;
	return cancel_after && done >= cancel_after;
}

int main(int argc, char **argv)
{
	rh_net_cfg c;
	uint64_t max = 1u << 20, size = 0;
	const char *sha = NULL, *url = NULL, *dest = NULL;
	char msg[160];
	int i, rc;

	memset(&c, 0, sizeof c);
	for (i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--ca") && i + 1 < argc) c.ca_bundle = argv[++i];
		else if (!strcmp(argv[i], "--extra-ca") && i + 1 < argc) c.extra_ca = argv[++i];
		else if (!strcmp(argv[i], "--max") && i + 1 < argc) max = strtoull(argv[++i], NULL, 10);
		else if (!strcmp(argv[i], "--size") && i + 1 < argc) size = strtoull(argv[++i], NULL, 10);
		else if (!strcmp(argv[i], "--sha") && i + 1 < argc) sha = argv[++i];
		else if (!strcmp(argv[i], "--read-ms") && i + 1 < argc) c.read_ms = (unsigned)atoi(argv[++i]);
		else if (!strcmp(argv[i], "--total-ms") && i + 1 < argc) c.total_ms = (unsigned)atoi(argv[++i]);
		else if (!strcmp(argv[i], "--cancel-after") && i + 1 < argc) { cancel_after = strtoull(argv[++i], NULL, 10); c.progress = progress; }
		else if (!url) url = argv[i];
		else if (!dest) dest = argv[i];
		else return 64;
	}
	if (!url || !dest) return 64;
	rc = rh_net_get_file(&c, url, dest, max, size, sha, msg, sizeof msg);
	if (rc) {
		printf("FAIL %d %s\n", rc, msg);
		return rc;
	}
	{
		struct stat st;
		printf("OK %lld\n", stat(dest, &st) ? -1LL : (long long)st.st_size);
	}
	return 0;
}
