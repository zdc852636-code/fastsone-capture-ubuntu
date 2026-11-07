"""Tabbed image workspace with an independent drawing workspace."""
from gi.repository import Gtk, Gdk
from classic_ui import style, tool
from customize import ZOOM_CHOICES, apply_layout, editor_action

class Workspace(Gtk.Window):
    def __init__(self, app):
        super().__init__(title='fastsone capture-LW-ubuntu · 编辑器')
        self.app=app; self.set_default_size(1180,800); style(self)
        self.connect('delete-event',self.hide_workspace)
        self.connect('key-press-event',self.key)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.add(outer)
        menu=Gtk.MenuBar(); outer.pack_start(menu,False,False,0)
        groups=[('文件', [('打开…',app.open_image),('从剪贴板导入',self.paste),('保存',lambda *_:self.call('save')),('另存为…',lambda *_:self.call('save',True)),('打印…',lambda *_:self.call('print_image')),('关闭标签',lambda *_:self.close_current())]),
                ('编辑',[('撤销',lambda *_:self.call('history',True)),('重做',lambda *_:self.call('history',False)),('复制图片',lambda *_:self.call('copy_image')),('绘图工具',lambda *_:self.call('drawing',True)),('裁剪',lambda *_:self.call('activate_tool','crop'))]),
                ('捕获',[(label,lambda w,mode=mode:app.capture(mode)) for label,mode in [('活动窗口','window'),('窗口 / 对象','object'),('矩形区域','region'),('手绘区域','free'),('整个屏幕','full'),('滚动窗口','scroll'),('固定尺寸区域','fixed')]]),
                ('图像',[('调整尺寸…',lambda *_:self.call('resize_image')),('顺时针旋转',lambda *_:self.call('rotate_image')),('水平翻转',lambda *_:self.call('flip_image')),('添加标题…',lambda *_:self.call('caption')),('边框与阴影',lambda *_:self.call('edge')),('转为灰度',lambda *_:self.call('grayscale'))]),
                ('工具',[('屏幕录像机',app.record),('屏幕取色器',lambda *_:app.capture('color')),('屏幕标尺',lambda *_:app.capture('ruler')),('设置',app.preferences)]),('帮助',[('使用说明',app.about)])]
        for label,items in groups:
            mi=Gtk.MenuItem(label=label); sub=Gtk.Menu(); mi.set_submenu(sub); menu.append(mi)
            for text,fn in items:
                child=Gtk.MenuItem(label=text); child.connect('activate',fn); sub.append(child)
        row=Gtk.Box(spacing=3,margin=5); outer.pack_start(row,False,False,0)
        tools=[('open','打开',app.open_image),('save','保存',lambda *_:self.call('save')),
               ('draw','绘图',lambda *_:self.call('drawing',True)),('caption','标题',lambda *_:self.call('caption')),
               ('edge','边缘',lambda *_:self.call('edge')),('resize','尺寸',lambda *_:self.call('resize_image')),
               ('rotate','旋转',lambda *_:self.call('rotate_image')),('crop','裁剪',lambda *_:self.call('activate_tool','crop')),
               ('copy','复制',lambda *_:self.call('copy_image')),('print','打印',lambda *_:self.call('print_image')),
               ('pin','贴图',lambda *_:self.pin()),('undo','撤销',lambda *_:self.call('history',True)),('redo','重做',lambda *_:self.call('history',False))]
        self.toolbar_row = row
        self.toolbar_widgets = {}
        for icon, label, callback in tools:
            widget = tool(icon, label, callback)
            self.toolbar_widgets[icon] = widget
            row.pack_start(widget, False, False, 0)
        self.apply_toolbar()
        self.syncing_zoom=False
        zoom=Gtk.ComboBoxText(); self.zoom=zoom
        for text in ZOOM_CHOICES: zoom.append_text(text)
        zoom.set_active(0); zoom.connect('changed',lambda w:self.call('zoom_to',w.get_active_text()) if not self.syncing_zoom else None)
        row.pack_end(zoom,False,False,3)
        self.notebook=Gtk.Notebook(scrollable=True); outer.pack_start(self.notebook,True,True,0)
        self.notebook.connect('switch-page',self.sync_zoom)
        self.show_all()
    def apply_toolbar(self):
        apply_layout(self.toolbar_row, self.toolbar_widgets, self.app.settings, 'editor')

    def sync_zoom(self,notebook,editor,index):
        choices=ZOOM_CHOICES
        self.syncing_zoom=True
        self.zoom.set_active(choices.index(editor.zoom) if editor.zoom in choices else 0)
        self.syncing_zoom=False

    def current(self):
        return self.notebook.get_nth_page(self.notebook.get_current_page())
    def call(self,name,*args):
        editor=self.current()
        if editor: return getattr(editor,name)(*args)
    def attach(self,editor,title=None):
        box=Gtk.Box(spacing=6); editor.tab_label=Gtk.Label(label=title or f'截图 {len(self.app.editors)}'); box.pack_start(editor.tab_label,False,False,0)
        close=Gtk.Button.new_from_icon_name('window-close-symbolic',Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE); close.connect('clicked',lambda *_:self.close(editor))
        box.pack_start(close,False,False,0); box.show_all()
        index=self.notebook.append_page(editor,box); self.notebook.set_tab_reorderable(editor,True)
        editor.show_all(); editor.drawing(False); self.notebook.set_current_page(index)
        self.show(); editor.drawing(False); self.present()
    def close(self,editor):
        if editor.dirty:
            d=Gtk.MessageDialog(transient_for=self,modal=True,buttons=Gtk.ButtonsType.NONE,text='截图尚未保存')
            d.format_secondary_text('是否在关闭标签前保存？'); d.add_buttons('取消',Gtk.ResponseType.CANCEL,'不保存',Gtk.ResponseType.NO,'保存',Gtk.ResponseType.YES)
            response=d.run(); d.destroy()
            if response not in (Gtk.ResponseType.YES,Gtk.ResponseType.NO): return
            if response==Gtk.ResponseType.YES and not editor.save(): return
        editor.destroy()
        if not self.app.editors: self.hide()
    def close_current(self):
        if self.current(): self.close(self.current())
    def hide_workspace(self,*args):
        # Hide the workspace, keeping unsaved tabs available for the next capture.
        self.hide(); return True
    def paste(self,*args):
        pix=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_image()
        if pix: self.app.edit(pix)
    def pin(self):
        if self.current(): self.app.pin(self.current().result())
    def key(self,w,event):
        if isinstance(self.get_focus(),(Gtk.Entry,Gtk.TextView)):return False
        e=self.current()
        action = editor_action(self.app.settings, event)
        handlers = {'open': self.app.open_image, 'paste': self.paste, 'close': self.close_current}
        if action in handlers:
            handlers[action]()
            return True
        return e.key(e, event) if e else False
