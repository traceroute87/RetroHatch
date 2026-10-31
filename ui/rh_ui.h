/* RetroHatch Nano UI (240x240, SDL 1.2): screens + navigation.
 * Reads an rh_model; knows nothing about installing. */
#ifndef RH_UI_H
#define RH_UI_H
#include <stddef.h>
#include <SDL/SDL.h>
#include "rh_model.h"

typedef enum { RH_K_UP, RH_K_DOWN, RH_K_LEFT, RH_K_RIGHT, RH_K_A, RH_K_B } rh_key;
typedef enum { RH_S_HOME, RH_S_DISCOVER, RH_S_DETAILS, RH_S_INSTALLED, RH_S_UPDATES, RH_S_SETTINGS, RH_S_INFO,
	RH_S_CONFIRM, RH_S_WORKING, RH_S_RESULT } rh_screen;   /* last three: install flow (DEV builds only) */
typedef enum { RH_I_DEVICE, RH_I_CATALOG, RH_I_NETWORK, RH_I_ABOUT } rh_info;

/* App Details action bar (never focusable, A does nothing) */
typedef enum { RH_ACT_NONE, RH_ACT_INSTALLED, RH_ACT_UPDATE, RH_ACT_INSTALL_SOON, RH_ACT_UNAVAILABLE,
	RH_ACT_INSTALL,      /* DEV only: the one focusable action; A opens the confirm screen */
	RH_ACT_BLOCKED,      /* DEV only: install/update refused, reason shown, not focusable */
	RH_ACT_UPDATE_NOW,   /* DEV only: focusable "Update"; A opens the confirm screen */
	RH_ACT_UNINSTALL,    /* DEV only: focusable "Uninstall" (installed, no update pending, allowlisted) */
	RH_ACT_DOWNLOAD      /* DEV only: focusable "Download": verified entry whose file is not on the device yet */
} rh_action;

typedef struct {
	rh_screen screen;
	rh_action action;    /* RH_S_DETAILS only */
	rh_info info;        /* RH_S_INFO only */
	int app;             /* RH_S_DETAILS: index into model apps */
	int sel, count;      /* selected row / rows on this screen (lists, home, settings) */
	int scroll;          /* pixels */
	int sel_visible;     /* 1 when the selected row lies fully inside the content area */
	int depth;           /* 0 = home */
	int result;          /* RH_S_RESULT: 0 installed, 1 failed (nothing kept), 2 failed (restart to recover) */
} rh_ui_view;

/* Optional operations provider. NULL (production) = every action stays disabled and the UI links no
 * install code. A DEV build supplies one; the UI never touches the filesystem for installing itself. */
typedef struct {
	/* 1 = this verified, not-yet-installed app may be installed now; else why[] gets a short reason */
	int (*can_install)(const rh_app *a, char *why, size_t n);
	/* installed_ver = the version RetroHatch recorded. 1 = a strictly newer verified build may be installed over it now */
	int (*can_update)(const rh_app *a, const char *installed_ver, char *why, size_t n);
	int (*update)(const rh_app *a, char *msg, size_t n);   /* same return codes as install */
	/* uninstall of the app RetroHatch itself installed; saves/settings are never touched. Same return codes as install */
	int (*can_uninstall)(const rh_app *a, char *why, size_t n);
	int (*uninstall)(const rh_app *a, char *msg, size_t n);
	/* blocking. 0 = installed; 1 = failed, nothing kept; 2 = failed, restart to recover. msg[] = short reason */
	int (*install)(const rh_app *a, char *msg, size_t n);
	void (*refresh)(void);        /* reload the model after a change (may be NULL) */
	const char *build_label;      /* shown in Settings > About */
	/* network (all optional, NULL = no downloads in this build). Same return codes as install, msg[] = short reason */
	int (*can_download)(const rh_app *a, char *why, size_t n);   /* 1 = the verified file may be fetched now */
	int (*download)(const rh_app *a, char *msg, size_t n);       /* blocking; fills the local cache only, installs nothing */
	int (*refresh_catalog)(char *msg, size_t n);                 /* blocking; fetches and verifies a newer signed catalog */
	const char *(*net_status)(void);                             /* last network result for Settings > Network Status */
} rh_ui_ops;
void rh_ui_set_ops(const rh_ui_ops *ops);
/* Optional install PLANNER (read-only). Given the catalog names it returns the file an install would write, or why it would be
 * refused: 1 = target filled, 0 = refused, why = short reason (see rh_plan_target in rh_install.c). With a planner set and no ops,
 * a verified app's action bar opens an "Install Preview" screen: it shows the plan and changes nothing. */
typedef int (*rh_plan_fn)(const char *app_id, const char *version, const char *dest_name, char *target, size_t n, char *why, size_t wn);
void rh_ui_set_planner(rh_plan_fn plan);
void rh_ui_progress(uint64_t done, uint64_t total);   /* download progress for the "working" screen (total 0 = unknown) */
int rh_ui_busy(void);             /* install running: ignore quit/power keys until it ends */
int rh_ui_run_pending(void);      /* call after drawing: runs a queued install, returns 1 if it ran (redraw) */

/* asset_dir holds ui/assets. m must outlive the UI. Returns 0 on success. */
int rh_ui_init(const char *asset_dir, const rh_model *m);
void rh_ui_free(void);
void rh_ui_key(rh_key k);
void rh_ui_draw(SDL_Surface *scr);      /* scr is 240x240 */
void rh_ui_view_get(rh_ui_view *v);
#endif
