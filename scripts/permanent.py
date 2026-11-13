"""Own monitor-local boot component and saved configuration; never changes ADB startup."""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,re,sys,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mi_probe import ROOT,REMOTE,adb,tv_command
from local_asset_paths import budget_module,persistence_xml

PACKAGE='com.example.autoreboot'
BASE='/data/data/mitv.service/files/MIHDRControl'
DRIVER_SHA='eabc6d525ddd76cfaa9855b137af2df7247bccd4ec7166edef4d0dbfae5db4cd'


class Session:
    def __init__(self,folder=None):
        self.folder=Path(folder) if folder else ROOT/'captures'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-permanent')
        self.folder.mkdir(parents=True,exist_ok=True);self.rows=[];self.sequence=0
        channel=self.folder/'channel.json'
        if channel.exists():self.remote=json.loads(channel.read_text(encoding='utf-8'))['remote']
        else:
            self.remote=REMOTE+'/persistent_'+uuid.uuid4().hex
            self.run('shell','mkdir -p '+self.remote)
            channel.write_text(json.dumps({'remote':self.remote}),encoding='utf-8')

    def run(self,*args,check=True):
        p=adb(*args,raw=True,check=False)
        row=dict(command=args,stdout=p.stdout.decode(errors='replace'),stderr=p.stderr.decode(errors='replace'),exit_status=p.returncode)
        self.rows.append(row);(self.folder/'execution.json').write_text(json.dumps(self.rows,ensure_ascii=False,indent=2),encoding='utf-8')
        if check and p.returncode:raise RuntimeError(row)
        return row['stdout']

    def job(self,text):
        self.sequence+=1;nonce=uuid.uuid4().hex
        p=self.folder/'job.sh';p.write_text('( set -eu\n'+text+'\necho __job_done='+nonce+'\n) >'+self.remote+'/receipt.txt 2>&1\n',encoding='utf-8',newline='\n')
        self.run('push',str(p),self.remote+'/job.sh');self.run('shell',tv_command(['sh',self.remote+'/job.sh']))
        end=time.monotonic()+8;raw=''
        while time.monotonic()<end:
            raw=self.run('shell','cat '+self.remote+'/receipt.txt',check=False)
            if '__job_done='+nonce in raw:
                (self.folder/'receipt.txt').write_text(raw,encoding='utf-8');return raw
            time.sleep(.1)
        raise RuntimeError('没有本次设备任务回执：'+raw)

    def status(self):
        package=self.run('shell','pm path '+PACKAGE,check=False).strip()
        apk=package.removeprefix('package:') if package.startswith('package:') else ''
        if apk and not re.fullmatch(r'/data/app/[A-Za-z0-9_~+/=.\-]+/base\.apk',apk):raise ValueError('Unexpected installed package path')
        raw=self.job('b='+BASE+'\n'
            +'echo boot_id=$(cat /proc/sys/kernel/random/boot_id)\necho now=$(date +%s)\n'
            +'if [ -f "$b/enabled" ]; then echo enabled=1;else echo enabled=0;fi\n'
            +'if [ -d /sys/module/mi_oemabl ]; then echo module_loaded=1;else echo module_loaded=0;fi\n'
            +'if [ "$(cat "$b/bootstrap.boot-id" 2>/dev/null)" = "$(cat /proc/sys/kernel/random/boot_id)" ] && [ -f "$b/bootstrap.pid" ] && kill -0 "$(cat "$b/bootstrap.pid")" 2>/dev/null; then echo bootstrap_running=1;else echo bootstrap_running=0;fi\n'
            +('sha256sum '+apk+'\n' if apk else '')
            +'if [ -f "$b/runtime-state.json" ]; then cat "$b/runtime-state.json";echo;fi\n'
            +'if [ -f "$b/daemon-stopped.txt" ]; then echo stopped_boot=$(cat "$b/daemon-stopped.txt");fi\n'
            +'getenforce')
        fields=dict(l.split('=',1) for l in raw.splitlines() if '=' in l and not l.startswith('{'))
        local=next((json.loads(l) for l in raw.splitlines() if l.startswith('{')),None)
        expected=hashlib.sha256((ROOT/'tools/mi-hdr-persistence.apk').read_bytes()).hexdigest()
        owned=bool(apk and any(l.startswith(expected+' ') for l in raw.splitlines()))
        fresh=bool(local and local.get('boot_id')==fields.get('boot_id') and -2<=int(fields['now'])-local.get('heartbeat_ms',0)/1000<=6)
        stopped=fields.get('stopped_boot')==fields.get('boot_id')
        result=dict(installed=bool(apk),owned=owned,enabled=fields.get('enabled')=='1',module_loaded=fields.get('module_loaded')=='1',
                    current_boot=fields.get('boot_id'),running=fresh and not stopped,bootstrap_running=fields.get('bootstrap_running')=='1',paused=fresh and local.get('state')=='paused-this-boot',
                    local=local,selinux='Enforcing' if 'Enforcing' in raw else 'not-confirmed',captured_at=datetime.now().isoformat(timespec='seconds'),folder=str(self.folder))
        (self.folder/'status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result

    def firmware(self):
        identity=self.run('shell','getprop ro.product.device; uname -r')
        if 'beekeeper' not in identity or '5.15.148-android14-11-g37010446f523' not in identity:raise ValueError('不支持的设备/内核；未写入')
        if not self.run('shell','sha256sum /vendor/lib/modules/kdrv_ldm_sys.ko').startswith(DRIVER_SHA+' '):raise ValueError('驱动版本不匹配；未写入')

    def stop_owner(self,disable=False):
        self.job('b='+BASE+'\nmkdir -p "$b"\ntouch "$b/stop"\n'+('rm -f "$b/enabled"\n' if disable else ''))
        end=time.monotonic()+75
        while time.monotonic()<end:
            state=self.status()
            if not state['running'] and not state['bootstrap_running']:return state
            time.sleep(.3)
        raise RuntimeError('本机方案尚未停止；未覆盖运行中的控制器')


def validate_config(data):
    sys.path.insert(0,str(ROOT/'lab'))
    from features import validate_pattern,validate_calibration
    from server import validate
    from native_abl import validate as validate_abl
    if data.get('format')!='mi-hdr-controller-v1':raise ValueError('不支持的控制器配置')
    if type(data['selected_level']) is not int or data['selected_level'] not in (1,2,3):raise ValueError('档位错误')
    if type(data['selected_tone']) is not int or data['selected_tone'] not in (5,1,0,2):raise ValueError('模式错误')
    keys={f'{l}:{t}' for l in (1,2,3) for t in (5,1,0,2)}
    if set(data['profiles'])!=keys:raise ValueError('需要12组完整配置')
    for p in data['profiles'].values():
        validate(p['config']);validate_abl(p['native_abl'],True)
        if type(p['software_abl']) is not bool or type(p['budget']) is not int or not 0<=p['budget']<=86:raise ValueError('预算或ABL开关错误')
        if type(p.get('factory_budget',False)) is not bool:raise ValueError('原厂预算标记错误')
        if 'pattern' in p:validate_pattern(p['pattern'])
    validate_pattern(data['pattern']);validate_calibration(data['calibration']);return data


def status(folder=None):return Session(folder).status()


def pause(folder=None):
    s=Session(folder);before=s.status()
    if not before['installed'] or not before['owned']:return before
    s.job('cat /proc/sys/kernel/random/boot_id >'+BASE+'/pause-boot')
    end=time.monotonic()+8
    while time.monotonic()<end:
        out=s.status()
        if out['paused'] or not out['running']:return out
        time.sleep(.2)
    raise RuntimeError('尚未收到本机方案暂停状态；没有开始PC写入')


def disable_tuning(folder=None):
    """Disable only the owned HDR autostart/lease, retaining ADB components."""
    s=Session(folder);before=s.status()
    if before['installed'] and not before['owned']:raise ValueError('永久调光组件不属于本工具，未停止')
    if before['owned']:return s.stop_owner(disable=True)
    return before


def write_capability(model):
    accepted=json.loads((ROOT/'resources/persistence/acceptance.json').read_text(encoding='utf-8'))
    models=json.loads((ROOT/'resources/models/registry.json').read_text(encoding='utf-8'))['models']
    if model not in models or accepted.get('adapter')!='mi_oemabl':raise ValueError('不支持的机型或永久适配器')
    components=accepted.get('component_sha256',{})
    matches=bool(components) and all(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==h for n,h in components.items() for path in [budget_module() if n=='tools/mi-oem-runtime.ko' else ROOT/n])
    verified=matches and accepted.get('boot_verified') is True and accepted.get('model_id','32u-2026')==model
    return dict(enabled=True,boot_verified=verified,experimental=not verified,model_id=model)

def authorize_install(config,experimental_ack=False):
    capability=write_capability(config.get('model_id','32u-2026'))
    if capability['experimental'] and experimental_ack is not True:raise ValueError('永久写入已开放，但本机型尚未完成开机验收；请确认实验性永久方案提示')
    return capability

def install(config,folder=None,*,experimental_ack=False):
    capability=authorize_install(config,experimental_ack)
    config=validate_config(config)
    sys.path.insert(0,str(ROOT/'lab'))
    from hdr_mapping import attach_profiles
    config=attach_profiles(config);s=Session(folder);s.firmware();before=s.status()
    import device_backup
    info=device_backup.read_info(s)
    model=json.loads((ROOT/'resources/models/registry.json').read_text(encoding='utf-8'))['models'][capability['model_id']]
    if info['factory_ini'] not in [v['ldm_ini'] for v in model['variants'].values()]:raise ValueError('永久方案机型与实际活动屏型不一致；未写入')
    if before['installed'] and not before['owned']:raise ValueError('启动槽位已由其他APK占用，未覆盖')
    if before['owned']:s.stop_owner()
    resources=ROOT/'resources/persistence'
    files=[(p,p.name) for p in resources.iterdir() if p.is_file() and p.suffix=='.sh']
    files += [(persistence_xml(n),n) for n in ('event.xml','event_upload.xml')]
    tools=['MIHDRRuntime.jar','libmi-persistence.so','mi-hdr-persistence.apk','mi-ldm-lab','mi-oem-runtime.ko','mi-budget-prepare','mi-temporary-access','mi-service-call-args.so']
    tools+=['event'+n+'.so' for n in ('961','962','963','964','966','967')]
    files += [(budget_module() if n=='mi-oem-runtime.ko' else ROOT/'tools'/n,n) for n in tools if n!='mi-hdr-persistence.apk']
    data=json.dumps(config,ensure_ascii=False,indent=2);p=s.folder/'controller.json';p.write_text(data,encoding='utf-8',newline='\n');files.append((p,'controller.json'))
    for p,name in files:s.run('push',str(p),s.remote+'/'+name)
    s.job('b='+BASE+'\nmkdir -p "$b"\nchmod 700 "$b"\n'
          +''.join('cp '+s.remote+'/'+n+' "$b/'+n+'.next"\nmv "$b/'+n+'.next" "$b/'+n+'"\n' for _,n in files)
          +'chmod 700 "$b/start.sh" "$b/boot.sh" "$b/boot-root.sh" "$b/mi-ldm-lab" "$b/mi-budget-prepare" "$b/mi-temporary-access"\n'
          +'rm -f "$b/stop" "$b/pause-boot"\ntouch "$b/enabled"')
    if not before['installed']:s.run('install','-r',str(ROOT/'tools/mi-hdr-persistence.apk'))
    s.run('shell','am start -W -n '+PACKAGE+'/.MainActivity --ez background true')
    sha=hashlib.sha256(data.encode()).hexdigest();end=time.monotonic()+400
    while time.monotonic()<end:
        out=s.status();local=out.get('local') or {}
        if out['owned'] and out['running'] and local.get('config_sha256')==sha and local.get('state') in ('applied','waiting-HDR-input'):
            out['saved_config_sha256']=sha;out['write_capability']=capability;return out
        if local.get('boot_id')==out['current_boot'] and local.get('state')=='error':raise RuntimeError(local['error'])
        time.sleep(.7)
    raise RuntimeError('本机保存/启动未取得新心跳；未宣称永久成功。请读取 bootstrap.log')


def remove(folder=None):
    s=Session(folder);before=s.status()
    if before['installed'] and not before['owned']:raise ValueError('槽位APK不属于当前工具，未卸载')
    stopped=s.stop_owner(disable=True)
    if stopped['module_loaded']:
        s.firmware()
        s.job('nohup /system/bin/sh '+BASE+'/boot.sh remove >'+s.remote+'/remove.txt 2>&1 </dev/null &')
        end=time.monotonic()+75
        while time.monotonic()<end:
            raw=s.run('shell','cat '+s.remote+'/remove.txt',check=False)
            if '__remove_done=1' in raw:break
            time.sleep(.5)
        else:raise RuntimeError('未取得卸载模块回执；方案已禁用，但需核对原指令恢复')
    if before['installed']:s.run('uninstall',PACKAGE)
    out=s.status()
    if out['installed'] or out['module_loaded'] or out['running']:raise RuntimeError('移除后状态不匹配：'+str(out))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['status','install','remove','pause']);p.add_argument('--config',type=Path)
    p.add_argument('--ack-experimental',action='store_true',help='Confirm experimental monitor-local persistence; does not mark reboot verification passed')
    a=p.parse_args()
    if a.action=='install':
        if not a.config:p.error('install requires --config')
        result=install(json.loads(a.config.read_text(encoding='utf-8')),experimental_ack=a.ack_experimental)
    else:result=globals()[a.action]()
    print(json.dumps(result,ensure_ascii=False,indent=2))
