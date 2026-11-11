"""Execute the firmware's linked ARM64 scaling and spatial-filter functions.
Only hardware getters/host libc calls are fixtures. Never opens ADB.
"""
from pathlib import Path
import sys,struct,json,hashlib,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tools/predict-libs')]
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import *
from local_asset_paths import model_directory
D=model_directory()
class Driver:
    def __init__(self):
        self.u=u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
        with (D/'mdrv-test.elf').open('rb') as f:
            e=ELFFile(f);segments=[s for s in e.iter_segments() if s['p_type']=='PT_LOAD']
            lo=min(s['p_vaddr'] for s in segments)&~4095;hi=(max(s['p_vaddr']+s['p_memsz'] for s in segments)+4095)&~4095
            u.mem_map(lo,hi-lo)
            for s in segments:u.mem_write(s['p_vaddr'],s.data())
            self.symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols() if s.name}
        u.mem_map(0x50000000,0x2000000);u.mem_map(0x60000000,0x400000)
        u.reg_write(UC_ARM64_REG_SP_EL0,0x60300000);u.cpr_write(3,0,1,0,2,3<<20)
        self.put('mstar_pm_base',0x50000000,8)
        self.alpha=[0]*8;self.width=self.height=1
        self.hooks={address:name for name,address in self.symbols.items() if name.startswith('MHal_LD_Get') or name in ('MDrv_XC_VR_ReadByte','memset','memcpy','_printk','kernel_neon_begin','kernel_neon_end','__cfi_slowpath_diag')}
        
        for address in self.hooks:u.hook_add(UC_HOOK_CODE,self.host,begin=address,end=address)
    def put(self,name,value,size=4):self.u.mem_write(self.symbols[name],value.to_bytes(size,'little'))
    def host(self,u,address,size,data):
        name=self.hooks.get(address)
        if not name:return
        x=[u.reg_read(UC_ARM64_REG_X0+i) for i in range(3)]
        values={'MHal_LD_GetLDFBacklightWidth':self.width,'MHal_LD_GetLDFBacklightHeight':self.height,'MHal_LD_GetLDFDCMaxAlpha':8,'MHal_LD_Get_LDF_Blend':8,'MHal_LD_Get_LDF_DynamicAlphaEn':1,'MHal_LD_GetLDFWriteDCMaxEn':1}
        result=values.get(name,0)
        if name=='MHal_LD_Get_DynamicAlpha':result=self.alpha[x[0]]
        if name=='memset':u.mem_write(x[0],bytes([x[1]&255])*x[2]);result=x[0]
        if name=='memcpy':u.mem_write(x[0],bytes(u.mem_read(x[1],x[2])));result=x[0]
        u.reg_write(UC_ARM64_REG_X0,result);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30))
    def call(self,name,*args):
        u=self.u
        for i in range(8):u.reg_write(UC_ARM64_REG_X0+i,args[i] if i<len(args) else 0)
        u.reg_write(UC_ARM64_REG_SP,0x60010000);u.reg_write(UC_ARM64_REG_X18,0x60020000);u.reg_write(UC_ARM64_REG_X30,0x603f0000)
        u.emu_start(self.symbols[name],0x603f0000,count=3000000)
        assert u.reg_read(UC_ARM64_REG_PC)==0x603f0000,name
    def scaling(self,mean,maximum,alpha):
        self.width=self.height=1;self.alpha=alpha
        self.put('gu16LedWidth',1);self.put('gu16LedHeight',1)
        self.u.mem_write(0x60100000,bytes([mean,maximum]))
        self.call('MDrv_LD_AlgoScalingDown',0x60100000,0x60110000,0x60120000)
        return struct.unpack('<H',self.u.mem_read(0x60110000,2))[0]
    def spatial(self,k,block=1):
        w,h=48,24;r=k
        source=[65280 if abs(x-w//2)<=block//2 and abs(y-h//2)<=block//2 else 0 for y in range(h) for x in range(w)]
        coefficients=[0]*(16*11)
        sf=[255]*5;sf[k-1]=0
        for y in range(2*r+1):
            for x in range(2*r+1):
                ring=max(abs(x-r),abs(y-r));coefficients[y*16+x]=(sf[ring-1]<<8) if ring else 0
        self.u.mem_write(0x60100000,struct.pack('<1152H',*source));self.u.mem_write(0x60130000,struct.pack('<176H',*coefficients))
        name='MDrv_Alg_LD_SpatialFilter_NonLinearMode_'+('One' if k<4 else 'Two')+'_Array_NEON'
        self.call(name,0x60100000,0x60110000,h,w,0x60130000,r,r)
        out=struct.unpack('<1152H',self.u.mem_read(0x60110000,2304))
        changed=[(x-w//2,y-h//2,out[y*w+x]) for y in range(h) for x in range(w) if out[y*w+x]!=source[y*w+x]]
        return dict(sf=k,block=block,changed_count=len(changed),max_edge_ring=max((max(abs(x)-block//2,abs(y)-block//2,0) for x,y,v in changed),default=0),changed=changed)

