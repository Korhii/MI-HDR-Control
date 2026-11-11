#!/system/bin/sh
umask 022
b=/data/data/mitv.service/files/MIHDRControl
r=/data/miuilog/misight/MIHDRControl
{
id
echo __run_id=@RUN_ID@
echo __root_ready=1
policy="$r/policy.@RUN_ID@.before"
(sleep 70; [ ! -f "$policy" ] || /system/bin/load_policy "$policy"; /system/bin/setenforce 1; rmmod mi_oemabl 2>/dev/null) >"$r/watchdog.txt" 2>&1 &
watchdog=$!
restore_access() {
 if [ -f "$r/kptr.@RUN_ID@.before" ]; then cat "$r/kptr.@RUN_ID@.before" >/proc/sys/kernel/kptr_restrict; fi
 if [ -f "$policy" ]; then /system/bin/load_policy "$policy"; echo policy_restore_exit=$?; fi
 /system/bin/setenforce 1
 echo restore_setenforce_exit=$?
 kill "$watchdog" 2>/dev/null
 echo __access_restore_done=1
}
trap restore_access EXIT HUP INT TERM
for i in $(seq 1 150); do
 [ "$(cat /sys/fs/selinux/enforce 2>/dev/null)" != 0 ] || break
 sleep .1
done
[ "$(cat /sys/fs/selinux/enforce 2>/dev/null)" = 0 ] || exit 3
cp /sys/fs/selinux/policy "$policy" || exit 4
chmod 600 "$policy"
[ "$(sha256sum /vendor/lib/modules/kdrv_ldm_sys.ko | cut -d ' ' -f1)" = eabc6d525ddd76cfaa9855b137af2df7247bccd4ec7166edef4d0dbfae5db4cd ] || exit 5
cat /proc/sys/kernel/kptr_restrict >"$r/kptr.@RUN_ID@.before"
if [ @OPERATION@ = apply ]; then
 if [ ! -d /sys/module/mi_oemabl ]; then
  cat /proc/sys/kernel/kptr_restrict >"$r/kptr.@RUN_ID@.before"
  printf 0 >/proc/sys/kernel/kptr_restrict
  text=$(cat /sys/module/kdrv_ldm_sys/sections/.text)
  bss=$(cat /sys/module/kdrv_ldm_sys/sections/.bss)
  data=$(cat /sys/module/kdrv_ldm_sys/sections/.data)
  "$b/mi-budget-prepare" "$b/mi-oem-runtime.ko" "$r/prepared.ko" "$text" "$bss" "$data"
  rc=$?;echo prepare_exit=$rc;[ "$rc" = 0 ] || exit 7
  insmod "$r/prepared.ko"
  rc=$?;echo insmod_exit=$rc;rm -f "$r/prepared.ko";[ "$rc" = 0 ] || exit 8
 fi
 echo __module_ready=1
else
 if [ -d /sys/module/mi_oemabl ]; then rmmod mi_oemabl; rc=$?;echo rmmod_exit=$rc;[ "$rc" = 0 ] || exit 12; fi
 echo __module_removed=1
fi
restore_access
trap - EXIT HUP INT TERM
echo __root_done=1
} >"$r/root-proof.txt" 2>&1
