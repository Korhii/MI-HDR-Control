"""Prepare offline ARM64 images from the owner's unmodified device modules.

No device execution, compiler, Ghidra, downloaded firmware, or model binaries are needed.
Only the explicitly fingerprinted firmware layout is supported.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/predict-libs'))
from elftools.elf.elffile import ELFFile

INPUTS={
    'kdrv_ldm_sys.ko':'eabc6d525ddd76cfaa9855b137af2df7247bccd4ec7166edef4d0dbfae5db4cd',
    'mdrv_ldm.ko':'b23277ed8f914a4bdb759571fea940c9c37e7d85578803873d926a42c7764c01',
}


def source(path,expected):
    data=Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError('Unsupported firmware module: '+Path(path).name)
    return data,ELFFile(io.BytesIO(data))


def relocated(elf,addresses,externals,relax=False):
    """Apply the AArch64 static relocation kinds present in the supported inputs."""
    data={s.name:bytearray(s.data()) for s in elf.iter_sections() if s['sh_type']!='SHT_NOBITS'}
    symbols=elf.get_section_by_name('.symtab')
    def address(symbol):
        index=symbol['st_shndx']
        if index=='SHN_UNDEF':return externals[symbol.name]
        if index=='SHN_ABS':return symbol['st_value']
        return addresses[elf.get_section(index).name]+symbol['st_value']
    pairs={}
    for section in elf.iter_sections():
        if section['sh_type']!='SHT_RELA':continue
        target=elf.get_section(section['sh_info'])
        if target.name not in addresses:continue
        buffer=data[target.name]
        for relocation in section.iter_relocations():
            offset=relocation['r_offset'];kind=relocation['r_info_type']
            value=address(symbols.get_symbol(relocation['r_info_sym']))+relocation['r_addend']
            place=addresses[target.name]+offset
            if kind in (275,277):pairs[(target.name,offset)]=(kind,value)
            if kind in (257,258,260,261):
                size=8 if kind in (257,260) else 4
                if kind in (260,261):value-=place
                buffer[offset:offset+size]=(value&((1<<(size*8))-1)).to_bytes(size,'little')
                continue
            instruction=struct.unpack_from('<I',buffer,offset)[0]
            if kind==275:
                displacement=((value&~4095)-(place&~4095))>>12
                instruction=(instruction&~0x60ffffe0)|((displacement&3)<<29)|(((displacement>>2)&0x7ffff)<<5)
            elif kind in (277,278,284,285,286,299):
                scale={277:0,278:0,284:1,285:2,286:3,299:4}[kind]
                instruction=(instruction&~0x003ffc00)|(((value&4095)>>scale)<<10)
            elif kind in (282,283):
                instruction=(instruction&0xfc000000)|(((value-place)>>2)&0x3ffffff)
            else:raise ValueError('Unsupported AArch64 relocation: '+str(kind))
            struct.pack_into('<I',buffer,offset,instruction)
    if relax:
        # Match the original static linker's ADRP/ADD -> NOP/ADR relaxation.
        for (name,offset),(kind,value) in pairs.items():
            if offset not in (relax.get(name,[]) if isinstance(relax,dict) else relax if name=='.text' else []):continue
            if kind!=275 or pairs.get((name,offset+4))!=(277,value):continue
            buffer=data[name];first,second=struct.unpack_from('<II',buffer,offset)
            register=first&31;delta=value-(addresses[name]+offset+4)
            if second&0xffc00000==0x91000000 and second&31==register and (second>>5)&31==register and -(1<<20)<=delta<(1<<20):
                adr=0x10000000|((delta&3)<<29)|(((delta>>2)&0x7ffff)<<5)|register
                struct.pack_into('<II',buffer,offset,0xd503201f,adr)
    return data


def ldm_image(raw,elf,destination):
    layout=json.loads((ROOT/'resources/preparation/ldm-layout.json').read_text('utf-8'))
    addresses={b['name']:b['start'] for b in layout['blocks'] if b['start']}
    undefined=[s.name for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name and s['st_shndx']=='SHN_UNDEF']
    externals={name:addresses['EXTERNAL']+i*8 for i,name in enumerate(undefined)}
    data=relocated(elf,addresses,externals)
    destination.mkdir(parents=True,exist_ok=True)
    for block in layout['blocks']:
        if not block['file']:continue
        name=block['name']
        if name=='_elfHeader':content=raw[:elf['e_ehsize']]
        elif name=='_elfSectionHeaders':content=raw[elf['e_shoff']:elf['e_shoff']+elf['e_shentsize']*elf['e_shnum']]
        else:content=bytes(data[name])
        if len(content)!=block['size']:raise ValueError('Unexpected section size: '+name)
        (destination/block['file']).write_bytes(content)
    (destination/'manifest.json').write_text(json.dumps(layout,separators=(',',':')),encoding='utf-8')


def mdrv_image(elf,destination):
    layout=json.loads((ROOT/'resources/preparation/mdrv-layout.json').read_text('utf-8'))
    sections=layout['sections'];addresses={s['name']:s['address'] for s in sections}
    addresses['.text.ftrace_trampoline']=addresses['.text']+elf.get_section_by_name('.text')['sh_size']
    externals={name:layout['stub_start']+i*4 for i,name in enumerate(layout['stubs'])}
    data=relocated(elf,addresses,externals,relax=set(layout['relax_offsets']))
    text=bytearray(sections[0]['size']);text[:len(data['.text'])]=data['.text']
    stub_offset=layout['stub_start']-addresses['.text']
    text[stub_offset:]=bytes.fromhex('c0035fd6')*len(layout['stubs'])
    data['.text']=text
    # Keep the same emulated load addresses; omit historical linker debug records.
    segments=layout['segments'];result=bytearray(4096);segment_offsets=[]
    for segment in segments:
        result.extend(bytes((-len(result))%4096));offset=len(result);segment_offsets.append(offset)
        buffer=bytearray(segment['filesz'])
        for section in sections:
            delta=section['address']-segment['address']
            if section['type']!=8 and 0<=delta and delta+section['size']<=len(buffer):
                content=data[section['name']]
                if len(content)!=section['size']:raise ValueError('Unexpected model section size')
                buffer[delta:delta+len(content)]=content
        result.extend(buffer)
    headers=[[0]*10];names=bytearray(b'\0')
    def name(text):
        offset=len(names);names.extend(text.encode()+b'\0');return offset
    for section in sections:
        offset=0
        for segment,start in zip(segments,segment_offsets):
            delta=section['address']-segment['address']
            if 0<=delta and delta+section['size']<=segment['memsz']:
                offset=start+delta;break
        headers.append([name(section['name']),section['type'],section['flags'],section['address'],offset,section['size'],0,0,section['align'],0])
    indices={s['name']:i+1 for i,s in enumerate(sections)}
    symtab=elf.get_section_by_name('.symtab');strings=elf.get_section(symtab['sh_link']).data();table=bytearray(symtab.data())
    for i,symbol in enumerate(symtab.iter_symbols()):
        index=symbol['st_shndx'];value=symbol['st_value'];new_index=0
        if index=='SHN_UNDEF' and symbol.name:
            value=externals[symbol.name];new_index=indices['.text'];table[i*24+4]=0x12
        elif isinstance(index,int) and index:
            section_name=elf.get_section(index).name
            if section_name in addresses:
                value=addresses[section_name]+value;new_index=indices.get(section_name,indices['.text'])
            else:value=0
        elif index=='SHN_ABS':new_index=0xfff1
        struct.pack_into('<H',table,i*24+6,new_index);struct.pack_into('<Q',table,i*24+8,value)
    def append_section(section_name,content,kind,align=1,link=0,info=0,entsize=0):
        result.extend(bytes((-len(result))%align));offset=len(result);result.extend(content)
        headers.append([name(section_name),kind,0,0,offset,len(content),link,info,align,entsize])
    symbol_index=len(headers)
    append_section('.symtab',table,2,8,link=symbol_index+1,info=symtab['sh_info'],entsize=24)
    append_section('.strtab',strings,3)
    shstr_index=len(headers);shstr_name=name('.shstrtab');offset=len(result);result.extend(names)
    headers.append([shstr_name,3,0,0,offset,len(names),0,0,1,0])
    result.extend(bytes((-len(result))%8));shoff=len(result)
    for header in headers:result.extend(struct.pack('<IIQQQQIIQQ',*header))
    ident=b'\x7fELF\x02\x01\x01'+bytes(9)
    struct.pack_into('<16sHHIQQQIHHHHHH',result,0,ident,2,183,1,0,64,shoff,0,64,56,len(segments),64,len(headers),shstr_index)
    for i,(segment,offset) in enumerate(zip(segments,segment_offsets)):
        struct.pack_into('<IIQQQQQQ',result,64+i*56,1,segment['flags'],offset,segment['address'],segment['address'],segment['filesz'],segment['memsz'],4096)
    destination.write_bytes(result)


def build(input_directory,output_directory):
    input_directory=Path(input_directory);output_directory=Path(output_directory)
    modules={name:source(input_directory/name,digest) for name,digest in INPUTS.items()}
    output_directory.mkdir(parents=True,exist_ok=True)
    raw,elf=modules['kdrv_ldm_sys.ko'];ldm_image(raw,elf,output_directory/'ldm113')
    _,elf=modules['mdrv_ldm.ko'];mdrv_image(elf,output_directory/'mdrv-test.elf')
    return dict(output=str(output_directory.resolve()),source_modules=list(INPUTS),device_written=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_directory',type=Path);parser.add_argument('output_directory',type=Path)
    args=parser.parse_args();print(json.dumps(build(args.input_directory,args.output_directory)))
