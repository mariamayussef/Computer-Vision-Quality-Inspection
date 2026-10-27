"""Bounded, resumable download of MVTec AD bottle from a public CC BY-NC-SA mirror."""
import argparse, concurrent.futures, hashlib, json, shutil, urllib.request
from pathlib import Path

REPO = 'https://huggingface.co'
REVISION = 'main'

def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', default='data/mvtec')
    p.add_argument('--import-from', dest='source', type=Path, help='Owned/lawfully obtained bottle directory')
    args = p.parse_args()
    root = Path(args.root); root.mkdir(parents=True, exist_ok=True)
    if args.source:
        if not (args.source / 'train/good').is_dir():
            raise SystemExit('Expected bottle/train/good in import source')
        shutil.copytree(args.source, root / 'bottle', dirs_exist_ok=True)
        entries = None
    else:
        # Resolve an immutable revision before listing/downloading.
        meta = json.loads(fetch(f'{REPO}/api/datasets/foersben/mvtec-ad'))
        revision = meta['sha']
        entries = json.loads(fetch(f'{REPO}/api/datasets/foersben/mvtec-ad/tree/{revision}/bottle?recursive=true&limit=1000'))
        entries = [e for e in entries if e['type'] == 'file']
        total = sum(e['size'] for e in entries)
        if total > 250_000_000 or shutil.disk_usage(root).free < total + 300_000_000:
            raise SystemExit('Download exceeds 250 MB bound or insufficient free disk')
        failures = []
        def download(e):
            target = root / e['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_size == e['size']:
                return
            url = f'{REPO}/datasets/foersben/mvtec-ad/resolve/{revision}/{e["path"]}'
            for attempt in range(3):
                try:
                    payload = fetch(url)
                    if len(payload) != e['size']: raise ValueError('Size mismatch')
                    expected = e.get('lfs', {}).get('oid')
                    if expected and hashlib.sha256(payload).hexdigest() != expected:
                        raise ValueError('SHA256 mismatch')
                    temporary = target.with_suffix(target.suffix + '.part')
                    temporary.write_bytes(payload); temporary.replace(target)
                    return
                except Exception as ex:
                    if attempt == 2: failures.append({'path': e['path'], 'error': str(ex)})
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(download, entries))
        (root / 'acquisition.json').write_text(json.dumps({'source': 'foersben/mvtec-ad', 'revision': revision, 'bytes': total, 'failures': failures}, indent=2))
        if failures: raise SystemExit(f'{len(failures)} unavailable files; rerun to resume')
    from PIL import Image
    manifest = []
    for f in sorted((root / 'bottle').rglob('*.png')):
        with Image.open(f) as im: im.load(); size = im.size
        manifest.append({'path': str(f.relative_to(root)), 'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'size': size})
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f'Validated {len(manifest)} PNG images (including masks)')

if __name__ == '__main__': main()
