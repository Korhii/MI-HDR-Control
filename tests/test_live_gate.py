"""Session gates and truthful result states; all device operations are mocked."""
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import Mock
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app
from native_abl import DEFAULT as ABL_DEFAULT,validate as validate_abl

from _fixtures import confirmed

class LiveGateTests(TestCase):
    def bridge(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        b.factory_budget=False;b.auto_plans={};b.auto_previews={};b.shutdown_started=False;b.live_debug=False;b.risk_unlocked=False
        b.needs_restore=False;b.debug_phase='idle';b.default_restoration=None;b.disconnect_adb=Mock();b.restore_device_defaults=Mock()
        b.operation_results={};b.last_operation=None;b.wanted_sequence=b.ack_sequence=0
        b.active=None;b.state={'connected':True};b.runtime_loaded=False
        b.backlight_level=3;b.tone=5;b.budget_value=24
        b.profile_bank={'3:5':dict(budget=24,native_abl=validate_abl(ABL_DEFAULT))}
        b._perform=Mock();b.save_configuration=Mock();b.finish=Mock()
        return b

    def test_off_means_draft_even_with_connected_adb(self):
        b=self.bridge();b.perform('quick-budget',{'budget':30,'_field':'uniform'})
        self.assertEqual(b._perform.call_args.args[0],'runtime-draft')
        self.assertEqual(b.operation_results['uniform']['status'],'draft')
        b.perform('quick-halo',{'config':{},'_field':'alpha-0'})
        self.assertEqual(b._perform.call_args.args[0],'draft')

    def test_risky_value_blocked_before_any_apply(self):
        b=self.bridge()
        with self.assertRaisesRegex(ValueError,'41/86'):b.perform('quick-budget',{'budget':42,'_field':'uniform'})
        b._perform.assert_not_called()
        self.assertEqual(b.operation_results['uniform']['status'],'error')

    def test_ordinary_unlock_is_session_only(self):
        b=self.bridge();b.perform('risk-unlock',{'acknowledged':True})
        self.assertTrue(b.risk_unlocked)
        b.perform('quick-budget',{'budget':42,'_field':'uniform'})
        self.assertEqual(b._perform.call_args.args[0],'runtime-draft')
        self.assertFalse(self.bridge().risk_unlocked)

    def test_permanent_requires_fresh_separate_consent_even_after_unlock(self):
        b=self.bridge();b.risk_unlocked=True;b.profile_bank['3:5']['budget']=42
        with self.assertRaisesRegex(ValueError,'关闭PC不会自动回原厂'):b.perform('permanent-write',{})
        b._perform.assert_not_called()
        b.perform('permanent-write',{'permanent_risk_ack':True})
        self.assertEqual(b._perform.call_args.args[0],'permanent-write')
        with self.assertRaises(ValueError):b.perform('permanent-write',{})

    def test_off_is_never_blocked_by_dangerous_current_profile(self):
        b=self.bridge();b.live_debug=True;b.needs_restore=True;b.profile_bank['3:5']['budget']=86
        b.perform('live-debug',{'enabled':False})
        self.assertFalse(b.live_debug);b.restore_device_defaults.assert_called_once();b.disconnect_adb.assert_called_once()

    def test_high_budget_requires_separate_permanent_consent(self):
        b=self.bridge();b.profile_bank['3:5']['budget']=58
        with self.assertRaises(ValueError):b.check_risk('permanent-write',{})
        b.check_risk('permanent-write',{'permanent_risk_ack':True})


    def test_activation_uses_existing_verified_paths_in_order(self):
        b=self.bridge();b.activate_tuning()
        self.assertEqual([c.args[0] for c in b._perform.call_args_list],['runtime-load','apply-profile','runtime-set'])

    def test_multiple_fields_share_pending_device_ack_not_false_success(self):
        b=self.bridge();b.live_debug=True;b.active={'mode':'live'};b.wanted_sequence=7;b.ack_sequence=6
        b.perform('quick-halo',{'config':{},'_field':'halo','_fields':['sf-0','alpha-2']})
        for field in ('halo','sf-0','alpha-2'):
            self.assertEqual(b.operation_results[field]['status'],'waiting-ack')
            self.assertEqual(b.operation_results[field]['sequence'],7)

    def test_profile_switch_cannot_bypass_high_value_gate(self):
        b=self.bridge();b.profile_bank['2:1']=dict(budget=58,native_abl=validate_abl(ABL_DEFAULT))
        with self.assertRaises(ValueError):b.perform('profile-select',{'level':2,'tone':1})
        b._perform.assert_not_called()

if __name__=='__main__':main()
