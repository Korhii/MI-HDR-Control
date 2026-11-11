"""Owned runtime-module session and the verified OEM BSP parameter bridge."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import uuid
from mi_probe import ROOT,ENV,REMOTE,adb,tv_command


def sample(folder, value=None, running=None, policy=None):
    if value is not None and (type(value) is not int or not 0<=value<=86):raise ValueError('高档预算范围0～86')
    if running is not None and type(running) is not bool:raise ValueError('无效会话状态')
    folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'channel.json'
    if marker.exists():remote=json.loads(marker.read_text(encoding='utf-8'))['remote']
    else:
        remote=REMOTE+'/budget_'+uuid.uuid4().hex
        adb('shell','mkdir -p '+remote)
        marker.write_text(json.dumps({'remote':remote}),encoding='utf-8')
    local=ROOT/'tools/bsp-budget-parameters.so'
    deployed=folder/'bridge-size.txt'
    fingerprint=str(local.stat().st_mtime_ns)+':'+str(local.stat().st_size)
    if not deployed.exists() or deployed.read_text()!=fingerprint:
        adb('push',str(local),remote+'/bridge.so');deployed.write_text(fingerprint)
    variables=[]
    if value is not None:variables.append('MI_BUDGET_SET='+str(value))
    if running is not None:variables.append('MI_BUDGET_RUN='+str(int(running)))
    if policy is not None:
        if not all(c in '0123456789,' for c in policy):raise ValueError('无效累计ABL数据')
        variables.append('MI_OEM_ABL_CONFIG='+policy)
    private='/data/data/mitv.service/cache/MIResearch-bsp-budget.so'
    script=folder/'read.sh'
    script.write_text('{\ncp '+remote+'/bridge.so '+private+'\ntimeout 5 env '+' '.join(variables)
        +' LD_LIBRARY_PATH=/vendor/lib64:/vendor/lib64/hw:/system/lib64 LD_PRELOAD='+private
        +' /system/bin/app_process /system/bin\necho bridge_exit=$?\necho __bridge_done=1\n} >'+remote+'/result.txt 2>&1\n',encoding='utf-8',newline='\n')
    adb('push',str(script),remote+'/read.sh');adb('shell','rm -f '+remote+'/result.txt')
    adb('shell',tv_command(['sh',remote+'/read.sh']))
    end=time.monotonic()+8
    while time.monotonic()<end:
        raw=adb('shell','cat '+remote+'/result.txt',check=False)
        if '__bridge_done=1' in raw:break
        time.sleep(.05)
    (folder/'stdout.txt').write_text(raw,encoding='utf-8')
    values={line.split('=',1)[0]:line.split('=',1)[1] for line in raw.splitlines() if '=' in line}
    if values.get('bridge_exit')!='0' or values.get('__complete')!='1':raise RuntimeError('预算读写桥未完成：'+raw)
    names=['budget','budget_used','frames','lease_end','tick','raw_apl','raw_spi','window','level']
    if any(int(values.get('read_return.'+n,'0'))<=0 for n in names):raise RuntimeError('预算模块未加载，或参数读取不可用')
    result={n:int(values[n]) for n in names}
    if value is not None and (values.get('write_return')!='1' or result['budget']!=value):raise RuntimeError('预算设置值回读不一致')
    if running is not None and values.get('lease_write_return')!='1':raise RuntimeError('心跳写入失败；十秒到期将退回24')
    if policy is not None and values.get('policy_write_return')!='1':raise RuntimeError('累计ABL写入未完成')
    for name in ('enabled', 'l_th', 'e0', 'divisor', 'r_reset', 'k', 'energy', 'r_prev', 'gain_next', 'load', 'recovery', 'charge', 'delta', 'triggered', 'threshold', 'generation', 'gain_used', 'active', 'k_min', 'k_max', 'c_max', 'g_base', 'native_gain', 'stat_floor', 'factory_l_th', 'factory_e0', 'factory_divisor', 'factory_r_reset', 'factory_g_base', 'original_cap', 'post_cap', 'native_k', 'native_energy', 'native_r_prev'):
        if values.get(name,'').isdigit():result[name]=int(values[name])
    result.update(raw=result['raw_apl'],captured_at=datetime.now(timezone.utc).isoformat(),status='live-driver',
                  effective_high_only=False,effective_levels=[1,2,3],unit='internal driver units; not optical nits')
    (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def module(action,folder):
    if action not in ('load','unload'):raise ValueError(action)
    folder.mkdir(parents=True,exist_ok=True)
    command=[str(ROOT/'tools/python/python.exe'),'-u',str(ROOT/'scripts/budget_module_session.py'),action]
    with (folder/'stdout.txt').open('w',encoding='utf-8') as out,(folder/'stderr.txt').open('w',encoding='utf-8') as err:
        p=subprocess.run(command,env={**ENV,'PYTHONUTF8':'1'},stdout=out,stderr=err,timeout=140,creationflags=subprocess.CREATE_NO_WINDOW)
    (folder/'execution.json').write_text(json.dumps({'command':command,'exit_status':p.returncode}),encoding='utf-8')
    if p.returncode:raise RuntimeError('临时预算模块操作失败；查看 '+str(folder/'stdout.txt'))
