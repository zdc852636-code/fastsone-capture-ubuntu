import importlib.util,sys,time
from pathlib import Path
from types import SimpleNamespace as E
from test_support import capture as m
m.CONFIG=Path('work/test-v2-config')
assert m.Gtk.init_check()[0]
def pump(t=.15):
 end=time.monotonic()+t
 while time.monotonic()<end:
  while m.Gtk.events_pending():m.Gtk.main_iteration_do(False)
  time.sleep(.01)
def fail(text):raise AssertionError(text)
app=m.App(); app.error=fail; app.inform=lambda *args:print('INFO',*args,flush=True); pump()
app.settings['destination']='editor'
pix=m.GdkPixbuf.Pixbuf.new(m.GdkPixbuf.Colorspace.RGB,False,8,640,360);pix.fill(0xf8fafcff)
e=app.edit(pix);pump(); assert len(app.editors)==1 and app.workspace.notebook.get_n_pages()==1
assert not e.draw_row.get_visible()
e.drawing(True);pump();assert e.draw_row.get_visible()
for i,kind in enumerate(['arrow','rect','ellipse','pen','highlight','mosaic','number']):
 e.activate_tool(kind);x=e.offset[0]+(35+i*72)*e.scale;y=e.offset[1]+60*e.scale
 e.press(e.canvas,E(button=1,x=x,y=y))
 if kind!='number':e.motion(e.canvas,E(x=x+48*e.scale,y=y+100*e.scale));e.release(e.canvas,E(button=1,x=x+48*e.scale,y=y+100*e.scale))
 pump(.02)
assert len(e.ops)==7
# Editable annotation movement, delete, undo.
e.activate_tool('select');x=e.offset[0]+50*e.scale;y=e.offset[1]+80*e.scale
e.press(None,E(button=1,x=x,y=y));assert e.selected==0
e.motion(None,E(x=x+20*e.scale,y=y+10*e.scale));e.release(None,E(button=1,x=x,y=y));assert abs(e.ops[0]['a'][0]-55)<1
e.key(None,E(keyval=m.Gdk.KEY_Delete,state=0));assert len(e.ops)==6
e.history(True);assert len(e.ops)==7
e.remember();e.ops.append(dict(kind='text',a=(40,240),b=(40,240),color=(.1,.2,.4,1),width=3,size=26,text='经典操作 · Ubuntu 截图测试'))
root=Path('work')
for suffix in ['png','jpg','bmp','tiff','webp','pdf']:
 path=root/('v2-export.'+suffix);e.write_image(path);assert path.stat().st_size>100
# Additional drawing tools, preserving the original editor state after each operation.
for kind in ['line','blur','spotlight']:
 e.activate_tool(kind);x,y=e.offset
 e.press(None,E(button=1,x=x+20*e.scale,y=y+20*e.scale));e.motion(None,E(x=x+150*e.scale,y=y+100*e.scale));e.release(None,E(button=1,x=x+150*e.scale,y=y+100*e.scale));assert e.result();e.history(True)
e.remember();e.ops.append(dict(kind='callout',a=(120,100),b=(120,100),color=(.5,.2,.1,1),width=2,size=24,text='中文气泡'));assert e.result();e.history(True)
# Crop + undo + rotation + edge + zoom.
e.activate_tool('crop');x,y=e.offset
e.press(None,E(button=1,x=x+10*e.scale,y=y+10*e.scale));e.release(None,E(button=1,x=x+310*e.scale,y=y+210*e.scale))
assert e.pixbuf.get_width()==300;e.history(True);assert e.pixbuf.get_width()==640
e.rotate_image();assert e.pixbuf.get_width()==360;e.history(True)
e.edge();assert e.pixbuf.get_width()==670;e.history(True)
e.zoom_to('200%');pump();assert e.canvas.get_allocated_width()>=1280
e.zoom_to('适合窗口');pump()
e.copy_image();assert m.Gtk.Clipboard.get(m.Gdk.SELECTION_CLIPBOARD).wait_for_image().get_width()==640
app.paste_image();pump();assert app.workspace.notebook.get_n_pages()==2
for mode in ['full','window','region','fixed','free','object']:
 app.workspace.present();pump();old=len(app.editors);app.capture(mode);pump(.45)
 if app.selector:
  sel=app.selector
  if mode=='fixed':
   sel.press(None,E(button=1,x=300,y=300));sel.release(None,E(button=1,x=300,y=300))
  elif mode=='object':
   # Choose a point in our editor window, rather than a foreign app.
   _,wx,wy=app.workspace.get_window().get_origin();sel.press(None,E(button=1,x=wx+100,y=wy+100));sel.release(None,E(button=1,x=wx+100,y=wy+100))
  else:
   sel.press(None,E(button=1,x=100,y=100));sel.motion(None,E(x=400,y=100));sel.motion(None,E(x=400,y=300));sel.motion(None,E(x=100,y=300));sel.release(None,E(button=1,x=400,y=300))
  pump()
 assert len(app.editors)==old+1,(mode,len(app.editors),old)
 app.editors[-1].destroy()
# Direct output targets.
app.settings['destination']='clipboard';n=len(app.editors);app.deliver(pix);assert len(app.editors)==n
app.settings.update(destination='auto',save_dir=str(root/'autosaves'));app.deliver(pix);assert list((root/'autosaves').glob('*.png'))
app.settings['destination']='draw';ed=app.edit(pix);ed.destroy();app.deliver(pix);assert app.editors[-1].draw_row.get_visible();app.editors[-1].destroy();app.settings['destination']='editor'
# Escape and a real global fallback shortcut.
app.capture('region');pump(.4);app.selector.key(None,E(keyval=m.Gdk.KEY_Escape));assert not app.busy
import ctypes as C,ctypes.util
xt=C.CDLL(ctypes.util.find_library('Xtst'));xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
lib=app.hotkeys.lib;display=app.hotkeys.display
for sym in [0xffe3,0xffe9,ord('a')]:xt.XTestFakeKeyEvent(display,lib.XKeysymToKeycode(display,sym),True,0)
for sym in [ord('a'),0xffe9,0xffe3]:xt.XTestFakeKeyEvent(display,lib.XKeysymToKeycode(display,sym),False,0)
lib.XFlush(display);pump(.7);assert app.selector;app.selector.finish();pump()
# Synthetic scroll matcher: varied stripes, small/large/partial displacements and identical frames.
from workflows import match_scroll,Recorder,ScrollCapture
from PIL import Image,ImageDraw
im=Image.new('RGB',(320,2400),'white');draw=ImageDraw.Draw(im)
for y in range(0,2400,17):draw.rectangle((0,y,319,y+12),fill=((y*17)%255,(y*31)%255,(y*47)%255));draw.text((y%160,y),str(y),fill='black')
for shift in [1,40,137,280]:assert abs(match_scroll(im.crop((0,0,320,400)),im.crop((0,shift,320,shift+400)))-shift)<=1,shift
assert match_scroll(im.crop((0,0,320,400)),im.crop((0,0,320,400)))==0
print('PASS core UI, tools, output modes, exports, zoom, editable objects, captures, hotkeys, scroll matcher',flush=True)
# A real scrollable test window exercises wheel injection and screenshot stitching end to end.
win=m.Gtk.Window(title='LW scroll integration test');win.set_default_size(350,500);win.move(60,200)
scroll=m.Gtk.ScrolledWindow();area=m.Gtk.DrawingArea();area.set_size_request(320,2400)
from workflows import pixbuf
content=pixbuf(im)
def draw_area(widget,cr):m.Gdk.cairo_set_source_pixbuf(cr,content,0,0);cr.paint()
area.connect('draw',draw_area);scroll.add(area);win.add(scroll);win.show_all();win.present();pump(.4)
viewport=scroll.get_child();_,vx,vy=viewport.get_window().get_origin();rect=(vx+3,vy+3,300,400)
app.busy=True;session=ScrollCapture(app,rect);app.scroll_session=session;session.start();pump(6)
if app.scroll_session:app.scroll_session.finish()
assert app.editors[-1].pixbuf.get_height()>400,app.editors[-1].pixbuf.get_height()
print('PASS live scroll stitching:',app.editors[-1].pixbuf.get_width(),app.editors[-1].pixbuf.get_height(),flush=True)
win.destroy();pump()
# Actual X11 -> VP8 -> WebM recording, pause/resume and EOS finalization.
recordpath=root/'v2-recording.webm';recordpath.write_bytes(b'PREVIOUS VIDEO');rec=Recorder(app,(0,0,320,200),False,path=recordpath);app.recorder=rec;pump(1.4)
assert rec.pipeline is not None and not rec.finalized
assert recordpath.read_bytes()==b'PREVIOUS VIDEO','Recording must not truncate an existing destination'
rec.toggle();pump(.3);rec.toggle();pump(.7);rec.stop();pump(3)
assert rec.finalized and recordpath.stat().st_size>500
assert rec.timer is None and rec.eos_timer is None and rec.bus is None and rec.temp_path is None
from gi.repository import Gst
pipeline=Gst.parse_launch('filesrc location="'+str(recordpath)+'" ! matroskademux ! vp8dec ! fakesink');pipeline.set_state(Gst.State.PLAYING)
msg=pipeline.get_bus().timed_pop_filtered(5*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR);pipeline.set_state(Gst.State.NULL)
assert msg and msg.type==Gst.MessageType.EOS
print('PASS real recording, pause/resume, WebM decode',flush=True)
# Own-app previews only.
for ed in list(app.editors):
 if ed is not e:ed.destroy()
app.workspace.notebook.set_current_page(0);e.drawing(False);app.workspace.present();pump()
for name,window in [('v2-editor-preview.png',app.workspace),('v2-panel-preview.png',app.toolbar)]:
 gw=window.get_window();shot=m.Gdk.pixbuf_get_from_window(gw,0,0,gw.get_width(),gw.get_height());shot.savev(str(root/name),'png',[],[])
e.drawing(True);pump();gw=app.workspace.get_window();shot=m.Gdk.pixbuf_get_from_window(gw,0,0,gw.get_width(),gw.get_height());shot.savev(str(root/'v2-draw-preview.png'),'png',[],[])
for ed in list(app.editors):ed.destroy()
app.workspace.destroy();app.hotkeys.close();app.toolbar.destroy()
print('ALL PASS',flush=True)
