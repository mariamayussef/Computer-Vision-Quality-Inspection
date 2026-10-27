"""Fit on official normal training images only; calibrate on a disjoint normal holdout."""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.vision import decode, features, Detector, PREPROCESS

p = argparse.ArgumentParser()
p.add_argument('--data', default='data/mvtec/bottle')
p.add_argument('--output', default='models/bottle-v1')
a = p.parse_args()
paths = sorted((Path(a.data)/'train/good').glob('*.png'))
if len(paths) < 30: raise SystemExit('Need at least 30 lawful normal training images')
rng = np.random.default_rng(42)
order = rng.permutation(len(paths)); nval = max(10, round(len(paths)*.2))
val = [paths[i] for i in order[:nval]]; train = [paths[i] for i in order[nval:]]
bank = np.stack([features(decode(f.read_bytes())) for f in train])
scale = np.maximum(bank.std(axis=(0,1,2)), .03).astype(np.float32)
out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
np.savez_compressed(out/'normal_bank.npz', bank=bank, scale=scale)
def item(f): return {'path':str(f.relative_to(Path(a.data))), 'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
config = {'version':out.name, 'category':'bottle', 'preprocessing':PREPROCESS, 'image_size':128,
          'feature_grid':32, 'label_map':{'normal':0,'anomaly':1}, 'threshold':1.0,
          'method':'position-aware nearest-normal LAB/Sobel patch features', 'seed':42,
          'artifact_sha256':hashlib.sha256((out/'normal_bank.npz').read_bytes()).hexdigest(),
          'fit':[item(f) for f in train], 'validation':[item(f) for f in val],
          'threshold_rule':'95th percentile (higher) of held-out normal training scores',
          'review_band_fraction':.9, 'data_license':'CC-BY-NC-SA-4.0'}
(out/'config.json').write_text(json.dumps(config,indent=2))
model = Detector(out)
scores = [model.predict(decode(f.read_bytes()))['score'] for f in val]
config['threshold'] = float(np.quantile(scores,.95,method='higher'))
config['validation_scores'] = scores
(out/'config.json').write_text(json.dumps(config,indent=2))
print(json.dumps({'fit':len(train),'normal_validation':len(val),'threshold':config['threshold']},indent=2))
