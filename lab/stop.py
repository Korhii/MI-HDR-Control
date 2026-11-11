import json
import os
import urllib.request
from pathlib import Path
URL='http://127.0.0.1:'+os.environ.get('MI_CONTROL_PORT','18533')
with urllib.request.urlopen(URL+'/api/state',timeout=3) as r:state=json.load(r)
if state.get('app')!='mi-hdr-control':raise RuntimeError('此端口不是控制器，未操作')
if state.get('instance_root')!=str(Path(__file__).resolve().parents[1]):raise RuntimeError('正在运行的是另一个目录的副本，未停止它')
request=urllib.request.Request(URL+'/api/shutdown',data=b'{}',headers={
    'Content-Type':'application/json','Origin':URL,'X-MI-Token':state['token']})
with urllib.request.urlopen(request,timeout=40) as r:print(r.read().decode())
