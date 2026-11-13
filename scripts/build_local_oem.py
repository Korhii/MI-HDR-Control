"""Build the current project-owned adapter from the owner's original template; no compiler on consumer PCs."""
from pathlib import Path
import hashlib,io,json,struct,sys,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/predict-libs'))
from elftools.elf.elffile import ELFFile
SITE=0xffffffc002e2e7dc
OPS=0xffffffc0096ffc38
TEMPLATE_SHA256='788c06e5a7cc112c27fe54e9463ca18ea79ae878c98dc5b72058479948345297'
def build(input_file,output_directory):
    TEMPLATE=Path(input_file);D=Path(output_directory)
    if hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()!=TEMPLATE_SHA256:raise ValueError('Unsupported original module; no device write')
    D.mkdir(parents=True,exist_ok=True)
    obj=ROOT/'resources/preparation/oem-hooks.o'
    cobj=ROOT/'resources/preparation/oem-budget.o'
    helper=ELFFile(io.BytesIO(cobj.read_bytes()))
    original=TEMPLATE.read_bytes();elf=ELFFile(io.BytesIO(original));code=ELFFile(io.BytesIO(obj.read_bytes()))
    headers=[list(struct.unpack_from('<IIQQQQIIQQ',original,elf['e_shoff']+i*64)) for i in range(elf.num_sections())]
    data={i:s.data() for i,s in enumerate(elf.iter_sections()) if s['sh_type']!='SHT_NOBITS'}
    ids={s.name:i for i,s in enumerate(elf.iter_sections())};names=bytearray(data[ids['.shstrtab']])
    def section(name,content,kind=1,flags=0,align=8,link=0,info=0,entsize=0):
        index=len(headers);off=len(names);names.extend(name.encode()+b'\0')
        headers.append([off,kind,flags,0,0,len(content),link,info,align,entsize]);data[index]=bytes(content);return index
    cfg=section('.data.mi',struct.pack('<48IQQQ',24,0,0,0,0,0,0,0,0,18288,37491600,600,9760,31243,37491600,0,65535,0,0,0,22,0,0,1,0,0,65535,0,18288,31243,31243,65535,*([0]*16),0xffffffc002e97060,0xffffffc002e3b000,0)+bytes(448-216),flags=3)
    strings=bytearray(data[ids['.strtab']]);symtab=bytearray(data[ids['.symtab']]);symbol_ids={s.name:i for i,s in enumerate(elf.get_section_by_name('.symtab').iter_symbols())}
    def symbol(name,index,value,size=0,typ=1):
        pos=len(symtab)//24;off=len(strings);strings.extend(name.encode()+b'\0');symtab.extend(struct.pack('<IBBHQQ',off,0x10|typ,0,index,value,size));symbol_ids[name]=pos;return pos
    hook_offset=0x400;hook=code.get_section_by_name('.mi_hook').data()
    symbol('mi_cfg',cfg,0,448);symbol('mi_hook',ids['.text'],hook_offset,len(hook),2);symbol('mi_return',0xfff1,SITE+4)
    post_offset=0x600;post=code.get_section_by_name('.mi_post').data()
    helper_offset=0x1000;helper_code=helper.get_section_by_name('.text').data()
    symbol('mi_post',ids['.text'],post_offset,len(post),2);symbol('mi_post_return',0xfff1,0xffffffc002e2ee30)
    native_offset=0x800;native_code=code.get_section_by_name('.mi_native').data()
    symbol('mi_native_gate',ids['.text'],native_offset,len(native_code),2);symbol('mi_native_return',0xfff1,0xffffffc002e2f45c)
    for sym in helper.get_section_by_name('.symtab').iter_symbols():
        if sym.name in ('mi_budget_high','mi_budget_post','mi_install','mi_remove'):symbol(sym.name,ids['.text'],helper_offset+sym['st_value'],sym['st_size'],2)
    for section_info in helper.iter_sections():assert not (section_info['sh_type']=='SHT_RELA' and section_info['sh_size']),section_info.name
    blob=bytearray(data[ids['.text']])
    for off,content in [(hook_offset,hook),(post_offset,post),(native_offset,native_code),(helper_offset,helper_code)]:
        assert off+len(content)<=len(blob);blob[off:off+len(content)]=content
    data[ids['.text']]=blob
    for i,s in enumerate(elf.iter_sections()):
        if s['sh_type']=='SHT_RELA' and s['sh_info']==ids['.text']:
            data[i]=b''.join(struct.pack('<QQq',r['r_offset'],r['r_info'],r['r_addend']) for r in s.iter_relocations() if not any(off<=r['r_offset']<off+len(content) for off,content in [(hook_offset,hook),(post_offset,post),(native_offset,native_code),(helper_offset,helper_code)]))
        if s.name in ('.altinstructions','.rela.altinstructions','.rela.init.text','.rela.exit.text'):
            data[i]=b''
    for name,base in [('.init.text',0),('.exit.text',0),('.mi_hook',hook_offset),('.mi_post',post_offset),('.mi_native',native_offset)]:
        target=ids['.text'] if name in ('.mi_hook','.mi_post','.mi_native') else ids[name]
        content=code.get_section_by_name(name).data()
        if name not in ('.mi_hook','.mi_post','.mi_native'):
            data[target]=content
        relas=code.get_section_by_name('.rela'+name);out=bytearray()
        if relas:
            syms=code.get_section(relas['sh_link'])
            for r in relas.iter_relocations():
                symbol_name=syms.get_symbol(r['r_info_sym']).name
                assert symbol_name in symbol_ids,symbol_name
                out+=struct.pack('<QQq',base+r['r_offset'],symbol_ids[symbol_name]<<32|r['r_info_type'],r['r_addend'])
            section('.rela.mi'+name,out,kind=4,align=8,link=ids['.symtab'],info=target,entsize=24)
    # Expose supported values through ordinary module parameter sysfs operations.
    definitions=[('budget',cfg,0,0o644),('budget_used',cfg,4,0o444),('frames',cfg,8,0o444),('lease_end',cfg,16,0o644)]
    for name,index in [('enabled', 8), ('l_th', 9), ('e0', 10), ('divisor', 11), ('r_reset', 12), ('k', 13), ('energy', 14), ('r_prev', 15), ('gain_next', 16), ('load', 17), ('recovery', 18), ('charge', 19), ('delta', 20), ('triggered', 21), ('threshold', 22), ('generation', 23), ('gain_used', 26), ('active', 27), ('k_min', 28), ('k_max', 29), ('c_max', 30), ('g_base', 31), ('native_gain', 32), ('stat_floor', 33), ('native_calls', 34), ('factory_l_th', 35), ('factory_e0', 36), ('factory_divisor', 37), ('factory_r_reset', 38), ('factory_g_base', 39), ('budget_active', 40), ('source_format', 41), ('original_cap', 42), ('post_cap', 43), ('native_k',45), ('native_energy',46), ('native_r_prev',47)]:
        definitions.append((name,cfg,index*4,0o644 if name in ('enabled','l_th','e0','divisor','r_reset','generation') else 0o444))
    for name,index in [('hdr_sync',56),('hdr_generation',57),('hdr_active',58),('hdr_revision',60),('hdr_tone',61),('hdr_level',62),('hdr_gain',108)]+[('hdr_scale'+str(i),80+i) for i in range(11)]:
        definitions.append((name,cfg,index*4,0o644 if name in ('hdr_sync','hdr_generation','hdr_tone','hdr_level') or name.startswith('hdr_scale') else 0o444))
    hdr_fields=[('hdr_apl'+str(i),0x100+4*i) for i in range(11)]+[('hdr_p0',0x198),('hdr_mode_actual',0x18c),('hdr_picture',0x188),('hdr_floor',0xf4),('hdr_peak_filter',0xe8)]
    for name,offset in hdr_fields:
        symbol('mi_'+name,0xfff1,0);definitions.append((name,None,0,0o444))
    for name,address in [('tick',0xffffffc009bc6980),('raw_apl',0xffffffc002e97228),('raw_spi',0xffffffc002e9722c),('window',0xffffffc002e97230),('level',0xffffffc002e97234)]:
        symbol('mi_'+name,0xfff1,address);definitions.append((name,None,0,0o444))
    labels=b''.join(name.encode()+b'\0' for name,*_ in definitions);name_section=section('.rodata.mi_names',labels,flags=2,align=1)
    name_symbol=symbol('mi_param_names',name_section,0,len(labels));parameters=bytearray();relocs=[];name_offset=0
    def rela(off,sym,addend=0):relocs.append(struct.pack('<QQq',off,sym<<32|257,addend))
    for name,index,offset,perm in definitions:
        at=len(parameters);entry=bytearray(40);struct.pack_into('<QHbb',entry,16,OPS,perm,-1,0);parameters+=entry
        rela(at,name_symbol,name_offset);rela(at+8,symbol_ids['__this_module'])
        rela(at+32,symbol_ids['mi_cfg'] if index is not None else symbol_ids['mi_'+name],offset)
        name_offset+=len(name)+1
    params=section('__param',parameters,flags=2,entsize=40)
    section('.rela__param',b''.join(relocs),kind=4,link=ids['.symtab'],info=params,entsize=24)
    for name in ('.modinfo','.gnu.linkonce.this_module'):
        data[ids[name]]=data[ids[name]].replace(b'mtk_db_tool\0',b'mi_oemabl\0\0\0')
        assert len(data[ids[name]])==headers[ids[name]][5]
    data[ids['.symtab']]=symtab;data[ids['.strtab']]=strings;data[ids['.shstrtab']]=names
    result=bytearray(original)
    for i,h in enumerate(headers):
        if h[1]==8:continue
        content=data.get(i,b'');alignment=h[8] or 1
        result.extend(b'\0'*((-len(result))%alignment));h[4]=len(result);h[5]=len(content);result.extend(content)
    result.extend(b'\0'*((-len(result))%8));shoff=len(result)
    for h in headers:result.extend(struct.pack('<IIQQQQIIQQ',*h))
    struct.pack_into('<Q',result,40,shoff);struct.pack_into('<H',result,60,len(headers))
    path=D/'mi-oem-runtime.ko';path.write_bytes(result)
    # Reopen and validate cross-section links and required parameter size.
    e=ELFFile(io.BytesIO(path.read_bytes()));assert e.get_section_by_name('__param')['sh_size']==40*len(definitions)
    assert len(list(e.get_section_by_name('.symtab').iter_symbols()))==len(symtab)//24
    # File slots, not live memory writes. Every slot is guarded by the exact template hash.
    entries=[]
    def slot(offset,region,addend,expected):
        assert struct.unpack_from('<Q',result,offset)[0]==expected
        entries.append(dict(offset=offset,region=region,addend=addend,expected=expected))
    for name in ('.init.text','.exit.text'):
        s=e.get_section_by_name(name)
        for offset,addend in ((SITE,0x2f7dc),(0xffffffc002e2ee2c,0x2fe2c),(0xffffffc002e2f458,0x30458)):
            content=s.data();word=struct.pack('<Q',offset)
            assert content.count(word)==1,(name,hex(offset))
            slot(s['sh_offset']+content.index(word),'text',addend,offset)
    syms=e.get_section_by_name('.symtab')
    for i,s in enumerate(syms.iter_symbols()):
        mapping={'mi_native_return':('text',0x3045c),'mi_return':('text',0x2f7e0),'mi_post_return':('text',0x2fe30),
                 'mi_raw_apl':('data',0x1c8),'mi_raw_spi':('data',0x1cc),
                 'mi_window':('data',0x1d0),'mi_level':('data',0x1d4)}
        mapping.update({'mi_'+name:('hdr_data',offset) for name,offset in hdr_fields})
        if s.name in mapping:
            region,addend=mapping[s.name]
            assert s['st_shndx']=='SHN_ABS'
            slot(syms['sh_offset']+i*24+8,region,addend,s['st_value'])
    cfg_section=e.get_section_by_name('.data.mi')
    slot(cfg_section['sh_offset']+192,'data',0,0xffffffc002e97060)
    slot(cfg_section['sh_offset']+200,'bss',0,0xffffffc002e3b000)
    slot(cfg_section['sh_offset']+216,'hdr_data',0x38,0)
    assert len(entries)==32
    digest=hashlib.sha256(result).hexdigest()
    manifest=dict(schema='mi-hdr-module-addresses-v2',module='mi_oemabl',bytes=len(result),sha256=digest,entries=entries)
    (D/'budget-relocation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    header='#define MODULE_BYTES '+str(len(result))+'\n#define MODULE_SHA256 "'+digest+'"\n'
    header+='static const struct slot slots[]={\n'
    for x in entries:header+='  {%d,%d,0x%xULL,0x%xULL},\n'%(x['offset'],('text','bss','data','hdr_data').index(x['region']),x['addend'],x['expected'])
    (D/'budget_relocation.h').write_text(header+'};\n',encoding='utf-8')
    print(json.dumps({'output':str(path),'bytes':len(result),'parameters':[x[0] for x in definitions],'installed':False}))

    return path

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("input_file",type=Path);p.add_argument("output_directory",type=Path);a=p.parse_args();build(a.input_file,a.output_directory)
