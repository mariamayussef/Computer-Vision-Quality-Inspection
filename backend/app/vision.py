"""Position-aware nearest-normal handcrafted feature baseline. No pickle or pretrained weights."""
import hashlib
import io
import json
import time
import warnings
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

PREPROCESS = 'lab-gradient-32-v1'
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000

def decode(raw):
    if not raw or len(raw) > MAX_BYTES: raise ValueError('Image must be between 1 byte and 10 MiB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
        with image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'}: raise ValueError('Only PNG, JPEG and WebP supported')
            if image.width * image.height > 20_000_000 or min(image.size) < 64:
                raise ValueError('Image must be at least 64px per side and at most 20 megapixels')
            if getattr(image, 'n_frames', 1) != 1: raise ValueError('Animated images are unsupported')
            return np.array(ImageOps.exif_transpose(image).convert('RGB'))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise ValueError('Image could not be decoded safely') from e

def features(rgb):
    resized = cv2.resize(rgb, (128, 128), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(resized, cv2.COLOR_RGB2LAB).astype(np.float32) / 255
    gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    stack = np.dstack((lab, gx, gy, np.sqrt(gx*gx+gy*gy)))
    return cv2.resize(cv2.GaussianBlur(stack, (5, 5), 1), (32, 32), interpolation=cv2.INTER_AREA)

def quality(rgb):
    gray = cv2.cvtColor(cv2.resize(rgb, (256, 256)), cv2.COLOR_RGB2GRAY)
    warnings = []
    if gray.mean() < 35: warnings.append('Image is very dark')
    if gray.mean() > 235: warnings.append('Image is overexposed')
    if gray.std() < 12: warnings.append('Little visual content; object may be absent')
    if cv2.Laplacian(gray, cv2.CV_64F).var() < 25: warnings.append('Image may be blurred')
    if abs(rgb.shape[0] / rgb.shape[1] - 1) > .25: warnings.append('Framing differs from square benchmark images')
    return warnings

class Detector:
    def __init__(self, directory):
        self.path = Path(directory)
        self.config = json.loads((self.path / 'config.json').read_text())
        if self.config['preprocessing'] != PREPROCESS: raise ValueError('Unsupported preprocessing version')
        raw = (self.path / 'normal_bank.npz').read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.config['artifact_sha256']: raise ValueError('Model checksum mismatch')
        with np.load(io.BytesIO(raw), allow_pickle=False) as model:
            self.bank = model['bank']; self.scale = model['scale']
        if self.bank.shape[1:] != (32,32,6): raise ValueError('Invalid bank dimensions')

    def predict(self, rgb):
        start = time.perf_counter()
        x = features(rgb)
        pre_ms = (time.perf_counter()-start)*1000
        distances = np.mean(((self.bank-x[None]) / self.scale)**2, axis=-1)
        amap = np.sqrt(np.min(distances, axis=0))
        # Top 1% of cells; fixed before test evaluation.
        score = float(np.sort(amap.ravel())[-11:].mean())
        warnings = quality(rgb)
        threshold = self.config['threshold']
        suggestion = 'suspected_defect' if score > threshold else 'normal'
        if warnings or threshold * .9 <= score <= threshold: suggestion = 'needs_review'
        return {'score': score, 'suggestion': suggestion, 'warnings': warnings,
                'preprocessing_ms': pre_ms, 'inference_ms': (time.perf_counter()-start)*1000,
                'map': amap}

    def heatmap(self, amap, size):
        # Fixed model-relative scale, not a per-image normalization or probability.
        scaled = np.clip(amap / (self.config['threshold'] * 1.5), 0, 1)
        heat = cv2.applyColorMap((scaled*255).astype(np.uint8), cv2.COLORMAP_TURBO)
        heat = cv2.resize(heat, size, interpolation=cv2.INTER_LINEAR)
        return cv2.imencode('.png', heat)[1].tobytes()
