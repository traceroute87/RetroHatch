/* UI data model: real local catalog + installed record + device facts.
 * No UI and no install logic in here; the UI only reads this struct. */
#ifndef RH_MODEL_H
#define RH_MODEL_H
#include <stdint.h>

#define RH_MAX_APPS 32

typedef struct {
	char id[40], name[48], desc[96], developer[48], license[32], source[128];
	char status[16];      /* artifact status: "available" | "unavailable" */
	char reason[300];     /* catalog's unavailable_reason, verbatim */
	char version[24], compat[16], device[24], firmware[32];
	char sha256[65], dest_name[72];   /* artifact sha256 and install.dest_name; "" when the catalog has none */
	char url[256];        /* artifact download URL (signed catalogs only; "" otherwise) */
	uint64_t size;        /* 0 = unknown */
	int available;        /* status == "available" */
	int verified;         /* available AND compatibility level "verified": the only kind the UI treats as installable/updatable */
} rh_app;

typedef struct { char id[24], name[48]; } rh_dev;

typedef struct {
	char device[48], os[48], kernel[40], arch[24], storage[48]; /* "Unknown" when not readable */
} rh_devinfo;

typedef struct {
	rh_app apps[RH_MAX_APPS]; int n_apps;
	rh_dev devs[8];           int n_devs;
	/* installed record rows; app = index into apps or -1 when not in the catalog */
	struct { char id[40], version[24]; int app; } inst[RH_MAX_APPS]; int n_inst;
	int upd[RH_MAX_APPS];     int n_upd;   /* indexes into inst[]: catalog has a different available version */
	rh_devinfo di;
	/* signed catalog (DEV): where the entries came from and whether the signature held. source == "" = local files */
	struct { char source[16]; unsigned serial; char generated[11], expires[11]; int ok; char status[96]; } cat;
} rh_model;

/* catalog_dir has apps/ and devices/ JSON files; state_dir holds installed.tsv (may not exist). */
void rh_model_load(rh_model *m, const char *catalog_dir, const char *state_dir);
/* Entries from an index that rh_catalog_verify_persist() accepted (never call this with unverified bytes). src = "bundled" or
 * "cached". serial/generated/expires come from the verifier. Only apps for device_id are shown. */
void rh_model_load_signed(rh_model *m, const char *index, size_t len, const char *src, unsigned serial, const char *expires,
			  const char *device_id, const char *state_dir);
/* nothing could be verified: empty catalog with the reason shown on the Catalog Status page */
void rh_model_load_none(rh_model *m, const char *why, const char *state_dir);
/* dotted-number compare (1.9 < 1.10): -1/0/1, or 2 when either side is not plain numbers (never treated as newer) */
int rh_ver_cmp(const char *a, const char *b);
const char *rh_model_dev_name(const rh_model *m, const char *id);
#endif
