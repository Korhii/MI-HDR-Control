from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import hashlib,json,sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'lab')]
import permanent
from features import PATTERN,CALIBRATION
from native_abl import DEFAULT as ABL_DEFAULT,validate as validate_abl
from server import STOCK_BY_LEVEL


class PersistenceTests(TestCase):
    def config(self):
        return dict(format='mi-hdr-controller-v1',selected_level=3,selected_tone=5,
                    profiles={f'{l}:{t}':dict(config=STOCK_BY_LEVEL[l],software_abl=True,budget=41,native_abl=validate_abl(ABL_DEFAULT)) for l in (1,2,3) for t in (5,1,0,2)},pattern=dict(PATTERN),calibration=dict(CALIBRATION))

    def test_all_profiles_and_budget_bounds(self):
        self.assertEqual(len(permanent.validate_config(self.config())['profiles']),12)
        c=self.config();c['profiles']['3:5']['budget']=87
        with self.assertRaises(ValueError):permanent.validate_config(c)
        c=self.config();del c['profiles']['1:0']
        with self.assertRaises(ValueError):permanent.validate_config(c)

    def test_old_boot_heartbeat_is_not_current_success(self):
        with TemporaryDirectory() as d:
            s=permanent.Session.__new__(permanent.Session);s.folder=Path(d)
            s.run=lambda *a,**k:'package:/data/app/~~fixture/com.example.autoreboot-fixture==/base.apk'
            sha=hashlib.sha256((ROOT/'tools/mi-hdr-persistence.apk').read_bytes()).hexdigest()
            local=dict(boot_id='old',heartbeat_ms=1000000,owner='monitor',state='applied')
            s.job=lambda text:'boot_id=new\nnow=1000\nenabled=1\nmodule_loaded=1\nbootstrap_running=1\n'+sha+'  /data/app/fixture/base.apk\n'+json.dumps(local)+'\nEnforcing\n'
            self.assertFalse(s.status()['running'])
            local['boot_id']='new'
            self.assertTrue(s.status()['running'])
            local['heartbeat_ms']=900000
            self.assertFalse(s.status()['running'])

    def test_new_adapter_requires_its_own_boot_acceptance(self):
        with patch.object(permanent,'Session') as session:
            with self.assertRaisesRegex(ValueError,'开机验收'):permanent.install(self.config())
            session.assert_not_called()


    def test_does_not_overwrite_another_apk(self):
        with TemporaryDirectory() as d,patch.object(permanent.Session,'firmware'),patch.object(permanent.Session,'status',return_value={'installed':True,'owned':False}),patch.object(permanent.Session,'run') as run:
            with self.assertRaises(ValueError):permanent.install(self.config(),d)
            self.assertFalse(any(c.args and c.args[0]=='install' for c in run.call_args_list))


if __name__=='__main__':main(verbosity=2)
