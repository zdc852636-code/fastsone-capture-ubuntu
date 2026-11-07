#!/usr/bin/python3
"""Install for the current user, without root access."""
from pathlib import Path
import fcntl
import os
import shutil
import subprocess
import sys
import time

source = Path(__file__).resolve().parent
destination = Path.home() / '.local/share/fastsone-capture-lw-ubuntu'
if source != destination:
    destination.mkdir(parents=True, exist_ok=True)
    # Copy dependencies before the entry point; existing processes retain their session.
    for name in ('customize.py', 'storage.py', 'ocr.py', 'classic_ui.py', 'workspace.py', 'workflows.py', 'panel.py', 'README.txt', 'LICENSE', 'capture.py'):
        staged=destination/('.'+name+'.new')
        shutil.copy2(source/name,staged); os.replace(staged,destination/name)
    if (source/'vendor/gi').is_dir():
        shutil.copytree(source/'vendor', destination/'vendor', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
subprocess.run(['/usr/bin/python3', str(destination / 'capture.py'), '--install'], check=True)
logdir = Path.home() / '.config/fastsone-capture-lw-ubuntu'
logdir.mkdir(parents=True, exist_ok=True)
# Keep an existing editing session alive; installing must never discard screenshots.
with (logdir / 'app.lock').open('a') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('新版已安装。旧版仍在运行，请保存截图并退出，再从应用菜单启动新版。')
        sys.exit(0)
    fcntl.flock(lock, fcntl.LOCK_UN)
logpath = logdir / 'application.log'
if logpath.exists() and logpath.stat().st_size > 2_000_000:
    logpath.replace(logdir / 'application.previous.log')
with logpath.open('a') as log:
    child = subprocess.Popen(['/usr/bin/python3', str(destination / 'capture.py')],
                             stdout=log, stderr=log, start_new_session=True)
time.sleep(1)
if child.poll() not in (None, 0):
    sys.exit('安装完成，但启动失败。请查看：' + str(logpath))
print('安装位置：' + str(destination))
print('首次安装默认启用登录后自动启动；升级保留原有设置。快捷键：F3 / Ctrl+Alt+A 区域截图，F4 截图识字。')
