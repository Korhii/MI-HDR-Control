"""Read-only MTK snapshots and file extraction for the connected 32U."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
from portable_paths import activate
activate(ROOT)
ADB = ROOT / 'tools/platform-tools/adb.exe'
for directory in ('tmp','logs','state/android','captures','experiments'):
    (ROOT/directory).mkdir(parents=True,exist_ok=True)
ENV = os.environ.copy()
ENV.update(TEMP=str(ROOT / 'tmp'), TMP=str(ROOT / 'tmp'),
           ANDROID_ADB_LOG_PATH=str(ROOT / 'logs/adb-server.log'),
           ADB_VENDOR_KEYS=str(ROOT / 'state/android/adbkey'))
REMOTE = '/sdcard/Download/MIResearch20261106'
JAR = '/data/data/mitv.service/cache/MIHDRBridge.jar'
KEYS = ['g_video__picture_mode', 'g_dovi_info__', 'g_disp__disp_back_light',
        'g_video__vid_local_dimming', 'g_video__vid_hdr_tone_mapping_mode',
        'g_video__clr_temp', 'g_video__clr_gain_r', 'g_video__clr_gain_g',
        'g_video__clr_gain_b', 'g_video__contrast', 'g_video__brightness']


def connection():
    path=ROOT/'state/connection.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'serial':'','port':5041}


def adb_base():
    c=connection()
    return [str(ADB),'-P',str(c['port'])]+(['-s',c['serial']] if c['serial'] else [])


class ADBConnectionError(RuntimeError):
    pass


def connection_error(message):
    return any(s in message.lower() for s in ('device offline','device not found','no devices/emulators','no device/emulator','cannot connect to','device \'','transport error','connection reset','error: closed'))


def adb(*parts, check=True, raw=False, timeout=12):
    result = subprocess.run([*adb_base(), *parts],
                            capture_output=True, env=ENV, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    output = result.stdout.decode('utf-8', errors='replace')
    if check and result.returncode:
        message=result.stderr.decode('utf-8', errors='replace')
        raise (ADBConnectionError if connection_error(message) else RuntimeError)(message)
    return result if raw else output


def tv_command(parts):
    return 'service call TvService 3 s16 "sh -c eval' + ''.join(r'\${IFS}' + p for p in parts) + '"'


def deploy():
    adb('shell', f'mkdir -p {REMOTE} /sdcard/Download/Mimonitor_Toolbox')
    source = ROOT / 'tools/MIHDRBridge.jar'
    adb('push', str(source), REMOTE + '/helper.jar')
    adb('shell', tv_command(['cp', REMOTE + '/helper.jar', JAR]))


def native(action, output_dir, keys=(), timeout=20):
    # Only getters are exposed by this script. Never clear logcat.
    if action not in ('getBatch', 'getPictureState', 'getInputSignal'):
        raise ValueError(action)
    receipt = '/sdcard/Download/Mimonitor_Toolbox/.mtk_action_' + uuid.uuid4().hex + '.txt'
    command = tv_command(['CLASSPATH=' + JAR, '/system/bin/app_process',
                          '/data/data/mitv.service/cache', 'MIHDRBridge', action, *keys, receipt])
    deadline = time.monotonic() + timeout
    parcel = adb('shell', command,timeout=min(12,timeout))
    while time.monotonic() < deadline:
        result = adb('shell', 'cat ' + receipt, check=False,timeout=min(12,timeout))
        if '__complete=1' in result:
            (output_dir / (action + '.txt')).write_text(result, encoding='utf-8')
            (output_dir / (action + '-command.txt')).write_text(command + '\n' + parcel, encoding='utf-8')
            if 'fatal=' in result:
                raise RuntimeError(result)
            return dict(line.split('=', 1) for line in result.splitlines() if '=' in line)
        time.sleep(0.15)
    raise TimeoutError(action + ': missing receipt; ' + parcel)


def snapshot(label):
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    directory = ROOT / 'captures' / (stamp + '-' + label)
    directory.mkdir()
    results = {'time_hk': datetime.now(timezone(timedelta(hours=8))).isoformat()}
    for action, keys in [('getInputSignal', ()), ('getBatch', KEYS)]:
        results[action] = native(action, directory, keys)
    settings = adb('shell', 'settings list global')
    (directory / 'global_settings.txt').write_text(settings, encoding='utf-8')
    (directory / 'snapshot.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(directory), **results}, indent=2))


def pull(paths, via_service=False):
    destination = ROOT / 'artifacts/device'
    manifest = ROOT / 'artifacts/pull-manifest.jsonl'
    destination.mkdir(parents=True, exist_ok=True)
    for remote in paths:
        if not remote.startswith(('/vendor/', '/system/', '/system_ext/', '/odm/')):
            raise ValueError(remote)
        target = destination / remote.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc).isoformat()
        source = remote
        if via_service:
            stage = REMOTE + '/stage_' + uuid.uuid4().hex
            adb('shell', 'mkdir -p ' + stage)
            source = stage + '/' + Path(remote).name
            script = ROOT / 'tmp' / (Path(stage).name + '.sh')
            script.write_text('cp -R ' + shlex.quote(remote) + ' ' + shlex.quote(source)
                              + ' 2>' + stage + '/error.txt\necho $? >' + stage + '/exit.txt\n', encoding='utf-8', newline='\n')
            adb('push', str(script), stage + '/copy.sh')
            adb('shell', tv_command(['sh', stage + '/copy.sh']))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                status = adb('shell', 'cat ' + stage + '/exit.txt', check=False).strip()
                if status:
                    break
                time.sleep(0.1)
            else:
                raise TimeoutError('Staged copy not completed: ' + remote)
            if status != '0':
                print(adb('shell', 'cat ' + stage + '/error.txt', check=False))
        result = adb('pull', source, str(target), check=False, raw=True)
        success = result.returncode == 0
        output = (result.stdout + result.stderr).decode('utf-8', errors='replace')
        with manifest.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'remote': remote, 'local': str(target), 'utc': started,
                                     'via_service': via_service, 'source': source,
                                     'success': success, 'exit_code': result.returncode, 'output': output}) + '\n')
        print(('OK ' if success else 'FAILED ') + remote)
        if not success:
            print(output.strip())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy', action='store_true')
    parser.add_argument('--snapshot', metavar='LABEL')
    parser.add_argument('--pull', nargs='+', default=[])
    parser.add_argument('--via-service', action='store_true')
    args = parser.parse_args()
    if args.deploy:
        deploy()
    if args.snapshot:
        snapshot(args.snapshot)
    if args.pull:
        pull(args.pull, args.via_service)
