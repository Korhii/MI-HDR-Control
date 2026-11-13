"""Budget-induced TMO gain; stock tables stay on the monitor and are never flashed."""
from functools import lru_cache
import hashlib,json

@lru_cache(maxsize=128)
def gains(config_json,level,budget,model,tone):
    import device_models,ldf_response as l
    device_models.activate(model,tone)
    config=json.loads(config_json);scales=[]
    if budget in (0,24):scales=[65535]*6
    else:
        e=l.Engine(config,level,10000,tone_enabled=False)
        for area in (5,10,25,50,75,100):
            spatial=e.spatial(area);original=e.run(spatial,area,24)[0];modified=e.run(spatial,area,budget)[0]
            scales.append(max(1,min(4194240,round(modified/original*65535))) if original else 65535)
    return scales+scales[1:]

def compute(config,level,budget,model='32u-2026',tone=5):
    key=json.dumps(config,sort_keys=True,separators=(',',':'))
    return dict(version=1,enabled=budget>0,model_id=model,level=level,tone=tone,budget=budget,
                config_sha256=hashlib.sha256(key.encode()).hexdigest(),scales=gains(key,level,budget,model,tone),
                basis='原厂ARM64：固定当前SF/Alpha，比较当前预算与24；原厂TMO能力表在显示器内同步，ABL增益逐帧跟随；非光学校准')

def packet(data,generation):
    if data.get('version')!=1 or len(data['scales'])!=11:raise ValueError('HDR映射数据格式错误')
    return ','.join(map(str,[int(data['enabled']),data['level'],data['tone'],generation,*data['scales']]))

def attach_profiles(config):
    import model_worker
    config=json.loads(json.dumps(config));model=config.get('model_id','32u-2026')
    for key,p in config['profiles'].items():
        if p.get('factory_budget',False):p.pop('hdr_mapping',None);continue
        level,tone=map(int,key.split(':'))
        p['hdr_mapping']=model_worker.call('hdr-mapping',config=p['config'],level=level,budget=p['budget'],model_id=model,tone=tone)
    return config
