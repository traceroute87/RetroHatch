/* Production builds: no trusted catalog key until the production key has been generated offline (docs/TRUST.md).
 * With zero keys every catalog fails verification, so nothing signed can be shown. */
#ifndef RH_TRUSTED_KEYS_H
#define RH_TRUSTED_KEYS_H
#include <stdint.h>
static const uint8_t RH_TRUSTED_KEYS[][32] = {{0}};
#define RH_N_TRUSTED_KEYS 0
#endif
