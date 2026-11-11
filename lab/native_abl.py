"""OEM cumulative-load policy. Raw counts, not optical measurements. No device I/O."""
from dataclasses import dataclass

K_MAX=31243
K_MIN=18288
C_MAX=31243
G_BASE=65535
FACTORY_E0=37491600
FACTORY_R=9760
FACTORY_DIVISOR=600

@dataclass
class State:
    k:int=K_MAX
    energy:int=FACTORY_E0
    r_prev:int=0
    g_prev:int=G_BASE

def step(state,load,recovery,*,l_th=K_MIN,e0=FACTORY_E0,divisor=FACTORY_DIVISOR,r_reset=FACTORY_R):
    """Return this call's G; the caller's current output has already used G_prev."""
    load=int(load)&65535
    if state.r_prev<r_reset:
        state.k=K_MAX;state.energy=e0
    if load>l_th:
        charge=min(load,C_MAX)
        if state.energy<=charge:
            delta=((K_MAX-K_MIN)//divisor if divisor else 0)+1
            state.k=state.k-delta if state.k<=K_MAX and state.k>delta+K_MIN else K_MIN
        else:state.energy-=charge
    state.r_prev=int(recovery)&0xffffffff
    state.g_prev=G_BASE*state.k//K_MAX
    return state.g_prev


DEFAULT=dict(enabled=False,l_th=18288,e0=37491600,divisor=600,r_reset=9760)

def validate(p,device=False):
    if not isinstance(p,dict) or set(p)!=set(DEFAULT) or type(p['enabled']) is not bool:raise ValueError('原厂累计ABL参数不完整')
    for key,maximum in [('l_th',65535),('e0',None),('divisor',65535),('r_reset',82800)]:
        if type(p[key]) is not int or p[key]<0 or maximum is not None and p[key]>maximum:raise ValueError('无效累计ABL参数 '+key)
    if device and p['e0']>0xffffffff:raise ValueError('额度可无限制预览，但原厂u32执行范围为0–4294967295，超出不写入')
    return dict(p)

def packet(p,generation):
    p=validate(p,True)
    return ','.join(str(int(p[k])) for k in ('enabled','l_th','e0','divisor','r_reset'))+','+str(generation)

def load_at(hist,gain,stat_floor=0):
    total=bright=0
    for value,count in hist:
        y=value*gain//G_BASE;total+=y*count
        if y>>4>stat_floor:bright+=count
    return total//sum(count for _,count in hist),total//bright if bright else 0

def simulate(hist,peak_nits,params,hz=60):
    """Exact integer state transitions; skip only the constant initial-credit interval."""
    p=validate(params);state=State(energy=p['e0']);load,recovery=load_at(hist,G_BASE);peak_load=load
    trace=[[0,round(peak_nits,2)]];r_max=recovery
    if not p['enabled'] or not peak_nits or load<=p['l_th']:
        return dict(duration=None if peak_nits else 0,stable_nits=round(peak_nits,2),stop='disabled' if not p['enabled'] else 'threshold',k=K_MAX,trace=trace,r_max=r_max,load_peak=peak_load)
    charge=min(load,C_MAX)
    if recovery<p['r_reset'] and p['e0']>charge:
        return dict(duration=None,stable_nits=round(peak_nits,2),stop='reset',k=K_MAX,trace=trace,r_max=r_max,load_peak=peak_load)
    frames=max(1,(p['e0']+charge-1)//charge)
    state.energy=max(0,p['e0']-(frames-1)*charge);state.r_prev=recovery
    # The first dimmed output is the frame AFTER the state first decreases.
    duration=frames/hz;trace.append([(frames-1)/hz,round(peak_nits,2)])
    seen={};stop='limit';last_gain=G_BASE;cycle=None
    for n in range(4096):
        gain=state.g_prev;load,recovery=load_at(hist,gain);r_max=max(r_max,recovery)
        key=(state.k,state.energy,state.r_prev,state.g_prev)
        if key in seen:
            period=(n-seen[key])/hz
            if n-seen[key]==1:stop='reset-fixed'
            else:
                stop='cycle';start=(frames+seen[key]-1)/hz;end=(frames+n-1)/hz
                value=round(peak_nits*state.g_prev/G_BASE,2)
                points=[[0,value]]+[[t-start,v] for t,v in trace if start<t<end]+[[period,value]]
                cycle=dict(start_s=start,period_s=period,min_nits=min(v for _,v in points),max_nits=max(v for _,v in points),trace=points)
                trace.append([end,value])
            break
        seen[key]=n
        if load<=p['l_th'] and min(state.r_prev,recovery)>=p['r_reset']:stop='threshold';break
        if state.k==K_MIN and min(state.r_prev,recovery)>=p['r_reset']:stop='floor';break
        step(state,load,recovery,**{k:v for k,v in p.items() if k!='enabled'})
        if state.g_prev!=last_gain:
            trace.append([(frames+n)/hz,round(peak_nits*state.g_prev/G_BASE,2)]);last_gain=state.g_prev
    # No fabricated steady-state when a reset oscillation exists.
    value=round(peak_nits*state.g_prev/G_BASE,2)
    if len(trace)>80:trace=[trace[0],trace[1]]+[trace[i] for i in range(2,len(trace)-1,max(1,len(trace)//70))]+[trace[-1]]
    return dict(duration=duration,stable_nits=None if stop in ('cycle','limit') else value,ending_nits=value,stop=stop,cycle=cycle,k=state.k,trace=trace,r_max=r_max,load_peak=peak_load)

# Equivalent-load convenience reference, NOT watts or a new optical calibration.
def raw_from_nit(nit):
    return nit*18288/751 if nit<=751 else 18288+(nit-751)*(31243-18288)/(1236-751)
def nit_from_raw(raw):
    return raw*751/18288 if raw<=18288 else 751+(raw-18288)*(1236-751)/(31243-18288)
