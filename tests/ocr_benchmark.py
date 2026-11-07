#!/usr/bin/python3
"""Measure OCR text errors against fixed, synthetic ground truth; never scans the desktop."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
import unicodedata
from ocr_fixtures import cases,render


def normalize(text):
    # Ignore spacing/line breaks only. Preserve punctuation, letter case and numbers.
    return ''.join(unicodedata.normalize('NFC',text).split())


def distance(a,b):
    previous=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        row=[i]
        for j,cb in enumerate(b,1):row.append(min(row[-1]+1,previous[j]+1,previous[j-1]+(ca!=cb)))
        previous=row
    return previous[-1]


def summarize(rows):
    chars=sum(row['characters'] for row in rows);errors=sum(row['errors'] for row in rows)
    return dict(cases=len(rows),characters=chars,errors=errors,cer=errors/chars,
        character_accuracy=1-errors/chars,exact=sum(row['errors']==0 for row in rows),
        median_seconds=statistics.median(row['seconds'] for row in rows),
        mean_seconds=statistics.mean(row['seconds'] for row in rows))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,default=Path(__file__).resolve().parents[1]/'ocr.py')
    parser.add_argument('--split',choices=['dev','holdout','all'],default='dev')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--label',default='current')
    parser.add_argument('--models',type=Path,help='Optional high-accuracy models, for current OCR module')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('ocr_under_test',args.module)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[]
    for split in (['dev','holdout'] if args.split=='all' else [args.split]):
        for case in cases(split):
            image=render(case);start=time.monotonic()
            actual=module.recognize(image,model_dir=args.models) if args.models else module.recognize(image)
            elapsed=time.monotonic()-start
            expected=case['text'].replace('\f','\n');truth=normalize(expected);prediction=normalize(actual)
            row=dict(id=case['id'],group=case['group'],split=split,characters=len(truth),
                errors=distance(truth,prediction),seconds=round(elapsed,4),expected=expected,actual=actual)
            rows.append(row)
            print(f"{row['id']}: {row['errors']}/{row['characters']} errors, {elapsed:.2f}s",flush=True)
            image.save(args.out/(case['id']+'.png'))
    summary=summarize(rows)
    groups={group:summarize([row for row in rows if row['group']==group]) for group in sorted({r['group'] for r in rows})}
    payload=dict(label=args.label,metric='1 - Levenshtein CER after NFC + whitespace removal; punctuation and case retained',
        dataset='fixed synthetic screenshots; not a real-world accuracy guarantee',summary=summary,groups=groups,rows=rows)
    (args.out/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    with (args.out/'results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
