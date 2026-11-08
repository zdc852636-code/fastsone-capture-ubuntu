"""Test the actual CopyQ service using synthetic data, a private desktop and bus."""
import os
from pathlib import Path
import subprocess
import sys
import time

if os.environ.get('LW_TEST_ISOLATED') != '1':
    raise SystemExit('使用 tests/run.py test_clipboard_history.py 在独立桌面运行。')
if '--private-bus' not in sys.argv:
    env = os.environ.copy()
    env.pop('SESSION_MANAGER', None)
    for var, name in [('XDG_CONFIG_HOME','history-config'),('XDG_DATA_HOME','history-data'),
                      ('XDG_RUNTIME_DIR','history-runtime')]:
        directory = Path.cwd()/name
        directory.mkdir(mode=0o700, exist_ok=True)
        env[var] = str(directory)
    sys.exit(subprocess.call(['/usr/bin/dbus-run-session','--',sys.executable,'-B',__file__,'--private-bus'],env=env))

from test_support import capture as m, pump
from clipboard_history import CopyQHistory, HistoryApplication
store = CopyQHistory()
assert store.executable, '请安装 copyq'
clip = m.Gtk.Clipboard.get(m.Gdk.SELECTION_CLIPBOARD)


def wait_until(condition, timeout=8):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        pump(.05)
        if condition():
            return
    raise AssertionError('等待测试状态超时')


def read_text():
    return store.run('print(str(clipboard()))').decode()


def fill():
    store.run("tab(str(config('clipboard_tab')));for(var i=0;i<105;i++) add('sample-'+i);")


def cli_visible():
    tree=subprocess.check_output(['xwininfo','-root','-tree'],text=True)
    return '剪贴板历史 · '+m.NAME in tree


try:
    rows, recording, limit = store.entries()
    assert not rows and recording and limit==100,(len(rows),recording,limit)
    fill()
    rows=store.entries()[0]
    assert [r.label for r in rows]==['sample-'+str(i) for i in range(104,4,-1)]
    shifted=rows[18]
    stale=rows[-1]
    store.run("tab(str(config('clipboard_tab'))); add('number-106');")
    try:
        store.restore(stale)
    except RuntimeError as error:
        assert '刷新' in str(error),str(error)
    else:
        raise AssertionError('Evicted item was restored')
    store.restore(shifted)
    assert read_text()==shifted.label
    print('PASS cap=100 and eviction, copying the intended item after a reorder',flush=True)

    store.run("tab(str(config('clipboard_tab'))); setItem(0, {'text/plain':'rich example','text/html':'<b>rich example</b>'});")
    rich=next(r for r in store.entries()[0] if r.label=='rich example')
    store.restore(rich)
    assert store.run("print(str(clipboard('text/html')))").decode()=='<b>rich example</b>'
    image=m.GdkPixbuf.Pixbuf.new(m.GdkPixbuf.Colorspace.RGB,False,8,64,32)
    image.fill(0x419accff)
    clip.set_image(image)
    wait_until(lambda: bool(store.entries()[0][0].image))
    stored=store.entries()[0][0]
    assert store.thumbnail(stored).get_width()==64
    clip.set_text('模拟关联设备收到的文字',-1)
    wait_until(lambda: store.entries()[0][0].label=='模拟关联设备收到的文字')
    incoming=store.entries()[0][0]
    store.restore(stored)
    assert clip.wait_for_image().get_width()==64
    assert store.entries()[1] and len(store.entries()[0])==100
    print('PASS system clipboard text, PNG preview and restore, and HTML preservation',flush=True)

    command=[sys.executable,'-B',str(m.ROOT/'capture.py'),'--clipboard-history']
    first=subprocess.Popen(command)
    wait_until(cli_visible)
    second=subprocess.Popen(command)
    wait_until(lambda: second.poll() is not None and first.poll() is not None)
    assert first.returncode==second.returncode==0
    print('PASS desktop shortcut CLI opens and closes the same Capture history window',flush=True)

    app=HistoryApplication()
    app.register(None)
    app.activate()
    win=app.get_windows()[0]
    wait_until(lambda: len(win.items)==100)
    win.search.set_text('关联设备')
    wait_until(lambda: len(win.model)==1)
    assert win.selected==incoming.identity
    win.copy_selected()
    wait_until(lambda: not app.get_windows())
    assert read_text()==incoming.label
    print('PASS native search, selection and copy to clipboard',flush=True)

    store.run("tab('Other');config('maxitems',150);for(var i=0;i<105;i++) add('other-'+i);")
    assert store.entries()[2]==150, 'Opening history silently truncated another existing tab'
    store.limit_history()
    assert store.entries()[2]==100
    assert store.run("tab('Other');print(count())")==b'100'
    before=[r.identity for r in store.entries()[0]]
    subprocess.run([store.executable,'exit'],check=True,timeout=5)
    time.sleep(.5)
    assert [r.identity for r in store.entries()[0]]==before
    print('PASS persistent real storage limit and restart recovery',flush=True)
finally:
    subprocess.run([store.executable,'exit'],capture_output=True,timeout=8)
