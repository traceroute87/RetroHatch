#!/bin/sh
# Runs on the Nano (copied to /tmp, i.e. RAM, by tools/batch_test.py). Launches ONE installed OPK the way the FunKey frontend does and collects evidence.
#   batch_launch.sh <opk path> <id> [startup_s=8] [run_s=14] [term_wait_s=8]
# Sequence = what retrofe / native_launch.sh / the frontend loop do (usr/local/sbin/frontend, usr/games/launchers/native_launch.sh):
#   keymap rom <opk>  ->  opkrun <opk> (pid record / wait / pid erase)  ->  [stop]  ->  termfix_all  ->  keymap default  ->  umount /opk
# It never presses a button. Stopping is SIGTERM to the app's own processes (then SIGKILL only if it ignores TERM for term_wait_s seconds).
# Prints key=value lines; evidence files stay in /tmp/rhb (<id>.log app output, .msgs new syslog lines, .dmesg new kernel lines, .fb last frame).
# Test overrides: RHB_DIR RHB_FB RHB_MSGS RHB_FBBYTES.
# Same environment retrofe launches apps with (an SSH session lacks /usr/local/sbin, so keymap/pid were "not found" and SDL 1.2 apps failed to init).
export PATH="$PATH:/usr/local/games:/usr/games:/usr/local/sbin:/usr/local/bin" HOME=/mnt/FunKey SDL_NOMOUSE=1
OPK=$1; ID=$2; SU=${3:-8}; RUN=${4:-14}; TW=${5:-8}
D=${RHB_DIR:-/tmp/rhb}; FB=${RHB_FB:-/dev/fb0}; MSGS=${RHB_MSGS:-/tmp/messages}; FBN=${RHB_FBBYTES:-115200}
[ -f "$OPK" ] || { echo "ERROR=opk missing"; exit 3; }
mkdir -p "$D"; rm -f "$D/$ID".*

pid_alive() { [ -d "/proc/$1" ] && ! grep -q '^State:.*Z' "/proc/$1/status" 2>/dev/null; }
kids_of() {   # all descendants of pid $1, one per line (leaves first is not needed)
	all=$(for d in /proc/[0-9]*; do p=${d#/proc/}; pp=$(sed 's/^.*) //' "$d/stat" 2>/dev/null | cut -d' ' -f2); [ -n "$pp" ] && echo "$p $pp"; done)
	cur=$1; out=""
	for _ in 1 2 3 4 5 6; do
		nxt=""
		for c in $cur; do for k in $(echo "$all" | awk -v pp="$c" '$2==pp {print $1}'); do nxt="$nxt $k"; out="$out $k"; done; done
		[ -z "$nxt" ] && break; cur=$nxt
	done
	echo $out
}
ticks_of() {  # utime+stime of the pids given
	t=0
	for p in "$@"; do v=$(sed 's/^.*) //' "/proc/$p/stat" 2>/dev/null | cut -d' ' -f12,13); [ -n "$v" ] && t=$((t + $(echo $v | tr ' ' '+'))); done
	echo $t
}
frame() { head -c "$FBN" "$FB" 2>/dev/null | md5sum | cut -c1-8; }

msg0=$(wc -l < "$MSGS" 2>/dev/null || echo 0); dm0=$(dmesg 2>/dev/null | wc -l)
keymap rom "$OPK" >/dev/null 2>&1
( cd "$(dirname "$OPK")" && opkrun "$OPK" > "$D/$ID.log" 2>&1 & p=$!; echo $p > "$D/$ID.pid"; pid record $p 2>/dev/null; wait $p; echo $? > "$D/$ID.exit"; pid erase 2>/dev/null ) &
n=0; while [ ! -s "$D/$ID.pid" ] && [ $n -lt 20 ]; do sleep 0.2; n=$((n + 1)); done
OP=$(cat "$D/$ID.pid" 2>/dev/null)
[ -n "$OP" ] || { echo "ERROR=opkrun did not start"; keymap default >/dev/null 2>&1; exit 4; }

t=0; life=""; alive=1
while [ $t -lt $RUN ]; do
	sleep 1; t=$((t + 1))
	if ! pid_alive "$OP"; then alive=0; life=$t; break; fi
	case $t in 2|4|6|$SU) ks=$(kids_of "$OP"); echo "S$t=$(ticks_of $OP $ks),$(frame)";; esac
	[ $t -eq $SU ] && head -c "$FBN" "$FB" > "$D/$ID.fb" 2>/dev/null
done
[ $alive -eq 1 ] && [ ! -f "$D/$ID.fb" ] && head -c "$FBN" "$FB" > "$D/$ID.fb" 2>/dev/null
stop=none; stop_s=0
if [ $alive -eq 1 ]; then
	ks=$(kids_of "$OP"); echo "KIDS=$(echo $ks | wc -w)"
	stop=term; for p in $ks; do kill -TERM "$p" 2>/dev/null; done; [ -z "$ks" ] && kill -TERM "$OP" 2>/dev/null
	w=0; while [ $w -lt $TW ] && pid_alive "$OP"; do sleep 1; w=$((w + 1)); done
	if pid_alive "$OP"; then
		stop=kill; ks=$(kids_of "$OP"); for p in $ks; do kill -KILL "$p" 2>/dev/null; done; [ -z "$ks" ] && kill -KILL "$OP" 2>/dev/null
		w2=0; while [ $w2 -lt 4 ] && pid_alive "$OP"; do sleep 1; w2=$((w2 + 1)); done
		pid_alive "$OP" && stop=stuck
		w=$((w + w2))
	fi
	stop_s=$w
fi
n=0; while [ ! -f "$D/$ID.exit" ] && [ $n -lt 10 ] && [ "$stop" != stuck ]; do sleep 0.2; n=$((n + 1)); done
# the frontend loop's own clean-up after an app ends
if [ "$stop" != stuck ]; then
	termfix_all >/dev/null 2>&1; keymap default >/dev/null 2>&1; sleep 1
	KD=$(grep keymap "$MSGS" 2>/dev/null | tail -1 | grep -c 'default: LOAD')   # checked now, while the line is fresh (the RAM syslog rotates it out within minutes)
	if grep -q ' /opk ' /proc/mounts 2>/dev/null && ! pid_alive "$OP"; then umount /opk >/dev/null 2>&1; fi
fi
echo "ALIVE_AT_END=$alive"; echo "LIFE_S=$life"; echo "STOP=$stop"; echo "STOP_S=$stop_s"
echo "EXIT=$(cat "$D/$ID.exit" 2>/dev/null || echo -)"
echo "KEYMAP_DEFAULT=${KD:-skipped}"
echo "MOUNT_LEFT=$(grep -c ' /opk ' /proc/mounts 2>/dev/null)"
tail -n +$((msg0 + 1)) "$MSGS" 2>/dev/null | head -n 60 > "$D/$ID.msgs"
dmesg 2>/dev/null | tail -n +$((dm0 + 1)) | head -n 60 > "$D/$ID.dmesg"
echo "NEWMSGS=$(wc -l < "$D/$ID.msgs")"; echo "NEWDMESG=$(wc -l < "$D/$ID.dmesg")"
echo "DONE=1"
