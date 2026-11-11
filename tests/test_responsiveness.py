"""No live ADB calls. Regression tests for local/GPU and transport separation."""
from pathlib import Path
import copy,json,sys,tempfile,threading,time,unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app
import mi_probe
from features import PATTERN
from desktop_lifecycle import DEFAULT_UI,preferences

from _fixtures import confirmed

class ResponsivenessTests(unittest.TestCase):
    def test_mono_and_scale_defaults_and_floor(self):
        self.assertEqual(DEFAULT_UI['unit'],'mono');self.assertEqual(preferences({})['ui_scale'],'auto')
        for value in ('auto','100','95','90','75','65','50'):self.assertEqual(preferences({'ui_scale':value})['ui_scale'],value)
        for value in ('85','110',90):
            with self.assertRaises(ValueError):preferences({'ui_scale':value})
    def test_transport_error_is_not_remote_command_failure(self):
        self.assertTrue(mi_probe.connection_error("error: device 'ABC' not found"))
        self.assertTrue(mi_probe.connection_error('error: device offline'))
        self.assertFalse(mi_probe.connection_error('cat: permission denied'))
        self.assertFalse(mi_probe.connection_error('getBatch: missing receipt'))
    def test_non_transport_device_error_does_not_invent_disconnect(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge));b.state={'connected':True}
        with patch.object(app.lab.subprocess,'run',return_value=Mock(returncode=1,stdout=b'',stderr=b'cat: permission denied')):
            with self.assertRaises(RuntimeError):app.lab.Bridge.device(b,'shell','cat fixture')
        self.assertTrue(b.state['connected'])
    def test_native_receipt_error_keeps_transport_status(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge));b.state={'connected':True,'native':{}};b.live_debug=True
        with patch.object(app.lab.Bridge,'read_state',side_effect=TimeoutError('missing receipt')):
            with self.assertRaises(TimeoutError):b.read_state()
        self.assertTrue(b.state['connected']);self.assertTrue(b.live_debug)
    def test_explicit_transport_error_marks_offline(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge));b.state={'connected':True,'native':{}};b.live_debug=True
        with patch.object(app.lab.Bridge,'read_state',side_effect=mi_probe.ADBConnectionError('device offline')):
            with self.assertRaises(mi_probe.ADBConnectionError):b.read_state()
        self.assertFalse(b.state['connected']);self.assertFalse(b.live_debug)
    def test_disconnected_numeric_tuning_rejected_before_save(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge));b.shutdown_started=False;b.state={'connected':False};b.operation_results={};b.last_operation=None
        b.save_configuration=Mock();b._perform=Mock()
        for op,data in [('quick-budget',{'budget':24}),('native-abl-draft',{}),('auto-apply',{}),('abl',{'enabled':False})]:
            with self.assertRaisesRegex(ValueError,'请先连接ADB'):b.perform(op,data)
        b._perform.assert_not_called();b.save_configuration.assert_not_called()
    def test_pattern_lane_does_not_acquire_adb_lock_or_change_debug(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge));b.pattern_lock=threading.RLock();b.lock=threading.Lock()
        b.shutdown_started=False;b.live_debug=False;b.state={'connected':False,'pattern':True,'busy':True};b.pattern_sequence=7;b.pattern_config=copy.deepcopy(PATTERN)
        b.backlight_level=3;b.tone=5;b.profile_bank={'3:5':{}};b.operation_results={};b.last_operation=None;b.update_pattern=Mock();b.save_configuration=Mock()
        b.lock.acquire()
        try:
            result=b.fast_pattern({'config':dict(PATTERN,area_percent=12)})
        finally:b.lock.release()
        b.update_pattern.assert_called_once();self.assertEqual(result['status'],'submitted');self.assertFalse(b.live_debug);self.assertFalse(b.state['connected'])
    def test_close_pattern_does_not_stop_adb_tuning(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge));b.pattern_lock=threading.RLock();b.stop_pattern_process=Mock();b.finish=Mock()
        b.close_pattern();b.stop_pattern_process.assert_called_once();b.finish.assert_not_called()
    def test_auto_edit_reuses_live_session_in_the_same_context(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        b.state={'connected':True,'native':{'g_video__vid_local_dimming':'3','g_video__vid_hdr_tone_mapping_mode':'5'}}
        b.factory_budget=False;b.runtime_loaded=True;b.active={'mode':'live'};b.backlight_level=3;b.tone=5;b.draft={'fixture':1};b.budget_value=30
        b.request_live=Mock();b._perform=Mock();b.activate_tuning()
        b.request_live.assert_called_once_with(b.draft);b._perform.assert_called_once_with('runtime-set',{'budget':30})
    def test_desktop_owner_heartbeats_without_browser_timers(self):
        import desktop_lifecycle as life
        kernel=Mock();kernel.OpenProcess.return_value=1;kernel.WaitForSingleObject.side_effect=[0x102,0x102,0]
        server=Mock();server.bridge.beat=0
        def immediate(*args,**kwargs):
            return Mock(start=lambda:kwargs['target']())
        with patch.dict(life.os.environ,{'MI_DESKTOP_OWNER_PID':'123'}),patch.object(life.ctypes,'WinDLL',return_value=kernel),patch.object(life.threading,'Thread',side_effect=immediate):
            life.watch_owner(server)
        self.assertGreater(server.bridge.beat,0);server.stop_controller.assert_called_once_with('desktop-owner-exited')
