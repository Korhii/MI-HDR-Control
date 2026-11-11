"""Install/remove the on-monitor ADB boot receiver; never changes USB roles or authentication."""
import argparse,difflib,hashlib,json,sys,time,uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mi_probe import ROOT,REMOTE,adb,tv_command

PACKAGE='local.mi.adbkeepalive'
STATUS=('echo __package; pm path '+PACKAGE+'; echo __permission; dumpsys package '+PACKAGE
        +' | grep WRITE_SECURE_SETTINGS; echo __state; '
        +'echo adb_enabled=$(settings get global adb_enabled); '
        +'echo daemon=$(getprop init.svc.adbd); '
        +'echo tcp_port=$(getprop persist.adb.tcp.port); '
        +'echo usb_persistent=$(getprop persist.sys.usb.config); '
        +'echo auth=$(getprop ro.adb.secure); '
        +'echo boot_count=$(settings get global boot_count); '
        +'echo __receipts; logcat -d -s MIADBKeepalive:I "*:S"')

def perform(action,folder=None):
    folder=Path(folder) if folder else ROOT/'captures'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-adb-autostart')
    folder.mkdir(parents=True,exist_ok=True);records=[]
    def run(*args):
        p=adb(*args,check=False,raw=True)
        row=dict(command=args,stdout=p.stdout.decode('utf-8',errors='replace'),stderr=p.stderr.decode('utf-8',errors='replace'),exit_status=p.returncode)
        records.append(row)
        (folder/'execution.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        if p.returncode:raise RuntimeError(row)
        return row['stdout']
    before=run('shell',STATUS)
    (folder/'before.txt').write_text(before,encoding='utf-8')
    def policy(mode):
        remote=REMOTE+'/adb_autostart_'+uuid.uuid4().hex
        run('shell','mkdir -p '+remote)
        config='/data/system/mitv_security_center.xml'
        def script_run(text,label):
            script=folder/('policy-'+label+'.sh')
            script.write_text('( set -eu\n'+text+'\necho __policy_done=1\n) >'+remote+'/receipt.txt 2>&1\n',encoding='utf-8',newline='\n')
            run('push',str(script),remote+'/run.sh');run('shell','rm -f '+remote+'/receipt.txt')
            run('shell',tv_command(['sh',remote+'/run.sh']))
            deadline=time.monotonic()+5;receipt=''
            while time.monotonic()<deadline:
                receipt=run('shell','cat '+remote+'/receipt.txt')
                if '__policy_done=1' in receipt:break
                time.sleep(.1)
            (folder/('policy-'+label+'.txt')).write_text(receipt,encoding='utf-8')
            if '__policy_done=1' not in receipt:raise RuntimeError(receipt)
        script_run('cp '+config+' '+remote+'/before.xml','read')
        local=folder/'policy-before.xml';run('pull',remote+'/before.xml',str(local));raw=local.read_bytes()
        tree=ET.fromstring(raw);feature=tree.findall("./app_name[@name='system']/feature[@name='boot_autostart']")
        if len(feature)!=1:raise ValueError('Unsupported stock boot-autostart policy')
        entries=feature[0].findall("./package[@name='"+PACKAGE+"']")
        if len(entries)>1:raise ValueError('Duplicate companion self-start entries')
        enabled=bool(entries and entries[0].get('white_list')=='true')
        if mode is None:return enabled
        opening=b'<feature name="boot_autostart">';begin=raw.index(opening)+len(opening);end=raw.index(b'</feature>',begin)
        line=b'\n      <package name="local.mi.adbkeepalive" white_list="true"/>'
        if mode and not entries:changed=raw[:begin]+line+raw[begin:]
        elif not mode and entries and line in raw[begin:end]:changed=raw[:begin]+raw[begin:end].replace(line,b'',1)+raw[end:]
        elif enabled==mode:return enabled
        else:raise ValueError('Companion entry was independently modified; inspect before replacing')
        ET.fromstring(changed)
        path=folder/'policy-modified.xml';path.write_bytes(changed)
        (folder/'policy.diff').write_text(''.join(difflib.unified_diff(raw.decode('utf-8').splitlines(True),changed.decode('utf-8').splitlines(True),fromfile=config,tofile=config)),encoding='utf-8')
        run('push',str(path),remote+'/modified.xml')
        baseline=hashlib.sha256(raw).hexdigest();modified=hashlib.sha256(changed).hexdigest()
        backup='/data/data/mitv.service/files/MIADBKeepalive'
        script_run('[ "$(sha256sum '+config+' | cut -d " " -f1)" = '+baseline+' ]\n'
            +'mkdir -p '+backup+'\nchmod 700 '+backup+'\n'
            +'if [ ! -f '+backup+'/security-center-baseline.xml ]; then cp '+config+' '+backup+'/security-center-baseline.xml; fi\n'
            +'cp '+remote+'/modified.xml '+config+'\n'
            +'[ "$(sha256sum '+config+' | cut -d " " -f1)" = '+modified+' ]\n'
            +'cp '+config+' '+remote+'/after.xml\nls -lZ '+config,'write')
        run('pull',remote+'/after.xml',str(folder/'policy-after.xml'))
        assert (folder/'policy-after.xml').read_bytes()==changed
        return mode
    if action=='install':
        run('install','-r',str(ROOT/'tools/mi-adb-keepalive.apk'))
        run('shell','pm grant '+PACKAGE+' android.permission.WRITE_SECURE_SETTINGS')
        allowed=policy(True)
        run('shell','am start -W -n '+PACKAGE+'/.MainActivity --ez enable true')
        time.sleep(1)
    elif action=='remove':
        allowed=policy(False)
        if 'package:' in run('shell','pm path '+PACKAGE):
            run('uninstall',PACKAGE)
    elif action!='status':raise ValueError(action)
    if action=='status':allowed=policy(None)
    after=run('shell',STATUS)
    after+='\npolicy_boot_autostart='+str(allowed).lower()+'\n'
    (folder/'after.txt').write_text(after,encoding='utf-8')
    if action=='install':
        assert 'WRITE_SECURE_SETTINGS: granted=true' in after,after
        receipt=[line for line in after.splitlines() if 'MIADBKeepalive:' in line][-1:]
        assert receipt and receipt[0] not in before and 'after=1 write_ok=true' in receipt[0],after
        assert 'daemon=running' in after,after
    if action=='remove':assert 'package:' not in after.split('__permission')[0],after
    return after,folder

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['install','remove','status'])
    args=parser.parse_args();output,folder=perform(args.action);print(output);print('Evidence:',folder)
