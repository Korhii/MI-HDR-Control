"""Focused checks for the illustrated 0.9.26 documentation; no ADB or device writes."""
from pathlib import Path
import hashlib,json,re,struct,unittest,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

class Documentation(unittest.TestCase):
 def test_confirmed_license_and_real_monitor_route(self):
  meta=json.loads((ROOT/'release-meta.json').read_text('utf-8'))
  self.assertEqual(meta['pending_decisions'],[]);self.assertEqual(meta['documentation_gaps'],[])
  self.assertFalse(meta.get('automatic_upload',False))
  if meta['publication_authorized']:
   self.assertTrue(meta['release_ready']);self.assertIn('repository',meta['publication'])
  else:self.assertFalse(meta['release_ready'])
  self.assertEqual(meta['confirmed_decisions']['program_license'],'GPL-2.0-only')
  self.assertEqual((ROOT/'LICENSE').read_text('utf-8'),(ROOT/'LICENSES/GPL-2.0-only.txt').read_text('utf-8'))
  p=json.loads((ROOT/'docs/assets/screenshots/provenance.json').read_text('utf-8'))
  self.assertTrue(p['monitor_adb_route_verified']);self.assertTrue(p['monitor_about_verified']);self.assertFalse(p['developer_options_required'])
  self.assertEqual(len(p['monitor_screenshots']),4)
  for row in p['monitor_screenshots']:
   self.assertFalse(row['generative_editing']);self.assertTrue(row['pixels_match_source_outside_masks'])
   self.assertEqual(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['sha256'])
  for lang in ('zh-CN','en'):
   text=(ROOT/f'docs/guide.{lang}.md').read_text('utf-8')
   for row in p['monitor_screenshots']:self.assertIn(Path(row['path']).name,text)
   self.assertIn('ADB调试',text);self.assertNotIn('5–7',text)

 def test_paired_documents_and_templates(self):
  names=['README.md','README.en.md']+[f'docs/{stem}.{lang}.md' for stem in ('guide','modules','RESEARCH','SAFETY','LEGAL','THEME_REVIEW','RELEASING','VALIDATION') for lang in ('zh-CN','en')]
  version=json.loads((ROOT/'release-meta.json').read_text('utf-8'))['version']
  for name in names:
   with self.subTest(name=name):
    rendered=(ROOT/'release-tools/templates'/(name+'.template')).read_text('utf-8').replace('{{PUBLIC_VERSION}}',version).replace('{{SOURCE_VERSION}}',version.split('-')[0])
    self.assertEqual((ROOT/name).read_text('utf-8'),rendered)

 def test_language_and_publication_decisions(self):
  meta=json.loads((ROOT/'release-meta.json').read_text('utf-8'));c=meta['confirmed_decisions']
  self.assertFalse(c['english_gui_required']);self.assertEqual(c['readme_languages'],['zh-CN','en'])
  self.assertEqual(c['credit'],'MI HDR Control contributors');self.assertEqual(c['release_level'],'experimental-preview')
  self.assertEqual(c['original_documentation_license'],'CC-BY-NC-SA-4.0')
  if meta['pending_decisions']:self.assertFalse(meta['release_ready'])
  for name in ('docs/SAFETY.zh-CN.md','docs/SAFETY.en.md'):
   s=(ROOT/name).read_text('utf-8')
   for removed in ('依法不得排除、限制的责任不受本声明影响','免责声明不替代第三方授权','This disclaimer does not replace third-party permission','Liability that cannot lawfully be excluded'):
    self.assertNotIn(removed,s)

 def test_research_arrays_and_observed_results(self):
  d=json.loads((ROOT/'docs/assets/research/model-experiments.json').read_text('utf-8'))
  self.assertEqual([r['lit_cells'] for r in d['sf_rings']['cases']],[1,9,17,25,33,41])
  self.assertEqual([r['edge_raw'] for r in d['sf_strength']['cases']],[65280,48896,32512,16128,3840,0])
  self.assertEqual([sum(v!=0 for v in r['delta']) for r in d['same_area_geometry']],[0,1152])
  self.assertTrue(all(abs(r['white_area_percent']-10)<1e-10 for r in d['same_area_geometry']))
  self.assertEqual(max(d['same_area_geometry'][1]['delta']),47872)
  full=d['budget_curves']['cases'][0]['rows'][-1]
  self.assertEqual([v['peak_raw'] for v in full['values']],[12191,18287,31242])
  for name,digest in d['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)

 def test_figure_pairs_and_actual_capture_provenance(self):
  for name in ('sf-rings','sf-strength','alpha-bins','alpha-geometry','budget-curves','driver-stages'):
   for lang in ('zh','en'):
    self.assertIn('<svg ',(ROOT/f'docs/assets/research/{name}.{lang}.svg').read_text('utf-8'))
    self.assertTrue((ROOT/f'docs/assets/research/{name}.{lang}.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
  p=json.loads((ROOT/'docs/assets/screenshots/provenance.json').read_text('utf-8'))
  self.assertEqual(len(p['screenshots']),21)
  self.assertEqual(p['source_version'],'0.9.26')
  for row in p['screenshots']:
   self.assertFalse(row['device_connected']);self.assertFalse(row['synthetic_success'])
   self.assertEqual((row['theme'],row['unit']),('dark','mono'))
   self.assertFalse(row['generative_editing']);self.assertEqual(row['format'],'PNG')
   data=(ROOT/row['path']).read_bytes();self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
   self.assertEqual(struct.unpack('>II',data[16:24]),(row['pixel_width'],row['pixel_height']))
   self.assertEqual((row['pixel_width'],row['pixel_height']),(1000,1414))
   self.assertEqual(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['sha256'])

 def test_novice_steps_and_research_on_homepage(self):
  for lang in ('zh-CN','en'):
   guide=(ROOT/f'docs/guide.{lang}.md').read_text('utf-8')
   for anchor in ('prepare','adb','first-run','first-adjustment','pattern','save-restore','persistent'):
    self.assertIn(f'id="{anchor}"',guide)
   modules=(ROOT/f'docs/modules.{lang}.md').read_text('utf-8')
   for anchor in ('auto','budget','halo','pattern','readback','save-restore','restore-scope'):
    self.assertIn(f'id="{anchor}"',modules)
   headings=re.findall(r'^## (\d\d) /',modules,re.M)
   self.assertEqual(headings,['00','01','02','04','05','06'])
   self.assertIn(f'modules.{lang}.md',guide)
   for label in ('保存选择','选择配置','应用统一亮度设置','永久保存到显示器','恢复设备出厂调光'):
    self.assertIn(label,guide)
  for name in ('README.md','README.en.md'):
   text=(ROOT/name).read_text('utf-8')
   for figure in ('sf-strength','alpha-geometry','budget-curves','driver-stages'):self.assertIn(figure,text)
   self.assertIn('10000',text);self.assertIn('EOTF',text)

 def test_alpha_legend_counts_and_bars_match_arrays(self):
  d=json.loads((ROOT/'docs/assets/research/model-experiments.json').read_text('utf-8'))
  for lang in ('zh','en'):
   svg=ET.parse(ROOT/f'docs/assets/research/alpha-geometry.{lang}.svg').getroot()
   meta=json.loads(svg.find("{http://www.w3.org/2000/svg}metadata").text)
   self.assertEqual(meta['legend_bins'],[0,4,7])
   for case,groups in zip(d['same_area_geometry'],meta['groups']):
    self.assertEqual(sum(g['count'] for g in groups),1152)
    for g in groups:
     idx=[i for i,k in enumerate(case['bins']) if k==g['bin']]
     self.assertEqual(len(idx),g['count'])
     self.assertEqual({case['factory_output'][i] for i in idx},{g['before']})
     self.assertEqual({case['alpha0_16_output'][i] for i in idx},{g['after']})
   self.assertNotIn('α3',''.join(svg.itertext()))
   self.assertEqual({(g['bin'],g['count'],g['before'],g['after']) for g in meta['groups'][0]},
                    {(-1,1024,0,0),(4,32,57088,57088),(7,96,65280,65280)})
   self.assertEqual(meta['groups'][1][0]['after']-meta['groups'][1][0]['before'],47872)

 def test_theme_gallery_is_complete_and_at_homepage_end(self):
  p=json.loads((ROOT/'docs/assets/screenshots/provenance.json').read_text('utf-8'))
  self.assertEqual({r['unit'] for r in p['theme_screenshots']},{'mono','unit01','unit00','unit02','unit08','mark06'})
  for row in p['theme_screenshots']:
   self.assertEqual(row['theme'],'dark')
   self.assertTrue(row['device_connected']);self.assertFalse(row['live_debug']);self.assertEqual(row['title'],'APL与ABL控制')
   self.assertEqual(row['scroll_y'],0);self.assertEqual((row['pixel_width'],row['pixel_height']),(1770,2908))
   self.assertEqual(row['privacy_edit']['pixels_outside_mask_changed'],0)
   self.assertEqual(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['sha256'])
  for name in ('README.md','README.en.md'):
   text=(ROOT/name).read_text('utf-8');gallery=text[text.index('<a id="themes">'):]
   for row in p['theme_screenshots']:self.assertIn(row['path'],gallery)
   self.assertNotIn('docs/assets/themes/',text[:text.index('<a id="themes">')])

 def test_tutorials_only_reference_current_mono_app_images(self):
  p=json.loads((ROOT/'docs/assets/screenshots/provenance.json').read_text('utf-8'))
  paths={Path(r['path']).name for r in p['screenshots']}
  for lang in ('zh-CN','en'):
   for stem in ('guide','modules'):
    text=(ROOT/f'docs/{stem}.{lang}.md').read_text('utf-8')
    images=re.findall(r'!\[[^\]]*\]\(assets/screenshots/(app-[^)]+)\)',text)
    self.assertTrue(images)
    self.assertTrue(all(name in paths and name.endswith('.png') for name in images))
    self.assertNotIn('assets/themes/',text)

if __name__=='__main__':unittest.main(verbosity=2)
