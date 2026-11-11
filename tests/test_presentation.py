"""Keep reference nit visible without disguising it as an optical measurement."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json,sys,time,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'lab'))
from portable_server import PortableBridge
from firmware_model import stock,calibrated
from features import PATTERN

from _fixtures import confirmed

class PresentationTests(unittest.TestCase):
    def make(self,folder,q=10000,raw=20698):
        b=confirmed(PortableBridge.__new__(PortableBridge))
        b.state=dict(pattern=True,connected=True,native={},config=stock(3))
        b.backlight_level=3;b.tone=5;b.telemetry=dict(raw=raw,status='live-driver',level=3,budget_used=24)
        b.pattern_config={**PATTERN,'input_nits':q,'area_percent':100,'mode':'fullscreen','label':False}
        b.pattern_check={'actual_area_percent':100};b.pattern_dir=Path(folder);b.pattern_sequence=1
        b.factory_budget=True;b.native_abl={'enabled':False}
        return b
    def receipt(self,folder,**changes):
        d=dict(sequence=1,visible=True,occluded=False,foreground=True,wall_time_ms=time.time()*1000);d.update(changes)
        (Path(folder)/'presentation.json').write_text(json.dumps(d),encoding='utf-8')
    def test_factory_fullscreen_does_not_treat_aw_variation_as_new_budget(self):
        with TemporaryDirectory() as folder:
            self.receipt(folder)
            for raw in (18288,20698):
                b=self.make(folder,raw=raw);r=b.current_brightness()
                self.assertEqual(r['nits'],751);self.assertEqual(r['raw'],raw);self.assertFalse(r['aw_gain_applied'])
    def test_1000_to_10000_factory_plateau_comes_from_reference_not_clamp(self):
        with TemporaryDirectory() as folder:
            self.receipt(folder)
            self.assertEqual(self.make(folder,q=1000).current_brightness()['nits'],750)
            self.assertEqual(self.make(folder,q=10000).current_brightness()['nits'],751)
    def test_occlusion_keeps_numeric_estimate_and_marks_quality(self):
        with TemporaryDirectory() as folder:
            self.receipt(folder,occluded=True,foreground=True)
            r=self.make(folder).current_brightness()
            self.assertEqual(r['nits'],751);self.assertEqual(r['raw'],20698);self.assertEqual(r['estimate_quality'],'mixed')
            self.assertIn('遮挡',r['note'])
    def test_presentation_delay_does_not_blank_valid_live_estimate(self):
        with TemporaryDirectory() as folder:
            for changes in ({'visible':False},{'wall_time_ms':0},{'sequence':0}):
                self.receipt(folder,**changes);r=self.make(folder).current_brightness()
                self.assertEqual(r['nits'],751);self.assertEqual(r['estimate_quality'],'pending')
    def footer(self,b):
        b.runtime_loaded=True;b.budget_value=41;b.pattern_started=0;b.operation_results={}
        b.pattern_label()
        return (b.pattern_dir/'status.txt').read_text(encoding='utf-8')
    def test_footer_numeric_first_no_diagnostic_paragraph(self):
        with TemporaryDirectory() as folder:
            self.receipt(folder,occluded=True);b=self.make(folder);b.pattern_config['label']=True
            footer=self.footer(b)
            self.assertTrue(footer.startswith('预估显示亮度 ≈751 nit（参考换算） | AW驱动全局增益原始值 20698'))
            self.assertLess(len(footer),240);self.assertEqual(len(footer.splitlines()),1)
            for word in ('遮挡','采样','标签','非实测','估算','混合'):self.assertNotIn(word,footer)
    def test_details_off_keeps_nit(self):
        with TemporaryDirectory() as folder:
            self.receipt(folder,occluded=True);b=self.make(folder)
            self.assertEqual(self.footer(b),'预估显示亮度 ≈751 nit')
    def test_small_window_and_array_notes_stay_out_of_footer(self):
        with TemporaryDirectory() as folder:
            b=self.make(folder);b.pattern_config.update(label=True,area_percent=.01,rows=8,cols=8,mode='windowed')
            b.pattern_check['actual_area_percent']=.01
            footer=self.footer(b)
            self.assertIn('AW驱动全局增益原始值 20698',footer);self.assertIn('标签',b.current_brightness()['note'])
            self.assertNotIn('标签',footer);self.assertNotIn('窗口化',footer)
    def test_no_valid_sampling_has_placeholder_not_stale_number(self):
        with TemporaryDirectory() as folder:
            for changes in ({'connected':False},{'status':'offline'},{'raw':None}):
                b=self.make(folder);b.pattern_config['label']=True
                if 'connected' in changes:b.state.update(changes)
                else:b.telemetry.update(changes)
                self.assertTrue(self.footer(b).startswith('预估显示亮度 nit —（参考换算） | AW驱动全局增益原始值 —'))
                b.pattern_config['label']=False
                self.assertEqual(self.footer(b),'预估显示亮度 nit —')
    def test_covered_custom_budget_keeps_numeric_readback(self):
        with TemporaryDirectory() as folder:
            self.receipt(folder,occluded=True);b=self.make(folder,raw=31243)
            b.factory_budget=False;b.telemetry['budget_used']=41
            self.assertGreater(b.current_brightness()['nits'],1200)
            self.assertIn('nit',self.footer(b));self.assertNotIn('—',self.footer(b))
    def test_overridden_budget_still_tracks_valid_live_gain(self):
        with TemporaryDirectory() as folder:
            self.receipt(folder);b=self.make(folder,raw=31243);b.factory_budget=False;b.telemetry['budget_used']=41
            self.assertGreater(b.current_brightness()['nits'],1200)
    def test_actual_gain_used_not_aw_controls_live_abl_estimate(self):
        with TemporaryDirectory() as folder:
            for level in (1,2,3):
                b=self.make(folder);b.backlight_level=level;b.telemetry['level']=level;b.state['config']=stock(level)
                b.telemetry['gain_used']=65535;full=b.current_brightness()['nits']
                b.telemetry['gain_used']=32767;half=b.current_brightness()
                self.assertAlmostEqual(half['nits'],full*32767/65535,delta=.1)
                self.assertIn('G_prev',half['note'])
    def test_keyboard_bridge_does_not_activate_range_or_checkbox(self):
        code=(ROOT/'lab/modules.js').read_text(encoding='utf-8')
        self.assertIn("postMessage('keyboard-focus')",code)
        self.assertIn("['range','checkbox','radio'",code)
        self.assertIn('miRestoreInputFocus',code)
