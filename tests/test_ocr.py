"""Exercise F4 -> real screen selection -> bilingual OCR -> text clipboard."""
import ctypes as C
import ctypes.util
from pathlib import Path
import time
from PIL import Image
from test_support import capture as m,pump
from storage import pixbuf_image

m.CONFIG=Path('work/ocr-config')
assert m.Gtk.init_check()[0]
app=m.App();errors=[];notices=[]
app.error=errors.append;app.notify=lambda *args:notices.append(args)
app.settings.update(destination='auto',copy_always=True,save_dir=str(Path('work/ocr-must-not-save').resolve()))
clipboard=m.Gtk.Clipboard.get(m.Gdk.SELECTION_CLIPBOARD)
clipboard.set_text('previous clipboard',-1)

window=m.Gtk.Window(title='LW OCR test text');window.set_default_size(700,200);window.move(100,400)
area=m.Gtk.DrawingArea();window.add(area)
def draw(widget,cr):
    cr.set_source_rgb(1,1,1);cr.paint();cr.set_source_rgb(0,0,0);cr.move_to(28,26)
    layout=m.PangoCairo.create_layout(cr)
    layout.set_font_description(m.Pango.FontDescription('Noto Sans CJK SC 28'))
    layout.set_text('截图识字测试\nUbuntu OCR 12345',-1)
    m.PangoCairo.show_layout(cr,layout)
area.connect('draw',draw);window.show_all();window.present();pump(.4)
lib=app.hotkeys.lib;display=app.hotkeys.display
xt=C.CDLL(ctypes.util.find_library('Xtst'))
xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
xt.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
xt.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
def key(sym):
    code=lib.XKeysymToKeycode(display,sym)
    for down in (1,0):xt.XTestFakeKeyEvent(display,code,down,0)
    lib.XFlush(display);pump(.55)
def move(x,y):xt.XTestFakeMotionEvent(display,-1,x,y,0);lib.XFlush(display);pump(.06)
def button(down):xt.XTestFakeButtonEvent(display,1,down,0);lib.XFlush(display);pump(.06)

_,x,y=area.get_window().get_origin();width,height=area.get_allocated_width(),area.get_allocated_height()
key(m.Gdk.KEY_F4);assert app.selector and app.selector.mode=='ocr'
key(m.Gdk.KEY_Escape)
assert app.selector is None and clipboard.wait_for_text()=='previous clipboard'
key(m.Gdk.KEY_F4);assert app.selector
move(x+1,y+1);button(1);move(x+width-2,y+height-2);button(0)
deadline=time.monotonic()+20
while app.ocr_running and time.monotonic()<deadline:pump(.05)
assert not app.ocr_running and not errors,errors
text=clipboard.wait_for_text();normalized=''.join(text.split())
assert '截图识字测试' in normalized and 'UbuntuOCR12345' in normalized,repr(text)
assert not app.editors and not Path(app.settings['save_dir']).exists()
assert any(title=='文字已复制' for title,message in notices)
print('PASS real F4 / Esc / bilingual screen OCR / automatic text clipboard / output independence',flush=True)

app.recognize_text(pixbuf_image(Image.new('RGB',(160,80),'white')))
app.capture('region');assert app.selector is None,'Do not start another capture while OCR is pending'
deadline=time.monotonic()+10
while app.ocr_running and time.monotonic()<deadline:pump(.05)
assert not app.ocr_running and clipboard.wait_for_text()==text and notices[-1][0]=='未识别到文字'
app.ocr_done(None,'injected engine failure')
assert errors[-1]=='injected engine failure' and clipboard.wait_for_text()==text
app.ocr_done('Uncertain sample',None,True)
assert clipboard.wait_for_text()=='Uncertain sample' and '核对' in notices[-1][1]
print('PASS blank capture, failure and repeated-key protection preserve clipboard',flush=True)
window.destroy();app.hotkeys.close();app.toolbar.destroy()
