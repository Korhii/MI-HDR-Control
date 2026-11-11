"""Foreign identities and LAN scenarios, simulated only; no network/device operations."""
from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts')]
import adb_discovery as adb

class Scripted(adb.Discovery):
 def __init__(self,folder,devices='',mdns='',identities=None,arp=''):
  super().__init__(5059,folder);self.devices=devices;self.mdns=mdns;self.identities=identities or {};self.arp=arp;self.commands=[]
 def run(self,*args,**kw):
  self.commands.append(args)
  if args[:2]==('devices','-l'):out='List of devices attached\n'+self.devices
  elif args[:2]==('mdns','services'):out=self.mdns
  elif args[:2]==('arp','-a'):out=self.arp
  elif args[:1]==('connect',):out='connected to '+args[1]
  elif args[:1]==('-s',):
   model,serial=self.identities.get(args[1],('other',''))
   out=model+'\n'+serial+'\n' if 'getprop ro.product.device' in args[-1] else '0\n'
  else:out=''
  return dict(stdout=out,stderr='',exit_status=0)

class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  p=patch.object(adb,'CACHE',self.root/'state/cache.json');p.start();self.addCleanup(p.stop)
 def make(self,**kw):return Scripted(self.root/'audit',**kw)
 def test_three_private_networks_and_no_unspecified_endpoint(self):
  for host in ('10.137.0.44','10.44.3.9','172.20.8.51'):self.assertEqual(adb.endpoint(host+':37051'),host+':37051')
  for host in ('0.0.0.0','127.0.0.1','224.0.0.1','8.8.8.8'):self.assertIsNone(adb.endpoint(host+':5555'))
 def test_mdns_dynamic_port_and_pairing_port_separated(self):
  out='foreign _adb-tls-pairing._tcp 10.1.2.3:40001\nforeign _adb-tls-connect._tcp 10.1.2.3:37051\n'
  self.assertEqual(adb.mdns_endpoints(out),['10.1.2.3:37051'])
 def test_new_usb_identity_needs_no_author_serial(self):
  d=self.make(devices='FOREIGN_USB_01\tdevice\nPHONE\tdevice\n',identities={'FOREIGN_USB_01':('beekeeper','ANOTHER_DISPLAY'),'PHONE':('phone','PHONE')})
  self.assertEqual(d.find()['serial'],'FOREIGN_USB_01')
  self.assertFalse(any(op in ('root','tcpip','reboot','kill-server') for c in d.commands for op in c))
 def test_same_physical_display_on_usb_and_wifi_is_one_device(self):
  d=self.make(devices='FOREIGN_USB\tdevice\n10.3.2.7:5555\tdevice\n',identities={'FOREIGN_USB':('beekeeper','SAME_DISPLAY'),'10.3.2.7:5555':('beekeeper','SAME_DISPLAY')})
  self.assertEqual(d.find()['serial'],'FOREIGN_USB')
 def test_first_connection_on_another_lan_and_dynamic_port(self):
  d=self.make(mdns='foreign _adb-tls-connect._tcp 172.29.4.19:41793\n',identities={'172.29.4.19:41793':('beekeeper','NEW_DISPLAY')})
  self.assertEqual(d.find()['serial'],'172.29.4.19:41793')
 def test_two_lan_displays_require_selection(self):
  d=self.make(mdns='one _adb._tcp 10.2.1.1:5555\ntwo _adb._tcp 10.2.1.2:5555',identities={'10.2.1.1:5555':('beekeeper','A'),'10.2.1.2:5555':('beekeeper','B')})
  with self.assertRaisesRegex(ValueError,'多台'):d.find()
 def test_remembered_identity_selects_correct_lan_display(self):
  adb.CACHE.parent.mkdir();adb.CACHE.write_text(json.dumps(dict(endpoints=[],device_serial='B')),encoding='utf-8')
  d=self.make(mdns='one _adb._tcp 10.2.1.1:5555\ntwo _adb._tcp 10.2.1.2:5555',identities={'10.2.1.1:5555':('beekeeper','A'),'10.2.1.2:5555':('beekeeper','B')})
  self.assertEqual(d.find()['serial'],'10.2.1.2:5555')
 def test_more_than_32_neighbors_not_silently_omitted(self):
  text='\n'.join(f'10.50.0.{i} 02-11-22-33-44-{i:02x} dynamic' for i in range(1,70))
  self.assertIn('10.50.0.69:5555',adb.neighbor_endpoints(text))
 def test_truncated_cache_is_recovered_without_forcing_ip(self):
  adb.CACHE.parent.mkdir();adb.CACHE.write_text('{"endpoints":',encoding='utf-8')
  d=self.make(devices='NEW_USB\tdevice\n',identities={'NEW_USB':('beekeeper','NEW')})
  self.assertEqual(d.find()['device_serial'],'NEW')
 def test_rsa_authorization_has_actionable_message(self):
  d=self.make(devices='FOREIGN_USB\tunauthorized\n')
  with self.assertRaisesRegex(ValueError,'授权'):d.find()
if __name__=='__main__':unittest.main(verbosity=2)
