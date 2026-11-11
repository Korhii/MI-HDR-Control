"""Test portable action routing without writing a device during unit tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
import portable_server as app


from _fixtures import confirmed

class DeviceControls(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.b=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        self.b.shutdown_started=False
        self.b.risk_unlocked=False;self.b.live_debug=False
        self.b.folder=Path(self.tmp.name);self.b.count=0
        self.b.state={'events':[],'connected':True}

    def test_public_build_has_no_launcher_routes_or_loader(self):
        self.assertFalse(hasattr(app.PortableBridge,'launcher_action'))
        self.assertFalse((ROOT/'scripts/launcher_control.py').exists())
        self.assertFalse((ROOT/'scripts/launcher_load.py').exists())
        self.assertNotIn('launcher-apply',(ROOT/'lab/portable.html').read_text('utf-8'))

    def test_adb_autostart_routes_and_readback(self):
        for op,action in [('adb-boot-status','status'),('adb-boot-enable','install'),('adb-boot-disable','remove')]:
            enabled=action!='remove'
            raw=('package:/data/app/companion/base.apk\n' if enabled else '')+'__permission\npolicy_boot_autostart='+str(enabled).lower()
            with self.subTest(op=op),patch.object(app.adb_autostart,'perform',return_value=(raw,self.b.folder)) as call:
                self.b.perform(op,{})
                self.assertEqual(call.call_args.args[0],action)
                self.assertEqual(self.b.adb_boot['enabled'],enabled)


if __name__=='__main__':main(verbosity=2)
