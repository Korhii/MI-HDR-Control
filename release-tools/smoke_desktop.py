"""Own EXE integration test: offline defaults and app-owned shutdown API. No ADB/UI input."""
from pathlib import Path
import argparse,json,os,socket,subprocess,time,urllib.request

def test(root):
 root=Path(root).resolve()
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 url='http://127.0.0.1:'+str(port)
 env={**os.environ,'MI_CONTROL_PORT':str(port),'MI_CONTROL_NO_AUTOCONNECT':'1','PYTHONDONTWRITEBYTECODE':'1'}
 startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
 command=[str(root/'MI HDR Control.exe')]
 p=subprocess.Popen(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,startupinfo=startup)
 state=None
 try:
  for _ in range(150):
   if p.poll() is not None:raise RuntimeError('Desktop exited before ready: '+str(p.returncode))
   try:
    with urllib.request.urlopen(url+'/api/state',timeout=.5) as r:state=json.load(r)
    if state:break
   except OSError:time.sleep(.1)
  assert state and state['instance_root']==str(root) and not state['connected'] and not state['live_debug']
  assert state['factory_budget'] and state['ui_preferences']['auto_connect'] is False
  assert 'launcher' not in state and 'launcher' not in state['capabilities']
  ready=root/'tmp'/('desktop-'+str(p.pid)+'.txt')
  for _ in range(50):
   if ready.exists():break
   time.sleep(.1)
  assert ready.exists()
  request=urllib.request.Request(url+'/api/shutdown',data=b'{}',headers={'Origin':url,'X-MI-Token':state['token'],'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=5) as r:assert json.load(r)['closing']
  stdout,stderr=p.communicate(timeout=20);assert p.returncode==0
  stopped=False
  for _ in range(40):
   try:urllib.request.urlopen(url+'/api/state',timeout=.3).close();time.sleep(.1)
   except OSError:stopped=True;break
  assert stopped,'App shutdown left its backend running'
  return dict(command=command,stdout=stdout.decode(errors='replace'),stderr=stderr.decode(errors='replace'),exit_status=p.returncode,
              unicode_path=any(ord(c)>127 for c in str(root)),space_in_path=' ' in str(root),native_ready_file=True,device_connected=False,
              factory_budget=True,auto_connect=False,app_shutdown_stopped_backend=True)
 finally:
  if p.poll() is None:
   if state:
    try:urllib.request.urlopen(urllib.request.Request(url+'/api/shutdown',data=b'{}',headers={'Origin':url,'X-MI-Token':state['token'],'Content-Type':'application/json'}),timeout=5).close()
    except OSError:pass
   try:p.wait(timeout=15)
   except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);a=parser.parse_args()
 result=test(a.candidate);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print('PASS native startup, offline/factory defaults and app-owned shutdown; exit=0')
