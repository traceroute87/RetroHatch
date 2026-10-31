#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <dirent.h>
#include <unistd.h>
#include <sys/statvfs.h>
#include <sys/utsname.h>
#include "rh_json.h"
#include "rh_model.h"

#define CP(d, s) snprintf((d), sizeof(d), "%s", (s))

static char *slurp(const char *path)
{
	FILE *f = fopen(path, "rb");
	char *b; long n;
	if (!f) return NULL;
	fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
	if (n < 0 || n > 65536 || !(b = malloc(n + 1))) { fclose(f); return NULL; }
	if (fread(b, 1, n, f) != (size_t)n) { fclose(f); free(b); return NULL; }
	fclose(f); b[n] = 0;
	return b;
}

static rj *load_json(const char *dir, const char *sub, const char *name)
{
	char path[512], *txt; rj *j;
	snprintf(path, sizeof path, "%s/%s/%s", dir, sub, name);
	if (!(txt = slurp(path))) return NULL;
	j = rj_parse(txt); free(txt);
	return j;
}

static int ends_json(const char *n) { size_t l = strlen(n); return l > 5 && !strcmp(n + l - 5, ".json"); }

static int app_cmp(const void *a, const void *b)
{
	const rh_app *x = a, *y = b;
	int tx = !strcmp(x->id, "tarafi"), ty = !strcmp(y->id, "tarafi");
	if (tx != ty) return ty - tx;         /* TaraFi first */
	return strcmp(x->name, y->name);
}

static const char *const KW[RH_CAT_N][22] = {
	[RH_CAT_GAMES] = {"game", "games", "minigame", "minigames", "puzzle", "puzzles", "arcade", "platformer", "roguelike", "rpg", "shooter", "sokoban", "sudoku", NULL},
	[RH_CAT_EMU] = {"emulator", "emulators", "emulation", "libretro", "retroarch", NULL},
	[RH_CAT_MEDIA] = {"music", "audio", "video", "movie", "movies", "mp3", "podcast", "radio", "photo", "photos", "media", "ebook", NULL},
	[RH_CAT_UTIL] = {"utility", "utilities", "viewer", "editor", "manager", "calculator", "clock", "terminal", "launcher", "backup", "converter", NULL},
	[RH_CAT_ENGINE] = {"engine", "engines", "runtime", "library", "lib", "libs", "framework", "sdk", "toolkit", "toolchain", "tool", "tools", "compiler", "interpreter", "devkit", NULL},
};
static const char *const CAT_NAME[RH_CAT_N] = {"All", "Games", "Emulators", "Media", "Utilities", "Engines & Tools", "Other"};
const char *rh_cat_name(rh_cat c) { return (unsigned)c < RH_CAT_N ? CAT_NAME[c] : CAT_NAME[RH_CAT_OTHER]; }

static unsigned cat_bits(const char *s)   /* bit c set when a whole word of s is a keyword of category c */
{
	char tok[24]; size_t n = 0; int big = 0; unsigned bits = 0;
	if (!s) return 0;
	for (;; s++) {
		if (*s && isalnum((unsigned char)*s)) { if (n < sizeof tok - 1) tok[n++] = (char)tolower((unsigned char)*s); else big = 1; continue; }
		if (n && !big) {
			int c, i; tok[n] = 0;
			for (c = 1; c < RH_CAT_OTHER; c++) for (i = 0; KW[c][i]; i++) if (!strcmp(tok, KW[c][i])) bits |= 1u << c;
		}
		n = 0; big = 0;
		if (!*s) break;
	}
	return bits;
}

rh_cat rh_categorize(const char *name, const char *desc, const char *topics)
{
	unsigned b = cat_bits(name) | cat_bits(desc) | cat_bits(topics); int c;
	for (c = 1; c < RH_CAT_OTHER; c++) if (b == 1u << c) return (rh_cat)c;
	return RH_CAT_OTHER;
}

static void load_app(rh_model *m, const rj *j, const char *target)
{
	rh_app *a; const rj *arts, *art, *k; const char *s;
	if (m->n_apps >= RH_MAX_APPS || !rj_str(j, "id", NULL) || !rj_str(j, "name", NULL)) return;
	a = &m->apps[m->n_apps++];
	memset(a, 0, sizeof *a);
	CP(a->id, rj_str(j, "id", "")); CP(a->name, rj_str(j, "name", ""));
	CP(a->desc, rj_str(j, "description", "")); CP(a->developer, rj_str(j, "developer", ""));
	a->cat = rh_categorize(a->name, a->desc, NULL);
	CP(a->license, rj_str(j, "license", "")); CP(a->source, rj_str(j, "source", "")); CP(a->category, rj_str(j, "category", ""));
	CP(a->status, "unavailable");
	arts = rj_get(j, "artifacts");
	art = arts ? arts->kid : NULL;
	for (k = art; k; k = k->next) if (!strcmp(rj_str(k, "device", ""), target)) { art = k; break; }
	if (!art) return;
	CP(a->device, rj_str(art, "device", "")); CP(a->firmware, rj_str(art, "firmware", ""));
	CP(a->status, rj_str(art, "status", "unavailable"));
	CP(a->reason, rj_str(art, "unavailable_reason", ""));
	CP(a->version, rj_str(art, "version", ""));
	CP(a->sha256, rj_str(art, "sha256", ""));
	CP(a->dest_name, rj_str(rj_get(art, "install"), "dest_name", ""));
	CP(a->url, rj_str(art, "url", ""));
	if ((k = rj_get(art, "size")) && k->t == '#' && k->num > 0) a->size = (uint64_t)k->num;
	if ((k = rj_get(art, "compatibility")) && (s = rj_str(k, "level", NULL))) CP(a->compat, s);
	a->available = !strcmp(a->status, "available");
	a->verified = a->available && !strcmp(a->compat, "verified");
}

static int plain_ver(const char *s)   /* digits separated by single dots: "1", "1.10", "2.0.3" */
{
	int digit = 0;
	for (; *s; s++) {
		if (isdigit((unsigned char)*s)) digit = 1;
		else if (*s == '.' && digit) digit = 0;
		else return 0;
	}
	return digit;
}

int rh_ver_cmp(const char *a, const char *b)
{
	if (!plain_ver(a) || !plain_ver(b)) return 2;   /* checked up front: "1.1.0-rc1" must never look newer than 1.0.0 */
	for (;;) {
		char *ea, *eb; unsigned long x, y;
		if (!isdigit((unsigned char)*a) || !isdigit((unsigned char)*b)) return 2;
		x = strtoul(a, &ea, 10); y = strtoul(b, &eb, 10);
		if (x != y) return x < y ? -1 : 1;
		a = ea; b = eb;
		if (!*a && !*b) return 0;
		if (*a == '.') a++; else if (*a) return 2; else a = "0";   /* missing part counts as 0: 1.1 == 1.1.0 */
		if (*b == '.') b++; else if (*b) return 2; else b = "0";
	}
}

static void load_installed(rh_model *m, const char *state_dir)
{
	char path[512], line[512]; FILE *f; int i;
	snprintf(path, sizeof path, "%s/installed.tsv", state_dir);
	if (!(f = fopen(path, "r"))) return;
	while (m->n_inst < RH_MAX_APPS && fgets(line, sizeof line, f)) {
		char *id = strtok(line, "\t\r\n"), *ver = strtok(NULL, "\t\r\n");
		if (!id || !ver) continue;
		CP(m->inst[m->n_inst].id, id); CP(m->inst[m->n_inst].version, ver);
		m->inst[m->n_inst].app = -1;
		for (i = 0; i < m->n_apps; i++) if (!strcmp(m->apps[i].id, id)) m->inst[m->n_inst].app = i;
		m->n_inst++;
	}
	fclose(f);
	for (i = 0; i < m->n_inst; i++) {
		int a = m->inst[i].app;
		if (a >= 0 && m->apps[a].verified && rh_ver_cmp(m->inst[i].version, m->apps[a].version) < 0)
			m->upd[m->n_upd++] = i;
	}
}

static void trim(char *s)
{
	size_t n = strlen(s);
	while (n && (s[n - 1] == '\n' || s[n - 1] == '"' || s[n - 1] == ' ')) s[--n] = 0;
}

static void load_devinfo(rh_devinfo *d)
{
	struct utsname u; struct statvfs sv; FILE *f; char line[160];
	CP(d->device, "Unknown"); CP(d->os, "Unknown"); CP(d->kernel, "Unknown");
	CP(d->arch, "Unknown"); CP(d->storage, "Unknown");
	if ((f = fopen("/proc/device-tree/model", "r"))) {
		if (fgets(line, sizeof line, f) && line[0]) CP(d->device, line);
		fclose(f);
	}
	if (!uname(&u)) { CP(d->kernel, u.release); CP(d->arch, u.machine); }
	if ((f = fopen("/etc/os-release", "r"))) {
		char name[48] = "", ver[24] = "";
		while (fgets(line, sizeof line, f)) {
			if (!strncmp(line, "NAME=", 5)) { CP(name, line + 5); trim(name); }
			if (!strncmp(line, "VERSION_ID=", 11)) { CP(ver, line + 11); trim(ver); }
		}
		fclose(f);
		if (name[0]) {
			const char *n = name[0] == '"' ? name + 1 : name, *v = ver[0] == '"' ? ver + 1 : ver;
			snprintf(d->os, sizeof d->os, "%s%s%s", n, *v ? " " : "", v);
		}
	}
	{
		const char *p = !access("/mnt", F_OK) ? "/mnt" : "/";
		if (!statvfs(p, &sv) && sv.f_frsize)
			snprintf(d->storage, sizeof d->storage, "%.1f GB free (%s)",
			         (double)sv.f_bavail * sv.f_frsize / 1073741824.0, p);
	}
	trim(d->device);
}

void rh_model_load(rh_model *m, const char *dir, const char *state_dir)
{
	char path[512], target[24] = "rg-nano"; DIR *d; struct dirent *e; rj *j;
	memset(m, 0, sizeof *m);
	snprintf(path, sizeof path, "%s/DEV_FIXTURE", dir);
	m->dev_fixture = !access(path, F_OK);
	snprintf(path, sizeof path, "%s/devices", dir);
	if ((d = opendir(path))) {
		while ((e = readdir(d)) && m->n_devs < 8)
			if (ends_json(e->d_name) && (j = load_json(dir, "devices", e->d_name))) {
				CP(m->devs[m->n_devs].id, rj_str(j, "id", "")); CP(m->devs[m->n_devs].name, rj_str(j, "name", ""));
				if (m->devs[m->n_devs].id[0]) m->n_devs++;
				rj_free(j);
			}
		closedir(d);
	}
	if (m->n_devs) CP(target, m->devs[0].id);
	snprintf(path, sizeof path, "%s/apps", dir);
	if ((d = opendir(path))) {
		while ((e = readdir(d)))
			if (ends_json(e->d_name) && (j = load_json(dir, "apps", e->d_name))) { load_app(m, j, target); rj_free(j); }
		closedir(d);
	}
	qsort(m->apps, m->n_apps, sizeof m->apps[0], app_cmp);
	load_installed(m, state_dir);
	load_devinfo(&m->di);
}

static const char *const CAT_ID[RH_CAT_N] = {"", "games", "emulators", "media", "utilities", "engines", "other"};
static int cat_from_id(const char *s)   /* RH_CAT_* for a snapshot category id, 0 when unknown (never RH_CAT_ALL) */
{
	int c;
	for (c = 1; c < RH_CAT_N; c++) if (!strcmp(s, CAT_ID[c])) return c;
	return 0;
}

void rh_model_load_candidates(rh_model *m, const char *path)
{
	char *txt = slurp(path); rj *j; const rj *k, *c;
	m->n_cands = 0;
	if (!txt) return;
	j = rj_parse(txt); free(txt);
	if (!j) return;
	if ((k = rj_get(j, "candidates")))
		for (c = k->kid; c && m->n_cands < RH_MAX_CANDS; c = c->next) {
			rh_cand *x = &m->cands[m->n_cands]; const rj *p = rj_get(c, "package"), *cl = rj_get(c, "claim"), *n; int i, dup = 0;
			if (strcmp(rj_str(c, "approval", ""), "unapproved") || strcmp(rj_str(c, "hardware_test", ""), "none")) continue;   /* anything else is not ours to show */
			memset(x, 0, sizeof *x);
			CP(x->name, rj_str(c, "name", "")); CP(x->desc, rj_str(c, "description", ""));
			if (strlen(rj_str(c, "description", "")) >= sizeof x->desc) strcpy(x->desc + sizeof x->desc - 4, "...");   /* cut text says so */
			CP(x->version, rj_str(c, "version", ""));
			CP(x->repo, rj_str(c, "repo", "")); CP(x->source, rj_str(c, "source", "")); CP(x->license, rj_str(c, "license", ""));
			CP(x->last_activity, rj_str(c, "last_activity", ""));
			if (!x->name[0] || !x->repo[0]) continue;
			for (i = 0; i < m->n_cands; i++) dup |= !strcmp(m->cands[i].repo, x->repo);
			for (i = 0; i < m->n_apps; i++) dup |= x->source[0] && !strcmp(m->apps[i].source, x->source);   /* already a catalog entry */
			if (dup) continue;
			if (p) {
				CP(x->pkg_name, rj_str(p, "name", "")); x->zipped = !strcmp(rj_str(p, "container", ""), "zip");
				x->sig_ok = !strcmp(rj_str(p, "format", ""), "opk") && !strcmp(rj_str(p, "signature", ""), "squashfs");
				if ((n = rj_get(p, "size")) && n->t == '#' && n->num > 0) x->size = (uint64_t)n->num;
				if ((n = rj_get(p, "more_packages")) && n->t == '#' && n->num > 0) x->more = (int)n->num;
			}
			{
				char tb[256] = ""; const rj *t = rj_get(c, "topics"); size_t tl = 0;
				for (t = t ? t->kid : NULL; t && tl + 1 < sizeof tb; t = t->next) if (t->t == 's' && t->s) tl += snprintf(tb + tl, sizeof tb - tl, "%s ", t->s);
				x->cat = rh_categorize(x->name, rj_str(c, "description", ""), tb);   /* full description, not the possibly cut copy */
				if ((i = cat_from_id(rj_str(c, "category", ""))) && rj_str(c, "category_basis", "")[0]) {   /* reviewed category wins, only with its evidence */
					x->cat = (rh_cat)i; CP(x->cat_basis, rj_str(c, "category_basis", ""));
				}
			}
			if (cl) { CP(x->claim, rj_str(cl, "kind", "")); CP(x->claim_text, rj_str(cl, "text", "")); CP(x->claim_where, rj_str(cl, "where", "")); }
			m->n_cands++;
		}
	rj_free(j);
}

void rh_model_load_signed(rh_model *m, const char *index, size_t len, const char *src, unsigned serial, const char *expires,
			  const char *device_id, const char *state_dir)
{
	char *txt = malloc(len + 1); rj *j; const rj *k;
	memset(m, 0, sizeof *m);
	load_devinfo(&m->di);
	CP(m->cat.source, src); m->cat.serial = serial; CP(m->cat.expires, expires ? expires : "");
	if (!txt) { CP(m->cat.status, "Out of memory"); return; }
	memcpy(txt, index, len); txt[len] = 0;
	j = rj_parse(txt); free(txt);
	if (!j) { m->cat.source[0] = 0; CP(m->cat.status, "Catalog could not be read"); return; }
	CP(m->cat.generated, rj_str(j, "generated", ""));
	if ((k = rj_get(j, "devices")))
		for (k = k->kid; k && m->n_devs < 8; k = k->next) {
			CP(m->devs[m->n_devs].id, rj_str(k, "id", "")); CP(m->devs[m->n_devs].name, rj_str(k, "name", ""));
			if (m->devs[m->n_devs].id[0]) m->n_devs++;
		}
	if ((k = rj_get(j, "apps")))
		for (k = k->kid; k; k = k->next) load_app(m, k, device_id);
	rj_free(j);
	m->cat.ok = 1; CP(m->cat.status, "Signature verified");
	qsort(m->apps, m->n_apps, sizeof m->apps[0], app_cmp);
	load_installed(m, state_dir);
}

void rh_model_load_none(rh_model *m, const char *why, const char *state_dir)
{
	memset(m, 0, sizeof *m);
	load_devinfo(&m->di);
	CP(m->cat.status, why);
	load_installed(m, state_dir);
}

const char *rh_model_dev_name(const rh_model *m, const char *id)
{
	int i;
	for (i = 0; i < m->n_devs; i++) if (!strcmp(m->devs[i].id, id)) return m->devs[i].name;
	return id[0] ? id : "Unknown";
}
