# Dataset and acquisition record

## Exact choice and supported task

MVTec AD, **bottle** category only. Benchmark photos show centered top-down
bottles under controlled conditions. Defect folders: `broken_large`,
`broken_small`, `contamination`. This supports an anomaly-assistance task for
bottle glass/rim appearance and contamination. It does not train label checking,
component placement, general object recognition or fine-grained crack naming.

Official source and terms, verified 2026-10-27:
https://www.mvtec.com/research-teaching/datasets/mvtec-ad

The provider currently displays a **Fill in the form** download route. No form
was submitted, agreement accepted or provider contacted. The official page
states CC BY-NC-SA 4.0 and prohibits commercial use. License:
https://creativecommons.org/licenses/by-nc-sa/4.0/

Acquired via the public, attributed CC BY-NC-SA redistribution:
https://huggingface.co/datasets/foersben/mvtec-ad/tree/main/bottle

Pinned mirror revision: `c75b39616f84db43677bcc8228caaafaf5096d7f`.
The mirror is a third-party redistribution, not a provider-operated endpoint.
The origin of its category structure, attribution and license is consistent
with the official benchmark; this is not a provider-signed archive verification.

## Acquired and decoded

156,570,806 bytes across **357 files**: 355 PNGs plus `license.txt` and
`readme.txt`. All 355 PNGs were successfully decoded with Pillow:

| Subset | Counts |
|---|---:|
| Official train/good | 209 |
| Official test/good | 20 |
| Official test/broken_large | 20 |
| Official test/broken_small | 22 |
| Official test/contamination | 21 |
| Ground-truth test masks | 63 |

No unavailable files were reported. Acquisition log: `data/mvtec/acquisition.json`.
The full per-file SHA-256/decode manifest is retained in
`models/dataset-manifest.json`. Large input images stay in ignored `data/mvtec/`.
The downloader resolves an immutable repository revision, restricts downloads to
bottle files, caps total size at 250 MB, requires extra free space, uses four
workers and three bounded attempts per file, validates expected byte lengths
and LFS SHA-256 when supplied, writes via `.part` files, and resumes existing
complete files. A decode pass and SHA-256 manifest follow. Existing same-size
files are not redownloaded; rerun with the affected file removed if decode
validation detects corruption. The import flag accepts lawfully obtained data
in the same directory layout without calling the mirror.

## Protocol

Seed 42, NumPy default RNG permutation of sorted official training filenames:
167 normal fitting images and 42 disjoint normal validation images. Threshold
is the higher 95th percentile of validation anomaly scores, without any defect
labels or masks. Exact filenames and content hashes are in model `config.json`.
No test data enter fitting, feature scale estimation, or threshold selection.

Before looking at test predictions, filename `000.png` in each test condition
(including good) was designated a demo and excluded from evaluation. Thus the
reported test has 19 normal, 19 broken_large, 21 broken_small and 20 contamination
images (79 total). Test masks were decoded for integrity, but not used to train,
calibrate or claim segmentation performance. Train/validation versus test hash
overlap is checked by the evaluator. The official benchmark does not expose
physical batch/session IDs; independence beyond the official split cannot be
verified. Owned acquisitions must be split by object/batch/session, with all
augmentations of a source kept together.

Demo images are unchanged copies; visualization evidence and fitted normal
features are derivatives and distributed under the same noncommercial license.
Credit: Paul Bergmann, Michael Fauser, David Sattlegger, Carsten Steger,
MVTec Software GmbH, CVPR 2019; extended IJCV article:
https://doi.org/10.1007/s11263-020-01400-4 . See `NOTICE.md`.
