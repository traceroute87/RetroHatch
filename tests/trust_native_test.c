/* Native verifier unit tests: RFC 8032 vectors through crypto_ed25519_check (the primitive RetroHatch uses),
 * plus argument/size/key-list guards of rh_catalog_verify that must trigger before any cryptography.
 * Policy and cross-implementation checks live in tests/test_trust_native.py. Build: make -C tests native-test */
#include "../core/rh_catalog.h"
#include "../vendor/monocypher/monocypher-ed25519.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rfc8032_vectors.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)

int main(void)
{
	uint8_t sig[64], pk[32], *msg;
	int i, b;
	static const uint8_t k0[1][32] = {{1}};
	static const uint8_t two[2] = {'{', '}'};
	uint8_t *big;
	rh_cat_state st;
	const char *why;

	for (i = 0; i < NVEC; i++) {
		msg = malloc(vec[i].msglen + 1);
		memcpy(msg, vec[i].msg, vec[i].msglen);
		CHECK(crypto_ed25519_check(vec[i].sig, vec[i].pk, msg, vec[i].msglen) == 0);
		for (b = 0; b < 64 * 8; b += 7) {          /* any signature bit flip is rejected */
			memcpy(sig, vec[i].sig, 64);
			sig[b / 8] ^= (uint8_t)(1 << (b % 8));
			CHECK(crypto_ed25519_check(sig, vec[i].pk, msg, vec[i].msglen) != 0);
		}
		for (b = 0; b < 32 * 8; b += 5) {          /* any public key bit flip is rejected */
			memcpy(pk, vec[i].pk, 32);
			pk[b / 8] ^= (uint8_t)(1 << (b % 8));
			CHECK(crypto_ed25519_check(vec[i].sig, pk, msg, vec[i].msglen) != 0);
		}
		if (vec[i].msglen) {
			msg[vec[i].msglen - 1] ^= 1;           /* modified message */
			CHECK(crypto_ed25519_check(vec[i].sig, vec[i].pk, msg, vec[i].msglen) != 0);
			CHECK(crypto_ed25519_check(vec[i].sig, vec[i].pk, msg, vec[i].msglen - 1) != 0); /* truncated */
		}
		/* S + L (malleable encoding of the same signature) must not verify */
		{
			static const uint8_t L[32] = {0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
				0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10};
			unsigned c = 0;
			int k;
			memcpy(sig, vec[i].sig, 64);
			for (k = 0; k < 32; k++) {
				c += sig[32 + k] + L[k];
				sig[32 + k] = (uint8_t)c;
				c >>= 8;
			}
			if (!c)
				CHECK(crypto_ed25519_check(sig, vec[i].pk, vec[i].msg, vec[i].msglen) != 0);
		}
		free(msg);
	}

	/* guards that run before any crypto */
	CHECK(rh_catalog_verify(two, 2, two, 2, NULL, 0, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_NOKEY);
	CHECK(rh_catalog_verify(two, 0, two, 2, k0, 1, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_SIZE);
	CHECK(rh_catalog_verify(two, 2, two, 0, k0, 1, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_SIZE);
	CHECK(rh_catalog_verify(two, 2, two, RH_CAT_MAX_SIG + 1, k0, 1, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_SIZE);
	big = calloc(RH_CAT_MAX_INDEX + 1, 1);
	CHECK(rh_catalog_verify(big, RH_CAT_MAX_INDEX + 1, two, 2, k0, 1, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_SIZE);
	free(big);
	CHECK(rh_catalog_verify(NULL, 2, two, 2, k0, 1, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_ARG);
	CHECK(rh_catalog_verify(two, 2, two, 2, k0, 1, NULL, "f", NULL, &st, NULL, &why) == RH_CAT_E_ARG);
	CHECK(rh_catalog_verify(two, 2, two, 2, k0, 1, "d", "f", NULL, NULL, NULL, &why) == RH_CAT_E_ARG);
	CHECK(rh_catalog_verify(two, 2, two, 2, NULL, 1, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_ARG);
	CHECK(rh_catalog_verify(two, 2, two, 2, k0, 1, "d", "f", NULL, &st, NULL, &why) == RH_CAT_E_SIGDOC); /* "{}" is no signature doc */

	if (fails) {
		printf("%d FAILED\n", fails);
		return 1;
	}
	printf("native tests OK (%d RFC 8032 vectors)\n", NVEC);
	return 0;
}
