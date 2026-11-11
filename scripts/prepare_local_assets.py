"""Prepare from the owner's files, without a compiler, AI, vendor downloads or parameter writes."""
from pathlib import Path
import hashlib,json,os,shutil,tempfile,threading,time
from local_asset_paths import ROOT,CACHE,generator_fingerprint
from build_local_models import build as model_build
from build_local_adaptive import build as adaptive_build
from build_local_oem import build as module_build
LOCK=threading.Lock()
def inputs():return json.loads((ROOT/'resources/preparation/inputs-v17.json').read_text('utf-8'))
def valid(cache):
    marker=cache/'complete.json'
    if not marker.exists():return False
    record=json.loads(marker.read_text('utf-8'))
    return record.get('generator')==generator_fingerprint() and record['source_sha256']=={k:v['sha256'] for k,v in inputs().items()} and all((cache/n).is_file() and hashlib.sha256((cache/n).read_bytes()).hexdigest()==h for n,h in record['generated_sha256'].items())
def prepare_directory(directory,cache=CACHE):
    directory=Path(directory);cache=Path(cache)
    with LOCK:
        for name,row in inputs().items():
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('原厂文件不匹配：'+name+'；未写入显示器')
        if valid(cache):return dict(ready=True,reused=True,output=str(cache),device_written=False)
        cache.parent.mkdir(parents=True,exist_ok=True);start=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='prepare-',dir=cache.parent) as temporary:
            staging=Path(temporary)/'assets';staging.mkdir();model_build(directory,staging/'model');adaptive_build(directory/'adaptive_hdr_algo.ko',staging/'model/adaptive-hdr');module_build(directory/'mtk-db-tool.ko',staging/'module')
            for name in inputs():
                if name.startswith('models/') or name.startswith('adaptive/luts/'):
                    relative=name if name.startswith('models/') else 'model/adaptive-hdr/luts/'+Path(name).name
                    output=staging/relative;output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(directory/name,output)
            for name in ('event.xml','event_upload.xml'):
                target=staging/'firmware'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(directory/name,target)
                text=(directory/name).read_text('utf-8');closing='</EventRoot>' if name=='event.xml' else '</Upload>'
                addition='<Event id="@EVENT_ID@" FaultType="FAULT" FaultLevel="CRITICAL" PrivacyLevel="L1">\n  <Param id="0" name="Research" type="string" len="40"/>\n</Event>\n' if name=='event.xml' else '<Event range1="@EVENT_ID@">\n  <Cmd FaultLevel="GENERAL" PrivacyLevel="L1" run="/system/bin/sh /data/miuilog/misight/MIHDRControl/phase.sh" output="MIHDR-persistence.log" option="block=90"/>\n</Event>\n'
                assert text.count(closing)==1;target=staging/'persistence'/name;target.parent.mkdir(exist_ok=True);target.write_text(text.replace(closing,addition+closing),encoding='utf-8',newline='\n')
            hashes={f.relative_to(staging).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in staging.rglob('*') if f.is_file()}
            record=dict(format='mi-local-assets-v17',generator=generator_fingerprint(),source_sha256={k:v['sha256'] for k,v in inputs().items()},generated_sha256=hashes)
            cache.mkdir(exist_ok=True);marker=cache/'complete.json'
            if marker.exists():marker.unlink()
            for f in staging.rglob('*'):
                if f.is_file():target=cache/f.relative_to(staging);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
            pending=cache/'complete.next.json';pending.write_text(json.dumps(record,indent=2),encoding='utf-8');os.replace(pending,marker)
        return dict(ready=True,reused=False,output=str(cache),seconds=round(time.monotonic()-start,3),device_written=False)
def prepare_device(device):
    rows=inputs()
    if valid(CACHE):
        text=device('shell','sha256sum '+' '.join(v['remote'] for v in rows.values()));observed={l.split()[-1]:l.split()[0] for l in text.splitlines() if len(l.split())==2}
        if any(observed.get(v['remote'])!=v['sha256'] for v in rows.values()):raise ValueError('当前固件文件与已准备组件不同；未应用设置')
        return dict(ready=True,reused=True,output=str(CACHE),device_written=False)
    (ROOT/'tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='owner-input-',dir=ROOT/'tmp') as temporary:
        directory=Path(temporary)
        for name,row in rows.items():
            result=device('exec-out','cat',row['remote'],raw=True);f=directory/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(result.stdout)
        return prepare_directory(directory)
