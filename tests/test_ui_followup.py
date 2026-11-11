"""Current PC-only export/autosave and isolated model-worker checks. No ADB calls."""
from pathlib import Path
import io,json,sys,tempfile,threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'lab'),str(ROOT/'scripts'),str(ROOT/'tools/predict-libs')]

class PcConfigurationTests(unittest.TestCase):
    def test_export_returns_snapshot_without_writing_a_fixed_folder(self):
        import portable_server as app
        config={'label':'中文配置','profiles':{}}
        b=SimpleNamespace(token='fixture',config_lock=threading.RLock(),export_config=Mock(return_value=config))
        h=app.Handler.__new__(app.Handler);h.path='/api/config-export';h.headers={'Origin':app.lab.URL,'X-MI-Token':'fixture','Content-Length':'0'};h.rfile=io.BytesIO(b'');h.server=SimpleNamespace(bridge=b);h.reply=Mock()
        with tempfile.TemporaryDirectory() as temp,patch.object(app,'ROOT',Path(temp)):
            h.do_POST();self.assertFalse((Path(temp)/'profiles').exists())
        reply=h.reply.call_args.args[0];self.assertEqual(reply['config'],config);self.assertTrue(reply['filename'].endswith('.json'));self.assertNotIn('path',reply)

    def test_preferences_and_auto_preview_save_without_a_manual_button(self):
        import test_profile_workflow as fixture
        f=fixture.ProfileWorkflowTests();f.setUp()
        try:
            b=f.b;b.state['connected']=False
            b.perform('preferences',{'config':{**b.ui_preferences,'theme':'dark'}})
            saved=json.loads((f.root/'profiles/controller.json').read_text('utf-8'));self.assertEqual(saved['ui']['theme'],'dark')
            b.perform('auto-preview',{'preview':dict(mode='global',ceiling=30,targets=[[0]*13]*2)})
            saved=json.loads((f.root/'profiles/controller.json').read_text('utf-8'));self.assertEqual(saved['auto_previews']['3:5']['ceiling'],30)
        finally:f.tearDown()

class ParallelResponseTests(unittest.TestCase):
    def test_worker_count_is_bounded_by_available_cpus(self):
        import ldf_response as l
        for count,expected in ((1,1),(2,1),(8,7),(32,16)):
            with patch.object(l.os,'process_cpu_count',return_value=count):self.assertEqual(l.surface_workers(),expected)

    def test_parallel_matches_serial_across_models_levels_and_tones(self):
        import firmware_model as f,ldf_response as l,device_models,abl_predict
        def activate(model,tone):
            device_models.activate(model,tone)
            for fn in (f.predict_cached,f.illumination_cached,l.ldf,l.blocks,l.anchor_corrections,l.correction,l.spill_offsets,l.stock_drive,abl_predict.peaks):fn.cache_clear()
        try:
            for model,tone,level,q in (('27u-2026',5,1,1000),('32u-2026',1,2,4000),('32u-2026',0,3,1000),('27u-2026',2,3,4000)):
                with self.subTest(model=model,tone=tone,level=level,q=q):
                    activate(model,tone);c=f.stock(level);c['alpha'][2:]=[16]*6
                    with patch.object(l,'ALPHA',[0,16]),patch.object(l,'save_progress'):
                        serial,calls=l.build_surface(c,level,q,1);parallel,parallel_calls=l.build_surface(c,level,q,2)
                    self.assertEqual(parallel.tobytes(),serial.tobytes());self.assertEqual(parallel_calls,calls)
        finally:activate('32u-2026',5)

if __name__=='__main__':unittest.main(verbosity=2)

