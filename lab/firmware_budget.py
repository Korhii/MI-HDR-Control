"""Execute the extracted ARM64 algorithm offline; never contact the monitor."""
import argparse
import json
import math
from pathlib import Path
import statistics
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/predict-libs'))
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *

from local_asset_paths import model_directory
IMAGE = model_directory()/'ldm113'
MANIFEST = json.loads((IMAGE/'manifest.json').read_text(encoding='utf-8'))
FUNCTIONS = {f['name']: f['address'] for f in MANIFEST['functions']}
SYMBOLS = MANIFEST['symbols']
STACK, BUFFER, TLS, RETURN = 0x60000000, 0x61000000, 0x62000000, 0x63000000
PATCH = 0x1a57dc
WIDTH, HEIGHT = 48, 24
N = WIDTH*HEIGHT


class Algorithm:
    def __init__(self, level=3, budget=None, source_format=1, device_type=113):
        self.u = u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        u.mem_map(0x100000, 0xb0000)
        for block in MANIFEST['blocks']:
            if block['start'] >= 0x100000 and block['file']:
                u.mem_write(block['start'], (IMAGE/block['file']).read_bytes())
        for address, size in [(STACK, 0x20000), (BUFFER, 0x10000), (TLS, 0x1000), (RETURN, 0x1000)]:
            u.mem_map(address, size)
        u.reg_write(UC_ARM64_REG_SP_EL0, TLS)
        u.cpr_write(3, 0, 1, 0, 2, 3 << 20)
        self.external = {f['address']:f['name'] for f in MANIFEST['functions'] if 0x1a9000 <= f['address'] < 0x1aa000}
        u.hook_add(UC_HOOK_CODE, self.host_call, begin=0x1a9000, end=0x1a9fff)
        if budget is not None:
            original = bytes(u.mem_read(PATCH, 4))
            if original != bytes.fromhex('09054079'):
                raise ValueError('HIGH-only patch point changed: '+original.hex())
            u.mem_write(PATCH, struct.pack('<I', 0x52800009 | (budget << 5)))
        if device_type not in (112,113):raise ValueError('Unsupported 2026 LED type')
        self.call('LED_Customized_init_bcon_mini_monitor_pm2u_dc', device_type)
        for name,value in [('gu8SourceFormat',source_format),('gu8LdLevel',level),('gu8CusBoost',0),('gu8TFSelect',0)]:
            u.mem_write(SYMBOLS[name], bytes([value]))

    def host_call(self, u, address, size, data):
        name = self.external.get(address)
        args = [u.reg_read(UC_ARM64_REG_X0+i) for i in range(3)]
        result = 0
        if name == 'memset':
            u.mem_write(args[0], bytes([args[1]&255])*args[2])
            result = args[0]
        elif name == 'memcpy':
            u.mem_write(args[0], bytes(u.mem_read(args[1], args[2])))
            result = args[0]
        elif name == 'ktime_get_raw_ts64':
            u.mem_write(args[0], bytes(16))
        elif name not in ('msleep','_printk','__cfi_slowpath_diag'):
            raise RuntimeError('Unmodelled external call: '+str(name)+' at '+hex(address))
        u.reg_write(UC_ARM64_REG_X0, result)
        u.reg_write(UC_ARM64_REG_PC, u.reg_read(UC_ARM64_REG_X30))

    def call(self, name, *args):
        u = self.u
        for index in range(8):
            u.reg_write(UC_ARM64_REG_X0+index, args[index] if index < len(args) else 0)
        u.reg_write(UC_ARM64_REG_SP, STACK+0x10000)
        u.reg_write(UC_ARM64_REG_X18, STACK+0x18000)
        u.reg_write(UC_ARM64_REG_X30, RETURN)
        u.emu_start(FUNCTIONS[name], RETURN, count=2000000)
        if u.reg_read(UC_ARM64_REG_PC) != RETURN:
            raise RuntimeError('Offline instruction limit reached')

    def frame(self, source):
        self.u.mem_write(BUFFER, struct.pack('<'+str(N)+'H', *source))
        self.call('LED_MCU_Common_BoostInsertToAlgo_xiaomi_monitor_pm2u_dc', BUFFER, WIDTH, HEIGHT)
        values = struct.unpack('<'+str(N)+'H', self.u.mem_read(BUFFER,N*2))
        info = struct.unpack('<6I',self.u.mem_read(SYMBOLS['bCusHdrInfo'],24))
        return {'output_mean':statistics.mean(values),'output_max':max(values),'output_min':min(values),
                'apl_raw':info[0],'spi_raw':info[1],'window_raw':info[2],'level':info[3]}


def source_for(fraction):
    width = max(1,round(WIDTH*math.sqrt(fraction)))
    height = max(1,round(HEIGHT*math.sqrt(fraction)))
    left,top = (WIDTH-width)//2,(HEIGHT-height)//2
    return [65535 if left<=x<left+width and top<=y<top+height else 0 for y in range(HEIGHT) for x in range(WIDTH)]


