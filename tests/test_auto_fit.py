from pathlib import Path
import json,sys
from unittest import TestCase
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
from auto_fit import validate_plan,AUTO_KNOTS
from native_abl import DEFAULT as ABL_DEFAULT,validate as validate_abl
import portable_server as app

from _fixtures import confirmed

class AutoPlanTests(TestCase):
    def plan(self):
        return dict(mode='global',recipe='path-a3-sf255',ceiling=24,budget=24)

    def test_deleted_segmented_mode_rejected(self):
        p=self.plan();p['mode']='segmented'
        with self.assertRaises(ValueError):validate_plan(p,3,ROOT/'resources/ui/joint-output.json')

    def test_cap_and_recipe_cannot_be_bypassed(self):
        for field,value in [('budget',25),('recipe','not-tested')]:
            p=self.plan();p[field]=value
            with self.assertRaises(ValueError):validate_plan(p,3,ROOT/'resources/ui/joint-output.json')
    def test_old_window_schema_is_not_accepted(self):
        p=self.plan();p['curve']={}
        with self.assertRaises(ValueError):validate_plan(p,3,ROOT/'resources/ui/joint-output.json')

    def test_saved_global_recipe_requires_a_fresh_session_token(self):
        with self.assertRaisesRegex(ValueError,'令牌'):
            validate_plan(self.plan(),3,ROOT/'resources/ui/joint-output.json')
    def test_auto_apply_off_requires_explicit_live_gate(self):
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        b.shutdown_started=False;b.risk_unlocked=False;b.live_debug=False;b.auto_plans={}
        b.backlight_level=3;b.tone=5;b.active=None;b.wanted_sequence=b.ack_sequence=0
        b.operation_results={};b.last_operation=None;b.save_draft=Mock();b.save_configuration=Mock();b.activate_tuning=Mock()
        b.state={'connected':True};b.native_abl=dict(ABL_DEFAULT)
        with self.assertRaisesRegex(ValueError,'先开启实时调试'):b.perform('auto-apply',{**self.plan(),'_field':'auto'})
        b.activate_tuning.assert_not_called();b.save_draft.assert_not_called()
    def test_current_tone_context_is_sent_to_fit_validation(self):
        from firmware_model import stock
        b=confirmed(app.PortableBridge.__new__(app.PortableBridge))
        b.shutdown_started=False;b.risk_unlocked=False;b.live_debug=True;b.backlight_level=3;b.tone=1
        b.state={'connected':True};b.native_abl=dict(ABL_DEFAULT);b.draft=stock(3)
        b.save_draft=Mock();b.save_configuration=Mock();b.activate_tuning=Mock();b.auto_plans={};b.active=None;b.wanted_sequence=b.ack_sequence=0
        with patch.object(app.model_worker,'call',side_effect=ValueError('fixture validation rejected')) as worker:
            with self.assertRaisesRegex(ValueError,'fixture validation'):b.perform('auto-apply',self.plan())
        self.assertEqual(worker.call_args.kwargs['tone'],1);self.assertEqual(worker.call_args.kwargs['model_id'],'32u-2026')
        b.save_draft.assert_not_called();b.activate_tuning.assert_not_called()
