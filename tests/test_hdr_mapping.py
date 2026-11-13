"""Owned HDR mapping protocol and compiled ARM code; no ADB/device access."""
from pathlib import Path
import ast,importlib.util,json,os,struct,sys,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lab'))

class ProtocolTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('mapping_under_test',ROOT/'lab/hdr_mapping.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_reference_budget_has_unity_gains(self):
        m=self.module();config=dict(sf=[255]*5,alpha=list(range(8)),dc=8,blend=8,dynamic=1)
        for budget in (0,24):
            with patch.dict(sys.modules,{'device_models':SimpleNamespace(activate=lambda *args:None),'ldf_response':SimpleNamespace()}):value=m.compute(config,3,budget)
            self.assertEqual(value['scales'],[65535]*11)
            self.assertEqual(value['enabled'],budget>0);self.assertEqual(len(m.packet(value,7).split(',')),15)
    def test_packet_shape_is_explicit(self):
        m=self.module()
        for value in [dict(version=0,scales=[1]*11),dict(version=1,scales=[1]*10)]:
            with self.assertRaises(ValueError):m.packet(value,1)

class CouplingTests(unittest.TestCase):
    def bridge(self):
        source=(ROOT/'lab/portable_server.py').read_text('utf8');tree=ast.parse(source)
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='read_budget')
        worker=SimpleNamespace(call=Mock(return_value=dict(version=1,enabled=True,level=3,tone=5,scales=[65535]*11)))
        budget=SimpleNamespace(sample=Mock(return_value=dict(status='live-driver',tick=1,frames=1,hdr_mode_actual=5,level=3,hdr_active=1)))
        ns=dict(abl_packet=lambda config,generation:json.dumps(config),model_worker=worker,budget=budget,time=time)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-read-budget','exec'),ns)
        b=type('Bridge',(),dict(read_budget=ns['read_budget']))();b.budget_value=31;b.native_abl={'e0':999};b.factory_budget=True
        b.comparison_config={'sf':[128]*5};b.draft={'sf':[100]*5};b.backlight_level=3;b.tone=5;b.model_id='32u-2026';b.telemetry={};b.folder=ROOT/'tmp';b.budget_active=True
        return b,worker,budget
    def test_mapping_uses_applied_budget_and_saved_comparison_not_draft(self):
        b,worker,budget=self.bridge();b.read_budget(20,True,True,config={'e0':123})
        payload=worker.call.call_args.kwargs;self.assertEqual(payload['budget'],20);self.assertEqual(payload['config'],{'sf':[128]*5})
        self.assertEqual(json.loads(budget.sample.call_args.args[3]),{'e0':123})
    def test_failed_mapping_stops_the_existing_heartbeat_as_well_as_lease(self):
        b,worker,budget=self.bridge();budget.sample.return_value['hdr_active']=0
        with self.assertRaisesRegex(RuntimeError,'HDR映射'):b.read_budget(20,True,True)
        self.assertFalse(b.budget_active);self.assertFalse(budget.sample.call_args.args[2])
    def test_read_only_sampling_does_not_recompute_mapping(self):
        b,worker,budget=self.bridge();b.read_budget();worker.call.assert_not_called();self.assertIsNone(budget.sample.call_args.args[4])

@unittest.skipUnless(os.name=='nt','Publisher ARM emulation uses the bundled Windows Unicorn library')
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(ROOT/'tools/predict-libs'))
        import io
        from elftools.elf.elffile import ELFFile
        from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
        from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6,UC_ARM64_REG_X30,UC_ARM64_REG_SP
        self.regs=[UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6];self.lr=UC_ARM64_REG_X30;self.sp=UC_ARM64_REG_SP
        elf=ELFFile(io.BytesIO((ROOT/'resources/preparation/oem-budget.o').read_bytes()));text=elf.get_section_by_name('.text').data()
        symbol=next(x for x in elf.get_section_by_name('.symtab').iter_symbols() if x.name=='mi_budget_post')
        self.pc=0x100000+symbol['st_value'];self.stop=0x13fff0;self.c=0x500000;self.buffer=0x600000;self.bss=0x700000;self.hdr=0x800000
        self.u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
        for address,size in [(0x100000,0x40000),(self.c,0x10000),(self.buffer,0x10000),(self.bss,0x100000),(self.hdr,0x10000),(0x900000,0x10000),(0xffffffc009bc6000,0x1000)]:self.u.mem_map(address,size)
        self.u.mem_write(0x100000,text);self.u.mem_write(0xffffffc009bc6980,struct.pack('<I',100))
        values=[0]*112
        for index,value in {0:41,4:1000,8:1,9:18288,10:37491600,11:600,12:9760,13:31243,14:37491600,15:20000,16:65535,23:1,24:1,44:3,56:1,57:1,60:2,61:5,62:3}.items():values[index]=value
        for i in range(11):values[80+i]=98303
        self.u.mem_write(self.c,struct.pack('<112I',*values));self.u.mem_write(self.c+200,struct.pack('<Q',self.bss));self.u.mem_write(self.c+216,struct.pack('<Q',self.hdr))
        self.u.mem_write(self.bss+0x104,b'\1');self.u.mem_write(self.bss+366348,struct.pack('<8H',*([24000]*8)));self.u.mem_write(self.buffer,struct.pack('<8H',*([24000]*8)))
        self.original=[2000,1800,1600,1200,1000,900,800,750,700,650,600]
        self.u.mem_write(self.hdr+200,struct.pack('<11I',*self.original));self.u.mem_write(self.hdr+340,struct.pack('<I',5));self.u.mem_write(self.hdr+336,struct.pack('<I',16));self.u.mem_write(self.hdr+176,b'\1');self.floor=2000<<16|3000;self.u.mem_write(self.hdr+188,struct.pack('<I',self.floor))
    def word(self,index,value=None):
        if value is not None:self.u.mem_write(self.c+4*index,struct.pack('<I',value))
        return struct.unpack('<I',self.u.mem_read(self.c+4*index,4))[0]
    def call(self,gain=65535):
        self.word(16,gain);self.u.reg_write(self.sp,0x90ff00);self.u.reg_write(self.lr,self.stop)
        for reg,value in zip(self.regs,[self.c,self.buffer,8,40000,24000,1000,3]):self.u.reg_write(reg,value)
        self.u.emu_start(self.pc,self.stop,count=100000)
        return list(struct.unpack('<11I',self.u.mem_read(self.hdr+200,44)))
    def test_applied_frame_gain_not_next_gain_controls_capabilities(self):
        peak=self.call();self.assertEqual(peak,[v*98303//65535 for v in self.original]);self.assertEqual(self.word(58),1)
        dim=self.call(38360);self.assertEqual(dim,[max(100,v*98303//65535*38360//65535) for v in self.original]);self.assertEqual(self.word(108),38360)
        self.assertEqual(self.call(),peak)
    def test_expired_lease_restores_anchors_floor_and_peak_filter(self):
        self.call(38360);self.word(4,0);self.assertEqual(self.call(),self.original);self.assertEqual(self.word(58),0)
        self.assertEqual(bytes(self.u.mem_read(self.hdr+176,1)),b'\1');self.assertEqual(struct.unpack('<I',self.u.mem_read(self.hdr+188,4))[0],self.floor)
    def test_another_tone_mode_does_not_receive_the_saved_mapping(self):
        self.u.mem_write(self.hdr+340,struct.pack('<I',1));self.assertEqual(self.call(),self.original);self.assertEqual(self.word(58),0)

if __name__=='__main__':unittest.main(verbosity=2)
