/* See rh_net.h. */
#define _GNU_SOURCE 1 /* strcasestr */
#include "rh_net.h"
#include "sha256.h"
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/time.h>
#include <openssl/err.h>
#include <openssl/ssl.h>
#include <openssl/x509.h>
#include <openssl/x509_vfy.h>
#include <openssl/x509v3.h>

#define MAX_REDIRECTS 5
#define MAX_HDR_LINE 4096
#define MAX_HDR_TOTAL 16384

typedef struct {
	char host[256], path[1024];
	int port;
} url_t;

typedef struct {
	int fd;                   /* blocking socket with send/receive timeouts; -1 = none */
	SSL *ssl;                 /* NULL = no TLS session */
	unsigned char buf[4096];  /* read-ahead */
	size_t pos, len;
	long long deadline;       /* CLOCK_MONOTONIC ms */
	int err;                  /* RH_NET_E_* from the failing read */
	char why[96];
} conn;

static long long now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void hostport(const url_t *u, char *o, size_t n)
{
	if (u->port == 443) snprintf(o, n, "%s", u->host);
	else snprintf(o, n, "%s:%d", u->host, u->port);
}

static int fail(char *msg, size_t n, int code, const char *why)
{
	if (msg && n)
		snprintf(msg, n, "%s", why);
	return code;
}

/* ---- TLS context + CA store: built once per process ----
 * OpenSSL (the firmware's own libssl/libcrypto 1.1.1) instead of mbedTLS 2.16, which has no TLS 1.3: static.miraheze.org (the FunKey wiki's file host) answers
 * a TLS 1.2 hello with "protocol_version" alert. TLS 1.2 stays the floor; 1.3 is negotiated when the server offers it. Verification is mandatory. */
static SSL_CTX *g_ctx;
static char g_ca_key[600];

static int load_ca(const rh_net_cfg *c)
{
	char key[600];
	struct stat st;
	SSL_CTX *x;

	snprintf(key, sizeof key, "%s|%s", c->ca_bundle, c->extra_ca ? c->extra_ca : "");
	if (g_ctx && !strcmp(key, g_ca_key))
		return 0;
	if (g_ctx) {
		SSL_CTX_free(g_ctx);
		g_ctx = NULL;
	}
	ERR_clear_error();
	x = SSL_CTX_new(TLS_client_method());
	if (!x)
		return -1;
	SSL_CTX_set_min_proto_version(x, TLS1_2_VERSION);
	SSL_CTX_set_options(x, SSL_OP_NO_COMPRESSION | SSL_OP_NO_RENEGOTIATION);
#ifdef SSL_OP_IGNORE_UNEXPECTED_EOF
	SSL_CTX_set_options(x, SSL_OP_IGNORE_UNEXPECTED_EOF);   /* OpenSSL 3: a close without close_notify is an EOF (length checks catch truncation), as with 1.1.1 */
#endif
	SSL_CTX_set_verify(x, SSL_VERIFY_PEER, NULL);          /* never relaxed: an untrusted or mismatched certificate fails the handshake */
	if (SSL_CTX_load_verify_locations(x, c->ca_bundle, NULL) != 1 ||
	    sk_X509_OBJECT_num(X509_STORE_get0_objects(SSL_CTX_get_cert_store(x))) <= 0 ||
	    (c->extra_ca && !stat(c->extra_ca, &st) && S_ISREG(st.st_mode) && SSL_CTX_load_verify_locations(x, c->extra_ca, NULL) != 1)) {
		SSL_CTX_free(x);
		return -1;
	}
	g_ctx = x;
	snprintf(g_ca_key, sizeof g_ca_key, "%s", key);
	return 0;
}

/* ---- URL ---- */
static int parse_url(const char *u, url_t *o)
{
	const char *p, *e;
	size_t n;

	if (!u || strncmp(u, "https://", 8))
		return -1;
	for (p = u; *p; p++)
		if ((unsigned char)*p <= ' ' || (unsigned char)*p >= 0x7f || *p == '\\')
			return -1;
	p = u + 8;
	e = p + strcspn(p, "/:?#");
	n = (size_t)(e - p);
	if (!n || n >= sizeof o->host || memchr(p, '@', n) || memchr(p, '[', n))
		return -1;
	memcpy(o->host, p, n);
	o->host[n] = 0;
	o->port = 443;
	if (*e == ':') {
		char *end;
		long v = strtol(e + 1, &end, 10);
		if (end == e + 1 || v < 1 || v > 65535 || (*end && *end != '/'))
			return -1;
		o->port = (int)v;
		e = end;
	}
	if (*e == '?' || *e == '#')
		snprintf(o->path, sizeof o->path, "/%s", e);
	else
		snprintf(o->path, sizeof o->path, "%s", *e ? e : "/");
	return strlen(o->path) < sizeof o->path - 1 ? 0 : -1;
}

/* ---- connection ---- */
static int tcp_connect(const url_t *u, long long deadline, unsigned connect_ms, char *why, size_t wn)
{
	struct addrinfo hints, *res, *a;
	char port[8];
	int fd = -1, gai;

	memset(&hints, 0, sizeof hints);
	hints.ai_socktype = SOCK_STREAM;
	snprintf(port, sizeof port, "%d", u->port);
	gai = getaddrinfo(u->host, port, &hints, &res);
	if (gai) {
		snprintf(why, wn, "Cannot reach %.60s (offline?)", u->host);
		return -1;
	}
	for (a = res; a; a = a->ai_next) {
		long long left = deadline - now_ms(), lim = connect_ms;
		fd_set w;
		struct timeval tv;
		int soerr = 0;
		socklen_t sl = sizeof soerr;

		if (left <= 0)
			break;
		if (lim > left)
			lim = left;
		fd = socket(a->ai_family, a->ai_socktype, a->ai_protocol);
		if (fd < 0)
			continue;
		fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
		if (connect(fd, a->ai_addr, a->ai_addrlen) && errno == EINPROGRESS) {
			FD_ZERO(&w);
			FD_SET(fd, &w);
			tv.tv_sec = (time_t)(lim / 1000);
			tv.tv_usec = (suseconds_t)(lim % 1000) * 1000;
			if (select(fd + 1, NULL, &w, NULL, &tv) > 0 && !getsockopt(fd, SOL_SOCKET, SO_ERROR, &soerr, &sl) && !soerr)
				break;
		} else if (!errno || errno == EISCONN) {
			break;
		}
		close(fd);
		fd = -1;
	}
	freeaddrinfo(res);
	if (fd < 0) {
		snprintf(why, wn, "Cannot connect to %.60s (offline?)", u->host);
		return -1;
	}
	fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) & ~O_NONBLOCK);
	return fd;
}

static void conn_close(conn *c)
{
	if (c->ssl) {
		SSL_shutdown(c->ssl);   /* one call: sends close_notify, does not wait for the peer */
		SSL_free(c->ssl);
		c->ssl = NULL;
	}
	if (c->fd >= 0) {
		close(c->fd);
		c->fd = -1;
	}
}

static int conn_open(conn *c, const rh_net_cfg *cfg, const url_t *u)
{
	int fd, r;
	unsigned rd = cfg->read_ms ? cfg->read_ms : 15000;
	struct timeval tv;
	unsigned char ip[16];
	long vf;

	memset(c->why, 0, sizeof c->why);
	c->pos = c->len = 0;
	c->fd = -1;
	fd = tcp_connect(u, c->deadline, cfg->connect_ms ? cfg->connect_ms : 10000, c->why, sizeof c->why);
	if (fd < 0)
		return RH_NET_E_OFFLINE;
	c->fd = fd;
	tv.tv_sec = (time_t)(rd / 1000);
	tv.tv_usec = (suseconds_t)(rd % 1000) * 1000;
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
	setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
	ERR_clear_error();
	c->ssl = SSL_new(g_ctx);
	if (!c->ssl || !SSL_set_fd(c->ssl, fd)) {
		snprintf(c->why, sizeof c->why, "TLS setup failed");
		return RH_NET_E_TLS;
	}
	if (inet_pton(AF_INET, u->host, ip) == 1 || inet_pton(AF_INET6, u->host, ip) == 1) {
		if (!X509_VERIFY_PARAM_set1_ip_asc(SSL_get0_param(c->ssl), u->host)) {
			snprintf(c->why, sizeof c->why, "TLS setup failed");
			return RH_NET_E_TLS;
		}
	} else if (!SSL_set_tlsext_host_name(c->ssl, u->host) || !SSL_set1_host(c->ssl, u->host)) {   /* SNI + hostname check */
		snprintf(c->why, sizeof c->why, "TLS setup failed");
		return RH_NET_E_TLS;
	}
	errno = 0;
	r = SSL_connect(c->ssl);
	if (r != 1) {
		int e = SSL_get_error(c->ssl, r);
		vf = SSL_get_verify_result(c->ssl);
		if ((e == SSL_ERROR_SYSCALL || e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) && (errno == EAGAIN || errno == EWOULDBLOCK)) { snprintf(c->why, sizeof c->why, "TLS handshake timed out"); return RH_NET_E_TIMEOUT; }
		if (vf == X509_V_ERR_CERT_HAS_EXPIRED || vf == X509_V_ERR_CERT_NOT_YET_VALID) {
			snprintf(c->why, sizeof c->why, "Certificate date invalid: check the device date and time");
			return RH_NET_E_CERT_TIME;
		}
		if (vf == X509_V_ERR_HOSTNAME_MISMATCH || vf == X509_V_ERR_IP_ADDRESS_MISMATCH) snprintf(c->why, sizeof c->why, "Certificate is for a different host");
		else if (vf == X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT_LOCALLY || vf == X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT || vf == X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT ||
			 vf == X509_V_ERR_SELF_SIGNED_CERT_IN_CHAIN || vf == X509_V_ERR_CERT_UNTRUSTED) snprintf(c->why, sizeof c->why, "Certificate not trusted");
		else if (vf != X509_V_OK) snprintf(c->why, sizeof c->why, "Certificate rejected");
		else snprintf(c->why, sizeof c->why, "TLS handshake failed");
		return RH_NET_E_TLS;
	}
	if (now_ms() > c->deadline) { snprintf(c->why, sizeof c->why, "Timed out"); return RH_NET_E_TIMEOUT; }
	if (SSL_get_verify_result(c->ssl) != X509_V_OK) {   /* belt and braces: SSL_VERIFY_PEER already fails the handshake */
		snprintf(c->why, sizeof c->why, "Certificate rejected");
		return RH_NET_E_TLS;
	}
	return 0;
}

static int conn_write_all(conn *c, const char *s, size_t n)
{
	while (n) {
		int r = SSL_write(c->ssl, s, n > 16384 ? 16384 : (int)n);
		if (r <= 0)
			return -1;
		s += r;
		n -= (size_t)r;
	}
	return 0;
}

/* >0 bytes, 0 = clean end of stream, <0 = error (c->err set) */
static int conn_read(conn *c, unsigned char *b, size_t n)
{
	for (;;) {
		int r, e;
		if (now_ms() > c->deadline) { c->err = RH_NET_E_TIMEOUT; snprintf(c->why, sizeof c->why, "Download took too long"); return -1; }
		ERR_clear_error();
		errno = 0;
		r = SSL_read(c->ssl, b, n > 16384 ? 16384 : (int)n);
		if (r > 0)
			return r;
		e = SSL_get_error(c->ssl, r);
		if (e == SSL_ERROR_ZERO_RETURN)
			return 0;
		if ((e == SSL_ERROR_SYSCALL || e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) && (errno == EAGAIN || errno == EWOULDBLOCK)) {   /* SO_RCVTIMEO expired (the BIO reports it as "retry") */
			c->err = RH_NET_E_TIMEOUT; snprintf(c->why, sizeof c->why, "Connection stalled");
			return -1;
		}
		if (e == SSL_ERROR_SYSCALL && (r == 0 || errno == ECONNRESET))   /* end without close_notify: same as before, the size checks catch truncation */
			return 0;
		c->err = RH_NET_E_IO;
		snprintf(c->why, sizeof c->why, "Connection error");
		return -1;
	}
}

static int br_fill(conn *c)
{
	int r = conn_read(c, c->buf, sizeof c->buf);
	if (r <= 0)
		return r;
	c->pos = 0;
	c->len = (size_t)r;
	return r;
}

/* one header/chunk line without CRLF. >=0 length, -1 error (c->err), -2 EOF */
static int br_line(conn *c, char *out, size_t cap)
{
	size_t n = 0;
	for (;;) {
		if (c->pos == c->len) {
			int r = br_fill(c);
			if (r < 0) return -1;
			if (r == 0) return -2;
		}
		while (c->pos < c->len) {
			char ch = (char)c->buf[c->pos++];
			if (ch == '\n') {
				if (n && out[n - 1] == '\r') n--;
				out[n] = 0;
				return (int)n;
			}
			if (n + 1 >= cap) { c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Header too long"); return -1; }
			out[n++] = ch;
		}
	}
}

/* body bytes: buffered first, then the wire */
static int br_read(conn *c, unsigned char *b, size_t n)
{
	if (c->pos < c->len) {
		size_t k = c->len - c->pos < n ? c->len - c->pos : n;
		memcpy(b, c->buf + c->pos, k);
		c->pos += k;
		return (int)k;
	}
	return conn_read(c, b, n);
}

typedef struct {
	int status;
	long long clen;     /* -1 unknown */
	int chunked;
	char location[1100];
} reply;

static int read_headers(conn *c, reply *r)
{
	char line[MAX_HDR_LINE];
	size_t total = 0;
	int n, first = 1;

	memset(r, 0, sizeof *r);
	r->clen = -1;
	for (;;) {
		n = br_line(c, line, sizeof line);
		if (n == -2) { c->err = RH_NET_E_IO; snprintf(c->why, sizeof c->why, "Connection closed early"); return -1; }
		if (n < 0) return -1;
		total += (size_t)n + 2;
		if (total > MAX_HDR_TOTAL) { c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Headers too large"); return -1; }
		if (first) {
			char *sp;
			first = 0;
			if (strncmp(line, "HTTP/1.", 7) || !(sp = strchr(line, ' ')) || sp[1] < '1' || sp[1] > '5') {
				c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Not an HTTP reply"); return -1;
			}
			r->status = atoi(sp + 1);
			continue;
		}
		if (!n)
			return 0;
		if (!strncasecmp(line, "content-length:", 15)) {
			char *e;
			unsigned long long v = strtoull(line + 15, &e, 10);
			while (*e == ' ') e++;
			if (e == line + 15 || *e || v > (1ULL << 40)) { c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Bad Content-Length"); return -1; }
			r->clen = (long long)v;
		} else if (!strncasecmp(line, "transfer-encoding:", 18)) {
			if (strcasestr(line + 18, "chunked")) r->chunked = 1;
			else if (strcasestr(line + 18, "identity") == NULL) { c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Unsupported encoding"); return -1; }
		} else if (!strncasecmp(line, "content-encoding:", 17)) {
			const char *v = line + 17;
			while (*v == ' ') v++;
			if (*v && strcasecmp(v, "identity")) { c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Unsupported encoding"); return -1; }
		} else if (!strncasecmp(line, "location:", 9)) {
			const char *v = line + 9;
			while (*v == ' ') v++;
			if (snprintf(r->location, sizeof r->location, "%s", v) >= (int)sizeof r->location) { c->err = RH_NET_E_REDIRECT; snprintf(c->why, sizeof c->why, "Bad redirect"); return -1; }
		}
	}
}

typedef struct {
	FILE *f;
	rh_sha256 sha;
	uint64_t got, max, total;
	const rh_net_cfg *cfg;
	long long last_cb;
} sink;

static int sink_put(conn *c, sink *s, const unsigned char *b, size_t n)
{
	if (s->got + n > s->max) { c->err = RH_NET_E_TOO_BIG; snprintf(c->why, sizeof c->why, "File is larger than the catalog says"); return -1; }
	if (fwrite(b, 1, n, s->f) != n) { c->err = RH_NET_E_IO; snprintf(c->why, sizeof c->why, "Cannot write to storage"); return -1; }
	rh_sha256_update(&s->sha, b, n);
	s->got += n;
	if (s->cfg->progress && now_ms() - s->last_cb >= 100) {
		s->last_cb = now_ms();
		if (s->cfg->progress(s->got, s->total, s->cfg->ctx)) { c->err = RH_NET_E_CANCEL; snprintf(c->why, sizeof c->why, "Cancelled"); return -1; }
	}
	return 0;
}

/* returns 0 = body complete, -1 = error (c->err) */
static int read_body(conn *c, const reply *r, sink *s)
{
	unsigned char b[4096];
	int n;

	if (r->chunked) {
		for (;;) {
			char line[128], *e;
			unsigned long long sz;
			n = br_line(c, line, sizeof line);
			if (n == -2) { c->err = RH_NET_E_SIZE; snprintf(c->why, sizeof c->why, "Download was cut short"); return -1; }
			if (n < 0) return -1;
			sz = strtoull(line, &e, 16);
			if (e == line || (*e && *e != ';' && *e != ' ') || sz > (1ULL << 32)) { c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Bad chunk"); return -1; }
			if (!sz) {                                            /* trailers until an empty line */
				do { n = br_line(c, line, sizeof line); } while (n > 0);
				return n == -1 ? -1 : 0;
			}
			while (sz) {
				n = br_read(c, b, sz < sizeof b ? (size_t)sz : sizeof b);
				if (n < 0) return -1;
				if (!n) { c->err = RH_NET_E_SIZE; snprintf(c->why, sizeof c->why, "Download was cut short"); return -1; }
				if (sink_put(c, s, b, (size_t)n)) return -1;
				sz -= (unsigned)n;
			}
			n = br_line(c, line, sizeof line);                    /* CRLF after the chunk */
			if (n != 0) { if (n == -1) return -1; c->err = RH_NET_E_PROTO; snprintf(c->why, sizeof c->why, "Bad chunk"); return -1; }
		}
	}
	if (r->clen >= 0) {
		unsigned long long left = (unsigned long long)r->clen;
		if (left > s->max) { c->err = RH_NET_E_TOO_BIG; snprintf(c->why, sizeof c->why, "File is larger than the catalog says"); return -1; }
		while (left) {
			n = br_read(c, b, left < sizeof b ? (size_t)left : sizeof b);
			if (n < 0) return -1;
			if (!n) { c->err = RH_NET_E_SIZE; snprintf(c->why, sizeof c->why, "Download was cut short"); return -1; }
			if (sink_put(c, s, b, (size_t)n)) return -1;
			left -= (unsigned)n;
		}
		return 0;
	}
	for (;;) {                                                       /* until the server closes */
		n = br_read(c, b, sizeof b);
		if (n < 0) return -1;
		if (!n) return 0;
		if (sink_put(c, s, b, (size_t)n)) return -1;
	}
}

static void hex(const uint8_t *b, char *o)
{
	int i;
	for (i = 0; i < 32; i++) { o[2 * i] = "0123456789abcdef"[b[i] >> 4]; o[2 * i + 1] = "0123456789abcdef"[b[i] & 15]; }
	o[64] = 0;
}

int rh_net_get_file(const rh_net_cfg *cfg, const char *url, const char *dest, uint64_t max_bytes, uint64_t want_size,
		    const char *want_sha256, char *msg, size_t msglen)
{
	url_t u;
	conn c;
	reply rep;
	sink s;
	char part[1100], req[1500], digest[65], hp[300];
	uint8_t d[32];
	int hop, rc = RH_NET_E_ARG, have_part = 0;
	unsigned total_ms;

	if (msg && msglen) msg[0] = 0;
	if (!cfg || !cfg->ca_bundle || !url || !dest || !max_bytes || strlen(dest) + 6 >= sizeof part)
		return fail(msg, msglen, RH_NET_E_ARG, "Bad request");
	if (want_sha256 && strlen(want_sha256) != 64)
		return fail(msg, msglen, RH_NET_E_ARG, "Bad request");
	if (parse_url(url, &u))
		return fail(msg, msglen, RH_NET_E_ARG, "Only https:// links are allowed");
	if (load_ca(cfg))
		return fail(msg, msglen, RH_NET_E_TLS, "No trusted certificates on this device");
	snprintf(part, sizeof part, "%s.part", dest);
	memset(&c, 0, sizeof c);
	c.fd = -1;
	total_ms = cfg->total_ms ? cfg->total_ms : 180000;
	c.deadline = now_ms() + total_ms;
	memset(&s, 0, sizeof s);
	s.cfg = cfg;
	s.max = max_bytes;
	s.total = want_size;
	rh_sha256_init(&s.sha);
	s.f = fopen(part, "wb");
	if (!s.f)
		return fail(msg, msglen, RH_NET_E_IO, "Cannot write to storage");
	have_part = 1;

	for (hop = 0;; hop++) {
		int r;
		if (hop > MAX_REDIRECTS) { rc = RH_NET_E_REDIRECT; snprintf(c.why, sizeof c.why, "Too many redirects"); goto out; }
		r = conn_open(&c, cfg, &u);
		if (r) { rc = r; goto out; }
		hostport(&u, hp, sizeof hp);
		snprintf(req, sizeof req, "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: RetroHatch/1\r\nAccept: */*\r\n"
			 "Accept-Encoding: identity\r\nConnection: close\r\n\r\n", u.path, hp);
		if (conn_write_all(&c, req, strlen(req))) { rc = RH_NET_E_IO; snprintf(c.why, sizeof c.why, "Connection error"); goto out; }
		c.err = RH_NET_E_IO;
		if (read_headers(&c, &rep)) { rc = c.err; goto out; }
		if (rep.status >= 300 && rep.status < 400 && rep.status != 304 && rep.status != 300) {
			url_t nu;
			char abs[1500];
			if (!rep.location[0]) { rc = RH_NET_E_REDIRECT; snprintf(c.why, sizeof c.why, "Bad redirect"); goto out; }
			if (rep.location[0] == '/' && rep.location[1] != '/')
				snprintf(abs, sizeof abs, "https://%s%s", hp, rep.location);
			else
				snprintf(abs, sizeof abs, "%s", rep.location);
			if (parse_url(abs, &nu)) { rc = RH_NET_E_REDIRECT; snprintf(c.why, sizeof c.why, "Redirect to a non-https link refused"); goto out; }
			conn_close(&c);
			u = nu;
			continue;
		}
		if (rep.status != 200) {
			rc = RH_NET_E_HTTP;
			snprintf(c.why, sizeof c.why, rep.status == 404 ? "Not found on the server (404)" : "Server error (HTTP %d)", rep.status);
			goto out;
		}
		if (rep.clen >= 0 && !s.total)
			s.total = (uint64_t)rep.clen;
		if (want_size && rep.clen >= 0 && (uint64_t)rep.clen != want_size) { rc = RH_NET_E_SIZE; snprintf(c.why, sizeof c.why, "Size differs from the catalog"); goto out; }
		c.err = RH_NET_E_IO;
		if (read_body(&c, &rep, &s)) { rc = c.err; goto out; }
		break;
	}
	conn_close(&c);
	if (fflush(s.f) || fsync(fileno(s.f)) < 0 || fclose(s.f)) { s.f = NULL; rc = RH_NET_E_IO; snprintf(c.why, sizeof c.why, "Cannot write to storage"); goto out; }
	s.f = NULL;
	if (want_size && s.got != want_size) { rc = RH_NET_E_SIZE; snprintf(c.why, sizeof c.why, "Size differs from the catalog"); goto out; }
	rh_sha256_final(&s.sha, d);
	hex(d, digest);
	if (want_sha256 && strcmp(digest, want_sha256)) { rc = RH_NET_E_HASH; snprintf(c.why, sizeof c.why, "SHA-256 mismatch: file rejected"); goto out; }
	if (rename(part, dest)) { rc = RH_NET_E_IO; snprintf(c.why, sizeof c.why, "Cannot write to storage"); goto out; }
	have_part = 0;
	if (cfg->progress) cfg->progress(s.got, s.total, cfg->ctx);
	rc = RH_NET_OK;
out:
	conn_close(&c);
	if (s.f) fclose(s.f);
	if (have_part) unlink(part);
	if (msg && msglen)
		snprintf(msg, msglen, "%s", rc ? c.why : "");
	return rc;
}
