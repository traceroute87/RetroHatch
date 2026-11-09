#!/bin/sh
# Build $NAME.opk for the RG Nano with the existing FunKey Buildroot toolchain
# (read-only use). Builds and stages only; never deploys.
# Run in WSL:  sh platforms/nano/ui/build-opk.sh   -> build/$NAME.opk (+ .sha256)
# Needs: arm-linux-gcc (musl, sysroot has SDL 1.2 + SDL_image), mksquashfs.
set -e
BR=${BR:-$HOME/nanofi-build/FunKey-OS/FunKey/output}
CC=${CC:-$BR/host/bin/arm-linux-gcc}
STRIP=${STRIP:-$BR/host/bin/arm-linux-strip}
SYSROOT=$("$CC" -print-sysroot)
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
OUT=${OUT:-$ROOT/build}   # override to build somewhere that must not replace the staged artifacts
# TEST=1 builds RetroHatchTest.opk: same binary, launcher reads isolated test data (see run-test.sh)
# DEV=1 builds RetroHatchDev.opk: install flow for RH Probe only, DEV state dir only (ui/rh_ops.c); never for production
EXTRA=""; DEFS=""; LIBS=""; ICON=retrohatch
MC="$ROOT/vendor/monocypher"
if [ "${TEST:-0}" = 1 ]; then NAME=RetroHatchTest; RUN=run-test.sh; DESK=retrohatchtest
elif [ "${DEV:-0}" = 1 ]; then NAME=RetroHatchDev; RUN=run.sh; DESK=retrohatchdev; ICON=retrohatchdev
	EXTRA="$ROOT/ui/rh_ops.c $ROOT/ui/rh_source.c $ROOT/core/rh_net.c $ROOT/core/rh_zip.c $ROOT/core/rh_catalog.c $ROOT/core/rh_catalog_state.c $MC/monocypher.c $MC/monocypher-ed25519.c"
	DEFS="-DRH_DEV -DRH_EXPERIMENTAL -I$HERE"   # trusted_keys_dev.h: the DEV signing key's PUBLIC half only; RH_EXPERIMENTAL = UNVERIFIED test installs of candidates (DEV only, never in the production build)
	LIBS="$SYSROOT/usr/lib/libssl.a $SYSROOT/usr/lib/libcrypto.a -lz -ldl -lpthread"
	DEVCAT=${DEVCAT:-$ROOT/build/dev-catalog/bundled.pkg}   # signed with the DEV key: python tools/make_dev_catalog.py --key ...
	[ -f "$DEVCAT" ] || { echo "missing $DEVCAT (run tools/make_dev_catalog.py --out build/dev-catalog --key <dev key>)" >&2; exit 1; }
else NAME=RetroHatch; RUN=run.sh; DESK=retrohatch; fi
if [ "${DEV:-0}" != 1 ]; then   # production (and TEST): signed catalog + the same install engine, the PRODUCTION key only (trusted_keys_prod.h; the DEV key header is not on the include path)
	EXTRA="$ROOT/ui/rh_ops.c $ROOT/ui/rh_source.c $ROOT/core/rh_net.c $ROOT/core/rh_catalog.c $ROOT/core/rh_catalog_state.c $MC/monocypher.c $MC/monocypher-ed25519.c"
	DEFS="-I$HERE"
	LIBS="$SYSROOT/usr/lib/libssl.a $SYSROOT/usr/lib/libcrypto.a -ldl"
fi
PKG=$OUT/opk-stage-$NAME
rm -rf "$PKG"; mkdir -p "$PKG/assets" "$PKG/catalog/apps" "$PKG/catalog/devices"

"$CC" -std=gnu99 -Os -Wall -Wextra -Wno-format-truncation -D_GNU_SOURCE=1 -D_REENTRANT $DEFS \
	-I"$SYSROOT/usr/include/SDL" \
	-o "$PKG/retrohatch" \
	"$ROOT/ui/rh_ui_main.c" "$ROOT/ui/rh_ui.c" "$ROOT/ui/rh_gfx.c" "$ROOT/ui/rh_model.c" "$ROOT/ui/rh_json.c" \
	"$ROOT/platforms/nano/rh_install.c" "$ROOT/core/sha256.c" $EXTRA \
	-lSDL_image -lSDL $LIBS -lm -lpthread
"$STRIP" "$PKG/retrohatch"

cp "$ROOT"/ui/assets/* "$PKG/assets/"
cp "$ROOT"/catalog/apps/*.json "$PKG/catalog/apps/"          # read-only snapshot; TaraFi stays unavailable
cp "$ROOT"/catalog/devices/*.json "$PKG/catalog/devices/"
mkdir -p "$PKG/candidates" && cp "$ROOT/candidates/rg-nano.json" "$PKG/candidates/" && mkdir -p "$PKG/candidates/icons"   # UNAPPROVED discovery snapshot: read-only in production; in the DEV build the installable ones get an experimental test install
# icons: only the files the snapshots name (a snapshot names an icon only when its redistribution status is "redistributable"); a missing named file stops the build
for f in $(grep -ho '"icon_file": *"icons/[A-Za-z0-9._-]*\.png"' "$ROOT/candidates/rg-nano.json" | sed 's/.*"icons\//icons\//; s/"$//'); do cp "$ROOT/candidates/$f" "$PKG/candidates/$f"; done
# the notices (MIT text, copyright lines) that the shipped icons require travel with them
cp "$ROOT/candidates/icons/NOTICE.md" "$PKG/candidates/icons/NOTICE.md"
if [ "${DEV:-0}" = 1 ]; then   # DEV: signed catalog snapshot + trusted roots instead of loose JSON files (the candidate snapshot above stays)
	rm -rf "$PKG/catalog"; mkdir -p "$PKG/catalog" "$PKG/certs"
	cp "$DEVCAT" "$PKG/catalog/catalog.pkg"; cp "$HERE/ca-bundle.crt" "$PKG/certs/ca-bundle.crt"
fi
if [ "${DEV:-0}" != 1 ]; then
	mkdir -p "$PKG/certs"; cp "$HERE/ca-bundle.crt" "$PKG/certs/ca-bundle.crt"
	# A signed catalog snapshot is bundled only when one is supplied: PRODCAT=<catalog.pkg made by tools/make_pkg.py from a catalog signed with the
	# production key>. None is published yet, so by default there is none and the app can install nothing until a refresh verifies one.
	if [ -n "${PRODCAT:-}" ]; then [ -f "$PRODCAT" ] || { echo "missing $PRODCAT" >&2; exit 1; }; mkdir -p "$PKG/catalog"; cp "$PRODCAT" "$PKG/catalog/catalog.pkg"; fi
fi
cp "$HERE/$RUN" "$PKG/run.sh"
cp "$HERE/$DESK.funkey-s.desktop" "$PKG/"
cp "$ROOT/ui/$ICON.png" "$PKG/$DESK.png"
chmod 755 "$PKG/run.sh" "$PKG/retrohatch"

rm -f "$OUT/$NAME.opk"
mksquashfs "$PKG" "$OUT/$NAME.opk" -all-root -noappend -no-xattrs -comp gzip -mkfs-time 0 -all-time 0 >/dev/null
( cd "$OUT" && sha256sum $NAME.opk | tee $NAME.opk.sha256 && ls -l $NAME.opk )
file "$PKG/retrohatch"
