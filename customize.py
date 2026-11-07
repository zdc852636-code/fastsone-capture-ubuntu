"""Editable shortcuts and toolbar layouts for the GTK interface."""
from gi.repository import Gdk, Gtk

# Keep the original four setting keys so existing installations inherit their bindings.
GLOBAL_KEYS = {
    'quick_region': ('快速矩形截图', 'F3', 'region'),
    'ocr': ('截图识字', 'F4', 'ocr'),
    'region': ('矩形截图', '<Control>Print', 'region'),
    'full': ('全屏截图', 'Print', 'full'),
    'window': ('活动窗口', '<Alt>Print', 'window'),
    'object': ('点选窗口', '<Shift>Print', 'object'),
    'alt_region': ('矩形截图备用键', '<Control><Alt>a', 'region'),
    'alt_full': ('全屏截图备用键', '<Control><Alt>f', 'full'),
    'alt_window': ('活动窗口备用键', '<Control><Alt>w', 'window'),
    'free': ('手绘截图', '', 'free'), 'fixed': ('固定尺寸截图', '', 'fixed'),
    'scroll': ('滚动截图', '', 'scroll'), 'color': ('屏幕取色', '', 'color'),
    'ruler': ('屏幕标尺', '', 'ruler'),
    'record': ('开始或停止录像', '<Control><Alt>r', 'record'),
}
EDITOR_KEYS = {
    'open': ('打开图片', '<Control>o'), 'paste': ('导入剪贴板', '<Control>v'),
    'close': ('关闭标签', '<Control>w'), 'save': ('保存', '<Control>s'),
    'save_as': ('另存为', '<Control><Shift>s'), 'copy': ('复制图片', '<Control>c'),
    'undo': ('撤销', '<Control>z'), 'redo': ('重做', '<Control><Shift>z'),
    'delete': ('删除选中标注', 'Delete'), 'done': ('结束绘图', 'Escape'),
}
TOOLBARS = {
    'panel': dict(open='打开图片', active='活动窗口', window='点选窗口', region='矩形截图',
                  free='手绘截图', full='全屏截图', scroll='滚动截图', fixed='固定区域',
                  record='录像', output='输出目标', delay='延迟', settings='设置'),
    'editor': dict(open='打开', save='保存', draw='绘图', caption='标题', edge='边缘',
                   resize='尺寸', rotate='旋转', crop='裁剪', copy='复制', print='打印',
                   pin='贴图', undo='撤销', redo='重做'),
}
ZOOM_LEVELS = (10, 25, 50, 75, 100, 125, 150, 200, 300, 400, 600, 800)
ZOOM_CHOICES = ['适合窗口', *(f'{n}%' for n in ZOOM_LEVELS)]
MODS = (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK |
        Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.SUPER_MASK)


def binding(settings, group, action):
    defaults = GLOBAL_KEYS if group == 'hotkeys' else EDITOR_KEYS
    return settings.get(group, {}).get(action, defaults[action][1])


def display_chord(chord):
    if not chord:
        return ''
    key, mods = Gtk.accelerator_parse(chord)
    if not key:
        return chord
    prefixes = [(Gdk.ModifierType.CONTROL_MASK, 'Ctrl'), (Gdk.ModifierType.MOD1_MASK, 'Alt'),
                (Gdk.ModifierType.SHIFT_MASK, 'Shift'), (Gdk.ModifierType.SUPER_MASK, 'Super')]
    name = Gdk.keyval_name(key)
    return '+'.join([label for mask, label in prefixes if mods & mask] +
                    [name.upper() if len(name) == 1 else name])


def editor_action(settings, event):
    for action in EDITOR_KEYS:
        chord = binding(settings, 'editor_keys', action)
        if chord:
            key, mods = Gtk.accelerator_parse(chord)
            if Gdk.keyval_to_lower(event.keyval) == key and event.state & MODS == mods:
                return action
    return None


def parse_chord(text):
    text = text.strip()
    if not text:
        return ''
    if '+' in text and not text.startswith('<'):
        parts = [part.strip() for part in text.split('+')]
        aliases = {'ctrl': 'Control', 'control': 'Control', 'shift': 'Shift',
                   'alt': 'Alt', 'super': 'Super', 'win': 'Super'}
        if any(part.lower() not in aliases for part in parts[:-1]):
            raise ValueError('请使用 Ctrl、Alt、Shift 或 Super 组合键。')
        text = ''.join('<' + aliases[part.lower()] + '>' for part in parts[:-1]) + parts[-1]
    key, mods = Gtk.accelerator_parse(text)
    if not key or int(mods) & ~int(MODS) or not Gtk.accelerator_valid(key, mods):
        raise ValueError('按键名称无效，例如 F6 或 Ctrl+Alt+K。')
    return Gtk.accelerator_name(Gdk.keyval_to_lower(key), mods)


def read_bindings(entries):
    groups = {'hotkeys': {}, 'editor_keys': {}}
    used = {}
    for group, definitions in [('hotkeys', GLOBAL_KEYS), ('editor_keys', EDITOR_KEYS)]:
        for action, definition in definitions.items():
            label = definition[0]
            try:
                chord = parse_chord(entries[group, action].get_text())
            except ValueError as error:
                raise ValueError(f'{label}的快捷键有误。{error}') from error
            if chord:
                key, mods = Gtk.accelerator_parse(chord)
                if group == 'hotkeys' and not mods and Gdk.keyval_to_unicode(key) >= 32:
                    raise ValueError(f'{label}需要组合键或功能键，以免影响正常打字。')
                if chord in used:
                    raise ValueError(f'“{label}”和“{used[chord]}”使用了同一个快捷键。')
                used[chord] = label
            groups[group][action] = chord
    return groups


def key_page(settings):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
    outer.pack_start(Gtk.Label(label='输入 F6 或 Ctrl+Alt+K。清空可停用该快捷键。', xalign=0), False, False, 0)
    scroll = Gtk.ScrolledWindow()
    grid = Gtk.Grid(column_spacing=16, row_spacing=4, margin=4)
    scroll.add(grid)
    outer.pack_start(scroll, True, True, 0)
    entries = {}
    row = 0
    for group, title, definitions in [('hotkeys','全局快捷键',GLOBAL_KEYS), ('editor_keys','编辑器快捷键',EDITOR_KEYS)]:
        grid.attach(Gtk.Label(label=title, xalign=0), 0, row, 2, 1)
        row += 1
        for action, definition in definitions.items():
            grid.attach(Gtk.Label(label=definition[0], xalign=0), 0, row, 1, 1)
            entry = Gtk.Entry(hexpand=True)
            entry.set_text(display_chord(binding(settings, group, action)))
            grid.attach(entry, 1, row, 1, 1)
            entries[group, action] = entry
            row += 1
    reset = Gtk.Button(label='恢复默认快捷键')
    def reset_keys(*_):
        for (group, action), entry in entries.items():
            entry.set_text(display_chord(binding({}, group, action)))
    reset.connect('clicked', reset_keys)
    outer.pack_end(reset, False, False, 0)
    return outer, entries


def layout(settings, scope):
    defaults = TOOLBARS[scope]
    config = settings.get('toolbars', {}).get(scope, {})
    order = list(dict.fromkeys(k for k in config.get('order', []) if k in defaults))
    order.extend(k for k in defaults if k not in order)
    hidden = set(config.get('hidden', [])) & defaults.keys()
    hidden.discard('settings')
    return order, hidden


def apply_layout(row, widgets, settings, scope):
    order, hidden = layout(settings, scope)
    for index, action in enumerate(order):
        widget = widgets[action]
        row.reorder_child(widget, index)
        widget.set_no_show_all(action in hidden)
        if action in hidden:
            widget.hide()
        else:
            widget.show_all()


class LayoutPage(Gtk.Box):
    def __init__(self, settings):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
        self.models = {}
        self.scope = Gtk.ComboBoxText()
        self.scope.append('panel', '悬浮工具栏')
        self.scope.append('editor', '编辑器工具栏')
        self.pack_start(self.scope, False, False, 0)
        self.tree = Gtk.TreeView(reorderable=True)
        toggle = Gtk.CellRendererToggle()
        toggle.connect('toggled', self.toggle)
        self.tree.append_column(Gtk.TreeViewColumn('显示', toggle, active=0, activatable=3))
        self.tree.append_column(Gtk.TreeViewColumn('工具', Gtk.CellRendererText(), text=2))
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        self.pack_start(scroll, True, True, 0)
        for scope in TOOLBARS:
            model = Gtk.ListStore(bool, str, str, bool)
            self.fill(model, scope, settings)
            self.models[scope] = model
        self.scope.connect('changed', lambda choice: self.tree.set_model(self.models[choice.get_active_id()]))
        self.scope.set_active_id('panel')
        buttons = Gtk.Box(spacing=6)
        for title, callback in [('上移', lambda *_: self.move(-1)), ('下移', lambda *_: self.move(1)), ('恢复此栏默认布局', self.reset)]:
            button = Gtk.Button(label=title)
            button.connect('clicked', callback)
            buttons.pack_start(button, False, False, 0)
        self.pack_start(buttons, False, False, 0)

    @staticmethod
    def fill(model, scope, settings):
        order, hidden = layout(settings, scope)
        model.clear()
        for key in order:
            model.append((key not in hidden, key, TOOLBARS[scope][key], key != 'settings'))

    def toggle(self, renderer, path):
        row = self.tree.get_model()[path]
        if row[3]:
            row[0] = not row[0]

    def move(self, step):
        model, current = self.tree.get_selection().get_selected()
        if current is not None:
            index = model.get_path(current).get_indices()[0] + step
            if 0 <= index < len(model):
                model.swap(current, model[index].iter)

    def reset(self, *_):
        scope = self.scope.get_active_id()
        self.fill(self.models[scope], scope, {})

    def values(self):
        return {scope: {'order': [row[1] for row in model], 'hidden': [row[1] for row in model if not row[0]]}
                for scope, model in self.models.items()}
