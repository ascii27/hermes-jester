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
- **Item** — an envelope: a validated `payload` (the data), free-form `metadata`
  (sender context), plus system fields (`id`, `type`, `source`, `created_at`, `read_at`).
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

All `/api/*` routes require `Authorization: Bearer <api_key>`.

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| GET  | `/health` | — | liveness |
| POST | `/api/types` | admin | register a type `{name, description, schema}` |
| GET  | `/api/types` · `/api/types/{name}` | read | list / fetch types |
| PUT  | `/api/types/{name}` | admin | update a type |
| POST | `/api/items` | write | submit `{type, payload, metadata?}` |
| GET  | `/api/submit` | write | submit via query params (`type`, JSON `payload`, JSON `metadata`) |
| GET  | `/api/items` | read | poll: `?unread=true&type=&since=<iso>&limit=50` |
| GET  | `/api/items/{id}` | read | fetch one item |
| POST | `/api/items/ack` | read | mark read `{ids:[...]}` |

Submitting an item:

```bash
curl -X POST https://lectern-queenside.exe.xyz/api/items \
  -H "Authorization: Bearer $WRITE_KEY" -H 'Content-Type: application/json' \
  -d '{"type":"link","payload":{"url":"https://example.com"},"metadata":{"from":"reader"}}'
```

GET submission (for sources that can only issue GETs):

```bash
curl -G https://lectern-queenside.exe.xyz/api/submit \
  -H "Authorization: Bearer $WRITE_KEY" \
  --data-urlencode 'type=link' \
  --data-urlencode 'payload={"url":"https://example.com"}'
```

## hermes cron loop

Give hermes a `read`-scoped key. On each cron tick it drains the new items:

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
