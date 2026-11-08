"""Original vector icons and a classic desktop theme."""
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk
import math

CSS=b'''
.lw-classic { background: #ece9df; color: #18202b; font-family: Sans; font-size: 12px; }
.lw-classic button { background-image: linear-gradient(#fffefb,#e4e1d7); color:#18202b; border:1px solid #aaa99e; border-radius:2px; box-shadow:none; padding:4px 7px; min-height:20px; }
.lw-classic button:hover { background-image:linear-gradient(#fffbe5,#f6d99c); border-color:#c8983a; }
.lw-classic button:checked { background-image:none; background-color:#f6d79a; border-color:#ba8b30; }
.lw-classic .panel-icon { padding:2px; min-width:25px; min-height:25px; border-color:transparent; background:none; }
.lw-classic .panel-icon:hover { border-color:#cb963d; background:#fff0ca; }
.lw-classic .panel-red-strip { background:#df2727; min-height:6px; }
.lw-classic .panel-title { background-image:linear-gradient(#fcfcfa,#d6d4ca); color:#1a2531; padding:3px 5px; font-size:11px; }
.lw-classic menubar, .lw-classic menu { background:#f4f2eb; color:#18202b; }
.lw-classic menuitem { color:#18202b; }
.lw-classic flowbox, .lw-classic flowboxchild, .lw-classic .draw-controls { background:#ece9df; color:#18202b; }
.lw-classic menuitem:hover { background:#c9dff0; }
.lw-classic notebook header { background:#e7e4da; }
.lw-classic notebook tab { background:#dedbd1; color:#1e2935; padding:4px 10px; }
.lw-classic notebook tab:checked { background:#fffdf5; border-top:2px solid #df9b31; }
.lw-classic entry, .lw-classic spinbutton, .lw-classic combobox { color:#18202b; background:#fff; }
.lw-classic .status { background:#e6e3da; color:#3f4853; padding:5px; }
.lw-preferences { font-size: 1.12em; }
.lw-preferences .shortcut-group { font-weight: bold; margin-top: 6px; }
.lw-preferences treeview.view { -GtkTreeView-vertical-separator: 6; }
'''

_styled_screens=set()

def style(widget):
    screen=widget.get_screen()
    if screen not in _styled_screens:
        provider=Gtk.CssProvider(); provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(screen,provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _styled_screens.add(screen)
    widget.get_style_context().add_class('lw-classic')

class Icon(Gtk.DrawingArea):
    def __init__(self,kind,size=23):
        super().__init__(); self.kind=kind; self.set_size_request(size,size); self.connect('draw',self.draw)
    def draw(self,w,c):
        c.scale(w.get_allocated_width()/24,w.get_allocated_height()/24)
        c.set_line_width(1.3); c.set_line_join(1); c.set_line_cap(1)
        k=self.kind
        def rect(x,y,w,h,fill=None):
            c.rectangle(x,y,w,h)
            if fill: c.set_source_rgb(*fill); c.fill_preserve()
            c.set_source_rgb(.17,.24,.32); c.stroke()
        def line(points,color=(.12,.28,.48)):
            c.set_source_rgb(*color); c.move_to(*points[0])
            for p in points[1:]: c.line_to(*p)
            c.stroke()
        if k in ('active','window','region','full','scroll','fixed','free','record'):
            rect(3,5,18,15,(.96,.98,1)); rect(3,5,18,3,(.34,.58,.8))
            if k=='active': rect(6,11,12,6,(.8,.9,.98))
            if k=='window': rect(10,12,11,8,(1,.9,.6)); line([(13,9),(13,16),(19,16)])
            if k=='region':
                c.set_dash([2,2]); rect(7,10,10,7); c.set_dash([])
            if k=='full':
                for x,y,sx,sy in [(6,10,1,1),(18,10,-1,1),(6,17,1,-1),(18,17,-1,-1)]: line([(x,y+sy*3),(x,y),(x+sx*3,y)])
            if k=='free': line([(7,12),(12,9),(16,13),(13,18),(7,16),(7,12)],(.75,.25,.2))
            if k=='scroll': line([(12,10),(12,18),(9,15),(12,18),(15,15)],(.2,.5,.24))
            if k=='fixed': rect(7,10,10,7,(.95,.9,.68)); line([(8,13),(16,13)])
            if k=='record':
                c.set_source_rgb(.83,.12,.1); c.arc(12,14,4,0,math.tau); c.fill()
        elif k=='history':
            rect(4,4,16,18,(.9,.95,.99)); rect(8,2,8,4,(.55,.69,.8))
            for y in (10,14,18):line([(8,y),(16,y)])
        elif k=='open':
            rect(4,5,10,11,(.9,.92,.95)); c.move_to(2,11); c.line_to(22,11); c.line_to(18,21); c.line_to(3,21); c.close_path(); c.set_source_rgb(.94,.7,.25); c.fill_preserve(); c.set_source_rgb(.5,.37,.1); c.stroke()
        elif k=='save':
            rect(4,3,16,18,(.35,.56,.78)); rect(7,3,10,6,(.94,.96,1)); rect(7,13,10,8,(1,1,1))
        elif k=='copy': rect(4,3,12,15,(.9,.94,1)); rect(9,8,12,15,(1,1,1))
        elif k=='draw':
            line([(5,20),(17,5)],(.78,.2,.13)); line([(4,21),(7,20),(5,18),(4,21)])
        elif k=='crop': line([(7,2),(7,18),(22,18)]); line([(2,7),(18,7),(18,22)])
        elif k=='resize': rect(3,10,11,11,(.88,.93,.98)); line([(12,11),(21,2),(15,2),(21,2),(21,8)])
        elif k=='print': rect(6,2,12,8,(1,1,1)); rect(3,9,18,10,(.72,.75,.79)); rect(6,15,12,8,(1,1,1))
        elif k=='output':
            for i,color in enumerate([(.8,.2,.2),(.9,.7,.1),(.2,.55,.8)]): c.set_source_rgb(*color); c.arc(6+i*6,12,3,0,math.tau); c.fill()
        elif k=='settings':
            c.set_source_rgb(.35,.44,.52); c.arc(12,12,7,0,math.tau); c.stroke(); c.arc(12,12,3,0,math.tau); c.stroke()
            for a in range(8): line([(12+8*math.cos(a*math.pi/4),12+8*math.sin(a*math.pi/4)),(12+10*math.cos(a*math.pi/4),12+10*math.sin(a*math.pi/4))])
        elif k=='delay':
            c.set_source_rgb(.2,.35,.52); c.arc(12,14,8,0,math.tau); c.stroke(); line([(12,8),(12,14),(16,14)]); line([(9,2),(15,2)])
        elif k in ('undo','redo'):
            c.save()
            if k=='redo': c.translate(24,0); c.scale(-1,1)
            line([(6,8),(3,12),(8,15)],(.17,.46,.67)); c.set_source_rgb(.17,.46,.67); c.arc(12,15,7,math.pi,math.tau*1.13); c.stroke(); c.restore()
        elif k=='pin': line([(7,4),(18,4),(16,12),(20,15),(6,15),(10,12),(7,4)],(.6,.2,.2)); line([(13,15),(10,23)])
        elif k=='rotate': line([(7,6),(12,3),(19,6),(21,14),(17,20),(9,21)],(.17,.45,.65)); line([(7,2),(7,6),(12,7)])
        elif k=='edge': rect(3,4,18,16,(.7,.75,.8)); rect(5,6,13,10,(.97,.98,1))
        elif k=='caption':
            c.set_source_rgb(.2,.3,.5); c.select_font_face('Sans'); c.set_font_size(19); c.move_to(4,20); c.show_text('T')
        elif k=='color':
            for i,color in enumerate([(.9,.2,.2),(.2,.65,.3),(.2,.4,.9)]): c.set_source_rgb(*color); c.arc(8+i*4,10+(i%2)*6,5,0,math.tau); c.fill()
        else:
            line([(5,19),(18,5)],(.2,.4,.65)); line([(11,5),(18,5),(18,12)],(.2,.4,.65))

def tool(kind,label,callback,caption=True):
    b=Gtk.Button(); box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=1)
    box.pack_start(Icon(kind),False,False,0)
    if caption: box.pack_start(Gtk.Label(label=label),False,False,0)
    else: b.get_style_context().add_class('panel-icon')
    b.add(box); b.set_tooltip_text(label); b.connect('clicked',callback)
    return b
