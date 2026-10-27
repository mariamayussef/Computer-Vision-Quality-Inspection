# Operation, retention and security

Run all commands from the repository root. `scripts/start.sh` sets up migrations
and the first local admin; it uses the existing `.venv` and built frontend.
Passwords are entered with `getpass`, not stored in source or shell scripts.
CLI creation can also accept `INITIAL_PASSWORD` for controlled noninteractive
setup; unset it immediately afterward and never commit secrets. Additional
reviewer/viewer users can be created via CLI or authenticated admin API.

Default local persistence is `data/inspection.db` (SQLite WAL) and
`data/private/` (generated UUID filenames, mode 0600). The included fitted model
is `models/bottle-v1/`. PostgreSQL is selected with a
`postgresql+psycopg://...` DATABASE_URL. Run `python scripts/manage.py migrate`
before starting the API. The active folder must have a registered immutable
configuration; registration is `python scripts/manage.py register-model`.
A missing or mismatched model keeps the app readable but disables UI inference;
API attempts persist an explicit needs-review error. Diagnostics are admin-only.

The uploaded original image bytes, generated heatmap, source hash, dimensions,
references, capture method/time and machine result are retained. No camera video
or microphone input is recorded. Request logs contain endpoint paths and status,
not image payloads/passwords; application errors log the inspection UUID and
stack trace. A generated private storage interface is used for every image.
No user-supplied remote fetches, public static image mounts or pickle checkpoints.

## Retention

Retention is **manual, indefinite until an administrator deletes it**. Use the
selected-record "Delete retained images" action or authorized DELETE endpoint,
with a reason. Image files are removed and product/batch fields are scrubbed;
records are hidden from normal history/export. Technical metadata, machine
result, hashes, review identities/reasons/timestamps and deletion audit remain.
Authenticated detail access to a tombstone remains for audit; image endpoints
return 404. Do not put sensitive personal content in references/review reasons.
Versioned candidate-feedback snapshots in private storage may also retain
exported metadata; include them in your retention review. Deletion is not a
promise to remove backups or exported copies. Remove those deliberately under
your own retention policy. Protect backup access and encrypt backup media.

## Camera and HTTPS

Browsers typically allow camera permission on `localhost` and `127.0.0.1` over
HTTP. Other origins require HTTPS. HTTPS guidance for a deployment: terminate
TLS at a trusted reverse proxy, forward only to the private application port,
set `COOKIE_SECURE=true`, set `ALLOWED_ORIGIN_HOSTS` to the exact HTTPS hostname
and port, use a trusted certificate, and verify auth/camera in the target
browser. Keep proxy request limits near the app's 10 MiB limit. Do not expose
the database port. Compose binds the app only to 127.0.0.1 by default. Do not
expose a public deployment without reviewing access and licensing first.

## Backups and recovery

Back up the database and private file volume as a consistent pair while writes
are stopped. Preserve all model folders/configs used by stored inspections.
On SQLite, use SQLite's backup API or stop the app before copying DB/WAL files;
copying only the main database during writes is unsafe. Compose uses named
volumes. Stop/restart retains records, sessions and images; never use
`docker compose down -v` unless you intend permanent volume deletion.

Use **one** application process. Startup converts any unfinished persisted
`processing` record to a needs-review error. It does not silently rerun work or
call an error normal. Supply a fresh idempotency key to deliberately inspect
that image again. Already-complete duplicate submissions retain their old UUID.
