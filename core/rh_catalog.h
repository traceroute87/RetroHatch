/* Signed-catalog verifier (Phase 6C-2). Pure function: no file, network or clock access.
 * Verifies an index produced by tools/trust.py: Ed25519 (Monocypher crypto_ed25519_check, RFC 8032) over the
 * exact bytes, then a strict canonical-JSON parse and the publish gates (approved, verified, available,
 * release URL, destination, device/firmware, revocation). Fails closed. Policy mirrors tools/trust.py check_index. */
#ifndef RH_CATALOG_H
#define RH_CATALOG_H
#include <stddef.h>
#include <stdint.h>

#define RH_CAT_MAX_INDEX (256u * 1024u)  /* tools/trust.py MAX_INDEX */
#define RH_CAT_MAX_SIG 1024u
#define RH_CAT_MAX_TOKENS 8192u          /* tools/trust.py MAX_TOKENS; 20 B each => 160 KiB heap while verifying */
#define RH_CAT_MAX_DEPTH 12
#define RH_CAT_MAX_ARTIFACTS 256

enum {
	RH_CAT_OK = 0, RH_CAT_E_ARG, RH_CAT_E_SIZE, RH_CAT_E_NOKEY, RH_CAT_E_SIGDOC, RH_CAT_E_UNKNOWN_KEY,
	RH_CAT_E_BADSIG, RH_CAT_E_PARSE, RH_CAT_E_POLICY, RH_CAT_E_DEVICE, RH_CAT_E_ROLLBACK, RH_CAT_E_FORK,
	RH_CAT_E_LIMIT, RH_CAT_E_NOMEM,
	RH_CAT_E_STATE /* rollback state corrupt/unreadable/unsaveable (rh_catalog_state.h; never returned by rh_catalog_verify) */
};

typedef struct {
	uint32_t serial;     /* newest accepted index */
	uint8_t sha256[32];  /* of its exact bytes */
} rh_cat_state;

typedef struct {
	uint32_t serial;
	uint32_t n_apps;
	uint32_t n_artifacts;  /* published artifacts for the requested device */
	char expires[11];      /* "" or YYYY-MM-DD; informational only, never enforced (device clock is untrusted) */
} rh_cat_info;

/* keys: nkeys trusted raw 32-byte Ed25519 public keys (nkeys == 0 fails closed).
 * prev: newest state accepted so far, or NULL on first use. On RH_CAT_OK, *next is the state to persist (caller's job).
 * *why (optional) gets a static message. */
int rh_catalog_verify(const uint8_t *index, size_t index_len, const uint8_t *sig, size_t sig_len,
		      const uint8_t (*keys)[32], size_t nkeys, const char *device, const char *firmware,
		      const rh_cat_state *prev, rh_cat_state *next, rh_cat_info *info, const char **why);

#endif
