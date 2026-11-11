"""Original ARM64 256-point TMO with OEM LUTs; stationary synthetic-window fixture.
The output is algorithm luminance, not measured screen luminance. No ADB access.
"""
from pathlib import Path
from functools import lru_cache
import json,re,struct
from firmware_scaling import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,ELFFile
from unicorn.arm64_const import *
import device_models

ROOT=Path(__file__).resolve().parents[1]
from local_asset_paths import model_directory,models_directory
IMAGE=model_directory()/'adaptive-hdr'
FILES={5:'HDR.ini',0:'HDR_GRADATION.ini',1:'HDR_BRIGHTNESS.ini',2:'HDR_DYNAMIC.ini'}
LUTS=[('Hdr_Oetf_Max_Nits_Lut','hdr_oetf_lut_1_10000nit.bin'),('Hdr_Oetf_Min_Nits_Lut','hdr_oetf_lut_0_100nit.bin'),('Hdr_Eotf_Max_Nits_Lut','hdr_eotf_lut_1_10000nit.bin'),('Hdr_Eotf_Min_Nits_Lut','hdr_eotf_lut_0_92nit.bin'),('Hdr_Cust_Pow_Lut','cust_pow.bin')]

class ToneAlgorithm:
    def __init__(self):
        self.types=json.loads((IMAGE/'types.json').read_text(encoding='utf-8'))
        self.u=u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
        with (IMAGE/'adaptive.elf').open('rb') as fh:
            elf=ELFFile(fh);segments=[s for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
            lo=min(s['p_vaddr'] for s in segments)&~4095;hi=(max(s['p_vaddr']+s['p_memsz'] for s in segments)+4095)&~4095
            u.mem_map(lo,hi-lo)
            for s in segments:u.mem_write(s['p_vaddr'],s.data())
            self.symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
            self.initial=[(s['p_vaddr'],bytes(u.mem_read(s['p_vaddr'],s['p_memsz']))) for s in segments if s['p_flags']&2]
        u.mem_map(0x60000000,0x1000000);u.reg_write(UC_ARM64_REG_SP_EL0,0x60e00000);u.cpr_write(3,0,1,0,2,3<<20)
        self.source=bytes(u.mem_read(self.symbols['_u32Tmo256PointsInputValue'],1024))
        self.luts=[]
        for i,(field,name) in enumerate(LUTS):
            addr=0x60400000+i*0x100000;u.mem_write(addr,(IMAGE/'luts'/name).read_bytes());self.luts.append((field,addr))
        self.hooks={self.symbols[n]:n for n in re.findall(r'^(\w+): ret$',(IMAGE/'stubs.s').read_text(),re.M)}
        for addr in self.hooks:u.hook_add(UC_HOOK_CODE,self.host,begin=addr,end=addr)
        self.ldm=(0,0,0,3,0,0)

    def put(self,root,name,value):
        f=self.types[root]['fields'][name];self.u.mem_write(self.symbols[root]+f['offset'],int(value).to_bytes(f['size'] or 8,'little'))
    def get(self,root,name):
        f=self.types[root]['fields'][name];return int.from_bytes(self.u.mem_read(self.symbols[root]+f['offset'],f['size'] or 8),'little')
    def host(self,u,addr,size,data):
        name=self.hooks[addr];x=[u.reg_read(UC_ARM64_REG_X0+i) for i in range(3)];result=0
        if name=='memcpy':u.mem_write(x[0],bytes(u.mem_read(x[1],x[2])));result=x[0]
        elif name=='memset':u.mem_write(x[0],bytes([x[1]&255])*x[2]);result=x[0]
        elif name=='query_ldm_current_params':u.mem_write(x[0],struct.pack('<6I',*self.ldm));result=1
        elif name in ('_raw_spin_lock_irqsave','_raw_spin_unlock_irqrestore','__cfi_slowpath_diag','_printk'):pass
        else:raise RuntimeError('Unmodelled TMO host call: '+name)
        u.reg_write(UC_ARM64_REG_X0,result);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30))

    def configure(self,model,tone):
        for addr,blob in self.initial:self.u.mem_write(addr,blob)
        spec=device_models.spec(model);folder=spec['variants'][spec['default_variant']]['hdr_folder']
        text=(models_directory()/model/folder/FILES[tone]).read_text(encoding='utf-8')
        aliases={'u8_HDR_GT_filter':'GT_filter','u8_HDR_GT_filter_step':'GT_filter_step','u8_HDR_KT_filter':'KT_filter','u8_HDR_KT_filter_step':'KT_filter_step','u16_Backlight_APL_Base':'Backlight_APL_Base'}
        for name,value in re.findall(r'^\s*(\w+)\s*=\s*(\d+)\s*;',text,re.M):
            name=aliases.get(name,name)
            if name in self.types['hist_info']['fields']:self.put('hist_info',name,int(value))
        for name,values in re.findall(r'(\w+)\s*=\s*\{([^}]+)\}',text):
            f=self.types['hist_info']['fields'].get(name)
            if f:self.u.mem_write(self.symbols['hist_info']+f['offset'],b''.join(int(v).to_bytes(f['size'],'little') for v in values.split()))
        # Mirror OEM gamma parsing: nonzero APL entries override compiled defaults.
        # 27 gamma was not acquired; use screenshot APL anchors, explicitly estimated.
        if model=='32u-2026':
            references=json.loads((ROOT/'resources/preparation/reference-apl.json').read_text('utf-8'))['values']
            for section,suffix in [('APLWindow',''),('APLWindow_High','_High')]:
                for area,value in references[section].items():
                    if value>0:self.put('hist_info','u32_APL'+area+suffix+'_Level',value)
        else:
            ref=device_models.window_reference(model)
            for level,suffix in [('medium',''),('high','_High')]:
                for area in (10,25,50,75,100):self.put('hist_info','u32_APL'+str(area)+suffix+'_Level',ref['tones']['5'][level][ref['areas'].index(area)])
        # Stationary comparison, not a simulation of transition time or ambient adaptation.
        for name in ('GT_filter','KT_filter','u8_Peak_Luma_Filter'):self.put('hist_info',name,0)
        self.put('hist_info','u32_TF_Str',256)
        for field,addr in self.luts:self.put('hist_info',field,addr)
        self.put('display_dev','HDR_init_falg',1);self.put('hist_ctl','Backlight_level',255)
        self.put('hist_ctl','HDR_Pic_Mode',16);self.put('hist_ctl','u32HdrMode',tone)

    def run(self,model,tone,area,q,ldm):
        from firmware_model import pq,interp
        self.configure(model,tone);self.ldm=tuple(ldm);u=self.u;p=0x60200000
        apl=round(pq(q)*255*65536*area/100) if q else 0
        u.mem_write(p,struct.pack('<I4xQI4xQiBB6x',256,0x60210000,256,0x60220000,apl,0,0))
        u.mem_write(p+40,bytes(48));u.mem_write(p+72,struct.pack('<4I',10000,0,10000,10000))
        u.mem_write(p+88,struct.pack('<I4xQ',128,0x60230000));u.mem_write(0x60210000,self.source);u.mem_write(0x60220000,self.source)
        hist=[0]*128;pixels=max(1,round(8294400*area/100)) if area>0 and q>0 else 0;index=min(127,round(pq(q)*127)) if q>0 else 0
        hist[0]=8294400-pixels;hist[index]+=pixels;u.mem_write(0x60230000,struct.pack('<128I',*hist))
        u.reg_write(UC_ARM64_REG_X0,p);u.reg_write(UC_ARM64_REG_X18,0x60d00000);u.reg_write(UC_ARM64_REG_SP,0x60c00000);u.reg_write(UC_ARM64_REG_X30,0x60ff0000)
        u.emu_start(self.symbols['Xiaomi_HDR_Adaptive_Algo_TMO256p_OETF'],0x60ff0000,count=10000000)
        if u.reg_read(UC_ARM64_REG_PC)!=0x60ff0000:raise RuntimeError('TMO offline instruction limit')
        src=struct.unpack('<256I',u.mem_read(0x60210000,1024));tgt=struct.unpack('<256I',u.mem_read(0x60220000,1024))
        points=dict(zip(src,tgt));mapped=interp(sorted(points.items()),q*1024)/1024 if q>0 else 0.
        return dict(mapped_nits=mapped,peak=self.get('hist_ctl','u32_Tgt_P0'),knee=self.get('hist_ctl','u32_Tgt_KS'),ldm=list(ldm),source=list(src),target=list(tgt))

@lru_cache(maxsize=1)
def algorithm():return ToneAlgorithm()

@lru_cache(maxsize=256)
def compare(model,tone,level,area,q):
    from ldf_response import Engine
    from firmware_budget import SYMBOLS
    c=device_models.defaults(level,model);engine=Engine(c,level,q,tone_enabled=False,device_type=device_models.spec(model)['led_type']);engine.run(engine.spatial(area),area,24)
    ldm=struct.unpack('<6I',engine.alg.u.mem_read(SYMBOLS['bCusHdrInfo'],24))
    a=algorithm();base=a.run(model,5,area,q,ldm);current=base if tone==5 else a.run(model,tone,area,q,ldm)
    return dict(ratio=current['mapped_nits']/base['mapped_nits'] if base['mapped_nits'] else 1.,hgig=base,current=current,
                basis='原厂ARM64 256点TMO+五张原厂LUT；纯窗直方图、10000nit元数据、统一内部HDR参考参数、HGiG以HDR.ini初始化、静态无时域滤波；实际切换历史可能影响结果，非屏幕nit实测')

@lru_cache(maxsize=256)
def equivalent_input(model,tone,level,area,q):
    if tone==5 or q<=0 or area<=0:return q
    from firmware_model import interp
    c=compare(model,tone,level,area,q)
    if abs(c['ratio']-1)<1e-8:return q
    # Convert into an equivalent HGiG signal instead of treating target-P0 ratios
    # as direct screen-nit multipliers. Plateaus use the first reachable input.
    inverse={}
    for x,y in zip(c['hgig']['source'],c['hgig']['target']):inverse.setdefault(y,x)
    return min(10000,max(0,interp(sorted(inverse.items()),c['current']['mapped_nits']*1024)/1024))
