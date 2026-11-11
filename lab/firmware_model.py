"""PC-only original ARM64 response and screenshot-anchored estimates. Never opens ADB."""
from functools import lru_cache
from pathlib import Path
import json,math,struct,threading
from firmware_scaling import Driver as BaseDriver,UC_ARM64_REG_X0,UC_ARM64_REG_PC,UC_ARM64_REG_X30
from firmware_hook import Algorithm,install,frame,CFG
from measured_response import basis as measured_basis
import device_models

ROOT=Path(__file__).resolve().parents[1];W,H=48,24;N=W*H
AREAS=[0,100/8294400,.001,.01,.1,.5,1,2,5,10,20,25,50,75,100]
STOCK_ALPHA=[3,5,7,9,11,13,15,16]
def stock(level):return device_models.defaults(level)
def pq(n):
    p=(max(0,n)/10000)**(2610/16384);return ((3424/4096+2413/128*p)/(1+2392/128*p))**(2523/32)
def inverse_pq(v):
    p=v**(32/2523);return 10000*(max(0,p-3424/4096)/(2413/128-2392/128*p))**(16384/2610)

@lru_cache(maxsize=1)
def spatial_reference():return json.loads((ROOT/'resources/ui/spatial-calibration.json').read_text(encoding='utf-8'))
@lru_cache(maxsize=256)
def aperture_weights(area,sigma=None):
    sigma=sigma or spatial_reference()['sigma_zones'];s=math.sqrt(2)*sigma
    w=max(1,int(3840*math.sqrt(max(0,area)/100)+.5));h=max(1,int(2160*math.sqrt(max(0,area)/100)+.5))
    left=(3840-w)//2/80;top=(2160-h)//2/90
    def axis(count,start,length):return [math.erf((start+length-i-.5)/s)-math.erf((start-i-.5)/s) for i in range(count)]
    xx=axis(W,left,w/80);yy=axis(H,top,h/90);values=[x*y for y in yy for x in xx];total=sum(values)
    return tuple(v/total for v in values)
def aperture_fraction(spatial,area):
    peak=max(spatial);return sum(v*w for v,w in zip(spatial,aperture_weights(area)))/peak if peak else 0.

@lru_cache(maxsize=512)
def illumination_cached(config_json,area,input_nits):
    spatial,_=Driver(json.loads(config_json)).process(statistics(area,input_nits)[0]);return aperture_fraction(spatial,area)
def illumination_fraction(config,area,input_nits):return illumination_cached(json.dumps(config,sort_keys=True),area,input_nits)
def statistics(area,input_nits,layout='center'):
    code=max(0,min(255,int(pq(input_nits)*255+.5))) if input_nits>0 else 0
    if area<=0 or not code:return [(0,0)]*N,0
    width=max(1,int(3840*math.sqrt(area/100)+.5));height=max(1,int(2160*math.sqrt(area/100)+.5))
    left=(3840-width)//2;top=(2160-height)//2
    if layout=='zone-center':left=1960-width//2;top=1125-height//2
    right=left+width;bottom=top+height
    counts=[max(0,min((x+1)*80,right)-max(x*80,left))*max(0,min((y+1)*90,bottom)-max(y*90,top)) for y in range(H) for x in range(W)]
    return [(min(code,c*code//7200),code if c else 0) for c in counts],sum(counts)/8294400*100

class Driver(BaseDriver):
    def __init__(self,config):self.config=config;super().__init__()
    def host(self,u,address,size,data):
        name=self.hooks.get(address);values={'MHal_LD_GetLDFDCMaxAlpha':self.config['dc'],'MHal_LD_Get_LDF_Blend':self.config['blend'],'MHal_LD_Get_LDF_DynamicAlphaEn':self.config['dynamic']}
        if name in values:u.reg_write(UC_ARM64_REG_X0,values[name]);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30));return
        super().host(u,address,size,data)
    def process(self,cells):
        self.width=W;self.height=H;self.alpha=self.config['alpha'];self.put('gu16LedWidth',W);self.put('gu16LedHeight',H)
        self.u.mem_write(0x60100000,bytes(v for pair in cells for v in pair));self.call('MDrv_LD_AlgoScalingDown',0x60100000,0x60110000,0x60120000)
        scaled=struct.unpack('<1152H',self.u.mem_read(0x60110000,N*2));sf=self.config['sf'];radius=max((i+1 for i,v in enumerate(sf) if v!=255),default=0)
        if radius:
            coeff=[0]*176
            for y in range(radius*2+1):
                for x in range(radius*2+1):
                    ring=max(abs(x-radius),abs(y-radius));coeff[y*16+x]=(sf[ring-1]<<8) if ring else 0
            self.u.mem_write(0x60130000,struct.pack('<176H',*coeff));name='MDrv_Alg_LD_SpatialFilter_NonLinearMode_'+('One' if radius<4 else 'Two')+'_Array_NEON'
            self.call(name,0x60110000,0x60140000,H,W,0x60130000,radius,radius);spatial=struct.unpack('<1152H',self.u.mem_read(0x60140000,N*2))
        else:spatial=scaled
        dark=[v for v,c in zip(spatial,cells) if c[1]==0]
        return spatial,dict(scaled_max=max(scaled),spatial_max=max(spatial),dark_mean=round(sum(dark)/max(1,len(dark)),3),dark_max=max(dark,default=0),alpha_bins=sorted(set(min(7,c[0]//32) for c in cells if c[1]>0)))

def budget_values(spatial,level):
    a=Algorithm(level=level,device_type=device_models.spec()['led_type']);install(a,value=0);samples={};errors=[]
    def read(b):
        if b not in samples:a.u.mem_write(CFG,struct.pack('<I',b));samples[b]=frame(a,spatial,1000+b)
        return samples[b]['output_max']
    def split(left,right):
        if right-left<2:return
        mid=(left+right)//2;x=read(mid);estimate=read(left)+(read(right)-read(left))*(mid-left)/(right-left);error=abs(x-estimate);errors.append(error)
        if error>max(32,max(x,read(left),read(right))*.0025):split(left,mid);split(mid,right)
    knots=[0,1,8,24,41,86]
    for b in knots:read(b)
    for left,right in zip(knots,knots[1:]):split(left,right)
    keys=sorted(samples);values=[]
    for b in range(87):
        hi=next(x for x in keys if x>=b);lo=max(x for x in keys if x<=b);values.append(read(lo) if hi==lo else round(read(lo)+(read(hi)-read(lo))*(b-lo)/(hi-lo)))
    return values,samples[24]['window_raw']/100,len(samples)

def response(config,level,input_nits,areas=None):
    from ldf_response import response as ldf_response
    return ldf_response(config,level,input_nits,areas)

@lru_cache(maxsize=32)
def predict_cached(config_json,level,input_nits):return response(json.loads(config_json),level,input_nits)
PREDICT_LOCK=threading.Lock()
def predict(config,level,input_nits):
    with PREDICT_LOCK:return predict_cached(json.dumps(config,sort_keys=True),level,input_nits)

@lru_cache(maxsize=1)
def reference():return json.loads((ROOT/'resources/ui/optical-reference.json').read_text(encoding='utf-8'))
@lru_cache(maxsize=1)
def factory():return json.loads((ROOT/'resources/ui/factory-output.json').read_text(encoding='utf-8'))
def interp(points,x,log=False):
    if x<=points[0][0]:return points[0][1]
    if x>=points[-1][0]:return points[-1][1]
    for (a,u),(b,v) in zip(points,points[1:]):
        if x<=b:
            t=(math.log10(x)-math.log10(a))/(math.log10(b)-math.log10(a)) if log and a>0 else (x-a)/(b-a);return u+(v-u)*t
def factory_raw(level,area,input_nits):
    data=factory();row=next(r for r in data['rows'] if r['level']==level);inputs=data['inputs']
    points=[]
    for q in inputs:
        values=row['input_rows'][str(q)]['native'];points.append((pq(q),interp(list(zip(data['areas'],values)),area,True)))
    return interp(points,pq(input_nits))
@lru_cache(maxsize=256)
def calibration_input(level,area,q):
    if q<=1000 or q>=10000:return q
    from firmware_tone import compare
    a=max(.01,area)
    value=lambda n:compare('32u-2026',5,level,a,n)['hgig']['mapped_nits']
    lo,hi,current=value(1000),value(10000),value(q)
    t=max(0,min(1,(current-lo)/(hi-lo))) if hi>lo else 1.
    return inverse_pq(pq(1000)+(pq(10000)-pq(1000))*t)

def factory_nits_32(level,area,input_nits):
    if area<=0 or input_nits<=0:return 0.
    # Sparse optical table: interpolate the 1000..10000 gap in the OEM TMO
    # output domain, not linearly in PQ. Clipped 4000 and10000 inputs must agree.
    input_nits=calibration_input(level,area,input_nits)
    data=reference();table=data['high'];a=max(.01,min(100,area));values=[]
    for q,row in zip(table['inputs'],table['nits']):values.append((pq(q),interp(sorted(zip(table['areas'],row)),a,True)))
    high=interp(values,pq(input_nits))
    if level!=3:
        peak=interp(list(zip(data['bars']['areas'],data['bars']['peak_nits'][str(level)])),a,True)
        high_peak=interp(sorted(zip(table['areas'],table['nits'][-1])),a,True);high=peak*(high/high_peak if high_peak else 0)
    if area<.01:
        row=next(r for r in factory()['rows'] if r['level']==level)
        def fraction(a):
            points=[(pq(q),interp(list(zip(factory()['areas'],[m['aperture_fraction'] for m in row['input_rows'][str(q)]['metrics']])),a,True)) for q in factory()['inputs']]
            return interp(points,pq(input_nits))
        baseline=factory_raw(level,.01,input_nits)*fraction(.01)
        high*=factory_raw(level,area,input_nits)*fraction(area)/baseline if baseline else 0
    return max(0,high)

def signal_input(level,area,q):
    from firmware_tone import equivalent_input
    return equivalent_input(device_models.ACTIVE_MODEL,device_models.ACTIVE_TONE,level,area,q)

def ldf_signal_input(level,area,q):
    return calibration_input(level,area,signal_input(level,area,q))

def factory_nits(level,area,input_nits):
    if area<=0 or input_nits<=0:return 0.
    q=signal_input(level,area,input_nits)
    if device_models.ACTIVE_MODEL=='32u-2026':return factory_nits_32(level,area,q)
    ref=device_models.window_reference('27u-2026');areas=ref['areas'];row=ref['tones']['5'][{1:'low',2:'medium',3:'high'}[level]]
    a=max(.01,min(100,area));peak=interp(list(zip(areas,row)),a,True)
    # Only 10000nit input is measured in the 27-inch table. The normalized input
    # response and sub-0.01% aperture transfer borrow 32-inch data, not new samples.
    base=factory_nits_32(level,a,10000)
    return max(0,peak*factory_nits_32(level,area,q)/base) if base else 0.

def prediction_note():
    note='32寸HGiG截图/实机DMA参考；高输入按原厂TMO饱和映射，不按PQ直线插值；nit是光学代理估算'
    if device_models.ACTIVE_MODEL=='27u-2026':note='27寸HGiG 10000nit PQ窗口表锚点（观测时长未注明）；SF/Alpha、光场及其他输入形状借用32寸，未做27寸实机标定'
    if device_models.ACTIVE_TONE!=5:note+='；当前亮暗模式使用原厂ARM64 TMO推算等效HGiG输入（固定元数据/纯窗/静态），不是该模式的光学实测'
    return note
def calibrated(raw,level,area,input_nits,tone=5,config=None,raw_kind='zone-maximum',factory_path=False,budget_value=24):
    factory_path=factory_path and level==3
    if raw_kind=='global-aw':
        row=predict(config or stock(level),level,input_nits)
        values=[v[24 if factory_path else budget_value] for v in row['nits']]
        return dict(nits=round(interp(list(zip(AREAS,values)),area,True),1),note=prediction_note()+'；AW不冒充分区输出',aw_gain_applied=False)
    base=factory_raw(level,area,input_nits);nits=factory_nits(level,area,input_nits)
    factory_fraction=illumination_fraction(stock(level),area,input_nits);current_fraction=illumination_fraction(config or stock(level),area,input_nits)
    factor=current_fraction/factory_fraction if factory_fraction else 1.
    value=0. if raw==0 else raw/base*nits*factor if base>0 else None
    note='截图参考 × 同窗raw比值 × 当前SF/Alpha邻区光场；空间核为经验拟合，非本机光学实测'
    if level!=3:note+='；中/低档输入响应借用高档归一化形状'
    if area<.01:note+='；小于0.01%为外推'
    return dict(nits=round(value,1) if value is not None else None,note=note,factory_raw=round(base),factory_nits=round(nits,3),spatial_factor=round(factor,6),input_nits=input_nits,area=area,level=level)
