/* Signed catalog source for the DEV UI (Phase 7): loads the newest signed catalog the device already holds (bundled in the
 * OPK, or downloaded earlier) and refreshes it over HTTPS. Everything goes through rh_catalog_verify_persist(): signature,
 * policy gates and rollback state. A catalog that does not verify is never shown, never cached as trusted.
 *
 * Cache file = one atomic file: <signature document>\n<index bytes>  (so a power cut can never pair a new index with an old
 * signature). A downloaded pair is first written as <cache>.new, verified, then renamed over <cache>; if the rename never
 * happened, rh_src_load still finds the verified .new. */
#ifndef RH_SOURCE_H
#define RH_SOURCE_H
#include <stddef.h>
#include <stdint.h>
#include "../core/rh_net.h"

/* Where the signed catalog is published (GitHub Pages: static index.json + index.json.sig, see docs/PUBLISHING.md).
 * Assumes the repository traceroute87/RetroHatch; change here if it is named differently. DEV builds can override it with
 * <state>/catalog-url.txt. */
#define RH_CATALOG_BASE_URL "https://traceroute87.github.io/RetroHatch/catalog/"
#define RH_DEVICE_ID   "rg-nano"
#define RH_FIRMWARE_ID "funkeyos-drum78"

typedef struct {
	const char *state_dir;      /* holds catalog.state (rollback record) */
	const char *cache_pkg;      /* downloaded catalog; "<cache_pkg>.new" is the in-flight copy */
	const char *bundled_pkg;    /* read-only snapshot shipped in the OPK; may be missing */
	const uint8_t (*keys)[32];  /* trusted Ed25519 public keys; none = nothing can verify */
	size_t nkeys;
} rh_src_cfg;

typedef struct {
	char source[16];            /* "bundled" | "cached" */
	unsigned serial;
	char expires[11];
	char why[96];               /* when load fails: the reason to show */
} rh_src_info;

/* 0 = *index (malloc, caller frees) holds a verified index and info is filled; otherwise info->why says why not. */
int rh_src_load(const rh_src_cfg *c, char **index, size_t *len, rh_src_info *info);

/* Downloads <base_url>index.json and index.json.sig, verifies them like rh_src_load, and only then replaces the cache.
 * 0 = ok (msg says updated / already current); else msg says why and the cache is untouched. base_url must end in '/'. */
int rh_src_refresh(const rh_src_cfg *c, const rh_net_cfg *net, const char *base_url, char *msg, size_t n);
#endif
