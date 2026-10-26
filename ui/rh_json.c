#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include "rh_json.h"

typedef struct { const char *p; int depth; } P;

static void ws(P *p) { while (isspace((unsigned char)*p->p)) p->p++; }
static rj *mk(int t) { rj *j = calloc(1, sizeof *j); if (j) j->t = t; return j; }

void rj_free(rj *j)
{
	while (j) { rj *n = j->next; rj_free(j->kid); free(j->s); free(j->key); free(j); j = n; }
}

static char *pstr(P *p)
{
	size_t cap = 16, n = 0;
	char *o = malloc(cap);
	if (!o || *p->p != '"') { free(o); return NULL; }
	for (p->p++; *p->p && *p->p != '"'; p->p++) {
		unsigned c = (unsigned char)*p->p;
		if (n + 5 >= cap) { char *t = realloc(o, cap *= 2); if (!t) { free(o); return NULL; } o = t; }
		if (c == '\\') {
			c = (unsigned char)*++p->p;
			switch (c) {
			case 'n': c = '\n'; break;
			case 't': c = '\t'; break;
			case 'u': {
				char h[5] = {0};
				memcpy(h, p->p + 1, 4);
				c = (unsigned)strtoul(h, NULL, 16); p->p += 4;
				if (c >= 0x800) { o[n++] = (char)(0xE0 | c >> 12); o[n++] = (char)(0x80 | (c >> 6 & 63)); c = 0x80 | (c & 63); }
				else if (c >= 0x80) { o[n++] = (char)(0xC0 | c >> 6); c = 0x80 | (c & 63); }
				break; }
			case 0: free(o); return NULL;
			}
		}
		o[n++] = (char)c;
	}
	if (*p->p != '"') { free(o); return NULL; }
	p->p++; o[n] = 0;
	return o;
}

static rj *pval(P *p)
{
	rj *j, **tail;
	ws(p);
	if (p->depth > 16) return NULL;
	if (*p->p == '"') {
		j = mk('s');
		if (j && !(j->s = pstr(p))) { rj_free(j); return NULL; }
		return j;
	}
	if (*p->p == '{' || *p->p == '[') {
		char close = *p->p == '{' ? '}' : ']';
		j = mk(close == '}' ? 'o' : 'a'); tail = &j->kid; p->p++; p->depth++;
		for (ws(p); *p->p != close; ws(p)) {
			rj *k; char *key = NULL;
			if (close == '}') {
				key = pstr(p); ws(p);
				if (!key || *p->p++ != ':') { free(key); rj_free(j); return NULL; }
			}
			k = pval(p);
			if (!k) { free(key); rj_free(j); return NULL; }
			k->key = key; *tail = k; tail = &k->next;
			ws(p);
			if (*p->p == ',') p->p++;
			else if (*p->p != close) { rj_free(j); return NULL; }
		}
		p->p++; p->depth--;
		return j;
	}
	if (!strncmp(p->p, "true", 4) || !strncmp(p->p, "false", 5)) {
		j = mk('b'); j->num = *p->p == 't'; p->p += j->num ? 4 : 5; return j;
	}
	if (!strncmp(p->p, "null", 4)) { p->p += 4; return mk('n'); }
	{
		char *e; double d = strtod(p->p, &e);
		if (e == p->p) return NULL;
		j = mk('#'); j->num = d; p->p = e; return j;
	}
}

rj *rj_parse(const char *txt)
{
	P p = {txt, 0};
	rj *j = pval(&p);
	if (j) { ws(&p); if (*p.p) { rj_free(j); j = NULL; } }
	return j;
}

const rj *rj_get(const rj *o, const char *key)
{
	const rj *k;
	if (o && o->t == 'o') for (k = o->kid; k; k = k->next) if (k->key && !strcmp(k->key, key)) return k;
	return NULL;
}

const char *rj_str(const rj *o, const char *key, const char *dflt)
{
	const rj *k = rj_get(o, key);
	return k && k->t == 's' ? k->s : dflt;
}
