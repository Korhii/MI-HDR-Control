"""Immutable initial dimming backup inside the portable folder, mirrored on-device.

Observed current values are kept separately from immutable vendor defaults. No
vendor partition is ever written: our permanent policy is an owned boot overlay.
"""
from pathlib import Path
from datetime import datetime,timezone
import base64,gzip,hashlib,json,os,re
import permanent
from mi_probe import ROOT

REMOTE=permanent.BASE+'/backup/initial-v1.json'
DRIVER='/vendor/lib/modules/kdrv_ldm_sys.ko'
INIS=['/vendor/tvconfig/bsp/chip/ldm_xiaomi/'+panel+'/ldm.ini' for panel in ('ldm_ptbcn1l','ldm_ptfcn1l','ldm_ptfcn2l')]
INDICES=[7,8,9,10,11,20,22,21,23,24,25,26,27,28,29,30]
SCOPE='本工具涉及的SF/Alpha/DC/Blend/Dynamic、原厂预算与累计ABL路径、调光档位/模式及本工具永久调光；不重置账号、ADB、桌面或未知校准区'

def digest(raw):return hashlib.sha256(raw).hexdigest()

def factory_defaults(raw):
    text=raw.decode('utf-8-sig')
    def value(name):
        match=re.search(r'^\s*'+re.escape(name)+r'\s*=\s*(0[xX][0-9a-fA-F]+|[0-9]+)\s*;',text,re.M)
        if not match:raise ValueError('原厂INI缺少字段 '+name)
        return int(match[1],0) if match[1].lower().startswith('0x') else int(match[1])
    result={}
    for level,suffix in ((1,'_LOW'),(2,'_MID'),(3,'_HIGH')):
        result[str(level)]=dict(sf=[value('u8SFStrength'+('' if i==1 else str(i))+suffix) for i in range(1,6)],
            alpha=[value('u8DynamicAlpha'+str(i)) for i in range(8)],dc=value('u8DCMaxAlpha'+suffix),
            blend=value('u8LDFBlendAlpha'+suffix),dynamic=value('u8DynamicAlphaEn'+suffix))
    return result

def values(config):return [*config['sf'],config['dc'],config['blend'],config['dynamic'],*config['alpha']]

def parse_info(raw):
    if '__info_verified=1' not in raw:raise RuntimeError('OEM控光快照读取未完成：'+raw)
    match=re.search(r'LDM Cus path:(/vendor/tvconfig/bsp/chip/ldm_xiaomi/[^\s]+)',raw)
    ini=match[1].rstrip('/')+'/ldm.ini' if match else ''
    if ini not in INIS:raise ValueError('未知面板初始化路径；未允许写入')
    sf=[int(n,16) for n in re.findall(r'Spetail filter [1-5]:\s*0x([0-9a-fA-F]+)',raw)]
    dc=re.search(r'DC max alpha:\s*0x([0-9a-fA-F]+)',raw);pip=re.search(r'CusBoost:\s*0x([0-9a-fA-F]+)',raw)
    if len(sf)!=5 or not dc or not pip:raise ValueError('OEM控光快照缺少可回读字段')
    return dict(factory_ini=ini,sf=sf,dc=int(dc[1],16),pip_bypass=int(pip[1],16),raw=raw,
        note='系统接口可独立读回SF/DC/CusBoost；Alpha/Blend/Dynamic以原厂INI和写入回执为依据，不冒充完整运行寄存器转储')

def identity(s):
    fields=s.run('shell','getprop ro.serialno; getprop ro.product.device; getprop ro.build.fingerprint; uname -r').strip().splitlines()
    if len(fields)!=4 or not fields[0] or fields[1]!='beekeeper':raise ValueError('无法绑定稳定设备身份；未允许调光写入')
    return dict(zip(('serial','device','fingerprint','kernel'),fields))

def validate(raw,device):
    data=json.loads(raw)
    if data.get('format')!='mi-hdr-initial-backup-v1' or data.get('identity')!=device:raise ValueError('初始备份设备/固件不匹配；不会覆盖')
    files=data['vendor_files'];ini=data['factory_ini']
    if ini not in INIS or set(files)!={DRIVER,ini}:raise ValueError('未知原厂文件范围')
    for name in (DRIVER,ini):
        blob=gzip.decompress(base64.b64decode(files[name]['gzip_base64'],validate=True))
        if digest(blob)!=files[name]['sha256']:raise ValueError('初始备份文件损坏')
    if files[DRIVER]['sha256']!=permanent.DRIVER_SHA:raise ValueError('原始驱动版本不匹配')
    original_ini=gzip.decompress(base64.b64decode(files[ini]['gzip_base64']))
    if data['factory_defaults']!=factory_defaults(original_ini):raise ValueError('原厂默认表与备份INI不一致')
    native=data['initial_snapshot']['native']
    if native['g_video__vid_local_dimming'] not in ('1','2','3') or native['g_video__vid_hdr_tone_mapping_mode'] not in ('0','1','2','5'):
        raise ValueError('初始档位/模式不在此构建支持的范围')
    return data

def remote_digest(s):
    raw=s.job('if [ -f '+REMOTE+' ];then sha256sum '+REMOTE+';else echo backup_absent=1;fi')
    match=re.search(r'(?m)^([0-9a-f]{64})\s',raw)
    if not match and 'backup_absent=1' not in raw:raise RuntimeError('无法核实显示器已有备份；未新建副本')
    return match[1] if match else None

def read_remote(s):
    # Only recover a missing PC canonical copy; normal reconnects compare hashes.
    p=s.folder/'backup-transfer.json';remote=s.remote+'/backup-transfer.json'
    try:
        s.job('cp '+REMOTE+' '+remote)
        s.run('pull',remote,str(p));return p.read_bytes()
    finally:
        p.unlink(missing_ok=True);s.job('rm -f '+remote)

def write_remote(s,raw):
    p=s.folder/'backup-transfer.json';remote=s.remote+'/backup-transfer.json'
    try:
        p.write_bytes(raw);s.run('push',str(p),remote)
        s.job('mkdir -p '+permanent.BASE+'/backup\nchmod 700 '+permanent.BASE+'/backup\n'
            +'test ! -f '+REMOTE+'\ncp '+remote+' '+REMOTE+'.next\nchmod 600 '+REMOTE+'.next\nmv '+REMOTE+'.next '+REMOTE)
    finally:
        p.unlink(missing_ok=True);s.job('rm -f '+remote)

def read_policy():
    path=ROOT/'state/backup-policy.json'
    return validate_policy(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else dict(pc=True,device=False,confirmed=False)

def validate_policy(value):
    if value.get('pc') is not True or type(value.get('device')) is not bool or value.get('confirmed') is not True:
        raise ValueError('必须选择电脑备份；显示器副本可选，不能仅保存在显示器')
    return dict(pc=True,device=value['device'],confirmed=True)

def save_policy(value):
    value=validate_policy(value);path=ROOT/'state/backup-policy.json';path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.next');temporary.write_text(json.dumps(value),encoding='utf-8');temporary.replace(path);return value

def local_inventory():
    return [str(p) for p in (ROOT/'state/device-backups').glob('*/initial-v1.json')]

def read_info(s):
    s.run('push',str(ROOT/'tools/bsp-ldm-snapshot.so'),s.remote+'/ldm-info.so')
    raw=s.job('cp '+s.remote+'/ldm-info.so /data/data/mitv.service/cache/mi-ldm-info.so\n'
        +'if timeout 5 env LD_LIBRARY_PATH=/vendor/lib64:/vendor/lib64/hw:/system/lib64 LD_PRELOAD=/data/data/mitv.service/cache/mi-ldm-info.so /system/bin/app_process /system/bin;then echo info_exit=0;else echo info_exit=$?;fi')
    return parse_info(raw)

def ensure(folder,native,session=None,home=None,policy=None):
    policy=validate_policy(policy or read_policy())
    s=session or permanent.Session(folder);s.firmware();device=identity(s)
    key=digest((device['serial']+'\n'+device['device']).encode())[:24]
    parent=Path(home or ROOT/'state/device-backups')/key
    parent.mkdir(parents=True,exist_ok=True);pc=parent/'initial-v1.json'
    local=pc.read_bytes() if pc.exists() else None;remote_sha=remote_digest(s)
    if local is not None:validate(local,device)
    if local is not None and remote_sha is not None and digest(local)!=remote_sha:raise ValueError('两份初始备份不一致；保留原件，未允许写入')
    raw=local if local is not None else read_remote(s) if remote_sha else None
    if raw is not None:validate(raw,device)
    if raw is None:
        current=read_info(s);ini=current['factory_ini'];files={}
        for i,name in enumerate((DRIVER,ini)):
            target=s.folder/('vendor-'+str(i));staging=s.remote+'/vendor-'+str(i)
            try:
                s.job('cp '+name+' '+staging);s.run('pull',staging,str(target));blob=target.read_bytes()
                files[name]=dict(sha256=digest(blob),gzip_base64=base64.b64encode(gzip.compress(blob,mtime=0)).decode())
            finally:
                target.unlink(missing_ok=True);s.job('rm -f '+staging)
        defaults=factory_defaults(gzip.decompress(base64.b64decode(files[ini]['gzip_base64'])))
        data=dict(format='mi-hdr-initial-backup-v1',created_at=datetime.now(timezone.utc).isoformat(),identity=device,
            initial_snapshot=dict(native=dict(native),observed=current,note='首次受保护接入时的实际值；不是未经修改的原厂证明'),factory_ini=ini,
            factory_defaults=defaults,vendor_files=files,scope=SCOPE,
            provenance='原厂只读vendor驱动与ldm.ini；永久方案是独立启动覆盖，不改写这些原厂默认表')
        raw=json.dumps(data,ensure_ascii=False,indent=2).encode();validate(raw,device)
    if local is None:
        with pc.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    if policy['device'] and remote_sha is None:write_remote(s,raw);remote_sha=remote_digest(s)
    if pc.read_bytes()!=raw or policy['device'] and remote_sha!=digest(raw):raise RuntimeError('所选备份位置读回不一致；未允许写入')
    return dict(ready=True,id=digest(raw),pc_path=str(pc),device_path=REMOTE if remote_sha else None,
        pc_saved=True,device_copy_exists=remote_sha is not None,device_selected=policy['device'],
        notice_pending=not (parent/'notice-ack').exists(),data=validate(raw,device),scope=SCOPE)

def public(backup):return {k:v for k,v in (backup or dict(ready=False)).items() if k!='data'}

def acknowledge(backup):
    if not backup or not backup['ready']:raise ValueError('尚无已验证的初始备份')
    Path(backup['pc_path']).with_name('notice-ack').write_text(backup['id'],encoding='ascii');backup['notice_pending']=False

def restore(backup,folder):
    """Restore owned fields, not a flash/write of vendor or unrelated Android data."""
    s=permanent.Session(folder);s.firmware();data=validate(Path(backup['pc_path']).read_bytes(),identity(s))
    level=data['initial_snapshot']['native']['g_video__vid_local_dimming'];tone=data['initial_snapshot']['native']['g_video__vid_hdr_tone_mapping_mode']
    s.job('test ! -d /sys/module/mi_oemabl\ntest ! -d /sys/module/mi_budget\n'
          +''.join('test "$(sha256sum '+name+' | cut -d " " -f 1)" = '+entry['sha256']+'\n' for name,entry in data['vendor_files'].items()))
    from mi_probe import JAR,native,KEYS
    # A real level transition invokes the untouched OEM per-level initialization.
    current=native('getBatch',s.folder,KEYS)
    if current.get('g_video__vid_hdr_tone_mapping_mode')!=tone:
        import uuid
        tone_receipt='/sdcard/Download/Mimonitor_Toolbox/.mtk_action_'+uuid.uuid4().hex+'.txt'
        raw=s.job('if CLASSPATH='+JAR+' /system/bin/app_process /data/data/mitv.service/cache MIHDRBridge setHdrToneMappingChecked '+tone+' 3 '+str(int(current['g_video__picture_mode']))+' '+tone_receipt+';then echo tone_exit=0;else echo tone_exit=$?;fi\ncat '+tone_receipt)
        if '__complete=1' not in raw or 'fatal=' in raw:raise RuntimeError('色调映射恢复回执未确认：'+raw)
    for value in ('0',level):
        raw=s.job('CLASSPATH='+JAR+' /system/bin/app_process /data/data/mitv.service/cache MIHDRBridge set g_video__vid_local_dimming '+value+' 3')
        if not re.search(r'return:\s*0',raw):raise RuntimeError('原生档位写回未确认：'+raw)
    config=data['factory_defaults'][level]
    s.run('push',str(ROOT/'tools/mi-ldm-snapshot'),s.remote+'/ldm-restore')
    raw=s.job('cp '+s.remote+'/ldm-restore /data/data/mitv.service/cache/mi-ldm-restore\nchmod 700 /data/data/mitv.service/cache/mi-ldm-restore\n/data/data/mitv.service/cache/mi-ldm-restore restore '+' '.join(map(str,values(config))))
    pairs=re.findall(r'written_index=(\d+)\s+written_value=(\d+)',raw)
    if pairs!=list(zip(map(str,INDICES),map(str,values(config)))) or '__ldm_written=1' not in raw:raise RuntimeError('原厂控光写入回执不一致')
    observed=read_info(s)
    if observed['factory_ini']!=data['factory_ini'] or observed['sf']!=config['sf'] or observed['dc']!=config['dc'] or observed['pip_bypass']!=0:raise RuntimeError('原厂控光独立可读字段不一致')
    readback=native('getBatch',s.folder,KEYS)
    if readback.get('g_video__vid_local_dimming')!=level or readback.get('g_video__vid_hdr_tone_mapping_mode')!=tone:raise RuntimeError('初始档位/模式恢复回读不一致')
    # Clear only owned dimming policy; the shared boot APK, launcher and ADB remain.
    s.job('b='+permanent.BASE+'\nrm -f "$b/enabled" "$b/controller.json" "$b/runtime-state.json" "$b/pause-boot"\n'
          +'test ! -f "$b/enabled"\ntest ! -f "$b/controller.json"\necho __factory_dimming_restored=1')
    receipt=dict(verified=True,native=readback,config=config,observed=observed,alpha_validation='原厂档位重新初始化 + 16项写入成功回执；无独立Alpha/Blend/Dynamic回读',backup_id=backup['id'],scope=SCOPE,folder=str(s.folder))
    (s.folder/'restored.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');return receipt
