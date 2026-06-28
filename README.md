# hermes-jester

Small authenticated service that lets other applications push data into a queue
for **hermes** (the agent in exe.dev) to process. Senders POST/GET items of a
pre-registered, schema-validated *type*; hermes polls the queue on a cron, reads
only **new** (unread) items, and acks them so nothing is processed twice. A simple
Google-authenticated web UI manages types, the queue, and API keys.

- **Stack:** Python + FastAPI, SQLite (used as a flexible JSON KV store).
- **Auth:** self-managed long-lived API keys (bearer) for the API; Google OAuth for the UI.
- **Deploy:** an exe.dev VM with the proxy set public — see [`deploy/README.md`](deploy/README.md).

## Concepts

- **Type** — a named category of data with a JSON Schema. Item payloads are
  validated against it on submit and rejected (422) if they don't match.
- **Item** — the posted JSON body (validated against the type's schema), plus
  system fields (`id`, `type`, `source`, `created_at`, `read_at`).
- **API key scopes** — `write` (submit), `read` (poll/ack, for hermes),
  `admin` (manage types & keys; implies the others).

## Local development

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest                 # run the test suite
JESTER_DB_PATH=data/jester.db .venv/bin/python -m jester.admin init-db
.venv/bin/uvicorn jester.app:create_app --factory --reload --port 8077
```

## Admin CLI

```bash
python -m jester.admin init-db
python -m jester.admin create-key --name hermes-cron --scope read
python -m jester.admin list-keys
python -m jester.admin revoke-key <key_id>
python -m jester.admin register-type --name link --description "A link" --schema-file link.schema.json
```

## API

REST API. All `/api/*` routes require `Authorization: Bearer <api_key>`. The
item **type is part of the path** (`/api/item/{type}`).

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| GET    | `/health` | — | liveness |
| GET    | `/api/discover` | read | self-describing manifest of all types + how to consume them |
| GET    | `/api/types` | read | list types |
| POST   | `/api/types` | admin | create a type `{name, description, schema}` |
| GET    | `/api/types/{type}` | read | fetch a type |
| PUT    | `/api/types/{type}` | admin | update a type |
| DELETE | `/api/types/{type}` | admin | delete a type (409 if items exist) |
| POST   | `/api/item/{type}` | write | submit an item — the request body **is** the payload |
| GET    | `/api/items` | read | cross-type feed: `?unread=true&type=&since=<iso>&limit=50` |
| GET    | `/api/item/{type}` | read | items of one type: `?unread=&since=&limit=` |
| GET    | `/api/item/{type}/{id}` | read | fetch one item |
| PATCH  | `/api/item/{type}/{id}` | read | mark read/unread `{"read": true}` |
| DELETE | `/api/item/{type}/{id}` | admin | delete one item |
| POST   | `/api/items/ack` | read | bulk mark read `{ids:[...]}` |

Submitting an item — the request body is the payload, validated against the
type's JSON Schema:

```bash
curl -X POST https://lectern-queenside.exe.xyz/api/item/link \
  -H "Authorization: Bearer $WRITE_KEY" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com"}'
```

The management UI shows ready-to-run examples for each registered type under
**Types → Usage examples**.

## hermes cron loop

Give hermes a `read`-scoped key. It can call `GET /api/discover` once to learn
every registered type — what each is for, the content schema (with an example),
and the exact URLs to fetch them — then on each cron tick it drains the new items:

```bash
BASE=https://lectern-queenside.exe.xyz
# 1. fetch unread items (oldest first)
items=$(curl -s "$BASE/api/items?unread=true&limit=100" -H "Authorization: Bearer $READ_KEY")
# 2. ...hermes processes each item...
# 3. ack the ones it handled so they don't come back
ids=$(echo "$items" | jq -c '[.[].id]')
curl -s -X POST "$BASE/api/items/ack" -H "Authorization: Bearer $READ_KEY" \
  -H 'Content-Type: application/json' -d "{\"ids\": $ids}"
```

`since` (an ISO-8601 timestamp) is available as an additional window filter, but the
`unread` flag is the primary "only the new stuff" mechanism.

## Management UI

`https://lectern-queenside.exe.xyz/` — sign in with an allowlisted Google account
(`JESTER_ALLOWED_EMAILS`). Dashboard, queue browser (view / ack / mark-unread /
delete), type editor, and API-key management (create shows the token once; revoke).

## Deployment

See [`deploy/README.md`](deploy/README.md).
