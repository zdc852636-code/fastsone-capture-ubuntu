"""Validated settings and atomic image exports; no desktop state is accessed."""
import json
import math
import os
from pathlib import Path
import tempfile
from PIL import Image

IMAGE_FORMATS={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.bmp':'BMP',
               '.tif':'TIFF','.tiff':'TIFF','.webp':'WEBP','.pdf':'PDF'}


def image_path(path):
    path=Path(path).expanduser()
    return path if path.suffix.lower() in IMAGE_FORMATS else Path(str(path)+'.png')


def pil_image(pix):
    mode='RGBA' if pix.get_has_alpha() else 'RGB'
    return Image.frombytes(mode,(pix.get_width(),pix.get_height()),bytes(pix.get_pixels()),
                           'raw',mode,pix.get_rowstride())


def pixbuf_image(image):
    from gi.repository import GLib, GdkPixbuf
    alpha='A' in image.getbands()
    image=image.convert('RGBA' if alpha else 'RGB')
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(image.tobytes()),
        GdkPixbuf.Colorspace.RGB,alpha,8,image.width,image.height,image.width*(4 if alpha else 3))


def write_image(pix,path):
    """Do not touch an existing destination until encoding succeeds completely."""
    path=image_path(path)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',suffix='.tmp',dir=path.parent)
    os.close(fd)
    temp=Path(name)
    try:
        fmt=IMAGE_FORMATS[path.suffix.lower()]
        if fmt=='PDF':
            import cairo
            from gi.repository import Gdk
            surface=cairo.PDFSurface(str(temp),pix.get_width(),pix.get_height())
            try:
                cr=cairo.Context(surface); cr.set_source_rgb(1,1,1); cr.paint()
                Gdk.cairo_set_source_pixbuf(cr,pix,0,0); cr.paint()
            finally:surface.finish()
        else:
            image=pil_image(pix)
            if fmt in ('JPEG','BMP') and image.mode=='RGBA':
                background=Image.new('RGB',image.size,'white')
                background.paste(image,mask=image.getchannel('A')); image=background
            image.save(temp,format=fmt,**({'quality':95} if fmt in ('JPEG','WEBP') else {}))
        with temp.open('rb') as stream:os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def load_settings(path):
    try:
        data=json.loads(Path(path).read_text())
    except (OSError,ValueError,UnicodeError):return {}
    if not isinstance(data,dict):return {}
    result={}
    for key,low,high in [('delay',0,10),('fixed_width',16,12000),('fixed_height',16,12000)]:
        value=data.get(key)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
            result[key]=max(low,min(high,int(value)))
    pos=data.get('position')
    if isinstance(pos,list) and len(pos)==2 and all(type(n) is int and -100000<=n<=100000 for n in pos):result['position']=pos
    if data.get('destination') in ('editor','auto','clipboard','file','draw','printer'):result['destination']=data['destination']
    if type(data.get('copy_always')) is bool:result['copy_always']=data['copy_always']
    if isinstance(data.get('save_dir'),str) and data['save_dir'] and '\0' not in data['save_dir']:result['save_dir']=data['save_dir']
    for group in ('hotkeys', 'editor_keys'):
        if isinstance(data.get(group), dict):
            keys = {k: v for k, v in data[group].items()
                    if isinstance(k, str) and len(k) < 64 and isinstance(v, str) and len(v) < 100}
            if keys:
                result[group] = keys
    if isinstance(data.get('toolbars'), dict):
        toolbars = {}
        for scope in ('panel', 'editor'):
            config = data['toolbars'].get(scope)
            if isinstance(config, dict):
                toolbars[scope] = {key: [v for v in config[key][:64] if isinstance(v, str)]
                                   for key in ('order', 'hidden') if isinstance(config.get(key), list)}
        result['toolbars'] = toolbars
    return result


def write_settings(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.settings-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)
