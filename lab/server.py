"""Local-only HTML bridge; runtime data stays beside this portable copy."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ctypes
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from mi_probe import ENV, ADB, REMOTE, JAR, KEYS, native, tv_command, adb_base,ADBConnectionError,connection_error

PORT = int(os.environ.get('MI_CONTROL_PORT','18533'))
URL = f'http://127.0.0.1:{PORT}'
STOCK = dict(sf=[255]*5, dc=8, blend=8, dynamic=1, alpha=[3,5,7,9,11,13,15,16])
AREAS = [('1×1 像素',100/8294400), ('4×2 像素',.0001),
         *[(f'{p:g}%',p) for p in (.01,.02,.05,.1,.2,.5,1,2,3,5,10,15,20,25)],
         ('100%（保留参考列）',100), ('黑底（保留参考列）',0)]
PRESETS = {'原厂高档':STOCK, '邻区扩展 SF128':{**STOCK,'sf':[128,255,255,255,255]},
           'Alpha0=12':{**STOCK,'alpha':[12,5,7,9,11,13,15,16]},
           'Alpha0=16':{**STOCK,'alpha':[16,5,7,9,11,13,15,16]},
           '统计最大值优先':{**STOCK,'dynamic':0}}
BACKLIGHT_LEVELS = {1:'低', 2:'中 · 持续亮度', 3:'高'}
STOCK_BY_LEVEL = {1:{**STOCK,'dc':7},2:{**STOCK,'dc':6,'blend':6},3:STOCK}


def validate(value):
    if not isinstance(value,dict) or set(value)!=set(STOCK):
        raise ValueError('参数组合不完整')
    for key,count,limit in [('sf',5,255),('alpha',8,16)]:
        if not isinstance(value[key],list) or len(value[key])!=count:
            raise ValueError(key+' 数量错误')
        if any(type(n) is not int or not 0<=n<=limit for n in value[key]):
            raise ValueError(key+' 超出范围')
    for key,limit in [('dc',8),('blend',8),('dynamic',1)]:
        if type(value[key]) is not int or not 0<=value[key]<=limit:
            raise ValueError(key+' 超出范围')
    return json.loads(json.dumps(value))


def hdr_input(state):
    # Signal-family codes, not a requirement to use one named picture preset.
    return state.get('g_dovi_info__')=='0' and int(state.get('g_video__picture_mode',-1)) in (15,16,17,18,19,35,55,76,*range(25,35))

class Bridge:
    def __init__(self):
        self.lock=threading.RLock()
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.folder=ROOT/'experiments'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-html-lab')
        self.folder.mkdir()
        self.token=secrets.token_hex(24)
        self.active=None
        self.pattern=None
        self.pattern_dir=None
        self.key_offset=0
        self.beat=0
        self.last_device_beat=0
        self.count=0
        self.closing=False
        self.seconds=60
        self.panel=None
        self.panel_dir=None
        self.panel_sequence=0
        self.wanted_sequence=0
        self.sent_sequence=0
        self.ack_sequence=0
        self.sent_config=None
        self.sent_pip=0
        self.pending_at=0
        self.last_result_read=0
        self.request_lock=threading.Lock()
        self.state={'connected':False,'busy':False,'error':'','phase':'原厂待连接',
                    'config':STOCK,'active':False,'remaining':0,'pattern':False,'area':5,
                    'events':[],'native':{},'signal':{},'restoration':'尚未读取',
                    'backlight_level':3,'pip_bypass':False,
                    'folder':str(self.folder)}
        settings=ROOT/'state/lab-settings.json'
        self.draft=validate(json.loads(settings.read_text(encoding='utf-8'))) if settings.exists() else validate(STOCK)
        self.backlight_level=3
        self.backlight_presets={str(n):validate(self.draft) for n in BACKLIGHT_LEVELS}
        saved_backlight=ROOT/'state/lab-backlight-presets.json'
        if saved_backlight.exists():
            saved_modes=json.loads(saved_backlight.read_text(encoding='utf-8'))
            self.backlight_level=saved_modes['selected']
            if type(self.backlight_level) is not int or self.backlight_level not in BACKLIGHT_LEVELS:
                raise ValueError('未知背光档位')
            self.backlight_presets={str(n):validate(saved_modes['profiles'][str(n)]) for n in BACKLIGHT_LEVELS}
            self.draft=validate(self.backlight_presets[str(self.backlight_level)])
        self.save_draft(self.draft)
        self.presets=dict(PRESETS)
        saved=ROOT/'state/lab-presets.json'
        if saved.exists():
            self.presets.update({k:validate(v) for k,v in json.loads(saved.read_text(encoding='utf-8')).items()})
        threading.Thread(target=self.tick,daemon=True).start()

    def event(self,text,**data):
        row={'time':datetime.now().isoformat(timespec='seconds'),'text':text,**data}
        self.state['events']=(self.state['events']+[row])[-30:]
        with (self.folder/'events.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n')

    def device(self,*args,check=True,raw=False):
        r=subprocess.run([*adb_base(),*args],
                         env=ENV,capture_output=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode and check:
            message=r.stderr.decode('utf-8',errors='replace').strip()
            if connection_error(message):self.state['connected']=False
            raise (ADBConnectionError if connection_error(message) else RuntimeError)(message)
        return r if raw else r.stdout.decode('utf-8',errors='replace')

    def snapshot(self):
        return json.loads(json.dumps({**self.state,'app':'mi-luma-lab','version':'live-3','draft':self.draft,
                                     'areas':AREAS,'token':self.token,'panel':bool(self.panel),
                                     'selected_backlight_level':self.backlight_level,
                                     'backlight_presets':self.backlight_presets,
                                     'wanted_sequence':self.wanted_sequence,'ack_sequence':self.ack_sequence},ensure_ascii=False))

    def save_draft(self,config):
        self.draft=validate(config)
        self.backlight_presets[str(self.backlight_level)]=validate(config)
        (ROOT/'state/lab-settings.json').write_text(json.dumps(self.draft,indent=2),encoding='utf-8')
        (ROOT/'state/lab-backlight-presets.json').write_text(json.dumps({
            'selected':self.backlight_level,'profiles':self.backlight_presets},indent=2),encoding='utf-8')

    def device_heartbeat(self,remote):
        self.device('shell','date +%s > '+remote+'/heartbeat.tmp && mv '+remote+'/heartbeat.tmp '+remote+'/heartbeat')

    def request_live(self,config):
        config=validate(config)
        with self.request_lock:
            self.save_draft(config)
            self.wanted_sequence+=1
            self.pending_at=time.monotonic()+.08
        if not self.active and not self.state['busy']:
            self.submit('live',{'config':config,'full_screen':False,'panel':False})

    def publish_live(self):
        if not self.active or self.active['mode']!='live':
            return
        with self.request_lock:
            sequence=self.wanted_sequence
            config=validate(getattr(self,'comparison_config',None) or self.draft)
        if sequence<=self.sent_sequence or time.monotonic()<self.pending_at:
            return
        packet=self.active['folder']/'live-config.txt'
        values=[*config['sf'],config['dc'],config['blend'],config['dynamic'],*config['alpha']]
        pip=int(getattr(self,'software_abl',True)==False)
        packet.write_text(str(sequence)+' '+' '.join(map(str,[*values,pip]))+'\n',encoding='utf-8')
        remote=self.active['remote']
        self.device('push',str(packet),remote+'/config.tmp')
        self.device('shell','mv '+remote+'/config.tmp '+remote+'/config')
        self.sent_sequence=sequence
        self.sent_config=config
        self.sent_pip=pip

    def panel_state(self):
        if not self.panel_dir:
            return
        c=self.draft
        values=[*c['sf'],c['dc'],c['blend'],c['dynamic'],*c['alpha']]
        status=self.state['error'] or ('已写入（回执）' if self.active and self.ack_sequence>=self.wanted_sequence else
                                    '写入中' if self.active else '尚未应用')
        text=str(self.panel_sequence)+' '+' '.join(map(str,values))+'\n'+status+'\n'+AREAS[self.state['area']][0]+'\n'+str(self.backlight_level)+'\n'
        (self.panel_dir/'state.txt').write_text(text,encoding='utf-8')

    def show_panel(self):
        if self.panel and self.panel.poll() is None:
            return
        self.count+=1
        self.panel_dir=self.folder/f'panel-{self.count}'
        self.panel_dir.mkdir()
        self.panel_sequence=0
        self.panel_state()
        self.panel=subprocess.Popen([str(ROOT/'tools/ldm-panel.exe'),str(self.panel_dir/'packet.txt'),
            str(self.panel_dir/'state.txt'),str(self.panel_dir/'heartbeat'),str(self.panel_dir/'stop')],
            env=ENV,creationflags=subprocess.CREATE_NO_WINDOW)

    def close_panel(self):
        if self.panel:
            (self.panel_dir/'stop').touch()
            try:
                self.panel.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.panel.terminate()
                self.panel.wait(timeout=2)
        self.panel=None

    def panel_alive(self):
        if not self.panel or self.panel.poll() is not None:
            return False
        heartbeat=self.panel_dir/'heartbeat'
        return heartbeat.exists() and time.time()-heartbeat.stat().st_mtime<3

    def panel_input(self):
        if not self.panel_dir or not self.panel:
            return
        packet=self.panel_dir/'packet.txt'
        if not packet.exists():
            return
        try:
            data=list(map(int,packet.read_text(encoding='utf-8').split()))
        except ValueError:
            return
        if len(data)!=18 or data[0]<=self.panel_sequence:
            return
        sequence,action,*v=data
        if action==4:
            self.perform('close-pattern',{})
            return
        if action in (5,6,7):
            self.save_draft({'sf':v[:5],'dc':v[5],'blend':v[6],'dynamic':v[7],'alpha':v[8:]})
            self.panel_sequence=sequence
            self.submit('backlight',{'level':action-4})
            return
        if action in (1,2):
            self.set_area((self.state['area']+(-1 if action==1 else 1))%len(AREAS))
        elif action in (0,3):
            c=validate(STOCK_BY_LEVEL[self.backlight_level]) if action==3 else {'sf':v[:5],'dc':v[5],'blend':v[6],'dynamic':v[7],'alpha':v[8:]}
            self.request_live(c)
        else:
            return
        self.panel_sequence=sequence

    def submit(self,operation,data):
        if self.state['busy'] and operation!='restore':
            raise ValueError('上一操作仍在执行，请稍等')
        self.state['busy']=True
        self.state['error']=''
        def job():
            try:
                with self.lock:
                    self.perform(operation,data)
            except Exception as e:
                with self.lock:
                    self.state['error']=str(e)
                    self.event('操作未完成',operation=operation,error=str(e))
            finally:
                self.state['busy']=False
        self.pool.submit(job)

    def read_state(self,include_signal=True,timeout=20):
        self.count+=1
        dest=self.folder/f'read-{self.count}'
        dest.mkdir()
        self.state['native']=native('getBatch',dest,KEYS,timeout=timeout)
        if include_signal:self.state['signal']=native('getInputSignal',dest,timeout=timeout)
        self.state['backlight_level']=int(self.state['native']['g_video__vid_local_dimming'])
        self.state['connected']=True
        return self.state['native']

    def preflight(self):
        state=self.read_state()
        if not hdr_input(state) or state.get('g_disp__disp_back_light')!='100' or state.get('g_video__vid_local_dimming') not in ('1','2','3'):
            raise ValueError('等待实际HDR输入、有效分区档位与背光100；不限定画面预设名称')
        if self.state['signal'].get('input.width')!='3840' or self.state['signal'].get('input.height')!='2160':
            raise ValueError('当前图样和1像素目标要求3840×2160输入')

    def label(self):
        if not self.pattern_dir:
            return
        c=self.state['config']
        text=('实时调参 · F8 参数面板' if self.active and self.active['mode']=='live' else
              f"{self.state['phase']} SF{c['sf'][0]} A{c['alpha'][0]} D{c['dynamic']}")
        if self.active and self.active['mode']!='live':
            text+=f" {self.state['remaining']}s"
        temp=self.pattern_dir/'status.tmp'
        temp.write_text(text,encoding='utf-8')
        temp.replace(self.pattern_dir/'status.txt')

    def set_area(self,index):
        if type(index) is not int or not 0<=index<len(AREAS):
            raise ValueError('未知窗口面积')
        self.state['area']=index
        if self.pattern_dir:
            temp=self.pattern_dir/'live.tmp'
            temp.write_text(str(AREAS[index][1]/100),encoding='utf-8')
            temp.replace(self.pattern_dir/'live.txt')

    def show_pattern(self):
        if self.pattern and self.pattern.poll() is None:
            return
        self.count+=1
        self.pattern_dir=self.folder/f'pattern-{self.count}'
        self.pattern_dir.mkdir()
        self.key_offset=0
        self.label()
        self.set_area(self.state['area'])
        self.pattern=subprocess.Popen([str(ROOT/'tools/hdr-pattern.exe'),'0',
            str(AREAS[self.state['area']][1]/100),'4000',str(self.pattern_dir/'check.json'),
            'single','references',str(self.pattern_dir/'status.txt'),str(self.pattern_dir/'live.txt'),
            str(self.pattern_dir/'keys.txt'),'windowed'],env=ENV,creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,stderr=(self.pattern_dir/'error.txt').open('w',encoding='utf-8'))
        end=time.monotonic()+6
        while not (self.pattern_dir/'check.json').exists():
            if self.pattern.poll() is not None or time.monotonic()>end:
                raise RuntimeError('HDR图样未启动，请确认Windows HDR已开启')
            time.sleep(.1)
        check=json.loads((self.pattern_dir/'check.json').read_text(encoding='utf-8'))
        if check['wrong_pixels']:
            raise RuntimeError('GPU图样校验失败')
        self.state['pattern']=True
        self.event('原生HDR图样已显示',check=check)

    def finish(self):
        if not self.active:
            return
        active=self.active
        self.device('shell','touch '+active['remote']+'/stop')
        end=time.monotonic()+18
        while time.monotonic()<end:
            raw=self.device('shell','cat '+active['remote']+'/result.txt',check=False)
            if '__lab_session_complete=1' in raw:
                self.complete(raw)
                return
            time.sleep(.2)
        raise RuntimeError('未收到恢复回执；设备端仍有12秒失联恢复，请重新连接核对')

    def complete(self,raw):
        active=self.active
        if '__lab_session_complete=1' in raw:
            raw=self.device('shell','cat '+active['remote']+'/result.txt')
        (active['folder']/'result.txt').write_text(raw,encoding='utf-8')
        self.active=None
        self.state.update(active=False,remaining=0,phase='原厂',config=validate(STOCK),pip_bypass=False)
        restored='__native_restored=1' in raw and '__exit=0' in raw and 'restore_pip_return=0' in raw and re.search(r'RESULT: SET g_video__vid_local_dimming to 3 .*return: 0',raw)
        self.state['restoration']='设备端恢复回执正常' if restored else '恢复未确认，请重连核对'
        self.event(self.state['restoration'],session=str(active['folder']))
        self.state['last_trial']=json.loads((active['folder']/'plan.json').read_text(encoding='utf-8'))
        self.label()
        state=self.read_state()
        if state['g_video__vid_local_dimming']!='3' or not restored:
            raise RuntimeError('恢复核对未通过，请使用恢复原厂按钮')

    def run(self,mode,config,seconds,full_screen):
        self.finish()
        if self.pattern and self.pattern.poll() is not None:
            self.pattern=None
            self.state['pattern']=False
        self.preflight()
        if full_screen:
            if self.pattern and self.pattern.poll() is None:
                self.pattern.terminate()
                self.pattern.wait(timeout=3)
            self.show_pattern()
        self.count+=1
        folder=self.folder/f'trial-{self.count}'
        folder.mkdir()
        remote=REMOTE+'/lab_'+self.folder.name[:15]+'_'+str(self.count)
        config=validate(config)
        values=[*config['sf'],config['dc'],config['blend'],config['dynamic'],*config['alpha']]
        level=0 if mode=='off' else self.backlight_level if mode=='live' else 3
        pip=int(mode=='live' and getattr(self,'software_abl',True)==False)
        self.device('shell','mkdir -p '+remote)
        self.device('push',str(ROOT/'tools/mi-ldm-lab'),remote+'/worker')
        exe='/data/data/mitv.service/cache/MIResearch-lab-worker'
        set_level=lambda n: f'CLASSPATH={JAR} /system/bin/app_process /data/data/mitv.service/cache MIHDRBridge set g_video__vid_local_dimming {n} 3'
        script=folder/'run.sh'
        script.write_text('{\ncp '+remote+'/worker '+exe+'\nchmod 755 '+exe+'\n'
            +set_level(level)+'\n'
            +exe+' '+str(seconds)+' '+('0' if mode=='off' else '1')+' '+remote+' '+' '.join(map(str,[*values,pip]))
            +'\ncode=$?\n'+set_level(3)+'\necho __exit=$code\necho __lab_session_complete=1\n} >'+remote+'/result.txt 2>&1\n',
            encoding='utf-8',newline='\n')
        (folder/'plan.json').write_text(json.dumps({'mode':mode,'seconds':seconds,'config':config,
            'backlight_level':level,'pip_bypass':bool(pip),
            'area':AREAS[self.state['area']],'fine_register_readback':False},indent=2,ensure_ascii=False),encoding='utf-8')
        self.device('push',str(script),remote+'/run.sh')
        self.device_heartbeat(remote)
        self.active={'remote':remote,'folder':folder,'end':time.monotonic()+seconds,'mode':mode}
        self.device('shell',tv_command(['sh',remote+'/run.sh']))
        end=time.monotonic()+8
        while time.monotonic()<end:
            raw=self.device('shell','cat '+remote+'/result.txt',check=False)
            if '__lab_session_complete=1' in raw:
                self.complete(raw)
                raise RuntimeError('实验提前结束，请查看回执')
            if '__applied=1' in raw:
                if not re.search(r'RESULT: SET g_video__vid_local_dimming to '+str(level)+r' .*return: 0',raw):
                    self.finish()
                    raise RuntimeError('控光档位回执未确认')
                break
            time.sleep(.1)
        else:
            self.finish()
            raise RuntimeError('未收到应用回执')
        state=self.read_state()
        if state['g_video__vid_local_dimming']!=str(level):
            self.finish()
            raise RuntimeError('控光档位原生回读不匹配')
        self.beat=time.monotonic()
        self.last_device_beat=time.monotonic()
        self.state.update(active=True,config=config,remaining=seconds,phase=BACKLIGHT_LEVELS[level] if mode=='live' else '控光关' if mode=='off' else '实验',backlight_level=level,pip_bypass=bool(pip),restoration='退出或失联后恢复' if mode=='live' else '倒计时后恢复')
        if mode=='live':
            self.sent_sequence=0
            self.ack_sequence=0
            with self.request_lock:
                self.wanted_sequence+=1
            self.pending_at=0
            self.publish_live()
        self.label()
        self.event('临时实验已应用',mode=mode,config=config,seconds=seconds)

    def switch_backlight(self,level):
        config=validate(self.backlight_presets[str(level)])
        if not self.active or self.active['mode']!='live':
            self.backlight_level=level
            self.save_draft(config)
            self.run('live',config,0,False)
            self.show_panel()
            return
        self.device_heartbeat(self.active['remote'])
        self.count+=1
        folder=self.folder/f'backlight-{self.count}'
        folder.mkdir()
        remote=self.active['remote']
        receipt=remote+'/backlight-'+str(self.count)+'.txt'
        script=folder/'switch.sh'
        script.write_text('{\n'+f'CLASSPATH={JAR} /system/bin/app_process /data/data/mitv.service/cache MIHDRBridge set g_video__vid_local_dimming {level} 3'
            +'\necho __complete=1\n} >'+receipt+' 2>&1\n',encoding='utf-8',newline='\n')
        self.device('push',str(script),remote+'/switch.sh')
        self.device('shell',tv_command(['sh',remote+'/switch.sh']))
        end=time.monotonic()+8
        while time.monotonic()<end:
            raw=self.device('shell','cat '+receipt,check=False)
            if '__lab_session_complete=1' in raw:
                break
            time.sleep(.1)
        (folder/'result.txt').write_text(raw,encoding='utf-8')
        if not re.search(r'RESULT: SET g_video__vid_local_dimming to '+str(level)+r' .*return: 0',raw):
            raise RuntimeError('控光切档回执未确认')
        state=self.read_state()
        if state['g_video__vid_local_dimming']!=str(level):
            raise RuntimeError('控光切档原生回读不匹配')
        self.backlight_level=level
        with self.request_lock:
            self.save_draft(config)
            self.wanted_sequence+=1
            self.pending_at=0
        self.publish_live()
        self.state['phase']=BACKLIGHT_LEVELS[level]
        self.beat=time.monotonic()
        self.event('已切换控光预设',level=level,config=config,pip_bypass=level==2)

    def perform(self,op,data):
        if op=='connect':
            self.device('get-state')
            self.read_state()
            self.state['phase']='原厂待实验' if not self.active else self.state['phase']
            self.event('ADB读取成功')
        elif op=='run':
            self.run(data['mode'],data['config'],data['seconds'],data.get('full_screen',True))
        elif op=='live':
            if data.get('panel',True):
                self.close_panel()
            if not data.get('full_screen',True) and data.get('panel',True) and self.pattern:
                self.perform('close-pattern',{})
            self.run('live',data['config'],0,data.get('full_screen',True))
            if data.get('panel',True):
                self.show_panel()
        elif op=='backlight':
            self.switch_backlight(data['level'])
        elif op=='pattern':
            self.set_area(data['area'])
            if not self.pattern or self.pattern.poll() is not None:
                self.preflight()
                self.show_pattern()
        elif op=='area':
            self.set_area(data['area'])
        elif op=='restore':
            self.close_panel()
            if self.active:
                self.finish()
            else:
                self.run('trial',STOCK,3,False)
                self.finish()
        elif op=='close-pattern':
            self.close_panel()
            if self.pattern and self.pattern.poll() is None:
                self.pattern.terminate()
                self.pattern.wait(timeout=3)
            self.pattern=None
            self.pattern_dir=None
            self.state['pattern']=False
            self.finish()

    def tick(self):
        while not self.closing:
            try:
                with self.lock:
                    self.panel_input()
                    if self.panel and self.panel.poll() is not None:
                        self.panel=None
                        self.finish()
                    if self.active:
                        self.state['remaining']=0 if self.active['mode']=='live' else max(0,int(self.active['end']-time.monotonic()))
                        if time.monotonic()-self.beat>10 and not self.panel_alive():
                            self.finish()
                        else:
                            self.publish_live()
                            if time.monotonic()-self.last_device_beat>3:
                                self.device_heartbeat(self.active['remote'])
                                self.last_device_beat=time.monotonic()
                            if time.monotonic()-self.last_result_read>1:
                                raw=self.device('shell','tail -n 80 '+self.active['remote']+'/result.txt')
                                self.last_result_read=time.monotonic()
                                acknowledgements=re.findall(r'applied_sequence=(\d+)',raw)
                                if acknowledgements:
                                    self.ack_sequence=int(acknowledgements[-1])
                                    if self.ack_sequence==self.sent_sequence:
                                        self.state['config']=self.sent_config
                                        self.state['pip_bypass']=bool(self.sent_pip)
                                if '__lab_session_complete=1' in raw:
                                    self.complete(raw)
                    if self.pattern and self.pattern.poll() is not None:
                        if self.pattern.returncode and self.pattern_dir:
                            error_file=self.pattern_dir/'error.txt'
                            if error_file.exists():
                                self.state['error']='图样已停止：'+error_file.read_text(encoding='utf-8',errors='replace')
                        self.pattern=None
                        self.state['pattern']=False
                        if not self.panel_alive() and not getattr(self,'live_debug',False):
                            self.finish()
                        self.pattern_dir=None
                    if self.pattern and self.pattern_dir:
                        keys=self.pattern_dir/'keys.txt'
                        if keys.exists():
                            lines=keys.read_text(encoding='utf-8').splitlines()
                            for line in lines[self.key_offset:]:
                                key=line.split(',')[-1]
                                if key in ('previous','next'):
                                    self.set_area((self.state['area']+(-1 if key=='previous' else 1))%len(AREAS))
                                elif key in ('stock','trial','off'):
                                    op='restore' if key=='stock' else 'run'
                                    self.submit(op,{'mode':key,'config':self.draft,'seconds':12 if key=='off' else self.seconds,'full_screen':False})
                            self.key_offset=len(lines)
                    if self.active or self.pattern:
                        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
                    else:
                        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                    self.label()
                    self.panel_state()
                    if hasattr(self,'tick_budget'):
                        self.tick_budget()
            except Exception as e:
                self.state['error']=str(e)
                # Local pattern/receipt errors are not proof that the ADB transport disconnected.
                if isinstance(e,ADBConnectionError):self.state['connected']=False
            time.sleep(.1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def reply(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get('Host')!=f'127.0.0.1:{PORT}':
            self.reply({'error':'localhost only'},403)
            return
        if self.path=='/api/state':
            self.reply(self.server.bridge.snapshot())
        elif urlparse(self.path).path in ('/','/index.html'):
            raw=(ROOT/'lab/index.html').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.reply({'error':'not found'},404)

    def do_POST(self):
        b=self.server.bridge
        if self.headers.get('Origin')!=URL or self.headers.get('X-MI-Token')!=b.token:
            self.reply({'error':'请从本机实验台操作'},403)
            return
        try:
            n=int(self.headers.get('Content-Length',0))
            if n>16000:
                raise ValueError('请求过大')
            data=json.loads(self.rfile.read(n) or b'{}')
            op=self.path.removeprefix('/api/')
            if op=='heartbeat':
                b.beat=time.monotonic()
            elif op=='update':
                b.request_live(data['config'])
                b.beat=time.monotonic()
            elif op=='live':
                config=validate(data['config'])
                b.save_draft(config)
                b.submit('live',{'config':config,'full_screen':bool(data.get('full_screen',True)),'panel':True})
            elif op=='backlight':
                level=data['level']
                if type(level) is not int or level not in BACKLIGHT_LEVELS:
                    raise ValueError('未知背光档位')
                b.submit('backlight',{'level':level})
            elif op in ('draft','preset','note'):
                with b.lock:
                    if op=='note':
                        text=str(data.get('text','')).strip()[:2000]
                        if not text:
                            raise ValueError('请先填写观察')
                        b.event('人工观察',note=text,config=b.state['config'],draft=b.draft,
                                last_trial=b.state.get('last_trial'),area=AREAS[b.state['area']])
                    else:
                        b.save_draft(data['config'])
                        seconds=data.get('seconds',b.seconds)
                        if type(seconds) is not int or not 10<=seconds<=180:
                            raise ValueError('每次实验10～180秒')
                        b.seconds=seconds
                        (ROOT/'state/lab-settings.json').write_text(json.dumps(b.draft,indent=2),encoding='utf-8')
                        if op=='preset':
                            name=str(data.get('name','')).strip()[:40]
                            if not name:
                                raise ValueError('请填写方案名称')
                            if name in PRESETS:
                                raise ValueError('内置方案不能覆盖，请换一个名称')
                            b.presets[name]=b.draft
                            (ROOT/'state/lab-presets.json').write_text(json.dumps(b.presets,ensure_ascii=False,indent=2),encoding='utf-8')
            elif op in ('connect','run','pattern','area','restore','close-pattern'):
                if op=='run':
                    data['config']=validate(data['config'])
                    if data.get('mode') not in ('trial','off'):
                        raise ValueError('未知模式')
                    if type(data.get('seconds')) is not int or not 10<=data['seconds']<=180:
                        raise ValueError('每次实验10～180秒')
                    if data['mode']=='off':
                        data['seconds']=12
                    if type(data.get('full_screen',True)) is not bool:
                        raise ValueError('未知图样选项')
                b.submit(op,data)
            else:
                raise ValueError('未知操作')
            self.reply({'ok':True})
        except (ValueError,KeyError,TypeError) as e:
            self.reply({'error':str(e)},400)


def main():
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    server.bridge=Bridge()
    print(URL,flush=True)
    try:
        server.serve_forever()
    finally:
        with server.bridge.lock:
            server.bridge.finish()
            server.bridge.closing=True
        server.server_close()


if __name__=='__main__':
    main()
