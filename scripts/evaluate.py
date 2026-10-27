"""One-shot test evaluation. Thresholds/model remain frozen; demo examples excluded."""
import argparse, csv, hashlib, json, platform, shutil, sys, time
from collections import Counter
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.vision import Detector, decode
p=argparse.ArgumentParser();p.add_argument('--data',default='data/mvtec/bottle');p.add_argument('--model',default='models/bottle-v1');a=p.parse_args()
model=Detector(a.model);root=Path(a.data)
# Selected by filename, before looking at predictions. These are demos, excluded from reported metrics.
demos=[sorted(d.glob('*.png'))[0] for d in sorted((root/'test').iterdir()) if d.is_dir()]
Path('demo').mkdir(exist_ok=True)
for path in demos: shutil.copyfile(path,Path('demo')/(path.parent.name+'-'+path.name))
Path('demo/manifest.json').write_text(json.dumps([{'source':str(f.relative_to(root)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'purpose':'demonstration only; excluded from evaluation'} for f in demos],indent=2))
fit_hash={e['sha256'] for e in model.config['fit']+model.config['validation']}
records=[]
for f in sorted((root/'test').glob('*/*.png')):
    if f in demos: continue
    start=time.perf_counter();raw=f.read_bytes();rgb=decode(raw)
    h=hashlib.sha256(raw).hexdigest()
    if h in fit_hash: raise RuntimeError('Train/test leakage detected')
    prediction=model.predict(rgb);prediction.pop('map')
    records.append({'path':str(f.relative_to(root)),'sha256':h,'condition':f.parent.name,'anomaly':f.parent.name!='good',**prediction,'decode_and_inference_ms':(time.perf_counter()-start)*1000})
y=np.array([r['anomaly'] for r in records]); scores=np.array([r['score'] for r in records]); pred=scores>model.config['threshold']
def metrics(mask):
    yt=y[mask];pt=pred[mask];tp=int((yt&pt).sum());fn=int((yt&~pt).sum());fp=int((~yt&pt).sum());tn=int((~yt&~pt).sum())
    return {'count':int(mask.sum()),'tp':tp,'fn':fn,'fp':fp,'tn':tn,'recall':tp/(tp+fn) if tp+fn else None,'precision':tp/(tp+fp) if tp+fp else None,'false_reject_rate':fp/(fp+tn) if fp+tn else None}
# Pairwise AUROC accounts for ties; AP uses grouped equal scores.
pos=scores[y];neg=scores[~y];auc=float(((pos[:,None]>neg).mean())+.5*(pos[:,None]==neg).mean())
ap=0.;previous_recall=0.
for cutoff in sorted(set(scores),reverse=True):
    chosen=scores>=cutoff;tp=(y&chosen).sum();recall=tp/y.sum();precision=tp/chosen.sum();ap+=(recall-previous_recall)*precision;previous_recall=recall
result={'model':model.config['version'],'artifact_sha256':model.config['artifact_sha256'],'threshold':model.config['threshold'],
 'hardware':{'machine':platform.machine(),'processor':'Apple M3 (MacBook Air, 8 cores, 8 GB RAM)','python':platform.python_version(),'platform':platform.platform(),'execution':'CPU only'},
 'split':{'fit_normal':len(model.config['fit']),'validation_normal':len(model.config['validation']),'test_normal':int((~y).sum()),'test_defect':int(y.sum()),'demo_excluded':len(demos)},
 'binary_threshold_metrics':metrics(np.ones(len(y),dtype=bool)),'image_auroc':auc,'average_precision':float(ap),
 'triage_suggestions':dict(Counter(r['suggestion'] for r in records)),
 'per_condition':{c:metrics(np.array([r['condition']==c for r in records])) for c in sorted({r['condition'] for r in records})},
 'latency_ms':{k:{'median':float(np.median([r[k] for r in records])),'p95':float(np.quantile([r[k] for r in records],.95))} for k in ['preprocessing_ms','inference_ms','decode_and_inference_ms']},
 'false_negatives':[r['path'] for r in records if r['anomaly'] and r['score']<=model.config['threshold']],
 'false_positives':[r['path'] for r in records if not r['anomaly'] and r['score']>model.config['threshold']],
 'records':records}
Path('docs/evaluation.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
# Labeled contact sheet of actual test failures/near-threshold examples. Anomaly maps are qualitative evidence.
from PIL import Image,ImageDraw
chosen=[r for r in records if r['path'] in result['false_negatives']+result['false_positives']]
for condition in sorted({r['condition'] for r in records}):
    options=[r for r in records if r['condition']==condition]
    candidate=min(options,key=lambda r:abs(r['score']-model.config['threshold']))
    if candidate not in chosen: chosen.append(candidate)
chosen=chosen[:12]
sheet=Image.new('RGB',(660, len(chosen)*190),'#f6f7f3');draw=ImageDraw.Draw(sheet)
for i,r in enumerate(chosen):
    raw=(root/r['path']).read_bytes();rgb=decode(raw);out=model.predict(rgb)
    image=Image.fromarray(rgb);image.thumbnail((160,160));sheet.paste(image,(10,i*190+5))
    heat=Image.open(__import__('io').BytesIO(model.heatmap(out['map'],(160,160))))
    original=Image.fromarray(rgb).resize((160,160));sheet.paste(Image.blend(original,heat,.45),(180,i*190+5))
    draw.text((360,i*190+15),f"{r['path']}\nTrue: {'defect' if r['anomaly'] else 'normal'}\nScore: {r['score']:.3f} / {model.config['threshold']:.3f}\nSuggestion: {r['suggestion']}\nWarnings: {', '.join(r['warnings']) or 'none'}",fill='#253c2c')
sheet.save('docs/failure-examples.jpg')
