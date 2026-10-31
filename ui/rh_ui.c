#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rh_gfx.h"
#include "rh_ui.h"

/* ---- Sunset Ember palette (exact) ---- */
#define RGB(h) {(Uint8)((h) >> 16), (Uint8)((h) >> 8), (Uint8)(h)}
static const rh_rgb C_BG = RGB(0x171B19), C_CARD = RGB(0x272721), C_ROW = RGB(0x35352B),
	C_TXT = RGB(0xFFF0D2), C_TXT2 = RGB(0xB9B3A3), C_ACC = RGB(0xE9A23B), C_ONACC = RGB(0x35251D),
	C_GREEN = RGB(0x82A779), C_LINE = RGB(0x494638), C_DIS = RGB(0x77786E), C_ERR = RGB(0xE87555);

/* ---- layout (px) ---- */
enum { W = 240, HDR_H = 32, CONT_Y = 36, CONT_B = 213, HINT_Y = 217,
       LIST_RH = 42, LIST_P = 44,      /* app list row height / pitch */
       SET_RH = 38, SET_P = 41,        /* settings row */
       HOME_Y = 123, HOME_RH = 21, HOME_P = 22, CTA_H = 24, STEP = 16 };

enum { IC_CHEV, IC_SEARCH, IC_GRID, IC_REFRESH, IC_GEAR, IC_LOCK, IC_DOWNLOAD, IC_DATABASE, IC_WIFI,
       IC_INFO, IC_PHONE, IC_PACKAGE, IC_GRID_L, IC_REFRESH_L, IC_CHECK, IC_CHECK_L, IC_ALERT_L, IC_TRASH, IC_N };
static const char *IC_FILE[IC_N] = {
	"ic_chevron_16", "ic_search_20", "ic_grid_20", "ic_refresh_20", "ic_gear_20", "ic_lock_24", "ic_download_20",
	"ic_database_20", "ic_wifi_20", "ic_info_20", "ic_phone_20", "ic_package_28", "ic_grid_48", "ic_refresh_48", "ic_check_20", "ic_check_48", "ic_alert_48", "ic_trash_20" };

static SDL_Surface *ic[IC_N], *img_header, *img_home, *img_logo, *img_mark;
static rh_font *f_body, *f_title;
static const rh_model *M;
static const rh_ui_ops *OPS;
static rh_plan_fn PLAN;
static int preview;   /* the open RH_S_CONFIRM screen is a read-only Install/Update Preview */
static char blocked_why[40], res_msg[96];
static int res_rc, pending, cur_op;   /* cur_op: 0 install, 1 update, 2 uninstall, 3 download, 4 refresh catalog */
static uint64_t prog_done, prog_total;
void rh_ui_progress(uint64_t done, uint64_t total) { prog_done = done; prog_total = total; }
static const char *host_of(const char *url, char *o, size_t n)   /* "https://host/path" -> "host" */
{
	size_t k = 0;
	if (!strncmp(url, "https://", 8)) url += 8;
	while (url[k] && url[k] != '/' && k + 1 < n) { o[k] = url[k]; k++; }
	o[k] = 0;
	return o;
}

typedef struct { rh_screen s; rh_info info; int app, sel, scroll; } frame;
static frame st[8];
static int depth;
#define CUR (st[depth])

/* ---- init ---- */
int rh_ui_init(const char *dir, const rh_model *m)
{
	char p[512]; int i;
	M = m; depth = 0; memset(st, 0, sizeof st);
	snprintf(p, sizeof p, "%s/tarafi16.fnt", dir); f_body = gfx_font_load(p);
	snprintf(p, sizeof p, "%s/15-KodeMono-SemiBold.fnt", dir); f_title = gfx_font_load(p);
	if (!f_title) f_title = f_body;
	for (i = 0; i < IC_N; i++) { snprintf(p, sizeof p, "%s/%s.png", dir, IC_FILE[i]); ic[i] = gfx_img_load(p); if (!ic[i]) return -1; }
	snprintf(p, sizeof p, "%s/header.png", dir); img_header = gfx_img_load(p);
	snprintf(p, sizeof p, "%s/home_bg.png", dir); img_home = gfx_img_load(p);
	snprintf(p, sizeof p, "%s/logo.png", dir); img_logo = gfx_img_load(p);
	snprintf(p, sizeof p, "%s/mark.png", dir); img_mark = gfx_img_load(p);
	return f_body && img_header && img_home && img_logo && img_mark ? 0 : -1;
}

void rh_ui_free(void)
{
	int i;
	for (i = 0; i < IC_N; i++) { SDL_FreeSurface(ic[i]); ic[i] = NULL; }
	SDL_FreeSurface(img_header); SDL_FreeSurface(img_home); SDL_FreeSurface(img_logo); SDL_FreeSurface(img_mark);
	img_header = img_home = img_logo = img_mark = NULL;
	if (f_title != f_body) gfx_font_free(f_title);
	gfx_font_free(f_body); f_body = f_title = NULL;
}

/* ---- small helpers ---- */
static void icon(SDL_Surface *d, int id, int cx, int cy, rh_rgb c)   /* centred */
{
	gfx_mask(d, ic[id], cx - ic[id]->w / 2, cy - ic[id]->h / 2, c);
}

static void paragraph(SDL_Surface *d, int x, int *y, int w, const char *s, rh_rgb c, int centre)
{
	const char *st_[12]; int ln[12], n = gfx_wrap(f_body, s, w, st_, ln, 12), i;
	for (i = 0; i < n; i++) {
		char b[160];
		snprintf(b, sizeof b, "%.*s", ln[i], st_[i]);
		if (centre) gfx_text_c(d, f_body, b, x + w / 2, *y, c); else gfx_text(d, f_body, b, x, *y, c);
		*y += 18;
	}
}

static const char *or_unknown(const char *s) { return s && s[0] && strcmp(s, "unknown") ? s : "Unknown"; }

/* ---- rows ---- */
static void row_bg(SDL_Surface *d, int x, int y, int w, int h, int sel)
{
	if (sel) gfx_rfill(d, x, y, w, h, 4, C_ACC); else gfx_rbox(d, x, y, w, h, 4, C_LINE, C_ROW);
}

static void app_tile(SDL_Surface *d, int x, int y, int s, int sel)
{
	gfx_rbox(d, x, y, s, s, 4, sel ? C_ONACC : C_LINE, C_CARD);
	icon(d, IC_PACKAGE, x + s / 2, y + s / 2, C_GREEN);
}

static void list_row(SDL_Surface *d, int y, int sel, const char *name, const char *sub)
{
	char b[80]; int hn = gfx_font_h(f_title), ty = y + (LIST_RH - (hn + 16)) / 2 + 1;
	row_bg(d, 8, y, 224, LIST_RH, sel);
	app_tile(d, 14, y + 5, 32, sel);
	gfx_text(d, f_title, gfx_ellipsize(f_title, name, 150, b, sizeof b), 54, ty, sel ? C_ONACC : C_TXT);
	gfx_text(d, f_body, gfx_ellipsize(f_body, sub, 150, b, sizeof b), 54, ty + hn, sel ? C_ONACC : C_TXT2);
	icon(d, IC_CHEV, 220, y + LIST_RH / 2, sel ? C_ONACC : C_TXT2);
}

static void menu_row(SDL_Surface *d, int x, int y, int w, int h, int sel, int ico, const char *label)
{
	row_bg(d, x, y, w, h, sel);
	icon(d, ico, x + 20, y + h / 2, sel ? C_ONACC : C_GREEN);
	gfx_text(d, f_title, label, x + 40, y + (h - gfx_font_h(f_title)) / 2, sel ? C_ONACC : C_TXT);
	icon(d, IC_CHEV, x + w - 14, y + h / 2, sel ? C_ONACC : C_TXT2);
}

/* ---- key/value card (details, device info, ...) ---- */
typedef struct { char l[24], v[96]; } kv;

static int kv_card(SDL_Surface *d, int y, const kv *r, int n, rh_rgb vc)
{
	int i, labw = 0, h = 0, x = 8, w = 224;
	for (i = 0; i < n; i++) if (gfx_text_w(f_body, r[i].l) > labw) labw = gfx_text_w(f_body, r[i].l);
	labw += 14;
	for (i = 0; i < n; i++) {
		const char *s_[6]; int ln[6];
		h += 8 + 16 * gfx_wrap(f_body, r[i].v, w - 16 - labw, s_, ln, 6);
	}
	gfx_rbox(d, x, y, w, h + 2, 4, C_LINE, C_CARD);
	for (i = 0, h = 1; i < n; i++) {
		const char *s_[6]; int ln[6], k, c = gfx_wrap(f_body, r[i].v, w - 16 - labw, s_, ln, 6);
		if (i) gfx_fill(d, x + 8, y + h, w - 16, 1, C_LINE);
		gfx_text(d, f_body, r[i].l, x + 8, y + h + 4, C_TXT2);
		for (k = 0; k < c; k++) {
			char b[96]; snprintf(b, sizeof b, "%.*s", ln[k], s_[k]);
			gfx_text(d, f_body, b, x + 8 + labw, y + h + 4 + 16 * k, vc);
		}
		h += 8 + 16 * c;
	}
	return h + 2;
}

/* ---- details ---- */
static void fmt_size(char *o, size_t n, unsigned long long b)
{
	if (!b) snprintf(o, n, "Unknown");
	else if (b >= 1048576) snprintf(o, n, "%.1f MB", b / 1048576.0);
	else snprintf(o, n, "%.1f KB", b / 1024.0);
}

/* draws (d != NULL) or measures (d == NULL); y is the content top with scroll applied. Returns total height. */
static int details(SDL_Surface *d, int y0, const rh_app *a)
{
	int y = y0 + 4, h; kv r[8]; int n = 0; char b[96];
	gfx_rbox(d, 8, y, 40, 40, 5, C_LINE, C_CARD);
	icon(d, IC_PACKAGE, 28, y + 20, C_GREEN);
	gfx_text(d, f_title, gfx_ellipsize(f_title, a->name, 170, b, sizeof b), 56, y + 2, C_TXT);
	if (a->developer[0]) {
		char e[96];
		snprintf(b, sizeof b, "by %s", a->developer);
		gfx_text(d, f_body, gfx_ellipsize(f_body, b, 170, e, sizeof e), 56, y + 22, C_TXT2);
	}
	y += 48;
	if (M->dev_fixture) paragraph(d, 10, &y, 220, "DEV FIXTURE. Not an approved app.", C_ERR, 0);
	if (a->desc[0]) { paragraph(d, 10, &y, 220, a->desc, C_TXT, 0); y += 4; }
	if (!a->verified) {
		char why[96];   /* short status here; the catalog's full reason follows the facts card */
		const char *s_[4]; int ln[4], c;
		snprintf(why, sizeof why, "A verified build for %s is not available yet.", rh_model_dev_name(M, a->device));
		c = gfx_wrap(f_body, why, 208, s_, ln, 4);
		h = 34 + c * 18 + 4;
		gfx_rbox(d, 8, y, 224, h, 4, C_LINE, C_CARD);
		icon(d, IC_LOCK, 26, y + 18, C_ERR);
		gfx_text(d, f_title, "Not available", 46, y + 8, C_ERR);
		{ int yy = y + 32; paragraph(d, 16, &yy, 208, why, C_TXT2, 0); }
		y += h + 6;
	}
	snprintf(r[n].l, sizeof r[n].l, "Version"); snprintf(r[n++].v, sizeof r[0].v, "%s", a->version[0] ? a->version : "Not published");
	snprintf(r[n].l, sizeof r[n].l, "Category"); snprintf(r[n++].v, sizeof r[0].v, "%c%s", a->category[0] >= 'a' && a->category[0] <= 'z' ? a->category[0] - 32 : a->category[0] ? a->category[0] : 'U', a->category[0] ? a->category + 1 : "nknown");
	snprintf(r[n].l, sizeof r[n].l, "Device"); snprintf(r[n++].v, sizeof r[0].v, "%s", rh_model_dev_name(M, a->device));
	snprintf(r[n].l, sizeof r[n].l, "Firmware"); snprintf(r[n++].v, sizeof r[0].v, "%s", or_unknown(a->firmware));
	snprintf(r[n].l, sizeof r[n].l, "Compat"); snprintf(r[n++].v, sizeof r[0].v, "%c%s", a->compat[0] ? a->compat[0] & ~32 : 'U', a->compat[0] ? a->compat + 1 : "nknown");
	snprintf(r[n].l, sizeof r[n].l, "License"); snprintf(r[n++].v, sizeof r[0].v, "%s", or_unknown(a->license));
	snprintf(r[n].l, sizeof r[n].l, "Size"); fmt_size(r[n++].v, sizeof r[0].v, a->size);
	snprintf(r[n].l, sizeof r[n].l, "Source"); snprintf(r[n++].v, sizeof r[0].v, "%s", strncmp(a->source, "https://", 8) ? or_unknown(a->source) : a->source + 8);
	y += kv_card(d, y, r, n, C_TXT) + 8;
	if (!a->verified && a->reason[0]) {
		char note[sizeof a->reason + 8];
		snprintf(note, sizeof note, "Catalog note: %s", a->reason);
		paragraph(d, 10, &y, 220, note, C_TXT2, 0);
	}
	return y + 2 - y0;
}

/* ---- info pages ---- */
static const char *INFO_TITLE[] = {"Device Information", "Catalog Status", "Network Status", "About RetroHatch"};

static int info_page(SDL_Surface *d, int y0, rh_info which)
{
	kv r[8]; int n = 0, y = y0 + 4, i, avail = 0; const char *note = NULL;
#define ROW(L, ...) do { snprintf(r[n].l, sizeof r[n].l, "%s", L); snprintf(r[n++].v, sizeof r[0].v, __VA_ARGS__); } while (0)
	for (i = 0; i < M->n_apps; i++) avail += M->apps[i].available;
	switch (which) {
	case RH_I_DEVICE:
		ROW("Device", "%s", M->di.device); ROW("OS", "%s", M->di.os); ROW("Kernel", "%s", M->di.kernel);
		ROW("Architecture", "%s", M->di.arch); ROW("Storage", "%s", M->di.storage);
		break;
	case RH_I_CATALOG:
		if (M->cat.status[0]) {                       /* signed catalog (DEV builds) */
			ROW("Source", "%s", M->cat.source[0] ? (M->cat.source[0] == 'b' ? "Signed, bundled" : "Signed, downloaded") : "None");
			ROW("Signature", "%s", M->cat.ok ? "Verified" : "Not verified");
			if (M->cat.ok) { ROW("Serial", "%u", M->cat.serial); ROW("Published", "%s", M->cat.generated[0] ? M->cat.generated : "Unknown"); }
			ROW("Apps", "%d", M->n_apps);
			if (M->cat.ok) note = OPS && OPS->refresh_catalog ? "Press A to look for a newer catalog. It is only used if its signature checks out."
			                                                  : "Only entries covered by the signature are shown.";
			else note = M->cat.status;
			break;
		}
		ROW("Source", "Local files"); ROW("Apps", "%d", M->n_apps); ROW("Available", "%d", avail);
		ROW("Devices", "%d", M->n_devs); ROW("Signature", "Not checked");
		note = "The catalog is read from files on this device. Signed catalogs are not implemented yet.";
		break;
	case RH_I_NETWORK:
		if (OPS && OPS->download) {
			ROW("Last result", "%s", OPS->net_status ? OPS->net_status() : "None yet"); ROW("Downloads", "HTTPS only");
			note = "Connect to Wi-Fi first. Server certificates are always checked, and every file is verified before it is used.";
			break;
		}
		ROW("Status", "Not implemented"); ROW("Downloads", "Disabled");
		note = "RetroHatch makes no network connections in this build.";
		break;
	default:
		ROW("App", "RetroHatch"); ROW("Build", "%s", OPS && OPS->build_label ? OPS->build_label : "Nano UI preview");
		ROW("Installing", "%s", OPS ? "DEV: test app only" : "Not in this UI");
		ROW("Fonts", "GNU Unifont, Kode Mono"); ROW("Icons", "Lucide");
		break;
	}
	y += kv_card(d, y, r, n, C_TXT) + 8;
	if (note) paragraph(d, 10, &y, 220, note, C_TXT2, 0);
	return y + 4 - y0;
}

/* ---- empty states ---- */
static void empty_state_c(SDL_Surface *d, int ico, rh_rgb col, const char *title, const char *body)
{
	int y = CONT_Y + 32;
	icon(d, ico, 120, y + 24, col);
	gfx_text_c(d, f_title, title, 120, y + 62, C_TXT);
	y += 86;
	paragraph(d, 20, &y, 200, body, C_TXT2, 1);
}

static void empty_state(SDL_Surface *d, int ico, const char *title, const char *body)
{
	empty_state_c(d, ico, C_GREEN, title, body);
}

/* nothing-to-show states (no apps, none installed, no updates): the RetroHatch mark instead of a generic glyph */
static void empty_state_mark(SDL_Surface *d, const char *title, const char *body)
{
	int y = CONT_Y + 32;
	gfx_img(d, img_mark, 120 - img_mark->w / 2, y - 4);
	gfx_text_c(d, f_title, title, 120, y + 62, C_TXT);
	y += 86;
	paragraph(d, 20, &y, 200, body, C_TXT2, 1);
}

/* ---- install flow screens (reachable only when an ops provider is set) ---- */
static void fmt_size(char *o, size_t n, unsigned long long b);

static void button(SDL_Surface *d, int y, int sel, const char *label)
{
	row_bg(d, 8, y, 224, 22, sel);
	gfx_text_c(d, f_title, label, 120, y + (22 - gfx_font_h(f_title)) / 2, sel ? C_ONACC : C_TXT);
}

static const char *inst_ver(int ai)
{
	int i;
	for (i = 0; i < M->n_inst; i++) if (M->inst[i].app == ai) return M->inst[i].version;
	return "";
}

/* Read-only plan for a production build: what an install would do and where, from the installer's own name checks. Nothing runs. */
static void draw_preview(SDL_Surface *d)
{
	const rh_app *a = &M->apps[CUR.app];
	kv r[3]; char b[96], t[96], why[48] = "";
	const char *ver = a->version[0] ? a->version : "Unknown";
	gfx_text_c(d, f_title, gfx_ellipsize(f_title, a->name, 210, b, sizeof b), 120, 37, C_TXT);
	gfx_text_c(d, f_body, M->dev_fixture ? "DEV FIXTURE. Preview only." : "Preview only. No changes.", 120, 55, M->dev_fixture ? C_ERR : C_TXT2);
	snprintf(r[0].l, sizeof r[0].l, "Action");
	if (cur_op) snprintf(r[0].v, sizeof r[0].v, "Update %s > %s", inst_ver(CUR.app)[0] ? inst_ver(CUR.app) : "Unknown", ver);   /* the font has no arrow glyph */
	else snprintf(r[0].v, sizeof r[0].v, "Install %s", ver);
	snprintf(r[1].l, sizeof r[1].l, "Target");
	if (PLAN && PLAN(a->id, a->version, a->dest_name, t, sizeof t, why, sizeof why)) snprintf(r[1].v, sizeof r[1].v, "%s", t);
	else snprintf(r[1].v, sizeof r[1].v, "Unknown. %s", why[0] ? why : "No plan");
	snprintf(r[2].l, sizeof r[2].l, "Size"); fmt_size(r[2].v, sizeof r[2].v, a->size);
	kv_card(d, 74, r, 3, C_TXT);
}

static void draw_confirm(SDL_Surface *d)
{
	if (preview) { draw_preview(d); return; }
	const rh_app *a = &M->apps[CUR.app];
	kv r[3]; char b[96]; int y0 = CONT_B - 47;
	gfx_text_c(d, f_title, gfx_ellipsize(f_title, a->name, 210, b, sizeof b), 120, 37, C_TXT);
	if (cur_op == 2) {                              /* uninstall: warning in orange, then what stays */
		gfx_text_c(d, f_body, "This removes the app", 120, 55, C_ERR);
		snprintf(r[0].l, sizeof r[0].l, "Version"); snprintf(r[0].v, sizeof r[0].v, "%s", inst_ver(CUR.app));
		snprintf(r[1].l, sizeof r[1].l, "File"); snprintf(r[1].v, sizeof r[1].v, "%s", a->dest_name);
		kv_card(d, 74, r, 2, C_TXT);
		gfx_text_c(d, f_body, "Saves and settings are kept", 120, 146, C_TXT2);
		button(d, y0, CUR.sel == 0, "Cancel");
		button(d, y0 + 25, CUR.sel == 1, "Uninstall");
		return;
	}
	if (cur_op == 3) {                              /* download: what and from where; nothing is installed */
		char hb[64];
		gfx_text_c(d, f_body, "Downloads over HTTPS", 120, 55, C_TXT2);
		snprintf(r[0].l, sizeof r[0].l, "Version"); snprintf(r[0].v, sizeof r[0].v, "%s", a->version);
		snprintf(r[1].l, sizeof r[1].l, "Size"); fmt_size(r[1].v, sizeof r[1].v, a->size);
		snprintf(r[2].l, sizeof r[2].l, "From"); snprintf(r[2].v, sizeof r[2].v, "%s", host_of(a->url, hb, sizeof hb));
		kv_card(d, 74, r, 3, C_TXT);
		button(d, y0, CUR.sel == 0, "Cancel");
		button(d, y0 + 25, CUR.sel == 1, "Download");
		return;
	}
	gfx_text_c(d, f_body, cur_op ? "Old version is backed up" : "Local file, no download", 120, 55, C_TXT2);
	snprintf(r[0].l, sizeof r[0].l, "Version");
	if (cur_op) snprintf(r[0].v, sizeof r[0].v, "%s > %s", inst_ver(CUR.app), a->version);   /* the font has no arrow glyph */
	else snprintf(r[0].v, sizeof r[0].v, "%s", a->version);
	snprintf(r[1].l, sizeof r[1].l, "Size"); fmt_size(r[1].v, sizeof r[1].v, a->size);
	snprintf(r[2].l, sizeof r[2].l, "File"); snprintf(r[2].v, sizeof r[2].v, "%s", a->dest_name);
	kv_card(d, 74, r, 3, C_TXT);
	button(d, y0, CUR.sel == 0, "Cancel");          /* default focus: Cancel */
	button(d, y0 + 25, CUR.sel == 1, cur_op ? "Update" : "Install");
}

static void draw_result(SDL_Surface *d)
{
	const rh_app *a = &M->apps[CUR.app < M->n_apps ? CUR.app : 0];
	char b[200];
	if (cur_op == 4) {                                    /* catalog refresh: msg says what happened */
		snprintf(b, sizeof b, "%s", res_msg);
		if (res_rc == 0) empty_state_c(d, IC_CHECK_L, C_GREEN, "Catalog", b);
		else empty_state_c(d, IC_ALERT_L, C_ERR, "Refresh failed", b);
		return;
	}
	if (cur_op == 3) {
		if (res_rc == 0) { snprintf(b, sizeof b, "%s %s is verified and ready to install.", a->name, a->version); empty_state_c(d, IC_CHECK_L, C_GREEN, "Downloaded", b); }
		else { snprintf(b, sizeof b, "%s. Nothing was kept.", res_msg); empty_state_c(d, IC_ALERT_L, C_ERR, "Download failed", b); }
		return;
	}
	if (res_rc == 0) {
		if (cur_op == 2) snprintf(b, sizeof b, "%s was removed. Saves and settings are kept.", a->name);
		else snprintf(b, sizeof b, cur_op ? "%s is now %s. Re-open the Apps drawer." : "%s %s. Open the Apps drawer to use it.", a->name, a->version);
		empty_state_c(d, IC_CHECK_L, C_GREEN, cur_op == 2 ? "Uninstalled" : cur_op ? "Updated" : "Installed", b);
	} else {
		snprintf(b, sizeof b, "%s. %s", res_msg, res_rc == 2 ? "Restart RetroHatch to recover." : cur_op == 2 ? "The app was kept." : cur_op ? "Previous version kept." : "No changes were kept.");
		empty_state_c(d, IC_ALERT_L, C_ERR, cur_op == 2 ? "Uninstall failed" : cur_op ? "Update failed" : "Install failed", b);
	}
}

/* ---- state helpers ---- */
static int list_n(void)
{
	switch (CUR.s) {
	case RH_S_HOME: case RH_S_SETTINGS: return 4;
	case RH_S_DISCOVER: return M->n_apps;
	case RH_S_INSTALLED: return M->n_inst;
	case RH_S_UPDATES: return M->n_upd;
	default: return 0;
	}
}
static int row_p(void) { return CUR.s == RH_S_SETTINGS ? SET_P : LIST_P; }
static int row_h(void) { return CUR.s == RH_S_SETTINGS ? SET_RH : LIST_RH; }
static int is_list(void) { return CUR.s == RH_S_DISCOVER || CUR.s == RH_S_INSTALLED || CUR.s == RH_S_UPDATES || CUR.s == RH_S_SETTINGS; }
static int has_cta(void) { return CUR.s == RH_S_DETAILS; }   /* every details page carries the action bar */

static rh_action app_action(int ai)
{
	const rh_app *a = &M->apps[ai];
	int i;
	for (i = 0; i < M->n_inst; i++)
		if (M->inst[i].app == ai)
		{
			if (!(a->verified && rh_ver_cmp(M->inst[i].version, a->version) < 0))   /* no update pending: Uninstall (DEV, allowlisted) */
				return OPS && OPS->can_uninstall && OPS->can_uninstall(a, blocked_why, sizeof blocked_why) ? RH_ACT_UNINSTALL : RH_ACT_INSTALLED;
			if (!OPS || !OPS->can_update) return RH_ACT_UPDATE;       /* production: shown, never actionable */
			if (OPS->can_update(a, M->inst[i].version, blocked_why, sizeof blocked_why)) return RH_ACT_UPDATE_NOW;
			return OPS->can_download && OPS->can_download(a, blocked_why, sizeof blocked_why) ? RH_ACT_DOWNLOAD : RH_ACT_BLOCKED;
		}
	if (!a->verified) return RH_ACT_UNAVAILABLE;
	if (!OPS) return RH_ACT_INSTALL_SOON;                       /* production: never actionable */
	if (OPS->can_install(a, blocked_why, sizeof blocked_why)) return RH_ACT_INSTALL;
	if (OPS->can_download && OPS->can_download(a, blocked_why, sizeof blocked_why)) return RH_ACT_DOWNLOAD;
	return RH_ACT_BLOCKED;
}

void rh_ui_set_ops(const rh_ui_ops *ops) { OPS = ops; }
void rh_ui_set_planner(rh_plan_fn plan) { PLAN = plan; }
static int act_preview(rh_action a) { return PLAN && (a == RH_ACT_INSTALL_SOON || a == RH_ACT_UPDATE); }   /* production bars that open the preview */
static int act_focus(rh_action a)
{
	return a == RH_ACT_INSTALL || a == RH_ACT_UPDATE_NOW || a == RH_ACT_UNINSTALL || a == RH_ACT_DOWNLOAD || act_preview(a);
}
int rh_ui_busy(void) { return CUR.s == RH_S_WORKING; }

int rh_ui_run_pending(void)
{
	if (!pending) return 0;
	pending = 0;
	res_msg[0] = 0;
	prog_done = prog_total = 0;
	if (!OPS) res_rc = 1;
	else if (cur_op == 4) res_rc = OPS->refresh_catalog ? OPS->refresh_catalog(res_msg, sizeof res_msg) : 1;
	else if (cur_op == 3) res_rc = OPS->download ? OPS->download(&M->apps[CUR.app], res_msg, sizeof res_msg) : 1;
	else res_rc = (cur_op == 2 ? OPS->uninstall : cur_op ? OPS->update : OPS->install)(&M->apps[CUR.app], res_msg, sizeof res_msg);
	if (OPS && OPS->refresh) OPS->refresh();
	CUR.s = RH_S_RESULT;
	return 1;
}
static int view_h(void) { return CONT_B - CONT_Y - (has_cta() ? CTA_H + 4 : 0); }

static int total_h(void)
{
	if (CUR.s == RH_S_DETAILS) return details(NULL, 0, &M->apps[CUR.app]);
	if (CUR.s == RH_S_INFO) return info_page(NULL, 0, CUR.info);
	if (is_list()) return list_n() * row_p();
	return 0;
}
static int max_scroll(void) { int m = total_h() - view_h(); return m > 0 ? m : 0; }

static void ensure_visible(void)
{
	int top = CUR.sel * row_p(), bot = top + row_h();
	if (top < CUR.scroll) CUR.scroll = top;
	if (bot > CUR.scroll + view_h())   /* snap to whole rows: no sliver of the row above */
		CUR.scroll = (bot - view_h() + row_p() - 1) / row_p() * row_p();
	if (CUR.scroll < 0) CUR.scroll = 0;
}

static void go(rh_screen s, rh_info info, int app)
{
	if (depth >= 7) return;
	st[++depth] = (frame){s, info, app, 0, 0};
}

/* app index a catalog-backed row should open; -1 = none */
static int row_app(int i)
{
	switch (CUR.s) {
	case RH_S_DISCOVER: return i;
	case RH_S_INSTALLED: return M->inst[i].app;
	case RH_S_UPDATES: return M->inst[M->upd[i]].app;
	default: return -1;
	}
}

void rh_ui_key(rh_key k)
{
	int n = list_n();
	if (CUR.s == RH_S_WORKING) return;                          /* install running: no input */
	if (k == RH_K_B) { if (depth) depth--; return; }
	if (CUR.s == RH_S_CONFIRM && preview) { if (k == RH_K_A && depth) depth--; return; }   /* nothing to confirm: A/B go back */
	if (CUR.s == RH_S_CONFIRM) {
		if (k == RH_K_UP || k == RH_K_DOWN) CUR.sel = k == RH_K_DOWN;
		else if (k == RH_K_A) { if (CUR.sel == 0) depth--; else { CUR.s = RH_S_WORKING; pending = 1; } }
		return;
	}
	if (CUR.s == RH_S_RESULT) { if (k == RH_K_A && depth) depth--; return; }
	if (k == RH_K_UP || k == RH_K_DOWN) {
		int dn = k == RH_K_DOWN;
		if (CUR.s == RH_S_HOME || is_list()) {
			if (n) CUR.sel += dn ? (CUR.sel < n - 1) : -(CUR.sel > 0);
			if (CUR.s != RH_S_HOME) ensure_visible();
		} else if (CUR.s == RH_S_DETAILS || CUR.s == RH_S_INFO) {
			CUR.scroll += dn ? STEP : -STEP;
			if (CUR.scroll > max_scroll()) CUR.scroll = max_scroll();
			if (CUR.scroll < 0) CUR.scroll = 0;
		}
		return;
	}
	if (k != RH_K_A) return;
	switch (CUR.s) {
	case RH_S_HOME: go((rh_screen[]){RH_S_DISCOVER, RH_S_INSTALLED, RH_S_UPDATES, RH_S_SETTINGS}[CUR.sel], 0, 0); break;
	case RH_S_SETTINGS: go(RH_S_INFO, (rh_info)CUR.sel, 0); break;
	case RH_S_INFO:
		if (CUR.info == RH_I_CATALOG && OPS && OPS->refresh_catalog && M->cat.status[0]) { cur_op = 4; go(RH_S_WORKING, 0, 0); pending = 1; }
		break;
	case RH_S_DISCOVER: case RH_S_INSTALLED: case RH_S_UPDATES:
		if (n && row_app(CUR.sel) >= 0) go(RH_S_DETAILS, 0, row_app(CUR.sel));
		break;
	case RH_S_DETAILS:
		{ rh_action act = app_action(CUR.app);
		  if (act_preview(act)) { preview = 1; cur_op = act == RH_ACT_UPDATE; go(RH_S_CONFIRM, 0, CUR.app); break; }
		  preview = 0;
		  if (act == RH_ACT_INSTALL || act == RH_ACT_UPDATE_NOW || act == RH_ACT_UNINSTALL || act == RH_ACT_DOWNLOAD) {
			cur_op = act == RH_ACT_DOWNLOAD ? 3 : act == RH_ACT_UNINSTALL ? 2 : act == RH_ACT_UPDATE_NOW; go(RH_S_CONFIRM, 0, CUR.app); } }   /* every other bar is inert */
		break;
	default: break;
	}
}

void rh_ui_view_get(rh_ui_view *v)
{
	memset(v, 0, sizeof *v);
	v->action = CUR.s == RH_S_DETAILS ? app_action(CUR.app) : RH_ACT_NONE;
	v->screen = CUR.s; v->info = CUR.info; v->app = CUR.app; v->sel = CUR.sel; v->scroll = CUR.scroll; v->depth = depth;
	v->count = list_n();
	v->result = res_rc;
	if (CUR.s == RH_S_HOME) v->sel_visible = 1;
	else if (is_list() && v->count) {
		int top = CONT_Y + CUR.sel * row_p() - CUR.scroll;
		v->sel_visible = top >= CONT_Y && top + row_h() <= CONT_B;
	} else v->sel_visible = 1;
}

/* ---- drawing ---- */
static const char *screen_title(void)
{
	switch (CUR.s) {
	case RH_S_DISCOVER: return "Discover";
	case RH_S_DETAILS: return "App Details";
	case RH_S_INSTALLED: return "Installed";
	case RH_S_UPDATES: return "Updates";
	case RH_S_SETTINGS: return "Settings";
	case RH_S_INFO: return INFO_TITLE[CUR.info];
	case RH_S_CONFIRM: if (preview) return cur_op ? "Update Preview" : "Install Preview";   /* fall through */
	case RH_S_RESULT: return cur_op == 4 ? "Catalog" : cur_op == 3 ? "Download" : cur_op == 2 ? "Uninstall" : cur_op ? "Update" : "Install";
	case RH_S_WORKING: return cur_op == 4 ? "Refreshing" : cur_op == 3 ? "Downloading" : cur_op == 2 ? "Removing" : cur_op ? "Updating" : "Installing";
	default: return "";
	}
}

static void hint(SDL_Surface *d, int cx, const char *letter, rh_rgb disc, const char *label, rh_rgb tc)
{
	gfx_disc(d, cx, HINT_Y + 10, 8, disc);
	gfx_text_c(d, f_body, letter, cx, HINT_Y + 2, C_ONACC);
	gfx_text(d, f_body, label, cx + 12, HINT_Y + 2, tc);
}

static void scrollbar(SDL_Surface *d, int total, int vh, int scroll)
{
	int th;
	if (total <= vh) return;
	th = vh * vh / total; if (th < 12) th = 12;
	gfx_fill(d, 235, CONT_Y, 3, vh, C_CARD);
	gfx_fill(d, 235, CONT_Y + (vh - th) * scroll / (total - vh), 3, th, C_TXT2);
}

static void draw_home(SDL_Surface *d)
{
	static const char *L[4] = {"Discover", "Installed", "Updates", "Settings"};
	static const int I[4] = {IC_SEARCH, IC_GRID, IC_REFRESH, IC_GEAR};
	int i;
	gfx_img(d, img_home, 0, 0);
	gfx_img(d, img_logo, (W - img_logo->w) / 2, 0);
	for (i = 0; i < 4; i++) menu_row(d, 8, HOME_Y + i * HOME_P, 224, HOME_RH, i == CUR.sel, I[i], L[i]);
}

static void draw_action(SDL_Surface *d, rh_action act)
{
	static const struct { int ico; const char *txt; } A[] = {
		{0, ""}, {IC_CHECK, "Installed"}, {IC_REFRESH, "Update available"}, {IC_DOWNLOAD, "Install (Coming soon)"}, {IC_LOCK, "Not available"},
		{IC_DOWNLOAD, "Install"}, {IC_LOCK, NULL} };
	rh_rgb ic_c = act == RH_ACT_INSTALLED ? C_GREEN : act == RH_ACT_UPDATE ? C_ACC : act == RH_ACT_INSTALL_SOON ? C_TXT2 : C_DIS;
	rh_rgb tx_c = act == RH_ACT_INSTALL_SOON ? C_TXT2 : act == RH_ACT_UNAVAILABLE ? C_DIS : C_TXT;
	int cy = CONT_B - CTA_H;
	if (act_focus(act)) {   /* DEV actions and the production preview: the only focusable bar -> selected-row style */
		int dl = act == RH_ACT_INSTALL || act == RH_ACT_DOWNLOAD || act == RH_ACT_INSTALL_SOON, rf = act == RH_ACT_UPDATE_NOW || act == RH_ACT_UPDATE;
		gfx_rfill(d, 8, cy, 224, CTA_H, 4, C_ACC);
		icon(d, dl ? IC_DOWNLOAD : rf ? IC_REFRESH : IC_TRASH, 26, cy + CTA_H / 2, C_ONACC);
		gfx_text(d, f_title, act == RH_ACT_INSTALL ? "Install" : act == RH_ACT_DOWNLOAD ? "Download" : act == RH_ACT_UPDATE_NOW ? "Update" : act == RH_ACT_INSTALL_SOON ? "Preview install" : act == RH_ACT_UPDATE ? "Preview update" : "Uninstall", 44, cy + (CTA_H - gfx_font_h(f_title)) / 2, C_ONACC);
		icon(d, IC_CHEV, 218, cy + CTA_H / 2, C_ONACC);
		return;
	}
	gfx_rbox(d, 8, cy, 224, CTA_H, 4, C_LINE, C_CARD);   /* card style, not the amber selected style: it is not focusable */
	icon(d, A[act].ico, 26, cy + CTA_H / 2, ic_c);
	gfx_text(d, f_title, A[act].txt ? A[act].txt : blocked_why, 44, cy + (CTA_H - gfx_font_h(f_title)) / 2, tx_c);
}

static void draw_content(SDL_Surface *d)
{
	int i, y, vh = view_h(), total = total_h();
	switch (CUR.s) {
	case RH_S_DISCOVER:
		for (i = 0; i < M->n_apps; i++) {
			const rh_app *a = &M->apps[i];
			y = CONT_Y + i * LIST_P - CUR.scroll;
			if (y + LIST_RH > CONT_Y && y < CONT_B) {
				char sub[160];   /* installed status comes from RetroHatch's own record; absent record = nothing claimed */
				snprintf(sub, sizeof sub, "%s%s", inst_ver(i)[0] ? "Installed. " : "", a->desc[0] ? a->desc : "No description");
				list_row(d, y, i == CUR.sel, a->name, sub);
			}
		}
		if (!M->n_apps) empty_state_mark(d, "No catalog entries", "No app files were found in the local catalog.");
		break;
	case RH_S_INSTALLED:
		for (i = 0; i < M->n_inst; i++) {
			char sub[48]; int a = M->inst[i].app;
			snprintf(sub, sizeof sub, "Version %s", M->inst[i].version);
			y = CONT_Y + i * LIST_P - CUR.scroll;
			if (y + LIST_RH > CONT_Y && y < CONT_B) list_row(d, y, i == CUR.sel, a >= 0 ? M->apps[a].name : M->inst[i].id, sub);
		}
		if (!M->n_inst) empty_state_mark(d, "No installed applications", "You haven't installed any applications with RetroHatch yet.");
		break;
	case RH_S_UPDATES:
		for (i = 0; i < M->n_upd; i++) {
			char sub[64]; int ii = M->upd[i], a = M->inst[ii].app;
			snprintf(sub, sizeof sub, "%s > %s", M->inst[ii].version, M->apps[a].version);
			y = CONT_Y + i * LIST_P - CUR.scroll;
			if (y + LIST_RH > CONT_Y && y < CONT_B) list_row(d, y, i == CUR.sel, M->apps[a].name, sub);
		}
		if (!M->n_upd) empty_state_mark(d, "No updates available", "All of your applications are up to date.");
		break;
	case RH_S_SETTINGS: {
		static const int I[4] = {IC_PHONE, IC_DATABASE, IC_WIFI, IC_INFO};
		for (i = 0; i < 4; i++) {
			y = CONT_Y + i * SET_P - CUR.scroll;
			menu_row(d, 8, y, 224, SET_RH, i == CUR.sel, I[i], INFO_TITLE[i]);
		}
		break; }
	case RH_S_DETAILS: details(d, CONT_Y - CUR.scroll, &M->apps[CUR.app]); break;
	case RH_S_INFO: info_page(d, CONT_Y - CUR.scroll, CUR.info); break;
	case RH_S_CONFIRM: draw_confirm(d); break;
	case RH_S_WORKING:
		if (cur_op == 3 || cur_op == 4) {
			char pb[80];
			if (cur_op == 3 && prog_total) snprintf(pb, sizeof pb, "%u%% of %.1f KB. B cancels.", (unsigned)(prog_done * 100 / prog_total), prog_total / 1024.0);
			else snprintf(pb, sizeof pb, "%s", cur_op == 3 ? "Connecting... B cancels." : "Connecting...");
			empty_state(d, IC_REFRESH_L, cur_op == 3 ? "Downloading..." : "Refreshing...", pb);
		} else empty_state(d, IC_REFRESH_L, cur_op == 2 ? "Removing..." : cur_op ? "Updating..." : "Installing...", "Please wait. Do not power off.");
		break;
	case RH_S_RESULT: draw_result(d); break;
	default: break;
	}
	if (CUR.s != RH_S_SETTINGS) scrollbar(d, total, vh, CUR.scroll);
}

void rh_ui_draw(SDL_Surface *scr)
{
	SDL_Rect clip = {0, CONT_Y, W, (Uint16)(CONT_B - CONT_Y)}, all = {0, 0, W, W};
	int a_ok;
	gfx_fill(scr, 0, 0, W, W, C_BG);
	if (CUR.s == RH_S_HOME) draw_home(scr);
	else {
		clip.h = (Uint16)view_h();
		SDL_SetClipRect(scr, &clip);
		draw_content(scr);
		SDL_SetClipRect(scr, &all);
		if (has_cta()) draw_action(scr, app_action(CUR.app));
		gfx_img(scr, img_header, 0, 0);
		gfx_fill(scr, 0, HDR_H, W, 1, C_LINE);
		{
			char t[48]; int dev = M->dev_fixture && (CUR.s == RH_S_DISCOVER || CUR.s == RH_S_DETAILS || CUR.s == RH_S_INSTALLED || CUR.s == RH_S_UPDATES || CUR.s == RH_S_CONFIRM);
			snprintf(t, sizeof t, "%s%s", screen_title(), dev ? " [DEV]" : "");   /* fixture entries are never shown as real apps */
			gfx_text_c(scr, f_title, t, W / 2, (HDR_H - gfx_font_h(f_title)) / 2, C_TXT);
		}
	}
	a_ok = CUR.s == RH_S_HOME || CUR.s == RH_S_CONFIRM || CUR.s == RH_S_RESULT || (CUR.s == RH_S_DETAILS && act_focus(app_action(CUR.app))) || (CUR.s == RH_S_INFO && CUR.info == RH_I_CATALOG && OPS && OPS->refresh_catalog && M->cat.status[0]) || (is_list() && list_n() && (CUR.s == RH_S_SETTINGS || row_app(CUR.sel) >= 0));
	gfx_fill(scr, 8, HINT_Y - 2, 224, 1, C_LINE);
	hint(scr, 22, "A", a_ok ? C_GREEN : C_DIS, "Select", a_ok ? C_TXT : C_DIS);
	hint(scr, 178, "B", depth && CUR.s != RH_S_WORKING ? C_ACC : C_DIS, "Back", depth && CUR.s != RH_S_WORKING ? C_TXT : C_DIS);
}
