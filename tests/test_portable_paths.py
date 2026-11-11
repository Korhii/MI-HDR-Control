"""Portable root follows the program after a move, independent of the launch cwd."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]

class PortablePaths(unittest.TestCase):
 def test_moved_package_ignores_working_directory(self):
  temp=ROOT/'tmp';temp.mkdir(exist_ok=True)
  with tempfile.TemporaryDirectory(dir=temp,prefix='portable-path-') as directory:
   outer=Path(directory);old=outer/'before';new=outer/'移动后 portable'
   (old/'scripts').mkdir(parents=True)
   shutil.copyfile(ROOT/'scripts/portable_paths.py',old/'scripts/portable_paths.py')
   old.rename(new)
   code="import sys,json;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/'scripts'));from portable_paths import activate;print(json.dumps({k:str(v) for k,v in activate().items()}))"
   env_before=dict(os.environ)
   q=subprocess.run([sys.executable,'-c',code,str(new)],cwd=outer,capture_output=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1'})
   self.assertEqual(q.returncode,0,q.stderr.decode(errors='replace'))
   paths=json.loads(q.stdout.decode('utf-8'))
   self.assertTrue(all(Path(v).is_relative_to(new) for v in paths.values()))
   self.assertEqual(Path(paths['TEMP']),new/'tmp')
   self.assertEqual(Path(paths['LOCALAPPDATA']),new/'state/local')
   self.assertEqual(Path(paths['ADB_VENDOR_KEYS']),new/'state/android/adbkey')
   self.assertEqual(dict(os.environ),env_before)

if __name__=='__main__':unittest.main(verbosity=2)
