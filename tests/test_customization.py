"""Exercise actual wheel input and the preferences dialog on the isolated desktop."""
import ctypes as C
import ctypes.util
from pathlib import Path
from test_support import capture as m, pump
from customize import EDITOR_KEYS, GLOBAL_KEYS, LayoutPage, binding
from storage import load_settings

m.CONFIG = Path('work/custom-config')
app = m.App()
pix = m.GdkPixbuf.Pixbuf.new(m.GdkPixbuf.Colorspace.RGB, False, 8, 2000, 1400)
pix.fill(0x546e88ff)
editor = app.edit(pix)
window = app.workspace
editor.zoom_to('100%')
pump(.3)
horizontal = editor.scroller.get_hadjustment()
vertical = editor.scroller.get_vadjustment()
horizontal.set_value(240)
vertical.set_value(160)
pump()
display = app.hotkeys.display
lib = app.hotkeys.lib
xt = C.CDLL(ctypes.util.find_library('Xtst'))
xt.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
xt.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
xt.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]


def press_key(sym, down):
    xt.XTestFakeKeyEvent(display, lib.XKeysymToKeycode(display, sym), down, 0)
    lib.XFlush(display)


def tap(sym):
    press_key(sym, 1)
    press_key(sym, 0)
    pump(.5)


def scroll(button):
    for down in (1, 0):
        xt.XTestFakeButtonEvent(display, button, down, 0)
    lib.XFlush(display)
    pump(.25)


_, cx, cy = editor.canvas.get_window().get_origin()
px = round(cx + horizontal.get_value() + 210)
py = round(cy + vertical.get_value() + 170)
xt.XTestFakeMotionEvent(display, -1, px, py, 0)
lib.XFlush(display)
pump()


def image_point():
    _, x, y = editor.canvas.get_window().get_origin()
    return ((px-x-editor.offset[0])/editor.scale, (py-y-editor.offset[1])/editor.scale)


before = image_point()
press_key(m.Gdk.KEY_Control_L, 1)
scroll(4)
assert editor.zoom == window.zoom.get_active_text() == '125%', editor.zoom
assert max(abs(a-b) for a,b in zip(before,image_point())) < 3, (before,image_point())
scroll(5)
press_key(m.Gdk.KEY_Control_L, 0)
assert editor.zoom == '100%'
start = vertical.get_value()
scroll(5)
assert editor.zoom == '100%' and vertical.get_value() > start
print('PASS Ctrl+wheel in both directions, cursor anchor, zoom indicator, ordinary scrolling', flush=True)

errors = []
def dialog_error(parent, message):
    errors.append(message)
    m.GLib.idle_add(parent.response, m.Gtk.ResponseType.CANCEL)
m.notify_error = dialog_error


def change_settings():
    dialog = next(w for w in m.Gtk.Window.list_toplevels() if isinstance(w,m.Gtk.Dialog) and w.get_visible())
    tabs = dialog.get_content_area().get_children()[0]
    key_box = tabs.get_nth_page(1)
    grid = key_box.get_children()[1].get_child().get_child()
    grid.get_child_at(1,1).set_text('F8')
    grid.get_child_at(1,2).set_text('F9')
    grid.get_child_at(1,2+len(GLOBAL_KEYS)+list(EDITOR_KEYS).index('copy')).set_text('Ctrl+Alt+Y')
    page = tabs.get_nth_page(2)
    assert isinstance(page, LayoutPage)
    for scope, move, hide in [('panel','region','full'),('editor','draw','print')]:
        page.scope.set_active_id(scope)
        model = page.tree.get_model()
        pos = next(i for i,r in enumerate(model) if r[1]==move)
        page.tree.get_selection().select_path(pos)
        for _ in range(pos):
            page.move(-1)
        index = next(i for i,r in enumerate(model) if r[1]==hide)
        page.toggle(None, str(index))
    dialog.response(m.Gtk.ResponseType.OK)
    return False

m.GLib.timeout_add(150, change_settings)
app.preferences()
assert not errors, errors
saved = load_settings(m.CONFIG/'settings.json')
assert binding(saved,'hotkeys','quick_region') == 'F8'
assert saved['toolbars']['panel']['order'][0] == 'region'
assert saved['toolbars']['editor']['order'][0] == 'draw'
assert app.panel_row.get_children()[0] is app.panel_widgets['region']
assert window.toolbar_row.get_children()[0] is window.toolbar_widgets['draw']
app.toolbar.show_all()
window.show_all()
assert not app.panel_widgets['full'].get_visible() and not window.toolbar_widgets['print'].get_visible()
tap(m.Gdk.KEY_F3)
assert app.selector is None
tap(m.Gdk.KEY_F8)
assert app.selector and app.selector.mode == 'region'
tap(m.Gdk.KEY_Escape)
tap(m.Gdk.KEY_F9)
assert app.selector and app.selector.mode == 'ocr'
tap(m.Gdk.KEY_Escape)
window.present()
pump()
copied = []
editor.copy_image = lambda: copied.append(True)
press_key(m.Gdk.KEY_Control_L, 1)
press_key(m.Gdk.KEY_Alt_L, 1)
tap(m.Gdk.KEY_y)
press_key(m.Gdk.KEY_Alt_L, 0)
press_key(m.Gdk.KEY_Control_L, 0)
assert copied == [True], copied
print('PASS preferences UI, live global/editor shortcuts, saved toolbar order and visibility', flush=True)

# A failed write must restore the old key grab as well as the settings object.
from unittest.mock import patch
new_keys = dict(saved['hotkeys'], quick_region='F7')
with patch.object(m, 'write_settings', side_effect=OSError('read only')):
    try:
        app.apply_preferences({'hotkeys':new_keys})
    except OSError:
        pass
    else:
        raise AssertionError('Expected write failure')
tap(m.Gdk.KEY_F7)
assert app.selector is None
tap(m.Gdk.KEY_F8)
assert app.selector and app.selector.mode=='region'
tap(m.Gdk.KEY_Escape)
# A separate X11 client owns F6. Changing F8 to F6 must be rejected atomically.
other = lib.XOpenDisplay(None)
reserved = lib.XKeysymToKeycode(other, m.Gdk.KEY_F6)
lib.XGrabKey(other, reserved, 0, lib.XDefaultRootWindow(other), False, 1, 1)
lib.XSync(other, False)
try:
    app.apply_preferences({'hotkeys': dict(saved['hotkeys'], quick_region='F6')})
except ValueError:
    assert app.settings['hotkeys']['quick_region'] == 'F8'
else:
    raise AssertionError('Conflicting X11 grab was accepted')
finally:
    lib.XCloseDisplay.argtypes = [C.c_void_p]
    lib.XCloseDisplay(other)
tap(m.Gdk.KEY_F8)
assert app.selector and app.selector.mode == 'region'
tap(m.Gdk.KEY_Escape)
print('PASS conflicting desktop shortcut preserves previous bindings', flush=True)
editor.destroy()
window.destroy()
app.hotkeys.close()
app.toolbar.destroy()
print('PASS failed settings save keeps the previous working key', flush=True)
