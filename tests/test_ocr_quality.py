"""Regression checks for layout, blank images, and a failing optional quality pass."""
from pathlib import Path
import sys
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ocr
from ocr_fixtures import cases,render
from ocr_benchmark import normalize

for color in ('white','black','#999999'):
    assert ocr.recognize(Image.new('RGB',(120,60),color))==''
assert ocr.recognize(Image.new('RGBA',(120,60),(0,0,0,0)))==''
print('PASS uniform light/dark/gray and transparent images produce no invented text',flush=True)

for case in cases('dev'):
    if case['group']!='columns':continue
    assert normalize(ocr.recognize(render(case)))==normalize(case['text']),case['id']
print('PASS independent column reading order for Chinese and English',flush=True)

image=render(next(case for case in cases('dev') if case['id']=='dev-normal-1'))
first=ocr.OCRResult('Retained first-pass text',70,True)
with patch.object(ocr,'run_pass',side_effect=[first,RuntimeError('optional retry failed')]):
    result=ocr.recognize_detailed(image)
assert result.text==first.text and result.needs_review
with patch.object(ocr,'run_pass',side_effect=RuntimeError('primary engine failed')):
    try:ocr.recognize(image)
    except RuntimeError as error:assert 'primary' in str(error)
    else:raise AssertionError('A primary failure must be reported, not mistaken for blank text')
print('PASS quality-retry failures retain text and primary failures are surfaced',flush=True)
