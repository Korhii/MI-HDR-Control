"""Relocate the owner's adaptive-HDR module; only layout facts and project RET stubs are bundled."""
from pathlib import Path
import hashlib,io,json,struct
from build_local_models import relocated
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]

def build(input_file,output_directory):
    layout=json.loads((ROOT/'resources/preparation/adaptive-layout.json').read_text('utf-8'))
    data=Path(input_file).read_bytes()
    if hashlib.sha256(data).hexdigest()!=layout['input_sha256']:raise ValueError('Unsupported adaptive HDR module; no device write')
    elf=ELFFile(io.BytesIO(data));sections=layout['sections'];addresses={s['name']:s['address'] for s in sections}
    payloads=relocated(elf,addresses,layout['symbols'],layout['relaxation'])
    payloads['.text']+=b''.join(struct.pack('<I',word) for word in layout['project_stub_words'])
    segments=[]
    for s in layout['segments']:segments.append((s,bytearray(s['size'])))
    for section in sections:
        if section['kind']==8:continue
        payload=bytes(payloads[section['name']]);assert len(payload)==section['size'],section['name']
        segment,buffer=next((s,a) for s,a in segments if s['address']<=section['address'] and section['address']+section['size']<=s['address']+s['size'])
        offset=section['address']-segment['address'];buffer[offset:offset+len(payload)]=payload
    image=bytearray(64+56*len(segments));programs=[];offsets={}
    for s,buffer in segments:
        image+=b'\0'*((-len(image))%8);offset=len(image);programs.append((1,s['flags'],offset,s['address'],s['address'],len(buffer),len(buffer),1));image+=buffer
        for section in sections:
            if s['address']<=section['address'] and section['address']+section['size']<=s['address']+s['size']:offsets[section['name']]=offset+section['address']-s['address']
    headers=[(0,0,0,0,0,0,0,0,0,0)];names=bytearray(b'\0')
    def add(name,kind,flags,address,offset,size,link=0,info=0,alignment=1,entry=0):
        n=len(names);names.extend(name.encode()+b'\0');headers.append((n,kind,flags,address,offset,size,link,info,alignment,entry));return len(headers)-1
    for s in sections:add(s['name'],s['kind'],s['flags'],s['address'],offsets[s['name']],s['size'],alignment=s['alignment'])
    strings=bytearray(b'\0');symbols=bytearray(bytes(24))
    for name,value in layout['symbols'].items():
        if not name or any(c in name for c in ('/','\\',':')):continue
        off=len(strings);strings.extend(name.encode()+b'\0');symbols+=struct.pack('<IBBHQQ',off,0x11,0,0xfff1,value,0)
    string_at=len(image);image+=strings;string_id=add('.strtab',3,0,0,string_at,len(strings))
    image+=b'\0'*((-len(image))%8);sym_at=len(image);image+=symbols;add('.symtab',2,0,0,sym_at,len(symbols),link=string_id,info=1,alignment=8,entry=24)
    name_at=len(image);name_id=add('.shstrtab',3,0,0,name_at,0);headers[name_id]=(*headers[name_id][:5],len(names),*headers[name_id][6:]);image+=names
    image+=b'\0'*((-len(image))%8);section_at=len(image)
    for row in headers:image+=struct.pack('<IIQQQQIIQQ',*row)
    ident=b'\x7fELF\x02\x01\x01'+bytes(9);image[:64]=struct.pack('<16sHHIQQQIHHHHHH',ident,2,183,1,0,64,section_at,0,64,56,len(programs),64,len(headers),name_id)
    for i,row in enumerate(programs):struct.pack_into('<IIQQQQQQ',image,64+i*56,*row)
    output=Path(output_directory);output.mkdir(parents=True,exist_ok=True);path=output/'adaptive.elf';path.write_bytes(image)
    reopened=ELFFile(io.BytesIO(path.read_bytes()));assert reopened.get_section_by_name('.symtab')
    for source,name in [('adaptive-types.json','types.json'),('adaptive-stubs.s','stubs.s')]:
        (output/name).write_bytes((ROOT/'resources/preparation'/source).read_bytes())
    return path
