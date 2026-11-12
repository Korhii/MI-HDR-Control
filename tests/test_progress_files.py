"""Windows progress-file contention must not fail a model computation."""
import ast,json,os
from pathlib import Path
import tempfile,threading,time,unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('MI_TEST_ROOT',Path(__file__).resolve().parents[1]))

def writer(root):
    source=(ROOT/'lab/ldf_response.py').read_text('utf8')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='save_progress')
    ns=dict(ROOT=root,json=json,time=time)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'save_progress','exec'),ns)
    return ns['save_progress']

def reader(root):
    source=(ROOT/'lab/model_worker.py').read_text('utf8')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='progress')
    ns=dict(ROOT=root,json=json)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'progress','exec'),ns)
    return ns['progress']

class ProgressTests(unittest.TestCase):
    def test_brief_destination_lock_is_retried(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save=writer(root);original=Path.replace;attempts=[]
            def replace(path,target):
                attempts.append(1)
                if len(attempts)<3:raise PermissionError('fixture: reader holds destination')
                return original(path,target)
            with patch.object(Path,'replace',replace):save({'done':9})
            self.assertEqual(len(attempts),3)
            self.assertEqual(json.loads((root/'state/model-progress.json').read_text()),{'done':9})

    def test_busy_progress_display_does_not_abort_the_calculation(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Path,'replace',side_effect=PermissionError('fixture: busy')):
            writer(Path(d))({'done':9})

    def test_other_io_errors_are_not_hidden(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Path,'replace',side_effect=OSError('fixture: disk I/O')):
            with self.assertRaisesRegex(OSError,'disk I/O'):writer(Path(d))({'done':9})

    def test_real_updates_remain_parseable_during_polling(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save=writer(root);read=reader(root);save({'done':0});stop=threading.Event();errors=[]
            def poll():
                while not stop.is_set():
                    try:
                        value=read()
                        assert value is None or isinstance(value['done'],int)
                    except Exception as e:errors.append(repr(e))
            thread=threading.Thread(target=poll);thread.start()
            try:
                for n in range(100):save({'done':n})
            finally:stop.set();thread.join()
            self.assertEqual(errors,[])

if __name__=='__main__':unittest.main(verbosity=2)
