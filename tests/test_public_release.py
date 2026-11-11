"""Current public-release contract; separate from inherited development fixtures."""
from pathlib import Path
import hashlib,json,os,sys,tarfile,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'release-tools'),str(ROOT/'scripts'),str(ROOT/'lab'),str(ROOT/'tools/predict-libs')]
import release,permanent,local_asset_paths

class PublicContract(unittest.TestCase):
 def test_clean_export(self):
  self.assertEqual(release.check(ROOT)['errors'],[])
 def test_scope(self):
  self.assertFalse((ROOT/'scripts/launcher_control.py').exists())
  self.assertNotIn('def launcher_action', (ROOT/'lab/portable_server.py').read_text('utf-8'))
  self.assertNotIn('data-device-op="launcher-',(ROOT/'lab/portable.html').read_text('utf-8'))
  import re
  script=re.search(r'<script>(.*?)</script>',(ROOT/'lab/portable.html').read_text('utf-8'),re.S).group(1)
  self.assertEqual(hashlib.sha256(script.encode()).hexdigest(),json.loads((ROOT/'resources/ui/control-contract.json').read_text('utf-8'))['controller_script_sha256'])
 def test_no_author_cache(self):
  self.assertFalse((ROOT/'tools/MtkDirectTool.jar').exists())
  self.assertFalse((ROOT/'tools/mi-oem-runtime.ko').exists())
  self.assertFalse((ROOT/'resources/model').exists())
 def test_safe_initial_defaults(self):
  from desktop_lifecycle import DEFAULT_UI
  self.assertFalse(DEFAULT_UI['auto_connect']);self.assertEqual(DEFAULT_UI['unit'],'mono')
  c=json.loads((ROOT/'profiles/controller.json').read_text('utf-8'))
  self.assertEqual(len(c['profiles']),12);self.assertTrue(all(x['factory_budget'] for x in c['profiles'].values()))
  self.assertEqual(json.loads((ROOT/'state/connection.json').read_text('utf-8')),{'serial':'','port':5041})
 def test_model_limits(self):
  self.assertEqual(set(json.loads((ROOT/'resources/models/registry.json').read_text('utf-8'))['models']),{'32u-2026','27u-2026'})
  receipt=json.loads((ROOT/'resources/persistence/acceptance.json').read_text('utf-8'))
  self.assertEqual(permanent.write_capability('32u-2026')['boot_verified'],receipt['boot_verified'])
  self.assertFalse(permanent.write_capability('27u-2026')['boot_verified'])
 def test_acceptance_expires_with_component_change(self):
  with tempfile.TemporaryDirectory() as temp:
   t=Path(temp);(t/'resources/models').mkdir(parents=True);(t/'resources/persistence').mkdir()
   (t/'resources/models/registry.json').write_bytes((ROOT/'resources/models/registry.json').read_bytes())
   good=b'valid component';(t/'fixture.bin').write_bytes(good)
   (t/'resources/persistence/acceptance.json').write_text(json.dumps(dict(adapter='mi_oemabl',model_id='32u-2026',boot_verified=True,component_sha256={'fixture.bin':hashlib.sha256(good).hexdigest()})),encoding='utf-8')
   with patch.object(permanent,'ROOT',t):
    self.assertTrue(permanent.write_capability('32u-2026')['boot_verified'])
    (t/'fixture.bin').write_bytes(b'changed');self.assertFalse(permanent.write_capability('32u-2026')['boot_verified'])
 def test_source_archives(self):
  with tarfile.open(ROOT/'third_party/sources/unicorn-2.1.4.tar.gz') as z:
   names=z.getnames()
   for end in ('src/uc.c','src/qemu/target/arm/translate.c','src/CMakeLists.txt','src/qemu/COPYING'):
    self.assertTrue(any(n.endswith(end) for n in names),end)
 def test_font_provenance(self):
  rows=json.loads((ROOT/'third_party/provenance.json').read_text('utf-8'))
  for row in rows:
   if row['component'].endswith('.ttf'):self.assertEqual(hashlib.sha256((ROOT/'resources/fonts'/row['component']).read_bytes()).hexdigest(),row['sha256'])
  css=(ROOT/'lab/eva.css').read_text('utf-8');self.assertNotIn('Matisse',css)
 def test_palette_names(self):
  js=(ROOT/'lab/tuning.js').read_text('utf-8');html=(ROOT/'lab/portable.html').read_text('utf-8')
  for label in ('初·绿紫','零·蓝银','二·赤橙','八·桃绿','六·蓝金','素·黑白'):self.assertIn(label,js);self.assertIn(label,html)
  self.assertNotIn('EVA / UNIT',js);self.assertNotIn('机体主题',html)
 def test_readiness_is_explicit(self):
  self.assertIn('local_assets',(ROOT/'lab/portable_server.py').read_text('utf-8'))
  self.assertIn('local_assets?.ready===false',(ROOT/'lab/auto.js').read_text('utf-8'))
 def test_recipe_is_not_upload(self):
  m=json.loads((ROOT/'release-meta.json').read_text('utf-8'))
  self.assertFalse(m.get('automatic_upload',False))
  if m['publication_authorized']:
   self.assertTrue(m['release_ready']);self.assertEqual(m['publication']['tag'],'v'+m['version']);self.assertTrue(m['publication']['ai_assisted'])
  else:self.assertFalse(m['release_ready'])
 def test_original_objects_have_source(self):
  for n in ('scripts/oem_native_budget.c','scripts/preparation/oem-hooks.S','resources/preparation/oem-budget.o','resources/preparation/oem-hooks.o'):self.assertTrue((ROOT/n).is_file())
  self.assertTrue((ROOT/'resources/ui/ldf-samples.json').is_file())

@unittest.skipUnless(os.environ.get('MI_OWNER_INPUTS'),'requires private owner-input fixture, not distributed')
class OwnerPreparation(unittest.TestCase):
 def test_no_compiler_and_complete_recipe(self):
  from prepare_local_assets import prepare_directory,valid,inputs
  self.assertEqual(len(inputs()),25)
  with tempfile.TemporaryDirectory() as temp,patch('subprocess.run',side_effect=AssertionError('Unexpected compiler/device process')):
   cache=Path(temp)/'prepared';r=prepare_directory(Path(os.environ['MI_OWNER_INPUTS']),cache)
   self.assertTrue(r['ready']);self.assertFalse(r['device_written']);self.assertTrue(valid(cache))
   self.assertTrue((cache/'models/32u-2026/PTBCN1L_31_3F/HDR.ini').is_file())
   self.assertIn('<Param id="0"', (cache/'persistence/event.xml').read_text('utf-8'))
   self.assertTrue(prepare_directory(Path(os.environ['MI_OWNER_INPUTS']),cache)['reused'])
   with patch.object(local_asset_paths,'CACHE',cache):
    from firmware_tone import compare
    self.assertGreater(compare('32u-2026',5,3,25,10000)['hgig']['mapped_nits'],0)
   with patch('prepare_local_assets.generator_fingerprint',return_value='changed'):self.assertFalse(valid(cache))
   f=cache/'model/mdrv-test.elf';f.write_bytes(b'corrupt');self.assertFalse(valid(cache))

if __name__=='__main__':unittest.main(verbosity=2)
