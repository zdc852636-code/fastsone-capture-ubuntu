"""Import the application only inside the runner's private X11 desktop."""
import os
from pathlib import Path
import sys

if os.environ.get('LW_TEST_ISOLATED') != '1':
    raise RuntimeError('请使用 /usr/bin/python3 tests/run.py，在独立测试桌面运行。')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import capture
capture.AUTOSTART=Path.cwd()/'work/autostart.desktop'


def pump(seconds=.15):
    import time
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        while capture.Gtk.events_pending():capture.Gtk.main_iteration_do(False)
        time.sleep(.004)
