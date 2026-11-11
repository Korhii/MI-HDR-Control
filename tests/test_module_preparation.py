"""File-only relocation checks; no connection or device writes."""
from pathlib import Path
import json,struct,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_budget_module import prepare
from local_asset_paths import budget_module,budget_manifest


class ModulePreparationTests(unittest.TestCase):
    def setUp(self):
        if not budget_module().is_file():self.skipTest('Owner-local firmware preparation required; no OEM module is distributed')
        self.source=budget_module().read_bytes()
        self.manifest=json.loads(budget_manifest().read_text(encoding='utf-8'))
        self.text=0xffffffc003454000
    def test_each_address_slot(self):
        bases=dict(text=self.text,bss=self.text+0x3c000,data=self.text+0x98060)
        result=prepare(self.source,self.manifest,**bases)
        self.assertEqual(len(self.manifest['entries']),15)
        self.assertEqual(len(result),len(self.source))
        for slot in self.manifest['entries']:
            self.assertEqual(struct.unpack_from('<Q',result,slot['offset'])[0],bases[slot['region']]+slot['addend'])
    def test_wrong_template_rejected(self):
        with self.assertRaises(ValueError):prepare(self.source[:-1],self.manifest,self.text,self.text+0x3c000,self.text+0x98060)
    def test_wrong_layout_rejected(self):
        with self.assertRaises(ValueError):prepare(self.source,self.manifest,self.text,self.text+0x3d000,self.text+0x98060)

if __name__=='__main__':unittest.main()
