/* Signed-catalog verifier. See rh_catalog.h. Order mirrors tools/trust.py verify():
 * sizes/keys -> signature document -> key id -> Ed25519 over the raw bytes -> canonical parse -> policy -> rollback.
 * Nothing in the index is parsed before the signature has been checked. */
#include "rh_catalog.h"
#include "sha256.h"
#include "../vendor/monocypher/monocypher-ed25519.h"
#include <stdlib.h>
#include <string.h>

typedef struct {
	uint8_t t;
	uint32_t s, e, next, n; /* span of the value (strings: inside the quotes), index after subtree, child count */
} tok;
enum { T_OBJ = 1, T_ARR, T_STR, T_INT, T_LIT };

typedef struct {
	const uint8_t *p;
	size_t len, pos;
	tok *t;
	size_t nt, cap;
	int code;
	const char *why;
} ps;

static int fail(ps *P, int code, const char *why)
{
	P->code = code;
	P->why = why;
	return -1;
}

static int hexv(int c)
{
	return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

/* ---- strict canonical JSON (exactly what tools/trust.py canonical() emits) ---- */

static int pstr(ps *P, int key, uint32_t *s, uint32_t *e)
{
	size_t i = P->pos + 1;
	unsigned v;
	int k;

	*s = (uint32_t)i;
	for (;;) {
		int c;
		if (i >= P->len)
			return fail(P, RH_CAT_E_PARSE, "unterminated string");
		c = P->p[i];
		if (c == '"')
			break;
		if (c < 0x20 || c > 0x7e)
			return fail(P, RH_CAT_E_PARSE, "non-canonical character");
		if (c != '\\') {
			i++;
			continue;
		}
		if (key)
			return fail(P, RH_CAT_E_PARSE, "escape in key");
		if (i + 1 >= P->len)
			return fail(P, RH_CAT_E_PARSE, "unterminated string");
		c = P->p[i + 1];
		if (c && strchr("\"\\bfnrt", c)) {
			i += 2;
			continue;
		}
		if (c != 'u' || i + 6 > P->len)
			return fail(P, RH_CAT_E_PARSE, "non-canonical escape");
		for (v = 0, k = 0; k < 4; k++) {
			int h = hexv(P->p[i + 2 + k]);
			if (h < 0)
				return fail(P, RH_CAT_E_PARSE, "non-canonical escape");
			v = v << 4 | (unsigned)h;
		}
		/* Python emits \uXXXX only for control chars without a short form, DEL and non-ASCII */
		if ((v >= 0x20 && v <= 0x7e) || v == 8 || v == 9 || v == 10 || v == 12 || v == 13)
			return fail(P, RH_CAT_E_PARSE, "non-canonical escape");
		i += 6;
	}
	*e = (uint32_t)i;
	P->pos = i + 1;
	return 0;
}

static int pnum(ps *P, uint32_t *s, uint32_t *e)
{
	size_t i = P->pos;
	unsigned long long v = 0;

	if (P->p[i] == '-')
		return fail(P, RH_CAT_E_PARSE, "negative number");
	*s = (uint32_t)i;
	if (P->p[i] == '0') {
		i++;
	} else {
		while (i < P->len && P->p[i] >= '0' && P->p[i] <= '9') {
			v = v * 10 + (unsigned)(P->p[i] - '0');
			if (v > 2147483647ULL)
				return fail(P, RH_CAT_E_PARSE, "number out of range");
			i++;
		}
		if (i == *s)
			return fail(P, RH_CAT_E_PARSE, "unexpected character");
	}
	if (i < P->len && P->p[i] >= '0' && P->p[i] <= '9')
		return fail(P, RH_CAT_E_PARSE, "leading zero");
	*e = (uint32_t)i;
	P->pos = i;
	return 0;
}

static int pval(ps *P, int depth)
{
	size_t me;
	int c;

	if (depth > RH_CAT_MAX_DEPTH)
		return fail(P, RH_CAT_E_LIMIT, "nesting too deep");
	if (P->pos >= P->len)
		return fail(P, RH_CAT_E_PARSE, "unexpected end");
	if (P->nt >= P->cap)
		return fail(P, RH_CAT_E_LIMIT, "too many tokens");
	me = P->nt++;
	P->t[me].n = 0;
	c = P->p[P->pos];
	if (c == '{' || c == '[') {
		int obj = c == '{';
		const uint8_t *pk = NULL;
		size_t pkl = 0;

		P->t[me].t = obj ? T_OBJ : T_ARR;
		P->t[me].s = (uint32_t)P->pos++;
		if (P->pos < P->len && P->p[P->pos] == (obj ? '}' : ']')) {
			P->pos++;
		} else {
			for (;;) {
				if (obj) {
					size_t k;
					uint32_t s, e;
					size_t l, m;
					int d;

					if (P->pos >= P->len || P->p[P->pos] != '"')
						return fail(P, RH_CAT_E_PARSE, "expected key");
					if (P->nt >= P->cap)
						return fail(P, RH_CAT_E_LIMIT, "too many tokens");
					k = P->nt++;
					if (pstr(P, 1, &s, &e))
						return -1;
					P->t[k].t = T_STR;
					P->t[k].s = s;
					P->t[k].e = e;
					P->t[k].next = (uint32_t)k + 1;
					P->t[k].n = 0;
					l = e - s;
					if (pk) {
						m = l < pkl ? l : pkl;
						d = memcmp(P->p + s, pk, m);
						if (d < 0 || (d == 0 && l <= pkl))
							return fail(P, RH_CAT_E_PARSE, "duplicate or unsorted keys");
					}
					pk = P->p + s;
					pkl = l;
					if (P->pos >= P->len || P->p[P->pos] != ':')
						return fail(P, RH_CAT_E_PARSE, "expected ':'");
					P->pos++;
				}
				if (pval(P, depth + 1))
					return -1;
				P->t[me].n++;
				if (P->pos < P->len && P->p[P->pos] == ',') {
					P->pos++;
					continue;
				}
				if (P->pos < P->len && P->p[P->pos] == (obj ? '}' : ']')) {
					P->pos++;
					break;
				}
				return fail(P, RH_CAT_E_PARSE, "expected ',' or closer");
			}
		}
		P->t[me].e = (uint32_t)P->pos;
	} else if (c == '"') {
		P->t[me].t = T_STR;
		if (pstr(P, 0, &P->t[me].s, &P->t[me].e))
			return -1;
	} else if (c == '-' || (c >= '0' && c <= '9')) {
		P->t[me].t = T_INT;
		if (pnum(P, &P->t[me].s, &P->t[me].e))
			return -1;
	} else {
		static const char *lit[] = {"true", "false", "null"};
		int i, ok = 0;
		for (i = 0; i < 3; i++) {
			size_t l = strlen(lit[i]);
			if (P->pos + l <= P->len && !memcmp(P->p + P->pos, lit[i], l)) {
				P->t[me].t = T_LIT;
				P->t[me].s = (uint32_t)P->pos;
				P->t[me].e = (uint32_t)(P->pos + l);
				P->pos += l;
				ok = 1;
				break;
			}
		}
		if (!ok)
			return fail(P, RH_CAT_E_PARSE, "unexpected character");
	}
	P->t[me].next = (uint32_t)P->nt;
	return 0;
}

static int parse_doc(ps *P, const uint8_t *b, size_t n, tok *buf, size_t cap)
{
	memset(P, 0, sizeof *P);
	P->p = b;
	P->len = n;
	P->t = buf;
	P->cap = cap;
	if (pval(P, 0))
		return -1;
	if (P->pos != P->len)
		return fail(P, RH_CAT_E_PARSE, "trailing data (not canonical)");
	if (P->t[0].t != T_OBJ)
		return fail(P, RH_CAT_E_PARSE, "not an object");
	return 0;
}

/* ---- accessors and field kinds ---- */

static size_t slen(const ps *P, size_t t) { return P->t[t].e - P->t[t].s; }
static const uint8_t *sptr(const ps *P, size_t t) { return P->p + P->t[t].s; }

static int span_eq(const ps *P, size_t t, const char *lit)
{
	size_t l = strlen(lit);
	return P->t[t].t == T_STR && slen(P, t) == l && !memcmp(sptr(P, t), lit, l);
}

static int tok_eq(const ps *P, size_t a, size_t b)
{
	return P->t[a].t == T_STR && P->t[b].t == T_STR && slen(P, a) == slen(P, b) && !memcmp(sptr(P, a), sptr(P, b), slen(P, a));
}

static int lc(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

static int ci_eq(const uint8_t *a, const char *b, size_t n)
{
	while (n--)
		if (lc(*a++) != lc((unsigned char)*b++))
			return 0;
	return 1;
}

static long oget(const ps *P, size_t o, const char *key)
{
	size_t i = o + 1, n = P->t[o].n;
	while (n--) {
		if (span_eq(P, i, key))
			return (long)i + 1;
		i = P->t[i + 1].next;
	}
	return -1;
}

static int in_list(const uint8_t *s, size_t l, const char *list)
{
	while (*list) {
		size_t w = strcspn(list, " ");
		if (w == l && !memcmp(s, list, l))
			return 1;
		list += w + (list[w] == ' ');
	}
	return 0;
}

static int check_obj(ps *P, size_t o, const char *allowed, const char *required)
{
	size_t i = o + 1, n = P->t[o].n;

	if (P->t[o].t != T_OBJ)
		return fail(P, RH_CAT_E_POLICY, "expected object");
	while (n--) {
		if (!in_list(sptr(P, i), slen(P, i), allowed))
			return fail(P, RH_CAT_E_POLICY, "unknown field");
		i = P->t[i + 1].next;
	}
	while (*required) {
		char k[32];
		size_t w = strcspn(required, " ");
		memcpy(k, required, w);
		k[w] = 0;
		if (oget(P, o, k) < 0)
			return fail(P, RH_CAT_E_POLICY, "missing field");
		required += w + (required[w] == ' ');
	}
	return 0;
}

static int plain(const ps *P, size_t t)
{
	size_t i;
	if (P->t[t].t != T_STR)
		return 0;
	for (i = 0; i < slen(P, t); i++)
		if (sptr(P, t)[i] == '\\')
			return 0;
	return 1;
}

enum { K_ANY, K_STR, K_ID, K_HTTPS, K_SHA, K_DATE, K_PINT, K_ENUM, K_DEST, K_UINT };

static long ival(const ps *P, size_t t)
{
	long v = 0;
	size_t i;
	for (i = 0; i < slen(P, t); i++)
		v = v * 10 + (sptr(P, t)[i] - '0');
	return v;
}

static int chk(ps *P, long t, int kind, const char *list)
{
	const uint8_t *s;
	size_t l, i;

	if (t < 0)
		return fail(P, RH_CAT_E_POLICY, "missing field");
	if (kind == K_PINT || kind == K_UINT) {
		if (P->t[t].t != T_INT || (kind == K_PINT && ival(P, t) < 1))
			return fail(P, RH_CAT_E_POLICY, "bad integer field");
		return 0;
	}
	if (P->t[t].t != T_STR)
		return fail(P, RH_CAT_E_POLICY, "expected string field");
	s = sptr(P, t);
	l = slen(P, t);
	if (kind == K_ANY)
		return 0;
	if (kind == K_STR) {
		if (l < 1)
			return fail(P, RH_CAT_E_POLICY, "empty string field");
		return 0;
	}
	if (!plain(P, t))
		return fail(P, RH_CAT_E_POLICY, "bad string field");
	switch (kind) {
	case K_ID:
		if (l < 1 || l > 64 || !((s[0] >= 'a' && s[0] <= 'z') || (s[0] >= '0' && s[0] <= '9')))
			return fail(P, RH_CAT_E_POLICY, "bad id");
		for (i = 1; i < l; i++)
			if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '-'))
				return fail(P, RH_CAT_E_POLICY, "bad id");
		return 0;
	case K_HTTPS:
		if (l <= 8 || memcmp(s, "https://", 8))
			return fail(P, RH_CAT_E_POLICY, "not an https url");
		for (i = 8; i < l; i++)
			if (s[i] == ' ')
				return fail(P, RH_CAT_E_POLICY, "not an https url");
		return 0;
	case K_SHA:
		if (l != 64)
			return fail(P, RH_CAT_E_POLICY, "bad sha256");
		for (i = 0; i < l; i++)
			if (hexv(s[i]) < 0)
				return fail(P, RH_CAT_E_POLICY, "bad sha256");
		return 0;
	case K_DATE:
		if (l != 10)
			return fail(P, RH_CAT_E_POLICY, "bad date");
		for (i = 0; i < 10; i++)
			if (i == 4 || i == 7 ? s[i] != '-' : !(s[i] >= '0' && s[i] <= '9'))
				return fail(P, RH_CAT_E_POLICY, "bad date");
		return 0;
	case K_ENUM:
		if (!in_list(s, l, list))
			return fail(P, RH_CAT_E_POLICY, "value not allowed");
		return 0;
	case K_DEST: {
		static const char *deny[] = {"tarafi.opk", "freewares_funkey-s.opk", "poweroff_funkey-s.opk", "reboot_funkey-s.opk",
			"installmusic.opk", "clock_funkey-s.opk", "connectivity_funkey-s.opk", "retrohatch.opk",
			"retrohatch_funkey-s.opk", NULL}; /* lower-case copy of rh_install.c ok_dest(); drift is tested */
		int d;
		if (l < 5 || l > 64 || !ci_eq(s + l - 4, ".opk", 4))
			return fail(P, RH_CAT_E_POLICY, "bad destination");
		for (i = 0; i < l; i++)
			if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '.' || s[i] == '_' || s[i] == '-'))
				return fail(P, RH_CAT_E_POLICY, "bad destination");
		for (d = 0; deny[d]; d++)
			if (strlen(deny[d]) == l && ci_eq(s, deny[d], l))
				return fail(P, RH_CAT_E_POLICY, "protected destination");
		return 0;
	}
	}
	return fail(P, RH_CAT_E_POLICY, "internal");
}

/* Artifact URL must be a release download of the entry's own GitHub repo; `release` (optional) the matching tag page. */
static int release_ok(const ps *P, size_t src, size_t url, long release)
{
	static const char host[] = "https://github.com/", dl[] = "/releases/download/", tg[] = "/releases/tag/";
	const uint8_t *s = sptr(P, src), *u = sptr(P, url);
	size_t sl = slen(P, src), ul = slen(P, url), end = sl, hl = sizeof host - 1, i, tag, tagl;
	int slash = 0;

	if (sl <= hl || memcmp(s, host, hl))
		return 0;
	if (s[end - 1] == '/')
		end--;
	if (end - hl > 4 && !memcmp(s + end - 4, ".git", 4))
		end -= 4;
	for (i = hl; i < end; i++) {
		if (s[i] == ' ')
			return 0;
		if (s[i] == '/') {
			if (slash || i == hl || i + 1 == end)
				return 0;
			slash = 1;
		}
	}
	if (!slash || ul <= end + sizeof dl - 1 || !ci_eq(u, (const char *)s, end) || !ci_eq(u + end, dl, sizeof dl - 1))
		return 0;
	tag = end + sizeof dl - 1;
	for (tagl = 0; tag + tagl < ul && u[tag + tagl] != '/'; tagl++)
		if (u[tag + tagl] == ' ')
			return 0;
	if (!tagl || tag + tagl + 1 >= ul)
		return 0;
	for (i = tag + tagl + 1; i < ul; i++)
		if (u[i] == '/' || u[i] == ' ')
			return 0;
	if (release >= 0) {
		const uint8_t *r = sptr(P, (size_t)release);
		size_t rl = slen(P, (size_t)release);
		if (rl != end + sizeof tg - 1 + tagl || !ci_eq(r, (const char *)s, end) || !ci_eq(r + end, tg, sizeof tg - 1) ||
		    !ci_eq(r + end + sizeof tg - 1, (const char *)u + tag, tagl))
			return 0;
	}
	return 1;
}

/* ---- publish gates (mirror of trust.py check_index) ---- */

#define MAXDEV 16

typedef struct {
	size_t dest, dev, fw, app;
} art;

static int policy(ps *P, const char *device, const char *firmware, rh_cat_info *info)
{
	size_t devs[MAXDEV], ndev = 0, apprs[RH_CAT_MAX_ARTIFACTS], nappr = 0, i, j, k, n;
	unsigned char used[RH_CAT_MAX_ARTIFACTS];
	art arts[RH_CAT_MAX_ARTIFACTS];
	size_t nart = 0, target = (size_t)-1;
	long v, ap, rv, dv, fw;
	size_t want_dev = strlen(device), want_fw = strlen(firmware);

#define CK(x) do { if (x) return -1; } while (0)
	CK(check_obj(P, 0, "approvals apps devices expires format generated revoked serial", "approvals apps devices format generated revoked serial"));
	v = oget(P, 0, "format");
	if (P->t[v].t != T_INT || ival(P, v) != 1)
		return fail(P, RH_CAT_E_POLICY, "unsupported format");
	CK(chk(P, oget(P, 0, "serial"), K_PINT, NULL));
	info->serial = (uint32_t)ival(P, (size_t)oget(P, 0, "serial"));
	CK(chk(P, oget(P, 0, "generated"), K_DATE, NULL));
	if ((v = oget(P, 0, "expires")) >= 0) {
		CK(chk(P, v, K_DATE, NULL));
		memcpy(info->expires, sptr(P, (size_t)v), 10);
	}
	for (i = 0; i < 4; i++) {
		static const char *names[] = {"approvals", "apps", "devices", "revoked"};
		if (P->t[oget(P, 0, names[i])].t != T_ARR)
			return fail(P, RH_CAT_E_POLICY, "expected array");
	}

	/* devices */
	v = oget(P, 0, "devices");
	if (P->t[v].n > MAXDEV)
		return fail(P, RH_CAT_E_LIMIT, "too many devices");
	for (i = 0, n = v + 1; i < P->t[v].n; i++, n = P->t[n].next) {
		long f;
		size_t m;
		CK(check_obj(P, n, "schema id name adapter package_format display firmware notes", "schema id name adapter package_format firmware"));
		if (P->t[oget(P, n, "schema")].t != T_INT || ival(P, (size_t)oget(P, n, "schema")) != 1)
			return fail(P, RH_CAT_E_POLICY, "bad schema");
		CK(chk(P, oget(P, n, "id"), K_ID, NULL));
		CK(chk(P, oget(P, n, "name"), K_STR, NULL));
		CK(chk(P, oget(P, n, "adapter"), K_ENUM, "opk-funkeyos android-packageinstaller"));
		CK(chk(P, oget(P, n, "package_format"), K_ENUM, "opk apk"));
		if ((f = oget(P, n, "display")) >= 0) {
			CK(check_obj(P, (size_t)f, "w h", "w h"));
			CK(chk(P, oget(P, (size_t)f, "w"), K_UINT, NULL));
			CK(chk(P, oget(P, (size_t)f, "h"), K_UINT, NULL));
		}
		if ((f = oget(P, n, "notes")) >= 0 && P->t[f].t != T_STR)
			return fail(P, RH_CAT_E_POLICY, "bad notes");
		f = oget(P, n, "firmware");
		if (P->t[f].t != T_ARR || P->t[f].n < 1)
			return fail(P, RH_CAT_E_POLICY, "bad firmware list");
		for (m = f + 1, j = 0; j < P->t[f].n; j++, m = P->t[m].next)
			CK(chk(P, (long)m, K_ID, NULL));
		for (j = 0; j < ndev; j++)
			if (tok_eq(P, (size_t)oget(P, devs[j], "id"), (size_t)oget(P, n, "id")))
				return fail(P, RH_CAT_E_POLICY, "duplicate device id");
		devs[ndev++] = n;
		if (slen(P, (size_t)oget(P, n, "id")) == want_dev && !memcmp(sptr(P, (size_t)oget(P, n, "id")), device, want_dev))
			target = n;
	}
	if (target == (size_t)-1)
		return fail(P, RH_CAT_E_DEVICE, "catalog has no profile for this device");
	fw = oget(P, target, "firmware");
	for (n = fw + 1, i = 0; i < P->t[fw].n && !(slen(P, n) == want_fw && !memcmp(sptr(P, n), firmware, want_fw)); i++, n = P->t[n].next)
		;
	if (i == P->t[fw].n)
		return fail(P, RH_CAT_E_DEVICE, "firmware not supported by this catalog");

	/* approvals */
	ap = oget(P, 0, "approvals");
	if (P->t[ap].n > RH_CAT_MAX_ARTIFACTS)
		return fail(P, RH_CAT_E_LIMIT, "too many approvals");
	for (i = 0, n = ap + 1; i < P->t[ap].n; i++, n = P->t[n].next) {
		CK(check_obj(P, n, "app approved_by date device firmware release sha256 size", "app approved_by date device firmware release sha256 size"));
		CK(chk(P, oget(P, n, "app"), K_ID, NULL));
		CK(chk(P, oget(P, n, "approved_by"), K_STR, NULL));
		CK(chk(P, oget(P, n, "date"), K_DATE, NULL));
		CK(chk(P, oget(P, n, "device"), K_ID, NULL));
		CK(chk(P, oget(P, n, "firmware"), K_ID, NULL));
		CK(chk(P, oget(P, n, "release"), K_HTTPS, NULL));
		CK(chk(P, oget(P, n, "sha256"), K_SHA, NULL));
		CK(chk(P, oget(P, n, "size"), K_PINT, NULL));
		for (j = 0; j < nappr; j++)
			if (tok_eq(P, (size_t)oget(P, apprs[j], "app"), (size_t)oget(P, n, "app")) &&
			    tok_eq(P, (size_t)oget(P, apprs[j], "device"), (size_t)oget(P, n, "device")) &&
			    tok_eq(P, (size_t)oget(P, apprs[j], "firmware"), (size_t)oget(P, n, "firmware")) &&
			    tok_eq(P, (size_t)oget(P, apprs[j], "sha256"), (size_t)oget(P, n, "sha256")))
				return fail(P, RH_CAT_E_POLICY, "duplicate approval");
		apprs[nappr] = n;
		used[nappr++] = 0;
	}

	/* revoked */
	rv = oget(P, 0, "revoked");
	for (i = 0, n = rv + 1; i < P->t[rv].n; i++, n = P->t[n].next) {
		CK(check_obj(P, n, "app reason sha256", "app reason sha256"));
		CK(chk(P, oget(P, n, "app"), K_ID, NULL));
		CK(chk(P, oget(P, n, "reason"), K_STR, NULL));
		CK(chk(P, oget(P, n, "sha256"), K_SHA, NULL));
	}

	/* apps */
	v = oget(P, 0, "apps");
	info->n_apps = (uint32_t)P->t[v].n;
	for (i = 0, n = v + 1; i < P->t[v].n; i++, n = P->t[n].next) {
		long ar, id = -1;
		size_t a, src;
		CK(check_obj(P, n, "schema id name description developer website source license category artifacts",
			     "schema id name description developer source license category artifacts"));
		if (P->t[oget(P, n, "schema")].t != T_INT || ival(P, (size_t)oget(P, n, "schema")) != 1)
			return fail(P, RH_CAT_E_POLICY, "bad schema");
		id = oget(P, n, "id");
		CK(chk(P, id, K_ID, NULL));
		for (j = 0, k = v + 1; j < i; j++, k = P->t[k].next)
			if (tok_eq(P, (size_t)oget(P, k, "id"), (size_t)id))
				return fail(P, RH_CAT_E_POLICY, "duplicate app id");
		CK(chk(P, oget(P, n, "name"), K_STR, NULL));
		CK(chk(P, oget(P, n, "description"), K_STR, NULL));
		CK(chk(P, oget(P, n, "developer"), K_STR, NULL));
		if (oget(P, n, "website") >= 0)
			CK(chk(P, oget(P, n, "website"), K_HTTPS, NULL));
		src = (size_t)oget(P, n, "source");
		CK(chk(P, (long)src, K_HTTPS, NULL));
		CK(chk(P, oget(P, n, "license"), K_STR, NULL));
		if (span_eq(P, (size_t)oget(P, n, "license"), "unknown"))
			return fail(P, RH_CAT_E_POLICY, "unknown license");
		CK(chk(P, oget(P, n, "category"), K_ENUM, "application utility launcher theme port other"));
		ar = oget(P, n, "artifacts");
		if (P->t[ar].t != T_ARR || P->t[ar].n < 1)
			return fail(P, RH_CAT_E_POLICY, "published app has no artifacts");
		for (a = ar + 1, j = 0; j < P->t[ar].n; j++, a = P->t[a].next) {
			long dev = -1, inst, comp, ev, sha, url, level;
			size_t d, e, m;
			int matched = 0;

			CK(check_obj(P, a, "device firmware format status unavailable_reason version url sha256 size install compatibility",
				     "device firmware format status version url sha256 size install compatibility"));
			dv = oget(P, a, "device");
			CK(chk(P, dv, K_ID, NULL));
			CK(chk(P, oget(P, a, "firmware"), K_ID, NULL));
			CK(chk(P, oget(P, a, "format"), K_ENUM, "opk apk"));
			if (!span_eq(P, (size_t)oget(P, a, "status"), "available"))
				return fail(P, RH_CAT_E_POLICY, "only available artifacts may be published");
			if (oget(P, a, "unavailable_reason") >= 0 && P->t[oget(P, a, "unavailable_reason")].t != T_STR)
				return fail(P, RH_CAT_E_POLICY, "bad unavailable_reason");
			CK(chk(P, oget(P, a, "version"), K_ANY, NULL));
			url = oget(P, a, "url");
			sha = oget(P, a, "sha256");
			CK(chk(P, url, K_HTTPS, NULL));
			CK(chk(P, sha, K_SHA, NULL));
			CK(chk(P, oget(P, a, "size"), K_PINT, NULL));
			for (d = 0; d < ndev; d++)
				if (tok_eq(P, (size_t)oget(P, devs[d], "id"), (size_t)dv))
					dev = (long)devs[d];
			if (dev < 0)
				return fail(P, RH_CAT_E_POLICY, "artifact device not in catalog");
			fw = oget(P, (size_t)dev, "firmware");
			for (m = fw + 1, e = 0; e < P->t[fw].n && !tok_eq(P, m, (size_t)oget(P, a, "firmware")); e++, m = P->t[m].next)
				;
			if (e == P->t[fw].n)
				return fail(P, RH_CAT_E_POLICY, "artifact firmware not on device");
			if (!tok_eq(P, (size_t)oget(P, a, "format"), (size_t)oget(P, (size_t)dev, "package_format")))
				return fail(P, RH_CAT_E_POLICY, "artifact format differs from device");
			if (!release_ok(P, src, (size_t)url, -1))
				return fail(P, RH_CAT_E_POLICY, "url is not a release download of the source repo");
			inst = oget(P, a, "install");
			CK(check_obj(P, (size_t)inst, "dest_name", "dest_name"));
			CK(chk(P, oget(P, (size_t)inst, "dest_name"), K_DEST, NULL));
			comp = oget(P, a, "compatibility");
			CK(check_obj(P, (size_t)comp, "level evidence", "level"));
			level = oget(P, (size_t)comp, "level");
			CK(chk(P, level, K_ENUM, "verified community experimental unsupported untested"));
			if (!span_eq(P, (size_t)level, "verified"))
				return fail(P, RH_CAT_E_POLICY, "compatibility level is not publishable");
			ev = oget(P, (size_t)comp, "evidence");
			if (ev < 0 || P->t[ev].t != T_ARR)
				return fail(P, RH_CAT_E_POLICY, "verified needs evidence");
			for (m = ev + 1, e = 0; e < P->t[ev].n; e++, m = P->t[m].next) {
				CK(check_obj(P, m, "sha256 date tester note", "sha256 date tester"));
				CK(chk(P, oget(P, m, "sha256"), K_SHA, NULL));
				CK(chk(P, oget(P, m, "date"), K_DATE, NULL));
				CK(chk(P, oget(P, m, "tester"), K_ANY, NULL));
				if (oget(P, m, "note") >= 0 && P->t[oget(P, m, "note")].t != T_STR)
					return fail(P, RH_CAT_E_POLICY, "bad note");
				if (tok_eq(P, (size_t)oget(P, m, "sha256"), (size_t)sha))
					matched = 1;
			}
			if (!matched)
				return fail(P, RH_CAT_E_POLICY, "no evidence for this artifact's sha256");
			/* approval for this exact artifact */
			for (m = 0; m < nappr; m++) {
				size_t ak = apprs[m];
				if (tok_eq(P, (size_t)oget(P, ak, "app"), (size_t)id) && tok_eq(P, (size_t)oget(P, ak, "device"), (size_t)dv) &&
				    tok_eq(P, (size_t)oget(P, ak, "firmware"), (size_t)oget(P, a, "firmware")) &&
				    tok_eq(P, (size_t)oget(P, ak, "sha256"), (size_t)sha)) {
					if (ival(P, (size_t)oget(P, ak, "size")) != ival(P, (size_t)oget(P, a, "size")) ||
					    !release_ok(P, src, (size_t)url, oget(P, ak, "release")))
						return fail(P, RH_CAT_E_POLICY, "approval does not match size/release");
					used[m] = 1;
					break;
				}
			}
			if (m == nappr)
				return fail(P, RH_CAT_E_POLICY, "artifact has no human approval");
			for (m = rv + 1, e = 0; e < P->t[rv].n; e++, m = P->t[m].next)
				if (tok_eq(P, (size_t)oget(P, m, "app"), (size_t)id) && tok_eq(P, (size_t)oget(P, m, "sha256"), (size_t)sha))
					return fail(P, RH_CAT_E_POLICY, "artifact is revoked");
			if (nart >= RH_CAT_MAX_ARTIFACTS)
				return fail(P, RH_CAT_E_LIMIT, "too many artifacts");
			arts[nart].dest = (size_t)oget(P, (size_t)inst, "dest_name");
			arts[nart].dev = (size_t)dv;
			arts[nart].fw = (size_t)oget(P, a, "firmware");
			arts[nart].app = i;
			/* one file per device: only the same app may reuse a name, and only for a different firmware profile */
			for (m = 0; m < nart; m++)
				if (tok_eq(P, arts[m].dev, (size_t)dv) && slen(P, arts[m].dest) == slen(P, arts[nart].dest) &&
				    ci_eq(sptr(P, arts[m].dest), (const char *)sptr(P, arts[nart].dest), slen(P, arts[nart].dest)) &&
				    (arts[m].app != i || tok_eq(P, arts[m].fw, arts[nart].fw)))
					return fail(P, RH_CAT_E_POLICY, "duplicate destination");
			nart++;
			if (tok_eq(P, (size_t)dv, (size_t)oget(P, target, "id")))
				info->n_artifacts++;
		}
	}
	for (i = 0; i < nappr; i++)
		if (!used[i])
			return fail(P, RH_CAT_E_POLICY, "approval matches no published artifact");
	return 0;
#undef CK
}

/* ---- signature document ---- */

static int b64_64(const ps *P, size_t t, uint8_t out[64])
{
	static const char A[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
	const uint8_t *s = sptr(P, t);
	size_t i, o = 0;
	int idx[4];

	if (slen(P, t) != 88 || s[86] != '=' || s[87] != '=')
		return -1;
	for (i = 0; i < 88; i += 4) {
		int k, pad = i == 84 ? 2 : 0;
		for (k = 0; k < 4 - pad; k++) {
			const char *c = memchr(A, s[i + k], 64);
			if (!c || !s[i + k])
				return -1;
			idx[k] = (int)(c - A);
		}
		out[o++] = (uint8_t)(idx[0] << 2 | idx[1] >> 4);
		if (pad) {
			if (idx[1] & 15)
				return -1;  /* non-zero padding bits: not what base64.b64encode emits */
			continue;
		}
		out[o++] = (uint8_t)((idx[1] & 15) << 4 | idx[2] >> 2);
		out[o++] = (uint8_t)((idx[2] & 3) << 6 | idx[3]);
	}
	return o == 64 ? 0 : -1;
}

int rh_catalog_verify(const uint8_t *index, size_t index_len, const uint8_t *sig, size_t sig_len,
		      const uint8_t (*keys)[32], size_t nkeys, const char *device, const char *firmware,
		      const rh_cat_state *prev, rh_cat_state *next, rh_cat_info *info, const char **why)
{
	tok stoks[16], *toks;
	ps P;
	rh_cat_info local;
	rh_sha256 h;
	uint8_t raw[64], kid[32];
	char kidhex[17];
	const char *w = "";
	long v;
	size_t i, k, found = (size_t)-1;
	int rc = RH_CAT_E_ARG;

#define BAIL(c, m) do { rc = (c); w = (m); goto out; } while (0)
	if (!info)
		info = &local;
	memset(info, 0, sizeof *info);
	if (!index || !sig || !device || !firmware || !next || (nkeys && !keys))
		BAIL(RH_CAT_E_ARG, "bad arguments");
	if (!nkeys)
		BAIL(RH_CAT_E_NOKEY, "no trusted key configured");
	if (!index_len || !sig_len)
		BAIL(RH_CAT_E_SIZE, "missing index or signature");
	if (index_len > RH_CAT_MAX_INDEX || sig_len > RH_CAT_MAX_SIG)
		BAIL(RH_CAT_E_SIZE, "index or signature too large");

	/* signature document: {"alg":"ed25519","key_id":"<16 hex>","sig":"<88 b64>","v":1} */
	if (parse_doc(&P, sig, sig_len, stoks, 16))
		BAIL(RH_CAT_E_SIGDOC, "malformed signature document");
	if (P.t[0].n != 4 || check_obj(&P, 0, "alg key_id sig v", "alg key_id sig v"))
		BAIL(RH_CAT_E_SIGDOC, "unsupported signature document");
	v = oget(&P, 0, "v");
	if (P.t[v].t != T_INT || ival(&P, (size_t)v) != 1 || !span_eq(&P, (size_t)oget(&P, 0, "alg"), "ed25519"))
		BAIL(RH_CAT_E_SIGDOC, "unsupported signature document");
	if (P.t[oget(&P, 0, "key_id")].t != T_STR || slen(&P, (size_t)oget(&P, 0, "key_id")) != 16 ||
	    P.t[oget(&P, 0, "sig")].t != T_STR || b64_64(&P, (size_t)oget(&P, 0, "sig"), raw))
		BAIL(RH_CAT_E_SIGDOC, "malformed signature");
	for (i = 0; i < nkeys; i++) {
		rh_sha256_init(&h);
		rh_sha256_update(&h, keys[i], 32);
		rh_sha256_final(&h, kid);
		for (k = 0; k < 8; k++) {
			kidhex[2 * k] = "0123456789abcdef"[kid[k] >> 4];
			kidhex[2 * k + 1] = "0123456789abcdef"[kid[k] & 15];
		}
		kidhex[16] = 0;
		if (span_eq(&P, (size_t)oget(&P, 0, "key_id"), kidhex))
			found = i;
	}
	if (found == (size_t)-1)
		BAIL(RH_CAT_E_UNKNOWN_KEY, "unknown signing key");
	if (crypto_ed25519_check(raw, keys[found], index, index_len))
		BAIL(RH_CAT_E_BADSIG, "bad signature");

	/* only now look inside the index */
	toks = malloc(RH_CAT_MAX_TOKENS * sizeof *toks);
	if (!toks)
		BAIL(RH_CAT_E_NOMEM, "out of memory");
	if (parse_doc(&P, index, index_len, toks, RH_CAT_MAX_TOKENS) || policy(&P, device, firmware, info)) {
		rc = P.code;
		w = P.why;
		free(toks);
		goto out;
	}
	free(toks);
	rh_sha256_init(&h);
	rh_sha256_update(&h, index, index_len);
	rh_sha256_final(&h, next->sha256);
	next->serial = info->serial;
	if (prev) {
		if (next->serial < prev->serial)
			BAIL(RH_CAT_E_ROLLBACK, "rollback: serial lower than the newest accepted");
		if (next->serial == prev->serial && memcmp(next->sha256, prev->sha256, 32))
			BAIL(RH_CAT_E_FORK, "same serial, different content");
	}
	rc = RH_CAT_OK;
out:
	if (why)
		*why = w;
	return rc;
#undef BAIL
}
