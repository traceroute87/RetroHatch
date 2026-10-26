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

static void load_app(rh_model *m, const rj *j, const char *target)
{
	rh_app *a; const rj *arts, *art, *k; const char *s;
	if (m->n_apps >= RH_MAX_APPS || !rj_str(j, "id", NULL) || !rj_str(j, "name", NULL)) return;
	a = &m->apps[m->n_apps++];
	memset(a, 0, sizeof *a);
	CP(a->id, rj_str(j, "id", "")); CP(a->name, rj_str(j, "name", ""));
	CP(a->desc, rj_str(j, "description", "")); CP(a->developer, rj_str(j, "developer", ""));
	CP(a->license, rj_str(j, "license", "")); CP(a->source, rj_str(j, "source", ""));
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
