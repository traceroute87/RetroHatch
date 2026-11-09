/* EXPERIMENTAL test install of an UNAPPROVED candidate. Included by rh_ops.c ONLY when built with -DRH_EXPERIMENTAL (the DEV OPK and the
 * experimental tests); the production program never contains this code. It also runs only when the ops were initialised !production.
 *
 * Download = HTTPS from the candidate's own upstream link into <cache>/x-<id>.opk (a ZIP is a temporary <cache>/x-<id>.zip from which
 * rh_zip_extract() takes the one named member). Install = the same engine as every other install, app id "x-<id>": it is recorded in
 * installed.tsv, backed up, uninstallable, and refuses to touch a file RetroHatch did not install. A download never installs anything.
 * A candidate without a trusted hash is downloaded on the user's explicit confirmation; the SHA-256 computed afterwards proves integrity
 * of what was fetched, never who published it. Nothing here approves, signs or publishes anything. */
#define X_CAP_OPK (64ull << 20)
#define X_CAP_ZIP (100ull << 20)
#define X_FREE    (200ull << 20)

static const struct { const char *id, *why; } XBLOCK[] = {   /* firmware / system changes and launcher stubs: refused even if a link appears later */
	{"gmenu2x", "Replaces firmware menu"}, {"switchtoadb", "Changes the USB mode"}, {"switchtousb", "Changes the USB mode"},
	{"usblink", "Changes the USB mode"}, {"handheldlink", "Loads kernel modules"},
	{"counterstrike", "Launcher stub only"}, {"halflife", "Launcher stub only"} };

static void x_app_id(const rh_cand *c, char *o, size_t n) { snprintf(o, n, "x-%s", c->id); }
static void x_path(const rh_cand *c, const char *ext, char *o, size_t n) { snprintf(o, n, "%s/x-%s.%s", cache, c->id, ext); }
static void x_clean(char *o, int dots)   /* every character the engine would refuse becomes '_' */
{
	size_t i;
	for (i = 0; o[i]; i++)
		if (!((o[i] >= 'a' && o[i] <= 'z') || (o[i] >= 'A' && o[i] <= 'Z') || (o[i] >= '0' && o[i] <= '9') || o[i] == '-' || o[i] == '_' || o[i] == '+' || (dots && o[i] == '.'))) o[i] = '_';
}
static void x_dest(const rh_cand *c, char *o, size_t n) { snprintf(o, n, "%s", c->pkg_name); x_clean(o, 1); }
static void x_version(const rh_cand *c, char *o, size_t n) { snprintf(o, n, "%s", c->version[0] ? c->version : "0"); x_clean(o, 1); if (o[0] == '.' || o[0] == '_' || o[0] == '+' || o[0] == '-') o[0] = '0'; }

/* 0 = may be offered; else why[] says why not */
static int x_blocked(const rh_cand *c, char *why, size_t n)
{
	size_t i; char id[48], dest[72], ver[40], tgt[160], w2[48];
	for (i = 0; i < sizeof XBLOCK / sizeof *XBLOCK; i++) if (!strcmp(c->id, XBLOCK[i].id)) { snprintf(why, n, "%s", XBLOCK[i].why); return 1; }
	if (c->url_long) { snprintf(why, n, "Package link too long"); return 1; }
	if (!c->url[0]) { snprintf(why, n, "Source only"); return 1; }
	if (strncmp(c->url, "https://", 8)) { snprintf(why, n, "Link is not HTTPS"); return 1; }
	if (strcmp(c->fmt, "opk")) { snprintf(why, n, "Not an OPK package"); return 1; }
	if (!c->pkg_name[0]) { snprintf(why, n, "File name unknown"); return 1; }
	if (c->size > (c->zipped ? X_CAP_ZIP : X_CAP_OPK)) { snprintf(why, n, "Package too large"); return 1; }
	x_app_id(c, id, sizeof id); x_dest(c, dest, sizeof dest); x_version(c, ver, sizeof ver);
	if (!rh_plan_target(id, ver, dest, tgt, sizeof tgt, w2, sizeof w2)) { snprintf(why, n, "File name not allowed"); return 1; }
	return 0;
}

static int x_recorded(const rh_cand *c)   /* RetroHatch's own record (installed.tsv) already holds this test install */
{
	char p[320], pre[64], l[400]; FILE *f; int hit = 0;
	snprintf(p, sizeof p, "%s/installed.tsv", eng.state_dir); snprintf(pre, sizeof pre, "x-%s	", c->id);
	if (!(f = fopen(p, "r"))) return 0;
	while (!hit && fgets(l, sizeof l, f)) hit = !strncmp(l, pre, strlen(pre));
	fclose(f);
	return hit;
}

static int x_state(const rh_cand *c, int installed, char *why, size_t n)
{
	char p[320]; struct stat st;
	why[0] = 0;
	if (prod) { snprintf(why, n, "Not available"); return RH_X_NO; }
	if (installed || x_recorded(c)) return RH_X_UNINSTALL;
	if (x_blocked(c, why, n)) return RH_X_NO;
	x_path(c, "opk", p, sizeof p);
	if (!lstat(p, &st) && S_ISREG(st.st_mode)) return RH_X_INSTALL;
	if (!net_on) { snprintf(why, n, "Downloads are off"); return RH_X_NO; }
	return RH_X_DOWNLOAD;
}

static int x_squashfs(const char *path)   /* an OPK is a squashfs image: little-endian magic "hsqs" */
{
	unsigned char b[4]; FILE *f = fopen(path, "rb"); size_t r;
	if (!f) return 0;
	r = fread(b, 1, 4, f); fclose(f);
	return r == 4 && !memcmp(b, "hsqs", 4);
}

static void x_facts(const rh_cand *c, int op, char *file, size_t fn, char *hash, size_t hn)
{
	char p[320], h[65];
	x_dest(c, file, fn);
	if (op == RH_X_INSTALL) {
		x_path(c, "opk", p, sizeof p);
		if (rh_sha256_file(p, h, NULL)) snprintf(hash, hn, "unreadable"); else snprintf(hash, hn, "%.16s...", h);
	} else snprintf(hash, hn, "%s", c->sha256[0] ? "From inventory" : "None. UNVERIFIED");
}

static int x_download(const rh_cand *c, char *msg, size_t n)
{
	char url[400], mapped[512], opk[320], zip[320], em[120], why[60], *b; struct statvfs sv; int rc; unsigned old_total = net.total_ms;
	if (x_state(c, 0, why, sizeof why) != RH_X_DOWNLOAD) { snprintf(msg, n, "%s", why[0] ? why : "Not available"); return 1; }
	if (!statvfs(cache, &sv) && (unsigned long long)sv.f_bavail * sv.f_frsize < X_FREE) { snprintf(msg, n, "Not enough free space"); return 1; }
	snprintf(url, sizeof url, "%s", c->url);
	if (!strncmp(url, "https://gitlab.com/", 19) && (b = strstr(url, "/-/blob/"))) { memmove(b + 6, b + 7, strlen(b + 7) + 1); memcpy(b, "/-/raw", 6); }   /* a GitLab file page -> the raw file of the same project */
	map_url(url, mapped, sizeof mapped);
	x_path(c, "opk", opk, sizeof opk); x_path(c, "zip", zip, sizeof zip);
	net.total_ms = 600000;   /* the biggest packages are about 60 MB */
	if (c->zipped) {
		rc = rh_net_get_file(&net, mapped, zip, X_CAP_ZIP, 0, c->sha256[0] ? c->sha256 : NULL, em, sizeof em);
		if (rc == RH_NET_OK) {
			rc = rh_zip_extract(zip, c->pkg_name, opk, X_CAP_OPK, em, sizeof em) ? RH_NET_E_PROTO : RH_NET_OK;
			unlink(zip);
		}
	} else rc = rh_net_get_file(&net, mapped, opk, X_CAP_OPK, 0, c->sha256[0] ? c->sha256 : NULL, em, sizeof em);
	net.total_ms = old_total;
	if (rc == RH_NET_OK && !x_squashfs(opk)) { unlink(opk); rc = RH_NET_E_PROTO; snprintf(em, sizeof em, "Not an OPK (bad file header)"); }
	if (rc == RH_NET_OK) { snprintf(last_net, sizeof last_net, "Test download %.40s", c->name); return 0; }
	snprintf(msg, n, "%s", rc == RH_NET_E_OFFLINE ? "No internet connection" : em);
	snprintf(last_net, sizeof last_net, "%s", msg);
	return 1;
}

static int x_install(const rh_cand *c, char *msg, size_t n)
{
	char why[60], src[320], id[48], dest[72], ver[40], h[65]; struct stat st; rh_pkg p; rh_err e; uint64_t sz = 0;
	if (x_state(c, 0, why, sizeof why) != RH_X_INSTALL) { snprintf(msg, n, "%s", why[0] ? why : "Download it first"); return 1; }
	x_path(c, "opk", src, sizeof src);
	if (lstat(src, &st) || !S_ISREG(st.st_mode) || !st.st_size) { snprintf(msg, n, "Downloaded file missing"); return 1; }
	if (!x_squashfs(src)) { snprintf(msg, n, "Not an OPK (bad file header)"); return 1; }
	if (rh_sha256_file(src, h, &sz) || sz != (uint64_t)st.st_size) { snprintf(msg, n, "Cannot read the downloaded file"); return 1; }
	if (!c->zipped && c->sha256[0] && strcmp(h, c->sha256)) { snprintf(msg, n, "SHA-256 differs from inventory"); return 1; }
	x_app_id(c, id, sizeof id); x_dest(c, dest, sizeof dest); x_version(c, ver, sizeof ver);
	p.app_id = id; p.version = ver; p.dest_name = dest; p.src_path = src; p.size = sz; p.sha256 = h;
	e = rh_install(&eng, &p);                        /* the engine does every real check and the file work */
	if (e == RH_OK) return 0;
	if (e == RH_E_UNMANAGED) snprintf(msg, n, "A file with that name already exists");
	else if (e == RH_E_HASH) snprintf(msg, n, "SHA-256 mismatch");
	else { const char *s = rh_strerr(e); snprintf(msg, n, "%c%s", s[0] >= 'a' && s[0] <= 'z' ? s[0] - 32 : s[0], s + 1); }
	return e == RH_E_RECOVER ? 2 : 1;
}

static int x_uninstall(const rh_cand *c, char *msg, size_t n)
{
	char id[48], dest[72]; rh_err e;
	x_app_id(c, id, sizeof id); x_dest(c, dest, sizeof dest);
	e = rh_uninstall(&eng, id, dest);
	if (e == RH_OK) return 0;
	if (e == RH_E_UNMANAGED) snprintf(msg, n, "Not installed by RetroHatch, or changed");
	else { const char *s = rh_strerr(e); snprintf(msg, n, "%c%s", s[0] >= 'a' && s[0] <= 'z' ? s[0] - 32 : s[0], s + 1); }
	return e == RH_E_RECOVER ? 2 : 1;
}

static int x_do(const rh_cand *c, int op, char *msg, size_t n)
{
	if (prod) { snprintf(msg, n, "Not available"); return 1; }
	return op == RH_X_DOWNLOAD ? x_download(c, msg, n) : op == RH_X_INSTALL ? x_install(c, msg, n) : op == RH_X_UNINSTALL ? x_uninstall(c, msg, n) : 1;
}
