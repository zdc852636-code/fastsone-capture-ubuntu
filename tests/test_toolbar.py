import sys,time,ctypes as C,ctypes.util,json
from pathlib import Path
from test_support import capture as m
m.CONFIG=Path('work/v22-test-config').resolve();m.CONFIG.mkdir(exist_ok=True)
(m.CONFIG/'settings.json').write_text(json.dumps({'position':[80,80],'delay':0}))
assert m.Gtk.init_check()[0]
def pump(t=.15):
 end=time.monotonic()+t
 while time.monotonic()<end:
  while m.Gtk.events_pending():m.Gtk.main_iteration_do(False)
  time.sleep(.004)
x=C.CDLL(ctypes.util.find_library('X11'))
for name,args,res in [('XOpenDisplay',[C.c_char_p],C.c_void_p),('XKeysymToKeycode',[C.c_void_p,C.c_ulong],C.c_uint),('XFlush',[C.c_void_p],C.c_int)]:
 f=getattr(x,name);f.argtypes=args;f.restype=res
d=x.XOpenDisplay(None)
t=C.CDLL(ctypes.util.find_library('Xtst'))
t.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
t.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
t.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
def move(px,py):t.XTestFakeMotionEvent(d,-1,px,py,0);x.XFlush(d);pump()
def mouse(down):t.XTestFakeButtonEvent(d,1,down,0);x.XFlush(d);pump(.05)
def key(sym):
 code=x.XKeysymToKeycode(d,sym)
 for down in [1,0]:t.XTestFakeKeyEvent(d,code,down,0)
 x.XFlush(d);pump(.55)
move(1000,1200)
app=m.App();errors=[];app.error=errors.append;pump(1.6)
assert app.panel.collapsed and not app.panel.body.get_visible()
gw=app.toolbar.get_window();_,px,py=gw.get_origin()
top=m.Gdk.Display.get_default().get_monitor_at_window(gw).get_workarea().y
assert py==top and gw.get_height()==6,(py,gw.get_height())
red=m.Gdk.pixbuf_get_from_window(gw,0,0,gw.get_width(),gw.get_height())
red.savev(str(Path('work/v22-red-strip.png').resolve()),'png',[],[])
assert tuple(red.get_pixels()[:3])==(223,39,39)
move(px+30,py+3);pump(.3)
assert not app.panel.collapsed and app.panel.body.get_visible() and gw.get_height()>40
# Child widgets remain visible through repeated show_all and collapse cycles.
app.toolbar.show_all();pump();assert app.destination_label.get_visible()
# Keep a menu open while pointer is outside the toolbar.
app.output.set_active(True);move(1100,1300);pump(1.6)
assert not app.panel.collapsed,'Collapsed while target menu was open'
app.output.set_active(False);app.output.get_popup().popdown();pump(1.6)
assert app.panel.collapsed
app.toolbar.hide();app.toolbar.show_all();pump();assert not app.panel.body.get_visible()
# A real F3 must activate rectangular selection even from the red strip.
key(m.Gdk.KEY_F3);assert app.selector and app.pending_mode=='region'
key(m.Gdk.KEY_Escape);assert app.selector is None and not app.busy
pump(1.5)
assert gw.get_origin()[1:]==(px,top),gw.get_origin()
move(px+30,top+3);pump();assert not app.panel.collapsed
folder=Path('work/v22-folder-output').resolve();folder.mkdir(exist_ok=True)
def choose_folder():
 dialogs=[w for w in m.Gtk.Window.list_toplevels() if isinstance(w,m.Gtk.FileChooserDialog)]
 assert dialogs
 dialog=dialogs[-1];dialog.set_current_folder(str(folder))
 m.GLib.timeout_add(250,lambda:dialog.response(m.Gtk.ResponseType.OK) or False)
 return False
m.GLib.timeout_add(150,choose_folder);app.choose_destination_folder();pump()
assert app.settings['destination']=='auto' and app.destination_folder()==folder
assert app.destination_label.get_text()=='目标：到文件夹'
assert app.destination_items['auto'].get_active()
# End-to-end F3 drag -> selected folder, with no editor opened.
before=set(folder.glob('*.png'));move(1100,1300);pump(1.5);key(m.Gdk.KEY_F3)
assert app.selector
move(200,500);mouse(True);move(460,660);mouse(False);pump()
files=set(folder.glob('*.png'))-before
assert len(files)==1 and not app.editors
shot=m.GdkPixbuf.Pixbuf.new_from_file(str(files.pop()));assert (shot.get_width(),shot.get_height())==(260,160)
# Destination changes persist and clipboard-only creates no editor.
app.destination_items['clipboard'].set_active(True);app.deliver(shot)
clip=m.Gtk.Clipboard.get(m.Gdk.SELECTION_CLIPBOARD).wait_for_image()
assert clip and clip.get_width()==260 and not app.editors
assert json.loads((m.CONFIG/'settings.json').read_text())['destination']=='clipboard'
app.destination_items['editor'].set_active(True);app.deliver(shot);assert len(app.editors)==1
app.destination_items['draw'].set_active(True);app.deliver(shot);assert app.editors[-1].draw_row.get_visible()
# Invalid folder must preserve the screenshot in the editor.
blocked=Path('work/v22-not-a-directory').resolve();blocked.write_text('test')
app.settings['save_dir']=str(blocked/'child');app.destination_items['auto'].set_active(True)
n=len(app.editors);app.deliver(shot);assert len(app.editors)==n+1 and errors
app.settings['save_dir']=str(folder);app.destination_items['editor'].set_active(True)
app.panel.expand();pump(.15)
gw=app.toolbar.get_window();m.Gdk.pixbuf_get_from_window(gw,0,0,gw.get_width(),gw.get_height()).savev(str(Path('work/v22-panel-preview.png').resolve()),'png',[],[])
for ed in list(app.editors):ed.destroy()
app.workspace.destroy();app.hotkeys.close();app.toolbar.destroy()
print('PASS red strip 6px / monitor top / hover expansion / popup protection / capture restore / real F3 and Esc / real F3 drag to selected folder / destination persistence / clipboard / editor / drawing / invalid-folder recovery',flush=True)
