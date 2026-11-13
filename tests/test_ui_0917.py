"""Focused regressions for presentation and fitting policy; never contacts a device."""
from pathlib import Path
import ast,copy,json,sys,unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
from portable_server import PortableBridge

class Presentation0917Tests(unittest.TestCase):
    def test_halo_pause_preserves_budget_and_connection_even_when_offline(self):
        b=PortableBridge.__new__(PortableBridge)
        b.clear_comparison()
        b.shutdown_started=False;b.model_confirmed=True;b.model_id='32u-2026'
        b.state={'connected':False};b.live_debug=True;b.halo_realtime=True;b.budget_active=True
        b.active={'mode':'live'};b.operation_results={};b.last_operation=None;b.wanted_sequence=2;b.ack_sequence=1;b.risk_unlocked=False
        b.device=Mock();b.finish=Mock();b.event=Mock()
        b.perform('halo-stop',{'_field':'halo'})
        self.assertFalse(b.halo_realtime);self.assertTrue(b.live_debug);self.assertTrue(b.budget_active)
        self.assertFalse(b.state['connected']);b.device.assert_not_called();b.finish.assert_not_called()
        self.assertEqual(b.operation_results['halo']['status'],'applied')
        self.assertIn('本次未写设备',b.operation_results['halo']['message'])

    def test_restart_existing_halo_does_not_restart_or_stop_budget(self):
        b=PortableBridge.__new__(PortableBridge)
        b.preflight=Mock();b.state={'connected':True,'native':{'g_video__vid_hdr_tone_mapping_mode':'5','g_video__vid_local_dimming':'3'}};b.tone=5;b.backlight_level=3
        b.active={'mode':'live'};b.draft={'alpha':[16]*8};b.budget_active=True;b.request_live=Mock();b.run=Mock();b.persistence={}
        b._perform('apply-profile',{})
        self.assertTrue(b.halo_realtime);self.assertTrue(b.budget_active)
        b.request_live.assert_called_once_with(b.draft);b.run.assert_not_called()

    def test_selecting_other_level_never_reuses_old_level_worker(self):
        b=PortableBridge.__new__(PortableBridge)
        b.preflight=Mock();b.state={'connected':True,'native':{'g_video__vid_hdr_tone_mapping_mode':'5','g_video__vid_local_dimming':'3'}}
        b.tone=5;b.backlight_level=2;b.active={'mode':'live'};b.draft={'alpha':[16]*8};b.persistence={};b.request_live=Mock();b.run=Mock()
        b._perform('apply-profile',{})
        b.request_live.assert_not_called();b.run.assert_called_once_with('live',b.draft,0,False)

    def test_removed_legacy_switch_cannot_silently_change_device(self):
        b=PortableBridge.__new__(PortableBridge);b.device=Mock()
        with self.assertRaisesRegex(ValueError,'已移除'):b._perform('abl',{'enabled':False})
        b.device.assert_not_called()

class AlphaPreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse((ROOT/'lab/ldf_response.py').read_text(encoding='utf-8-sig'))
        names={'alpha_policy','preferred_config','alpha_penalty'}
        cls.ns={'json':json,'AUTO':[0,.001,.01,.1,.5,1,2,5,10,25,50,75,100],'config_key':lambda c:json.dumps(c,sort_keys=True)}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'production-alpha-policy','exec'),cls.ns)

    def test_normal_target_prefers_high_bins_and_noninverted_low_bins(self):
        n=self.ns;targets=[0]+[1000]*12;p=n['alpha_policy'](targets,targets)
        c={'alpha':[12,2,4,6,8,10,12,14]};original=copy.deepcopy(c)
        self.assertFalse(p['valley']);self.assertFalse(p['large_window_dim'])
        self.assertEqual(n['preferred_config'](c,p)['alpha'][1],12);self.assertEqual(c,original)
        self.assertLess(n['alpha_penalty']({'alpha':[16]*8},p),n['alpha_penalty'](c,p))
        self.assertGreater(p['high_weight'],.1)

    def test_pronounced_valley_allows_alpha1_below_alpha0(self):
        n=self.ns;t=[0,100,300,1000,100,100,200,500,1200,1300,1000,900,750]
        p=n['alpha_policy'](t,[0]+[1000]*12);self.assertTrue(p['valley'])
        self.assertEqual(n['preferred_config']({'alpha':[12,2,16,16,16,16,16,16]},p)['alpha'][1],2)

    def test_extreme_large_window_dim_target_relaxes_high_bin_prior(self):
        n=self.ns;p=n['alpha_policy']([0]+[10]*12,[0]+[1000]*12)
        self.assertTrue(p['large_window_dim']);self.assertLess(p['high_weight'],.01)

if __name__=='__main__':unittest.main()
