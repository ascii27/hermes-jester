# hermes-jester — Design & Plan

Living design doc. Update it as the service evolves so future work has a single
reference for intent, architecture, and the deploy workflow.

## Context

Other applications had no way to push data to **hermes** (the agent running on
exe.dev) for it to process or act on. `hermes-jester` is the receiving end: a
small authenticated service that accepts data from other apps, validates it
against pre-registered types, stores it in a queue, and exposes a REST API that
hermes polls on a cron — fetching only new (unread) items and acking them so it
never reprocesses. A Google-authenticated web UI lets the owner manage types,
browse the queue, and issue API keys.

## Decisions (current)

- **Stack:** Python + FastAPI + uvicorn.
- **Storage:** SQLite as a flexible JSON store (one file on the exe.dev persistent disk).
- **Types:** registered ahead of time; each carries a JSON Schema. Posted item
  bodies are validated and **rejected (422)** on mismatch.
- **Items:** the **request body *is* the payload** — there is no `{payload, metadata}`
  envelope and no metadata concept. The service adds system fields only.
- **Read model:** per-item `read_at`. hermes polls unread (optionally by
  `type`/`since`), processes, then acks by id.
- **API auth:** self-managed long-lived API keys (bearer), stored hashed, scopes
  `write` / `read` / `admin` (`admin` implies the others).
- **UI auth:** app-level Google OAuth (Authlib) + signed session cookie;
  allowlist via `JESTER_ALLOWED_EMAILS` (default the owner's account).
- **Deploy:** exe.dev VM `lectern-queenside`, HTTP proxy set **public** so external
  apps reach it with our own bearer tokens; the app owns all authentication.

## Architecture

Single FastAPI app; server-rendered UI (Jinja2 + minimal CSS, no separate
frontend build); one SQLite file. The proxy is public at the exe.dev layer; the
app handles all auth — API keys for `/api/*`, Google OAuth sessions for the UI.

```
jester/
  config.py        # env-driven settings
  clock.py         # single UTC ISO8601 now()
  db.py            # SQLite connect + idempotent schema init + migrations
  errors.py        # domain errors -> HTTP status mapping
  types_repo.py    # type registry CRUD + JSON Schema validation
  items_repo.py    # queue: submit / query / ack / set_read / delete
  keys_repo.py     # API keys: create (plaintext once) / authenticate / revoke / scopes
  examples.py      # sample payload from a JSON Schema (for UI usage examples)
  models.py        # pydantic request models
  auth_api.py      # bearer dependency + scope enforcement
  auth_ui.py       # Google OAuth routes + session require_user gate
  api.py           # /api/* REST routes
  ui.py            # /, /login, /ui/* routes + render helper
  app.py           # factory: middleware, routers, static, exception handlers, /health
  admin.py         # CLI
  templates/ static/
tests/             # repos, api, ui, examples, admin
deploy/            # systemd unit, env example, exe.dev README
docs/DESIGN.md     # this file
```

## Data model (SQLite)

ISO8601 UTC text timestamps (sort lexically). JSON stored as TEXT.

- `types(name PK, description, schema, created_at, updated_at)`
- `items(id PK, type → types.name, payload, source, created_at, read_at NULL)`
  - indexes: `(read_at, created_at)`, `(type)`, `(created_at)`
- `api_keys(id PK, name, token_hash, scope, created_at, revoked_at NULL)`

`payload` = the posted JSON body (validated). `source` = the submitting key's name.
Migrations live in `db._migrate` (e.g. it drops the legacy `items.metadata` column).

## REST API (`Authorization: Bearer <api_key>`)

Item **type is part of the path**. Scopes: `admin` implies all; `write` = submit;
`read` = poll/ack.

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| GET    | `/health` | — | liveness |
| GET    | `/api/types` | read | list types |
| POST   | `/api/types` | admin | create type `{name, description, schema}` |
| GET    | `/api/types/{type}` | read | fetch type |
| PUT    | `/api/types/{type}` | admin | update type |
| DELETE | `/api/types/{type}` | admin | delete type (409 if items exist) |
| POST   | `/api/item/{type}` | write | submit — **request body is the payload** |
| GET    | `/api/items` | read | cross-type feed: `?unread=&type=&since=&limit=` |
| GET    | `/api/item/{type}` | read | items of one type: `?unread=&since=&limit=` |
| GET    | `/api/item/{type}/{id}` | read | fetch one item |
| PATCH  | `/api/item/{type}/{id}` | read | mark read/unread `{"read": true}` |
| DELETE | `/api/item/{type}/{id}` | admin | delete one item |
| POST   | `/api/items/ack` | read | bulk mark read `{ids:[...]}` |

## Management UI (Google OAuth session)

- `/login` — public landing page with "Sign in with Google"; `require_user`
  redirects gated routes here.
- `/auth/login` → Google; `/auth/callback` verifies the email allowlist and sets
  the session; `/auth/logout`.
- `/` dashboard (counts) · `/ui/types` (list + create/edit + **per-type usage
  examples** generated from the schema) · `/ui/items` (browse/filter, view,
  ack/unread/delete) · `/ui/keys` (list, create — token shown once, revoke).

## Config (env)

`JESTER_DB_PATH`, `JESTER_SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`JESTER_BASE_URL`, `JESTER_ALLOWED_EMAILS`.

## Admin CLI — `python -m jester.admin`

`init-db` (also runs migrations) · `create-key --name --scope` · `list-keys` ·
`revoke-key <id>` · `register-type --name --description --schema-file`.

## Deployment (exe.dev: lectern-queenside)

The VM proxy forwards to **port 8000**; the service binds there. Full steps in
[`../deploy/README.md`](../deploy/README.md). Summary:

1. Create a Google OAuth client; redirect URI `https://lectern-queenside.exe.xyz/auth/callback`.
2. Ship code (the VM has no GitHub creds, so push then deploy by archive):
   `git archive --format=tar <branch> | ssh lectern-queenside.exe.xyz 'tar -x -C ~/hermes-jester'`
3. `uv venv && uv pip install -e .`, write `.env`, `python -m jester.admin init-db`,
   mint keys.
4. systemd unit `deploy/jester.service` (User `exedev`, port 8000), `systemctl enable --now jester`.
5. `ssh exe.dev share set-public lectern-queenside` (external apps use our bearer
   tokens; this disables exe.dev's built-in login, which is why UI auth is in-app).

## Standing workflow — after every phase

1. Run the test suite; ensure green.
2. Commit and push to the feature branch.
3. Deploy to `lectern-queenside`: archive the branch to the VM, run
   `python -m jester.admin init-db` (applies migrations), `sudo systemctl restart jester`.
4. Verify against the public URL (`/health`, plus the endpoints touched this phase).

## hermes cron loop

hermes holds a `read` key. Each tick: `GET /api/items?unread=true&limit=N`,
process, then `POST /api/items/ack {ids}` for what it handled. `since` (ISO-8601)
is an extra window filter; `unread` is the primary "only new stuff" mechanism.

## Testing / verification

- Unit + integration via pytest (temp SQLite, FastAPI TestClient): auth
  (missing/bad/revoked/wrong-scope), type CRUD + schema rejection + delete-409,
  submit valid/invalid, per-type & cross-type reads, PATCH/ack read model,
  delete, UI auth gate + allowlist, schema-example generation, migration.
- Local end-to-end with uvicorn + curl; production smoke test after each deploy.
