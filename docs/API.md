# API and data contract

Interactive schema at `/docs`. All `/api` endpoints except login and the
minimal health check require an authenticated session cookie. The production
frontend is same-origin. Mutation requests with an unapproved Origin are denied;
SameSite=strict cookies further limit cross-site requests. No remote URL input.

| Endpoint | Access | Contract |
|---|---|---|
| POST /api/auth/login | Public, throttled | JSON username/password, sets HttpOnly 8-hour cookie |
| GET /api/auth/me | All roles | Current username/role |
| POST /api/auth/logout | All roles | Revoke current session |
| GET /api/profiles | All roles | Supported category, scope, model status/version |
| GET /api/vocabulary | All roles | Decisions, suggestions, capture methods |
| POST /api/inspections | Admin/reviewer | Multipart file, profile, optional product/batch, capture_method, optional timezone-aware captured_at; required Idempotency-Key header |
| GET /api/inspections | All roles | Filtered records, total, counts, offset/limit |
| GET /api/inspections/{id} | All roles | Machine result, metadata, ordered review history |
| GET /api/inspections/{id}/image/{kind} | All roles | Private original or heatmap; kind original/heatmap |
| POST /api/inspections/{id}/reviews | Admin/reviewer | JSON decision, reason, expected_revision |
| GET /api/export.csv | Admin/reviewer | CSV matching the same active filters |
| DELETE /api/inspections/{id} | Admin | JSON reason; delete images, scrub product/batch; preserve audit |
| GET /api/diagnostics | Admin | Model config and actionable loading error |
| POST /api/feedback/export | Admin | Persist/return versioned candidate label JSON, excludes exact official test hashes |
| POST /api/users | Admin | JSON username, password (12+ chars), role |

Filters: `q` (literal substring of product/batch/ID), exact `product`, exact
`batch`, `profile`, `review` (pending/reviewed), `suggestion`
(normal/suspected_defect/needs_review), `date_from` and `date_to` (ISO date,
UTC submitted day inclusive). `offset` >=0; `limit` 1–100, default 50. Counts and
CSV span **all** matching rows, not only the current page. Deleted records are
excluded. UI timestamps use the browser's local timezone; date filters use UTC.
Counts include accepted inspection records with processing errors, which remain
needs-review records. "Reviewed" means a human decision exists; a human
needs-review decision is not a normal or defect confirmation.

Valid image inputs: one PNG/JPEG/WebP, non-animated, 64+ pixels each side, <=20M
pixels, <=10 MiB; declared MIME must match decoded format. The original upload
bytes and SHA-256 are retained, and inference applies EXIF orientation. Failed
validation returns 4xx and creates no normal record. A valid input with missing
model, storage or inference failure creates an `error` result whose suggestion
is `needs_review`. Successful results preserve numeric score, threshold,
preprocessing version, fitted-artifact checksum, warnings, and timing.

Every accepted input gets a UUID; caller filenames are ignored for storage.
Idempotency keys are scoped to the submitting user. Reusing the same key and
identical request returns the original record; changing the request returns
409. Concurrent retries cannot create duplicate rows. Resubmitting the same
image deliberately with a new key creates a new inspection. A retry during a
request can return `processing`; read the detail endpoint for the final result.
The UI blocks duplicate clicks and gives each new image/metadata selection a
new key. No job queue or implicit retry route exists: synchronous CPU inference
runs in FastAPI's thread pool with at most two simultaneous model calls. A
single supported Uvicorn process resolves interrupted markers to explicit
errors on restart. Rerunning an interrupted inference is an intentional new
inspection and preserves the failed record.

Reviews use `normal`, `defect` or `needs_review`; a 3–2000 character reason is
required. The server derives reviewer identity from the session. Atomic revision
checks reject concurrent stale reviews with 409. New review events append;
original machine results are never replaced. Latest review drives the current
human decision; all previous decisions remain in detail history. Review date,
processing date and capture date are separate. Uploaded images do not assume a
capture date from their filesystem or EXIF metadata.

CSV exports neutralize spreadsheet formula prefixes in caller-supplied values.
They include original suggestion/score/version and current human decision/date.
Full review reasons/history are available in detail JSON. Export and retention
actions are separately audited. API DB credentials/admin access must be trusted;
audit tables are application-append-only, not cryptographically tamperproof.
