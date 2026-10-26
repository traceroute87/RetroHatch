#!/bin/sh
# opkrun chdir()s into the mounted OPK before running this. exec keeps the pid that
# opkrun recorded, so the power daemon's SIGUSR1 reaches retrohatch itself.
cd "$(dirname "$0")" || exit 1
exec ./retrohatch
