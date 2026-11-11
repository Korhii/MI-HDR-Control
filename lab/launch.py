"""Start the owned desktop service; the native EXE owns its visible lifetime."""
import argparse,json,os,subprocess,time,urllib.request,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from portable_paths import activate
activate(ROOT)
URL='http://127.0.0.1:'+os.environ.get('MI_CONTROL_PORT','18533')
def state():
    try:
        with urllib.request.urlopen(URL+'/api/state',timeout=1) as response:return json.load(response)
    except (OSError,ValueError):return None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--desktop-ready',type=Path);parser.add_argument('--owner',type=int);args=parser.parse_args()
    if not args.desktop_ready:
        subprocess.Popen([str(ROOT/'MI HDR Control.exe')],cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
        return
    for name in ('logs','tmp','state','profiles','experiments'):(ROOT/name).mkdir(exist_ok=True)
    current=state()
    if current and (current.get('app')!='mi-hdr-control' or current.get('instance_root')!=str(ROOT)):
        raise RuntimeError('另一个目录的控制器正在运行，请先退出旧副本。')
    if args.desktop_ready and current:raise RuntimeError('已有浏览器版服务，请先运行本目录“停止控制器.cmd”。')
    process=None
    if not current:
        env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
        if args.owner:env['MI_DESKTOP_OWNER_PID']=str(args.owner)
        with (ROOT/'logs/service.log').open('a',encoding='utf-8') as out:
            process=subprocess.Popen([str(ROOT/'tools/python/python.exe'),'-u',str(ROOT/'lab/portable_server.py')],cwd=ROOT,env=env,stdout=out,stderr=out,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            current=state()
            if current:break
            if process.poll() is not None:break
            time.sleep(.1)
    if not current:raise RuntimeError('服务未启动，请查看 logs/service.log。')
    if args.desktop_ready:
        assert process is not None
        temporary=args.desktop_ready.with_suffix('.tmp');temporary.write_text(URL+'\n'+str(process.pid)+'\n',encoding='utf-8');temporary.replace(args.desktop_ready)
if __name__=='__main__':
    try:main()
    except Exception as error:
        (ROOT/'logs').mkdir(exist_ok=True)
        with (ROOT/'logs/service.log').open('a',encoding='utf-8') as log:log.write('Launch error: '+str(error)+'\n')
        raise SystemExit(1)
