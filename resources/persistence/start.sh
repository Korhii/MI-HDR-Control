#!/system/bin/sh
b=/data/data/mitv.service/files/MIHDRControl
[ -f "$b/enabled" ] || exit 0
if [ -f "$b/bootstrap.pid" ]; then
 pid=$(cat "$b/bootstrap.pid")
 case "$pid" in ''|*[!0-9]*) ;; *)
  if [ "$(cat "$b/bootstrap.boot-id" 2>/dev/null)" = "$(cat /proc/sys/kernel/random/boot_id)" ] && kill -0 "$pid" 2>/dev/null; then
   if [ "$(cat "$b/runtime.pid" 2>/dev/null)" = "$pid" ] && [ "$(cat "$b/daemon-stopped.txt" 2>/dev/null)" = "$(cat /proc/sys/kernel/random/boot_id)" ]; then kill "$pid" 2>/dev/null;else exit 0;fi
  fi;;
 esac
fi
rm -f "$b/stop"
nohup /system/bin/sh "$b/boot.sh" >"$b/bootstrap.log" 2>&1 </dev/null &
echo $! >"$b/bootstrap.pid"
cat /proc/sys/kernel/random/boot_id >"$b/bootstrap.boot-id"
