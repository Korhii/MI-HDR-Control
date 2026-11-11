"""Compatibility entry: use explicit source, output and version arguments."""
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[1]
if len(sys.argv)==2:
    raise SystemExit('Use release-tools/release.py prepare --source SOURCE --output OUTPUT --version VERSION')
runpy.run_path(str(root/'release-tools/release.py'),run_name='__main__')
