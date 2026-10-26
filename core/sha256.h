/* SHA-256 (FIPS 180-4). Small, dependency-free; swap for mbedTLS later if it
 * is already linked (only rh_sha256_file is used outside this file). */
#ifndef RH_SHA256_H
#define RH_SHA256_H
#include <stddef.h>
#include <stdint.h>

typedef struct {
	uint32_t h[8];
	uint64_t len;
	uint8_t buf[64];
	size_t n;
} rh_sha256;

void rh_sha256_init(rh_sha256 *s);
void rh_sha256_update(rh_sha256 *s, const void *data, size_t len);
void rh_sha256_final(rh_sha256 *s, uint8_t out[32]);

/* Hash a file. hex gets 64 lowercase chars + NUL; *size gets the byte count
 * (may be NULL). Returns 0, or -1 on any open/read error. */
int rh_sha256_file(const char *path, char hex[65], uint64_t *size);

#endif
