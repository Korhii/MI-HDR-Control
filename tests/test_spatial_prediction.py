"""Regression of model sensitivity, not validation of actual optical nit."""
from pathlib import Path
import copy,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'lab'))
from firmware_model import Driver,stock,statistics,calibrated,illumination_fraction,aperture_weights
from _fixtures import confirmed

class SpatialPredictionTests(unittest.TestCase):
    def test_same_peak_raw_different_sf_changes_small_window_estimate(self):
        a=stock(3);b={**a,'sf':[0,255,255,255,255]};cells,_=statistics(.01,4000)
        x,_=Driver(a).process(cells);y,_=Driver(b).process(cells)
        self.assertEqual(max(x),max(y));self.assertNotEqual(x,y)
        base=calibrated(10560,3,.01,4000,config=a);wide=calibrated(10560,3,.01,4000,config=b)
        self.assertEqual(base['nits'],35.0);self.assertGreater(wide['nits'],base['nits']*2)
    def test_alpha_and_sf_effects_are_joint_not_replacement(self):
        a=stock(3);b={**a,'alpha':[16]+a['alpha'][1:]};c={**b,'sf':[0]+[255]*4}
        alpha=calibrated(50600,3,.01,4000,config=b);joint=calibrated(50600,3,.01,4000,config=c)
        self.assertGreater(alpha['nits'],calibrated(10560,3,.01,4000,config=a)['nits']);self.assertGreater(joint['nits'],alpha['nits'])
    def test_full_field_has_no_artificial_sf_brightness_multiplier(self):
        a=stock(3);b={**a,'sf':[0]+[255]*4}
        self.assertAlmostEqual(illumination_fraction(a,100,4000),illumination_fraction(b,100,4000),places=8)
    def test_aperture_kernel_is_positive_normalized_and_finite(self):
        for area in (0,.001,.01,.1,1,25,100):
            w=aperture_weights(area);self.assertEqual(len(w),1152);self.assertAlmostEqual(sum(w),1);self.assertGreaterEqual(min(w),0)
    def test_readback_uses_acknowledged_config_not_unapplied_draft(self):
        import portable_server as app
        from features import PATTERN
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge));b.state=dict(pattern=True,connected=True,native={},config={**stock(3),'sf':[0]+[255]*4})
        b.draft=stock(3);b.backlight_level=3;b.tone=5;b.telemetry=dict(raw=10560,status='live-driver',level=3)
        b.pattern_config={**PATTERN,'area_percent':.01};b.pattern_check={'actual_area_percent':.01}
        self.assertGreater(b.current_brightness()['nits'],31.1*2)
    def test_current_manual_parameter_limits_are_validated(self):
        from server import validate
        c={**stock(3),'alpha':[16]*8,'sf':[0,255,255,255,255]}
        self.assertEqual(validate(c),c)
        with self.assertRaises(ValueError):validate({**c,'alpha':[17]*8})
