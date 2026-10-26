#!/bin/sh
# Cross-compile the signed-catalog verifier CLI for the Nano with the existing FunKey Buildroot toolchain
# (read-only use; nothing is copied to a device). Run in WSL:  sh platforms/nano/cli/build-verify-arm.sh
# -> build/rh_verify_arm (static, -Os) + size report. Same flags as build-arm.sh.
set -e
CC=${CC:-$HOME/nanofi-build/FunKey-OS/FunKey/output/host/bin/arm-linux-gcc}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
MC="$ROOT/vendor/monocypher"
mkdir -p "$ROOT/build"
"$CC" -std=c99 -Os -Wall -Wextra -Wno-unused-result -static -ffunction-sections -fdata-sections -Wl,--gc-sections \
	-o "$ROOT/build/rh_verify_arm" \
	"$HERE/rh_verify_cli.c" "$ROOT/core/rh_catalog.c" "$ROOT/core/rh_catalog_state.c" "$ROOT/core/sha256.c" "$MC/monocypher.c" "$MC/monocypher-ed25519.c"
file "$ROOT/build/rh_verify_arm"
ls -l "$ROOT/build/rh_verify_arm"
"${CC%gcc}size" "$ROOT/build/rh_verify_arm" 2>/dev/null || true
sha256sum "$ROOT/build/rh_verify_arm"
