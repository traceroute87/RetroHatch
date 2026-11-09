#!/bin/sh
# Cross-compile the headless experimental-install driver for the Nano with the existing FunKey Buildroot toolchain (read-only use of the
# toolchain; nothing is copied to a device). Run in WSL:  sh platforms/nano/cli/build-exp-arm.sh   -> build/rh_exp_arm (static)
set -e
BR=${BR:-$HOME/nanofi-build/FunKey-OS/FunKey/output}
CC=${CC:-$BR/host/bin/arm-linux-gcc}
SYSROOT=$("$CC" -print-sysroot)
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
MC="$ROOT/vendor/monocypher"
mkdir -p "$ROOT/build"
"$CC" -std=gnu99 -Os -Wall -Wextra -Wno-format-truncation -D_GNU_SOURCE=1 -DRH_EXPERIMENTAL -static -ffunction-sections -fdata-sections -Wl,--gc-sections \
	-I"$SYSROOT/usr/include/SDL" -o "$ROOT/build/rh_exp_arm" \
	"$HERE/rh_exp_cli.c" "$ROOT/ui/rh_ops.c" "$ROOT/ui/rh_source.c" "$ROOT/ui/rh_model.c" "$ROOT/ui/rh_json.c" "$ROOT/platforms/nano/rh_install.c" \
	"$ROOT/core/sha256.c" "$ROOT/core/rh_net.c" "$ROOT/core/rh_zip.c" "$ROOT/core/rh_catalog.c" "$ROOT/core/rh_catalog_state.c" "$MC/monocypher.c" "$MC/monocypher-ed25519.c" \
	"$SYSROOT/usr/lib/libssl.a" "$SYSROOT/usr/lib/libcrypto.a" -lz -ldl -lpthread
file "$ROOT/build/rh_exp_arm"
ls -l "$ROOT/build/rh_exp_arm"
sha256sum "$ROOT/build/rh_exp_arm"
