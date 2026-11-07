"""Auto-hide toolbar: a red strip remains at the top of the current monitor."""
import time
from gi.repository import Gtk, Gdk, GLib


class AutoHidePanel:
    IDLE_SECONDS = 1.2
    STRIP_HEIGHT = 6

    def __init__(self, app, body, strip):
        self.app, self.window, self.body, self.strip = app, app.toolbar, body, strip
        self.collapsed = False
        self.transitioning = False
        self.last_inside = time.monotonic()
        self.last_position = tuple(app.settings.get('position',[80,80]))
        self.strip.set_tooltip_text('移入展开截图工具栏')
        # Restoring the toolbar after a capture must not reveal a hidden body.
        self.body.set_no_show_all(True)
        self.source = GLib.timeout_add(150, self.tick)
        self.window.connect('destroy', self.stop)
        self.window.connect('unmap', self.remember_position)
        self.window.connect('map-event', self.restore_position)

    def remember_position(self, *args):
        win=self.window.get_window()
        if win:
            _,x,y=win.get_origin()
            self.last_position=(x,y)

    def restore_position(self, *args):
        # Some window managers centre a hidden utility window when it is shown.
        # Restore the strip to the monitor edge after every completed/cancelled capture.
        x,y=self.last_position
        monitor=Gdk.Display.get_default().get_monitor_at_point(x,y)
        area=monitor.get_workarea(); win=self.window.get_window()
        x=max(area.x,min(x,area.x+area.width-win.get_width()))
        y=area.y if self.collapsed else max(area.y,min(y,area.y+area.height-win.get_height()))
        self.window.move(x,y)
        return False

    def blocked(self):
        return (self.app.busy or Gtk.grab_get_current() is not None or
                any(isinstance(w, Gtk.Dialog) and w.get_visible()
                    for w in Gtk.Window.list_toplevels()))

    def pointer_inside(self):
        win = self.window.get_window()
        if win is None:
            return False
        pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
        _, px, py = pointer.get_position()
        _, x, y = win.get_origin()
        return x <= px < x + win.get_width() and y <= py < y + win.get_height()

    def tick(self):
        if not self.window.get_visible() or self.blocked():
            self.last_inside = time.monotonic()
            return True
        if self.pointer_inside():
            self.last_inside = time.monotonic()
            if self.collapsed:
                self.expand()
        elif not self.collapsed and time.monotonic() - self.last_inside >= self.IDLE_SECONDS:
            self.collapse()
        return True

    def collapse(self):
        if self.collapsed or self.blocked() or not self.window.get_visible():
            return
        win = self.window.get_window()
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_window(win)
        geometry = monitor.get_workarea()
        _, x, _ = win.get_origin()
        width = win.get_width()
        x = max(geometry.x, min(x, geometry.x + geometry.width - width))
        self.transitioning = True
        self.collapsed = True
        strip_width = max(1, round(width / 3))
        self.strip.set_size_request(strip_width, self.STRIP_HEIGHT)
        self.body.hide()
        self.window.resize(strip_width, self.STRIP_HEIGHT)
        self.window.move(x, geometry.y)
        GLib.idle_add(self.settled)

    def expand(self):
        if not self.collapsed:
            return
        self.transitioning = True
        self.collapsed = False
        self.body.show()
        self.strip.set_size_request(-1, self.STRIP_HEIGHT)
        size = self.window.get_preferred_size()[1]
        self.window.resize(size.width, size.height)
        self.last_inside = time.monotonic()
        GLib.idle_add(self.settled)

    def settled(self):
        self.transitioning = False
        return False

    def stop(self, *args):
        if self.source:
            GLib.source_remove(self.source)
            self.source = None
