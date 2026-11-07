import importlib.util,time
from pathlib import Path
from types import SimpleNamespace as E
from test_support import capture as m
m.CONFIG=Path('work/edge-test-config').resolve()
assert m.Gtk.init_check()[0]
def pump():
 for _ in range(15):
  while m.Gtk.events_pending():m.Gtk.main_iteration_do(False)
  time.sleep(.01)
app=m.App();errors=[];app.error=errors.append
pix=m.GdkPixbuf.Pixbuf.new(m.GdkPixbuf.Colorspace.RGB,False,8,100,100);pix.fill(0xffffffff)
e=app.edit(pix);e.dirty=True;pump()
for response in (m.Gtk.ResponseType.DELETE_EVENT,m.Gtk.ResponseType.CANCEL):
 def dismiss(response=response):
  dialogs=[w for w in m.Gtk.Window.list_toplevels() if isinstance(w,m.Gtk.MessageDialog)]
  assert dialogs
  dialogs[-1].response(response);return False
 m.GLib.timeout_add(30,dismiss);app.workspace.close(e)
 assert e in app.editors and app.workspace.notebook.get_n_pages()==1
e.drawing(True);entry=e.width;entry.grab_focus();pump();assert app.workspace.get_focus() is entry
assert app.workspace.key(None,E(keyval=m.Gdk.KEY_c,state=m.Gdk.ModifierType.CONTROL_MASK)) is False
app.workspace.set_focus(None)
for kind in ('mosaic','blur'):
 for a,b in (((-100,-100),(-10,-10)),((200,200),(300,300)),((-20,-20),(30,30))):
  assert m.render(pix,[dict(kind=kind,a=a,b=b,color=(0,0,0,1),width=3,size=20)])
from workflows import ScrollCapture
from PIL import Image
deliveries=[];app.deliver=deliveries.append
app.busy=True;session=ScrollCapture(app,(0,0,100,100));app.scroll_session=session
session.frames=[Image.new('RGB',(100,100))];session.running=True
app.xtest_scroll=lambda *_:(_ for _ in ()).throw(RuntimeError('injected scroll failure'))
session.next();session.finish()
assert session.closed and not app.busy and app.scroll_session is None
assert app.toolbar.get_visible() and len(deliveries)==1 and errors[-1]=='injected scroll failure'
app.persist=lambda:(_ for _ in ()).throw(OSError('injected settings failure'))
app.capture('region')
assert not app.busy and app.toolbar.get_visible() and app.capture_timer is None
assert 'injected settings failure' in errors[-1]
for ed in list(app.editors):ed.destroy()
app.workspace.destroy();app.hotkeys.close();app.toolbar.destroy()
print('PASS: save-dialog close/cancel preserves tab; text-entry shortcuts; out-of-bounds mosaic/blur; scroll error restores UI once; settings error restores capture state')
