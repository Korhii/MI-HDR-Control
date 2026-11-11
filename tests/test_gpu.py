"""Actual D3D11 GPU readback, hidden windows; no ADB or monitor writes."""
from pathlib import Path
import json
import subprocess
import sys
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lab'))
from features import PATTERN,write_pattern
D=ROOT/'experiments'/('gpu-test-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));D.mkdir(parents=True)
cases=[('single_pixel',dict(pixel_width=1,pixel_height=1),1),
       ('4x2',dict(pixel_width=4,pixel_height=2),8),
       ('array64',dict(pixel_width=1,pixel_height=1,rows=8,cols=8),64),
       ('array_100',dict(rows=3,cols=5,area_percent=100),8294400),
       ('50pct',dict(area_percent=50),None),('75pct',dict(area_percent=75),None),
       ('100pct',dict(area_percent=100),8294400),('black',dict(area_percent=0,input_nits=0),0),
       ('labelled',dict(area_percent=100,label=True,input_nits=1000),8294400),
       ('fullblack_label',dict(area_percent=100,label=True,input_nits=0),8294400)]
results=[]
for i,(name,changes,expected) in enumerate(cases):
    folder=D/name;folder.mkdir();c=dict(PATTERN,**changes);write_pattern(folder/'config.txt',c,i+1)
    (folder/'status.txt').write_text('测试参数 "100%" · 原厂/实验 · 未标定nit',encoding='utf-8')
    cmd=[str(ROOT/'tools/hdr-pattern-control.exe'),str(folder/'config.txt'),str(folder/'check.json'),str(folder/'status.txt'),str(folder/'stop'),'check-only','1','0']
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
    row=dict(name=name,command=cmd,stdout=p.stdout,stderr=p.stderr,exit_status=p.returncode)
    (folder/'execution.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    assert p.returncode==0,(name,p.stderr)
    check=json.loads((folder/'check.json').read_text(encoding='utf-8'));row['readback']=check
    if name=='fullblack_label':assert check['lit_pixels_including_annotation']>0,'nit footer must remain visible on fullblack input'
    assert check['wrong_pixels']==0
    if expected is not None:
        if expected==8294400: expected=check['width']*check['height']
        assert check['geometric_pixels']==expected,(name,check)
    if not c['label'] and c['input_nits']>0:assert check['lit_pixels_including_annotation']==check['geometric_pixels']
    results.append(row);print(name,check['geometric_pixels'],check['actual_area_percent'],'wrong_pixels=0',flush=True)
(D/'result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(D)
