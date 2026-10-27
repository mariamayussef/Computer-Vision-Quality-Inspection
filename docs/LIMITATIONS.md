# Limits and outstanding validation

- **Controlled bottle images only.** A webcam photo with a different pose,
  background, bottle type, perspective or lighting is outside validated scope.
  No object detector establishes that a supported bottle is present. Match the
  profile's centered, top-down, square framing before interpreting a suggestion.
- Normal-only fitting measures appearance differences. The baseline can react
  to harmless reflections and miss subtle contamination. A score is not a
  calibrated defect probability and the heatmap is not validated segmentation.
- The normal calibration set contains 42 images. Its nominal 95th-percentile
  rule does not guarantee a 5% factory false-reject rate: observed held-out
  normal false rejects were **3/19 (15.79%)**. One of 60 defects was missed.
  Results are small-sample benchmark estimates, not savings or reliability claims.
- Defect examples are only used for final test measurement. No development defect
  recall/precision was validated during threshold selection. The now-inspected
  test set must not be used for future tuning and then called untouched.
- Heuristic blur/darkness/overexposure/low-contrast/aspect warnings abstain. They
  do not guarantee product presence, image suitability, or protection against
  all blank scenes. Operators can override warnings with a reason; review is
  mandatory for actual product-release decisions regardless of suggestion.
- Localization metrics are intentionally not reported: coarse handcrafted maps
  have not been validated as segmentation. No precise region label, box or
  fine-grained defect class is asserted.
- No physical webcam or browser camera permission was exercised. Manual capture
  and denied/unavailable handling are implemented; verify device selection,
  permission denial, orientation and framing on actual target hardware.
- Local SQLite migrations, persisted workflow and fresh app lifespan restart
  were exercised. Docker is absent in this environment; PostgreSQL/Compose build,
  migrations, volume permissions and container restart require deployment validation.
- UI desktop upload/inference/review was exercised using real labeled demo data
  in an isolated test database. Factory user-acceptance testing remains outstanding.
- One organization, one Uvicorn process. History/counts currently materialize
  filtered rows and their reviews in memory; this is suitable for a small
  portfolio prototype, not millions of records. Move filters/aggregates fully
  into SQL and add proper operational monitoring before expanding volume.
- Password throttling is in-memory per client IP and resets on restart. There
  is no MFA, password-reset/email flow, account disable UI, SSO or tenant
  isolation. All authenticated workspace users may view all inspection images.
- Audit history is append-only through the app, not tamperproof against DB
  administrators. Image deletion retains technical hashes, results, reviewer
  identities and written reasons; it is not total erasure of every personal datum.
- Candidate-feedback exclusion uses byte-identical official test hashes.
  Reencoded, cropped or augmented test images require manual provenance review.
  Candidate export does not automatically constitute a validated training set.
- Dataset, demos and fitted model are noncommercial CC BY-NC-SA 4.0. MIT app
  source does not remove those restrictions. No paid infrastructure or public
  deployment has been created. No regulatory, factory savings or scrap-reduction
  claim has been measured or implied.
