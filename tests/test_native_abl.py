"""Coupled OEM-policy regression tests. Offline firmware only; no ADB/photometer."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'lab'),str(ROOT/'scripts')]
from native_abl import *
from abl_predict import forecast
from firmware_model import stock

class NativeAblTests(unittest.TestCase):
    def test_strict_threshold_and_whole_load_debit(self):
        s=State();step(s,18288,31243);self.assertEqual(s.energy,FACTORY_E0)
        step(s,25000,31243);self.assertEqual(s.energy,FACTORY_E0-25000)
    def test_cap_and_insufficient_credit_is_retained(self):
        s=State(energy=17,r_prev=31243);step(s,65535,65535)
        self.assertEqual((s.energy,s.k),(17,31221))
    def test_previous_recovery_not_current(self):
        s=State(k=20000,energy=0,r_prev=20000);step(s,0,0)
        self.assertEqual(s.k,20000);step(s,0,20000);self.assertEqual(s.k,K_MAX)
    def test_output_uses_previous_gain(self):
        s=State(energy=0,r_prev=31243);used=s.g_prev;new=step(s,31243,31243,e0=0)
        self.assertEqual(used,65535);self.assertLess(new,used)
    def test_bright_count_is_shifted_and_tail_contributes_sum(self):
        self.assertEqual(load_at([(15,1151),(65535,1)],65535),(71,82800))
    def test_zero_and_infinite_duration(self):
        self.assertEqual(simulate([(0,1152)],0,dict(DEFAULT,enabled=True))['duration'],0)
        self.assertIsNone(simulate([(18288,1152)],751,dict(DEFAULT,enabled=True))['duration'])
    def test_every_policy_input_recomputes_the_trajectory(self):
        hist=[(31243,1152)];p=dict(DEFAULT,enabled=True);a=simulate(hist,1236,p)
        self.assertEqual(a['duration'],20)
        self.assertEqual(simulate(hist,1236,dict(p,e0=FACTORY_E0*2))['duration'],40)
        high=simulate(hist,1236,dict(p,l_th=40000));self.assertIsNone(high['duration']);self.assertEqual(high['stable_nits'],1236)
        speed=simulate(hist,1236,dict(p,divisor=300));self.assertLess(speed['trace'][-1][0],a['trace'][-1][0])
        reset=simulate(hist,1236,dict(p,r_reset=65535));self.assertIsNone(reset['duration'])
        self.assertEqual(a['k'],18288)
    def test_fixed_kmin_not_in_editable_packet(self):
        with self.assertRaises(ValueError):validate(dict(DEFAULT,k_min=12000))
        self.assertEqual(len(packet(DEFAULT,1).split(',')),6)
    def test_same_snapshot_couples_sf_alpha_and_load(self):
        a=forecast(stock(3),3,41,dict(DEFAULT,enabled=True),generation=11)
        c=stock(3);c['alpha']=[16]*8;c['sf']=[0,255,255,255,255]
        b=forecast(c,3,41,dict(DEFAULT,enabled=True),generation=12)
        self.assertEqual((a['generation'],b['generation']),(11,12))
        self.assertGreater(b['rows'][2]['peak_nits'],a['rows'][2]['peak_nits'])
        self.assertNotEqual(b['rows'][2]['load_peak'],a['rows'][2]['load_peak'])
        self.assertEqual(b['fixed']['k_min'],18288)
        self.assertEqual(a['rows'][-1]['trace'][-1][1],a['rows'][-1]['stable_nits'])
if __name__=='__main__':unittest.main(verbosity=2)
