"""Local scrolling capture and GStreamer recording backends."""
from pathlib import Path
import ctypes as C
import ctypes.util
import os
import tempfile
import time
import gi
gi.require_version('Gst','1.0')
gi.require_version('Gtk','3.0')
gi.require_version('Gdk','3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gst
from PIL import Image, ImageChops, ImageStat


def pil(pix):
    return Image.frombytes('RGBA' if pix.get_has_alpha() else 'RGB',(pix.get_width(),pix.get_height()),bytes(pix.get_pixels()),'raw','RGBA' if pix.get_has_alpha() else 'RGB',pix.get_rowstride()).convert('RGB')

def pixbuf(image):
    data=GLib.Bytes.new(image.convert('RGB').tobytes())
    return GdkPixbuf.Pixbuf.new_from_bytes(data,GdkPixbuf.Colorspace.RGB,False,8,image.width,image.height,image.width*3)

def match_scroll(previous,current):
    """Find real pixel displacement; reject unrelated frames instead of guessing."""
    a,b=previous.convert('RGB'),current.convert('RGB')
    w,h=a.size
    if b.size!=a.size: raise ValueError('滚动区域尺寸发生变化')
    width=min(96,w)
    def small(im,height): return im.resize((width,height)).convert('L')
    if ImageStat.Stat(ImageChops.difference(small(a,h),small(b,h))).mean[0]<.15: return 0
    height=max(30,h//4); aa,bb=small(a,height),small(b,height)
    def error(a,b,shift):
        return ImageStat.Stat(ImageChops.difference(a.crop((0,shift,a.width,a.height)),b.crop((0,0,b.width,b.height-shift)))).mean[0]
    candidates=range(1,max(2,int(height*.8)))
    coarse=sorted(candidates,key=lambda d:error(aa,bb,d))[:8]
    aa,bb=small(a,h),small(b,h)
    fine=set(range(1,min(16,h-2)))
    for c in coarse:
        center=round(c*h/height)
        fine.update(range(max(1,center-6),min(h-3,center+6)+1))
    shift=min(sorted(fine),key=lambda d:error(aa,bb,d))
    if error(aa,bb,shift)>13: raise ValueError('无法可靠拼接：请只框选可滚动内容，避开固定标题、侧栏和悬浮元素。')
    return shift

class ScrollCapture:
    def __init__(self,app,rect):
        self.app,self.rect=app,rect; self.frames=[]; self.last=None; self.running=False; self.timer=None; self.closed=False
        self.hidden=[]
        for w in [app.toolbar,app.workspace]+app.pins:
            if w and w.get_visible(): self.hidden.append(w); w.hide()
        self.window=Gtk.Window(title='滚动截图'); self.window.set_keep_above(True); self.window.set_accept_focus(False)
        self.window.set_default_size(350,110)
        x,y,w,h=rect; screen=Gdk.Screen.get_default()
        # Place controller outside the content rectangle where possible; hide it for each sample regardless.
        self.window.move(10,10 if y>140 else min(screen.get_height()-150,y+h+10))
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,margin=10); self.window.add(box)
        self.label=Gtk.Label(label='只框选滚动内容；请勿操作鼠标。\n点击开始，自动向下滚动并拼接。')
        box.pack_start(self.label,False,False,0)
        row=Gtk.Box(spacing=6); box.pack_start(row,False,False,0)
        start=Gtk.Button(label='开始滚动'); start.connect('clicked',self.start); row.pack_start(start,True,True,0)
        done=Gtk.Button(label='完成'); done.connect('clicked',lambda *_:self.finish()); row.pack_start(done,True,True,0)
        cancel=Gtk.Button(label='取消'); cancel.connect('clicked',lambda *_:self.finish(False)); row.pack_start(cancel,False,False,0)
        self.window.connect('delete-event',lambda *_:self.finish(False) or True)
        self.window.show_all()
    def start(self,*args):
        if self.running or self.closed:return
        self.running=True; self.window.hide(); self.timer=GLib.timeout_add(180,self.first)
    def screenshot(self):
        x,y,w,h=self.rect
        root=Gdk.Screen.get_default().get_root_window()
        p=Gdk.pixbuf_get_from_window(root,x,y,w,h)
        if p is None: raise RuntimeError('无法读取滚动区域')
        return pil(p)
    def first(self):
        self.timer=None
        if not self.running:return False
        try:
            self.last=self.screenshot(); self.frames=[self.last]
            self.app.xtest_scroll(self.rect,3)
            self.timer=GLib.timeout_add(650,self.sample)
        except Exception as e:self.fail(e)
        return False
    def sample(self):
        self.timer=None
        if not self.running:return False
        try:
            current=self.screenshot(); shift=match_scroll(self.last,current)
            if shift==0:self.finish(); return False
            self.frames.append(current.crop((0,current.height-shift,current.width,current.height))); self.last=current
            self.label.set_text(f'已拼接 {sum(f.height for f in self.frames)} 像素 · {len(self.frames)} 帧')
            if len(self.frames)>=35 or sum(f.height for f in self.frames)>=24000:self.finish(); return False
            self.window.show_all()
            self.timer=GLib.timeout_add(250,self.next)
        except Exception as e:self.fail(e)
        return False
    def next(self):
        self.timer=None
        if not self.running:return False
        try:
            self.window.hide(); self.app.xtest_scroll(self.rect,3)
            self.timer=GLib.timeout_add(650,self.sample)
        except Exception as error:self.fail(error)
        return False
    def fail(self,error):
        self.finish(bool(self.frames))
        self.app.error(str(error))
    def finish(self,deliver=True):
        if self.closed:return
        self.closed=True
        self.running=False
        if self.timer:GLib.source_remove(self.timer); self.timer=None
        self.window.destroy(); self.app.scroll_session=None
        for w in self.hidden:w.show()
        self.app.busy=False; self.app.toolbar.show_all()
        if deliver and self.frames:
            image=Image.new('RGB',(self.frames[0].width,sum(f.height for f in self.frames))); y=0
            for f in self.frames:image.paste(f,(0,y)); y+=f.height
            self.app.deliver(pixbuf(image))

class Recorder:
    def __init__(self,app,rect=None,audio=False,source=None,path=None):
        Gst.init(None); self.app=app; self.rect=rect; self.pipeline=None; self.path=path; self.finished=False; self.finalized=False
        self.timer=None; self.eos_timer=None; self.bus=None; self.bus_handler=None; self.temp_path=None
        self.window=Gtk.Window(title='屏幕录像机'); self.window.set_keep_above(True)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin=14); self.window.add(box)
        self.label=Gtk.Label(label='准备录制…'); box.pack_start(self.label,False,False,0)
        self.pause=Gtk.Button(label='暂停'); self.pause.connect('clicked',self.toggle); box.pack_start(self.pause,False,False,0)
        stop=Gtk.Button(label='停止并保存'); stop.connect('clicked',lambda *_:self.stop()); box.pack_start(stop,False,False,0)
        self.window.connect('delete-event',lambda *_:self.stop() or True)
        self.window.set_default_size(280,130)
        if not path:
            d=Gtk.FileChooserDialog(title='保存录像 · WebM',transient_for=app.toolbar,action=Gtk.FileChooserAction.SAVE)
            d.add_buttons('取消',Gtk.ResponseType.CANCEL,'录制',Gtk.ResponseType.OK); d.set_do_overwrite_confirmation(True)
            d.set_current_name('录像-'+time.strftime('%Y%m%d-%H%M%S')+'.webm')
            d.set_current_folder(str(Path.home()/'Videos') if (Path.home()/'Videos').is_dir() else str(Path.home()))
            if d.run()==Gtk.ResponseType.OK:
                chosen=Path(d.get_filename())
                target=chosen if chosen.suffix.lower()=='.webm' else Path(str(chosen)+'.webm')
                overwrite=True
                if target!=chosen and target.exists():
                    confirm=Gtk.MessageDialog(transient_for=d,modal=True,buttons=Gtk.ButtonsType.YES_NO,text='替换已有录像？')
                    confirm.format_secondary_text(str(target)); overwrite=confirm.run()==Gtk.ResponseType.YES; confirm.destroy()
                if overwrite:self.path=target
            d.destroy()
        if not self.path:
            self.finished=True; self.finalized=True; self.window.destroy(); app.recorder=None; return
        self.path=Path(self.path)
        if self.path.suffix.lower()!='.webm':self.path=Path(str(self.path)+'.webm')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd,name=tempfile.mkstemp(prefix='.'+self.path.stem+'-',suffix='.recording.webm',dir=self.path.parent)
            os.close(fd); self.temp_path=Path(name)
            self.pipeline=Gst.parse_launch('ximagesrc name=screen use-damage=false show-pointer=true ! video/x-raw,framerate=15/1 ! videoconvert ! queue ! vp8enc deadline=1 cpu-used=6 threads=4 ! queue ! webmmux name=mux ! filesink name=out')
            self.pipeline.get_by_name('out').set_property('location',str(self.temp_path))
            screen=self.pipeline.get_by_name('screen')
            if rect:
                x,y,w,h=rect
                for k,v in [('startx',x),('starty',y),('endx',x+w-1),('endy',y+h-1)]:screen.set_property(k,v)
            if audio:
                # The selected PulseAudio device can be a microphone or a speaker monitor.
                audio_bin=Gst.parse_bin_from_description('pulsesrc name=audio ! audioconvert ! audioresample ! vorbisenc ! queue',True)
                if source:audio_bin.get_by_name('audio').set_property('device',source)
                self.pipeline.add(audio_bin)
                if not audio_bin.link(self.pipeline.get_by_name('mux')):raise RuntimeError('无法连接录音设备')
            self.bus=self.pipeline.get_bus(); self.bus.add_signal_watch(); self.bus_handler=self.bus.connect('message',self.message)
            self.started=time.monotonic(); self.elapsed=0.; self.pause_at=None
            if self.pipeline.set_state(Gst.State.PLAYING)==Gst.StateChangeReturn.FAILURE:raise RuntimeError('录制组件无法启动')
            self.window.show_all()
            self.timer=GLib.timeout_add_seconds(1,self.tick)
        except Exception as e:
            self.complete(False,'启动录像失败：'+str(e))
    def tick(self):
        if self.finished:self.timer=None; return False
        secs=int(self.elapsed+(time.monotonic()-self.started if self.pause_at is None else 0))
        self.label.set_text(f'{"录制中" if self.pause_at is None else "已暂停"}  {secs//60:02d}:{secs%60:02d}\n{self.path.name}')
        return True
    def toggle(self,*args):
        if self.finished:return
        if self.pause_at is None:
            self.elapsed+=time.monotonic()-self.started; self.pause_at=time.monotonic(); self.pipeline.set_state(Gst.State.PAUSED); self.pause.set_label('继续')
        else:
            self.pause_at=None; self.started=time.monotonic(); self.pipeline.set_state(Gst.State.PLAYING); self.pause.set_label('暂停')
    def stop(self):
        if self.finished:return
        self.finished=True; self.label.set_text('正在保存录像…'); self.pause.set_sensitive(False)
        self.pipeline.set_state(Gst.State.PLAYING)
        if not self.pipeline.send_event(Gst.Event.new_eos()):
            self.complete(False,'录制组件无法结束封装'); return
        self.eos_timer=GLib.timeout_add_seconds(12,self.timeout)
    def timeout(self):
        self.eos_timer=None
        if not self.finalized:
            self.complete(False,'录像封装超时，文件可能不完整。')
        return False
    def message(self,bus,message):
        if message.type==Gst.MessageType.ERROR:
            error,debug=message.parse_error(); self.complete(False,str(error))
        elif message.type==Gst.MessageType.EOS:self.complete(True)
    def complete(self,success,error=None):
        if self.finalized:return
        self.finalized=True; self.finished=True
        for attr in ('timer','eos_timer'):
            source_id=getattr(self,attr)
            if source_id:GLib.source_remove(source_id); setattr(self,attr,None)
        if self.pipeline:self.pipeline.set_state(Gst.State.NULL)
        if self.bus:
            if self.bus_handler:self.bus.disconnect(self.bus_handler)
            self.bus.remove_signal_watch(); self.bus=None; self.bus_handler=None
        if success:
            try:
                if not self.temp_path or self.temp_path.stat().st_size==0:raise RuntimeError('没有生成有效的视频数据')
                with self.temp_path.open('rb') as stream:os.fsync(stream.fileno())
                os.replace(self.temp_path,self.path); self.temp_path=None
            except (OSError,RuntimeError) as e:success=False; error=str(e)
        if self.temp_path and self.temp_path.exists():
            if self.temp_path.stat().st_size:
                error=str(error)+'\n未完成的录像保留在：'+str(self.temp_path)
            else:self.temp_path.unlink(missing_ok=True)
        self.window.destroy(); self.app.recorder=None
        if success:self.app.inform('录像已保存',str(self.path))
        else:self.app.error('录像失败：'+str(error))
