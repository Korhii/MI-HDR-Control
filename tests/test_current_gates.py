"""Explicit negative preconditions; no device calls and no weakening of write gates."""
from pathlib import Path
import sys,unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app
from _fixtures import confirmed

class CurrentGates(unittest.TestCase):
    def bridge(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        b.shutdown_started=False;b.state={'connected':True};b._perform=Mock();b.save_configuration=Mock()
        return b
    def test_model_confirmation_precedes_parameter_edit(self):
        b=self.bridge();b.model_confirmed=False
        with self.assertRaisesRegex(ValueError,'侦测'):b.perform('quick-budget',{'budget':24})
        b._perform.assert_not_called()
    def test_adb_panel_verification_precedes_parameter_edit(self):
        b=self.bridge();b.device_model={'verified':False}
        with self.assertRaisesRegex(ValueError,'机型未复核'):b.perform('quick-budget',{'budget':24})
        b._perform.assert_not_called()
    def test_verified_initial_backup_precedes_parameter_edit(self):
        b=self.bridge();b.initial_backup={'ready':False}
        with self.assertRaisesRegex(ValueError,'初始设备备份'):b.perform('quick-budget',{'budget':24})
        b._perform.assert_not_called()
    def test_wrong_model_window_cannot_submit_after_model_change(self):
        b=self.bridge()
        with self.assertRaisesRegex(ValueError,'机型已切换'):b.perform('quick-budget',{'budget':24,'_model':'27u-2026'})
        b._perform.assert_not_called()

if __name__=='__main__':unittest.main()
