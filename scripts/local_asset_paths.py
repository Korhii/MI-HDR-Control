"""Owner-derived code and configuration stay in this portable instance's private cache."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'state/prepared/beekeeper-os3.0.120-v17'
def generator_fingerprint():
    files=[ROOT/'scripts'/n for n in ('local_asset_paths.py','prepare_local_assets.py','build_local_models.py','build_local_adaptive.py','build_local_oem.py')]
    files+=sorted((ROOT/'resources/preparation').glob('*'))
    return hashlib.sha256(b''.join(f.read_bytes() for f in files if f.is_file())).hexdigest()
def prepared():
    marker=CACHE/'complete.json'
    return marker.is_file() and json.loads(marker.read_text('utf-8')).get('generator')==generator_fingerprint()
def model_directory():return CACHE/'model' if prepared() else ROOT/'resources/model'
def models_directory():return CACHE/'models' if prepared() else ROOT/'resources/models'
def budget_module():return CACHE/'module/mi-oem-runtime.ko' if prepared() else ROOT/'tools/mi-oem-runtime.ko'
def budget_manifest():return CACHE/'module/budget-relocation.json' if prepared() else ROOT/'resources/budget-relocation.json'
def firmware_directory():return CACHE/'firmware' if prepared() else ROOT/'resources/firmware'
def persistence_xml(name):return CACHE/'persistence'/name if prepared() else ROOT/'resources/persistence'/name
def status():
    ready=budget_module().is_file() and (model_directory()/'mdrv-test.elf').is_file() and (model_directory()/'adaptive-hdr/adaptive.elf').is_file()
    return dict(ready=ready,locally_prepared=prepared(),message='本机组件已准备' if ready else '请先连接受支持的显示器，读取原厂文件并在本机准备组件')
def require_ready():
    if not status()['ready']:raise ValueError(status()['message'])
