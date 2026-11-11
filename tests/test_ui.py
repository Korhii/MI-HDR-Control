"""UI-only regressions. No ADB or device writes."""
from pathlib import Path
import hashlib,json,re,struct,unittest
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
class Nodes(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])

class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=(ROOT/'lab/portable.html').read_text(encoding='utf-8')
        cls.contract=json.loads((ROOT/'resources/ui/control-contract.json').read_text(encoding='utf-8'))
    def test_original_ids_once(self):
        ids=Nodes(self.text).ids
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(set(self.contract['ids']).issubset(ids))
    def test_controller_script_matches_release_contract(self):
        script=re.search(r'<script>(.*?)</script>',self.text,re.S).group(1)
        self.assertEqual(hashlib.sha256(script.encode()).hexdigest(),self.contract['controller_script_sha256'])
    def test_six_domains_after_removed_module(self):
        self.assertEqual(re.findall(r'<button[^>]*data-page="([^"]+)"',self.text),['auto','budget','halo','pattern','sensors','save'])
        for domain in ('auto','budget','halo','pattern','sensors','save'):
            self.assertEqual(self.text.count('data-panel="'+domain+'"'),1)
    def test_eva_is_more_than_accent_colors(self):
        css=(ROOT/'lab/eva.css').read_text(encoding='utf-8')
        for item in ('NotoSerifSC-VF.ttf','RobotoCondensed-VF.ttf','ShareTechMono-Regular.ttf','--unit-panel','repeating-linear-gradient','text-shadow','eva-chapter','risk-dialog'):
            self.assertIn(item,css)
        self.assertTrue((ROOT/'resources/fonts/NotoSerifSC-OFL.txt').exists())
    def test_achromatic_surfaces(self):
        for value in re.findall(r'background(?:-color)?:([^;}]+)',self.text):
            for color in re.findall(r'#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b',value):
                if len(color)==3:color=''.join(c*2 for c in color)
                self.assertEqual(color[:2],color[2:4]);self.assertEqual(color[2:4],color[4:6])
    def test_dark_palette(self):
        self.assertIn('--scheme:dark',self.text)
        self.assertIn('--scheme:light',self.text)
        self.assertIn('id="themeChoice"',self.text)
        self.assertIn('--c-f6f6f6:#0c0c0c',self.text)
        self.assertIn('.card{background:var(--c-fff)',self.text)
        self.assertIn('.sidebar{position:fixed',self.text)
    def test_icon_sizes(self):
        data=(ROOT/'resources/ui/app.ico').read_bytes()
        self.assertEqual(struct.unpack_from('<HHH',data),(0,1,7))
        self.assertEqual([data[6+i*16] or 256 for i in range(7)],[16,24,32,48,64,128,256])
        self.assertEqual((ROOT/'MI HDR Control.exe').read_bytes()[:2],b'MZ')

if __name__=='__main__':unittest.main()
