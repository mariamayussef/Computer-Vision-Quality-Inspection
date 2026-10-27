# Bottle v1 model card

## Intended use

Noncommercial inspection assistance on controlled, centered top-down bottle
images resembling MVTec AD. Category `bottle`; structural anomalies and
contamination. Operators confirm or correct results. This is not a certified
quality gate or a general-purpose bottle recognizer.

## Real fitted baseline

A position-aware nearest-normal feature detector implemented with NumPy and
OpenCV. This is an intentionally small CPU baseline, selected for the available
8 GB Mac and a single aligned category. It does not use pretrained weights,
PyTorch, an object detector or a supervised defect classifier. A pretrained
feature model is a potential future comparison; none is implied by these results.

Decode PNG/JPEG/WebP, apply EXIF orientation, convert RGB, resize to 128×128.
Convert to LAB/255 and grayscale/255, calculate Sobel x/y and gradient magnitude,
then Gaussian smooth and area-resize six channels to a 32×32 grid. Fit a feature
bank from 167 normals, with channel standard-deviation scales floored at 0.03.
For each grid position, find the closest normal feature at the same position
across fitting images. The anomaly map is the square root of the minimum mean
standardized squared channel distance. Image score is the mean of the top 11
of 1024 map cells (approximately the top 1%). All method choices were fixed
before test evaluation.

Threshold **0.25250953435897827**, the higher 95th percentile on 42 separate
normal training images. Scores above threshold suggest suspected defect. Scores
from 90% of the threshold through threshold, or any image-quality warning,
suggest needs review. Others suggest normal. These scores are **not calibrated
probabilities** and the map is **not verified segmentation**. A fixed scale
0–1.5×threshold is used for heatmap colors, avoiding per-image color rescaling.

Quality checks flag very dark, overexposed, low-contrast/possibly empty, blurry
or non-square images. They are heuristics, not object presence validation.
Operators can override warnings through a reasoned review, preserving evidence.

## Artifact and versioning

`models/bottle-v1/normal_bank.npz` (about 2.8 MiB), loaded with
`allow_pickle=False`; SHA-256:
`d961ca3cff53339391c29aa06fba34725b54b23053f5c1b4f8f65084bd6879a7`.

`config.json` versions category, method, preprocessing (`lab-gradient-32-v1`),
image size, label map, threshold, review band, split seed, source filenames,
source hashes, validation scores and artifact checksum. The API stores the
registered immutable model configuration and records its version, threshold,
preprocessing and artifact hash in each successful result. A changed file with
the same registered version cannot be activated.

See `EVALUATION.md` for actual results and failure evidence. Dataset, bank and
derivatives use CC BY-NC-SA 4.0; the app code uses MIT. No external pretrained
model/code license is involved. Original algorithm implementation is in
`backend/app/vision.py`.

## Deliberate offline update

1. Export candidate feedback as an administrator (`POST /api/feedback/export`).
   A timestamped UUID version and a private immutable JSON snapshot are retained.
2. Review consent, image ownership, labels, source hashes and session/batch
   provenance. Exact hashes of official test images are excluded automatically;
   modified or reencoded copies require a manual provenance check. Export does
   not promise a leakage-free dataset by itself.
3. The included fitter is **normal-only**. Import accepted normals in a separate
   MVTec-format directory. Keep owned development defects separate; do not place
   reviewed defects in `train/good`. Split by physical object/session first.
4. Fit to a new output/version, e.g.
   `python scripts/train.py --data data/owned/bottle --output models/bottle-v2`.
   The generic random normal split assumes deduplicated independent sources;
   create a separately grouped directory/split before using it on collected data.
5. Evaluate both frozen versions on a separately reserved, lawful, untouched
   owned test set. The included evaluator expects MVTec `test/*` layout and
   reserves one demo per condition. Do not tune against the previously inspected
   benchmark test results and claim fresh held-out validation.
6. Compare recall, precision, false rejects, abstentions, failures and latency.
   Document acceptance manually. Exporting reviews never retrains anything.
7. With the server stopped, register the candidate using `MODEL_DIR=... python
   scripts/manage.py register-model`; set `MODEL_DIR` to that folder and restart.
   Registration validates the artifact. Retain the old folder/configuration and
   database version for rollback. No activation endpoint or silent hot swap.
