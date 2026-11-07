#!/usr/bin/python3
"""An independent GTK screenshot utility for Ubuntu X11."""
import argparse
import copy
import ctypes as C
import ctypes.util
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

import gi
# Ubuntu 24.04 / Python 3.12 helper, shipped from the signed Ubuntu archive.
vendor = Path(__file__).resolve().parent / 'vendor' / 'gi'
if vendor.is_dir():
    gi.__path__.append(str(vendor))
gi.require_foreign('cairo')
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango, PangoCairo
import cairo

NAME = 'fastsone capture-LW-ubuntu'
IDENT = 'fastsone-capture-lw-ubuntu'
ROOT = Path(__file__).resolve().parent
CONFIG = Path.home() / '.config' / IDENT
AUTOSTART = Path.home() / '.config/autostart' / (IDENT + '.desktop')
sys.path.insert(0,str(ROOT))
from classic_ui import style, tool, Icon
from workspace import Workspace
from panel import AutoHidePanel
from customize import (GLOBAL_KEYS, ZOOM_LEVELS, LayoutPage, apply_layout, binding,
                       key_page, read_bindings, editor_action, display_chord, TOOLBARS)
from storage import image_path, write_image as export_image, load_settings, write_settings


def notify_error(parent, text):
    d = Gtk.MessageDialog(transient_for=parent, modal=True,
                          message_type=Gtk.MessageType.ERROR,
                          buttons=Gtk.ButtonsType.CLOSE, text=text)
    d.run()
    d.destroy()


def button(label, callback, tip=None):
    b = Gtk.Button(label=label)
    b.connect('clicked', callback)
    if tip:
        b.set_tooltip_text(tip)
    return b


def render(pixbuf, operations, base=None):
    """Render in image coordinates; the same path is used for preview and export."""
    w, h = pixbuf.get_width(), pixbuf.get_height()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    if base is None:Gdk.cairo_set_source_pixbuf(cr,pixbuf,0,0)
    else:cr.set_source_surface(base)
    cr.paint()
    for op in operations:
        kind, a, b = op['kind'], op['a'], op['b']
        x, y = a
        dx, dy = b[0] - x, b[1] - y
        cr.save()
        cr.set_source_rgba(*op['color'])
        cr.set_line_width(op['width'])
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        if kind == 'pen':
            cr.move_to(*op['points'][0])
            for p in op['points'][1:]:
                cr.line_to(*p)
            if len(op['points']) == 1:
                cr.line_to(x + .1, y)
            cr.stroke()
        elif kind == 'line':
            cr.move_to(x,y); cr.line_to(*b); cr.stroke()
        elif kind == 'spotlight':
            cr.rectangle(0,0,w,h); cr.rectangle(min(x,b[0]),min(y,b[1]),abs(dx),abs(dy))
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD); cr.set_source_rgba(0,0,0,.55); cr.fill()
        elif kind == 'arrow':
            cr.move_to(x, y)
            cr.line_to(*b)
            cr.stroke()
            angle = math.atan2(dy, dx)
            length = max(14, op['width'] * 4)
            cr.move_to(*b)
            cr.line_to(b[0] - length * math.cos(angle - .45), b[1] - length * math.sin(angle - .45))
            cr.line_to(b[0] - length * math.cos(angle + .45), b[1] - length * math.sin(angle + .45))
            cr.close_path()
            cr.fill()
        elif kind in ('rect', 'highlight'):
            cr.rectangle(min(x, b[0]), min(y, b[1]), abs(dx), abs(dy))
            if kind == 'highlight':
                cr.set_source_rgba(*op['color'][:3], .3)
                cr.fill()
            else:
                cr.stroke()
        elif kind == 'ellipse' and abs(dx) > 1 and abs(dy) > 1:
            cr.translate(x + dx / 2, y + dy / 2)
            cr.scale(abs(dx) / 2, abs(dy) / 2)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.save()
            cr.set_source_rgba(*op['color'])
            cr.set_line_width(op['width'])
            cr.stroke()
        elif kind in ('mosaic','blur') and abs(dx) >= 2 and abs(dy) >= 2:
            rx, ry = max(0, int(min(x, b[0]))), max(0, int(min(y, b[1])))
            rw,rh=min(w,int(max(x,b[0])))-rx,min(h,int(max(y,b[1])))-ry
            if rw<=0 or rh<=0:
                cr.restore(); continue
            # Capture earlier annotations too, so text beneath the mosaic is covered.
            surface.flush()
            patch = Gdk.pixbuf_get_from_surface(surface, rx, ry, rw, rh)
            if patch:
                if kind=='blur':
                    from PIL import ImageFilter
                    from storage import pil_image,pixbuf_image
                    large=pixbuf_image(pil_image(patch).filter(ImageFilter.GaussianBlur(12)))
                else:
                    small = patch.scale_simple(max(1, rw // 14), max(1, rh // 14), GdkPixbuf.InterpType.BILINEAR)
                    large = small.scale_simple(rw, rh, GdkPixbuf.InterpType.NEAREST)
                cr.rectangle(rx, ry, rw, rh)
                cr.clip()
                Gdk.cairo_set_source_pixbuf(cr, large, rx, ry)
                cr.paint()
        elif kind in ('text', 'number', 'callout'):
            size = op.get('size', 24)
            if kind == 'number':
                cr.arc(x, y, size * .72, 0, 2 * math.pi)
                cr.fill()
                cr.set_source_rgb(1, 1, 1)
            layout = PangoCairo.create_layout(cr)
            font = Pango.FontDescription('Sans Bold' if kind == 'number' else 'Sans')
            font.set_absolute_size(size * Pango.SCALE)
            layout.set_font_description(font)
            layout.set_text(op['text'], -1)
            tw, th = layout.get_pixel_size()
            if kind=='callout':
                cr.set_source_rgb(1,.96,.74); cr.rectangle(x-8,y-5,tw+16,th+10); cr.fill_preserve()
                cr.set_source_rgba(*op['color']); cr.stroke()
                cr.move_to(x+12,y+th+5); cr.line_to(x+3,y+th+23); cr.line_to(x+34,y+th+5); cr.close_path()
                cr.set_source_rgb(1,.96,.74); cr.fill_preserve(); cr.set_source_rgba(*op['color']); cr.stroke()
            cr.move_to(x - tw / 2 if kind == 'number' else x,
                       y - th / 2 if kind == 'number' else y)
            PangoCairo.show_layout(cr, layout)
        cr.restore()
    surface.flush()
    return surface


def to_pixbuf(surface):
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, surface.get_width(), surface.get_height())


class Editor(Gtk.Box):
    def __init__(self, app, pixbuf):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.filename=None; self.dirty=True; self.zoom='适合窗口'; self.selected=None; self.drag=None
        self._render_cache=None
        self.app = app
        self.pixbuf = pixbuf
        self.ops, self.undo_stack, self.redo_stack = [], [], []
        self.preview = None
        self.tool = 'select'
        self.scale, self.offset = 1., (0., 0.)
        self.connect('destroy', lambda *_: app.editors.remove(self) if self in app.editors else None)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.get_style_context().add_class('lw-classic')
        self.pack_start(outer,True,True,0)
        row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=20)
        self.tools = {}; self.choosing=False
        for label, kind in [('选择 / 移动','select'), ('箭头','arrow'), ('直线','line'), ('矩形','rect'), ('椭圆','ellipse'), ('画笔','pen'),
                            ('文字','text'), ('气泡','callout'), ('高亮','highlight'), ('聚光灯','spotlight'), ('模糊','blur'), ('马赛克','mosaic'), ('编号','number'), ('裁剪','crop')]:
            b = Gtk.ToggleButton(label=label)
            b.connect('toggled', lambda w,k=kind:self.choose(w,k) if w.get_active() else None)
            self.tools[kind] = b
            row.add(b)
        self.tools['select'].set_active(True)
        self.draw_row=row
        outer.pack_start(row, False, False, 0)
        options = Gtk.Box(spacing=8, margin_start=10, margin_end=10)
        self.draw_options=options
        options.get_style_context().add_class('draw-controls')
        options.pack_start(button('完成绘图',lambda *_:self.drawing(False)),False,False,0)
        self.color = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.parse('#f04438')
        self.color.set_rgba(rgba)
        options.pack_start(Gtk.Label(label='颜色'), False, False, 0)
        options.pack_start(self.color, False, False, 0)
        self.width = Gtk.SpinButton.new_with_range(1, 20, 1)
        self.width.set_value(3)
        options.pack_start(Gtk.Label(label='线宽'), False, False, 0)
        options.pack_start(self.width, False, False, 0)
        self.textsize = Gtk.SpinButton.new_with_range(12, 100, 2)
        self.textsize.set_value(26)
        options.pack_start(Gtk.Label(label='字号'), False, False, 0)
        options.pack_start(self.textsize, False, False, 0)
        options.pack_end(button('保存…', lambda *_: self.save()), False, False, 0)
        options.pack_end(button('复制', lambda *_: self.copy_image()), False, False, 0)
        options.pack_end(button('贴图', lambda *_: app.pin(self.result())), False, False, 0)
        options.pack_end(button('重做', lambda *_: self.history(False)), False, False, 0)
        options.pack_end(button('撤销', lambda *_: self.history(True)), False, False, 0)
        outer.pack_start(options, False, False, 0)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.canvas.connect('draw', self.draw)
        self.canvas.connect('button-press-event', self.press)
        self.canvas.connect('motion-notify-event', self.motion)
        self.canvas.connect('button-release-event', self.release)
        self.canvas.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.canvas.connect('scroll-event', self.wheel_zoom)
        self.canvas.connect_after('size-allocate', self.restore_zoom_anchor)
        self.zoom_anchor = None
        self.scroll_delta = 0.
        self.scroller=Gtk.ScrolledWindow()
        self.scroller.add(self.canvas)
        outer.pack_start(self.scroller, True, True, 0)
        self.status = Gtk.Label(label=f'{pixbuf.get_width()} × {pixbuf.get_height()} 像素 · 点击上方“绘图”添加标注', xalign=0, margin_start=8)
        self.status.get_style_context().add_class('status')
        outer.pack_start(self.status, False, False, 0)
        self.show_all()

    def choose(self, selected, kind):
        if self.choosing:return
        self.choosing=True
        self.tool=kind
        self.drag=None; self.preview=None
        for key,b in self.tools.items():b.set_active(key==kind)
        self.choosing=False

    def remember(self):
        self._render_cache=None
        self.dirty=True
        self.undo_stack.append((self.pixbuf, copy.deepcopy(self.ops)))
        self.undo_stack = self.undo_stack[-30:]
        self.redo_stack.clear()

    def history(self, undo):
        src, dst = (self.undo_stack, self.redo_stack) if undo else (self.redo_stack, self.undo_stack)
        if src:
            dst.append((self.pixbuf, copy.deepcopy(self.ops)))
            self.pixbuf, self.ops = src.pop()
            self.dirty=True; self.selected=None; self._render_cache=None
            self.zoom_to(self.zoom)

    def redraw(self):
        self._render_cache=None
        self.canvas.queue_draw()

    def surface(self):
        if self._render_cache is None:self._render_cache=render(self.pixbuf,self.ops)
        return self._render_cache

    def result(self):
        return to_pixbuf(self.surface())

    def draw(self, widget, cr):
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        self.scale = max(.01,min((w-24)/iw,(h-24)/ih,1.)) if self.zoom=='适合窗口' else float(self.zoom.strip('%'))/100
        self.offset = ((w - iw * self.scale) / 2, (h - ih * self.scale) / 2)
        cr.set_source_rgb(.56,.57,.57)
        cr.paint()
        cr.translate(*self.offset)
        cr.scale(self.scale, self.scale)
        surface=self.surface()
        if self.preview and self.tool!='crop':surface=render(self.pixbuf,[self.preview],base=surface)
        cr.set_source_surface(surface)
        cr.paint()
        if self.preview and self.tool == 'crop':
            a, b = self.preview['a'], self.preview['b']
            cr.set_source_rgb(.2, .7, 1)
            cr.set_line_width(2 / self.scale)
            cr.rectangle(a[0], a[1], b[0] - a[0], b[1] - a[1])
            cr.stroke()

    def point(self, event):
        return (min(self.pixbuf.get_width()-1, max(0, (event.x-self.offset[0])/self.scale)),
                min(self.pixbuf.get_height()-1, max(0, (event.y-self.offset[1])/self.scale)))

    def press(self, widget, event):
        if event.button != 1:
            return
        a = self.point(event)
        if self.tool=='select':
            self.selected=None
            for index in reversed(range(len(self.ops))):
                op=self.ops[index]; x,y=op['a']; bx,by=op['b']
                if op['kind'] in ('text','number','callout'): bx=x+max(30,len(op['text'])*op.get('size',24)); by=y+op.get('size',24)*1.5
                if min(x,bx)-12<=a[0]<=max(x,bx)+12 and min(y,by)-12<=a[1]<=max(y,by)+12:
                    self.selected=index; self.drag=(a,copy.deepcopy(op),False); break
            self.redraw(); return
        color = self.color.get_rgba()
        op = dict(kind=self.tool, a=a, b=a, color=(color.red,color.green,color.blue,1),
                  width=self.width.get_value(), size=self.textsize.get_value(), points=[a])
        if self.tool in ('text','callout'):
            d = Gtk.Dialog(title='输入标注文字', transient_for=self.app.workspace, modal=True)
            d.add_buttons('取消', Gtk.ResponseType.CANCEL, '添加', Gtk.ResponseType.OK)
            entry = Gtk.Entry(activates_default=True, width_chars=35)
            d.get_content_area().pack_start(entry, True, True, 14)
            d.set_default_response(Gtk.ResponseType.OK)
            d.show_all()
            response = d.run()
            text = entry.get_text()
            d.destroy()
            if response == Gtk.ResponseType.OK and text.strip():
                self.remember()
                op['text'] = text
                self.ops.append(op)
                self.redraw()
        elif self.tool == 'number':
            self.remember()
            op['text'] = str(1 + sum(o['kind'] == 'number' for o in self.ops))
            self.ops.append(op)
            self.redraw()
        else:
            self.preview = op

    def motion(self, widget, event):
        if self.drag and self.selected is not None:
            start,original,remembered=self.drag
            if not remembered: self.remember(); self.drag=(start,original,True)
            p=self.point(event); dx,dy=p[0]-start[0],p[1]-start[1]
            op=copy.deepcopy(original)
            for key in ('a','b'): op[key]=(original[key][0]+dx,original[key][1]+dy)
            if 'points' in original: op['points']=[(x+dx,y+dy) for x,y in original['points']]
            self.ops[self.selected]=op; self.redraw(); return
        if self.preview:
            p = self.point(event)
            self.preview['b'] = p
            if self.tool == 'pen':
                self.preview['points'].append(p)
            self.canvas.queue_draw()

    def release(self, widget, event):
        if self.drag: self.drag=None; return
        if event.button != 1 or not self.preview:
            return
        self.preview['b'] = self.point(event)
        op, self.preview = self.preview, None
        a, b = op['a'], op['b']
        if self.tool == 'crop':
            x, y = int(min(a[0], b[0])), int(min(a[1], b[1]))
            w, h = int(abs(b[0]-a[0])), int(abs(b[1]-a[1]))
            if w >= 2 and h >= 2:
                self.remember()
                self.pixbuf = self.result().new_subpixbuf(x, y, w, h).copy()
                self.ops = []; self.selected=None; self.drag=None; self._render_cache=None
                self.zoom_to(self.zoom)
        elif self.tool == 'pen' or math.dist(a, b) >= 2:
            self.remember()
            self.ops.append(op)
        self.redraw()

    def copy_image(self):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_image(self.result())
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).store()
        self.status.set_text('已复制到剪贴板')

    def write_image(self,path):
        path=export_image(self.result(),path)
        self.filename=path; self.dirty=False
        self.app.settings['save_dir']=str(path.parent)
        try:self.app.persist()
        except OSError:
            self.status.set_text('截图已保存，但无法记住保存目录：'+str(path))
        else:self.status.set_text('已保存：'+str(path))
        if hasattr(self,'tab_label'):self.tab_label.set_text(path.name)
        return path

    def save(self,save_as=False):
        if self.filename and not save_as and image_path(self.filename)==self.filename:
            try: self.write_image(self.filename); return True
            except Exception as e: notify_error(self.app.workspace,'保存失败：'+str(e)); return False
        d=Gtk.FileChooserDialog(title='另存为 · PNG / JPEG / BMP / TIFF / WebP / PDF',transient_for=self.app.workspace,action=Gtk.FileChooserAction.SAVE)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'保存',Gtk.ResponseType.OK); d.set_do_overwrite_confirmation(True)
        folder=Path(self.app.settings.get('save_dir',str(Path.home()/'Pictures')))
        d.set_current_folder(str(folder if folder.is_dir() else Path.home()))
        d.set_current_name(self.filename.name if self.filename else '截图-'+GLib.DateTime.new_now_local().format('%Y%m%d-%H%M%S')+'.png')
        success=False
        if d.run()==Gtk.ResponseType.OK:
            try:
                chosen=Path(d.get_filename()); target=image_path(chosen)
                overwrite=True
                if target!=chosen and target.exists():
                    confirm=Gtk.MessageDialog(transient_for=d,modal=True,buttons=Gtk.ButtonsType.YES_NO,text='替换已有图片？')
                    confirm.format_secondary_text(str(target)); overwrite=confirm.run()==Gtk.ResponseType.YES; confirm.destroy()
                if overwrite:self.write_image(target); success=True
            except Exception as e: notify_error(self.app.workspace,'保存失败：'+str(e))
        d.destroy(); return success

    def drawing(self,enabled):
        self.draw_row.set_visible(enabled); self.draw_options.set_visible(enabled)
        if enabled: self.activate_tool('arrow')
        else: self.tool='select'; self.preview=None

    def activate_tool(self,kind):
        self.choose(None,kind)
        self.status.set_text('拖动选区裁剪，松开即应用' if kind=='crop' else '拖动绘制，使用选择工具可移动标注')

    def wheel_zoom(self, widget, event):
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            self.scroll_delta = 0.
            return False
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            valid, _, delta = event.get_scroll_deltas()
            if not valid:
                return False
            self.scroll_delta += delta
            if abs(self.scroll_delta) < 1:
                return True
            upward = self.scroll_delta < 0
            self.scroll_delta = 0.
        elif event.direction in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.DOWN):
            upward = event.direction == Gdk.ScrollDirection.UP
        else:
            return False
        current = self.scale * 100 if self.zoom == '适合窗口' else float(self.zoom[:-1])
        choices = ZOOM_LEVELS if upward else reversed(ZOOM_LEVELS)
        target = next((level for level in choices if (level > current + .01 if upward else level < current - .01)), None)
        if target is None:
            return True
        hx, vy = self.scroller.get_hadjustment(), self.scroller.get_vadjustment()
        point = self.point(event)
        view_x, view_y = event.x - hx.get_value(), event.y - vy.get_value()
        self.zoom_to(f'{target}%')
        self.zoom_anchor = (point, view_x, view_y, target / 100)
        return True

    def restore_zoom_anchor(self, widget, allocation):
        if self.zoom_anchor is None:
            return
        point, x, y, scale = self.zoom_anchor
        self.zoom_anchor = None
        offset_x = (allocation.width - self.pixbuf.get_width() * scale) / 2
        offset_y = (allocation.height - self.pixbuf.get_height() * scale) / 2
        self.scroller.get_hadjustment().set_value(offset_x + point[0] * scale - x)
        self.scroller.get_vadjustment().set_value(offset_y + point[1] * scale - y)

    def zoom_to(self,text):
        self.zoom=text
        self.zoom_anchor = None
        if self.app.workspace and self.app.workspace.current() is self:
            self.app.workspace.sync_zoom(None, self, 0)
        if text=='适合窗口': self.canvas.set_size_request(1,1)
        else:
            factor=float(text.strip('%'))/100
            self.canvas.set_size_request(int(self.pixbuf.get_width()*factor)+24,int(self.pixbuf.get_height()*factor)+24)
        self.canvas.queue_draw()

    def replace_image(self,pix):
        self.remember(); self.pixbuf=pix; self.ops=[]; self.selected=None; self.zoom_to(self.zoom)

    def resize_image(self):
        d=Gtk.Dialog(title='调整图像尺寸',transient_for=self.app.workspace,modal=True)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'确定',Gtk.ResponseType.OK)
        box=d.get_content_area(); width=Gtk.SpinButton.new_with_range(1,20000,1); height=Gtk.SpinButton.new_with_range(1,20000,1)
        width.set_value(self.pixbuf.get_width()); height.set_value(self.pixbuf.get_height())
        lock=Gtk.CheckButton(label='保持宽高比'); lock.set_active(True)
        ratio=self.pixbuf.get_height()/self.pixbuf.get_width()
        width.connect('value-changed',lambda w:height.set_value(round(w.get_value()*ratio)) if lock.get_active() else None)
        for w in [Gtk.Label(label='宽度（像素）'),width,Gtk.Label(label='高度（像素）'),height,lock]: box.pack_start(w,False,False,4)
        d.show_all()
        if d.run()==Gtk.ResponseType.OK: self.replace_image(self.result().scale_simple(width.get_value_as_int(),height.get_value_as_int(),GdkPixbuf.InterpType.HYPER))
        d.destroy()

    def rotate_image(self): self.replace_image(self.result().rotate_simple(GdkPixbuf.PixbufRotation.CLOCKWISE))
    def flip_image(self): self.replace_image(self.result().flip(True))
    def grayscale(self):
        pix=self.result(); out=pix.copy(); pix.saturate_and_pixelate(out,0,False); self.replace_image(out)

    def caption(self):
        d=Gtk.Dialog(title='添加图像标题',transient_for=self.app.workspace,modal=True)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'确定',Gtk.ResponseType.OK)
        text=Gtk.Entry(placeholder_text='输入标题 / 说明'); d.get_content_area().pack_start(text,False,False,12); d.show_all()
        if d.run()==Gtk.ResponseType.OK and text.get_text():
            pix=self.result(); surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,pix.get_width(),pix.get_height()+54)
            c=cairo.Context(surface); c.set_source_rgb(1,1,1); c.paint(); Gdk.cairo_set_source_pixbuf(c,pix,0,0); c.paint()
            c.set_source_rgb(.1,.15,.2); layout=PangoCairo.create_layout(c); layout.set_text(text.get_text(),-1); layout.set_font_description(Pango.FontDescription('Sans 14')); c.move_to(14,pix.get_height()+14); PangoCairo.show_layout(c,layout)
            self.replace_image(to_pixbuf(surface))
        d.destroy()

    def edge(self):
        pix=self.result(); w,h=pix.get_width(),pix.get_height(); surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w+30,h+30)
        c=cairo.Context(surface); c.set_source_rgb(1,1,1); c.paint(); c.set_source_rgba(0,0,0,.2); c.rectangle(17,17,w,h); c.fill()
        c.set_source_rgb(.3,.3,.3); c.rectangle(9,9,w+2,h+2); c.stroke(); Gdk.cairo_set_source_pixbuf(c,pix,10,10); c.paint(); self.replace_image(to_pixbuf(surface))

    def print_image(self):
        pix=self.result(); op=Gtk.PrintOperation(); op.set_n_pages(1)
        def draw(operation,context,page):
            c=context.get_cairo_context(); factor=min(context.get_width()/pix.get_width(),context.get_height()/pix.get_height())
            c.scale(factor,factor); Gdk.cairo_set_source_pixbuf(c,pix,0,0); c.paint()
        op.connect('draw-page',draw)
        try: op.run(Gtk.PrintOperationAction.PRINT_DIALOG,self.app.workspace)
        except Exception as e: notify_error(self.app.workspace,str(e))

    def key(self, widget, event):
        action = editor_action(self.app.settings, event)
        if action == 'delete' and self.selected is not None:
            if self.selected < len(self.ops):
                self.remember()
                self.ops.pop(self.selected)
                self.selected = None
                self.redraw()
            return True
        handlers = {
            'done': lambda: self.drawing(False), 'save': self.save,
            'save_as': lambda: self.save(True), 'copy': self.copy_image,
            'undo': lambda: self.history(True), 'redo': lambda: self.history(False),
        }
        if action in handlers:
            handlers[action]()
            return True
        return False


class Selector(Gtk.Window):
    def __init__(self, app, pixbuf):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app, self.pixbuf = app, pixbuf
        self.a = self.b = None
        self.closed=False; self.grabbed=False; self.grab_source=None; self.grab_attempts=0
        self.click_capture=None; self.cancel_pending=False
        self.seat=Gdk.Display.get_default().get_default_seat()
        self.mode=app.pending_mode; self.points=[]; self.windows=[]
        if self.mode=='object':
            for w in reversed(Gdk.Screen.get_default().get_window_stack() or []):
                if w.is_visible():
                    r=w.get_frame_extents(); self.windows.append((r.x,r.y,r.width,r.height))
        self.set_decorated(False)
        self.set_keep_above(True)
        # Span the entire virtual desktop, including multiple monitors.
        self.set_default_size(pixbuf.get_width(), pixbuf.get_height())
        self.move(0, 0)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.realize()
        self.get_window().set_override_redirect(True)
        self.canvas = Gtk.DrawingArea()
        self.add(self.canvas)
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.canvas.connect('draw',self.dispatch,self.draw)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        # owner_events=False routes grabbed pointer events to the top-level
        # GdkWindow, not to the child DrawingArea. Listen at that same level.
        for name,method in [('button-press-event',self.press),('motion-notify-event',self.motion),('button-release-event',self.release)]:
            self.connect(name,self.dispatch,method)
        self.connect('key-press-event',self.dispatch,self.key)
        self.connect('grab-broken-event',self.grab_broken)
        self.connect('unmap',lambda *_:self.cleanup())
        self.connect('destroy',lambda *_:self.cleanup())
        self.show_all()
        self.get_window().set_cursor(Gdk.Cursor.new_for_display(Gdk.Display.get_default(),Gdk.CursorType.CROSSHAIR))
        # Acquire only after the overlay is mapped; a held global shortcut may
        # temporarily own the keyboard through the separate X11 connection.
        self.grab_source=GLib.timeout_add(25,self.acquire_input)

    def dispatch(self,widget,*args):
        if self.closed:return False
        method=args[-1]
        try:return method(widget,*args[:-1])
        except Exception as error:
            # Never destroy a widget while GTK still owns its draw context.
            # Release input immediately; dispose of the overlay at idle.
            self.cleanup()
            GLib.idle_add(self.abort_after_error,str(error))
            return True

    def abort_after_error(self,message):
        self.hide(); self.destroy()
        return self.report_error(message)

    def report_error(self,message):
        self.app.error('截图已取消，鼠标已释放：'+message)
        return False

    def acquire_input(self):
        if self.closed:self.grab_source=None; return False
        status=self.seat.grab(self.get_window(),Gdk.SeatCapabilities.POINTER|Gdk.SeatCapabilities.KEYBOARD,False,None,None,None,None)
        self.last_grab_status=status
        if status==Gdk.GrabStatus.SUCCESS:
            self.grabbed=True; self.grab_source=None; return False
        self.grab_attempts+=1
        if self.grab_attempts<80:return True
        self.grab_source=None
        self.finish()
        GLib.idle_add(self.report_error,'无法取得截图输入焦点，请松开快捷键后重试。')
        return False

    def grab_broken(self,widget,event):
        if self.grabbed and not self.closed:self.finish()
        return False

    def cleanup(self):
        if self.closed:return
        self.closed=True
        if self.grab_source:
            GLib.source_remove(self.grab_source); self.grab_source=None
        try:
            if self.grabbed:self.seat.ungrab()
        finally:
            self.grabbed=False
            Gdk.Display.get_default().flush()
            if self.app.selector is self:self.app.selector=None
            self.app.busy=False
            self.app.toolbar.show_all()


    def draw(self, widget, cr):
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
        cr.paint()
        cr.set_source_rgba(0, 0, 0, .38)
        cr.paint()
        if self.mode=='free' and len(self.points)>1:
            cr.save(); cr.move_to(*self.points[0])
            for p in self.points[1:]:cr.line_to(*p)
            cr.close_path(); cr.clip(); Gdk.cairo_set_source_pixbuf(cr,self.pixbuf,0,0); cr.paint(); cr.restore()
        if self.a and self.b:
            x,y,w,h = self.rect()
            cr.save()
            if self.mode!='free':
                cr.rectangle(x,y,w,h); cr.clip()
                Gdk.cairo_set_source_pixbuf(cr,self.pixbuf,0,0); cr.paint()
            cr.restore()
            cr.set_source_rgb(.25,.75,1)
            cr.set_line_width(2)
            cr.rectangle(x,y,w,h)
            cr.stroke()
            message = f'{w} × {h}  '+('单击完成 · Esc 取消' if self.mode in ('fixed','object') else '松开鼠标完成 · Esc 取消')
        else:
            message = {'object':'移动鼠标高亮窗口，单击截取 · Esc 取消','fixed':'移动鼠标定位固定区域，单击截取 · Esc 取消','free':'按住左键绘制轮廓，松开完成 · Esc 取消','color':'单击拾取颜色 · Esc 取消','scroll':'只框选滚动内容，不包含固定标题和侧栏 · Esc 取消'}.get(self.mode,'拖动选择截图区域 · Esc 取消')
        layout = PangoCairo.create_layout(cr)
        layout.set_text(message,-1)
        layout.set_font_description(Pango.FontDescription('Sans 13'))
        tw,th=layout.get_pixel_size()
        cr.set_source_rgba(.04,.08,.14,.95)
        cr.rectangle(20,20,tw+28,th+22)
        cr.fill()
        cr.set_source_rgb(1,1,1)
        cr.move_to(34,31)
        PangoCairo.show_layout(cr,layout)

    def coords(self, event):
        return (max(0,min(self.pixbuf.get_width(),int(event.x))), max(0,min(self.pixbuf.get_height(),int(event.y))))

    def locate(self,p):
        x,y=p; width,height=self.pixbuf.get_width(),self.pixbuf.get_height()
        if self.mode=='fixed':
            w=min(width,self.app.settings.get('fixed_width',640)); h=min(height,self.app.settings.get('fixed_height',480))
            left=max(0,min(width-w,x-w//2)); top=max(0,min(height-h,y-h//2))
            self.a=(left,top); self.b=(left+w,top+h)
        elif self.mode=='object':
            self.a=self.b=None
            for left,top,w,h in self.windows:
                if left<=x<left+w and top<=y<top+h:
                    self.a=(max(0,left),max(0,top)); self.b=(min(width,left+w),min(height,top+h)); break
        self.canvas.queue_draw()
    def press(self,w,e):
        if e.button==3:self.cancel_pending=True; return
        if e.button!=1:return
        p=self.coords(e)
        if self.mode=='color':
            x=min(p[0],self.pixbuf.get_width()-1); y=min(p[1],self.pixbuf.get_height()-1)
            self.click_capture=(self.pixbuf.new_subpixbuf(x,y,1,1).copy(),(x,y,1,1)); return
        if self.mode in ('object','fixed'):
            self.locate(p)
            if self.a and self.b:
                x,y,w,h=self.rect()
                if w>0 and h>0:self.click_capture=(self.pixbuf.new_subpixbuf(x,y,w,h).copy(),(x,y,w,h))
            return
        self.a=self.b=p; self.points=[p]
    def motion(self,w,e):
        p=self.coords(e)
        if self.mode in ('fixed','object'):self.locate(p); return
        if self.a:
            if self.mode=='free':
                self.points.append(p)
                self.a=(min(q[0] for q in self.points),min(q[1] for q in self.points))
                self.b=(max(q[0] for q in self.points),max(q[1] for q in self.points))
            else:self.b=p
            self.canvas.queue_draw()

    def rect(self):
        return (min(self.a[0],self.b[0]),min(self.a[1],self.b[1]),abs(self.a[0]-self.b[0]),abs(self.a[1]-self.b[1]))

    def release(self,w,e):
        if e.button==3 and self.cancel_pending:self.finish(); return
        if e.button!=1:return
        if self.click_capture:self.finish(*self.click_capture); return
        if self.mode in ('object','fixed','color'):return
        if self.a is None:return
        if self.mode!='free':self.b=self.coords(e)
        x,y,width,height=self.rect()
        if width<2 or height<2 or (self.mode=='free' and len(self.points)<3):self.finish(); return
        if width >= 2 and height >= 2:
            pix=self.pixbuf.new_subpixbuf(x,y,width,height).copy()
            if self.mode=='free':
                from PIL import Image,ImageDraw
                from storage import pil_image
                image=pil_image(pix).convert('RGBA'); mask=Image.new('L',image.size,0)
                ImageDraw.Draw(mask).polygon([(px-x,py-y) for px,py in self.points],fill=255); image.putalpha(mask)
                pix=GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(image.tobytes()),GdkPixbuf.Colorspace.RGB,True,8,width,height,width*4)
            self.finish(pix,(x,y,width,height))

    def key(self,w,e):
        if e.keyval == Gdk.KEY_Escape:
            self.finish(); return True
        return False

    def finish(self,pix=None,rect=None):
        if self.closed:return
        self.cleanup()
        self.hide()
        self.destroy()
        if pix is not None:GLib.idle_add(self.deliver_result,pix,rect)

    def deliver_result(self,pix,rect):
        try:self.app.finish_selection(pix,rect,mode=self.mode)
        except Exception as error:self.app.error('截图处理失败：'+str(error))
        return False


class Hotkeys:
    """Use a dedicated X connection, integrated into the GTK event loop."""
    def __init__(self, app):
        self.app=app
        self.lib=C.CDLL(ctypes.util.find_library('X11'))
        self.lib.XOpenDisplay.argtypes=[C.c_char_p]; self.lib.XOpenDisplay.restype=C.c_void_p
        self.lib.XDefaultRootWindow.argtypes=[C.c_void_p]; self.lib.XDefaultRootWindow.restype=C.c_ulong
        self.lib.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong]; self.lib.XKeysymToKeycode.restype=C.c_uint
        self.lib.XGrabKey.argtypes=[C.c_void_p,C.c_int,C.c_uint,C.c_ulong,C.c_int,C.c_int,C.c_int]
        self.lib.XPending.argtypes=[C.c_void_p]; self.lib.XNextEvent.argtypes=[C.c_void_p,C.c_void_p]
        self.lib.XFlush.argtypes=[C.c_void_p]
        self.lib.XConnectionNumber.argtypes=[C.c_void_p]; self.lib.XConnectionNumber.restype=C.c_int
        self.lib.XSetErrorHandler.argtypes=[C.c_void_p]; self.lib.XSetErrorHandler.restype=C.c_void_p
        self.error=False
        self.handler=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)(self.on_error)
        self.display = self.lib.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError('无法连接 X11')
        self.lib.XSync.argtypes = [C.c_void_p, C.c_int]
        self.lib.XUngrabKey.argtypes = [C.c_void_p, C.c_int, C.c_uint, C.c_ulong]
        self.root = self.lib.XDefaultRootWindow(self.display)
        self.codes = {}
        self.rebind(app.settings)
        self.source = GLib.io_add_watch(self.lib.XConnectionNumber(self.display), GLib.IO_IN, self.events)

    def ungrab(self, chord):
        code, mods = chord
        for locks in (0, 2, 16, 18):
            self.lib.XUngrabKey(self.display, code, mods | locks, self.root)

    def rebind(self, settings, changed=(), save=None):
        desired = {}
        labels = {}
        missing = []
        for action, (label, _, mode) in GLOBAL_KEYS.items():
            chord = binding(settings, 'hotkeys', action)
            if not chord:
                continue
            sym, mods = Gtk.accelerator_parse(chord)
            code = self.lib.XKeysymToKeycode(self.display, sym) if sym else 0
            if not code:
                missing.append(action)
                continue
            mask = int(mods) & (1 | 4 | 8)
            if mods & Gdk.ModifierType.SUPER_MASK:
                mask |= 64
            key = (code, mask)
            if key in desired:
                missing.append(action)
                continue
            desired[key] = mode
            labels[key] = action
        added = []
        previous = self.lib.XSetErrorHandler(C.cast(self.handler, C.c_void_p))
        try:
            for key in list(desired):
                if key in self.codes:
                    continue
                code, mask = key
                self.error = False
                for locks in (0, 2, 16, 18):
                    self.lib.XGrabKey(self.display, code, mask | locks, self.root, False, 1, 1)
                self.lib.XSync(self.display, False)
                if self.error:
                    self.ungrab(key)
                    missing.append(labels[key])
                    del desired[key]
                else:
                    added.append(key)
            conflicts = [name for name in missing if name in changed]
            if conflicts:
                for key in added:
                    self.ungrab(key)
                label = GLOBAL_KEYS[conflicts[0]][0]
                raise ValueError(f'“{label}”的按键被占用或键盘不支持，请换一个。')
            if save is not None:
                try:
                    save()
                except OSError:
                    for key in added:
                        self.ungrab(key)
                    raise
            for key in self.codes.keys() - desired.keys():
                self.ungrab(key)
            self.codes = desired
            self.error = bool(missing)
        finally:
            self.lib.XSync(self.display, False)
            self.lib.XSetErrorHandler(previous)

    def close(self):
        if getattr(self,'source',None):GLib.source_remove(self.source); self.source=None
        if getattr(self,'display',None):
            self.lib.XCloseDisplay.argtypes=[C.c_void_p]
            self.lib.XCloseDisplay(self.display); self.display=None

    def on_error(self,*args): self.error=True; return 0

    def events(self,*args):
        class Event(C.Structure):
            _fields_=[('type',C.c_int),('serial',C.c_ulong),('send_event',C.c_int),('display',C.c_void_p),
                      ('window',C.c_ulong),('root',C.c_ulong),('subwindow',C.c_ulong),('time',C.c_ulong),
                      ('x',C.c_int),('y',C.c_int),('x_root',C.c_int),('y_root',C.c_int),
                      ('state',C.c_uint),('keycode',C.c_uint),('same_screen',C.c_int),('padding',C.c_long*16)]
        while self.lib.XPending(self.display):
            e=Event(); self.lib.XNextEvent(self.display,C.byref(e))
            chord=(e.keycode,e.state & (1|4|8|64))
            if e.type == 2 and chord in self.codes and not self.app.configuring:
                mode=self.codes[chord]
                if mode=='record':
                    if self.app.recorder:self.app.recorder.stop()
                    else:self.app.record()
                else:self.app.capture(mode)
        return True


class App:
    def __init__(self):
        self.editors=[]; self.pins=[]; self.selector=None; self.busy=False
        self.workspace=None; self.recorder=None; self.scroll_session=None; self.pending_mode='region'; self.capture_timer=None
        CONFIG.mkdir(parents=True,exist_ok=True)
        self.settings=load_settings(CONFIG/'settings.json')
        self.position_source=None; self.last_settings=None
        self.ocr_running=False
        self.configuring = False
        self.toolbar=Gtk.Window(title=NAME); style(self.toolbar)
        self.toolbar.set_decorated(False); self.toolbar.set_keep_above(True)
        self.toolbar.set_accept_focus(False); self.toolbar.set_resizable(False)
        self.toolbar.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.toolbar.connect('delete-event',lambda *_:self.quit() or True)
        shell=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); self.toolbar.add(shell)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); shell.pack_start(outer,False,False,0)
        title=Gtk.EventBox(); title.get_style_context().add_class('panel-title')
        titlebox=Gtk.Box(spacing=3); title.add(titlebox)
        titlebox.pack_start(Gtk.Label(label='◩  '+NAME),True,True,0)
        close=Gtk.Button(label='×'); close.set_relief(Gtk.ReliefStyle.NONE); close.connect('clicked',self.quit)
        titlebox.pack_end(close,False,False,0)
        title.connect('button-press-event',lambda w,e:self.toolbar.begin_move_drag(e.button,int(e.x_root),int(e.y_root),e.time) if e.button==1 else None)
        outer.pack_start(title,False,False,0)
        row=Gtk.Box(spacing=1,margin=3); outer.pack_start(row,False,False,0)
        self.panel_row = row
        self.panel_widgets = {}
        for icon,label,fn in [('open','打开图片',self.open_image),('active','捕获活动窗口',lambda *_:self.capture('window')),
                              ('window','捕获窗口 / 对象',lambda *_:self.capture('object')),
                              ('region','捕获矩形区域',lambda *_:self.capture('region')),
                              ('free','捕获手绘区域',lambda *_:self.capture('free')),('full','捕获整个屏幕',lambda *_:self.capture('full')),
                              ('scroll','捕获滚动窗口',lambda *_:self.capture('scroll')),('fixed','捕获固定尺寸区域',lambda *_:self.capture('fixed')),
                              ('record','屏幕录像机',self.record)]:
            widget = tool(icon, label, fn, False)
            self.panel_widgets[icon] = widget
            row.pack_start(widget,False,False,0)
        self.output=Gtk.MenuButton(); outputbox=Gtk.Box(spacing=4)
        outputbox.pack_start(Icon('output'),False,False,0)
        self.destination_label=Gtk.Label(); outputbox.pack_start(self.destination_label,False,False,0)
        outputbox.pack_start(Gtk.Label(label='▾'),False,False,0); self.output.add(outputbox)
        self.output.set_tooltip_text('目标：选择截图完成后的去向'); row.pack_start(self.output,False,False,0)
        menu=Gtk.Menu(); group=None; self.destination_items={}
        self.destinations={'editor':'到编辑器','auto':'到文件夹','clipboard':'到剪贴板','file':'到文件…','draw':'到绘图','printer':'到打印机…'}
        for key,label in self.destinations.items():
            item=Gtk.RadioMenuItem.new_with_label(group,label); group=item.get_group()
            item.set_active(self.settings.get('destination','editor')==key)
            item.connect('toggled',lambda w,k=key:self.destination(k) if w.get_active() else None); menu.append(item)
            self.destination_items[key]=item
        menu.append(Gtk.SeparatorMenuItem())
        folderitem=Gtk.MenuItem(label='选择目标文件夹…'); folderitem.connect('activate',self.choose_destination_folder); menu.append(folderitem)
        openfolder=Gtk.MenuItem(label='打开目标文件夹'); openfolder.connect('activate',self.open_destination_folder); menu.append(openfolder)
        menu.append(Gtk.SeparatorMenuItem())
        copyitem=Gtk.CheckMenuItem(label='同时复制到剪贴板'); copyitem.set_active(self.settings.get('copy_always',False))
        copyitem.connect('toggled',lambda w:self.set_option('copy_always',w.get_active())); menu.append(copyitem)
        menu.show_all(); self.output.set_popup(menu); self.update_destination_label()
        delaybutton=Gtk.MenuButton(); delaybutton.add(Icon('delay')); delaybutton.get_style_context().add_class('panel-icon')
        delaybutton.set_tooltip_text('捕获前延迟（秒）'); popup=Gtk.Popover.new(delaybutton)
        db=Gtk.Box(spacing=5,margin=10); db.pack_start(Gtk.Label(label='延迟秒数'),False,False,0)
        self.delay=Gtk.SpinButton.new_with_range(0,10,1); self.delay.set_value(self.settings.get('delay',0)); db.pack_start(self.delay,False,False,0)
        popup.add(db); db.show_all(); delaybutton.set_popover(popup); row.pack_start(delaybutton,False,False,0)
        settings=Gtk.MenuButton(); settings.add(Icon('settings')); settings.get_style_context().add_class('panel-icon')
        settings.set_tooltip_text('设置与工具'); menu=Gtk.Menu()
        auto=Gtk.CheckMenuItem(label='登录后自动启动'); auto.set_active(AUTOSTART.exists()); auto.connect('toggled',self.autostart); menu.append(auto)
        for label,fn in [('设置…',self.preferences),('截图识字',lambda *_:self.capture('ocr')),('从剪贴板导入',self.paste_image),('显示编辑器',self.show_workspace),('屏幕取色器',lambda *_:self.capture('color')),('屏幕标尺',lambda *_:self.capture('ruler')),('使用说明',self.about),('退出',self.quit)]:
            item=Gtk.MenuItem(label=label); item.connect('activate',fn); menu.append(item)
        menu.show_all(); settings.set_popup(menu); row.pack_start(settings,False,False,0)
        self.panel_widgets.update(output=self.output, delay=delaybutton, settings=settings)
        apply_layout(row, self.panel_widgets, self.settings, 'panel')
        strip=Gtk.EventBox(); strip.get_style_context().add_class('panel-red-strip'); strip.set_size_request(-1,AutoHidePanel.STRIP_HEIGHT)
        shell.pack_end(strip,False,False,0)
        self.toolbar.move(*self.settings.get('position',[80,80])); self.toolbar.show_all()
        self.panel=AutoHidePanel(self,outer,strip)
        self.refresh_shortcut_labels()
        self.toolbar.connect('configure-event',self.position)
        try:
            self.hotkeys=Hotkeys(self)
            if self.hotkeys.error:self.toolbar.set_tooltip_text('部分全局快捷键被占用，可在设置中更改。')
        except Exception as e:self.toolbar.set_tooltip_text('全局快捷键不可用：'+str(e))

    def refresh_shortcut_labels(self):
        targets = {'active': 'window', 'window': 'object', 'region': 'region',
                   'full': 'full', 'record': 'record'}
        for icon, mode in targets.items():
            shortcuts = [display_chord(binding(self.settings, 'hotkeys', action))
                         for action, (_, _, target) in GLOBAL_KEYS.items() if target == mode]
            hint = ' / '.join(value for value in shortcuts if value)
            self.panel_widgets[icon].set_tooltip_text(TOOLBARS['panel'][icon] + (' · ' + hint if hint else ''))

    def set_option(self,key,value):
        self.settings[key]=value
        try:self.persist()
        except OSError as error:self.error('本次设置已生效，但无法保存供下次启动使用：'+str(error))
    def destination(self,key):
        self.set_option('destination',key); self.update_destination_label()
    def update_destination_label(self):
        key=self.settings.get('destination','editor')
        self.destination_label.set_text('目标：'+self.destinations.get(key,'到编辑器'))
        self.output.set_tooltip_text('截图目标：'+self.destinations.get(key,'到编辑器')+
                                     ('\n'+str(self.destination_folder()) if key=='auto' else ''))
    def destination_folder(self):
        return Path(self.settings.get('save_dir',str(Path.home()/'Pictures'))).expanduser()
    def choose_destination_folder(self,*args):
        d=Gtk.FileChooserDialog(title='选择截图目标文件夹',transient_for=self.toolbar,
                                action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'选择',Gtk.ResponseType.OK)
        d.set_current_folder(str(self.destination_folder()))
        try:
            if d.run()==Gtk.ResponseType.OK and d.get_filename():
                self.set_option('save_dir',d.get_filename())
                self.destination_items['auto'].set_active(True)
                self.update_destination_label()
        finally:d.destroy()
    def open_destination_folder(self,*args):
        try:
            folder=self.destination_folder(); folder.mkdir(parents=True,exist_ok=True)
            Gtk.show_uri_on_window(self.toolbar,folder.resolve().as_uri(),Gdk.CURRENT_TIME)
        except Exception as error:self.error('无法打开目标文件夹：'+str(error))
    def error(self,text): notify_error(self.workspace if self.workspace and self.workspace.get_visible() else self.toolbar,text)
    def inform(self,title,text):
        d=Gtk.MessageDialog(transient_for=self.workspace if self.workspace and self.workspace.get_visible() else self.toolbar,message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.CLOSE,text=title)
        d.format_secondary_text(text); d.run(); d.destroy()
    def show_workspace(self,*args):
        if self.workspace is None:self.workspace=Workspace(self)
        self.workspace.show_all()
        for e in self.editors:e.drawing(False)
        self.workspace.present()
    def paste_image(self,*args):
        pix=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_image()
        if pix:self.edit(pix)
        else:self.inform('剪贴板为空','请先复制一张图片。')
    def deliver(self,pix):
        dest=self.settings.get('destination','editor')
        if dest=='clipboard' or self.settings.get('copy_always'):
            clip=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD); clip.set_image(pix); clip.store()
        if dest=='clipboard':return
        if dest=='auto':
            try:
                folder=self.destination_folder(); folder.mkdir(parents=True,exist_ok=True)
                path=folder/('截图-'+GLib.DateTime.new_now_local().format('%Y%m%d-%H%M%S-%f')+'.png')
                export_image(pix,path)
            except Exception as e:self.error('自动保存失败：'+str(e)); self.edit(pix)
            return
        editor=self.edit(pix)
        if dest=='draw':editor.drawing(True)
        elif dest=='file':editor.save()
        elif dest=='printer':editor.print_image()
    def finish_selection(self,pix,rect=None,mode=None):
        mode=mode or self.pending_mode
        if mode=='ocr':self.recognize_text(pix)
        elif mode=='color':
            data=pix.get_pixels(); rgb=tuple(data[:3]); value='#%02X%02X%02X'%rgb
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(value,-1); self.inform('屏幕取色',value+'\nRGB '+str(rgb)+'\n已复制颜色值。')
        elif mode=='ruler':self.inform('屏幕标尺',f'宽度：{pix.get_width()} px\n高度：{pix.get_height()} px\n对角线：{math.hypot(pix.get_width(),pix.get_height()):.1f} px')
        elif mode=='scroll':
            from workflows import ScrollCapture
            self.busy=True; self.scroll_session=ScrollCapture(self,rect)
        elif mode=='record_region':self.start_record(rect)
        else:self.deliver(pix)

    def notify(self,title,message):
        self.toolbar.set_tooltip_text(title+'\n'+message)
        try:
            subprocess.Popen(['notify-send','--app-name',NAME,'--icon','accessories-text-editor',
                '--expire-time','3500','--',title,message],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError:pass

    def recognize_text(self,pix):
        if self.ocr_running:return
        from storage import pil_image
        from ocr import recognize_detailed
        image=pil_image(pix)
        self.ocr_running=True;self.notify('正在识别文字','完成后会自动复制，中英文均可。')
        def work():
            try:
                result=recognize_detailed(image)
                GLib.idle_add(self.ocr_done,result.text,None,result.needs_review)
            except Exception as error:GLib.idle_add(self.ocr_done,None,str(error))
        threading.Thread(target=work,daemon=True,name='screenshot-ocr').start()

    def ocr_done(self,text,error,needs_review=False):
        self.ocr_running=False
        if error:self.error(error)
        elif not text:self.notify('未识别到文字','请框选清晰文字后重试，原剪贴板内容已保留。')
        else:
            clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text,-1);clipboard.store()
            self.notify('文字已复制',f'已复制 {len(text)} 个字符，按 Ctrl+V 粘贴。'+
                ('\n部分文字不够确定，请核对原图。' if needs_review else ''))
        return False
    def xtest_scroll(self,rect,clicks):
        lib=self.hotkeys.lib; display=self.hotkeys.display
        lib.XWarpPointer.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_int]
        x,y,w,h=rect; root=lib.XDefaultRootWindow(display)
        lib.XWarpPointer(display,0,root,0,0,0,0,x+w//2,y+h//2)
        xt=C.CDLL(ctypes.util.find_library('Xtst')); xt.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        for i in range(clicks):xt.XTestFakeButtonEvent(display,5,True,0); xt.XTestFakeButtonEvent(display,5,False,35)
        lib.XFlush(display)
    def record(self,*args):
        if self.recorder:self.recorder.window.present(); return
        d=Gtk.Dialog(title='屏幕录像机',transient_for=self.toolbar,modal=True); style(d)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'开始录制…',Gtk.ResponseType.OK)
        box=d.get_content_area(); mode=Gtk.ComboBoxText()
        for text in ['整个屏幕','矩形区域']:mode.append_text(text)
        mode.set_active(0); box.pack_start(mode,False,False,5)
        audio=Gtk.ComboBoxText()
        for label in ['不录制声音','麦克风','系统声音']:audio.append_text(label)
        audio.set_active(0); box.pack_start(audio,False,False,5)
        box.pack_start(Gtk.Label(label='保存为 WebM · 15 FPS · 支持暂停 / 继续'),False,False,6)
        d.show_all(); response=d.run(); selection=mode.get_active(); self.record_audio=audio.get_active()>0; self.record_device='@DEFAULT_MONITOR@' if audio.get_active()==2 else ''; d.destroy()
        if response==Gtk.ResponseType.OK:
            if selection==1:self.capture('record_region')
            else:self.start_record(None)
    def start_record(self,rect):
        from workflows import Recorder
        recorder=Recorder(self,rect,getattr(self,'record_audio',False),getattr(self,'record_device',''))
        if recorder.pipeline and not recorder.finalized:self.recorder=recorder
    def preferences(self,*args):
        d=Gtk.Dialog(title='设置 · '+NAME,transient_for=self.toolbar,modal=True); style(d); d.set_default_size(500,390)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'应用',Gtk.ResponseType.OK)
        tabs=Gtk.Notebook(); d.get_content_area().pack_start(tabs,True,True,8)
        general=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9,margin=14)
        auto=Gtk.CheckButton(label='登录桌面后自动启动'); auto.set_active(AUTOSTART.exists()); general.pack_start(auto,False,False,0)
        folder=Gtk.FileChooserButton(title='自动保存目录'); folder.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        folder.set_filename(self.settings.get('save_dir',str(Path.home()/'Pictures')))
        general.pack_start(Gtk.Label(label='自动保存目录',xalign=0),False,False,0); general.pack_start(folder,False,False,0)
        dims=Gtk.Box(spacing=6); fw=Gtk.SpinButton.new_with_range(16,12000,1); fh=Gtk.SpinButton.new_with_range(16,12000,1)
        fw.set_value(self.settings.get('fixed_width',640)); fh.set_value(self.settings.get('fixed_height',480))
        for w in [Gtk.Label(label='固定区域'),fw,Gtk.Label(label='×'),fh]:dims.pack_start(w,False,False,0)
        general.pack_start(dims,False,False,0); tabs.append_page(general,Gtk.Label(label='捕获与保存'))
        keys, entries = key_page(self.settings)
        layout_page = LayoutPage(self.settings)
        tabs.append_page(keys, Gtk.Label(label='快捷键'))
        tabs.append_page(layout_page, Gtk.Label(label='图标布局'))
        d.set_default_size(560, 500)
        self.configuring = True
        try:
            d.show_all()
            while d.run() == Gtk.ResponseType.OK:
                try:
                    changes = read_bindings(entries)
                    changes.update(fixed_width=fw.get_value_as_int(), fixed_height=fh.get_value_as_int(),
                                   save_dir=folder.get_filename() or str(Path.home()/'Pictures'),
                                   toolbars=layout_page.values())
                    self.apply_preferences(changes)
                except (ValueError, OSError) as error:
                    notify_error(d, str(error))
                    continue
                self.autostart(auto)
                break
        finally:
            self.configuring = False
            d.destroy()

    def apply_preferences(self, changes):
        candidate = {**self.settings, **changes}
        changed = [action for action in GLOBAL_KEYS if Gtk.accelerator_parse(binding(self.settings, 'hotkeys', action))
                   != Gtk.accelerator_parse(binding(candidate, 'hotkeys', action))]
        keys = getattr(self, 'hotkeys', None)
        if changed and not keys:
            raise ValueError('当前桌面无法注册全局快捷键。')
        def save():
            write_settings(CONFIG/'settings.json', candidate)

        if keys:
            keys.rebind(candidate, changed, save)
        else:
            save()
        self.settings = candidate
        self.last_settings = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
        apply_layout(self.panel_row, self.panel_widgets, candidate, 'panel')
        self.refresh_shortcut_labels()
        if self.workspace:
            self.workspace.apply_toolbar()
        self.update_destination_label()

    def quit(self,*args):
        if self.ocr_running:
            self.notify('文字识别尚未完成','请稍候再退出。');return
        if self.selector:self.selector.finish()
        if self.capture_timer:GLib.source_remove(self.capture_timer); self.capture_timer=None; self.busy=False
        if self.recorder:
            self.inform('请先停止录像','点击录像控制窗口的“停止并保存”后再退出。'); self.recorder.window.present(); return
        if self.scroll_session:self.scroll_session.finish(False)
        if self.workspace:
            for e in list(self.editors):
                self.workspace.close(e)
                if e in self.editors:return
        if self.position_source:GLib.source_remove(self.position_source); self.save_position()
        if hasattr(self,'hotkeys'):self.hotkeys.close()
        self.panel.stop()
        Gtk.main_quit()

    def persist(self):
        data=json.dumps(self.settings,ensure_ascii=False,sort_keys=True)
        if data!=self.last_settings:
            write_settings(CONFIG/'settings.json',self.settings)
            self.last_settings=data

    def save_position(self):
        self.position_source=None
        try:self.persist()
        except OSError as error:print('无法保存工具栏位置：'+str(error),file=sys.stderr)
        return False

    def position(self,w,e):
        if not self.busy and not self.panel.collapsed and not self.panel.transitioning:
            self.settings['position']=[e.x,e.y]
            if self.position_source:GLib.source_remove(self.position_source)
            self.position_source=GLib.timeout_add(350,self.save_position)

    def autostart(self,item):
        try:
            if item.get_active():
                AUTOSTART.parent.mkdir(parents=True,exist_ok=True)
                AUTOSTART.write_text(desktop_entry())
            else: AUTOSTART.unlink(missing_ok=True)
        except OSError as e: notify_error(self.toolbar,'修改自动启动失败：'+str(e))

    def capture(self,mode):
        if self.busy:return
        if self.ocr_running:
            self.notify('正在识别文字','完成后即可再次截图。');return
        if mode=='ocr':
            try:
                from ocr import engine
                engine()
            except RuntimeError as error:self.error(str(error));return
        self.busy=True
        try:
            self.settings['delay']=self.delay.get_value_as_int(); self.persist()
            self.toolbar.hide()
            self.capture_timer=GLib.timeout_add(250+(0 if mode=='ocr' else 1000*self.delay.get_value_as_int()),self.take,mode)
        except Exception as error:
            self.busy=False; self.toolbar.show_all(); self.error('启动截图失败：'+str(error))

    def take(self,mode):
        self.capture_timer=None
        try:
            screen=Gdk.Screen.get_default()
            root=screen.get_root_window()
            pix=Gdk.pixbuf_get_from_window(root,0,0,root.get_width(),root.get_height())
            if pix is None: raise RuntimeError('屏幕读取失败')
            if mode in ('region','object','free','fixed','scroll','color','ruler','record_region','ocr'):
                self.pending_mode=mode
                self.selector=Selector(self,pix)
                return False
            if mode=='window':
                active=screen.get_active_window()
                if active is None: raise RuntimeError('没有可截取的活动窗口，请先选中目标窗口')
                _,x,y=active.get_origin()
                w,h=active.get_width(),active.get_height()
                left,top=max(0,x),max(0,y)
                right,bottom=min(pix.get_width(),x+w),min(pix.get_height(),y+h)
                if right<=left or bottom<=top: raise RuntimeError('活动窗口不在屏幕内')
                pix=pix.new_subpixbuf(left,top,right-left,bottom-top).copy()
            self.deliver(pix)
        except Exception as e:
            notify_error(self.toolbar,'截图失败：'+str(e))
        self.busy=False; self.toolbar.show_all()
        return False

    def edit(self,pix):
        if self.workspace is None:self.workspace=Workspace(self)
        editor=Editor(self,pix); self.editors.append(editor); self.workspace.attach(editor)
        return editor

    def pin(self,pix):
        win=Gtk.Window(title='LW 贴图 · Esc 关闭')
        win.set_keep_above(True)
        win.set_default_size(min(800,pix.get_width()),min(600,pix.get_height()))
        area=Gtk.DrawingArea(); win.add(area)
        def draw(w,cr):
            scale=min(w.get_allocated_width()/pix.get_width(),w.get_allocated_height()/pix.get_height())
            cr.scale(scale,scale); Gdk.cairo_set_source_pixbuf(cr,pix,0,0); cr.paint()
        area.connect('draw',draw)
        win.connect('key-press-event',lambda w,e:w.destroy() if e.keyval==Gdk.KEY_Escape else False)
        self.pins.append(win)
        win.connect('destroy',lambda *_:self.pins.remove(win))
        win.show_all()

    def open_image(self,*args):
        d=Gtk.FileChooserDialog(title='打开图片',transient_for=self.toolbar,action=Gtk.FileChooserAction.OPEN)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'打开',Gtk.ResponseType.OK)
        filt=Gtk.FileFilter(); filt.set_name('图片'); filt.add_pixbuf_formats(); d.add_filter(filt)
        if d.run()==Gtk.ResponseType.OK:
            try:
                path=Path(d.get_filename()); editor=self.edit(GdkPixbuf.Pixbuf.new_from_file(str(path)))
                editor.filename=path; editor.dirty=False; editor.tab_label.set_text(path.name)
            except Exception as e: notify_error(self.toolbar,str(e))
        d.destroy()

    def about(self,*args):
        self.inform(NAME+' · 2.6', '经典悬浮工具栏 → 输出目标 → 多标签编辑器 → 绘图\n\n活动窗口、窗口点选、矩形、手绘、全屏、固定尺寸与滚动拼接。\n滚动截图请只框选可滚动内容，排除固定标题及侧栏。\n录像为 WebM，支持区域、暂停与 PulseAudio 录音。\n\n默认快捷键（可在设置中更改）\nF4 框选识字到剪贴板 · F3 / Ctrl+Alt+A 区域 · Ctrl+Alt+F 全屏 · Ctrl+Alt+W 窗口\nCtrl+Alt+R 停止录像\nPrint 风格快捷键可在设置中更改。\n\nCtrl+S 保存 · Ctrl+C 复制 · Ctrl+V 导入 · Ctrl+Z 撤销\n编辑器关闭时保留未保存标签，退出软件时提示保存。\n\n适用 Ubuntu 24.04 X11。支持本地中英文 OCR（F4）。尚不支持 Wayland、FSC、Office 输出及视频剪辑。')


def desktop_entry():
    # Desktop Entry quoting rules differ from shell quoting.
    escaped=str(ROOT/'capture.py').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
    return f'[Desktop Entry]\nType=Application\nName={NAME}\nComment=截图、滚动长图、录屏与图像标注\nExec=/usr/bin/python3 "{escaped}"\nIcon=applets-screenshooter\nTerminal=false\nCategories=Utility;Graphics;\nStartupNotify=false\nX-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=6\n'


def main():
    parser=argparse.ArgumentParser(description=NAME)
    parser.add_argument('--version',action='version',version=NAME+' 2.6')
    parser.add_argument('--install',action='store_true',help='安装菜单入口并开启自动启动')
    args=parser.parse_args()
    if args.install:
        launcher=Path.home()/'.local/share/applications'/(IDENT+'.desktop')
        paths=[launcher]
        if not launcher.exists() and not AUTOSTART.exists():paths.append(AUTOSTART)
        for path in paths:
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(desktop_entry())
        print('已更新应用菜单入口；登录后自动启动：'+('开启' if AUTOSTART.exists() else '关闭'))
        return
    if not Gtk.init_check()[0]:
        sys.exit('无法连接桌面。请在 Ubuntu 图形会话中运行。')
    if os.environ.get('XDG_SESSION_TYPE')=='wayland':
        notify_error(None,'当前版本需要 X11。请在登录界面的齿轮菜单选择 Ubuntu on Xorg。'); return
    CONFIG.mkdir(parents=True,exist_ok=True)
    lock=(CONFIG/'app.lock').open('w')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: print('软件已运行，请使用悬浮工具栏或截图快捷键。'); return
    app=App()
    signal.signal(signal.SIGTERM,lambda *_:Gtk.main_quit())
    signal.signal(signal.SIGINT,lambda *_:Gtk.main_quit())
    Gtk.main()


if __name__=='__main__': main()
