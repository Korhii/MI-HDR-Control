"""Prepare a fresh module copy for this boot's driver addresses; never writes device memory."""
import argparse,hashlib,json,struct
from pathlib import Path

def prepare(source,manifest,text,bss,data):
    if len(source)!=manifest['bytes'] or hashlib.sha256(source).hexdigest()!=manifest['sha256']:
        raise ValueError('Module template mismatch')
    if manifest['schema']!='mi-hdr-module-addresses-v1':raise ValueError('Unknown relocation schema')
    if text&0xffffffff00000fff!=0xffffffc000000000 or bss!=text+0x3c000 or data!=text+0x98060:
        raise ValueError('Driver section layout mismatch')
    bases=dict(text=text,bss=bss,data=data);result=bytearray(source)
    for slot in manifest['entries']:
        if struct.unpack_from('<Q',result,slot['offset'])[0]!=slot['expected']:
            raise ValueError('Address slot mismatch')
        struct.pack_into('<Q',result,slot['offset'],bases[slot['region']]+slot['addend'])
    return bytes(result)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('manifest',type=Path);p.add_argument('output',type=Path)
    for name in ('text','bss','data'):p.add_argument('--'+name,required=True,type=lambda x:int(x,0))
    a=p.parse_args();result=prepare(a.source.read_bytes(),json.loads(a.manifest.read_text(encoding='utf-8')),a.text,a.bss,a.data)
    with a.output.open('xb') as f:f.write(result)
    assert a.output.read_bytes()==result
    print(json.dumps(dict(output=str(a.output.resolve()),bytes=len(result),sha256=hashlib.sha256(result).hexdigest(),installed=False)))
