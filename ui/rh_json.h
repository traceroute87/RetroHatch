/* Tiny JSON reader for the local catalog files. Trusted-size input only. */
#ifndef RH_JSON_H
#define RH_JSON_H
typedef struct rj {
	int t;                 /* 'n' null, 'b' bool, '#' number, 's' string, 'a' array, 'o' object */
	double num;
	char *s;               /* string value */
	char *key;             /* member name when child of an object */
	struct rj *kid, *next;
} rj;
rj *rj_parse(const char *txt);   /* NULL on any syntax error */
void rj_free(rj *j);
const rj *rj_get(const rj *o, const char *key);
const char *rj_str(const rj *o, const char *key, const char *dflt);
#endif
