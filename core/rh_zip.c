#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <zlib.h>
#include "rh_zip.h"

#define MAX_ENTRIES 4096
#define MAX_CD      (1u << 20)      /* central directory bytes we are willing to read */
#define CHUNK       16384

static uint16_t u16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t u32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

static int fail(char *msg, size_t n, int rc, const char *why) { snprintf(msg, n, "%s", why); return rc; }

static int read_at(int fd, uint64_t off, void *buf, size_t n)
{
	uint8_t *p = buf;
	while (n) {
		ssize_t r = pread(fd, p, n, (off_t)off);
		if (r < 0 && errno == EINTR) continue;
		if (r <= 0) return -1;
		p += r; off += (uint64_t)r; n -= (size_t)r;
	}
	return 0;
}

/* a name we are willing to match: no NUL/control bytes, no backslash, not absolute, no ".." component */
static int name_safe(const uint8_t *s, size_t n)
{
	size_t i, comp = 0;
	if (!n || n > 255 || s[0] == '/') return 0;
	for (i = 0; i <= n; i++) {
		if (i < n && (s[i] < 0x20 || s[i] == 0x7f || s[i] == '\\')) return 0;
		if (i == n || s[i] == '/') {
			if (i - comp == 2 && s[comp] == '.' && s[comp + 1] == '.') return 0;
			comp = i + 1;
		}
	}
	return 1;
}

int rh_zip_extract(const char *zip_path, const char *want, const char *dest, uint64_t max_out, char *msg, size_t msglen)
{
	int fd = -1, out = -1, rc = RH_ZIP_E_FORMAT, found = 0, z_init = 0;
	struct stat st;
	uint8_t tail[22 + 65535], *cd = NULL, lh[30], ibuf[CHUNK], obuf[CHUNK];
	size_t tail_n, i, eocd = (size_t)-1, wlen = want ? strlen(want) : 0, pos;
	uint64_t zsize, cd_off, cd_size, off, ent = 0;
	int created = 0;
	unsigned entries, k;
	uint32_t crc = 0, m_crc = 0, m_csize = 0, m_usize = 0, m_lho = 0;
	unsigned m_method = 0;
	z_stream zs;
	snprintf(msg, msglen, "Bad ZIP file");
	if (!wlen || wlen > 255 || strchr(want, '/') || !dest) return fail(msg, msglen, RH_ZIP_E_FORMAT, "Bad request");
	if ((fd = open(zip_path, O_RDONLY)) < 0) return fail(msg, msglen, RH_ZIP_E_IO, "Cannot open ZIP");
	if (fstat(fd, &st) || !S_ISREG(st.st_mode)) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Cannot read ZIP"); goto done; }
	zsize = (uint64_t)st.st_size;
	if (zsize < 22 || zsize > 0x7fffffffu) { rc = fail(msg, msglen, zsize < 22 ? RH_ZIP_E_FORMAT : RH_ZIP_E_UNSUPPORTED, zsize < 22 ? "Bad ZIP file" : "ZIP over 2 GB not supported"); goto done; }

	tail_n = zsize < sizeof tail ? (size_t)zsize : sizeof tail;
	if (read_at(fd, zsize - tail_n, tail, tail_n)) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Cannot read ZIP"); goto done; }
	for (i = tail_n - 22 + 1; i-- > 0;)   /* last end-of-central-directory record whose comment length reaches exactly the end */
		if (u32(tail + i) == 0x06054b50u && i + 22 + u16(tail + i + 20) == tail_n) { eocd = i; break; }
	if (eocd == (size_t)-1) goto done;
	if (u16(tail + eocd + 4) || u16(tail + eocd + 6)) { rc = fail(msg, msglen, RH_ZIP_E_UNSUPPORTED, "Multi-part ZIP not supported"); goto done; }
	entries = u16(tail + eocd + 10);
	cd_size = u32(tail + eocd + 12); cd_off = u32(tail + eocd + 16);
	if (entries == 0xFFFF || cd_size == 0xFFFFFFFFu || cd_off == 0xFFFFFFFFu) { rc = fail(msg, msglen, RH_ZIP_E_UNSUPPORTED, "ZIP64 not supported"); goto done; }
	if (entries != u16(tail + eocd + 8) || !entries || entries > MAX_ENTRIES || cd_size > MAX_CD || cd_off + cd_size > zsize - tail_n + eocd) goto done;
	if (!(cd = malloc((size_t)cd_size))) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Out of memory"); goto done; }
	if (read_at(fd, cd_off, cd, (size_t)cd_size)) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Cannot read ZIP"); goto done; }

	for (pos = 0, k = 0; k < entries; k++) {   /* central directory: find the one member whose BASE name is `want` */
		uint16_t flags, method, nl, el, cl; uint32_t attrs, csize, usize; unsigned host; const uint8_t *nm;
		if (pos + 46 > cd_size || u32(cd + pos) != 0x02014b50u) goto done;
		host = cd[pos + 5]; flags = u16(cd + pos + 8); method = u16(cd + pos + 10);
		nl = u16(cd + pos + 28); el = u16(cd + pos + 30); cl = u16(cd + pos + 32);
		attrs = u32(cd + pos + 38); csize = u32(cd + pos + 20); usize = u32(cd + pos + 24);
		if (pos + 46 + (size_t)nl + el + cl > cd_size) goto done;
		nm = cd + pos + 46;
		{   /* base name compare; entries that end in '/' are directories */
			size_t bs = nl; int hit;
			while (bs && nm[bs - 1] != '/') bs--;
			hit = nl && nm[nl - 1] != '/' && nl - bs == wlen && !memcmp(nm + bs, want, wlen);
			if (hit) {
				if (found++) { rc = fail(msg, msglen, RH_ZIP_E_AMBIGUOUS, "Two files with that name in the ZIP"); goto done; }
				if (!name_safe(nm, nl)) { rc = fail(msg, msglen, RH_ZIP_E_UNSAFE, "Unsafe file name in ZIP"); goto done; }
				if (flags & 0x41) { rc = fail(msg, msglen, RH_ZIP_E_UNSUPPORTED, "Encrypted ZIP not supported"); goto done; }
				if (method != 0 && method != 8) { rc = fail(msg, msglen, RH_ZIP_E_UNSUPPORTED, "ZIP compression not supported"); goto done; }
				if (csize == 0xFFFFFFFFu || usize == 0xFFFFFFFFu) { rc = fail(msg, msglen, RH_ZIP_E_UNSUPPORTED, "ZIP64 not supported"); goto done; }
				if (u16(cd + pos + 34)) { rc = fail(msg, msglen, RH_ZIP_E_UNSUPPORTED, "Multi-part ZIP not supported"); goto done; }
				if (host == 3 && (attrs >> 16) && ((attrs >> 16) & 0170000) != 0100000) { rc = fail(msg, msglen, RH_ZIP_E_UNSAFE, "Not a regular file in ZIP"); goto done; }   /* symlink, device, ... */
				if ((attrs & 0x10) || (attrs & 0x400)) { rc = fail(msg, msglen, RH_ZIP_E_UNSAFE, "Not a regular file in ZIP"); goto done; }   /* DOS directory / reparse point */
				if (!usize) { rc = fail(msg, msglen, RH_ZIP_E_SIZE, "File in ZIP is empty"); goto done; }
				if (usize > max_out) { rc = fail(msg, msglen, RH_ZIP_E_SIZE, "File in ZIP is too large"); goto done; }
				if (method == 0 ? csize != usize : (uint64_t)usize > (uint64_t)csize * 1100 + 64) { rc = fail(msg, msglen, RH_ZIP_E_SIZE, "ZIP sizes do not add up"); goto done; }
				m_crc = u32(cd + pos + 16); m_csize = csize; m_usize = usize; m_lho = u32(cd + pos + 42); m_method = method;
				ent = pos;
			}
		}
		pos += 46 + (size_t)nl + el + cl;
	}
	if (!found) { rc = fail(msg, msglen, RH_ZIP_E_NOTFOUND, "File not found in ZIP"); goto done; }

	{   /* local header: same name and method as the central entry, data fully inside the file before the central directory */
		uint16_t nl = u16(cd + ent + 28), lnl, lel; uint64_t data;
		if (read_at(fd, m_lho, lh, 30) || u32(lh) != 0x04034b50u) goto done;
		lnl = u16(lh + 26); lel = u16(lh + 28);
		if (lnl != nl || u16(lh + 8) != m_method || (u16(lh + 6) & 0x41)) goto done;
		{
			uint8_t lname[256];
			if (lnl > sizeof lname || read_at(fd, (uint64_t)m_lho + 30, lname, lnl) || memcmp(lname, cd + ent + 46, lnl)) goto done;
		}
		data = (uint64_t)m_lho + 30 + lnl + lel;
		if (data + m_csize > cd_off) goto done;
		off = data;
	}

	if ((out = open(dest, O_WRONLY | O_CREAT | O_EXCL, 0644)) < 0) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Cannot create file"); goto done; }
	created = 1;
	if (m_method == 8) {
		memset(&zs, 0, sizeof zs);
		if (inflateInit2(&zs, -MAX_WBITS) != Z_OK) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Out of memory"); goto done; }
		z_init = 1;
	}
	{
		uint64_t in_left = m_csize, out_total = 0; int zr = Z_OK;
		while (in_left || (m_method == 8 && zr != Z_STREAM_END)) {
			size_t take = in_left > CHUNK ? CHUNK : (size_t)in_left;
			if (take && read_at(fd, off, ibuf, take)) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Cannot read ZIP"); goto done; }
			off += take; in_left -= take;
			if (m_method == 0) {
				crc = (uint32_t)crc32(crc, ibuf, (uInt)take); out_total += take;
				if (write(out, ibuf, take) != (ssize_t)take) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Write failed (storage full?)"); goto done; }
				continue;
			}
			zs.next_in = ibuf; zs.avail_in = (uInt)take;
			do {
				size_t got;
				zs.next_out = obuf; zs.avail_out = CHUNK;
				zr = inflate(&zs, Z_NO_FLUSH);
				if (zr != Z_OK && zr != Z_STREAM_END && zr != Z_BUF_ERROR) { rc = fail(msg, msglen, RH_ZIP_E_FORMAT, "Damaged data in ZIP"); goto done; }
				got = CHUNK - zs.avail_out;
				out_total += got;
				if (out_total > m_usize) { rc = fail(msg, msglen, RH_ZIP_E_SIZE, "ZIP data larger than declared"); goto done; }
				crc = (uint32_t)crc32(crc, obuf, (uInt)got);
				if (got && write(out, obuf, got) != (ssize_t)got) { rc = fail(msg, msglen, RH_ZIP_E_IO, "Write failed (storage full?)"); goto done; }
				if (zr == Z_STREAM_END) break;
				if (zr == Z_BUF_ERROR && !zs.avail_in) break;   /* needs more input */
			} while (zs.avail_in || zs.avail_out == 0);
			if (zr == Z_STREAM_END && (in_left || zs.avail_in)) { rc = fail(msg, msglen, RH_ZIP_E_FORMAT, "Extra data in ZIP"); goto done; }
			if (!in_left && zr != Z_STREAM_END) { rc = fail(msg, msglen, RH_ZIP_E_FORMAT, "ZIP data is cut short"); goto done; }
		}
		if (out_total != m_usize) { rc = fail(msg, msglen, RH_ZIP_E_SIZE, "ZIP size does not match"); goto done; }
	}
	if (crc != m_crc) { rc = fail(msg, msglen, RH_ZIP_E_CRC, "ZIP checksum mismatch"); goto done; }
	if (fsync(out) || close(out)) { out = -1; rc = fail(msg, msglen, RH_ZIP_E_IO, "Write failed (storage full?)"); goto done; }
	out = -1; msg[0] = 0; rc = RH_ZIP_OK;
done:
	if (z_init) inflateEnd(&zs);
	if (out >= 0) close(out);
	if (rc != RH_ZIP_OK && created) unlink(dest);   /* only a file this call created */
	free(cd);
	if (fd >= 0) close(fd);
	return rc;
}
