"""96x48 LDF -> original ARM64 scaling -> exact spatial port -> original ARM64 MCU.
Allowed auto controls are SF1/Alpha0..7; high Alpha bins prefer16. Optical and halo transfer remains
an estimate; historical DMA anchors correct the hardware-fixture discrepancy.
"""
from pathlib import Path
from functools import lru_cache
from array import array
from collections import OrderedDict
import base64,ctypes,hashlib,json,math,struct,threading,time,os,sys,multiprocessing
from concurrent.futures import ProcessPoolExecutor
import firmware_model as f
import device_models
from firmware_budget import BUFFER,MANIFEST
from firmware_hook import BSS_BASE,CFG

ROOT=Path(__file__).resolve().parents[1]
MODEL_ID=hashlib.sha256(b''.join(p.read_bytes() for p in (Path(__file__),ROOT/'lab/firmware_model.py',ROOT/'tools/response-math.dll',ROOT/'resources/ui/ldf-samples.json',ROOT/'resources/ui/alpha01-response.json'))).hexdigest()[:16]
AREAS=f.AREAS
KNOTS=[0,1,4,8,16,24,41,62,86]
SF=[0,4,8,16,32,64,128,192,255]
ALPHA=list(range(0,17,2))
AUTO=[0,.001,.01,.1,.5,1,2,5,10,25,50,75,100]
V=ctypes.c_uint16*1152;S=ctypes.c_uint8*5;W=ctypes.c_double*1152
LIB=ctypes.CDLL(str(ROOT/'tools/response-math.dll'))
LOCK=threading.RLock();PROGRESS={};FIT_RESULTS={};FIT_MATRICES={}

@lru_cache(maxsize=1)
def templates():return json.loads((ROOT/'resources/ui/ldf-samples.json').read_text(encoding='utf-8'))['rows']

@lru_cache(maxsize=256)
def ldf(area,q):
    rows=[r for r in templates() if r['area']==area]
    if rows:
        r=min(rows,key=lambda r:abs(f.pq(r['input_nits'])-f.pq(q)));raw=base64.b64decode(r['ldf'])
        if r['input_nits']==q:return raw,'historical-device-96x48'
        scale=f.pq(q)/f.pq(r['input_nits']) if q else 0
        return bytes(min(255,round(v*scale)) for v in raw),'PQ-scaled-LDF-estimate'
    if area<=0 or q<=0:return bytes(9216),'black'
    code=round(f.pq(q)*255);width=max(1,round(3840*math.sqrt(area/100)));height=max(1,round(2160*math.sqrt(area/100)));left=(3840-width)//2;top=(2160-height)//2
    raw=bytes(v for y in range(48) for x in range(96) for v in (max(0,min((x+1)*40,left+width)-max(x*40,left))*max(0,min((y+1)*45,top+height)-max(y*45,top))*code//1800,code if min((x+1)*40,left+width)>max(x*40,left) and min((y+1)*45,top+height)>max(y*45,top) else 0))
    return raw,'geometric-96x48-estimate'

@lru_cache(maxsize=128)
def blocks(area,q):
    raw,_=ldf(area,q);lookup={};indices=[]
    for y in range(24):
        for x in range(48):
            p=(y*2*96+x*2)*2;block=raw[p:p+4]+raw[p+192:p+196]
            if block not in lookup:lookup[block]=len(lookup)
            indices.append(lookup[block])
    return tuple(lookup),tuple(indices)

@lru_cache(maxsize=128)
def weights(area):
    roi=f.aperture_weights(area);side=math.sqrt(max(0,area)/100);half_x=48*side/2;half_y=24*side/2
    near=[];far=[]
    for y in range(24):
        for x in range(48):
            dx=abs(x+.5-24)-half_x;dy=abs(y+.5-12)-half_y
            near.append(1. if max(dx,dy)>0 and max(dx,dy)<=2 else 0.)
            far.append(1. if max(dx,dy)>2 else 0.)
    def normalize(v):return [x/max(1,sum(v)) for x in v]
    return W(*roi),W(*normalize(near)),W(*normalize(far))

def config_key(c):return json.dumps(c,sort_keys=True,separators=(',',':'))
def equal(a,b):return config_key(a)==config_key(b)

@lru_cache(maxsize=1)
def scaler():return f.Driver(f.stock(3))
@lru_cache(maxsize=6)
def mcu(level,device_type):
    a=f.Algorithm(level,device_type=device_type);f.install(a,value=24)
    a.stationary=[(b['start'],bytes(a.u.mem_read(b['start'],b['size']))) for b in MANIFEST['blocks'] if b['name'] in ('.bss','.data')]
    a.stationary.append((CFG,bytes(a.u.mem_read(CFG,192))))
    return a

class Engine:
    def __init__(self,c,level,q,tone_enabled=True,device_type=None):
        self.c=json.loads(config_key(c));self.level=level;self.q=q;self.tone_enabled=tone_enabled;self.driver=scaler();self.scaled_cache=OrderedDict();self.alg=mcu(level,device_type or device_models.spec()['led_type']);self.original_calls=0
        self.driver.width=self.driver.height=2;self.driver.put('gu16LedWidth',1);self.driver.put('gu16LedHeight',1)
    def spatial(self,area,c=None):
        c=c or self.c
        q=f.ldf_signal_input(self.level,area,self.q) if self.tone_enabled else self.q
        self.driver.config=c;self.driver.alpha=c['alpha'];unique,indices=blocks(area,q);values=[]
        self.driver.width=self.driver.height=2;self.driver.put('gu16LedWidth',1);self.driver.put('gu16LedHeight',1)
        ck=(tuple(c['alpha']),c['dc'],c['blend'],c['dynamic'])
        for block in unique:
            key=(ck,block)
            if key not in self.scaled_cache:
                self.driver.u.mem_write(0x60100000,block);self.driver.call('MDrv_LD_AlgoScalingDown',0x60100000,0x60110000,0x60120000);self.original_calls+=1
                self.scaled_cache[key]=struct.unpack('<H',self.driver.u.mem_read(0x60110000,2))[0]
                if len(self.scaled_cache)>32768:self.scaled_cache.popitem(last=False)
            else:self.scaled_cache.move_to_end(key)
            values.append(self.scaled_cache[key])
        source=V(*(values[i] for i in indices));out=V();LIB.spatial(source,S(*c['sf']),out);return bytes(out)
    def run(self,spatial,area,budget):
        # Grid cases are independent stationary experiments. OEM globals include
        # previous-frame state; pooled runtimes must not leak it between recipes.
        for address,blob in self.alg.stationary:self.alg.u.mem_write(address,blob)
        self.alg.u.mem_write(CFG,struct.pack('<I',budget));self.alg.u.mem_write(BUFFER,spatial);self.alg.call('LED_MCU_Common_BoostInsertToAlgo_xiaomi_monitor_pm2u_dc',BUFFER,48,24);self.original_calls+=1
        output=V.from_buffer_copy(self.alg.u.mem_read(BUFFER,2304));metric=(ctypes.c_double*4)();LIB.metrics(output,*weights(area),metric)
        return tuple(metric)
    def hist(self,spatial,budget):
        self.run(spatial,100,budget);raw=struct.unpack('<1152H',self.alg.u.mem_read(BSS_BASE+366348,2304))
        if self.level<3:
            ctl=struct.unpack('<48I',self.alg.u.mem_read(CFG,192));cap,want=ctl[42:44];raw=[min(65535,v*want//cap) if cap else 0 for v in raw]
        return raw

@lru_cache(maxsize=1)
def live_samples():return json.loads((ROOT/'resources/ui/alpha01-response.json').read_text(encoding='utf-8'))['rows']

def vector_config(p,level=3):return dict(sf=list(p[:5]),dc={1:7,2:6,3:8}[level],blend=6 if level==2 else 8,dynamic=p[7],alpha=list(p[8:]))
def blend_anchors(c,anchors,field=1,log=True):
    points=[]
    for item in anchors:
        a=item[0];value=item[field] if len(item)>field else 0.
        d=((c['sf'][0]**.4-a['sf'][0]**.4)/(255**.4))**2+sum(((x-y)/16)**2 for x,y in zip(c['alpha'],a['alpha']))
        d+=sum(((x-y)/255)**2 for x,y in zip(c['sf'][1:],a['sf'][1:]))+((c['dc']-a['dc'])/8)**2+((c['blend']-a['blend'])/8)**2
        if d<1e-12:return value
        points.append((d,value))
    if not points:return 1. if log else 0.
    points=sorted(points)[:4];total=sum(1/d**2 for d,g in points)
    value=sum((math.log(max(.00001,g)) if log else g)/d**2 for d,g in points)/total
    return math.exp(value) if log else value

@lru_cache(maxsize=96)
def anchor_corrections(level,area,q):
    if area<=0 or q<=0:return []
    engine=Engine(f.stock(level),level,q);base=engine.run(engine.spatial(area),area,24)[0];out=[]
    source=f.measured_basis.__globals__['source']()
    for p in {tuple(r['parameters']) for r in source['rows']}:
        c=vector_config(p,level);m=f.measured_basis(c,level,area,max(4000,q))
        if not m:continue
        model=engine.run(engine.spatial(area,c),area,24)[0]
        if model>0 and base>0:out.append((c,max(.005,min(200.,m['driver_ratio24']*base/model)),0.,0.))
    # New independent GET-confirmed SF1/A0/A1 captures. Input/area outside the
    # measured domain retains the original-function estimate, not a fake sample.
    if .01<=area<=5 and q>=4000:
        rows=live_samples();groups={}
        for r in rows:groups.setdefault(tuple(r['parameters']),[]).append(r)
        baseline=next(p for p,rs in groups.items() if rs[0]['stage']=='stock');initial=vector_config(baseline,level)
        initial_model=engine.run(engine.spatial(area,initial),area,24);initial_gain=blend_anchors(initial,out)
        def at(p,field):return f.interp(sorted((r['area_percent'],r[field]) for r in groups[p]),area,True)
        measured_initial=at(baseline,'effective_drive');unit=initial_model[3]/max(1,at(baseline,'maximum'));fresh=[]
        for p in groups:
            c=vector_config(p,level);m=engine.run(engine.spatial(area,c),area,24)
            gain=initial_gain*initial_model[0]/max(.00001,m[0])*at(p,'effective_drive')/max(.00001,measured_initial)
            fresh.append((c,gain,at(p,'halo_mean')*unit-m[1],at(p,'black_mean')*unit-m[2]))
        out=fresh+out
    return out

@lru_cache(maxsize=65536)
def correction(key,level,area,q):
    c=json.loads(key)
    if equal(c,f.stock(level)) or area<=0 or q<=0:return 1.
    # Fresh calibration varied only A0/A1. Do not invent a penalty for other
    # Alpha bins; their effect comes from the original scaling function itself.
    c['alpha'][2:]=f.stock(level)['alpha'][2:]
    return blend_anchors(c,anchor_corrections(level,max(.01,area),q))
@lru_cache(maxsize=65536)
def spill_offsets(key,level,area,q):
    anchors=anchor_corrections(level,max(.01,area),q);c=json.loads(key);c['alpha'][2:]=f.stock(level)['alpha'][2:]
    return blend_anchors(c,anchors,2,False),blend_anchors(c,anchors,3,False)
def spill(metric,c,level,area,q):
    h,b=spill_offsets(config_key(c),level,area,q)
    return max(0,metric[1]+h),max(0,metric[2]+b)

@lru_cache(maxsize=96)
def stock_drive(level,area,q):
    e=Engine(f.stock(level),level,q);return e.run(e.spatial(area),area,24)[0]

def scale_nit(metric,c,level,area,q):
    base=stock_drive(level,area,q)
    signal=f.signal_input(level,area,q)
    return max(0,f.factory_nits(level,area,q)*metric[0]/base*correction(config_key(c),level,area,signal)) if base>0 else 0.

def interpolate_curve(values,b):return f.interp(list(zip(KNOTS,values)),b)

def response(c,level,q,areas=None):
    e=Engine(c,level,q);areas=areas or AREAS;raw=[];nits=[];metrics=[];native=[]
    for area in areas:
        spatial=e.spatial(area);samples=[(0.,0.,0.,0.) if b==0 else e.run(spatial,area,b) for b in KNOTS]
        ns=[scale_nit(v,c,level,area,q) for v in samples];rs=[v[3] for v in samples]
        raw.append([round(interpolate_curve(rs,b)) for b in range(87)]);nits.append([round(interpolate_curve(ns,b),3) for b in range(87)]);native.append(round(rs[5]))
        values=struct.unpack('<1152H',spatial);peak=max(values);m=samples[5]
        metrics.append(dict(aperture_fraction=m[0]/m[3] if m[3] else 0,driver_window_percent=sum(values)/max(1,peak)/1152*100,dark_mean=m[2],halo_mean=m[1],driver_basis=f.prediction_note(),input_basis=('借用32寸LDF：' if device_models.ACTIVE_MODEL=='27u-2026' else '')+ldf(area,f.ldf_signal_input(level,area,q))[1],effective_input_nits=round(f.ldf_signal_input(level,area,q),3)))
    return dict(areas=list(areas),raw=raw,nits=nits,metrics=metrics,native=native,factory_nits=[round(f.factory_nits(level,a,q),3) for a in areas],input_nits=q,native_budget_samples=e.original_calls,model='ldf96-corrected-v6',model_id=device_models.ACTIVE_MODEL,tone=device_models.ACTIVE_TONE,level=level,scope=f.prediction_note())

def context(c,level,q):
    base=json.loads(config_key(c));base['sf'][0]=255;base['alpha']=[0,0,16,16,16,16,16,16]
    payload=dict(format='mi-fit-surface-v7-all-alpha',engine_id=MODEL_ID,model_id=device_models.ACTIVE_MODEL,tone=device_models.ACTIVE_TONE,base=base,level=level,input_nits=q)
    return payload,hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:24]

def save_progress(value):
    p=ROOT/'state/model-progress.json';p.parent.mkdir(exist_ok=True);t=p.with_suffix('.next');t.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    # Windows readers can briefly hold the destination without delete sharing.
    # Progress is informational: a busy reader must not abort a model calculation.
    for _ in range(5):
        try:t.replace(p);return
        except PermissionError:time.sleep(.01)

def surface_workers():
    return min(16,max(1,(os.process_cpu_count() or 1)-1))

def surface_pair(e,c,level,q,pair):
    draft=json.loads(config_key(c));draft['alpha'][:2]=pair;values=array('f');before=e.original_calls
    for sf in SF:
        draft['sf'][0]=sf;mat=[[0.]*15 for _ in KNOTS]
        for i,area in enumerate(AUTO):
            if area<=0:continue
            spatial=e.spatial(area,draft);factor=scale_nit((1.,0,0,0),draft,level,area,q)
            for j,b in enumerate(KNOTS):
                if not b:continue
                m=e.run(spatial,area,b);mat[j][i]=m[0]*factor
                if area<10:
                    h,dark=spill(m,draft,level,area,q);mat[j][13]+=h/65535/7;mat[j][14]+=dark/65535/7
        for row in mat:values.extend(row)
    return values,e.original_calls-before

_surface_engine=None
def init_surface_worker(c,level,q,model,tone):
    global _surface_engine
    device_models.activate(model,tone)
    _surface_engine=Engine(c,level,q)

def surface_task(pair):
    e=_surface_engine
    return surface_pair(e,e.c,e.level,e.q,pair)

def build_surface(c,level,q,workers):
    pairs=[(a0,a1) for a0 in ALPHA for a1 in ALPHA];values=array('f');calls=0
    progress=dict(done=0,total=729,workers=workers,message='并行缓存原厂响应' if workers>1 else '缓存原厂响应')
    save_progress(progress)
    def accept(result):
        nonlocal calls
        chunk,count=result;values.extend(chunk);calls+=count;progress['done']+=len(SF);save_progress(progress)
    if workers==1:
        e=Engine(c,level,q)
        for pair in pairs:accept(surface_pair(e,c,level,q,pair))
    else:
        # Each process owns its ARM runtime. Threads must not share MCU/register state.
        pythonw=Path(sys.executable).with_name('pythonw.exe')
        if os.name=='nt' and pythonw.is_file():multiprocessing.set_executable(str(pythonw))
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),initializer=init_surface_worker,initargs=(c,level,q,device_models.ACTIVE_MODEL,device_models.ACTIVE_TONE)) as pool:
            for result in pool.map(surface_task,pairs):accept(result)
    return values,calls

def surface(c,level,q):
    ctx,key=context(c,level,q);directory=ROOT/'state/response-model';path=directory/(key+'.bin');meta=directory/(key+'.json');count=9*9*9*9*15
    if path.exists() and meta.is_file() and path.stat().st_size==count*4:
        values=array('f');values.frombytes(path.read_bytes());return values,json.loads(meta.read_text(encoding='utf-8'))
    start=time.monotonic();workers=surface_workers();values,calls=build_surface(c,level,q,workers)
    assert len(values)==count
    report={**ctx,'context':key,'original_arm_calls':calls,'workers':workers,'sampled_combinations':729,'dense_search_combinations':73984,'seconds':round(time.monotonic()-start,3),'sf_knots':SF,'alpha_knots':ALPHA,'budget_knots':KNOTS,'areas':AUTO,'note':'729组合原厂算法采样；其间插值密搜73984组合及0–预算上限。36帧新SF1/Alpha0/1实机末级DMA校正亮度与邻区/黑场代理；其余为插值或原函数估算，非73984组实机/光学实测。'}
    directory.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.next');tmp.write_bytes(values.tobytes());tmp.replace(path);meta.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');save_progress(dict(done=729,total=729,workers=workers,message='响应表已缓存'))
    return values,report

def alpha_policy(targets,references):
    # A pronounced rise/dip/rebound is the only ordinary reason for Alpha1 below Alpha0.
    positive=list(zip(AUTO[1:],targets[1:]))
    valley=any(a<=5 and c>=10 and u-v>max(50,.2*u) and w-v>max(50,.2*w)
               for i,(a,u) in enumerate(positive) for j,(b,v) in enumerate(positive[i+1:],i+1)
               for c,w in positive[j+1:])
    dim=any(a>=50 and ref>0 and t<.15*ref for a,t,ref in zip(AUTO,targets,references))
    return dict(valley=valley,large_window_dim=dim,high_weight=.004 if dim else .35,a1_weight=.001 if dim else .025)

def preferred_config(config,policy):
    config=json.loads(config_key(config));alpha=config['alpha']
    if not policy['valley']:alpha[1]=max(alpha[0],alpha[1])
    return config

def alpha_penalty(config,policy):
    alpha=config['alpha']
    order=0. if policy['large_window_dim'] else .08*sum((max(0,alpha[i]-alpha[i+1])/16)**2 for i in range(1,7))/6
    return policy['high_weight']*sum(((16-a)/16)**2 for a in alpha[2:])/6+policy['a1_weight']*((16-alpha[1])/16)**2+order

_fit_pool=None
_fit_pool_context=None

def close_fit_pool():
    global _fit_pool,_fit_pool_context
    if _fit_pool is not None:_fit_pool.shutdown(wait=True);_fit_pool=None;_fit_pool_context=None

def fit_pool(c,level,q,key):
    global _fit_pool,_fit_pool_context
    if _fit_pool_context!=key:
        close_fit_pool()
        pythonw=Path(sys.executable).with_name('pythonw.exe')
        if os.name=='nt' and pythonw.is_file():multiprocessing.set_executable(str(pythonw))
        _fit_pool=ProcessPoolExecutor(max_workers=surface_workers(),mp_context=multiprocessing.get_context('spawn'),initializer=init_surface_worker,initargs=(c,level,q,device_models.ACTIVE_MODEL,device_models.ACTIVE_TONE))
        _fit_pool_context=key
    return _fit_pool

def fit_matrix(e,config,knots,level,q):
    if not hasattr(e,'sample'):e.sample=lru_cache(maxsize=16384)(e.run)
    matrix=[[0.]*15 for _ in knots];before=e.original_calls
    for i,area in enumerate(AUTO):
        if not area:continue
        spatial=e.spatial(area,config);factor=scale_nit((1.,0,0,0),config,level,area,q)
        for j,b in enumerate(knots):
            if not b:continue
            m=e.sample(spatial,area,b);matrix[j][i]=m[0]*factor
            if area<10:
                h,dark=spill(m,config,level,area,q);matrix[j][13]+=h/65535/7;matrix[j][14]+=dark/65535/7
    return matrix,e.original_calls-before

def fit_matrix_task(task):
    e=_surface_engine
    return fit_matrix(e,*task,e.level,e.q)


@lru_cache(maxsize=2)
def fit_engine(context,key,level,q):
    # Only fitting consumes cached metrics, never the MCU RAM needed by hist().
    # Context includes model, tone, input and frozen parameters; buffers are exact.
    engine=Engine(json.loads(key),level,q)
    engine.sample=lru_cache(maxsize=16384)(engine.run)
    return engine


def fit(c,level,q,targets,ceiling):
    with LOCK:
        started=time.monotonic();seed=json.loads(config_key(c));seed['alpha'][2:]=[16]*6
        policy=alpha_policy(targets,[f.factory_nits(level,a,q) if a else 0. for a in AUTO])
        values,report=surface(seed,level,q);result=(ctypes.c_double*21)();goal=(ctypes.c_double*13)(*targets)
        data=(ctypes.c_float*len(values)).from_buffer(values);LIB.solve(data,goal,ceiling,result)
        e=fit_engine(report['context'],config_key(c),level,q);cache={};calls_before=e.original_calls
        knots=[b for b in KNOTS if b<=ceiling]
        if knots[-1]!=ceiling:knots.append(next(b for b in KNOTS if b>ceiling))
        def loss(pred):
            errors=[((v-t)/max(100,t))**2 for v,t in zip(pred[1:],targets[1:])]
            return sum(errors)/12+.5*max(errors)
        def objective(p):return p['score']+alpha_penalty(p['config'],policy)+.0005*(p['halo']+2*p['black'])
        def choose(points):return min(points,key=lambda p:(objective(p),p['score']))
        parallel_calls=0
        def prepare(configs):
            nonlocal parallel_calls
            missing={}
            for config in configs:
                key=config_key(preferred_config(config,policy));matrix_key=(report['context'],key,tuple(knots))
                if key not in cache and matrix_key not in FIT_MATRICES:missing.setdefault(matrix_key,config)
            if not missing:return
            tasks=[(config,knots) for config in missing.values()]
            parallel=len(tasks)>1 and surface_workers()>1
            if parallel:results=fit_pool(c,level,q,report['context']).map(fit_matrix_task,tasks)
            else:results=(fit_matrix(e,config,knots,level,q) for config in missing.values())
            # Ordered map preserves the old first-candidate and tie-breaking order.
            for matrix_key,(matrix,calls) in zip(missing,results):
                if len(FIT_MATRICES)>=512:FIT_MATRICES.pop(next(iter(FIT_MATRICES)))
                FIT_MATRICES[matrix_key]=matrix;parallel_calls+=calls if parallel else 0
        def evaluate(config):
            key=config_key(preferred_config(config,policy))
            if key in cache:return cache[key]
            matrix_key=(report['context'],key,tuple(knots))
            matrix=FIT_MATRICES.get(matrix_key)
            if matrix is None:prepare([config]);matrix=FIT_MATRICES[matrix_key]
            points=[];j=0
            for b in range(ceiling+1):
                while j<len(knots)-2 and knots[j+1]<b:j+=1
                t=(b-knots[j])/(knots[j+1]-knots[j]) if len(knots)>1 else 0.
                row=[u+(v-u)*t for u,v in zip(matrix[j],matrix[min(j+1,len(knots)-1)])]
                pred=row[:13];score=loss(pred)
                points.append(dict(config=json.loads(key),budget=b,score=score,halo=row[13],black=row[14],peak=pred,long=pred))
            cache[key]=choose(points)
            if len(cache)%8==0:save_progress(dict(done=len(cache),total=400,message='全部Alpha原厂函数联合细化；不写入设备'))
            return cache[key]
        a0,a1,sf=map(round,result[:3]);dense=json.loads(config_key(seed));dense['alpha'][:2]=[a0,a1];dense['sf'][0]=sf
        full=json.loads(config_key(seed));full['alpha']=[16]*8;full['sf'][0]=0
        # Include the known bright endpoint explicitly; an interpolated seed may
        # never exclude SF1=0/Alpha=16 from attainable candidates.
        # Search the cached plane inside the requested low-bin ordering as well.
        # Projecting only the unconstrained optimum can miss every good ordered seed.
        ordered=[]
        for i,a0 in enumerate(ALPHA):
            for j,a1 in enumerate(ALPHA):
                if a1<a0 and not policy['valley']:continue
                for k,sf in enumerate(SF):
                    draft=json.loads(config_key(seed));draft['alpha'][:2]=[a0,a1];draft['sf'][0]=sf;points=[]
                    for m,b in enumerate(KNOTS):
                        if b>ceiling:continue
                        start=(((i*9+j)*9+k)*9+m)*15;row=values[start:start+15]
                        points.append(dict(config=draft,budget=b,score=loss(row[:13]),halo=row[13],black=row[14]))
                    ordered.append(choose(points))
        initial=[dense,full,c]+[p['config'] for p in sorted(ordered,key=objective)[:3]];prepare(initial)
        starts=[evaluate(x) for x in initial]
        def joint_refine(point):
            damping=.01
            for iteration in range(6):
                config=point['config'];position=[a/16 for a in config['alpha']]+[config['sf'][0]/255];columns=[];probes=[]
                for i in range(9):
                    draft=json.loads(config_key(config));current=config['alpha'][i] if i<8 else config['sf'][0];step=1 if i<8 else 8;maximum=16 if i<8 else 255
                    value=current+step if current+step<=maximum else max(0,current-step)
                    if i<8:draft['alpha'][i]=value
                    else:draft['sf'][0]=value
                    probes.append((draft,(value-current)/maximum))
                prepare([draft for draft,du in probes])
                for draft,du in probes:
                    probe=evaluate(draft)
                    columns.append([(v-u)/max(100,t)/du for v,u,t in zip(probe['peak'][1:],point['peak'][1:],targets[1:])])
                residual=[(t-v)/max(100,t) for t,v in zip(targets[1:],point['peak'][1:])]
                worst=max(map(abs,residual),default=0.)
                weights=[math.sqrt(1+6*(abs(r)/worst)**4) if worst else 1. for r in residual]
                residual=[r*w for r,w in zip(residual,weights)];columns=[[v*w for v,w in zip(col,weights)] for col in columns]
                matrix=[[sum(a*b for a,b in zip(columns[i],columns[j]))+(damping if i==j else 0.) for j in range(9)] for i in range(9)]
                rhs=[sum(a*b for a,b in zip(columns[i],residual)) for i in range(9)]
                for i in range(9):
                    weight=policy['high_weight']/6 if 2<=i<8 else policy['a1_weight'] if i==1 else 0.
                    matrix[i][i]+=weight;rhs[i]+=weight*(1-position[i])
                # Small damped9x9 solve, no numerical package or new runtime.
                augmented=[row+[v] for row,v in zip(matrix,rhs)]
                for i in range(9):
                    pivot=max(range(i,9),key=lambda j:abs(augmented[j][i]));augmented[i],augmented[pivot]=augmented[pivot],augmented[i]
                    scale=augmented[i][i];augmented[i]=[x/scale for x in augmented[i]]
                    for j in range(9):
                        if j!=i:
                            factor=augmented[j][i];augmented[j]=[a-factor*b for a,b in zip(augmented[j],augmented[i])]
                delta=[max(-.35,min(.35,row[-1])) for row in augmented];trials=[point];drafts=[]
                for amount in (1.,.5,.25):
                    draft=json.loads(config_key(config));draft['alpha']=[max(0,min(16,round((v+amount*d)*16))) for v,d in zip(position[:8],delta[:8])];draft['sf'][0]=max(0,min(255,round((position[8]+amount*delta[8])*255)));drafts.append(draft)
                prepare(drafts);trials.extend(evaluate(draft) for draft in drafts)
                next_point=choose(trials)
                if config_key(next_point['config'])==config_key(point['config']):
                    if damping>=1.:break
                    damping*=10
                else:point=next_point;damping=max(.001,damping*.5)
            return point
        # A coupled step escapes the one-parameter local minimum. Refine both the
        # best dense seed and the explicitly reachable bright endpoint.
        best=choose([joint_refine(choose(starts)),joint_refine(starts[1])])
        for pass_index in range(2):
            candidates=[best]
            for i in (2,3,4,5,6,7,1,0):
                current=best['config']['alpha'][i]
                trial_values=range(17) if pass_index==0 else sorted({0,16,*range(max(0,current-2),min(16,current+2)+1)})
                trials=[best];drafts=[]
                for value in trial_values:
                    draft=json.loads(config_key(best['config']));draft['alpha'][i]=value;drafts.append(draft)
                prepare(drafts);trials.extend(evaluate(draft) for draft in drafts)
                best=choose(trials);candidates.extend(trials)
            current=best['config']['sf'][0]
            trial_values=sorted({*SF,0,255,*range(max(0,current-5),min(255,current+5)+1)})
            drafts=[]
            for value in trial_values:
                draft=json.loads(config_key(best['config']));draft['sf'][0]=value;drafts.append(draft)
            prepare(drafts);candidates.extend(evaluate(draft) for draft in drafts)
            best=choose(candidates)
        # Enumerate the final budget with the original function at every integer;
        # interpolation is only a search accelerator, never the delivered curve.
        draft=best['config'];spatials={a:e.spatial(a,draft) for a in AUTO if a};exact=[]
        for budget in range(ceiling+1):
            pred=[];halo=black=0.
            for area in AUTO:
                m=e.sample(spatials[area],area,budget) if area and budget else (0.,0.,0.,0.)
                pred.append(scale_nit(m,draft,level,area,q) if area else 0.)
                if 0<area<10:
                    h,dark=spill(m,draft,level,area,q);halo+=h/65535/7;black+=dark/65535/7
            score=loss(pred)
            exact.append(dict(config=draft,budget=budget,peak=pred,long=pred,score=score,halo=halo,black=black))
        best=choose(exact);score=best['score']
        report={**report,'all_alpha_candidates':len(cache),'refinement_arm_calls':e.original_calls-calls_before+parallel_calls,'fit_seconds':round(time.monotonic()-started,3),'fit_workers':surface_workers(),'loss':'mean-square plus half worst-window-square','free_alpha':list(range(8)),'alpha_policy':policy,'bright_endpoint_nits':starts[1]['peak'],
                'note':'先以Alpha2–7=16搜索SF1/Alpha0/1的729组原厂函数响应平面与73984组插值候选，再用耦合阻尼最小二乘与坐标搜索联合细化全部Alpha0–7和SF1；预算逐值搜索，最后整数预算原函数回算。平均与最差窗口误差共同计算，并加入强Alpha2–7=16正则、较弱Alpha1=16正则；通常Alpha按序不下降（高位为软偏好）。仅明确先升后降再回升的目标放开Alpha1<Alpha0；大窗低于默认15%的极暗目标放松高Alpha正则与高位顺序。再兼顾光晕/黑场；报告仍展示不含正则的真实拟合误差。高Alpha组合多为原厂函数估计，不是新增实机或光学标定。'}
        best.update(recipe='native-all-alpha',mode='global',ceiling=ceiling,input_nits=q,context=report['context'],level=level,rmse=round(math.sqrt(sum(((v-t)/max(100,t))**2 for v,t in zip(best['peak'][1:],targets[1:]))/12)*100,3),worst_error=round(max(abs(v-t)/max(100,t) for v,t in zip(best['peak'][1:],targets[1:]))*100,3),report=report,scope='SF1、全部Alpha与统一预算联合；SF2–5/DC/Blend/Dynamic冻结，累计ABL不参与。')
        token=hashlib.sha256(json.dumps(best,sort_keys=True).encode()).hexdigest()[:24];best['fit_id']=token;FIT_RESULTS[token]=best
        if len(FIT_RESULTS)>32:FIT_RESULTS.pop(next(iter(FIT_RESULTS)))
        save_progress(dict(done=1,total=1,message='全部Alpha联合拟合已完成；未写入设备'))
        return best

def validate_fit(data,c,level,q):
    result=FIT_RESULTS.get(data.get('fit_id'))
    if result is None:raise ValueError('拟合结果已失效，请重新预览')
    if result['context']!=context(c,level,q)[1] or result['ceiling']!=data['ceiling'] or result['budget']!=data['budget']:raise ValueError('固定参数、输入或上限已改变，请等待新拟合')
    return {k:v for k,v in result.items() if k not in ('peak','long','report')},result['config']

