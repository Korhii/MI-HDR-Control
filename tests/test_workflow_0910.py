"""One-shot commits, mutually exclusive modes and reset scopes; no device I/O."""
from pathlib import Path
import copy,json,sys,time,unittest
from unittest.mock import Mock,patch,call
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app
from auto_fit import validate_plan
import test_profile_workflow as profile_fixture

from _fixtures import confirmed

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture=profile_fixture.ProfileWorkflowTests();self.fixture.setUp();self.b=self.fixture.b
    def tearDown(self):self.fixture.tearDown()
    def plan(self):
        b=self.b
        return dict(mode='global',ceiling=30,budget=30,recipe='path-a8-sf128')
    def test_uniform_commit_preserves_oem_abl_and_manual_halo(self):
        b=self.b;b.live_debug=True
        config={**app.lab.STOCK_BY_LEVEL[3],'sf':[128,255,255,255,255]}
        with patch.object(app.model_worker,'call',return_value=(self.plan(),config)):
            b.perform('auto-apply',self.plan())
        b.active={'mode':'live'};b.runtime_loaded=True;b.budget_active=True;b.persistence={};b.native_abl['enabled']=True
        b.preflight=Mock();b.request_live=Mock();b.telemetry={'budget_used':28,'raw':21000};b.read_budget=Mock(return_value=b.telemetry)
        c=copy.deepcopy(b.draft);c['sf'][0]=77;b.perform('quick-halo',{'config':c});b.perform('quick-budget',{'budget':28})
        self.assertTrue(b.native_abl['enabled']);self.assertEqual(b.draft['sf'][0],77);self.assertEqual(b.budget_value,28)
        b.activate_tuning.assert_called_once();self.assertNotIn('3:5',b.auto_plans)
        b.read_budget.reset_mock();b.native_poll_at=b.adb_read_at=b.beat=time.monotonic();b.budget_sample_at=0
        for _ in range(3):b.tick_budget()
        self.assertEqual(b.read_budget.call_args_list,[call(running=True)]*3)
        self.assertEqual(b.draft['sf'][0],77);b.activate_tuning.assert_called_once()
    def test_auto_fit_rejects_abl_enabled(self):
        b=self.b;b.native_abl['enabled']=True;b.live_debug=True
        with self.assertRaisesRegex(ValueError,'不支持'):b.perform('auto-apply',self.plan())
        b.activate_tuning.assert_not_called()

    def test_current_profile_reset_leaves_other_eleven_unchanged(self):
        b=self.b;b.select_profile_data(2,1);b.budget_value=35;b.factory_budget=False;b.native_abl['enabled']=True
        c=copy.deepcopy(b.draft);c['sf'][0]=22;b.save_draft(c)
        others={k:copy.deepcopy(v) for k,v in b.profile_bank.items() if k!='2:1'}
        b.perform('profile-defaults',{'confirmed':True,'_profile':'2:1'})
        self.assertEqual(b.profile_bank['2:1'],app.device_profile(2));self.assertEqual(others,{k:v for k,v in b.profile_bank.items() if k!='2:1'})
        b.activate_tuning.assert_called_once()
    def test_software_reset_does_not_touch_live_or_permanent_state(self):
        b=self.b;b.active={'mode':'live'};b.budget_active=True;b.request_live=Mock();b.read_budget=Mock()
        before=(copy.deepcopy(b.draft),b.budget_value,copy.deepcopy(b.native_abl),copy.deepcopy(b.pattern_config),b.wanted_sequence)
        with patch.object(app.permanent,'disable_tuning') as permanent:
            b.perform('software-defaults',{'confirmed':True})
            permanent.assert_not_called()
        for k,p in b.profile_bank.items():self.assertEqual(p,app.device_profile(int(k.split(':')[0])))
        self.assertEqual(before,(b.draft,b.budget_value,b.native_abl,b.pattern_config,b.wanted_sequence))
        b.activate_tuning.assert_not_called();b.request_live.assert_not_called();b.read_budget.assert_not_called()
    def test_reset_confirmation_and_stale_profile_are_required(self):
        for op in ('profile-defaults','software-defaults'):
            with self.assertRaisesRegex(ValueError,'确认'):self.b.perform(op,{})
        with self.assertRaisesRegex(ValueError,'旧窗口'):self.b.perform('profile-defaults',{'confirmed':True,'_profile':'1:0'})

    def test_arbitrary_manual_sf_can_merge_measured_metric(self):
        from firmware_model import response,stock
        c=copy.deepcopy(stock(3));c['sf'][0]=77;c['alpha']=[16]*8
        r=response(c,3,4000,areas=[.01])
        self.assertEqual(len(r['raw'][0]),87);self.assertIn('driver_window_percent',r['metrics'][0])
