"""Remove local build-path prefixes only from non-loaded ELF debug strings.
Lengths, ELF headers, every PT_LOAD byte and runtime section remain unchanged.
"""
from pathlib import Path
import hashlib,io,re,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/predict-libs'))
from elftools.elf.elffile import ELFFile
PATTERN=re.compile(rb'[A-Z]:[\\/]+(?:Users[\\/]+[^\\/\x00]+|MI)[\\/]+')
def redact(data):
    elf=ELFFile(io.BytesIO(data));out=bytearray(data);count=0
    for section in elf.iter_sections():
        if section['sh_flags']&2 or not section.name.startswith('.debug'):continue
        raw=section.data()
        def replace(m):
            nonlocal count
            count+=1;return b'SOURCE'+b'_'*(len(m.group())-6)
        clean=PATTERN.sub(replace,raw)
        assert len(raw)==len(clean)
        off=section['sh_offset'];out[off:off+len(clean)]=clean
    result=bytes(out);after=ELFFile(io.BytesIO(result))
    for a,b in zip(elf.iter_segments(),after.iter_segments()):
        if a['p_type']=='PT_LOAD':assert a.header==b.header and a.data()==b.data()
    assert len(data)==len(result) and not PATTERN.search(result),'Build paths outside removable debug metadata require review'
    return result,count

if __name__=='__main__':
    source,destination=map(Path,sys.argv[1:]);original=source.read_bytes();clean,count=redact(original);destination.write_bytes(clean)
    print('Redacted debug prefixes='+str(count)+'; all PT_LOAD bytes unchanged')
