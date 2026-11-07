"""Failure injection protects existing files and desktop state."""
import json
from pathlib import Path
from types import SimpleNamespace as E
from unittest.mock import patch
from PIL import Image
from test_support import capture as m,pump
import storage

root=Path('work/storage');root.mkdir()
m.CONFIG=root/'config'
assert m.Gtk.init_check()[0]
image=Image.new('RGBA',(120,80),(240,20,30,255))
image.paste((0,0,0,0),(0,0,30,80))
pix=storage.pixbuf_image(image)
for extension in ('png','webp','tiff'):
    path=storage.write_image(pix,root/('alpha.'+extension))
    with Image.open(path) as saved:
        assert saved.size==(120,80) and saved.convert('RGBA').getpixel((1,1))[3]==0
for extension in ('jpg','bmp'):
    with Image.open(storage.write_image(pix,root/('flat.'+extension))) as saved:
        assert all(v>245 for v in saved.convert('RGB').getpixel((1,1)))
target=root/'existing.png';target.write_bytes(b'KEEP ORIGINAL')
with patch.object(Image.Image,'save',side_effect=OSError('injected disk failure')):
    try:storage.write_image(pix,target)
    except OSError:pass
    else:raise AssertionError('Expected save failure')
assert target.read_bytes()==b'KEEP ORIGINAL' and not list(root.glob('*.tmp'))
assert storage.write_image(pix,root/'no-extension').name=='no-extension.png'
settings=root/'settings.json'
for value in ('[1,2]','null','broken json','{"delay":"bad","position":[0],"hotkeys":12}'):
    settings.write_text(value);assert storage.load_settings(settings)=={}
storage.write_settings(settings,{'delay':99,'position':[20,40],'fixed_width':-5,'destination':'clipboard','hotkeys':{'full':'Print'}})
assert storage.load_settings(settings)=={'delay':10,'position':[20,40],'fixed_width':16,'destination':'clipboard','hotkeys':{'full':'Print'}}
original=settings.read_bytes()
with patch.object(storage.os,'replace',side_effect=OSError('injected rename failure')):
    try:storage.write_settings(settings,{'delay':0})
    except OSError:pass
assert settings.read_bytes()==original and not list(root.glob('*.tmp'))
print('PASS atomic image/config writes, damaged settings, alpha exports, JPEG white background',flush=True)

app=m.App();errors=[];app.error=errors.append;app.inform=lambda *args:None
editor=app.edit(pix);pump()
with patch.object(m,'render',wraps=m.render) as render:
    editor.redraw();first=editor.surface();editor.result();editor.zoom_to('200%');pump()
    assert editor.surface() is first and render.call_count==1,render.call_count
    editor.activate_tool('rect');x,y=editor.offset
    editor.press(None,E(button=1,x=x+10*editor.scale,y=y+10*editor.scale))
    editor.motion(None,E(x=x+50*editor.scale,y=y+50*editor.scale))
    assert editor.surface() is first,'Preview should reuse base annotations'
    editor.release(None,E(button=1,x=x+50*editor.scale,y=y+50*editor.scale))
    assert editor.surface() is not first
editor.dirty=True
with patch.object(m,'export_image',side_effect=OSError('injected failure')):
    try:editor.write_image(target)
    except OSError:pass
assert editor.dirty and editor.filename is None
with patch.object(app,'persist',side_effect=OSError('settings read-only')):
    editor.write_image(root/'saved.png')
assert not editor.dirty and (root/'saved.png').exists() and '已保存' in editor.status.get_text()
second=app.edit(pix);second.zoom_to('50%');app.workspace.notebook.set_current_page(0);pump()
assert app.workspace.zoom.get_active_text()=='200%'
app.workspace.notebook.set_current_page(1);pump();assert app.workspace.zoom.get_active_text()=='50%'
print('PASS render cache, save state after failures, independent tab zoom',flush=True)

from workflows import Recorder,Gst
blocked=root/'blocked';blocked.write_text('not a directory')
rec=Recorder(app,path=blocked/'video.webm')
assert rec.finalized and rec.finished and app.recorder is None and errors
video=root/'existing.webm';video.write_bytes(b'KEEP OLD VIDEO')
with patch.object(Gst,'parse_launch',side_effect=RuntimeError('missing encoder')):
    rec=Recorder(app,path=video)
assert rec.finalized and app.recorder is None and rec.timer is None
assert video.read_bytes()==b'KEEP OLD VIDEO' and not list(root.glob('*.recording.webm'))
rec.stop();rec.complete(False,'duplicate completion')
print('PASS recording startup failure cleanup and preservation of existing video',flush=True)
for item in list(app.editors):item.destroy()
app.workspace.destroy();app.hotkeys.close();app.toolbar.destroy()
