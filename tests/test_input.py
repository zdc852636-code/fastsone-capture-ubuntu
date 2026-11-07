import os,sys,time,subprocess,json,ctypes as C,ctypes.util
from pathlib import Path
from types import SimpleNamespace as E
from test_support import capture as m
m.CONFIG=Path('work/input-test-config').resolve();m.Gtk.init_check()
def pump(t=.12):
 end=time.monotonic()+t
 while time.monotonic()<end:
  while m.Gtk.events_pending():m.Gtk.main_iteration_do(False)
  time.sleep(.004)
x=C.CDLL(ctypes.util.find_library('X11'))
for name,args,res in [('XOpenDisplay',[C.c_char_p],C.c_void_p),('XDefaultRootWindow',[C.c_void_p],C.c_ulong),('XKeysymToKeycode',[C.c_void_p,C.c_ulong],C.c_uint),('XGrabPointer',[C.c_void_p,C.c_ulong,C.c_int,C.c_uint,C.c_int,C.c_int,C.c_ulong,C.c_ulong,C.c_ulong],C.c_int),('XGrabKeyboard',[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_int,C.c_ulong],C.c_int),('XUngrabPointer',[C.c_void_p,C.c_ulong],C.c_int),('XUngrabKeyboard',[C.c_void_p,C.c_ulong],C.c_int),('XFlush',[C.c_void_p],C.c_int)]:
 f=getattr(x,name);f.argtypes=args;f.restype=res
d=x.XOpenDisplay(None);root=x.XDefaultRootWindow(d)
t=C.CDLL(ctypes.util.find_library('Xtst'))
t.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
t.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
t.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
def move(a,b):t.XTestFakeMotionEvent(d,-1,a,b,0);x.XFlush(d);pump(.03)
def mouse(button,down):t.XTestFakeButtonEvent(d,button,down,0);x.XFlush(d);pump(.05)
def key(sym):
 code=x.XKeysymToKeycode(d,sym);t.XTestFakeKeyEvent(d,code,1,0);t.XTestFakeKeyEvent(d,code,0,0);x.XFlush(d);pump()
# A separate GTK process detects clicks; same-process widget tests would miss leaked input grabs.
state=Path('work/click-receiver.json').resolve();state.unlink(missing_ok=True)
script=r'''
import gi,json,sys
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
from pathlib import Path
path=Path(sys.argv[1]);w=Gtk.Window(title='LW external click receiver');w.move(850,1400);w.set_default_size(280,140);w.set_keep_above(True)
b=Gtk.Button(label='Input test target');w.add(b);count=0
def report():
 _,x,y=w.get_window().get_origin();path.write_text(json.dumps(dict(x=x+100,y=y+60,count=count)));return False
def clicked(*a):
 global count
 count+=1;report()
b.connect('clicked',clicked);w.show_all();GLib.timeout_add(250,report);Gtk.main()
'''
receiver=subprocess.Popen(['/usr/bin/python3','-c',script,str(state)])
try:
 for i in range(100):
  if state.exists():break
  pump(.05)
 assert state.exists()
 app=m.App();errors=[];delivered=[];app.error=errors.append;app.inform=lambda *a:None;app.finish_selection=lambda pix,rect,mode=None:delivered.append((pix,rect))
 r=m.Gdk.Screen.get_default().get_root_window();pix=m.Gdk.pixbuf_get_from_window(r,0,0,r.get_width(),r.get_height())
 def start(mode):
  app.pending_mode=mode;app.busy=True;app.toolbar.hide();app.selector=m.Selector(app,pix)
  for _ in range(40):
   pump(.05)
   if app.selector is None or app.selector.grabbed:break
  assert app.selector and app.selector.grabbed,(mode,errors,getattr(app.selector,'last_grab_status',None))
  return app.selector
 def restored():
  pump();assert app.selector is None and not app.busy
  assert x.XGrabPointer(d,root,False,4,1,1,0,0,0)==0,'Pointer still grabbed'
  x.XUngrabPointer(d,0)
  assert x.XGrabKeyboard(d,root,False,1,1,0)==0,'Keyboard still grabbed'
  x.XUngrabKeyboard(d,0);x.XFlush(d)
  before=json.loads(state.read_text());move(before['x'],before['y']);mouse(1,1);mouse(1,0);pump()
  after=json.loads(state.read_text())
  if after['count']!=before['count']+1:
   print('CLICK DEBUG',before,after,'root size',r.get_width(),r.get_height(),flush=True)
   subprocess.run(['xwininfo','-root','-tree'])
  assert after['count']==before['count']+1,'First external click was swallowed'
 restored()
 for mode in ['region','fixed','object','free','scroll','record_region','color','ruler','ocr']:
  print('TEST',mode,flush=True);start(mode);key(0xff1b);restored()
 start('region');move(200,400);mouse(1,1);move(480,620);mouse(1,0);restored();assert delivered[-1][0].get_width()==280
 start('region');move(250,450);mouse(1,1);mouse(1,0);restored()
 start('region');mouse(3,1);mouse(3,0);restored()
 for mode in ['fixed','color','object']:
  start(mode);pos=json.loads(state.read_text());move(pos['x'],pos['y']);n=len(delivered);mouse(1,1)
  assert app.selector is not None and len(delivered)==n,'Selection closed during mouse-down'
  mouse(1,0);restored();assert len(delivered)==n+1
 start('free');move(200,400);mouse(1,1);move(450,400);move(400,600);move(220,580);mouse(1,0);restored();assert delivered[-1][0].get_has_alpha()
 for action in ['destroy','hide']:
  sel=start('region');getattr(sel,action)();restored()
 # Force failure inside a real release-event callback.
 sel=start('region')
 def bad_rect():raise RuntimeError('Injected selection calculation failure')
 sel.rect=bad_rect
 move(200,400);mouse(1,1);move(450,600);mouse(1,0);restored();assert errors
 # Repeat completion/cancellation to catch stale window ownership or state.
 for i in range(6):start('region');key(0xff1b);restored()
 print('PASS: real Esc in 9 modes, drag completion, tiny click, right-click, release-only click capture, freehand, destroy/hide, injected exception, repeated captures and FIRST external click after every case.',flush=True)
 app.hotkeys.close();app.toolbar.destroy()
finally:receiver.terminate();receiver.wait(timeout=5)
