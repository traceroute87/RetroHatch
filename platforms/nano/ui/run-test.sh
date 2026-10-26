#!/bin/sh
# TEST-ONLY launcher (RetroHatchTest.opk). Reads isolated test data from /mnt/FunKey/.retrohatch-test:
#   mode               one of: populated | noupdates | empty   (default populated)
#   catalog/           test catalog (RH Probe entries, "(test)" names)
#   <mode>/installed.tsv
# Never touches /mnt/FunKey/.retrohatch (production state). The UI only reads; nothing is written.
cd "$(dirname "$0")" || exit 1
T=/mnt/FunKey/.retrohatch-test
M=$(cat "$T/mode" 2>/dev/null)
case "$M" in populated|noupdates|empty) ;; *) M=populated ;; esac
exec ./retrohatch --catalog "$T/catalog" --state "$T/$M"