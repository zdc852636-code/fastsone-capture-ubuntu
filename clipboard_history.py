"""Capture's clipboard history window, backed by the user's CopyQ recording tab."""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
from PIL import Image

from app_info import NAME

LIMIT = 100
# History content is passed over pipes. Only a bounded preview leaves CopyQ during listing.
_RECORDING = "var dest=str(config('clipboard_tab')); tab(dest);"
# On a fresh setup adopt the limit immediately. Existing oversized tabs need an
# explicit choice because CopyQ applies this setting to every tab.
_LIMIT_IF_SAFE = """
if (Number(config('maxitems'))!==100) {
    var names=tab(), fits=true;
    for (var t=0;t<names.length;t++) {tab(names[t]); if(count()>100) {fits=false;break;}}
    if(fits) config('maxitems',100);
}
"""
_LIST = _LIMIT_IF_SAFE + _RECORDING + """
var rows=[], n=Math.min(count(),100);
for (var i=0;i<n;i++) {
    var item=getItem(i), formats=Object.keys(item);
    var image=formats.filter(function(k){return k.indexOf('image/')===0;})[0] || '';
    var value=item['text/plain'] ? str(item['text/plain']).slice(0,2048) : '';
    var uri=item['text/uri-list'] ? str(item['text/uri-list']).slice(0,2048) : '';
    var label=value || uri || (image ? image+' · '+Math.ceil(item[image].length/1024)+' KiB' : '其他格式');
    rows.push([i,str(sha256sum(pack(item))),image?'图片':(uri?'文件':'文本'),label,image]);
}
print(JSON.stringify({rows:rows,monitoring:monitoring(),limit:Number(config('maxitems'))}));
"""
_LOOKUP = """
var item, candidate;
if (hint<count()) {
    candidate=getItem(hint);
    if (str(sha256sum(pack(candidate)))===wanted) item=candidate;
}
if (!item) for (var i=0;i<Math.min(count(),100);i++) {
    candidate=getItem(i);
    if (str(sha256sum(pack(candidate)))===wanted) {item=candidate;break;}
}
if (!item) throw new Error('STALE_ITEM');
"""
_COPY = """
var parts=[];
Object.keys(item).forEach(function(k){
    if (k.indexOf('application/x-copyq-')!==0) {parts.push(k);parts.push(item[k]);}
});
if (!parts.length) throw new Error('UNSUPPORTED_ITEM');
copy.apply(null,parts);
print('OK');
"""
_PREVIEW = """
var formats=['image/png','image/jpeg','image/webp','image/bmp'];
for(var i=0;i<formats.length;i++){
    var data=item[formats[i]];
    if(data && data.length<=8*1024*1024){print(str(toBase64(data)));break;}
}
"""


@dataclass(frozen=True)
class Entry:
    row: int
    identity: str
    kind: str
    label: str
    image: str


class CopyQHistory:
    def __init__(self, executable=None):
        personal = Path.home()/'.local/bin/copyq'
        self.executable = executable or shutil.which('copyq') or (str(personal) if personal.is_file() else None)

    def run(self, script):
        if not self.executable:
            raise RuntimeError('请安装剪贴板组件：sudo apt install copyq')
        try:
            command = [self.executable, '--', 'eval', script]
            result = subprocess.run(command, capture_output=True, timeout=25)
            if result.returncode and b'Cannot connect to server' in result.stderr:
                # A detached server must not inherit the client's output pipes.
                subprocess.Popen([self.executable], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                deadline = time.monotonic() + 6
                while time.monotonic() < deadline:
                    check = subprocess.run([self.executable, 'monitoring'], capture_output=True, timeout=3)
                    if check.returncode == 0:
                        result = subprocess.run(command, capture_output=True, timeout=25)
                        break
                    time.sleep(.15)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError('CopyQ 未响应，请确认它可以启动后再刷新。') from error
        if result.returncode:
            if b'STALE_ITEM' in result.stderr:
                raise RuntimeError('这条记录已被移出历史，请刷新后重新选择。')
            if b'UNSUPPORTED_ITEM' in result.stderr:
                raise RuntimeError('此记录需要在 CopyQ 中打开。')
            raise RuntimeError('无法访问 CopyQ 历史，请确认它正在当前桌面运行。')
        return result.stdout

    def entries(self):
        data = json.loads(self.run(_LIST))
        return [Entry(*row) for row in data['rows']], data['monitoring'], data['limit']

    def limit_history(self):
        self.run("config('maxitems', 100); if(Number(config('maxitems'))!==100) throw new Error('LIMIT');")

    def lookup(self, entry):
        if not re.fullmatch('[0-9a-f]{64}', entry.identity) or not 0 <= entry.row < LIMIT:
            raise ValueError('无效的历史记录')
        return _RECORDING + f"var wanted='{entry.identity}',hint={entry.row};" + _LOOKUP

    def restore(self, entry):
        if self.run(self.lookup(entry) + _COPY).strip() != b'OK':
            raise RuntimeError('复制未完成，请重试。')

    def thumbnail(self, entry):
        encoded = self.run(self.lookup(entry) + _PREVIEW)
        if not encoded:
            return None
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            if image.width * image.height > 32_000_000:
                return None
            image.thumbnail((420, 120))
            thumb = image.convert('RGBA')
            return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(thumb.tobytes()), GdkPixbuf.Colorspace.RGB,
                                                  True, 8, thumb.width, thumb.height, thumb.width*4)


def start_recording_backend():
    store = CopyQHistory()
    if store.executable:
        def connect():
            try:
                store.run(_LIMIT_IF_SAFE)
            except RuntimeError:
                # Interactive access reports service errors and allows retrying.
                pass
        threading.Thread(target=connect, name='connect-clipboard', daemon=True).start()


def sync_status():
    config_dir = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')
    settings = config_dir/'wetype-ime/clipboard.json'
    try:
        config = json.loads(settings.read_text())
        if not config.get('enabled'):
            return '微信文本同步已关闭'
        status = json.loads((Path(config['state_dir'])/'clipboard-status.json').read_text())
        if status.get('error') or time.time() - status.get('updated', 0) > 90:
            return '微信文本同步等待连接'
        return '微信文本同步运行中'
    except FileNotFoundError:
        return '微信文本同步等待连接' if settings.is_file() else ''
    except (OSError, ValueError, TypeError, KeyError):
        return '微信文本同步状态未知'


class HistoryWindow(Gtk.ApplicationWindow):
    def __init__(self, application, store):
        super().__init__(application=application, title='剪贴板历史 · '+NAME)
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.closed = self.loading = self.dirty = self.copying = False
        self.timer = 0
        self.items = []
        self.selected = None
        self.preview_job = None
        self.set_default_size(590, 500)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, margin=12)
        self.add(box)
        self.search = Gtk.SearchEntry(placeholder_text='搜索最近 100 条的内容预览')
        self.search.connect('search-changed', lambda *_: self.populate())
        self.search.connect('activate', lambda *_: self.copy_selected())
        self.search.connect('key-press-event', self.focus_list)
        box.pack_start(self.search, False, False, 0)
        self.model = Gtk.ListStore(str, str, str)
        self.tree = Gtk.TreeView(model=self.model, headers_visible=False, enable_search=False)
        self.tree.append_column(Gtk.TreeViewColumn('类型', Gtk.CellRendererText(), text=1))
        renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, ypad=6)
        self.tree.append_column(Gtk.TreeViewColumn('内容', renderer, text=2))
        self.tree.get_selection().connect('changed', self.selection_changed)
        self.tree.connect('row-activated', lambda *_: self.copy_selected())
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        box.pack_start(scroll, True, True, 0)
        self.preview = Gtk.Image()
        self.preview.set_no_show_all(True)
        box.pack_start(self.preview, False, False, 0)
        self.status = Gtk.Label(xalign=0, label='正在读取历史…', wrap=True)
        box.pack_start(self.status, False, False, 0)
        row = Gtk.Box(spacing=6)
        box.pack_start(row, False, False, 0)
        refresh = Gtk.Button(label='刷新')
        refresh.connect('clicked', lambda *_: self.refresh())
        row.pack_start(refresh, False, False, 0)
        self.limit = Gtk.Button(label='设置 100 条上限')
        self.limit.set_no_show_all(True)
        self.limit.connect('clicked', self.configure_limit)
        row.pack_start(self.limit, False, False, 0)
        self.copy_button = Gtk.Button(label='复制选中项')
        self.copy_button.set_sensitive(False)
        self.copy_button.connect('clicked', lambda *_: self.copy_selected())
        row.pack_end(self.copy_button, False, False, 0)
        self.connect('key-press-event', self.key)
        self.connect('destroy', self.dispose)
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.listener = self.clipboard.connect('owner-change', self.changed)

    def task(self, work, done):
        future = self.pool.submit(work)
        def complete(f):
            if not self.closed and not f.cancelled():
                GLib.idle_add(self.deliver, f, done)
        future.add_done_callback(complete)
        return future

    def deliver(self, future, done):
        if not self.closed:
            try:
                result = future.result()
            except Exception as error:
                done(None, error)
            else:
                done(result, None)
        return False

    def changed(self, *_):
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(450, self.refresh)

    def refresh(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if self.loading:
            self.dirty = True
        else:
            self.loading = True
            self.task(lambda: (*self.store.entries(), sync_status()), self.loaded)
        return False

    def loaded(self, result, error):
        self.loading = False
        if error:
            self.items = []
            self.status.set_text(str(error))
        else:
            self.items, monitoring, limit, sync = result
            self.limit.set_visible(limit != LIMIT)
            message = f'最近 {len(self.items)} 条'
            if limit != LIMIT:
                message += f' · CopyQ 存储上限 {limit}'
            if not monitoring:
                message += ' · 记录已暂停'
            self.status.set_text(message + (' · '+sync if sync else ''))
        self.populate()
        if self.dirty:
            self.dirty = False
            self.refresh()

    def populate(self):
        prior = self.selected
        query = self.search.get_text().casefold().strip()
        self.model.clear()
        target = None
        for entry in self.items:
            if query not in (entry.kind+' '+entry.label).casefold():
                continue
            node = self.model.append((entry.identity, entry.kind, ' '.join(entry.label.split())))
            if entry.identity == prior or target is None:
                target = node
        if target:
            self.tree.get_selection().select_iter(target)

    def selected_entry(self):
        return next((item for item in self.items if item.identity == self.selected), None)

    def selection_changed(self, selection):
        model, node = selection.get_selected()
        self.selected = model[node][0] if node is not None else None
        entry = self.selected_entry()
        self.copy_button.set_sensitive(entry is not None and not self.copying)
        self.preview.hide()
        if self.preview_job:
            self.preview_job.cancel()
        if entry and entry.image:
            def display(image, error):
                if image and self.selected == entry.identity:
                    self.preview.set_from_pixbuf(image)
                    self.preview.show()
            self.preview_job = self.task(lambda: self.store.thumbnail(entry), display)

    def copy_selected(self):
        entry = self.selected_entry()
        if self.copying or not entry:
            return
        self.copying = True
        self.copy_button.set_sensitive(False)
        def finish(_, error):
            self.copying = False
            if error:
                self.status.set_text(str(error))
                self.copy_button.set_sensitive(self.selected is not None)
            else:
                self.destroy()
        self.task(lambda: self.store.restore(entry), finish)

    def configure_limit(self, *_):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.OK_CANCEL,
                                   text='将 CopyQ 每个标签页的存储上限设为 100 条？')
        dialog.format_secondary_text('CopyQ 会移除超出上限的旧记录。')
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.task(self.store.limit_history, lambda _, error: self.status.set_text(str(error)) if error else self.refresh())

    def focus_list(self, widget, event):
        if event.keyval == Gdk.KEY_Down and len(self.model):
            self.tree.grab_focus()
            return True
        return False

    def key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        if event.keyval == Gdk.KEY_F5:
            self.refresh()
            return True
        return False

    def dispose(self, *_):
        self.closed = True
        if self.timer:
            GLib.source_remove(self.timer)
        self.clipboard.disconnect(self.listener)
        self.pool.shutdown(wait=False, cancel_futures=True)


class HistoryApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.fastsone.Capture.ClipboardHistory', flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        window = next(iter(self.get_windows()), None)
        if window and window.get_visible():
            window.destroy()
        else:
            window = HistoryWindow(self, CopyQHistory())
            window.show_all()
            window.present()
            window.search.grab_focus()
            window.refresh()


def main():
    return HistoryApplication().run([])
