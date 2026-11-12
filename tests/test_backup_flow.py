"""Synthetic backup/connection regression; no ADB, vendor inputs or device writes."""
from pathlib import Path
from datetime import datetime,timezone
import ast,base64,copy,gzip,hashlib,json,os,re,sys,tempfile,types,unittest
from unittest.mock import patch
ROOT=Path(os.environ.get('MI_TEST_ROOT',Path(__file__).resolve().parents[1]))
DRIVER='/vendor/lib/modules/kdrv_ldm_sys.ko'
INI='/vendor/tvconfig/bsp/chip/ldm_xiaomi/ldm_ptbcn1l/ldm.ini'
IDENTITY=dict(serial='TEST_SERIAL',device='beekeeper',fingerprint='TEST_FIRMWARE',kernel='5.15.148-android14-11-g37010446f523')
NATIVE=dict(g_video__vid_local_dimming='3',g_video__vid_hdr_tone_mapping_mode='5')
DRIVER_BYTES=b'project synthetic test driver, not firmware'
def load_backup(home):
 source=ROOT/'scripts/device_backup.py';tree=ast.parse(source.read_text('utf-8'))
 names={'digest','factory_defaults','identity','validate','read_policy','validate_policy','save_policy','local_inventory','ensure','public'}
 module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
 calls=dict(remote_writes=0,snapshot_reads=0,remote_reads=0)
 ini=[]
 for suffix in ('_LOW','_MID','_HIGH'):
  ini += [f'u8SFStrength{n if n>1 else ""}{suffix} = 255;' for n in range(1,6)]
  ini += [f'u8DCMaxAlpha{suffix} = 8;',f'u8LDFBlendAlpha{suffix} = 8;',f'u8DynamicAlphaEn{suffix} = 1;']
 ini += [f'u8DynamicAlpha{n} = {n+3};' for n in range(8)]
 ini_bytes='\n'.join(ini).encode()
 class Session:
  def __init__(self):self.folder=home/'commands';self.folder.mkdir(parents=True,exist_ok=True);self.remote='/TEST_ONLY';self.remote_raw=None;self.read_error=False
  def firmware(self):pass
  def run(self,*args,**kwargs):
   if args[0]=='shell':return '\n'.join(IDENTITY.values())
   if args[0]=='pull':Path(args[-1]).write_bytes(DRIVER_BYTES if args[1].endswith('vendor-0') else ini_bytes)
   return ''
  def job(self,text):return ''
 s=Session()
 def remote_digest(session):
  if session.read_error:raise RuntimeError('remote read failed')
  return hashlib.sha256(session.remote_raw).hexdigest() if session.remote_raw is not None else None
 def read_remote(session):calls['remote_reads']+=1;return session.remote_raw
 def write_remote(session,raw):calls['remote_writes']+=1;session.remote_raw=raw
 def read_info(session):calls['snapshot_reads']+=1;return dict(factory_ini=INI,sf=[255]*5,dc=8,pip_bypass=0,raw='test only')
 ns=dict(Path=Path,datetime=datetime,timezone=timezone,base64=base64,gzip=gzip,hashlib=hashlib,json=json,os=os,re=re,ROOT=home,DRIVER=DRIVER,INIS=[INI],SCOPE='test only',REMOTE='/TEST_ONLY/backup/initial-v1.json',permanent=types.SimpleNamespace(DRIVER_SHA=hashlib.sha256(DRIVER_BYTES).hexdigest(),Session=lambda folder:s),remote_digest=remote_digest,read_remote=read_remote,write_remote=write_remote,read_info=read_info)
 exec(compile(module,str(source),'exec'),ns)
 vendor={n:dict(sha256=hashlib.sha256(raw).hexdigest(),gzip_base64=base64.b64encode(gzip.compress(raw,mtime=0)).decode()) for n,raw in ((DRIVER,DRIVER_BYTES),(INI,ini_bytes))}
 data=dict(format='mi-hdr-initial-backup-v1',created_at='2026-01-01T00:00:00+00:00',identity=IDENTITY,initial_snapshot=dict(native=NATIVE),factory_ini=INI,factory_defaults=ns['factory_defaults'](ini_bytes),vendor_files=vendor)
 raw=json.dumps(data).encode();return ns,s,calls,raw
def route(name):
 tree=ast.parse((ROOT/'lab/portable_server.py').read_text('utf-8'));cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_perform')
 nodes=[n for n in ast.walk(method) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='op' and len(n.test.comparators)==1 and isinstance(n.test.comparators[0],ast.Constant) and n.test.comparators[0].value==name]
 assert len(nodes)==1
 fn=ast.FunctionDef(name='operation',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='self'),ast.arg(arg='data')],kwonlyargs=[],kw_defaults=[],defaults=[]),body=copy.deepcopy(nodes[0].body),decorator_list=[])
 return ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
def connect_case(home,remote=True,confirmed=False):
 ns,s,calls,raw=load_backup(home);s.remote_raw=raw if remote else None
 class Controller:
  def __init__(self):self.model_confirmed=True;self.backup_policy=dict(pc=True,device=False,confirmed=confirmed);self.folder=home;self.state=dict(connected=False,native=NATIVE);self.device_model=dict(verified=True,factory_ini=INI);self.initial_backup=None;self.runtime_loaded=False
  def prepare_adb(self,*args):return dict(serial='TEST_USB',port=0)
  def device(self,*args,**kwargs):return ('beekeeper\n'+IDENTITY['kernel']) if len(args)>1 and 'getprop' in args[1] else ''
  def read_state(self):self.state['connected']=True
  def verify_device_model(self):pass
  def event(self,*args,**kwargs):pass
  def read_budget(self):raise AssertionError('no runtime module expected')
 controller=Controller();dependency=types.ModuleType('prepare_local_assets');dependency.prepare_device=lambda device:None
 scope=dict(device_backup=types.SimpleNamespace(ensure=ns['ensure']),deploy=lambda:None,permanent=types.SimpleNamespace(status=lambda folder:{}))
 exec(compile(route('connect'),'real_connect_branch','exec'),scope)
 error=None
 with patch.dict(sys.modules,{'prepare_local_assets':dependency}):
  try:scope['operation'](controller,{})
  except Exception as e:error=str(e)
 return controller,calls,error,ns,s,raw
class BackupFlow(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name);self.ns,self.session,self.calls,self.raw=load_backup(self.home)
 def tearDown(self):self.temp.cleanup()
 def ensure(self,confirmed=False,device=False,existing_only=True):
  return self.ns['ensure'](self.home/'work',NATIVE,session=self.session,home=self.home/'backups',policy=dict(pc=True,device=device,confirmed=confirmed),existing_only=existing_only)
 def test_remote_backup_recovers_without_location_choice(self):
  self.session.remote_raw=self.raw;b=self.ensure();self.assertTrue(b['ready']);self.assertTrue(b['recovered_from_device']);self.assertTrue(b['reused']);self.assertEqual(Path(b['pc_path']).read_bytes(),self.raw);self.assertEqual(self.calls['remote_writes'],0)
 def test_another_extraction_reuses_same_monitor_backup(self):
  self.session.remote_raw=self.raw;a=self.ensure();self.ns['ROOT']=self.home/'another'
  b=self.ns['ensure'](self.home/'other-work',NATIVE,session=self.session,home=self.home/'other-backups',policy=dict(pc=True,device=False,confirmed=False),existing_only=True)
  self.assertEqual(a['id'],b['id']);self.assertEqual(self.session.remote_raw,self.raw);self.assertEqual(self.calls['remote_writes'],0)
 def test_existing_pc_does_not_create_device_copy_from_old_preference(self):
  self.session.remote_raw=self.raw;b=self.ensure();self.session.remote_raw=None;b=self.ensure(confirmed=True,device=True);self.assertTrue(b['ready']);self.assertFalse(b['device_copy_exists']);self.assertEqual(self.calls['remote_writes'],0)
 def test_missing_backup_waits_for_explicit_choice(self):
  b=self.ensure();self.assertFalse(b['ready']);self.assertEqual(b['status'],'missing');self.assertFalse(list((self.home/'backups').glob('*/initial-v1.json')));self.assertEqual(self.calls['snapshot_reads'],0)
 def test_old_global_preference_does_not_authorize_new_snapshot(self):
  b=self.ensure(confirmed=True,device=True);self.assertFalse(b['ready']);self.assertEqual(self.calls['snapshot_reads'],0);self.assertEqual(self.calls['remote_writes'],0)
 def test_read_failure_does_not_become_missing(self):
  self.session.read_error=True
  with self.assertRaisesRegex(RuntimeError,'read failed'):self.ensure()
  self.assertEqual(self.calls['snapshot_reads'],0)
 def test_corrupt_remote_does_not_create_replacement(self):
  self.session.remote_raw=b'invalid JSON'
  with self.assertRaises(ValueError):self.ensure()
  self.assertEqual(self.session.remote_raw,b'invalid JSON');self.assertEqual(self.calls['remote_writes'],0)
 def test_wrong_identity_does_not_create_replacement(self):
  data=json.loads(self.raw);data['identity']={**IDENTITY,'serial':'OTHER_DEVICE'};self.session.remote_raw=json.dumps(data).encode()
  with self.assertRaisesRegex(ValueError,'不匹配'):self.ensure()
  self.assertEqual(self.calls['remote_writes'],0)
 def test_pc_remote_conflict_preserves_both(self):
  self.session.remote_raw=self.raw;b=self.ensure();changed=json.loads(self.raw);changed['created_at']='other';self.session.remote_raw=json.dumps(changed).encode();before=self.session.remote_raw
  with self.assertRaisesRegex(ValueError,'不一致'):self.ensure()
  self.assertEqual(Path(b['pc_path']).read_bytes(),self.raw);self.assertEqual(self.session.remote_raw,before)
 def test_explicit_choice_can_create_once(self):
  b=self.ensure(confirmed=True,device=True,existing_only=False);self.assertTrue(b['ready']);self.assertEqual(self.calls['remote_writes'],1);self.assertEqual(self.calls['snapshot_reads'],1)
  self.ensure(confirmed=True,device=True,existing_only=False);self.assertEqual(self.calls['remote_writes'],1)
 def test_new_backup_still_requires_confirmed_policy(self):
  with self.assertRaisesRegex(ValueError,'必须选择'):self.ensure(existing_only=False)
 def test_connect_does_not_require_saved_location_policy(self):
  controller,calls,error,*_=connect_case(self.home);self.assertIsNone(error);self.assertTrue(controller.initial_backup['ready']);self.assertFalse(controller.backup_policy['confirmed']);self.assertEqual(calls['remote_writes'],0)
 def test_connect_with_no_backup_remains_read_only(self):
  controller,calls,error,*_=connect_case(self.home,remote=False,confirmed=True);self.assertIsNone(error);self.assertTrue(controller.state['connected']);self.assertEqual(controller.initial_backup['status'],'missing');self.assertEqual(calls['snapshot_reads'],0)
 def test_unchecked_device_is_not_reported_as_zero(self):
  self.assertEqual(self.ns['public'](None)['status'],'not-checked');self.assertIsNone(self.ns['public'](None)['device_copy_exists'])
 def test_read_change_does_not_store_a_different_backup(self):
  self.session.remote_raw=self.raw;changed=json.loads(self.raw);changed['created_at']='changed during transfer';self.ns['read_remote']=lambda session:json.dumps(changed).encode()
  with self.assertRaisesRegex(ValueError,'前后不一致'):self.ensure()
  self.assertFalse(list((self.home/'backups').glob('*/initial-v1.json')))
 def policy_operation(self,connected,status):
  controller=types.SimpleNamespace(state=dict(connected=connected,native=NATIVE),device_model=dict(verified=True,factory_ini=INI),initial_backup=dict(ready=False,status=status),backup_policy=dict(pc=True,device=False,confirmed=False),folder=self.home)
  scope=dict(device_backup=types.SimpleNamespace(save_policy=self.ns['save_policy'],ensure=self.ns['ensure']));exec(compile(route('backup-policy'),'real_policy_branch','exec'),scope)
  return controller,scope['operation']
 def test_policy_choice_requires_connection(self):
  controller,op=self.policy_operation(False,'missing')
  with self.assertRaisesRegex(ValueError,'先连接'):op(controller,dict(policy=dict(pc=True,device=True,confirmed=True)))
  self.assertFalse((self.home/'state/backup-policy.json').exists())
 def test_policy_choice_cannot_bypass_failed_discovery(self):
  controller,op=self.policy_operation(True,'error')
  with self.assertRaisesRegex(ValueError,'先完成'):op(controller,dict(policy=dict(pc=True,device=True,confirmed=True)))
  self.assertEqual(self.calls['remote_writes'],0)
 def test_explicit_choice_after_missing_backup_creates(self):
  controller,op=self.policy_operation(True,'missing');op(controller,dict(policy=dict(pc=True,device=True,confirmed=True)))
  self.assertTrue(controller.initial_backup['ready']);self.assertEqual(self.calls['remote_writes'],1)
if __name__=='__main__':
 if '--probe' in sys.argv:
  with tempfile.TemporaryDirectory() as tmp:
   obj,calls,error,*_=connect_case(Path(tmp));print(json.dumps(dict(connected=obj.state['connected'],backup_ready=bool(obj.initial_backup and obj.initial_backup.get('ready')),policy_confirmed=obj.backup_policy['confirmed'],remote_writes=calls['remote_writes'],snapshot_reads=calls['snapshot_reads'],error=error),ensure_ascii=False))
 else:unittest.main()
