"""Small offline regression suite. Never changes monitor settings."""
from pathlib import Path
import json
import math
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lab'))
from features import *
from native_abl import DEFAULT,validate as validate_abl,packet as abl_packet

class FeatureTests(unittest.TestCase):
    def test_oem_policy_packet_and_fixed_floor(self):
        values=abl_packet(DEFAULT,123).split(',')
        self.assertEqual(values,['0','18288','37491600','600','9760','123'])
        for p in [dict(DEFAULT,l_th=-1),dict(DEFAULT,divisor=65536),dict(DEFAULT,k_min=1)]:
            with self.assertRaises(ValueError):validate_abl(p)
        self.assertEqual(validate_abl(dict(DEFAULT,e0=10**40))['e0'],10**40)
        with self.assertRaises(ValueError):validate_abl(dict(DEFAULT,e0=2**32),True)

    def test_pattern_boundaries(self):
        for p in [dict(PATTERN),dict(PATTERN,pixel_width=1,pixel_height=1),dict(PATTERN,rows=64,cols=64,area_percent=100,input_nits=10000)]:
            self.assertEqual(validate_pattern(p),p)
        for p in [dict(PATTERN,area_percent=101),dict(PATTERN,input_nits=math.nan),dict(PATTERN,rows=0),dict(PATTERN,pixel_width=1),dict(PATTERN,label=1)]:
            with self.assertRaises(ValueError):validate_pattern(p)

    def test_control_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.txt';write_pattern(p,PATTERN,17)
            self.assertIn('sequence 17\n',p.read_text())
            self.assertIn('label 1\n',p.read_text())

    def test_sensors_no_invented_data(self):
        raw='__node\tthermal\t/sys/class/thermal/thermal_zone0/temp\tcpu\n__rc\t0\n47000\n__end\n__node\tthermal\t/sys/class/thermal/thermal_zone1/temp\tpanel\n__rc\t1\nPermission denied\n__end\n__sensors_complete=1\n'
        s=parse_sensors(raw);self.assertTrue(s['complete']);self.assertEqual(s['sensors'][0]['value'],47)
        self.assertEqual(s['sensors'][1]['status'],'unavailable');self.assertIsNone(s['sensors'][1]['value'])
        self.assertFalse(parse_sensors('')['complete'])

    def test_iio_scale(self):
        raw=''.join(f'__node\tiio\t/sys/bus/iio/devices/iio:device0/in_illuminance_{k}\tals\n__rc\t0\n{v}\n__end\n' for k,v in [('raw',200),('scale',.1),('offset',5)])+'__sensors_complete=1\n'
        r=parse_sensors(raw)['sensors'][0];self.assertEqual(r['unit'],'lux');self.assertAlmostEqual(r['value'],20.5)

    def test_estimate_context(self):
        e=estimate(31245,41,100,3,5,CALIBRATION)
        self.assertEqual(e['setting_nits'],1236);self.assertEqual(e['reading_nits'],1236)
        for area,level,tone in [(50,3,5),(100,2,5),(100,3,1)]:
            self.assertIsNone(estimate(31245,41,area,level,tone,CALIBRATION)['reading_nits'])
        self.assertIsNone(estimate(None,None,100,3,5,CALIBRATION)['reading_nits'])

    def test_android_alias_and_light(self):
        thermal='Cached temperatures:\nTemperature{mValue=99.0, mType=0, mName=CPU, mStatus=0}\nCurrent temperatures from HAL:\nTemperature{mValue=62.0, mType=0, mName=CPU, mStatus=0}\nTemperature{mValue=62.0, mType=11, mName=display, mStatus=0}\nCurrent cooling devices'
        light='0x00001000) Bottom light | silergy | type: android.sensor.light(5)\nRecent Sensor events:\nBottom light: last 2 events\n 1 (ts=10.0, wall=11:12:00.000) 120.00, 0.00, 0.00,\n 2 (ts=10.1, wall=11:12:00.100) 124.00, 0.00, 0.00,\nActive sensors:'
        rows=android_sensors(thermal,light)
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['value'],62)
        self.assertEqual(rows[0]['alias_count'],2);self.assertEqual(rows[1]['value'],124)
        self.assertEqual(rows[1]['unit'],'lux')

if __name__=='__main__':unittest.main(verbosity=2)
