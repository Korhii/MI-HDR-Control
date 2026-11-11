"""Process-local portable paths; never changes the user's system environment."""
from pathlib import Path
import os,socket

def activate(root=None):
    root=Path(root or Path(__file__).resolve().parents[1]).resolve()
    paths={'TEMP':root/'tmp','TMP':root/'tmp','TMPDIR':root/'tmp',
           'LOCALAPPDATA':root/'state/local','APPDATA':root/'state/roaming',
           'USERPROFILE':root/'state/home','HOME':root/'state/home',
           'ANDROID_USER_HOME':root/'state/android','ADB_VENDOR_KEYS':root/'state/android/adbkey'}
    for name,path in paths.items():
        (path.parent if name=='ADB_VENDOR_KEYS' else path).mkdir(parents=True,exist_ok=True)
        os.environ[name]=str(path)
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    return paths

def available_adb_port(preferred):
    # Never attach this app to another tool's server/log/key locations.
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',preferred))
        except OSError:probe.bind(('127.0.0.1',0))
        return probe.getsockname()[1]
