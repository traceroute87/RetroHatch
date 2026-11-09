#!/bin/sh
# Cross-compile the HTTPS download test tool for the Nano (Buildroot toolchain, static OpenSSL 1.1.1 from its sysroot). Run in WSL:
#   sh platforms/nano/cli/build-net-arm.sh  -> build/rh_get_arm
set -e
CC=${CC:-$HOME/nanofi-build/FunKey-OS/FunKey/output/host/bin/arm-linux-gcc}
SYSROOT=$("$CC" -print-sysroot)
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
mkdir -p "$ROOT/build"
"$CC" -std=c99 -Os -Wall -Wextra -Wno-unused-result -static -o "$ROOT/build/rh_get_arm" "$HERE/rh_net_cli.c" "$ROOT/core/rh_net.c" "$ROOT/core/sha256.c" \
	"$SYSROOT/usr/lib/libssl.a" "$SYSROOT/usr/lib/libcrypto.a" -ldl -lpthread
file "$ROOT/build/rh_get_arm"; ls -l "$ROOT/build/rh_get_arm"; sha256sum "$ROOT/build/rh_get_arm"
