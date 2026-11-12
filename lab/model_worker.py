"""One main-thread firmware worker. PC emulation never shares a native runtime with HTTP threads."""
from pathlib import Path
import json,os,subprocess,sys,threading,gc,math
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
_process=None;_log=None;_lock=threading.RLock()
_calibrated={};_response_rows={}
def response_key(d):
    return json.dumps([d.get('model_id','32u-2026'),d.get('tone',5),d['level'],d['input_nits'],d['config']],sort_keys=True)
def row_estimate(row,data):
    area=data['area'];b=24 if data.get('factory_path') and data['level']==3 else data.get('budget_value',24)
    points=list(zip(row['areas'],[v[b] for v in row['nits']]))
    value=points[-1][1]
    if area<=points[0][0]:value=points[0][1]
    else:
        for (a,u),(c,v) in zip(points,points[1:]):
            if area<=c:
                t=(math.log10(area)-math.log10(a))/(math.log10(c)-math.log10(a)) if a>0 else (area-a)/(c-a)
                value=u+(v-u)*t;break
    return dict(nits=round(value,1),note=row['scope']+'；复用当前原厂响应，拟合计算不阻塞nit读取；AW不冒充分区输出',aw_gain_applied=False)

def call(op,**data):
    global _process,_log
    from local_asset_paths import require_ready
    require_ready()
    with _lock:
        if _process is None or _process.poll() is not None:
            if _log:_log.close()
            (ROOT/'logs').mkdir(exist_ok=True);_log=(ROOT/'logs/model-worker.log').open('w',encoding='utf-8')
            _process=subprocess.Popen([sys.executable,'-u',str(Path(__file__)),'--serve'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=_log,text=True,encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1'},creationflags=subprocess.CREATE_NO_WINDOW)
        _process.stdin.write(json.dumps(dict(op=op,**data),ensure_ascii=False)+'\n');_process.stdin.flush();line=_process.stdout.readline()
        if not line:raise RuntimeError('固件模型进程已退出；请查看便携目录 logs/model-worker.log')
        result=json.loads(line)
        if 'error' in result:raise ValueError(result['error'])
        value=result['result']
        if op=='predict':
            if len(_response_rows)>=8:_response_rows.pop(next(iter(_response_rows)))
            _response_rows[response_key(data)]=value
        return value
def current_estimate(**data):
    key=json.dumps({k:v for k,v in data.items() if k!='raw'},sort_keys=True)
    if key in _calibrated:return dict(_calibrated[key])
    if data.get('raw_kind')=='global-aw':
        row=_response_rows.get(response_key(data))
        if row:return row_estimate(row,data)
    if not _lock.acquire(blocking=False):return dict(nits=None,note='当前固件模型正在重算，AW原始读回不受影响；不显示旧上下文nit')
    try:
        result=call('calibrated',**data)
        if len(_calibrated)>=128:_calibrated.clear()
        _calibrated[key]=dict(result);return dict(result)
    finally:_lock.release()

def progress():
    path=ROOT/'state/model-progress.json'
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError,PermissionError):return None
def close():
    global _process,_log
    with _lock:
        if _process and _process.poll() is None:_process.stdin.write('{"op":"stop"}\n');_process.stdin.flush();_process.wait(timeout=15)
        if _process and _process.returncode not in (0,None):raise RuntimeError('模型进程未正常退出：'+str(_process.returncode))
        _process=None
        if _log:_log.close();_log=None

def serve():
    import firmware_model as f,ldf_response as l
    import device_models
    import abl_predict
    from abl_predict import forecast
    gc.disable()  # Release native callback cycles only between complete model requests.
    for line in sys.stdin:
        try:
            d=json.loads(line);op=d.pop('op')
            if op=='stop':break
            model=d.pop('model_id','32u-2026');tone=d.pop('tone',5)
            if device_models.activate(model,tone):
                for fn in (f.predict_cached,f.illumination_cached,l.ldf,l.blocks,l.anchor_corrections,l.correction,l.spill_offsets,l.stock_drive,abl_predict.peaks):fn.cache_clear()
                l.FIT_RESULTS.clear()
            if op=='predict':value=f.predict(**d)
            elif op=='forecast':value=forecast(**d)
            elif op=='fit':value=l.fit(**d)
            elif op=='calibrated':value=f.calibrated(tone=tone,**d)
            elif op=='validate':value=l.validate_fit(**d)
            else:raise ValueError('未知模型操作')
            result=dict(result=value)
        except Exception as e:result=dict(error=str(e))
        gc.collect()
        print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':serve()
