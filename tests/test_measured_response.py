"""Driver samples are evidence of digital output, not optical nit measurements."""
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'lab'))
from measured_response import basis,source
from firmware_model import stock,calibrated

class MeasuredResponseTests(unittest.TestCase):
    def config(self,a=16,s=0):return {**stock(3),'alpha':[a]+[16]*7,'sf':[s]+[255]*4}
    def test_validated_capture_count_and_dimensions(self):
        data=source();self.assertEqual(len(data['rows']),168)
        self.assertEqual(data['ldf_shape'],[96,48])
        for r in data['rows']:self.assertEqual(len(r['vector']),1152)
        self.assertTrue(all(s['restored'] for s in data['sources']))
    def test_same_aw_and_peak_do_not_erase_sf_neighborhood_effect(self):
        a=basis(self.config(s=255),3,.01,4000);b=basis(self.config(),3,.01,4000)
        self.assertEqual(a['driver_aw24'],b['driver_aw24'])
        self.assertEqual(a['driver_peak24'],b['driver_peak24'])
        self.assertGreater(b['driver_ratio24'],a['driver_ratio24']*3)
    def test_live_global_aw_is_not_misread_as_zone_maximum(self):
        value=calibrated(65535,3,.01,10000,config=stock(3),raw_kind='global-aw')
        self.assertEqual(value['nits'],35);self.assertIn('AW不冒充分区输出',value['note'])
    def test_global_aw_does_not_scale_the_local_window_prediction(self):
        a=calibrated(100,3,.01,4000,config=self.config(),raw_kind='global-aw')
        b=calibrated(65535,3,.01,4000,config=self.config(),raw_kind='global-aw')
        self.assertEqual(a['nits'],b['nits']);self.assertFalse(a['aw_gain_applied'])
        stock_value=calibrated(65535,3,.01,4000,config=stock(3),raw_kind='global-aw')
        self.assertGreater(a['nits'],stock_value['nits']);self.assertIn('光学代理估算',a['note'])
    def test_unsampled_local_gray_and_sf2_are_not_claimed_measured(self):
        self.assertIsNone(basis(self.config(),3,.01,1000))
        c=self.config();c['sf'][1]=0;self.assertIsNone(basis(c,3,.01,4000))
    def test_fullscreen_no_sf_multiplier_and_no_endpoint_hardcoding(self):
        for a,s in [(0,255),(4,255),(8,64),(16,9),(16,0)]:
            self.assertAlmostEqual(basis(self.config(a,s),3,100,4000)['driver_ratio24'],1,places=5)
