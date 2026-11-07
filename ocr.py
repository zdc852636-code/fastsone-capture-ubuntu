"""Local screenshot OCR via Tesseract; screenshot pixels stay in memory."""
import io
import csv
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
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


@dataclass
class OCRResult:
    text: str
    confidence: float=0.
    needs_review: bool=False


def quality_models():
    for folder in (Path(__file__).resolve().parent/'ocr-models',
                   Path.home()/'.local/share/fastsone-capture-lw-ubuntu/ocr-models'):
        if all((folder/(language+'.traineddata')).is_file() for language in ('chi_sim','eng')):return folder
    return None


def bands(values):
    result=[];start=None
    for index,value in enumerate(list(values)+[0]):
        if value>1:
            if start is None:start=index
        elif start is not None:
            if index-start>=3:result.append((start,index))
            start=None
    return result


def text_geometry(gray):
    mask=gray.point(lambda value:255 if value<160 else 0)
    rows=bands(mask.resize((1,gray.height),Image.Resampling.BOX).getdata())
    heights=sorted(bottom-top for top,bottom in rows)
    return mask,rows,heights[len(heights)//2] if heights else 0


def prepare(image):
    if image.width*image.height>16_000_000:raise RuntimeError('识别区域过大，请分段框选。')
    if image.mode=='RGBA':
        white=Image.new('RGB',image.size,'white');white.paste(image,mask=image.getchannel('A'));image=white
    gray=ImageOps.autocontrast(image.convert('L'))
    low,high=gray.getextrema()
    if low==high:return None
    # A screenshot of a dark application benefits from a light background.
    if ImageStat.Stat(gray.resize((64,64))).median[0]<128:gray=ImageOps.invert(gray)
    mask,_,_=text_geometry(gray);box=mask.getbbox()
    if box is None:return None
    x0,y0,x1,y1=box
    return gray.crop((max(0,x0-4),max(0,y0-4),min(gray.width,x1+4),min(gray.height,y1+4)))


def columns(gray,depth=0):
    """Split a clear full-height gutter; preserve left-column-first reading order."""
    mask,rows,height=text_geometry(gray)
    if depth>=2 or len(rows)<3 or not height:return [gray]
    projection=list(mask.resize((gray.width,1),Image.Resampling.BOX).getdata())
    gaps=[];start=None
    for i,value in enumerate(projection+[255]):
        if value<=1:
            if start is None:start=i
        elif start is not None:
            if i-start>=max(40,3*height,gray.width*.08) and start>gray.width*.18 and i<gray.width*.82:
                gaps.append((i-start,start,i))
            start=None
    for _,left,right in sorted(gaps,reverse=True):
        parts=[gray.crop((0,0,left,gray.height)),gray.crop((right,0,gray.width,gray.height))]
        if all(len(text_geometry(part)[1])>=3 and part.width>=5*height for part in parts):
            return [piece for part in parts for piece in columns(part,depth+1)]
    return [gray]


def run_pass(gray,scale,executable,env,deadline):
    if gray.width*gray.height*scale*scale>24_000_000:scale=1
    if scale!=1:gray=gray.resize((max(1,round(gray.width*scale)),max(1,round(gray.height*scale))),Image.Resampling.LANCZOS)
    payload=io.BytesIO();ImageOps.expand(gray,border=16,fill='white').save(payload,format='PNG')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise RuntimeError('文字识别超时，请缩小区域后重试。')
    try:
        result=subprocess.run([executable,'stdin','stdout','-l','chi_sim+eng','--oem','1','--psm','6','--dpi','300',
                '-c','tessedit_create_tsv=1'],
            input=payload.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=remaining)
    except subprocess.TimeoutExpired:raise RuntimeError('文字识别超时，请缩小区域后重试。') from None
    except OSError as error:raise RuntimeError('无法启动文字识别：'+str(error)) from error
    if result.returncode:
        raise RuntimeError('文字识别失败，请检查中英文语言包。'+result.stderr.decode('utf-8',errors='replace')[-500:])
    output=result.stdout.decode('utf-8',errors='replace')
    if not output.startswith('level\t'):raise RuntimeError('文字识别引擎返回了无法读取的结果。')
    lines={};weighted=0.;characters=0;uncertain=0
    for word in csv.DictReader(io.StringIO(output),delimiter='\t',quoting=csv.QUOTE_NONE):
        value=word.get('text','').strip()
        confidence=float(word['conf'])
        if not value or confidence<0:continue
        key=tuple(word[k] for k in ('page_num','block_num','par_num','line_num'))
        lines.setdefault(key,[]).append(value)
        length=len(value);weighted+=confidence*length;characters+=length
        if confidence<60:uncertain+=length
    text='\n'.join(' '.join(words) for words in lines.values()).strip()
    # Join artificial OCR spaces within Chinese text; never guess/correct characters.
    text=re.sub(r'(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff，。！？；：、])','',text)
    confidence=weighted/max(1,characters)
    return OCRResult(text,confidence,confidence<85 or uncertain/max(1,characters)>.18)


def recognize_detailed(image,*,model_dir=None):
    executable,env=engine();deadline=time.monotonic()+40
    gray=prepare(image)
    if gray is None:return OCRResult('')
    models=Path(model_dir) if model_dir else quality_models()
    results=[]
    for part in columns(gray):
        _,_,height=text_geometry(part)
        scale=2 if 0<height<20 and max(part.size)<=2500 and part.width*part.height<=4_000_000 else 1
        best=run_pass(part,scale,executable,env,deadline)
        # Confidence is a retry signal, not a promise of text accuracy.
        if best.confidence<92:
            alternate=1 if scale==2 else (.75 if height>28 else 1.5)
            try:
                candidate=run_pass(part,alternate,executable,env,deadline)
                if candidate.text and candidate.confidence>best.confidence+1:
                    best=candidate;scale=alternate
                if models:
                    refined_env=env.copy();refined_env['TESSDATA_PREFIX']=str(models)
                    candidate=run_pass(part,scale,executable,refined_env,deadline)
                    if candidate.text and candidate.confidence>best.confidence+1:best=candidate
            except RuntimeError:
                # Optional quality retry failure must not discard a successful first pass.
                if not best.text:raise
                best.needs_review=True
        results.append(best)
    count=sum(len(result.text) for result in results)
    return OCRResult('\n\n'.join(r.text for r in results if r.text),
        sum(r.confidence*len(r.text) for r in results)/max(1,count),any(r.needs_review for r in results))


def recognize(image,*,model_dir=None):
    return recognize_detailed(image,model_dir=model_dir).text
