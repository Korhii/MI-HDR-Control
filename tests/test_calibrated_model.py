"""Screenshot-anchor reproduction is not independent optical validation. No ADB."""
from pathlib import Path
import io,json,sys,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'lab'))
from firmware_model import factory_nits,factory_raw,calibrated,reference,statistics,Driver,stock
from features import PATTERN

class CalibrationTests(unittest.TestCase):
    def test_all_high_nonblack_screenshot_anchors(self):
        table=reference()['high']
        for q,values in zip(table['inputs'],table['nits']):
            if q==0:continue
            for area,nits in zip(table['areas'],values):self.assertAlmostEqual(factory_nits(3,area,q),nits,places=6)
    def test_mid_low_peak_bar_anchors(self):
        bar=reference()['bars']
        for level in (1,2):
            for area,nits in zip(bar['areas'],bar['peak_nits'][str(level)]):self.assertAlmostEqual(factory_nits(level,area,10000),nits,places=6)
    def test_small_window_is_not_scaled_from_fullscreen(self):
        raw=factory_raw(3,.01,10000);value=calibrated(raw,3,.01,10000)
        self.assertEqual(value['nits'],35);self.assertGreater(raw/31242*1236,400)
        self.assertNotEqual(round(35/raw,5),round(751/factory_raw(3,100,10000),5))
    def test_dark_gray_local_mean_and_tiny_bright_share_alpha0(self):
        driver=Driver(stock(3));zero=[0]+[16]*7;raised=[8]+[16]*7
        for maximum in (32,230):self.assertGreater(driver.scaling(6,maximum,raised),driver.scaling(6,maximum,zero))
    def test_geometry_and_input_change_local_statistics(self):
        bright,_=statistics(.1,10000);gray,_=statistics(.1,1)
        self.assertNotEqual(bright,gray);self.assertNotEqual({a//32 for a,b in bright if b},{a//32 for a,b in gray if b})
        centered,_=statistics(.01,10000);offset,_=statistics(.01,10000,'zone-center')
        self.assertEqual(sum(b>0 for a,b in centered),4);self.assertEqual(sum(b>0 for a,b in offset),1)
    def test_saved_legacy_strategy_is_not_a_reusable_apply_token(self):
        from auto_fit import validate_plan
        with self.assertRaisesRegex(ValueError,'令牌'):
            validate_plan(dict(mode='global',recipe='path-a16-sf0',budget=24,ceiling=24),3,None)
    def test_default_and_unmapped_mode(self):
        self.assertEqual(PATTERN['seconds'],0);self.assertTrue(PATTERN['label']);self.assertGreaterEqual(calibrated(1000,3,1,10000,config=stock(3))['nits'],0)
        import device_models
        with self.assertRaises(ValueError):device_models.activate('32u-2026',99)
    def test_manual_prediction_http_route_is_pc_only(self):
        import portable_server as app
        body=json.dumps(dict(config=stock(3),level=3,input_nits=4000)).encode()
        handler=app.Handler.__new__(app.Handler);handler.path='/api/predict-response'
        handler.headers={'Origin':app.lab.URL,'X-MI-Token':'fixture','Content-Length':str(len(body))}
        handler.rfile=io.BytesIO(body);handler.server=SimpleNamespace(bridge=SimpleNamespace(token='fixture',model_id='32u-2026',model_confirmed=True,tone=5))
        handler.reply=Mock()
        with patch.object(app.model_worker,'call',return_value={'raw':'PC-only fixture'}) as predict:
            handler.do_POST()
        predict.assert_called_once_with('predict',model_id='32u-2026',tone=5,config=stock(3),level=3,input_nits=4000)
        handler.reply.assert_called_once_with({'ok':True,'response':{'raw':'PC-only fixture'}})
