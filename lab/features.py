"""Portable pattern controls, read-only sensors, and explicit nit estimates."""
from datetime import datetime, timezone
import json
import math
import re
import ctypes
import msvcrt
import os
import time
from pathlib import Path

PATTERN = dict(pixel_width=0, pixel_height=0, rows=1, cols=1, area_percent=50,
               input_nits=4000, background_nits=0, label=True, mode='windowed',
               seconds=0, monitor=0)


def validate_pattern(data):
    if not isinstance(data, dict) or set(data) != set(PATTERN):
        raise ValueError('图样参数不完整')
    for k, lo, hi in [('pixel_width',0,16384),('pixel_height',0,16384),
                      ('rows',1,64),('cols',1,64),('monitor',0,15)]:
        if type(data[k]) is not int or not lo <= data[k] <= hi:
            raise ValueError(k + ' 超出范围')
    for k, hi in [('area_percent',100),('input_nits',10000),('background_nits',10000),('seconds',86400)]:
        if type(data[k]) not in (int,float) or not math.isfinite(data[k]) or not 0 <= data[k] <= hi:
            raise ValueError(k + ' 超出范围')
    if bool(data['pixel_width']) != bool(data['pixel_height']):
        raise ValueError('宽和高必须同时为0（面积模式）或同时为正整数')
    if type(data['label']) is not bool or data['mode'] not in ('fullscreen','windowed'):
        raise ValueError('未知图样显示方式')
    return dict(data)


def write_pattern(path, config, sequence):
    config=validate_pattern(config)
    values={'sequence':sequence, **{k:int(v) if k=='label' else v for k,v in config.items()
                                 if k not in ('mode','seconds','monitor')}}
    temp=path.with_suffix('.tmp')
    temp.write_text(''.join(f'{k} {v}\n' for k,v in values.items()),encoding='ascii')
    replace_pattern_file(temp,path)


def replace_pattern_file(temp,path):
    # Windows may briefly retain a delete-pending handle during rapid renderer reads.
    for attempt in range(6):
        try:temp.replace(path);return
        except PermissionError:
            if attempt==5:raise
            time.sleep(.002*(attempt+1))


def read_pattern_check(path):
    # The renderer atomically replaces this file. A normal Windows CRT open denies delete-sharing.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    create=kernel.CreateFileW;create.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p];create.restype=ctypes.c_void_p
    for attempt in range(4):
        handle=create(str(path),0x80000000,7,None,3,0x80,None)
        if handle!=ctypes.c_void_p(-1).value:
            with open(msvcrt.open_osfhandle(handle,os.O_RDONLY),encoding='utf-8') as source:return json.load(source)
        error=ctypes.get_last_error()
        if error not in (5,32) or attempt==3:raise ctypes.WinError(error)
        time.sleep(.001)


# No writes, enable switches, emulated temperatures or trip-point modifications.
SENSOR_SCRIPT = r'''emit() {
 p="$1"; kind="$2"; name="$3"
 [ -e "$p" ] || [ "$kind" = thermal ] || return
 printf '__node\t%s\t%s\t%s\n' "$kind" "$p" "$name"
 value=$(cat "$p" 2>&1); rc=$?
 printf '__rc\t%s\n%s\n__end\n' "$rc" "$value"
}
for d in /sys/class/thermal/thermal_zone*; do
 [ -d "$d" ] || [ -L "$d" ] || continue
 name=$(cat "$d/type" 2>/dev/null)
 emit "$d/temp" thermal "$name"
done
for d in /sys/class/hwmon/hwmon*; do
 [ -d "$d" ] || continue
 name=$(cat "$d/name" 2>/dev/null)
 for p in "$d"/temp*_input; do
  label=$(cat "${p%_input}_label" 2>/dev/null)
  emit "$p" hwmon "$name $label"
 done
done
for d in /sys/bus/iio/devices/iio:device*; do
 [ -d "$d" ] || continue
 name=$(cat "$d/name" 2>/dev/null)
 for p in "$d"/in_illuminance* "$d"/in_temp* "$d"/in_intensity*; do
  case "$p" in *_input|*_raw|*_scale|*_offset) emit "$p" iio "$name";; esac
 done
done
echo __sensors_complete=1
'''


def parse_sensors(raw):
    result=[]; current=None
    for line in raw.splitlines():
        if line.startswith('__node\t'):
            _,kind,path,name=line.split('\t',3)
            current=dict(kind=kind,path=path,name=name or Path(path).parent.name,raw='',exit_status=None)
        elif current is not None and line.startswith('__rc\t'):
            current['exit_status']=int(line.split('\t')[1])
        elif current is not None and line=='__end':
            row=current;current=None
            row.update(value=None,unit='raw',status='unavailable',location='设备标签；物理位置未确认')
            if row['exit_status']==0:
                try:
                    n=float(row['raw'].strip())
                    if not math.isfinite(n): raise ValueError()
                    row.update(value=n,status='ok')
                    if row['kind'] in ('thermal','hwmon'):
                        row.update(value=n/1000,unit='°C',conversion='raw / 1000 (Linux thermal/hwmon ABI)')
                    elif 'illuminance' in row['path'] and row['path'].endswith('_input'):
                        row.update(unit='lux',conversion='processed IIO illuminance')
                    elif 'temp' in row['path'] and row['path'].endswith('_input'):
                        row.update(value=n/1000,unit='°C',conversion='processed IIO temperature / 1000')
                except ValueError:
                    row['status']='non_numeric'
            result.append(row)
        elif current is not None:
            current['raw']+=(line+'\n')
    # Only convert raw IIO channels when their own documented scale is available.
    bypath={r['path']:r for r in result}
    for row in result:
        if row['kind']!='iio' or not row['path'].endswith('_raw') or row['status']!='ok': continue
        stem=row['path'][:-4];scale=bypath.get(stem+'_scale');offset=bypath.get(stem+'_offset')
        if scale and scale['status']=='ok' and (not offset or offset['status']=='ok'):
            value=(float(row['raw'])+(offset['value'] if offset else 0))*scale['value']
            row.update(value=value,conversion='(raw + offset) * scale')
            if 'illuminance' in stem: row['unit']='lux'
            elif '/in_temp' in stem: row.update(value=value/1000,unit='°C',conversion='(raw + offset) * scale / 1000')
    return dict(captured_at=datetime.now(timezone.utc).isoformat(),complete='__sensors_complete=1' in raw,
                sensors=result,note='未发现节点不等于没有传感器；不把芯片温度当作面板温度。')


def android_sensors(thermal, sensor):
    """Use Android's existing sensor clients; never enable or impersonate a sensor."""
    rows=[]
    current=thermal.partition('Current temperatures from HAL:')[2].partition('Current cooling devices')[0]
    readings=re.findall(r'Temperature\{mValue=([-+\d.]+), mType=(\d+), mName=([^,]+), mStatus=(\d+)\}',current)
    alias=bool(readings) and len({r[0] for r in readings})==1 and len(readings)>1
    for raw,kind,name,status in readings:
        # This firmware reports the same value under 14 logical names, including "display".
        # Expose one CPU-labelled HAL report, not 14 purported physical thermometers.
        if kind!='0':continue
        rows.append(dict(kind='android-thermal',path='dumpsys thermalservice / Current temperatures from HAL / CPU',
            name='HAL CPU上报'+('（多个逻辑标签共用同一值）' if alias else ''),raw=raw,value=float(raw),unit='°C',
            status='ok',exit_status=0,location='非面板/背光专用测温；HAL逻辑名称',thermal_status=int(status),
            alias_count=len(readings) if alias else 1))
    light_names=re.findall(r'^0x[0-9a-f]+\) (.*?) \| .*type: android.sensor.light\(5\)',sensor,re.M)
    recent=sensor.partition('Recent Sensor events:')[2].partition('Active sensors:')[0]
    for name in light_names:
        block=recent.partition(name+': last ')[2]
        if not block:continue
        events=re.findall(r'\d+ \(ts=([\d.]+), wall=([^\)]+)\)\s+([-+\d.]+),',block.split('\n\n')[0])
        if not events:continue
        ts,wall,raw=events[-1]
        rows.append(dict(kind='android-light',path='dumpsys sensorservice / Recent Sensor events',name=name,
            raw=raw,value=float(raw),unit='lux',status='ok',exit_status=0,event_monotonic_seconds=float(ts),
            event_wall_time=wall,location='环境光；不是屏幕输出nit',note='最后上报事件；相同照度时可能不刷新'))
    return rows


CALIBRATION = dict(window_percent=100,reference_raw=31245,reference_nits=1236,
                   reference_budget=41,level=3,tone=5,measured=False,
                   source='用户中档全屏参考1236 nit；高档41/86读数31245。比例估算，未做光学标定。')


def validate_calibration(c):
    if not isinstance(c,dict) or set(c)!=set(CALIBRATION): raise ValueError('标定字段不完整')
    for k,hi in [('window_percent',100),('reference_raw',65535),('reference_nits',10000),('reference_budget',86)]:
        if type(c[k]) not in (int,float) or not math.isfinite(c[k]) or not 0<c[k]<=hi: raise ValueError('无效标定 '+k)
    if c['level'] not in (1,2,3) or c['tone'] not in (0,1,2,5) or type(c['measured']) is not bool:
        raise ValueError('无效标定模式')
    if not isinstance(c['source'],str) or len(c['source'])>1000: raise ValueError('无效来源')
    return dict(c)


def estimate(raw, budget, area, level, tone, calibration):
    c=validate_calibration(calibration)
    match=abs(area-c['window_percent'])<.01 and level==c['level'] and tone==c['tone']
    return dict(setting_nits=round(budget/c['reference_budget']*c['reference_nits'],1) if match and budget is not None else None,
                reading_nits=round(raw/c['reference_raw']*c['reference_nits'],1) if match and raw is not None else None,
                calibrated_context=match,kind='估算 nit，非光学实测',source=c['source'])

