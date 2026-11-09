/* Extract ONE regular member of a local ZIP file into a plain file (experimental test installs only).
 * Strict by design, everything else is refused: no ZIP64, no multi-disk, no encryption, only "stored" and "deflate";
 * the member is found by its base name, which must be unique; symlinks, directories and special files are refused;
 * the declared size must be <= max_out and the inflated size and CRC-32 must match exactly. The member's path inside the
 * ZIP is never used to build an output path: the caller names the destination. On any failure nothing is left at dest.
 * Needs zlib (inflate, crc32). */
#ifndef RH_ZIP_H
#define RH_ZIP_H
#include <stddef.h>
#include <stdint.h>

enum { RH_ZIP_OK = 0, RH_ZIP_E_IO, RH_ZIP_E_FORMAT, RH_ZIP_E_NOTFOUND, RH_ZIP_E_AMBIGUOUS, RH_ZIP_E_UNSUPPORTED, RH_ZIP_E_UNSAFE,
       RH_ZIP_E_SIZE, RH_ZIP_E_CRC };

/* dest must not exist yet (opened O_EXCL). msg gets a short reason on failure. */
int rh_zip_extract(const char *zip_path, const char *member_base_name, const char *dest, uint64_t max_out, char *msg, size_t msglen);
#endif
