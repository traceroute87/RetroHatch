#!/bin/sh
# Cross-compile the Phase 3B test CLI with the existing FunKey Buildroot
# toolchain (read-only use; does not run or modify Buildroot).
# Run in WSL:  sh platforms/nano/cli/build-arm.sh   -> build/rh_nano_test_cli
set -e
CC=${CC:-$HOME/nanofi-build/FunKey-OS/FunKey/output/host/bin/arm-linux-gcc}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
mkdir -p "$ROOT/build"
"$CC" -std=c99 -Os -Wall -Wextra -Wno-unused-result -static \
	-o "$ROOT/build/rh_nano_test_cli" \
	"$HERE/rh_nano_test_cli.c" "$ROOT/platforms/nano/rh_install.c" "$ROOT/core/sha256.c"
file "$ROOT/build/rh_nano_test_cli"
sha256sum "$ROOT/build/rh_nano_test_cli"
