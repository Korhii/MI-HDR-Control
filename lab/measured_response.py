"""Real, latched 48x24 DMA responses; optical conversion remains an estimate.

Only the sampled single-window HIGH/HGiG parameter domain is interpolated.
The same basis is used by the live AW conversion and the automatic recipe table.
"""
from functools import lru_cache
from pathlib import Path
import json, math

@lru_cache(maxsize=1)
def source():
    return json.loads((Path(__file__).resolve().parents[1]/'resources/ui/driver-response.json').read_text(encoding='utf-8'))

def interpolate(points,x,log=False):
    if x<=points[0][0]:return points[0][1]
    if x>=points[-1][0]:return points[-1][1]
    for (a,u),(b,v) in zip(points,points[1:]):
        if x<=b:
            t=math.log(x/a)/math.log(b/a) if log else (x-a)/(b-a)
            return u+(v-u)*t

def point(name,area,q,field):
    rows=[r for r in source()['rows'] if r['recipe']==name]
    inputs=sorted({r['input_nits'] for r in rows})
    def at(value):return interpolate(sorted((r['area_percent'],r[field]) for r in rows if r['input_nits']==value),area,True)
    return interpolate([(value,at(value)) for value in inputs],q)

def basis(config,level,area,q):
    if area<=0 or q<=0:return None
    # Low input/local-gray and manual SF2-5/Alpha1-7 combinations have not been
    # sampled. Do not pretend a bright-window area lookup models those cases.
    if q<4000 or config['dc']!={1:7,2:6,3:8}[level] or config['blend']!={1:8,2:6,3:8}[level] or config['dynamic']!=1:return None
    factory=config['sf']==[255]*5 and config['alpha']==[3,5,7,9,11,13,15,16]
    if not factory and (config['sf'][1:]!=[255]*4 or config['alpha'][1:]!=[16]*7):return None
    a=config['alpha'][0];s=config['sf'][0]
    if not factory and a<8 and s!=255:return None
    def value(field):
        at=lambda name:point(name,area,q,field)
        if factory:return at('stock')
        if a<=8:return interpolate([(0,at('a0sf255')),(4,at('a4sf255')),(8,at('a8sf255'))],a)
        low=interpolate([(9,at('a8sf9')),(64,at('a8sf64')),(255,at('a8sf255'))],s)
        high=interpolate([(0,at('a16sf0')),(9,at('a16sf9')),(255,at('a16sf255'))],s)
        return low+(high-low)*(a-8)/8
    # a=8 follows the measured SF line, rather than the Alpha-only branch.
    def selected(field):
        if not factory and a==8:return interpolate([(9,point('a8sf9',area,q,field)),(64,point('a8sf64',area,q,field)),(255,point('a8sf255',area,q,field))],s)
        return value(field)
    reference=point('stock',area,q,'effective_drive')
    exact=any(r['parameters']==[ *config['sf'],config['dc'],config['blend'],config['dynamic'],*config['alpha']] and r['input_nits']==q and r['area_percent']==area for r in source()['rows']) if level==3 else False
    return dict(driver_ratio24=selected('effective_drive')/reference if reference else 0,
                driver_aw24=selected('aw'),driver_peak24=selected('center_peak'),
                driver_window_percent=selected('window'),
                # The fitted spatial transfer is already in effective_drive.
                # Do not exponentiate the original budget/AW gain a second time.
                driver_power=1.,driver_sampled=exact,
                driver_basis='实机末级DMA逐区输出；光学代理估算'+('；高档比值借用于中低档' if level!=3 else '')+('；窗口/参数插值或外推' if not exact else ''))
