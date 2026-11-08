#!/usr/bin/python3
"""Run desktop regressions on a private Xvfb/Openbox display; clean all outputs."""
import argparse
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xvfb',default=shutil.which('Xvfb'))
    parser.add_argument('--openbox',default=shutil.which('openbox'))
    parser.add_argument('--runtime-root',type=Path,help='Optional extracted Ubuntu package tree')
    parser.add_argument('--previews',type=Path,help='Keep three synthetic UI previews in this directory')
    parser.add_argument('tests',nargs='*',help='Optional test file names')
    args=parser.parse_args()
    if not args.xvfb or not args.openbox:sys.exit('需要 Xvfb 和 Openbox：sudo apt install xvfb openbox')
    testdir=Path(__file__).resolve().parent
    names=args.tests or ['test_storage.py','test_edges.py','test_workflows.py','test_toolbar.py','test_input.py','test_ocr.py','test_ocr_quality.py','test_customization.py', 'test_clipboard_history.py']
    for name in names:
        if '/' in name or not (testdir/name).is_file():sys.exit('Invalid test name: '+name)
    processes=[]
    with tempfile.TemporaryDirectory(prefix='lw-capture-tests-') as folder:
        root=Path(folder);(root/'work').mkdir()
        env=os.environ.copy()
        env.update(XDG_CONFIG_HOME=str(root/'config'),XDG_CACHE_HOME=str(root/'cache'),
                   XDG_DATA_HOME=str(root/'data'),GTK_USE_PORTAL='0',GSETTINGS_BACKEND='memory',
                   GTK_IM_MODULE='gtk-im-context-simple',NO_AT_BRIDGE='1',XDG_SESSION_TYPE='x11',
                   PYTHONDONTWRITEBYTECODE='1',LW_TEST_ISOLATED='1')
        env.pop('WAYLAND_DISPLAY',None)
        if args.runtime_root:
            runtime=args.runtime_root.resolve()
            env['LD_LIBRARY_PATH']=str(runtime/'usr/lib/x86_64-linux-gnu')
            env['XDG_DATA_DIRS']=str(runtime/'usr/share')+':/usr/share'
        read_fd,write_fd=os.pipe()
        try:
            with (root/'xvfb.log').open('w') as log:
                server=subprocess.Popen([str(Path(args.xvfb).resolve()),'-displayfd',str(write_fd),
                    '-screen','0','1440x2560x24','-nolisten','tcp'],pass_fds=(write_fd,),stdout=log,stderr=log,env=env)
                processes.append(server)
            os.close(write_fd);write_fd=None
            if not select.select([read_fd],[],[],10)[0]:raise RuntimeError('Xvfb did not start: '+(root/'xvfb.log').read_text())
            display=os.read(read_fd,128).decode().strip()
            if not display.isdigit():raise RuntimeError('Invalid private display: '+display)
            env['DISPLAY']=':'+display
            print('Private test desktop ready',flush=True)
            command=[str(Path(args.openbox).resolve()),'--sm-disable']
            if args.runtime_root:command+=['--config-file',str(runtime/'etc/xdg/openbox/rc.xml')]
            with (root/'openbox.log').open('w') as log:
                processes.append(subprocess.Popen(command,env=env,cwd=root,stdout=log,stderr=log))
            time.sleep(.6)
            if processes[-1].poll() is not None:raise RuntimeError((root/'openbox.log').read_text())
            for name in names:
                print('\nRUN '+name,flush=True)
                result=subprocess.run([sys.executable,str(testdir/name)],env=env,cwd=root,timeout=100)
                if result.returncode:raise RuntimeError(name+' failed')
            if args.previews:
                destination=args.previews.resolve();destination.mkdir(parents=True,exist_ok=True)
                for name,title in [('v22-panel-preview.png','工具栏预览.png'),('v2-editor-preview.png','编辑器预览.png'),('v2-draw-preview.png','绘图模式预览.png')]:
                    if (root/'work'/name).exists():shutil.copy2(root/'work'/name,destination/title)
            print('\nALL TEST SUITES PASSED',flush=True)
        finally:
            os.close(read_fd)
            if write_fd is not None:os.close(write_fd)
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
