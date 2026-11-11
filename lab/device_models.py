"""Model selection from local monitor identity; firmware confirms the panel before writes."""
from pathlib import Path
from functools import lru_cache
import json,math,subprocess,os
ROOT=Path(__file__).resolve().parents[1]
ACTIVE_MODEL='32u-2026';ACTIVE_TONE=5
@lru_cache(maxsize=1)
def registry():return json.loads((ROOT/'resources/models/registry.json').read_text(encoding='utf-8'))['models']
def spec(model=None):return registry()[model or ACTIVE_MODEL]
def defaults(level,model=None):
    values=spec(model)['variants'][spec(model)['default_variant']]['defaults'][str(level)]
    return {k:list(v) if isinstance(v,list) else v for k,v in values.items()}
@lru_cache(maxsize=2)
def window_reference(model=None):return json.loads((ROOT/'resources/models'/(model or ACTIVE_MODEL)/'window-reference.json').read_text(encoding='utf-8'))
def identify_monitor(row):
    name=str(row.get('name',''));instance=str(row.get('instance',''));w=float(row.get('width_cm',0) or 0);h=float(row.get('height_cm',0) or 0);inch=math.hypot(w,h)/2.54
    xiaomi='DISPLAY\\XMI' in instance.upper() or any(n in name.lower() for n in ('redmi','g pro','gpro','xiaomi'))
    explicit='27u' if '27u' in name.lower().replace(' ','') else '32u' if '32u' in name.lower().replace(' ','') else None
    size='27u' if 25.5<=inch<=28.5 else '32u' if 30<=inch<=33.5 else None
    model=(explicit or size)+'-2026' if xiaomi and (explicit or size) else None
    if explicit and size and explicit!=size:model=None
    return {**row,'diagonal_estimate':round(inch,2) if inch else None,'model_id':model,'basis':'EDID型号/物理尺寸初筛；2026屏型待ADB复核' if model else '未识别为受支持的27/32寸系列，未默认套用32寸'}
def detect():
    script=r'''[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);$id=Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID;$dims=Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBasicDisplayParams;@($id | Where-Object {$_.Active} | ForEach-Object {$d=$dims|Where-Object InstanceName -eq $_.InstanceName;[pscustomobject]@{instance=$_.InstanceName;name=(-join($_.UserFriendlyName|Where-Object {$_}|ForEach-Object {[char]$_}));product=(-join($_.ProductCodeID|Where-Object {$_}|ForEach-Object {[char]$_}));width_cm=$d.MaxHorizontalImageSize;height_cm=$d.MaxVerticalImageSize}})|ConvertTo-Json -Compress'''
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=12,creationflags=subprocess.CREATE_NO_WINDOW)
    if p.returncode:return dict(monitors=[],error=p.stderr.strip())
    rows=json.loads(p.stdout or '[]');rows=rows if isinstance(rows,list) else [rows]
    monitors=[identify_monitor(row) for row in rows];return dict(monitors=monitors,error='',needs_choice=True)
def panel_identity(info):
    path=info['factory_ini']
    for key,model in registry().items():
        for name,variant in model['variants'].items():
            if path==variant['ldm_ini']:return dict(model_id=key,variant=name,led_type=model['led_type'],basis='原厂活动屏型路径',verified=True)
    return dict(model_id=None,variant=None,verified=False,basis='不支持的屏型（旧27寸107不作为2026版）')
def activate(model,tone=5):
    global ACTIVE_MODEL,ACTIVE_TONE
    if model not in registry() or tone not in (0,1,2,5):raise ValueError('无效机型/亮暗模式')
    changed=(ACTIVE_MODEL,ACTIVE_TONE)!=(model,tone);ACTIVE_MODEL=model;ACTIVE_TONE=tone;return changed
