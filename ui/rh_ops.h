/* DEV operations provider: connects the UI to the verified install engine
 * (platforms/nano/rh_install.c). Contains no install logic of its own: it only
 * gates which catalog entries may reach the engine and translates results.
 *
 * Gates (all fail closed):
 *  - state dir must be a directory named ".retrohatch-dev" (never the production state dir) and
 *    the local cache must live inside it;
 *  - only explicitly approved (app id, destination file) pairs, see ALLOWED in rh_ops.c;
 *  - catalog entry must be verified, with a sha256, a size and the approved destination;
 *  - the OPK must already be in the local cache as <cache>/<sha256>.opk. No network. */
#ifndef RH_OPS_H
#define RH_OPS_H
#include <stdint.h>
#include "rh_ui.h"

#define RH_DEV_STATE_DIR "/mnt/FunKey/.retrohatch-dev"   /* DEV: state, journal, backups, cache */
#define RH_DEV_CACHE_DIR RH_DEV_STATE_DIR "/cache"
#define RH_DEV_APPS_DIR  "/mnt/Applications"

typedef struct {
	const char *apps_dir, *state_dir, *cache_dir;
	const char *proc_mounts, *sys_block;   /* NULL = the real /proc/mounts and /sys/block */
	int (*hook)(const char *step);         /* engine test seam; NULL on the device */
	void (*refresh)(void);                 /* reload the UI model after a change */
	/* network (all optional; ca_bundle == NULL = downloads and catalog refresh stay disabled) */
	const char *ca_bundle, *extra_ca;      /* trusted roots; extra_ca = optional DEV test CA file */
	const char *mirror_file;               /* optional DEV file, lines "FROM TO": rewrite URL prefixes to a test server */
	const char *base_url, *base_url_file;  /* signed catalog directory URL (ends in '/'); optional override file */
	const char *cache_pkg, *bundled_pkg;   /* downloaded / bundled signed catalog files */
	const uint8_t (*keys)[32]; size_t nkeys;   /* trusted catalog keys */
	int (*progress)(uint64_t done, uint64_t total);   /* UI hook; non-zero = user cancelled */
} rh_ops_cfg;

/* Returns the UI ops to pass to rh_ui_set_ops(), or NULL when a gate rejects the configuration. */
const rh_ui_ops *rh_ops_init(const rh_ops_cfg *c);
/* Finish or undo an interrupted install (engine journal). Call once at startup. 0 = ok. */
int rh_ops_recover(void);
#endif
