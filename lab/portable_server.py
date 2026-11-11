"""Portable front end; uses the already verified LDM worker, not a web mock-up."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0,str(Path(__file__).resolve().parent))
import server as lab
from features import PATTERN,CALIBRATION,validate_pattern,write_pattern,read_pattern_check,replace_pattern_file,parse_sensors,SENSOR_SCRIPT,validate_calibration,android_sensors
from mi_probe import connection,deploy
import budget
import adb_autostart
import permanent
import device_backup
from adb_discovery import discover
from portable_paths import available_adb_port
from auto_fit import validate_plan,validate_preview
import model_worker
import device_models
from native_abl import DEFAULT as ABL_DEFAULT,validate as validate_abl,packet as abl_packet
from desktop_lifecycle import DEFAULT_UI,preferences,ManagedServer,watch_owner

ROOT=lab.ROOT
TONES={5:'HGiG',1:'明亮',0:'层次',2:'动态'}
RISK_BUDGET=41  # Short-run project boundary, NOT a certified electrical/thermal limit.

def maximum_budget(config,include_disabled=False):
    return config.get('budget',0)


def device_profile(level,pattern=None):
    return dict(config=lab.validate(lab.STOCK_BY_LEVEL[level]),software_abl=True,budget=24,native_abl=validate_abl(ABL_DEFAULT),factory_budget=True,pattern=validate_pattern(pattern or PATTERN))


class PortableBridge(lab.Bridge):
    def __init__(self):
        self.pattern_lock=threading.RLock()
        self.config_lock=threading.RLock()
        self.adb_owned=False
        self.adb_discovery={"searching":False,"message":"先点自动寻找；未找到时可在高级连接填写显示器地址"}
        self.adb_port=None
        self.needs_restore=False
        self.debug_phase='idle'
        self.default_restoration=None
        self.initial_backup=None
        self.model_id='32u-2026'
        self.model_confirmed=False
        self.model_detection=device_models.detect()
        self.model_monitor=None
        self.device_model={'verified':False,'model_id':None}
        self.backup_policy=device_backup.read_policy()
        self.auto_plans={}
        self.auto_previews={}
        self.factory_budget=False
        self.live_debug=False
        self.risk_unlocked=False
        self.operation_results={}
        self.last_operation=None
        self.adb_read_at=0
        self.nit_references=[dict(CALIBRATION)]
        self.ui_preferences=dict(DEFAULT_UI)
        self.config_saved_at=''
        self.runtime_loaded_by_pc=False
        self.shutdown_started=False
        self.pattern_config=dict(PATTERN)
        self.pattern_sequence=0
        self.software_abl=True;self.halo_realtime=False
        self.tone=5
        self.calibration=dict(CALIBRATION)
        self.sensors={'sensors':[],'complete':False,'note':'尚未读取设备；不显示模拟数值。'}
        self.telemetry={'status':'尚未连接数字输出读取模块','raw':None}
        self.runtime_loaded=False
        self.budget_active=False
        self.budget_value=24
        self.budget_sample_at=0
        self.native_poll_at=0
        self.native_abl=validate_abl(ABL_DEFAULT)
        self.profile_bank={f'{level}:{tone}':device_profile(level)
                           for level in lab.BACKLIGHT_LEVELS for tone in TONES}
        self.factory_budget=self.profile_bank['3:5']['factory_budget']
        self.pattern_check={}
        self.pattern_started=0
        self.adb_boot={'status':'not-read','enabled':None,'reference_reboot_passed':True,'stable_persistence_verified':False}
        self.persistence={'installed':False,'owned':False,'enabled':False,'running':False,'paused':False,'local':None,'status':'not-read'}
        self._ready=False
        super().__init__()
        self._ready=True
        self.profile_bank['3:5']['config']=lab.validate(self.draft)
        saved=ROOT/'profiles/controller.json'
        if saved.exists():
            data=json.loads(saved.read_text(encoding='utf-8'));self.model_id=data.get('model_id','32u-2026')
            self.install_model_defaults();self.import_config(data)

    def install_model_defaults(self):
        device_models.activate(self.model_id)
        lab.STOCK_BY_LEVEL={level:lab.validate(device_models.defaults(level,self.model_id)) for level in (1,2,3)}
        lab.STOCK=lab.STOCK_BY_LEVEL[3]

    def select_model(self,data):
        if self.state['connected'] or self.active or self.budget_active:raise ValueError('先关闭实时调试并断开ADB，再切换机型')
        key=data['model_id']
        if key not in device_models.registry():raise ValueError('未知机型')
        monitor=next((r for r in self.model_detection['monitors'] if r['instance']==data.get('monitor')),None)
        offline=data.get('offline') is True
        if not offline and (not monitor or monitor['model_id']!=key):raise ValueError('所选机型与侦测结果不一致，请重新侦测；未知机型只能先离线查看')
        self.write_configuration()
        self.model_id=key;self.model_confirmed=True;self.model_monitor=monitor;self.device_model={'verified':False,'model_id':None}
        self.initial_backup=None;self.install_model_defaults()
        self.backlight_presets={str(n):lab.validate(lab.STOCK_BY_LEVEL[n]) for n in lab.BACKLIGHT_LEVELS}
        self.profile_bank={f'{level}:{tone}':device_profile(level) for level in (1,2,3) for tone in TONES}
        self.backlight_level=3;self.tone=5;self.pattern_config=dict(PATTERN);self.budget_value=24;self.factory_budget=True;self.native_abl=validate_abl(ABL_DEFAULT);self.software_abl=True;self.auto_plans={};self.auto_previews={}
        self.calibration=dict(CALIBRATION);self.nit_references=[]
        if key=='27u-2026':self.calibration['source']='32寸旧参考占位，非27寸标定，不用于27寸预测曲线；27寸曲线使用10000nit PQ截图表。'
        path=ROOT/'profiles/models'/self.model_id/'controller.json'
        if path.exists():self.import_config(json.loads(path.read_text(encoding='utf-8')))
        else:self.save_draft(lab.STOCK_BY_LEVEL[3])
        self.state['config']=self.draft;self.operation_results={};self.last_operation=None
        self.save_configuration()

    def verify_device_model(self):
        session=permanent.Session(self.folder/'model-verification');session.firmware()
        info=device_backup.read_info(session);identity=device_models.panel_identity(info)
        matched=identity['verified'] and identity['model_id']==self.model_id
        self.device_model={**identity,'verified':matched,'factory_ini':info['factory_ini'],'expected':self.model_id}
        if not matched:
            raise ValueError('ADB活动屏型与所选机型不符；未允许调光写入：'+info['factory_ini'])
        self.device_model['note']='型号由原厂活动屏型复核；27寸调光关系尚未实机验证' if self.model_id=='27u-2026' else '型号由原厂活动屏型复核'


    def save_draft(self,c):
        super().save_draft(c)
        if self._ready:
            key=f'{self.backlight_level}:{self.tone}'
            self.profile_bank[key]={**self.profile_bank.get(key,{}),'config':lab.validate(c),'software_abl':self.software_abl,'budget':self.budget_value,'native_abl':validate_abl(self.native_abl),'factory_budget':self.factory_budget,'pattern':validate_pattern(self.pattern_config)}

    def current_brightness(self):
        raw=self.telemetry.get('raw')
        empty=dict(nits=None,raw=raw,kind='参考等效估算，非亮度计实测')
        if not self.state['pattern']:return dict(empty,note='请启动当前HDR图样')
        if not self.state['connected'] or raw is None or self.telemetry.get('status')!='live-driver':return dict(empty,raw=None,note='等待当前驱动采样；不显示旧数值')
        level=int(self.telemetry.get('level',self.backlight_level));tone=int(self.state['native'].get('g_video__vid_hdr_tone_mapping_mode',self.tone))
        area=self.pattern_check.get('actual_area_percent',self.pattern_config['area_percent'])
        factory_path=level==3 and getattr(self,'factory_budget',False) and not self.native_abl['enabled'] and self.telemetry.get('budget_used',24) in (24,'24')
        result=model_worker.current_estimate(model_id=self.model_id,raw=raw,level=level,area=area,input_nits=self.pattern_config['input_nits'],tone=tone,config=self.state.get('config',lab.STOCK_BY_LEVEL[level]),raw_kind='global-aw',factory_path=factory_path,budget_value=self.telemetry.get('budget_used',self.budget_value))
        gain=self.telemetry.get('gain_used',65535)
        if result.get('nits') is not None and gain!=65535:
            result['nits']=round(result['nits']*gain/65535,1);result['note']+='；已乘本轮实际ABL系数G_prev'
        result['estimate_quality']='estimated'
        folder=getattr(self,'pattern_dir',None)
        if folder and (folder/'presentation.json').exists():
            presentation=read_pattern_check(folder/'presentation.json')
            fresh=abs(time.time()*1000-presentation.get('wall_time_ms',0))<3000
            if not fresh or presentation.get('sequence')!=getattr(self,'pattern_sequence',None) or not presentation.get('visible') or presentation.get('occluded'):
                reason='画面有遮挡，保留参考估算' if presentation.get('occluded') else '图样状态待更新，保留参考估算'
                result.update(estimate_quality='mixed' if presentation.get('occluded') else 'pending',presentation=presentation)
                result['note']+='；'+reason
        if self.pattern_config['mode']=='windowed':result['note']+='；窗口化受桌面影响'
        if self.pattern_config['rows']*self.pattern_config['cols']>1:result['note']+='；多窗/星点不是单窗标定条件'
        if self.pattern_config['label'] and area<1:result['note']+='；标签也会影响小窗统计'
        return {**empty,**result,'raw':raw}

    def snapshot(self):
        data=super().snapshot()
        brightness=self.current_brightness()
        valid_context=brightness['nits'] is not None
        context_area=self.pattern_check.get('actual_area_percent',-1) if valid_context else -1
        accepted=ROOT/'resources/persistence/acceptance.json'
        boot_verified=permanent.write_capability(self.model_id)['boot_verified']
        operations=json.loads(json.dumps(self.operation_results))
        for record in operations.values():
            if record['status']=='waiting-ack' and self.ack_sequence>=record['sequence']:
                record.update(status='applied',message='设备执行回执已确认')
        data.update(app='mi-hdr-control',version=json.loads((ROOT/'release-meta.json').read_text('utf-8'))['version'],instance_root=str(ROOT),connection=connection(),
                    adb_discovery=self.adb_discovery,debug_phase=self.debug_phase,default_restoration=self.default_restoration,model_id=self.model_id,model_confirmed=self.model_confirmed,model_detection=self.model_detection,model_spec=device_models.spec(self.model_id),model_monitor=self.model_monitor,device_model=self.device_model,initial_backup=device_backup.public(self.initial_backup),backup_policy=self.backup_policy,fit_progress=model_worker.progress(),backup_inventory=device_backup.local_inventory(),
                    auto_plan=self.auto_plans.get(f'{self.backlight_level}:{self.tone}'),
                    auto_preview=self.auto_previews.get(f'{self.backlight_level}:{self.tone}'),profile_key=f'{self.backlight_level}:{self.tone}',factory_budget=self.factory_budget,current_brightness=brightness,
                    tuning_context=dict(hdr_input=lab.hdr_input(self.state['native']) if self.state['connected'] else None,backlight=self.state['native'].get('g_disp__disp_back_light')),live_debug=self.live_debug,risk_unlocked=self.risk_unlocked,risk_budget=RISK_BUDGET,
                    operation_results=operations,last_operation=operations.get(self.last_operation),
                    adb_age_seconds=round(time.monotonic()-self.adb_read_at,1) if self.adb_read_at else None,
                    pattern_config=self.pattern_config,pattern_check=self.pattern_check,sensors=self.sensors,
                    ui_preferences=self.ui_preferences,config_saved_at=self.config_saved_at,nit_references=self.nit_references,
                    desktop={'owned':bool(os.environ.get('MI_DESKTOP_OWNER_PID')),'auto_connect_allowed':os.environ.get('MI_CONTROL_NO_AUTOCONNECT')!='1'},
                    halo_realtime=bool(self.live_debug and self.halo_realtime and self.active and self.active.get('mode')=='live'),software_abl=self.software_abl,tone=self.tone,tones=TONES,telemetry=self.telemetry,
                    calibration=self.calibration,configuration=self.export_config(),
                    runtime={'loaded':self.runtime_loaded,'active':self.budget_active,'budget':self.budget_value,'timeout_seconds':10},
                    native_abl=self.native_abl,
                    adb_boot=self.adb_boot,
                    persistence=self.persistence,permanent_boot_verified=boot_verified,permanent_capability=permanent.write_capability(self.model_id),
                    estimate=dict(setting_nits=None,reading_nits=brightness['nits'],calibrated_context=valid_context,kind=brightness['kind'],source=brightness['note']),
                    nit_context=dict(valid=bool(valid_context),area=context_area,level=self.backlight_level,tone=self.tone,driver_level=self.state['native'].get('g_video__vid_local_dimming'),driver_tone=self.state['native'].get('g_video__vid_hdr_tone_mapping_mode')),
                    capabilities={'halo':'existing-device-worker','patterns':'GPU-readback',
                                  'sensors':'read-only-adb','runtime_budget':'three-level-leased-enforcing-bsp',
                                  'native_cumulative_abl':'experimental-high-medium-oem-policy','permanent_write':'monitor-local-boot-verified' if boot_verified else 'monitor-local-experimental-opt-in',
                                  'adb_boot':'native-whitelist-and-boot-receiver'})
        from local_asset_paths import status as asset_status
        data['local_assets']=asset_status()
        return data

    def export_config(self):
        return dict(format='mi-hdr-controller-v1',model_id=self.model_id,selected_level=self.backlight_level,selected_tone=self.tone,
                    profiles=self.profile_bank,pattern=self.pattern_config,calibration=self.calibration,ui=self.ui_preferences,nit_references=self.nit_references,auto_plans=self.auto_plans,auto_previews=self.auto_previews)

    def import_config(self,data):
        if self.active or self.budget_active: raise ValueError('请先停止实时调节，再载入配置')
        if data.get('format')!='mi-hdr-controller-v1': raise ValueError('不支持的配置文件格式')
        if data.get('model_id','32u-2026')!=self.model_id:raise ValueError('配置文件属于另一机型；请先切换对应27/32分支')
        level=data['selected_level'];tone=data['selected_tone']
        if type(level) is not int or level not in lab.BACKLIGHT_LEVELS or type(tone) is not int or tone not in TONES:
            raise ValueError('无效档位或模式')
        profiles={}
        if set(data['profiles'])!=set(self.profile_bank): raise ValueError('需要完整的三档×四模式配置')
        for key,p in data['profiles'].items():
            if type(p['software_abl']) is not bool: raise ValueError('ABL开关必须为布尔值')
            value=p.get('budget',24)
            if type(value) is not int or not 0<=value<=86:raise ValueError('预算范围0～86')
            profiles[key]={'config':lab.validate(p['config']),'software_abl':True,'budget':value,'native_abl':validate_abl(p.get('native_abl',ABL_DEFAULT)),'factory_budget':p.get('factory_budget',False),'pattern':validate_pattern(p.get('pattern',data['pattern']))}
            if type(profiles[key]['factory_budget']) is not bool:raise ValueError('原厂预算路径标记错误')
        pattern=validate_pattern(data['pattern']);cal=validate_calibration(data['calibration'])
        if 'nit_references' in data:self.nit_references=[validate_calibration(c) for c in data['nit_references']]
        if 'ui' in data:self.ui_preferences=preferences(data['ui'])
        self.auto_plans={}
        for key,plan in data.get('auto_plans',{}).items():
            if key not in profiles:raise ValueError('自动方案档位/模式无效')
            try:self.auto_plans[key]=validate_plan(plan,int(key.split(':')[0]),ROOT/'resources/ui/joint-output.json')[0]
            except ValueError:pass # Legacy wide-SF plans remain manual settings, never new automatic plans.
        self.auto_previews={k:validate_preview(v) for k,v in data.get('auto_previews',{}).items() if k in profiles and v.get('mode')=='global'}
        self.profile_bank=profiles;self.backlight_level=level;self.tone=tone
        self.software_abl=True
        self.budget_value=profiles[f'{level}:{tone}']['budget']
        self.native_abl=validate_abl(profiles[f'{level}:{tone}']['native_abl'])
        self.factory_budget=profiles[f'{level}:{tone}']['factory_budget']
        self.pattern_config=profiles[f'{level}:{tone}']['pattern']
        self.save_draft(profiles[f'{level}:{tone}']['config'])
        self.calibration=cal

    def show_panel(self):
        # Browser controls are the portable panel; do not create an unrelated second UI.
        pass

    def read_budget(self,value=None,running=None,configure=False):
        packet=abl_packet(self.native_abl,(time.monotonic_ns()//1000000)%2147483647) if configure else None
        previous=self.telemetry
        self.telemetry=budget.sample(self.folder/'budget-io',value,running,packet)
        if previous.get('status')=='live-driver' and self.telemetry['tick']!=previous.get('tick'):
            elapsed=(self.telemetry['tick']-previous['tick'])&0xffffffff;frames=(self.telemetry['frames']-previous['frames'])&0xffffffff
            rate=frames*250/elapsed
            if 10<=rate<=300:self.telemetry['driver_hz']=round(rate,2)
        self.budget_sample_at=time.monotonic()
        return self.telemetry

    def read_state(self,include_signal=True,timeout=20):
        previous_bank=self.state['native'].get('g_video__picture_mode')
        try:result=super().read_state(include_signal=include_signal,timeout=timeout)
        except lab.ADBConnectionError:
            self.state['connected']=False
            self.live_debug=False
            raise
        self.adb_read_at=time.monotonic()
        if previous_bank is not None and previous_bank!=result.get('g_video__picture_mode') and self.active and self.active.get('mode')=='live' and lab.hdr_input(result):
            if result.get('g_video__vid_local_dimming')==str(self.backlight_level) and result.get('g_video__vid_hdr_tone_mapping_mode')==str(self.tone):self.request_live(self.draft)
        return result

    def tick_budget(self):
        if self._ready and self.state['connected'] and not self.runtime_loaded and time.monotonic()-max(self.adb_read_at,self.native_poll_at)>30:
            self.native_poll_at=time.monotonic()
            self.read_state(include_signal=False,timeout=2)
        if not self._ready or not self.runtime_loaded or not self.state['connected'] or time.monotonic()-self.budget_sample_at<2:return
        if time.monotonic()-self.beat>8:
            if self.budget_active:
                self.budget_active=False;self.read_budget(running=False)
            return
        try:
            self.read_budget(running=True if self.budget_active else None)
            if time.monotonic()-self.native_poll_at>15:
                self.native_poll_at=time.monotonic()
                self.read_state(include_signal=False,timeout=2)
                if self.budget_active:
                    level=int(self.state['native'].get('g_video__vid_local_dimming',0))
                    tone=int(self.state['native'].get('g_video__vid_hdr_tone_mapping_mode',-1))
                    if level not in lab.BACKLIGHT_LEVELS or tone not in TONES:
                        self.budget_active=False;self.read_budget(running=False);return
                    if (level,tone)!=(self.backlight_level,self.tone):
                        self.select_profile_data(level,tone)
                        self.read_budget(None,False) if self.factory_budget else self.read_budget(self.budget_value,True,True)
                        if self.active:self.request_live(self.draft)
                        self.event('已跟随显示器切换档位/模式配置',level=level,tone=tone)
        except Exception:
            self.budget_sample_at=time.monotonic()
            self.telemetry={**self.telemetry,'status':'stale; 本次读回未确认，连接状态独立判断'}
            raise

    def finish(self):
        if self.budget_active:
            self.budget_active=False
            try:
                self.read_budget(running=False)
                self.event('自定义预算已停用，已回读原厂预算路径')
            except Exception as error:
                self.event('预算心跳已停止，至多十秒回退；当前未收到读回',error=str(error))
        super().finish()

    def preflight(self):
        state=self.state['native'] if self.state['connected'] and time.monotonic()-self.adb_read_at<2 else self.read_state()
        if not lab.hdr_input(state):raise ValueError('等待实际HDR输入稳定；不限定画面预设名称')
        if state.get('g_disp__disp_back_light')!='100':raise ValueError('当前nit参考以背光100为基准，请先设置背光100')
        if int(state.get('g_video__vid_hdr_tone_mapping_mode',-1)) not in TONES:
            raise ValueError('不支持的色调映射读数')

    def label(self):
        with self.pattern_lock:self.pattern_label()

    def pattern_label(self):
        if not self.pattern_dir:return
        p=self.pattern_config
        brightness=self.current_brightness()
        text=f"预估显示亮度 ≈{brightness['nits']:g} nit" if brightness['nits'] is not None else '预估显示亮度 nit —'
        if p['label']:
            geometry=f"每窗 {p['pixel_width']}×{p['pixel_height']} px" if p['pixel_width'] else f"窗口总面积 {p['area_percent']:g}%"
            text+=f"（参考换算） | AW驱动全局增益原始值 {brightness['raw'] if brightness['raw'] is not None else '—'}"
            text+=f" | {geometry} · {p['rows']}×{p['cols']} 阵列 | PQ输入 {p['input_nits']:g} nit（输入信号） | 分区{lab.BACKLIGHT_LEVELS[self.backlight_level]}/{TONES[self.tone]}"
            if self.runtime_loaded:text+=f" | 预算设置 {self.budget_value}/86 · 当前有效预算 {self.telemetry.get('budget_used','—')}/86"
            if self.runtime_loaded and self.telemetry.get('window') is not None:text+=f" · 驱动统计亮区 {self.telemetry['window']/100:g}%"
            if self.telemetry.get('active'):text+=f" | ABL系数 {self.telemetry.get('gain_used','—')}/65535 · L {self.telemetry.get('load','—')} · E {self.telemetry.get('energy','—')}"
            if self.pattern_started:text+=f" | 已显示 {int(time.monotonic()-self.pattern_started)}秒"
            text+=' | ·/` 菜单 · Esc退出'
        status=self.pattern_dir/'status.txt'
        if not status.exists() or status.read_text(encoding='utf-8')!=text:
            temp=self.pattern_dir/'status.tmp';temp.write_text(text,encoding='utf-8');replace_pattern_file(temp,status)
        check=self.pattern_dir/'check.json'
        if check.exists():
            self.pattern_check=read_pattern_check(check)
            if self.pattern_check.get('sequence')==self.pattern_sequence and 'windowed_preview' in self.pattern_check:self.pattern_config['mode']='windowed' if self.pattern_check['windowed_preview'] else 'fullscreen'
            record=self.operation_results.get('pattern')
            if record and record.get('pattern_sequence')==self.pattern_check.get('sequence') and self.pattern_check.get('wrong_pixels')==0:
                record.update(status='applied',message='本地图样GPU像素核对通过')

    def update_pattern(self,c):
        c=validate_pattern(c)
        restart=any(c[k]!=self.pattern_config[k] for k in ('mode','monitor','seconds'))
        if restart and self.pattern and self.pattern.poll() is None:
            self.stop_pattern_process();self.pattern_config=c;self.show_pattern();return
        self.pattern_config=c;self.pattern_sequence+=1
        if self.pattern_dir:
            write_pattern(self.pattern_dir/'pattern.txt',c,self.pattern_sequence)
            self.label()

    def show_pattern(self):
        if self.pattern and self.pattern.poll() is None:return
        self.count+=1;self.pattern_dir=self.folder/f'pattern-{self.count}';self.pattern_dir.mkdir()
        self.pattern_sequence+=1;write_pattern(self.pattern_dir/'pattern.txt',self.pattern_config,self.pattern_sequence)
        self.pattern_started=time.monotonic()
        self.label();p=self.pattern_config
        with (self.pattern_dir/'stdout.txt').open('w',encoding='utf-8') as out,(self.pattern_dir/'error.txt').open('w',encoding='utf-8') as err:
            self.pattern=subprocess.Popen([str(ROOT/'tools/hdr-pattern-control.exe'),str(self.pattern_dir/'pattern.txt'),
                str(self.pattern_dir/'check.json'),str(self.pattern_dir/'status.txt'),str(self.pattern_dir/'stop'),
                p['mode'],str(p['seconds']),str(p['monitor'])],env=lab.ENV,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        end=time.monotonic()+8
        while not (self.pattern_dir/'check.json').exists():
            if self.pattern.poll() is not None or time.monotonic()>end:
                err=(self.pattern_dir/'error.txt').read_text(encoding='utf-8')
                raise RuntimeError('图样启动失败：'+err)
            time.sleep(.05)
        self.label();self.state['pattern']=True;self.event('HDR图样GPU校验通过',check=self.pattern_check)

    def stop_pattern_process(self):
        if self.pattern and self.pattern.poll() is None:
            (self.pattern_dir/'stop').touch()
            self.pattern.wait(timeout=3)
        self.pattern=None;self.state['pattern']=False;self.pattern_dir=None

    def close_pattern(self):
        with self.pattern_lock:self.stop_pattern_process()

    def fast_pattern(self,data,operation='pattern-config'):
        """Local file/GPU lane; never waits for the ADB worker or its busy lock."""
        with self.pattern_lock:
            if self.shutdown_started:raise ValueError('控制器正在退出')
            if data.get('_profile') is not None and data['_profile']!=f'{self.backlight_level}:{self.tone}':raise ValueError('组合已切换，拒绝旧窗口的图样参数')
            if operation=='close-pattern':self.stop_pattern_process()
            else:
                self.update_pattern(data['config'])
                if operation=='pattern-start':self.show_pattern()
            field=data.get('_field','pattern')
            record=dict(id=data.get('_request_id',''),operation=operation,status='submitted' if self.state['pattern'] else 'draft',message='本地已提交，等待GPU像素回执' if self.state['pattern'] else '本地图样参数已保存；无需ADB',pattern_sequence=self.pattern_sequence,sequence=0)
            if operation=='close-pattern':record.update(status='applied',message='本地图样已关闭，ADB调试状态不变')
            self.operation_results[field]=record;self.last_operation=field
            self.profile_bank[f'{self.backlight_level}:{self.tone}']['pattern']=validate_pattern(self.pattern_config)
            self.save_configuration()
            return record

    def set_tone(self,value):
        self.count+=1;folder=self.folder/f'tone-{self.count}';folder.mkdir()
        remote=lab.REMOTE+'/portable-tone-'+folder.name+'-'+str(time.time_ns())
        self.device('shell','mkdir -p '+remote)
        script=folder/'tone.sh'
        receipt='/sdcard/Download/Mimonitor_Toolbox/.mtk_action_'+uuid.uuid4().hex+'.txt'
        bank=int(self.state['native']['g_video__picture_mode'])
        script.write_text(f'CLASSPATH={lab.JAR} /system/bin/app_process /data/data/mitv.service/cache MIHDRBridge setHdrToneMappingChecked {value} 3 {bank} {receipt}\n',encoding='utf-8',newline='\n')
        self.device('push',str(script),remote+'/tone.sh');self.device('shell',lab.tv_command(['sh',remote+'/tone.sh']))
        end=time.monotonic()+8
        while time.monotonic()<end:
            raw=self.device('shell','cat '+receipt,check=False)
            if '__complete=1' in raw: break
            time.sleep(.1)
        (folder/'receipt.txt').write_text(raw,encoding='utf-8')
        if '__complete=1' not in raw or 'fatal=' in raw: raise RuntimeError('色调映射未收到成功回执：'+raw)
        state=self.read_state()
        if state.get('g_video__vid_hdr_tone_mapping_mode')!=str(value): raise RuntimeError('色调映射回读不匹配')
        self.tone=value;self.event('色调映射已回读',value=value,name=TONES[value])

    def save_configuration(self):
        with self.config_lock:self.write_configuration()

    def write_configuration(self):
        data=json.dumps(self.export_config(),ensure_ascii=False,indent=2)
        for path in (ROOT/'profiles/controller.json',ROOT/'profiles/models'/self.model_id/'controller.json'):
            path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp');temporary.write_text(data,encoding='utf-8');temporary.replace(path)
        self.config_saved_at=datetime.now().isoformat(timespec='seconds')

    def close_controller(self,reason='user-exit'):
        if self.shutdown_started:return
        self.shutdown_started=True;self.closing=True
        self.pool.shutdown(wait=True)
        with self.lock:
            try:self.save_configuration()
            finally:
                if self.needs_restore:self.stop_debug()
                else:
                    self.close_pattern();self.close_panel()
                    if self.runtime_loaded_by_pc:
                        self.count+=1;budget.module('unload',self.folder/f'exit-budget-unload-{self.count}')
                        self.runtime_loaded=False;self.runtime_loaded_by_pc=False
                    self.disconnect_adb()
            self.event('控制器已保存PC配置并结束临时会话；未移除显示器永久方案',reason=reason)

    def prepare_adb(self,c=None):
        manual=c is not None;c=dict(c or connection());serial=str(c.get('serial','')).strip();port=c.get('port',5041)
        if not manual:
            if type(port) is not int or not 1024<=port<=65535:port=5041
            if not re.fullmatch(r'[A-Za-z0-9_.:\-]*',serial):serial=''
        if not re.fullmatch(r'[A-Za-z0-9_.:\-]*',serial) or type(port) is not int or not 1024<=port<=65535:
            raise ValueError('请输入有效ADB设备与服务端口')
        # 5037 belongs to general Android tooling. This controller owns a separate server.
        if port==5037:port=5041
        if self.adb_owned and port!=self.adb_port:raise ValueError('请先关闭实时调试/断开，再更改ADB服务端口')
        if not self.adb_owned:port=available_adb_port(port)
        c=dict(serial=serial,port=port)
        (ROOT/'state/connection.json').write_text(json.dumps(c),encoding='utf-8')
        if self.adb_owned:return c
        key=ROOT/'state/android/adbkey'
        if not key.exists():subprocess.run([str(lab.ADB),'keygen',str(key)],env=lab.ENV,capture_output=True,check=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        r=subprocess.run([str(lab.ADB),'-P',str(port),'start-server'],capture_output=True,env=lab.ENV,timeout=12,creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode:raise RuntimeError('ADB服务启动失败：'+r.stderr.decode('utf-8',errors='replace'))
        self.adb_owned=True;self.adb_port=port
        return c

    def disconnect_adb(self):
        if self.adb_owned:
            r=subprocess.run([str(lab.ADB),'-P',str(self.adb_port),'kill-server'],capture_output=True,env=lab.ENV,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode:raise RuntimeError('ADB尚未断开：'+r.stderr.decode('utf-8',errors='replace'))
            self.adb_owned=False;self.adb_port=None
        self.state['connected']=False;self.state['native']={};self.state['signal']={};self.adb_read_at=0
        self.telemetry={'status':'ADB已断开','raw':None}

    def restore_device_defaults(self,unload=True):
        # Preserve PC drafts. This is the existing receipt-verified factory worker, not a factory reset.
        tone=self.tone
        try:
            self.stop_pattern_process()
            budget_receipt=None
            if self.runtime_loaded:
                budget_receipt=self.read_budget(running=False)
                if budget_receipt.get('lease_end')!=0:
                    raise RuntimeError('预算租约停止未确认；保留连接以便重试')
            lab.Bridge.perform(self,'restore',{})
            native=self.read_state()
            if native.get('g_video__vid_hdr_tone_mapping_mode')!='5':self.set_tone(5)
            native=self.read_state()
            if native.get('g_video__vid_local_dimming')!='3' or native.get('g_video__vid_hdr_tone_mapping_mode')!='5':
                raise RuntimeError('原厂高档/HGiG恢复未确认；保留连接以便重试')
            if self.runtime_loaded_by_pc and unload:
                self.count+=1;budget.module('unload',self.folder/f'default-budget-unload-{self.count}')
                self.runtime_loaded=False;self.runtime_loaded_by_pc=False
                self.telemetry={'raw':None,'status':'设备默认已恢复；读取模块已卸载'}
            self.default_restoration=dict(verified=True,native=dict(native),budget=budget_receipt,captured_at=datetime.now().isoformat(timespec='seconds'),scope='控光/预算/软件ABL恢复回执；非整机恢复出厂')
            self.state['restoration']='原厂控光/预算/ABL已恢复，PC草稿保留'
        finally:self.tone=tone

    def stop_debug(self,c=None):
        self.live_debug=False
        if self.needs_restore:
            self.debug_phase='restoring'
            try:
                if not self.state['connected']:
                    self.prepare_adb(c);self._perform('auto-connect',{})
                self.restore_device_defaults()
            except Exception:
                self.debug_phase='restore-error';raise
            self.needs_restore=False
        self.debug_phase='disconnecting'
        try:self.disconnect_adb()
        except Exception:
            self.debug_phase='disconnect-error';raise
        self.debug_phase='idle'

    def module_defaults(self,module):
        if module not in ('auto','budget','halo','pattern'):raise ValueError('此页没有设备调光默认值')
        key=f'{self.backlight_level}:{self.tone}'
        if module=='pattern':
            self.update_pattern(dict(PATTERN));self.profile_bank[key]['pattern']=dict(PATTERN);return
        self.auto_plans.pop(key,None);self.auto_previews.pop(key,None)
        if module in ('auto','budget'):
            self.budget_value=24;self.factory_budget=True;self.native_abl=validate_abl(ABL_DEFAULT)
        if module=='auto':self.software_abl=True;self.halo_realtime=False
        self.save_draft(lab.STOCK_BY_LEVEL[self.backlight_level] if module in ('auto','halo') else self.draft)
        if self.state['connected']:
            self.needs_restore=True;self.activate_tuning();self.live_debug=True;self.debug_phase='live'

    def all_device_defaults(self):
        if not self.state['connected']:raise ValueError('请先连接ADB再恢复设备出厂调光')
        if not self.initial_backup or not self.initial_backup['ready']:raise ValueError('尚无已验证的电脑初始备份；未恢复')
        self.live_debug=False;self.budget_active=False;self.needs_restore=True
        self.persistence=permanent.disable_tuning(self.folder/'factory-disable-permanent')
        self.stop_pattern_process()
        if self.runtime_loaded:self.read_budget(running=False)
        self.finish()
        # Unload the owned adapter, rather than leaving a permanent overlay installed.
        if self.device('shell','test -d /sys/module/mi_oemabl && echo yes',check=False).strip()=='yes':
            self.count+=1;budget.module('unload',self.folder/f'factory-unload-{self.count}')
        self.count+=1
        receipt=device_backup.restore(self.initial_backup,self.folder/f'factory-backup-restore-{self.count}')
        self.runtime_loaded=False;self.runtime_loaded_by_pc=False
        self.profile_bank={f'{level}:{tone}':device_profile(level) for level in lab.BACKLIGHT_LEVELS for tone in TONES}
        self.backlight_level=int(receipt['native']['g_video__vid_local_dimming']);self.tone=int(receipt['native']['g_video__vid_hdr_tone_mapping_mode'])
        self.software_abl=True;self.budget_value=24;self.factory_budget=True;self.native_abl=validate_abl(ABL_DEFAULT)
        self.auto_plans={};self.auto_previews={};self.update_pattern(dict(PATTERN));self.save_draft(receipt['config'])
        self.state.update(native=receipt['native'],config=receipt['config'],restoration='初始备份原厂调光已恢复；永久调光已清除')
        self.default_restoration=receipt;self.needs_restore=False;self.debug_phase='idle'
        self.telemetry={'raw':None,'status':'初始备份已恢复；自定义预算模块已卸载'}
        self.event('已按初始备份恢复原厂调光；账号/ADB/桌面未重置',backup_id=receipt['backup_id'])

    def profile_defaults(self):
        key=f'{self.backlight_level}:{self.tone}'
        self.profile_bank[key]=device_profile(self.backlight_level)
        self.auto_plans.pop(key,None);self.auto_previews.pop(key,None)
        self.select_profile_data(self.backlight_level,self.tone)
        if self.state['connected']:
            self.needs_restore=True;self.activate_tuning();self.live_debug=True;self.debug_phase='live'
        self.event('当前1/12组合的全部参数已重置，其他11组不变')

    def software_defaults(self):
        # Only PC drafts change. Existing worker sequence, native lease and saved monitor policy do not.
        self.profile_bank={f'{level}:{tone}':device_profile(level) for level in lab.BACKLIGHT_LEVELS for tone in TONES}
        self.auto_plans={};self.auto_previews={}
        if not self.active and not self.budget_active and not self.state['pattern']:self.select_profile_data(self.backlight_level,self.tone)
        self.event('12组软件配置已重置；当前设备输出与显示器永久方案未改写')

    def select_profile_data(self,level,tone):
        if type(level) is not int or level not in lab.BACKLIGHT_LEVELS or type(tone) is not int or tone not in TONES:raise ValueError('未知档位/模式')
        p=self.profile_bank[f'{level}:{tone}']
        self.backlight_level=level;self.tone=tone;self.budget_value=p['budget'];self.native_abl=validate_abl(p['native_abl']);self.software_abl=True;self.factory_budget=p.get('factory_budget',False)
        with self.pattern_lock:self.update_pattern(validate_pattern(p.get('pattern',PATTERN)))
        self.save_draft(lab.validate(p['config']))

    def check_risk(self,op,data):
        if op=='permanent-write':
            dangerous=any(maximum_budget(p,True)>RISK_BUDGET for p in self.profile_bank.values())
            if dangerous and data.get('permanent_risk_ack') is not True:
                raise ValueError('危险值永久写入需要本次单独确认：显示器会自行续租，关闭PC不会自动回原厂')
            return
        if self.risk_unlocked:return
        values=[]
        if op in ('quick-budget','runtime-set','runtime-draft'):values=[data['budget']]
        elif op=='auto-apply':values=[data['budget']]
        elif op in ('live-debug','apply-profile'):
            values=[maximum_budget(self.profile_bank[f'{self.backlight_level}:{self.tone}'])]
        elif op=='profile-select':
            values=[maximum_budget(self.profile_bank[f"{data['level']}:{data['tone']}"])]
        elif op=='config-load':
            config=data['config']
            values=[maximum_budget(p) for p in config['profiles'].values()]
        if values and max(values)>RISK_BUDGET:
            raise ValueError('超过41/86项目短时验证边界；尚未确认风险，不应用。此边界不是设备安全极限。')

    def activate_tuning(self):
        if not self.state['connected']:raise ValueError('ADB未连接；草稿已保留，请连接后再开启实时调试')
        if not self.runtime_loaded and not self.factory_budget:self._perform('runtime-load',{})
        native=self.state.get('native',{})
        same_context=native.get('g_video__vid_local_dimming')==str(self.backlight_level) and native.get('g_video__vid_hdr_tone_mapping_mode')==str(self.tone)
        if self.active and self.active.get('mode')=='live' and same_context:self.request_live(self.draft)
        else:self._perform('apply-profile',{})
        if self.factory_budget:
            self.budget_active=False
            if self.runtime_loaded:
                if self.read_budget(running=False).get('lease_end')!=0:raise RuntimeError('原厂预算路径停止租约未确认')
        else:self._perform('runtime-set',{'budget':self.budget_value})

    def perform(self,op,data):
        if self.shutdown_started:raise ValueError('控制器正在退出')
        field=data.get('_field')
        record=None
        if field:
            record=dict(id=data.get('_request_id',''),operation=op,status='running',message='执行中',sequence=0)
            self.operation_results[field]=record;self.last_operation=field
            for key in data.get('_fields',[]):self.operation_results[key]=record
        try:
            if data.get('_model',self.model_id)!=self.model_id and op!='model-select':raise ValueError('机型已切换，旧窗口参数未写入')
            if op not in ('model-detect','model-select','preferences','backup-policy','backup-ack','config-save','shutdown','risk-lock','risk-unlock','close-pattern','restore') and not self.model_confirmed:raise ValueError('请先侦测并进入正确的27/32寸分支')
            profile_bound=op in ('profile-defaults','auto-apply','quick-budget','runtime-draft','runtime-set','quick-halo','draft','update','native-abl-draft','abl','profile-select','calibration','module-defaults')
            if profile_bound and data.get('_profile') is not None and data['_profile']!=f'{self.backlight_level}:{self.tone}':raise ValueError('档位/模式已切换；拒绝把旧窗口参数写入其他组合')
            device_edit=op in ('auto-apply','quick-budget','runtime-draft','runtime-set','quick-halo','draft','update','native-abl-draft','abl','profile-select','calibration') or op=='module-defaults' and data.get('module') not in ('pattern','sensors')
            if self.state['connected'] and (device_edit or op in ('runtime-load','apply-profile','permanent-write','all-defaults','profile-defaults','run','live','backlight')) and not self.device_model.get('verified'):raise ValueError('ADB机型未复核，未允许调光写入')
            if device_edit and not self.state['connected']:raise ValueError('请先连接ADB，再调整显示器参数；本地图样与界面设置不需要ADB')
            if self.state['connected'] and (device_edit or op in ('all-defaults','profile-defaults','permanent-write','apply-profile','runtime-load','live')) and not (self.initial_backup and self.initial_backup['ready']):raise ValueError('初始设备备份尚未完成所选位置读回；未允许调光写入')
            # Turning OFF must never be blocked by the current high-value draft.
            if op!='live-debug' or data.get('enabled'):self.check_risk(op,data)
            routed=op
            if op=='risk-unlock':
                if data.get('acknowledged') is not True:raise ValueError('必须明确确认风险说明')
                self.risk_unlocked=True
            elif op=='risk-lock':self.risk_unlocked=False
            elif op=='live-debug':
                if type(data.get('enabled')) is not bool:raise ValueError('实时调试必须为开关')
                if data['enabled']:
                    self.debug_phase='connecting'
                    try:
                        self.prepare_adb(data.get('connection'))
                        self._perform('auto-connect',{})
                        self.debug_phase='applying';self.needs_restore=True;self.default_restoration=None
                        self.activate_tuning()
                    except Exception:
                        self.stop_debug();raise
                    self.live_debug=True;self.debug_phase='live'
                else:self.stop_debug(data.get('connection'))
            else:
                if not self.live_debug:
                    if op in ('quick-halo','update'):routed='draft'
                    elif op in ('quick-budget','runtime-set'):routed='runtime-draft'
                    elif op in ('apply-profile','runtime-load','live'):
                        raise ValueError('请先开启顶栏“实时调试”；关闭时所有调节仅保存草稿')
                if op=='all-defaults':
                    if data.get('confirmed') is not True:raise ValueError('恢复全部调光需要明确确认')
                    self.all_device_defaults()
                elif op in ('profile-defaults','software-defaults'):
                    if data.get('confirmed') is not True:raise ValueError('重置需要明确确认')
                    if op=='profile-defaults':self.profile_defaults()
                    else:self.software_defaults()
                elif op=='auto-preview':
                    key=data.get('_profile',f'{self.backlight_level}:{self.tone}')
                    if key not in self.profile_bank:raise ValueError('未知的预览配置组合')
                    self.auto_previews[key]=validate_preview(data['preview'])
                elif op=='pattern-draft':
                    self.pattern_config=validate_pattern(data['config'])
                elif op=='module-defaults':self.module_defaults(data['module'])
                elif op=='auto-apply':
                    if not self.live_debug:raise ValueError('请先开启实时调试，再按应用可达方案；预览不会写入显示器')
                    if self.native_abl['enabled']:raise ValueError('自动联合拟合不支持开启累计ABL；请手动调节')
                    plan,config=model_worker.call('validate',model_id=self.model_id,tone=self.tone,data=data,c=self.draft,level=self.backlight_level,q=self.pattern_config['input_nits'])
                    self.factory_budget=False;self.budget_value=plan['budget'];self.save_draft(lab.validate(config))
                    self.auto_plans[f'{self.backlight_level}:{self.tone}']=plan
                    if self.live_debug:self.activate_tuning()
                else:self._perform(routed,data)
                if op=='profile-select':
                    self.needs_restore=True;self.activate_tuning();self.live_debug=True;self.debug_phase='live'
                if op in ('runtime-stop','runtime-unload','restore'):
                    self.live_debug=False;self.finish()
                if op in ('permanent-write','permanent-remove'):
                    # A successful permanent handoff is no longer a PC temporary session.
                    self.needs_restore=False;self.stop_debug()
            if op in {'profile-defaults','software-defaults','all-defaults','auto-preview','module-defaults','auto-apply','preferences','draft','update','quick-halo','quick-budget','profile-select','abl','calibration','native-abl-draft','runtime-draft','runtime-set','config-load','pattern-config','pattern-start','pattern-draft'}:
                if op in ('draft','update','quick-halo','quick-budget','abl','native-abl-draft','runtime-draft','runtime-set'):self.auto_plans.pop(f'{self.backlight_level}:{self.tone}',None)
                self.save_configuration()
            if record:
                draft=(op=='native-abl-draft' or op=='software-defaults' or op=='profile-defaults' and not self.state['connected'] or op=='auto-preview' or routed in ('draft','runtime-draft','pattern-draft') or (op in ('module-defaults','auto-apply','native-abl-draft','abl','profile-select') and not self.live_debug))
                waiting=not draft and bool(self.active) and self.wanted_sequence>self.ack_sequence
                record.update(status='draft' if draft else 'waiting-ack' if waiting else 'applied',
                              message='草稿已保存，未下发设备' if draft else '等待设备执行回执' if waiting else '操作完成 / 读回通过',
                              sequence=self.wanted_sequence)
                if op=='all-defaults':record.update(status='applied',message='全部设备出厂调光恢复回执已确认；永久调光停用')
                if op=='software-defaults':record.update(status='draft',message='12组PC软件配置已重置；未写入显示器或永久方案')
                if op=='halo-stop':record.update(status='applied',message='已暂停本模块自动下发；已写参数保持（本次未写设备）')
                if op=='module-defaults' and data['module']!='pattern':record.update(message='当前组合的本控制分区设备默认已应用；等待回执' if waiting else '当前组合的本控制分区设备默认已应用')
                if op=='live-debug' and not data['enabled']:record.update(message='默认状态已恢复，ADB已断开；PC草稿保留' if self.default_restoration else '未下发调试，ADB已断开')
                if op=='module-defaults' and data['module']=='pattern' and not self.state['pattern']:record.update(status='draft',message='默认图样已保存；没有打开测试窗口')
        except Exception as error:
            if record:record.update(status='error',message=str(error))
            raise

    def _perform(self,op,data):
        if op=='model-detect':
            self.model_detection=device_models.detect();return
        if op=='model-select':
            self.select_model(data);return
        if op=='backup-policy':
            self.backup_policy=device_backup.save_policy(data['policy'])
            if self.state['connected']:
                self.initial_backup=None
                self.initial_backup=device_backup.ensure(self.folder/'initial-backup',self.state['native'],policy=self.backup_policy)
                if self.initial_backup['data']['factory_ini']!=self.device_model['factory_ini']:raise ValueError('初始备份对应另一屏型；保留原件，未允许调光写入')
            return
        if op=='backup-ack':
            device_backup.acknowledge(self.initial_backup);return
        if op=='preferences':
            self.ui_preferences=preferences(data['config']);return
        if op=='halo-stop':
            self.halo_realtime=False
            self.event('光晕参数自动下发已关闭；已写参数保持，未停止预算或断开ADB')
            return
        if op in ('draft','update','quick-halo'):
            if op in ('update','quick-halo'):self.halo_realtime=True
            self.save_draft(lab.validate(data['config']))
            if op=='update' or (op=='quick-halo' and self.state['connected']):
                if self.active:self.request_live(self.draft)
                else:self._perform('apply-profile',{})
            return
        if op=='quick-budget':
            self._perform('runtime-draft',data)
            if 'native_abl' in data:self.native_abl=validate_abl({**data['native_abl'],'e0':int(data['native_abl']['e0'])},True)
            self.save_draft(self.draft)
            if not self.state['connected']:return
            had_halo=bool(self.active)
            if not self.runtime_loaded:self._perform('runtime-load',{})
            self.preflight()
            mismatch=(int(self.state['native']['g_video__vid_local_dimming']),int(self.state['native']['g_video__vid_hdr_tone_mapping_mode']))!=(self.backlight_level,self.tone)
            if mismatch or (had_halo and not self.active):self._perform('apply-profile',{})
            self._perform('runtime-set',data);return
        if op=='auto-connect':
            if not self.model_confirmed:raise ValueError('请先侦测显示器型号')
            if not self.backup_policy['confirmed']:raise ValueError('请先选择备份保存位置')
            c=self.prepare_adb();self.count+=1
            def progress(message):self.adb_discovery={'searching':True,'message':message}
            try:
                selected=discover(c['port'],self.folder/f'adb-discovery-{self.count}',c['serial'],progress)
                self._perform('connect',{'connection':dict(serial=selected['serial'],port=selected['port'])})
                self.adb_discovery={**selected,'searching':False,'message':'已自动连接 · '+selected['source']+' · '+selected['serial']}
            except Exception as error:
                self.adb_discovery={'searching':False,'message':str(error)};raise
            return
        if op in {'sensors','permanent-status','permanent-write','permanent-remove','adb-boot-status','adb-boot-enable','adb-boot-disable','runtime-load','runtime-set','runtime-stop','runtime-unload','apply-profile','restore'} and not self.state['connected']:
            raise ValueError('ADB已断开，不会由后台请求自动重连；请开启实时调试或手动连接')
        if op in ('apply-profile','runtime-set','runtime-stop','runtime-unload','live','update','restore') and self.persistence.get('owned') and self.persistence.get('enabled') and not self.persistence.get('paused'):
            self.persistence=permanent.pause(self.folder/'permanent-pause')
            self.event('显示器保存方案已在本次开机暂停；PC临时调节不会与本机心跳竞争')
        if op=='connect':
            if not self.model_confirmed:raise ValueError('请先侦测显示器型号')
            if not self.backup_policy['confirmed']:raise ValueError('请先选择备份保存位置')
            c=self.prepare_adb(data.get('connection'));serial=c['serial'];port=c['port']
            if ':' in serial:
                r=subprocess.run([str(lab.ADB),'-P',str(port),'connect',serial],capture_output=True,env=lab.ENV,timeout=12,creationflags=subprocess.CREATE_NO_WINDOW)
                if r.returncode: raise RuntimeError(r.stderr.decode('utf-8',errors='replace'))
            self.device('get-state')
            identity=self.device('shell','getprop ro.product.device; uname -r').splitlines()
            if 'beekeeper' not in identity or '5.15.148-android14-11-g37010446f523' not in identity:
                raise ValueError('此包的写入功能只适配已研究的 beekeeper 固件；读取到 '+str(identity))
            from prepare_local_assets import prepare_device
            prepare_device(self.device)
            deploy();self.read_state()
            try:
                self.verify_device_model()
                self.initial_backup=device_backup.ensure(self.folder/'initial-backup',self.state['native'],policy=self.backup_policy)
                if self.initial_backup['data']['factory_ini']!=self.device_model['factory_ini']:raise ValueError('初始备份对应另一屏型；保留原件，未允许调光写入')
            except Exception:
                self.state['connected']=False;self.initial_backup=None;raise
            self.state['phase']='所选位置初始备份读回通过，尚未应用'
            self.persistence=permanent.status(self.folder/'permanent-status')
            self.runtime_loaded=self.device('shell','test -d /sys/module/mi_oemabl && echo yes',check=False).strip()=='yes'
            if self.runtime_loaded:self.read_budget()
            self.event('便携控制器已连接',identity=identity)
        elif op=='permanent-status':
            self.persistence=permanent.status(self.folder/'permanent-status')
            self.runtime_loaded=self.device('shell','test -d /sys/module/mi_oemabl && echo yes',check=False).strip()=='yes'
            self.event('已读取显示器本机方案状态',running=self.persistence['running'],enabled=self.persistence['enabled'])
        elif op in ('adb-boot-status','adb-boot-enable','adb-boot-disable'):
            action={'adb-boot-status':'status','adb-boot-enable':'install','adb-boot-disable':'remove'}[op]
            self.count+=1;raw,folder=adb_autostart.perform(action,self.folder/f'adb-boot-{self.count}')
            self.adb_boot={'status':'fresh-readback','enabled':'policy_boot_autostart=true' in raw and 'package:' in raw.split('__permission')[0],
                          'captured_at':datetime.now().isoformat(timespec='seconds'),'folder':str(folder),
                          'reference_reboot_passed':True,'stable_persistence_verified':False}
            self.event('ADB随开机设置已读回',operation=action,enabled=self.adb_boot['enabled'])
        elif op=='pattern-config':
            self.update_pattern(data['config'])
        elif op=='pattern-start':
            self.update_pattern(data['config']);self.show_pattern()
        elif op=='close-pattern': self.close_pattern()
        elif op=='sensors':
            self.count+=1;folder=self.folder/f'sensors-{self.count}';folder.mkdir()
            script=folder/'read.sh';script.write_text(SENSOR_SCRIPT,encoding='utf-8',newline='\n')
            remote=lab.REMOTE+'/portable-sensors.sh'
            self.device('push',str(script),remote)
            raw=self.device('shell','sh '+remote)
            (folder/'stdout.txt').write_text(raw,encoding='utf-8');self.sensors=parse_sensors(raw)
            if not self.sensors['complete']: raise RuntimeError('传感器读取未完成')
            thermal=self.device('shell','dumpsys thermalservice')
            light=self.device('shell','dumpsys sensorservice')
            (folder/'thermalservice.txt').write_text(thermal,encoding='utf-8')
            (folder/'sensorservice.txt').write_text(light,encoding='utf-8')
            self.sensors['sensors']=android_sensors(thermal,light)+self.sensors['sensors']
            (folder/'sensors.json').write_text(json.dumps(self.sensors,ensure_ascii=False,indent=2),encoding='utf-8')
            self.event('传感器只读采样完成',count=len(self.sensors['sensors']))
        elif op=='profile-select':
            self.select_profile_data(data['level'],data['tone'])
        elif op=='apply-profile':
            self.preflight()
            if self.state['native'].get('g_video__vid_hdr_tone_mapping_mode')!=str(self.tone): self.set_tone(self.tone)
            self.halo_realtime=True
            same_level=self.state['native'].get('g_video__vid_local_dimming')==str(self.backlight_level)
            if self.active and self.active.get('mode')=='live' and same_level:self.request_live(self.draft)
            else:self.run('live',self.draft,0,False)
        elif op=='abl':
            raise ValueError('旧软件累计ABL开关已移除；保留原厂默认路径，请使用独立的实验计时ABL编辑器')
        elif op=='config-save':
            if 'pattern' in data:self.pattern_config=validate_pattern(data['pattern'])
            if 'native_abl' in data:self.native_abl=validate_abl(data['native_abl']);self.save_draft(self.draft)
            self.save_configuration()
            self.event('控制器配置已保存；没有写入显示器开机配置')
        elif op=='config-load': self.import_config(data['config'])
        elif op=='calibration':
            self.calibration=validate_calibration(data['config'])
            c=self.calibration
            self.nit_references=[r for r in self.nit_references if not (r['level']==c['level'] and r['tone']==c['tone'] and abs(r['window_percent']-c['window_percent'])<.01)]+[c]
        elif op=='native-abl-draft':
            self.native_abl=validate_abl({**data['config'],'e0':int(data['config']['e0'])});self.save_draft(self.draft)
            self.event('累计ABL草稿已保存；统一设置按应用才写入')
        elif op=='runtime-load':
            self.finish();self.preflight()
            try:self.read_budget()
            except RuntimeError:
                self.count+=1;budget.module('load',self.folder/f'budget-load-{self.count}');self.runtime_loaded_by_pc=True
                self.read_budget()
            self.runtime_loaded=True;self.event('临时三档预算模块已就绪；当前未启用提亮')
        elif op in ('runtime-draft','runtime-set'):
            value=data['budget']
            if type(value) is not int or not 0<=value<=86:raise ValueError('预算范围0～86')
            if op=='runtime-set':
                if not self.runtime_loaded:raise ValueError('请先初始化临时预算模块')
                self.preflight()
                if self.state['native'].get('g_video__vid_local_dimming') not in ('1','2','3'):raise ValueError('请先开启低、中或高档分区控光')
                if (int(self.state['native']['g_video__vid_local_dimming']),int(self.state['native']['g_video__vid_hdr_tone_mapping_mode']))!=(self.backlight_level,self.tone):raise ValueError('请先开始实时调节，应用所选档位和亮暗模式')
                self.read_budget(value,True,True);self.budget_active=True
                self.event('亮度预算已下发并读回',setting=value,used=self.telemetry['budget_used'],raw=self.telemetry['raw'])
            self.factory_budget=False;self.budget_value=value;self.save_draft(self.draft)
        elif op=='runtime-stop':
            self.budget_active=False
            if self.runtime_loaded:self.read_budget(running=False)
            self.event('自定义预算暂停；已返回所选档位的原厂预算路径')
        elif op=='runtime-unload':
            self.finish()
            if self.runtime_loaded:
                self.count+=1;budget.module('unload',self.folder/f'budget-unload-{self.count}')
            self.runtime_loaded=False;self.runtime_loaded_by_pc=False;self.telemetry={'status':'模块已卸载','raw':None};self.event('临时预算模块已卸载，原始指令已恢复')
        elif op=='restore':
            self.close_pattern()
            super().perform('restore',{})
            if self.state['native'].get('g_video__vid_hdr_tone_mapping_mode')!='5': self.set_tone(5)
            self.backlight_level=3;self.software_abl=True;self.save_draft(lab.STOCK)
        elif op=='permanent-write':
            permanent.authorize_install(self.export_config(),data.get('experimental_ack'))
            self.finish();self.count+=1
            self.persistence=permanent.install(self.export_config(),self.folder/f'permanent-write-{self.count}',experimental_ack=data.get('experimental_ack'))
            self.runtime_loaded=self.device('shell','test -d /sys/module/mi_oemabl && echo yes',check=False).strip()=='yes';self.budget_active=False;self.runtime_loaded_by_pc=False
            if self.runtime_loaded:self.read_budget()
            self.event('方案已保存到显示器并由本机执行；无需PC续心跳',state=self.persistence['local']['state'])
        elif op=='permanent-remove':
            self.close_pattern();self.count+=1
            self.persistence=permanent.remove(self.folder/f'permanent-remove-{self.count}')
            self.runtime_loaded=False;self.runtime_loaded_by_pc=False;self.budget_active=False;self.telemetry={'status':'持久化及临时模块已移除','raw':None}
            self.event('本机方案已移除，预算模块已卸载；未清空账号或整机设置')
        else: super().perform(op,data)


class Handler(lab.Handler):
    def do_GET(self):
        if self.headers.get('Host')!=f'127.0.0.1:{lab.PORT}': return self.reply({'error':'localhost only'},403)
        path=urlparse(self.path).path
        assets={'/models.js':ROOT/'lab/models.js','/parameters.js':ROOT/'lab/parameters.js','/dialogs.js':ROOT/'lab/dialogs.js','/factory-output.json':ROOT/'resources/ui/factory-output.json','/calibrated.js':ROOT/'lab/calibrated.js','/optical-reference.json':ROOT/'resources/ui/optical-reference.json','/abl.js':ROOT/'lab/abl.js','/abl.css':ROOT/'lab/abl.css','/modules.js':ROOT/'lab/modules.js','/modules.css':ROOT/'lab/modules.css','/responsive.js':ROOT/'lab/responsive.js','/responsive.css':ROOT/'lab/responsive.css','/':ROOT/'lab/portable.html','/index.html':ROOT/'lab/portable.html','/portable.html':ROOT/'lab/portable.html',
                '/model-guide':ROOT/'docs/27与32寸机型与预测说明.md','/guide':ROOT/'docs/使用说明.md','/app-icon.svg':ROOT/'resources/ui/app.svg','/sf-rings.svg':ROOT/'resources/ui/sf-rings.svg','/ux.js':ROOT/'lab/ux.js',
                '/tuning.js':ROOT/'lab/tuning.js','/tuning.css':ROOT/'lab/tuning.css','/window-output.json':ROOT/'resources/ui/window-output.json',
                '/auto.js':ROOT/'lab/auto.js','/eva.css':ROOT/'lab/eva.css','/joint-output.json':ROOT/'resources/ui/joint-output.json'}
        for name in ('NotoSerifSC-VF.ttf','RobotoCondensed-VF.ttf','ShareTechMono-Regular.ttf'):assets['/fonts/'+name]=ROOT/'resources/fonts'/name
        if path in assets:
            raw=assets[path].read_bytes();self.send_response(200)
            self.send_header('Content-Type','font/ttf' if path.endswith('.ttf') else 'text/plain; charset=utf-8' if path in ('/guide','/model-guide') else 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8' if path.endswith('.css') else 'application/json; charset=utf-8' if path.endswith('.json') else 'image/svg+xml' if path.endswith('.svg') else 'text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
        else:super().do_GET()

    def do_POST(self):
        op=self.path.removeprefix('/api/')
        custom={'model-detect','model-select','config-export','backup-policy','backup-ack','profile-defaults','software-defaults','predict-response','auto-fit','abl-predict','all-defaults','auto-preview','module-defaults','auto-apply','live-debug','risk-unlock','risk-lock','pattern-draft','preferences','auto-connect','quick-budget','quick-halo','draft','update','connect','pattern-config','pattern-start','sensors','profile-select','apply-profile','halo-stop','abl','config-save','config-load','calibration','permanent-write','close-pattern','restore','shutdown','runtime-load','runtime-draft','runtime-set','runtime-stop','runtime-unload','native-abl-draft',
                'adb-boot-status','adb-boot-enable','adb-boot-disable',
                'permanent-status','permanent-remove'}
        if op not in custom:return super().do_POST()
        b=self.server.bridge
        if self.headers.get('Origin')!=lab.URL or self.headers.get('X-MI-Token')!=b.token:return self.reply({'error':'请从本机控制器操作'},403)
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<=length<=64000:raise ValueError('请求过大')
            data=json.loads(self.rfile.read(length) or b'{}')
            if op=='config-export':
                with b.config_lock:
                    config=b.export_config()
                self.reply({'ok':True,'filename':'mi-hdr-controller-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json','config':config});return
            if op in ('pattern-config','pattern-draft','pattern-start','close-pattern'):
                self.reply({'ok':True,'result':b.fast_pattern(data,op)});return
            if data.get('_model',b.model_id)!=b.model_id and op!='model-select':raise ValueError('机型已改变，请刷新后重试')
            if op in ('abl-predict','predict-response','auto-fit') and not b.model_confirmed:raise ValueError('请先识别并选择显示器机型')
            if op=='abl-predict':
                config=lab.validate(data['config']);level=data['level'];value=data['budget']
                if type(level) is not int or level not in (1,2,3) or type(value) is not int or not 0<=value<=86:raise ValueError('预测档位/预算无效')
                params=data['native_abl'];params={**params,'e0':int(params['e0'])}
                result=model_worker.call('forecast',model_id=b.model_id,tone=data.get('tone',b.tone),config=config,level=level,budget=value,params=params,factory=data.get('factory',False),hz=b.telemetry.get('driver_hz',60),generation=data.get('generation',0))
                self.reply({'ok':True,'forecast':result});return
            if op=='auto-fit':
                config=lab.validate(data['config']);level=data['level'];nits=data['input_nits'];cap=data['ceiling'];targets=data['targets']
                if type(level) is not int or level not in (1,2,3) or type(nits) not in (int,float) or not 0<=nits<=10000 or type(cap) is not int or not 0<=cap<=86:raise ValueError('拟合档位/输入/上限无效')
                targets=validate_preview(dict(mode='global',ceiling=cap,targets=[targets,targets]))['targets'][0]
                self.reply({'ok':True,'fit':model_worker.call('fit',model_id=b.model_id,tone=data.get('tone',b.tone),c=config,level=level,q=nits,targets=targets,ceiling=cap)});return
            if op=='predict-response':
                config=lab.validate(data['config']);level=data['level'];nits=data['input_nits']
                if type(level) is not int or level not in (1,2,3) or type(nits) not in (int,float) or not 0<=nits<=10000:raise ValueError('预测档位/输入无效')
                self.reply({'ok':True,'response':model_worker.call('predict',model_id=b.model_id,tone=data.get('tone',b.tone),config=config,level=level,input_nits=nits)});return
            if op in ('preferences','auto-preview','backup-ack'):
                with b.config_lock:b.perform(op,data)
                self.reply({'ok':True});return
            if op=='shutdown':
                self.reply({'ok':True,'closing':True});threading.Thread(target=self.server.stop_controller,args=('user-exit',),daemon=True).start();return
            b.beat=time.monotonic();b.submit(op,data);self.reply({'ok':True})
        except (ValueError,KeyError,TypeError) as e:self.reply({'error':str(e)},400)
        except RuntimeError as e:self.reply({'error':str(e)},503)


def main():
    for name in ('state','profiles','experiments','tmp','logs'):(ROOT/name).mkdir(exist_ok=True)
    server=ManagedServer(('127.0.0.1',lab.PORT),Handler);server.bridge=PortableBridge()
    watch_owner(server)
    print(lab.URL,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.bridge.close_controller('server-finally')
        server.server_close()
        model_worker.close()


if __name__=='__main__':main()
