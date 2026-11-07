#!/usr/bin/python3
"""Install pinned, checksum-verified official Tesseract quality models for Capture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_info import IDENT

REVISION='e12c65a915945e4c28e237a9b52bc4a8f39a0cec'
FILES={
    'chi_sim.traineddata':'4fef2d1306c8e87616d4d3e4c6c67faf5d44be3342290cf8f2f0f6e3aa7e735b',
    'eng.traineddata':'8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba',
    'LICENSE':'a6cba85bc92e0cff7a450b1d873c0eaa2e9fc96bf472df0247a26bec77bf3ff9',
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-directory',type=Path,help='Use previously downloaded files; verify the same checksums')
    parser.add_argument('--destination',type=Path,default=Path.home()/'.local/share'/IDENT/'ocr-models')
    args=parser.parse_args();args.destination.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.model-install-',dir=args.destination) as temp:
        stage=Path(temp);metadata=[]
        for name,digest in FILES.items():
            url=f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{REVISION}/{name}'
            target=stage/name
            if args.from_directory:shutil.copyfile(args.from_directory/name,target)
            else:
                with urllib.request.urlopen(url,timeout=60) as response,target.open('wb') as stream:
                    shutil.copyfileobj(response,stream)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise RuntimeError('模型校验失败：'+name)
            metadata.append(dict(file=name,url=url,sha256=digest,bytes=target.stat().st_size))
        for name in FILES:os.replace(stage/name,args.destination/name)
        manifest=stage/'manifest.json'
        manifest.write_text(json.dumps(dict(repository='tesseract-ocr/tessdata_best',revision=REVISION,files=metadata),indent=2))
        os.replace(manifest,args.destination/'manifest.json')
    print('已安装中英文高精度复查模型：'+str(args.destination))


if __name__=='__main__':main()
