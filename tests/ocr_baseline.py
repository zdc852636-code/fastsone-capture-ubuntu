"""Local screenshot OCR via Tesseract; screenshot pixels stay in memory."""
import io
import os
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageOps, ImageStat


def engine():
    runtime=Path.home()/'.local/share/gimagereader-lw/runtime'
    local=runtime/'usr/bin/tesseract'
    env=os.environ.copy();env['OMP_THREAD_LIMIT']='2'
    if local.is_file():
        env['LD_LIBRARY_PATH']=str(runtime/'usr/lib/x86_64-linux-gnu')
        env['TESSDATA_PREFIX']=str(runtime/'usr/share/tesseract-ocr/5/tessdata')
        return str(local),env
    installed=shutil.which('tesseract')
    if installed:return installed,env
    raise RuntimeError('未安装文字识别组件，请安装 tesseract-ocr、tesseract-ocr-chi-sim 和 tesseract-ocr-eng。')


def recognize(image):
    executable,env=engine()
    if image.width*image.height>16_000_000:raise RuntimeError('识别区域过大，请分段框选。')
    if image.mode=='RGBA':
        white=Image.new('RGB',image.size,'white');white.paste(image,mask=image.getchannel('A'));image=white
    gray=ImageOps.autocontrast(image.convert('L'))
    # A screenshot of a dark application benefits from a light background.
    if ImageStat.Stat(gray.resize((64,64))).median[0]<128:gray=ImageOps.invert(gray)
    # Only enlarge small text. Enlarging already large CJK glyphs can hurt recognition.
    rows=gray.point(lambda value:255 if value<160 else 0).resize((1,gray.height),Image.Resampling.BOX)
    heights=[];run=0
    for value in list(rows.getdata())+[0]:
        if value>1:run+=1
        elif run:
            if run>=3:heights.append(run)
            run=0
    median=sorted(heights)[len(heights)//2] if heights else 0
    if 0<median<20 and max(gray.size)<=2500 and gray.width*gray.height<=4_000_000:
        gray=gray.resize((gray.width*2,gray.height*2),Image.Resampling.LANCZOS)
    gray=ImageOps.expand(gray,border=16,fill='white')
    payload=io.BytesIO();gray.save(payload,format='PNG')
    try:
        result=subprocess.run([executable,'stdin','stdout','-l','chi_sim+eng','--oem','1','--psm','6','--dpi','300'],
            input=payload.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=40)
    except subprocess.TimeoutExpired:raise RuntimeError('文字识别超时，请缩小区域后重试。') from None
    except OSError as error:raise RuntimeError('无法启动文字识别：'+str(error)) from error
    if result.returncode:
        raise RuntimeError('文字识别失败，请检查中英文语言包。'+result.stderr.decode('utf-8',errors='replace')[-500:])
    return result.stdout.decode('utf-8',errors='replace').replace('\r\n','\n').strip()
