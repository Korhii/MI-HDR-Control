"""Real profile/preview/default logic with device operations mocked. Never opens ADB."""
from pathlib import Path
import copy,json,shutil,sys,tempfile,unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app
from auto_fit import AUTO_KNOTS,validate_plan,validate_preview
from features import PATTERN

from _fixtures import confirmed

class ProfileWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for name in ('state','profiles','experiments','tmp','logs','resources/ui'):(self.root/name).mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'resources/ui/joint-output.json',self.root/'resources/ui/joint-output.json')
        self.patches=[patch.object(app,'ROOT',self.root),patch.object(app.lab,'ROOT',self.root),patch.object(app.lab.Bridge,'tick',return_value=None)]
        for p in self.patches:p.start()
        self.b=confirmed(app.PortableBridge());self.b.state['connected']=True;self.b.state['native']={'g_video__vid_local_dimming':'3','g_video__vid_hdr_tone_mapping_mode':'5'}
        self.b.activate_tuning=Mock();self.b.restore_device_defaults=Mock()
    def tearDown(self):
        self.b.closing=True;self.b.pool.shutdown(wait=True)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def preview(self):return dict(mode='global',ceiling=30,targets=[[0,100,200,300,500,1000,1400,1300,1200]]*2,abl=True,hold_seconds=10,fade_seconds=10)
    def test_25_percent_target_and_legacy_preview_migration(self):
        self.assertEqual(AUTO_KNOTS,[0,.001,.01,.1,.5,1,2,5,10,25,50,75,100])
        migrated=validate_preview(self.preview());self.assertEqual(len(migrated['targets'][0]),13);self.assertEqual(migrated['targets'][0][9],1150)
        current={**self.preview(),'targets':[[0,100,200,300,500,1000,777,1400,1300,1200]]*2}
        self.assertEqual(validate_preview(current)['targets'][0][9],777)
    def test_preview_during_live_does_not_change_parameters_or_write_device(self):
        b=self.b;b.live_debug=True;before=copy.deepcopy(b.profile_bank)
        b.perform('auto-preview',{'preview':self.preview(),'_profile':'3:5'})
        self.assertEqual(b.profile_bank,before);self.assertIn('3:5',b.auto_previews);b.activate_tuning.assert_not_called()
    def test_auto_application_is_explicit_and_safe_sf(self):
        b=self.b;b.live_debug=True
        plan=dict(mode='global',ceiling=30,budget=30,recipe='path-a8-sf128')
        config={**app.lab.STOCK_BY_LEVEL[3],'sf':[128,255,255,255,255]}
        with patch.object(app.model_worker,'call',return_value=(plan,config)) as worker:
            b.perform('auto-apply',{**plan,'_profile':'3:5'})
        self.assertEqual(worker.call_args.args,('validate',))
        self.assertEqual(b.draft['sf'],[128,255,255,255,255]);b.activate_tuning.assert_called_once()
        for name in ('stock-wide','stock-taper'):
            with self.assertRaisesRegex(ValueError,'令牌'):validate_plan({**plan,'recipe':name},3,ROOT/'resources/ui/joint-output.json')
    def test_twelve_profiles_and_pattern_values_stay_independent(self):
        b=self.b
        for level in (1,2,3):
            for tone in (5,1,0,2):
                b.select_profile_data(level,tone);b.budget_value=level*10+tone;b.pattern_config={**PATTERN,'area_percent':level*10+tone};c=copy.deepcopy(b.draft);c['sf'][0]=level*40+tone;b.save_draft(c)
        snapshot=copy.deepcopy(b.profile_bank)
        for level in (1,2,3):
            for tone in (5,1,0,2):
                b.perform('profile-select',dict(level=level,tone=tone));self.assertEqual(b.budget_value,level*10+tone);self.assertEqual(b.pattern_config['area_percent'],level*10+tone);self.assertEqual(b.draft['sf'][0],level*40+tone)
        self.assertEqual(snapshot,b.profile_bank);self.assertEqual(b.activate_tuning.call_count,12);self.assertTrue(b.live_debug)
    def test_stale_detached_window_cannot_write_new_profile(self):
        b=self.b;b.select_profile_data(2,1);old=copy.deepcopy(b.profile_bank)
        with self.assertRaisesRegex(ValueError,'旧窗口'):b.perform('quick-budget',dict(budget=40,_profile='3:5'))
        self.assertEqual(old,b.profile_bank);b.activate_tuning.assert_not_called()
    def test_module_default_applies_only_current_group_current_module(self):
        b=self.b;b.select_profile_data(2,1);b.budget_value=35;b.factory_budget=False;b.native_abl['enabled']=True;c=copy.deepcopy(b.draft);c['sf'][0]=0;b.save_draft(c)
        others={k:copy.deepcopy(v) for k,v in b.profile_bank.items() if k!='2:1'}
        b.perform('module-defaults',dict(module='halo',_profile='2:1'))
        self.assertEqual(b.draft,app.lab.STOCK_BY_LEVEL[2]);self.assertEqual(b.budget_value,35);self.assertTrue(b.native_abl['enabled']);self.assertFalse(b.factory_budget);b.activate_tuning.assert_called_once()
        self.assertEqual(others,{k:v for k,v in b.profile_bank.items() if k!='2:1'})
    def test_budget_default_is_native_path_not_a_fake_24_override(self):
        b=self.b;b.perform('module-defaults',dict(module='budget'));self.assertTrue(b.factory_budget);self.assertFalse(b.native_abl['enabled']);b.activate_tuning.assert_called_once()
    def test_global_default_disables_only_tuning_and_resets_all_twelve(self):
        b=self.b
        for value in b.profile_bank.values():value['budget']=40;value['config']['sf'][0]=0;value['factory_budget']=False
        receipt=dict(native=dict(g_video__vid_local_dimming='3',g_video__vid_hdr_tone_mapping_mode='5'),config=app.lab.STOCK_BY_LEVEL[3],backup_id='fixture')
        with patch.object(app.permanent,'disable_tuning',return_value={'owned':True,'enabled':False}) as disable,patch.object(app.permanent,'remove') as remove,patch.object(b,'device',return_value=''),patch.object(app.device_backup,'restore',return_value=receipt) as restore:
            b.perform('all-defaults',dict(confirmed=True))
        disable.assert_called_once();remove.assert_not_called();restore.assert_called_once();self.assertEqual(restore.call_args.args[0],b.initial_backup)
        for key,p in b.profile_bank.items():self.assertEqual(p['config'],app.lab.STOCK_BY_LEVEL[int(key[0])]);self.assertTrue(p['factory_budget']);self.assertTrue(p['software_abl']);self.assertFalse(p['native_abl']['enabled'])
    def test_global_default_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError,'明确确认'):self.b.perform('all-defaults',{})
        self.b.restore_device_defaults.assert_not_called()
    def test_live_global_aw_has_a_numeric_windowed_estimate_and_footer(self):
        b=self.b;b.state['pattern']=True;b.pattern_config={**PATTERN,'mode':'windowed','input_nits':10000};b.pattern_check={'actual_area_percent':.01};b.telemetry=dict(raw=65535,status='live-driver',level=3)
        value=b.current_brightness();self.assertAlmostEqual(value['nits'],35.0,places=1);self.assertIn('AW不冒充分区输出',value['note']);self.assertIn('窗口化',value['note'])
        b.pattern_dir=self.root/'pattern';b.pattern_dir.mkdir();b.pattern_label()
        self.assertIn('35 nit', (b.pattern_dir/'status.txt').read_text(encoding='utf-8'))
    def test_profile_export_import_preserves_preview_and_native_path(self):
        b=self.b;b.perform('auto-preview',{'preview':self.preview()});data=b.export_config();b.import_config(data)
        self.assertEqual(b.auto_previews['3:5']['ceiling'],30);self.assertEqual(len(b.profile_bank),12);self.assertTrue(b.factory_budget)
    def test_stale_pattern_receipt_does_not_override_new_window_mode(self):
        b=self.b;b.pattern_dir=self.root/'pattern';b.pattern_dir.mkdir();b.pattern_sequence=4;b.pattern_config={**PATTERN,'mode':'windowed'}
        check=b.pattern_dir/'check.json';check.write_text(json.dumps(dict(sequence=3,windowed_preview=False)),encoding='utf-8');b.pattern_label()
        self.assertEqual(b.pattern_config['mode'],'windowed')
        check.write_text(json.dumps(dict(sequence=4,windowed_preview=False)),encoding='utf-8');b.pattern_label()
        self.assertEqual(b.pattern_config['mode'],'fullscreen')
