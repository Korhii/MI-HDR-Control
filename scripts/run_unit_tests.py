"""Development regression entry. Owner-local model inputs are required; no device I/O."""
from pathlib import Path
import os,subprocess,sys,unittest
from unittest.mock import patch

def main():
    root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(root/'tests'),str(root/'lab'),str(root/'scripts'),str(root/'tools/predict-libs')]
    os.environ['MI_CONTROL_NO_AUTOCONNECT']='1'
    from local_asset_paths import CACHE,status
    if not status()['ready']:
        if not os.environ.get('MI_OWNER_INPUTS'):
            print('Full model regression requires locally prepared components. Connect your supported display first, or set MI_OWNER_INPUTS to your own verified input directory.',file=sys.stderr)
            sys.exit(2)
        from prepare_local_assets import prepare_directory
        prepare_directory(Path(os.environ['MI_OWNER_INPUTS']),CACHE)
    
    suite=unittest.TestSuite()
    for f in sorted((root/'tests').glob('test_*.py')):
        if f.name in ('test_gpu.py','test_public_release.py','test_documentation.py'):continue
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(f.stem))
    real_run=subprocess.run
    def no_unmocked_adb(command,*args,**kwargs):
        if isinstance(command,(list,tuple)) and Path(str(command[0])).name.lower()=='adb.exe':
            raise AssertionError('Unit test attempted an unmocked ADB command')
        return real_run(command,*args,**kwargs)
    with patch.object(subprocess,'run',no_unmocked_adb):
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
