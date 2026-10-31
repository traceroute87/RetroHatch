/* RetroHatch Nano install adapter: install/update a LOCAL OPK into
 * /mnt/Applications. No network, no UI, no catalog parsing, no scripts run.
 *
 * Device facts this relies on (observed on RG Nano, 2026-10-25):
 *  - sysapps_scan.sh scans only "*.opk" in the root of the app dirs, so a
 *    "<name>.opk.new" file is invisible to the Apps drawer.
 *  - The scanner rescans only when path|size|mtime changes, so every update
 *    must move the mtime (see rh_install.c: pick_mtime).
 *  - opkrun loop-mounts the running OPK as squashfs (at /opk).
 * Not assumed: FAT rename is power-loss-safe. A journal + backup make an
 * interrupted install recoverable by rh_recover(). */
#ifndef RH_INSTALL_H
#define RH_INSTALL_H
#include <stdint.h>
#include <time.h>

#define RH_NANO_APPS_DIR  "/mnt/Applications"
#define RH_NANO_STATE_DIR "/mnt/FunKey/.retrohatch" /* not a scanned dir */

typedef enum {
	RH_OK = 0,
	RH_E_ARG,           /* bad app id / version / hash string */
	RH_E_DEST,          /* dest name not allowed, or dirs unusable */
	RH_E_SRC,           /* source missing / unreadable */
	RH_E_SIZE,          /* source size != expected */
	RH_E_HASH,          /* sha256 mismatch */
	RH_E_SPACE,         /* not enough free storage */
	RH_E_BUSY,          /* target OPK is mounted (running or stale mount) */
	RH_E_UNKNOWN_MOUNT, /* could not determine mount state: fail closed */
	RH_E_UNMANAGED,     /* target exists but RetroHatch did not install it */
	RH_E_IO,
	RH_E_MTIME,         /* could not give the file a scanner-visible mtime */
	RH_E_RECOVER,       /* failed and could not roll back: run rh_recover */
	RH_E_INJECTED       /* test hook */
} rh_err;

typedef struct {
	const char *apps_dir;    /* must already exist */
	const char *state_dir;   /* created (one level) if missing */
	const char *proc_mounts; /* "/proc/mounts" */
	const char *sys_block;   /* "/sys/block" */
	uint64_t reserve_bytes;  /* free-space margin; 0 = 1 MiB */
	time_t (*now)(void);     /* NULL = time(NULL) */
	/* Test seam, NULL in production. Called at named steps; return 0 to
	 * continue, 1 to simulate an error, 2 to simulate a crash/power loss
	 * (function returns at once, no cleanup). */
	int (*hook)(const char *step);
} rh_cfg;

typedef struct {
	const char *app_id;   /* [a-z0-9-], matches catalog id */
	const char *version;
	const char *dest_name; /* bare file name ending in .opk */
	const char *src_path;  /* local file to install */
	uint64_t size;         /* expected bytes */
	const char *sha256;    /* expected, 64 lowercase hex */
} rh_pkg;

void rh_cfg_nano(rh_cfg *c);
rh_err rh_install(const rh_cfg *c, const rh_pkg *p);
/* Finish or undo an interrupted install. Safe to call at every startup. */
rh_err rh_recover(const rh_cfg *c);
/* Remove an OPK RetroHatch installed (record + hash must match). Protected,
 * unmanaged, mounted or unknown-mount-state targets are refused. */
rh_err rh_uninstall(const rh_cfg *c, const char *app_id, const char *dest_name);
const char *rh_strerr(rh_err e);
/* Where rh_install() would put dest_name on the Nano, after the same name checks and with no file access (a preview).
 * 1 = target filled; 0 = rh_install() would refuse these names, why = short reason. */
int rh_plan_target(const char *app_id, const char *version, const char *dest_name, char *target, size_t n, char *why, size_t wn);

#endif
