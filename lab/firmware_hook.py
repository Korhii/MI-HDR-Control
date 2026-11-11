"""Run the uniform/OEM-policy adapter with the extracted original ARM64 caller."""
from pathlib import Path
import io,struct,sys
from local_asset_paths import budget_module
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/predict-libs'))
from elftools.elf.elffile import ELFFile
from firmware_budget import Algorithm,source_for,SYMBOLS
MOD,CFG,TICK=0x200000,0x50000000,0xffffffc009bc6980
DATA_BASE,BSS_BASE=0x15ef60,0x102f08
INFO=SYMBOLS['bCusHdrInfo']
e=ELFFile(io.BytesIO(budget_module().read_bytes()))
syms=e.get_section_by_name('.symtab');indices={s.name:s for s in syms.iter_symbols()}
def install(a,value=41,lease=100000,native_abl=None):
    u=a.u;u.mem_map(MOD,0x10000);u.mem_map(CFG,0x1000);u.mem_map(TICK&~0xfff,0x1000)
    p=native_abl or {};config=[0]*48
    for i,v in {0:value,4:lease,8:int(p.get('enabled',False)),9:p.get('l_th',18288),10:p.get('e0',37491600),11:p.get('divisor',600),12:p.get('r_reset',9760),13:31243,14:p.get('e0',37491600),16:65535,23:1,28:18288,29:31243,30:31243,31:65535,32:65535,35:18288,36:37491600,37:600,38:9760,39:65535}.items():config[i]=v
    u.mem_write(CFG,struct.pack('<48IQQQ',*config,DATA_BASE,BSS_BASE,0x152000))
    text=bytearray(e.get_section_by_name('.text').data())
    for section in e.iter_sections():
        if section['sh_type']!='SHT_RELA' or e.get_section(section['sh_info']).name!='.text':continue
        for r in section.iter_relocations():
            name=syms.get_symbol(r['r_info_sym']).name;off=r['r_offset']
            if not name.startswith('mi_'):continue
            address={'mi_cfg':CFG,'mi_return':0x1a57e0,'mi_post_return':0x1a5e30,'mi_native_return':0x1a645c}.get(name,MOD+indices[name]['st_value'])+r['r_addend']
            kind=r['r_info_type']
            if kind==257:struct.pack_into('<Q',text,off,address)
            elif kind in (282,283):
                assert -(1<<27)<=address-(MOD+off)<1<<27
                struct.pack_into('<I',text,off,(0x14000000 if kind==282 else 0x94000000)|(((address-MOD-off)>>2)&0x3ffffff))
            else:raise AssertionError((name,kind))
    u.mem_write(MOD,bytes(text))
    for addr,name in [(0x1a57dc,'mi_hook'),(0x1a5e2c,'mi_post'),(0x1a6458,'mi_native_gate')]:
        word=0x14000000|(((MOD+indices[name]['st_value']-addr)>>2)&0x3ffffff)
        u.mem_write(addr,struct.pack('<I',word));u.ctl_remove_cache(addr,addr+4)
    return config

def frame(a,source,tick):
    a.u.mem_write(TICK,struct.pack('<Q',tick));return a.frame(source)
