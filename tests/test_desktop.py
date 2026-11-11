"""PC lifecycle/preferences tests. Device writes are mocked, never performed."""
from pathlib import Path
import json,sys,tempfile,threading,unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app
from desktop_lifecycle import DEFAULT_UI,preferences

from _fixtures import confirmed

class DesktopTests(unittest.TestCase):
    def test_theme_choices_and_old_defaults(self):
        self.assertEqual(preferences({}),DEFAULT_UI)
        for theme in ('light','dark','system'):self.assertEqual(preferences({'theme':theme})['theme'],theme)
        for invalid in ({'theme':'blue'},{'quick_tune':1},{'auto_connect':'true'},{'other':False}):
            with self.assertRaises(ValueError):preferences(invalid)

    def test_atomic_pc_save(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'profiles').mkdir()
            bridge=confirmed(app.PortableBridge.__new__(app.PortableBridge))
            bridge.config_lock=threading.RLock()
            bridge.export_config=Mock(return_value={'ui':{'theme':'system'},'budget':27})
            with patch.object(app,'ROOT',root):bridge.save_configuration()
            self.assertEqual(json.loads((root/'profiles/controller.json').read_text())['budget'],27)
            self.assertFalse((root/'profiles/controller.tmp').exists())

    def shutdown_bridge(self):
        bridge=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        bridge.shutdown_started=False;bridge.closing=False;bridge.runtime_loaded_by_pc=False
        bridge.needs_restore=False;bridge.disconnect_adb=Mock()
        bridge.pool=Mock();bridge.lock=threading.RLock();bridge.save_configuration=Mock()
        bridge.close_pattern=Mock();bridge.close_panel=Mock();bridge.event=Mock()
        return bridge

    def test_exit_saves_and_closes_without_removing_permanent(self):
        bridge=self.shutdown_bridge()
        with patch.object(app.permanent,'remove') as remove,patch.object(app.budget,'module') as module:
            bridge.close_controller();bridge.close_controller()
        bridge.pool.shutdown.assert_called_once_with(wait=True)
        bridge.save_configuration.assert_called_once();bridge.close_pattern.assert_called_once()
        remove.assert_not_called();module.assert_not_called()

    def test_only_pc_loaded_module_is_unloaded(self):
        bridge=self.shutdown_bridge();bridge.runtime_loaded_by_pc=True;bridge.count=0;bridge.folder=Path('SESSION')
        with patch.object(app.budget,'module') as module:bridge.close_controller()
        module.assert_called_once_with('unload',Path('SESSION/exit-budget-unload-1'))
        self.assertFalse(bridge.runtime_loaded_by_pc)

    def test_quick_budget_offline_only_drafts(self):
        bridge=confirmed(app.PortableBridge.__new__(app.PortableBridge));bridge.state={'connected':False};bridge._perform=Mock();bridge.native_abl=app.validate_abl(app.ABL_DEFAULT);bridge.draft={};bridge.save_draft=Mock()
        app.PortableBridge._perform(bridge,'quick-budget',{'budget':27})
        bridge._perform.assert_called_once_with('runtime-draft',{'budget':27})

    def test_quick_budget_prepares_existing_verified_path(self):
        bridge=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        bridge.state={'connected':True,'native':{'g_video__vid_local_dimming':'3','g_video__vid_hdr_tone_mapping_mode':'5'}}
        bridge.active=None;bridge.runtime_loaded=False;bridge.backlight_level=3;bridge.tone=5
        bridge._perform=Mock();bridge.preflight=Mock();bridge.native_abl=app.validate_abl(app.ABL_DEFAULT);bridge.draft={};bridge.save_draft=Mock()
        app.PortableBridge._perform(bridge,'quick-budget',{'budget':27})
        self.assertEqual([call.args[0] for call in bridge._perform.call_args_list],['runtime-draft','runtime-load','runtime-set'])
        bridge.preflight.assert_called_once()

    def test_auto_connect_uses_discovery_identity_and_propagates_ambiguity(self):
        bridge=confirmed(app.PortableBridge.__new__(app.PortableBridge));bridge._perform=Mock();bridge.count=0;bridge.folder=Path('SESSION')
        bridge.prepare_adb=Mock(return_value={'serial':'','port':5041})
        with patch.object(app,'discover',return_value={'serial':'FOREIGN-USB','port':5042,'source':'USB'}) as discover:
            app.PortableBridge._perform(bridge,'auto-connect',{})
        bridge._perform.assert_called_once_with('connect',{'connection':{'serial':'FOREIGN-USB','port':5042}})
        self.assertEqual(discover.call_args.args[0],5041)
        bridge._perform.reset_mock()
        with patch.object(app,'discover',side_effect=ValueError('multiple supported displays')):
            with self.assertRaisesRegex(ValueError,'multiple'):app.PortableBridge._perform(bridge,'auto-connect',{})
        bridge._perform.assert_not_called()

if __name__=='__main__':unittest.main()
