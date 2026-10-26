/* HTTPS file download (Phase 7). mbedTLS 2.16 client, certificate AND hostname verification always on (VERIFY_REQUIRED,
 * TLS 1.2+, no insecure mode, no http:// URLs, no https->http redirects). Blocking; bounded by per-read and total
 * deadlines. Writes <dest>.part and renames it to <dest> only after the size and SHA-256 you asked for matched.
 * Knows nothing about catalogs or installs. */
#ifndef RH_NET_H
#define RH_NET_H
#include <stddef.h>
#include <stdint.h>

typedef struct {
	const char *ca_bundle;   /* PEM bundle of trusted roots (required) */
	const char *extra_ca;    /* optional second PEM file of roots (DEV test CA); NULL in production */
	unsigned connect_ms;     /* 0 = 10000 */
	unsigned read_ms;        /* 0 = 15000: no data for this long = failure */
	unsigned total_ms;       /* 0 = 180000 */
	/* optional: called about every 100 ms and at the end; return non-zero to cancel. total = 0 when unknown */
	int (*progress)(uint64_t done, uint64_t total, void *ctx);
	void *ctx;
} rh_net_cfg;

enum {
	RH_NET_OK = 0, RH_NET_E_ARG, RH_NET_E_OFFLINE, RH_NET_E_TLS, RH_NET_E_CERT_TIME, RH_NET_E_HTTP, RH_NET_E_REDIRECT,
	RH_NET_E_TOO_BIG, RH_NET_E_SIZE, RH_NET_E_HASH, RH_NET_E_IO, RH_NET_E_TIMEOUT, RH_NET_E_CANCEL, RH_NET_E_PROTO
};

/* url must be https://host[:port]/path. max_bytes bounds the body (hard). want_size / want_sha256 (64 lowercase hex) are
 * checked when non-zero / non-NULL. On failure nothing is left at dest or dest.part and msg gets a short reason. */
int rh_net_get_file(const rh_net_cfg *cfg, const char *url, const char *dest, uint64_t max_bytes, uint64_t want_size,
		    const char *want_sha256, char *msg, size_t msglen);

#endif
