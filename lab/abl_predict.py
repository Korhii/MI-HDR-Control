"""One coupled forecast snapshot: original ARM64 spatial/budget demand + OEM policy."""
from collections import Counter
from functools import lru_cache
import json,struct
from firmware_model import Driver,statistics,stock,calibrated,factory_nits,measured_basis,PREDICT_LOCK,prediction_note
from firmware_hook import Algorithm,install,frame,CFG,BSS_BASE
from native_abl import simulate,validate

AREAS=[0,.001,.01,.1,.5,1,2,5,10,20,25,50,75,100]

@lru_cache(maxsize=32)
def peaks(config_json,level,budget,factory):
    from ldf_response import Engine,scale_nit
    config=json.loads(config_json);engine=Engine(config,level,10000);rows=[]
    for area in AREAS:
        spatial=engine.spatial(area);b=24 if factory else budget
        result=engine.run(spatial,area,b);raw=engine.hist(spatial,b)
        value=scale_nit(result,config,level,area,10000)
        rows.append(dict(area=area,peak_nits=round(value,2),hist=tuple(sorted(Counter(raw).items()))))
    return rows

def forecast(config,level,budget,params,*,factory=False,hz=60,generation=0):
    params=validate(params);hz=hz if 10<=hz<=300 else 60
    with PREDICT_LOCK:base=peaks(json.dumps(config,sort_keys=True),level,budget,factory)
    # Always rerun policy for every request; only the expensive ARM64 peak demand is cached.
    effective={**params,'enabled':params['enabled'] and level in (2,3)}
    rows=[{k:v for k,v in row.items() if k!='hist'}|simulate(row['hist'],row['peak_nits'],effective,hz) for row in base]
    return dict(generation=generation,rows=rows,params=params,hz=hz,r_max=max((r['r_max'] for r in rows),default=0),
                fixed=dict(k_min=18288,k_max=31243,c_max=31243,g_base=65535),
                scope='10000 nit PQ输入；原厂ARM64预算/SF/Alpha输出 + 整数累计模拟；'+prediction_note()+'；秒数取决于驱动调用频率，非热安全认证',
                supported=level in (2,3),snapshot=dict(config=config,level=level,budget=budget,factory=factory,params=params,hz=hz))
