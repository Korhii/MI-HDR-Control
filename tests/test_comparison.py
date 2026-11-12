"""Exercise actual A/B methods with synthetic receipts; no device I/O or imports."""
import ast
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT=Path(os.environ.get('MI_TEST_ROOT',Path(__file__).resolve().parents[1]))
STOCK=dict(sf=[255]*5,alpha=[3,5,7,9,11,13,15,16],dc=8,blend=8,dynamic=1)
ABL=dict(enabled=False,l_th=18288,e0=37491600,divisor=600,r_reset=9760)

def load_methods(file,names,namespace):
    tree=ast.parse((ROOT/'lab'/file).read_text('utf-8'))
    methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=methods,type_ignores=[]),file,'exec'),namespace)
    return {n.name:namespace[n.name] for n in methods}

class ComparisonTests(unittest.TestCase):
    def bridge(self,budget=True):
        clock=SimpleNamespace(monotonic=time.monotonic,sleep=lambda _:None)
        namespace=dict(lab=SimpleNamespace(validate=deepcopy,STOCK_BY_LEVEL={3:STOCK}),validate_abl=deepcopy,ABL_DEFAULT=ABL,RISK_BUDGET=41,time=clock,re=re)
        methods=load_methods('portable_server.py',{'clear_comparison','compare_configuration','check_risk'},namespace)
        b=type('Bridge',(),methods)()
        b.clear_comparison();b.live_debug=True;b.risk_unlocked=False
        b.active={'mode':'live','remote':'/fixture'};b.backlight_level=3;b.tone=5
        b.wanted_sequence=b.ack_sequence=4;b.request_lock=threading.Lock()
        b.state={'connected':True,'native':{'g_video__vid_local_dimming':'3','g_video__vid_hdr_tone_mapping_mode':'5'},'config':{**deepcopy(STOCK),'sf':[128]*5}}
        b.draft={**deepcopy(STOCK),'sf':[100]*5};b.native_abl={**ABL,'e0':999}
        b.profile_bank={'3:5':{'config':deepcopy(b.draft),'budget':31}}
        b.budget_value=31;b.runtime_loaded=budget;b.budget_active=budget
        b.preflight=Mock();b.event=Mock();b.publish_live=Mock()
        b.read_budget=Mock(return_value={**ABL,'enabled':1,'e0':123,'budget':30,'lease_end':0})
        b.device=Mock(side_effect=lambda *args:f'applied_sequence={b.wanted_sequence}')
        return b,clock

    def test_roundtrip_preserves_draft_and_restores_applied_not_unsent_values(self):
        b,_=self.bridge();before=deepcopy((b.draft,b.native_abl,b.profile_bank))
        for _ in range(2):
            b.compare_configuration('default')
            self.assertTrue(b.comparison_default);self.assertFalse(b.budget_active)
            self.assertEqual(b.comparison_config,STOCK)
            b.compare_configuration('tuned')
            self.assertFalse(b.comparison_default);self.assertTrue(b.budget_active)
            self.assertEqual(b.comparison_config['sf'],[128]*5)
            self.assertEqual(b.read_budget.call_args.args,(30,True,True))
            self.assertEqual(b.read_budget.call_args.kwargs['config']['e0'],123)
        self.assertEqual(before,(b.draft,b.native_abl,b.profile_bank))

    def test_factory_budget_without_runtime_stays_factory_on_return(self):
        b,_=self.bridge(False);b.compare_configuration('default');b.compare_configuration('tuned')
        b.read_budget.assert_not_called();self.assertFalse(b.budget_active)

    def test_pending_receipt_blocks_switch_without_writes(self):
        b,_=self.bridge();b.ack_sequence=3
        with self.assertRaisesRegex(ValueError,'回执'):b.compare_configuration('default')
        b.read_budget.assert_not_called();b.publish_live.assert_not_called()

    def test_offline_and_no_live_session_are_blocked(self):
        for attr in ('offline','debug-off','inactive'):
            b,_=self.bridge()
            if attr=='offline':b.state['connected']=False
            elif attr=='debug-off':b.live_debug=False
            else:b.active=None
            with self.assertRaises(ValueError):b.compare_configuration('default')
            b.read_budget.assert_not_called()

    def test_changed_context_never_applies_to_another_mode(self):
        b,_=self.bridge();b.state['native']['g_video__vid_hdr_tone_mapping_mode']='1'
        with self.assertRaisesRegex(ValueError,'模式已变化'):b.compare_configuration('default')
        b.publish_live.assert_not_called()

    def test_tuned_return_cannot_bypass_risk_consent(self):
        b,_=self.bridge();b.read_budget.return_value['budget']=58;b.compare_configuration('default');b.read_budget.reset_mock()
        with self.assertRaisesRegex(ValueError,'41/86'):b.compare_configuration('tuned')
        b.read_budget.assert_not_called();self.assertTrue(b.comparison_default)

    def test_stop_failure_does_not_report_success(self):
        b,_=self.bridge();b.read_budget.return_value['lease_end']=10
        with self.assertRaisesRegex(RuntimeError,'预算暂停'):b.compare_configuration('default')
        self.assertIsNone(b.comparison_default);b.publish_live.assert_not_called()

    def test_missing_ack_does_not_report_success(self):
        b,clock=self.bridge();b.device.return_value='';b.device.side_effect=None
        clock.monotonic=Mock(side_effect=[0,9])
        with self.assertRaisesRegex(RuntimeError,'设备回执'):b.compare_configuration('default')
        self.assertIsNone(b.comparison_default)

    def test_override_is_the_real_worker_packet_and_does_not_replace_draft(self):
        namespace=dict(validate=deepcopy,time=SimpleNamespace(monotonic=lambda:10))
        publish=load_methods('server.py',{'publish_live'},namespace)['publish_live']
        with tempfile.TemporaryDirectory() as folder:
            b=SimpleNamespace(active={'mode':'live','folder':Path(folder),'remote':'/fixture'},request_lock=threading.Lock(),wanted_sequence=7,sent_sequence=6,pending_at=0,software_abl=True,draft={**deepcopy(STOCK),'sf':[100]*5},comparison_config=deepcopy(STOCK),device=Mock())
            publish(b)
            self.assertEqual(b.sent_config,STOCK);self.assertEqual(b.draft['sf'],[100]*5)
            self.assertTrue((Path(folder)/'live-config.txt').read_text().startswith('7 255 255 255 255 255 '))

    def test_unknown_mode_and_empty_return_are_rejected(self):
        b,_=self.bridge()
        for mode in ('unknown','tuned'):
            with self.assertRaises(ValueError):b.compare_configuration(mode)
        b.publish_live.assert_not_called()

    def test_pattern_reset_preserves_comparison_and_applied_edit_ends_it(self):
        b,_=self.bridge();b.compare_configuration('default')
        ns=dict(lab=SimpleNamespace(),model_worker=None)
        perform=load_methods('portable_server.py',{'perform'},ns)['perform']
        b.shutdown_started=False;b.model_id='32u-2026';b.model_confirmed=True
        b.device_model={'verified':True};b.initial_backup={'ready':True}
        b.operation_results={};b.last_operation=None;b.auto_plans={}
        b.module_defaults=Mock();b.save_configuration=Mock();b._perform=Mock()
        perform(b,'module-defaults',{'module':'pattern'})
        self.assertTrue(b.comparison_default);self.assertIsNotNone(b.comparison_config)
        perform(b,'quick-budget',{'budget':20})
        self.assertFalse(b.comparison_default);self.assertIsNone(b.comparison_config)

    def test_failed_edit_does_not_claim_a_successful_tuned_switch(self):
        b,_=self.bridge();b.compare_configuration('default')
        perform=load_methods('portable_server.py',{'perform'},{})['perform']
        b.shutdown_started=False;b.model_id='32u-2026';b.model_confirmed=True
        b.device_model={'verified':True};b.initial_backup={'ready':True}
        b.operation_results={};b.last_operation=None;b._perform=Mock(side_effect=RuntimeError('fixture write failure'))
        with self.assertRaisesRegex(RuntimeError,'fixture write failure'):perform(b,'quick-budget',{'budget':20})
        self.assertIsNone(b.comparison_default);self.assertIsNotNone(b.comparison_saved)

if __name__=='__main__':unittest.main(verbosity=2)
