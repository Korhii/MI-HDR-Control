"""Switch ordering and scoped defaults. Real display operations are never used here."""
from pathlib import Path
import copy,json,sys,tempfile
from unittest import TestCase
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app
from features import PATTERN
from native_abl import DEFAULT as ABL_DEFAULT,validate as validate_abl

from _fixtures import confirmed

class SwitchDefaultsTests(TestCase):
    def bridge(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        b.factory_budget=False;b.auto_previews={};b.pattern_config=dict(PATTERN);b.pattern=None;b.pattern_dir=None;b.pattern_sequence=0;b.shutdown_started=False;b.live_debug=False;b.risk_unlocked=False;b.needs_restore=False;b.debug_phase='idle';b.default_restoration=None
        b.adb_owned=False;b.adb_port=None;b.backlight_level=3;b.tone=5;b.active=None;b.budget_active=False;b.runtime_loaded=False
        b.state={'connected':False,'pattern':False};b.operation_results={};b.last_operation=None;b.wanted_sequence=b.ack_sequence=0
        b.profile_bank={'3:5':dict(budget=41,native_abl=validate_abl(ABL_DEFAULT))};b.auto_plans={};b.budget_value=41;b.software_abl=False
        b.native_abl=validate_abl({**ABL_DEFAULT,'enabled':True,'e0':7});b.draft=copy.deepcopy(app.lab.STOCK);b.draft['sf'][0]=128
        b.save_configuration=Mock();b.prepare_adb=Mock();b._perform=Mock();b.activate_tuning=Mock();b.finish=Mock();b.disconnect_adb=Mock();b.restore_device_defaults=Mock()
        b.save_draft=Mock(side_effect=lambda c:setattr(b,'draft',copy.deepcopy(c)))
        return b
    def test_on_connects_then_applies_off_restores_then_disconnects(self):
        b=self.bridge();calls=[]
        b.prepare_adb.side_effect=lambda c=None:calls.append('connect-server')
        b._perform.side_effect=lambda op,data:calls.append(op)
        b.activate_tuning.side_effect=lambda:calls.append('apply')
        b.restore_device_defaults.side_effect=lambda:calls.append('restore-defaults')
        b.disconnect_adb.side_effect=lambda:calls.append('disconnect')
        b.state['connected']=True
        b.perform('live-debug',{'enabled':True});self.assertTrue(b.live_debug)
        b.perform('live-debug',{'enabled':False});self.assertFalse(b.live_debug)
        self.assertEqual(calls,['connect-server','auto-connect','apply','restore-defaults','disconnect'])
        self.assertEqual(b.budget_value,41) # Device defaults do not erase the PC draft.
    def test_restore_failure_does_not_claim_disconnect(self):
        b=self.bridge();b.needs_restore=True;b.state['connected']=True
        b.restore_device_defaults.side_effect=RuntimeError('no restore receipt')
        with self.assertRaises(RuntimeError):b.stop_debug()
        b.disconnect_adb.assert_not_called();self.assertEqual(b.debug_phase,'restore-error');self.assertTrue(b.needs_restore)
    def test_connection_failure_never_starts_parameter_writes(self):
        b=self.bridge();b._perform.side_effect=RuntimeError('offline')
        with self.assertRaises(RuntimeError):b.perform('live-debug',{'enabled':True})
        b.activate_tuning.assert_not_called();b.disconnect_adb.assert_called_once();self.assertFalse(b.live_debug)
    def test_permanent_handoff_does_not_undo_the_saved_scheme(self):
        b=self.bridge();b.live_debug=True;b.needs_restore=True;b.state['connected']=True
        b.perform('permanent-write',{})
        b._perform.assert_called_once_with('permanent-write',{})
        b.restore_device_defaults.assert_not_called();b.disconnect_adb.assert_called_once()
        self.assertFalse(b.needs_restore);self.assertFalse(b.live_debug)
    def test_halo_defaults_preserve_budget_and_curve(self):
        b=self.bridge();curve=copy.deepcopy(b.native_abl);b.module_defaults('halo')
        self.assertEqual(b.draft,app.lab.STOCK);self.assertEqual(b.budget_value,41);self.assertEqual(b.native_abl,curve)
        b.activate_tuning.assert_not_called()
    def test_budget_defaults_stop_experimental_abl_without_changing_halo(self):
        b=self.bridge();before=copy.deepcopy(b.draft);b.module_defaults('budget')
        self.assertEqual(b.draft,before);self.assertEqual(b.native_abl,validate_abl(ABL_DEFAULT));self.assertTrue(b.factory_budget)

    def test_deleted_module_default_rejected(self):
        with self.assertRaises(ValueError):self.bridge().module_defaults('curve')

    def test_auto_defaults_reset_its_shared_hdr_controls_only(self):
        b=self.bridge();b.module_defaults('auto');self.assertEqual(b.draft,app.lab.STOCK);self.assertEqual(b.budget_value,24);self.assertFalse(b.native_abl['enabled']);self.assertTrue(b.software_abl)
    def test_pattern_defaults_do_not_open_a_pattern(self):
        b=self.bridge();b.show_pattern=Mock();b.module_defaults('pattern');self.assertEqual(b.pattern_config,PATTERN);b.show_pattern.assert_not_called()
    def test_stale_background_request_cannot_reopen_adb_after_off(self):
        b=self.bridge();b.device=Mock()
        with self.assertRaisesRegex(ValueError,'后台请求'):app.PortableBridge._perform(b,'sensors',{})
        b.device.assert_not_called()
    def test_normal_android_port_is_not_owned_or_stopped(self):
        b=self.bridge()
        del b.prepare_adb
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'ROOT',Path(folder)),patch.object(app,'available_adb_port',return_value=5041),patch.object(app.subprocess,'run',return_value=Mock(returncode=0,stderr=b'')) as command:
            (Path(folder)/'state/android').mkdir(parents=True)
            app.PortableBridge.prepare_adb(b,dict(serial='USB',port=5037))
            self.assertEqual(b.adb_port,5041)
            self.assertIn('5041',command.call_args.args[0]);self.assertNotIn('5037',command.call_args.args[0])
    def test_factory_restore_keeps_pc_draft_and_selected_tone(self):
        b=self.bridge();b.tone=1;b.stop_pattern_process=Mock();b.runtime_loaded_by_pc=False
        b.read_state=Mock(side_effect=[{'g_video__vid_local_dimming':'3','g_video__vid_hdr_tone_mapping_mode':'1'},{'g_video__vid_local_dimming':'3','g_video__vid_hdr_tone_mapping_mode':'5'}]);b.set_tone=Mock()
        original=copy.deepcopy(b.draft)
        with patch.object(app.lab.Bridge,'perform') as restore:
            app.PortableBridge.restore_device_defaults(b)
        restore.assert_called_once_with(b,'restore',{});self.assertEqual(b.tone,1);self.assertEqual(b.draft,original);self.assertTrue(b.default_restoration['verified'])
    def test_factory_restore_requires_budget_stop_receipt(self):
        b=self.bridge();b.runtime_loaded=True;b.stop_pattern_process=Mock();b.read_budget=Mock(return_value={'lease_end':123})
        with patch.object(app.lab.Bridge,'perform') as restore:
            with self.assertRaisesRegex(RuntimeError,'预算租约停止未确认'):
                app.PortableBridge.restore_device_defaults(b)
        restore.assert_not_called();self.assertIsNone(b.default_restoration)
