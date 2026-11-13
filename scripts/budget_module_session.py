"""Temporary owned budget module load/unload; restore policy and diagnostic config before returning."""
from pathlib import Path
from datetime import datetime
import hashlib,sys,time,json
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mi_probe import REMOTE,adb,tv_command
ROOT=Path(__file__).resolve().parents[1]
MODE=sys.argv[1] if len(sys.argv)>1 else ''
if MODE not in ('load','unload'):raise ValueError('load or unload required')
EVENT='961099999' if MODE=='load' else '962099999'
expected='eabc6d525ddd76cfaa9855b137af2df7247bccd4ec7166edef4d0dbfae5db4cd'
if adb('shell','sha256sum /vendor/lib/modules/kdrv_ldm_sys.ko').split()[0]!=expected:raise RuntimeError('Firmware driver mismatch; no write performed')
if not adb('shell','sha256sum /vendor/lib/modules/adaptive_hdr_algo.ko').startswith('a061cd3df4a500965299be2e32c3acd4ac34ed9653e44c8ae9667b17c4e994bf '):raise RuntimeError('HDR firmware mismatch; no write performed')
if ': found' not in adb('shell','service check misight',check=False):raise RuntimeError('MiSight服务未就绪；未加载模块，未修改策略')
from local_asset_paths import budget_module,budget_manifest,firmware_directory
manifest=json.loads(budget_manifest().read_text(encoding='utf-8'))
template=budget_module()
if hashlib.sha256(template.read_bytes()).hexdigest()!=manifest['sha256']:raise RuntimeError('Budget module template mismatch; no write performed')

folder=ROOT/'captures'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-budget-module-session');folder.mkdir()
remote=REMOTE+'/'+folder.name;adb('shell','mkdir -p '+remote)
(ROOT/'state/budget-current-device-job.json').write_text(json.dumps({'remote':remote}),encoding='utf-8')
for local,name in [(ROOT/('tools/event'+EVENT[:3]+'.so'),'event.so'),(ROOT/'tools/mi-service-call-args.so','call-args.so')]:
    adb('push',str(local),remote+'/'+name)
adb('push',str(template),remote+'/mi-oem-runtime.ko')
adb('push',str(ROOT/'tools/mi-budget-prepare'),remote+'/mi-budget-prepare')
adb('push',str(ROOT/'tools/mi-temporary-access'),remote+'/access')
adb('shell',tv_command(['cp',remote+'/access','/data/data/mitv.service/cache/MIResearch-budget-access']))
adb('shell',tv_command(['chmod','755','/data/data/mitv.service/cache/MIResearch-budget-access']))
stock=firmware_directory()
for name in ['event.xml','event_upload.xml']:
    text=(stock/name).read_text(encoding='utf-8')
    if name=='event.xml':
        text=text.replace('</EventRoot>','<Event id="959099999" FaultType="FAULT" FaultLevel="CRITICAL" PrivacyLevel="L1">\n  <Param id="0" name="Research" type="string" len="40"/>\n</Event>\n</EventRoot>')
    else:
        text=text.replace('</Upload>','<Event range1="959099999"><Cmd FaultLevel="GENERAL" PrivacyLevel="L1" run="/system/bin/sh /data/miuilog/misight/MIResearch20261106/id.sh" output="MIResearch-id.log" option="block=90"/></Event>\n</Upload>')
    text=text.replace('959099999',EVENT)
    (folder/name).write_text(text,encoding='utf-8',newline='\n')
    adb('push',str(folder/name),remote+'/'+name)
script=folder/'identity.sh'
script.write_text('''{
set -u
base=/data/miuilog/misight/MIResearch20261106
cfg=/data/miuilog/misight/config/update1
before=$(getprop persist.sys.misight.cfg)
echo original_cfg=$before
if [ -n "$(ls -A "$cfg")" ]; then echo aborted_nonempty_config=1;exit 2;fi
mkdir -p "$base"
rm -f "$base/proof.txt"
cp REMOTE/call-args.so /data/data/mitv.service/cache/MIResearch-call-args.so
update_config() {
  ( export LD_PRELOAD=/data/data/mitv.service/cache/MIResearch-call-args.so
    exec -a com.miui.misightservice /system/bin/service call misight 4 s16 "$1" )
}
cat >"$base/id.sh" <<'PROBE'
umask 022
{
id
echo __run_id=REMOTE
echo __root_ready=1
keep_budget=0
(sleep 90; rmmod mi_oemabl 2>/dev/null; rmmod mi_report 2>/dev/null; if [ -f /data/miuilog/misight/MIResearch20261106/kptr-before ]; then cat /data/miuilog/misight/MIResearch20261106/kptr-before >/proc/sys/kernel/kptr_restrict; fi; /system/bin/setenforce 1; echo watchdog_restore_exit=$?) >/data/miuilog/misight/MIResearch20261106/watchdog.txt 2>&1 &
watchdog=$!
restore_access() {
 if [ "$keep_budget" = 0 ] && [ -d /sys/module/mi_oemabl ]; then rmmod mi_oemabl; fi
 if [ -d /sys/module/mi_report ]; then rmmod mi_report; fi
 if [ -f /data/miuilog/misight/MIResearch20261106/kptr-before ]; then cat /data/miuilog/misight/MIResearch20261106/kptr-before >/proc/sys/kernel/kptr_restrict; fi
 /system/bin/setenforce 1
 echo restore_setenforce_exit=$?
 kill "$watchdog" 2>/dev/null
 echo __access_restore_done=1
}
trap restore_access EXIT HUP INT TERM
for i in $(seq 1 100); do
 if [ "$(cat /sys/fs/selinux/enforce 2>/dev/null)" = 0 ]; then break; fi
 sleep 0.1
done
if [ "$(cat /sys/fs/selinux/enforce 2>/dev/null)" != 0 ]; then echo access_not_activated=1; exit 3; fi
echo __temporary_access=1
cat /proc/self/attr/current
cat /proc/sys/kernel/modules_disabled
cat /proc/sys/kernel/kptr_restrict >/data/miuilog/misight/MIResearch20261106/kptr-before
printf 0 >/proc/sys/kernel/kptr_restrict
echo kptr_restrict_current=$(cat /proc/sys/kernel/kptr_restrict)
driver_text=$(cat /sys/module/kdrv_ldm_sys/sections/.text)
driver_bss=$(cat /sys/module/kdrv_ldm_sys/sections/.bss)
driver_data=$(cat /sys/module/kdrv_ldm_sys/sections/.data)
hdr_data=$(cat /sys/module/adaptive_hdr_algo/sections/.data)
echo driver_text=$driver_text driver_bss=$driver_bss driver_data=$driver_data
base=/data/miuilog/misight/MIResearch20261106
if [ MODULE_ACTION = load ]; then
 if [ -d /sys/module/mi_oemabl ]; then rmmod mi_oemabl || exit 16;fi
 cp REMOTE/mi-oem-runtime.ko "$base/mi-oem-runtime.ko"
 if [ "$(sha256sum "$base/mi-oem-runtime.ko" | cut -d ' ' -f1)" != TEMPLATE_SHA ]; then echo aborted_template_changed=1;exit 10;fi
 cp REMOTE/mi-budget-prepare "$base/mi-budget-prepare"
 chmod 700 "$base/mi-budget-prepare"
 prepared="$base/PREPARED_NAME"
 "$base/mi-budget-prepare" "$base/mi-oem-runtime.ko" "$prepared" "$driver_text" "$driver_bss" "$driver_data" "$hdr_data"
 rc=$?;echo runtime_prepare_exit=$rc
 [ "$rc" = 0 ] || exit 11
 insmod "$prepared"
 rc=$?;echo runtime_insmod_exit=$rc
 rm -f "$prepared"
 [ "$rc" = 0 ] || exit 14
 keep_budget=1
 echo __module_loaded=1
else
 rmmod mi_oemabl
 rc=$?;echo runtime_rmmod_exit=$rc
 [ "$rc" = 0 ] || exit 15
 echo __module_unloaded=1
fi
echo __budget_trial_done=1

restore_access
trap - EXIT HUP INT TERM
echo MIResearch_identity_complete=1
} > /data/miuilog/misight/MIResearch20261106/proof.txt 2>&1
PROBE
chmod 0770 "$base"
chmod 0644 "$base/id.sh"
restore() {
  rm -f "$cfg/event.xml" "$cfg/event_upload.xml"
  if [ "$before" = 1 ]; then previous=update1;else previous=update0;fi
  update_config "$previous"
  setprop persist.sys.misight.cfg "$before"
  echo restored_cfg=$(getprop persist.sys.misight.cfg)
  echo __restore_complete=1
} >>REMOTE/result.txt 2>&1
trap restore EXIT HUP INT TERM
cp REMOTE/event.xml "$cfg/event.xml"
cp REMOTE/event_upload.xml "$cfg/event_upload.xml"
touch -d "@$(( $(date +%s) + 315360000 ))" "$cfg/event.xml" "$cfg/event_upload.xml"
ls -l "$cfg/event.xml" "$cfg/event_upload.xml"
update_config update1
echo active_cfg=$(getprop persist.sys.misight.cfg)
cp REMOTE/event.so /data/data/mitv.service/cache/MIResearch-event.so
timeout 8 env LD_LIBRARY_PATH=/system_ext/lib64:/system/lib64:/vendor/lib64 LD_PRELOAD=/data/data/mitv.service/cache/MIResearch-event.so /system/bin/app_process /system/bin
for i in $(seq 1 600); do if grep -q MIResearch_identity_complete "$base/proof.txt"; then break; fi; sleep 0.1; done
cat "$base/proof.txt"
echo __probe_complete=1
restore
trap - EXIT HUP INT TERM
} >REMOTE/result.txt 2>&1
'''.replace('REMOTE',remote).replace('MODULE_ACTION',MODE).replace('TEMPLATE_SHA',manifest['sha256']).replace('PREPARED_NAME','prepared-'+folder.name+'.ko'),encoding='utf-8',newline='\n')
adb('push',str(script),remote+'/identity.sh');adb('shell',tv_command(['sh',remote+'/identity.sh']))
apply_output=''
deadline=time.monotonic()+18
while time.monotonic()<deadline:
    proof=adb('shell',tv_command(['cp','/data/miuilog/misight/MIResearch20261106/proof.txt',remote+'/proof.txt']),check=False)
    proof=adb('shell','cat '+remote+'/proof.txt',check=False)
    if '__run_id='+remote in proof and '__root_ready=1' in proof: break
    time.sleep(.1)
else: raise RuntimeError('Root restore worker did not become ready; no write performed')
apply_script=folder/'apply.sh'
apply_script.write_text('{ /data/data/mitv.service/cache/MIResearch-budget-access --apply; echo apply_exit=$?; echo __apply_done=1; } >'+remote+'/apply.txt 2>&1\n',encoding='utf-8',newline='\n')
adb('push',str(apply_script),remote+'/apply.sh');adb('shell',tv_command(['sh',remote+'/apply.sh']))
deadline=time.monotonic()+50
while time.monotonic()<deadline:
    apply_output=adb('shell','cat '+remote+'/apply.txt',check=False)
    proof=adb('shell',tv_command(['cp','/data/miuilog/misight/MIResearch20261106/proof.txt',remote+'/proof.txt']),check=False)
    proof=adb('shell','cat '+remote+'/proof.txt',check=False)
    if '__run_id='+remote in proof and '__budget_trial_done=1' in proof and '__access_restore_done=1' in proof and '__apply_done=1' in apply_output:break
    time.sleep(.1)
(folder/'apply-result.txt').write_text(apply_output,encoding='utf-8')
(folder/'root-proof.txt').write_text(proof,encoding='utf-8')
print(apply_output);print(proof)
deadline=time.monotonic()+18
while time.monotonic()<deadline:
    output=adb('shell','cat '+remote+'/result.txt',check=False)
    if ('__run_id='+remote in output and '__restore_complete=1' in output) or 'aborted_nonempty_config=1' in output:break
    time.sleep(.1)
(folder/'result.txt').write_text(output,encoding='utf-8')
logs='Current-run proof and phase-specific kernel messages are recorded above.'
(folder/'service-log.txt').write_text(logs,encoding='utf-8')
print(folder);print(output);print('FINAL_SELINUX='+adb('shell','getenforce').strip())

if "__access_restore_done=1" not in proof or "__restore_complete=1" not in output:raise RuntimeError("Restore receipts missing; inspect capture")
if ("__module_loaded=1" if MODE=="load" else "__module_unloaded=1") not in proof:raise RuntimeError("Module operation not confirmed")
if adb("shell","getenforce").strip()!="Enforcing":raise RuntimeError("Policy restore not confirmed")
