/* Persistent rollback state for the signed catalog (Phase 6C-4). One small file, independent of the UI and of the
 * install engine (it does not include rh_install.h and never touches installed.tsv, journals, backups or OPKs).
 *
 *   <dir>/catalog.state       "RHCS1 <serial> <sha256 hex> <check>\n"   newest accepted {serial, sha256}
 *   <dir>/catalog.state.tmp   write-ahead copy, ignored by load
 *   <dir>/catalog.state.bak   previous record, only while a save is in flight
 *
 * Rules: absent state = first run (accept any validly signed catalog); ANY existing-but-unreadable or corrupt state is
 * refused, never treated as first run; state only advances after the catalog verified completely; it never moves back.
 * LIMITATION: deleting every state file (or the whole directory) is indistinguishable from a first run, so local state
 * alone cannot stop an attacker who can delete files from replaying an old signed catalog. A real defence needs
 * something outside this storage (shipped minimum serial, a trusted clock or server). See docs/TRUST.md.
 * Crash-safety pattern as in rh_install.c: write tmp, fsync, rename, fsync dir; FAT rename atomicity is NOT assumed, so
 * the previous record is parked as .bak and a lone .bak is recovered by rh_cstate_load. */
#ifndef RH_CATALOG_STATE_H
#define RH_CATALOG_STATE_H
#include "rh_catalog.h"

#define RH_CSTATE_FILE "catalog.state"

enum { RH_ST_OK = 0, RH_ST_NONE, RH_ST_CORRUPT, RH_ST_IO, RH_ST_ARG, RH_ST_REJECTED, RH_ST_INJECTED };

/* Test seam, NULL in production. Called at "tmp_open", "tmp_written", "bak_made", "renamed", "synced".
 * Return 0 to continue, 1 to simulate an I/O error, 2 to simulate a crash (function returns at once, no cleanup). */
typedef int (*rh_cstate_hook)(const char *step);

/* RH_ST_OK: *out filled. RH_ST_NONE: nothing stored (first run). RH_ST_CORRUPT / RH_ST_IO: refuse to continue. */
int rh_cstate_load(const char *dir, rh_cat_state *out);

/* Atomically replaces the record. RH_ST_REJECTED if it would lower the serial or fork it (same serial, other hash);
 * RH_ST_CORRUPT / RH_ST_IO if the existing record cannot be trusted (nothing is overwritten). Identical record = no-op OK. */
int rh_cstate_save(const char *dir, const rh_cat_state *s, rh_cstate_hook hook);

/* rh_catalog_verify() with persistence: loads state (corrupt/unreadable => RH_CAT_E_STATE, nothing verified against a
 * reset baseline), verifies the catalog completely, and only then saves the new serial/hash. A catalog that verified but
 * whose state could not be saved is reported as RH_CAT_E_STATE (fail closed). Nothing is written on any failure. */
int rh_catalog_verify_persist(const char *state_dir, const uint8_t *index, size_t index_len, const uint8_t *sig,
			      size_t sig_len, const uint8_t (*keys)[32], size_t nkeys, const char *device,
			      const char *firmware, rh_cat_info *info, const char **why, rh_cstate_hook hook);

#endif
