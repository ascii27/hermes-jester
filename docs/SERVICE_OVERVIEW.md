# hermes-jester — Service Overview (for design)

This document describes the service in plain terms: what it is, who uses it, the
end-to-end flows, and every screen in the web UI. It's written to give a designer
(human or Claude) enough context to redesign or extend the interface without
reading the code. For architecture and data-model detail see
[`DESIGN.md`](DESIGN.md).

---

## 1. What the service is

**hermes-jester is an authenticated inbox and queue.** Other applications push
small JSON "items" into it; an agent called **hermes** (running on exe.dev) drains
the queue on a schedule, processing only what's new.

Think of it as a typed, validated message box:

- **Producers** (any external app, webhook, or script) POST items in. Each item
  must match a pre-registered **type** with a JSON Schema — anything that doesn't
  fit is rejected.
- **The consumer** (hermes) polls for **unread** items, processes them, and
  **acks** (acknowledges) them so they're never handed out again.
- **The owner** (a single Google-authenticated person) uses a web UI to register
  types, watch the queue, and mint API keys.

There is no separate frontend build — the UI is server-rendered HTML with a small
stylesheet. It's intentionally utilitarian: tables, forms, and code snippets.

### The three actors

| Actor | Who | How they authenticate | What they do |
|-------|-----|----------------------|--------------|
| **Producer** | External apps / webhooks / scripts | API key (bearer), `write` scope | Submit items |
| **Consumer** | hermes (the cron agent) | API key (bearer), `read` scope | Poll unread, ack |
| **Owner** | The human operator | Google sign-in (session) | Manage types, keys; browse queue |

### Core concepts

- **Type** — a named category of item (e.g. `github-pr`, `calendar-invite`) with a
  JSON Schema describing its payload. Types are registered up front.
- **Item** — one submitted JSON payload of a given type. The HTTP request body
  *is* the payload; the service only adds system fields (id, type, source,
  timestamps, read state). An item is **unread** until acked, then **read**.
- **Source** — the name of the API key that submitted the item (so the owner can
  see where each item came from).
- **API key** — a long-lived bearer token with a scope: `write` (submit),
  `read` (poll/ack), or `admin` (manage everything; implies the others). Shown in
  plaintext exactly once at creation, stored hashed.

---

## 2. End-to-end flows

### Flow A — Producer submits an item

```
External app ──POST /api/item/{type}──▶ jester
                 Bearer <write-key>        │
                 body = payload            ├─ validate against type's JSON Schema
                                           │     ✗ mismatch → 422 rejected
                                           └─ store as unread item, source = key name
```

The producer just needs a `write` key and the type name. The body it sends is the
payload verbatim — no envelope, no metadata wrapper.

### Flow B — Consumer (hermes) drains the queue

This is the heartbeat of the system, run on a cron:

```
Each tick:
  1. GET  /api/items?unread=true&limit=N      → list of new items (any type)
  2. (hermes processes each item)
  3. POST /api/items/ack  {ids:[...]}          → mark handled items read
```

`unread=true` is the primary "only new stuff" filter. An optional `since=<iso8601>`
narrows by time window. Once acked, items won't be returned by an unread poll
again — hermes never reprocesses.

### Flow C — Discovery (hermes learns what exists)

Before/while polling, hermes can call `GET /api/discover` to get a self-describing
manifest: every type's purpose, its content schema + a concrete example payload,
the exact fetch URLs, and the polling/ack mechanism. This lets the consumer adapt
to new types without code changes.

### Flow D — Owner operates the service (web UI)

```
Owner ──▶ /login ──Google OAuth──▶ allowlist check ──▶ session ──▶ Dashboard
           then: register types · mint keys · browse & triage the queue
```

The owner's job is setup and oversight: define what types of data can come in,
hand out scoped keys to producers and to hermes, and watch/triage the queue.

---

## 3. The web UI — screens

All UI screens except `/login` require a logged-in, allowlisted Google account.
Every authenticated page shares a **top bar**: brand (links to Dashboard) ·
nav (Dashboard · Items · Types · Keys) · current user email · Sign out.
An error or success banner can appear at the top of the main content area.

### Screen map

```
/login  ──sign in──▶  /  (Dashboard)
                       ├──▶ /ui/items ──▶ /ui/items/{id}   (item detail)
                       ├──▶ /ui/types ──▶ /ui/types/{name}/edit
                       └──▶ /ui/keys
```

---

### 3.1 Login (`/login`) — public

The only unauthenticated page. A centered landing card:

- 🃏 logo, title **hermes-jester**
- Tagline: "An authenticated inbox & queue for hermes."
- Short blurb explaining producers push items and hermes drains them
- **Sign in with Google** button (primary)
- Fine print: "Access is limited to authorized accounts."

Sign-in goes through Google OAuth; only allowlisted emails are admitted (others
get a 403 "this Google account is not authorized"). Unauthenticated visits to any
gated page redirect here.

### 3.2 Dashboard (`/`)

At-a-glance health of the queue. Four stat cards:

- **Items** (total) · **Unread** · **Types** (count) · **API keys** (count)

Below: **Registered types** as a pill list linking to the Types page (or an empty
state prompting the owner to register one).

### 3.3 Items (`/ui/items`)

The queue browser and triage surface.

- **Filters** (GET form): Type (All + each registered type) · State (All /
  Unread only) · Filter button.
- **Items table**, newest-relevant first, columns: Created · Type · Source ·
  Status (read/unread tag) · Preview (the payload as compact JSON) · Actions.
  Unread vs. read rows are visually distinguished.
- **Row actions**: **View** (detail) · **ack** (if unread) or **unread** (if
  read) · **delete** (with confirm dialog).
- Empty state: "No items."

Listing is capped at 500 items in the UI (this is a browse/triage view, not the
machine feed).

### 3.4 Item detail (`/ui/items/{id}`)

Full view of one item.

- Back link to Items.
- **Metadata** list: ID · Type · Source · Created · Read (timestamp or "unread").
- **Payload**: pretty-printed JSON in a code block.
- **Actions**: **Ack (mark read)** if unread, or **Mark unread** if read; plus
  **Delete** (with confirm).
- If the id doesn't resolve: "Item not found" with a back link.

### 3.5 Types (`/ui/types`)

Manage the catalog of accepted item types.

- **Types table**: Name (code) · Description · Updated · Edit link. Each row has
  an expandable **"Usage examples"** disclosure showing copy-paste `curl`
  snippets — one to **submit** an item of that type (with a generated example
  payload from the schema, needs a `write` key) and one to **poll** that type
  (needs a `read` key).
- **Register a type** form: Name · Description · JSON Schema (textarea,
  pre-filled with an empty object-schema skeleton) · Register button.
- Validation errors (bad JSON, duplicate name, etc.) re-render the form with an
  error banner and the entered values preserved.

### 3.6 Edit type (`/ui/types/{name}/edit`)

- Heading shows the type name (immutable here).
- Form: Description · JSON Schema (pretty-printed in a tall textarea) · Save /
  Cancel.
- Invalid JSON or schema errors re-render with an error banner.

### 3.7 Keys (`/ui/keys`)

Issue and revoke API keys.

- **One-time token reveal**: right after creating a key, a success banner shows
  the new key's name and the **plaintext token in a code block** with "Copy it
  now — it won't be shown again." This is the only time the token is visible.
- **Keys table**: Name · Scope (tag) · Created · Status (active/revoked tag) ·
  revoke action (with confirm; hidden once revoked).
- **Create a key** form: Name (placeholder e.g. "hermes-cron or acme-webhook") ·
  Scope dropdown (`write` / `read` / `admin`) · Create button.
- Footer legend: `write` = submit items · `read` = poll/ack (hermes) ·
  `admin` = manage types & keys.

---

## 4. The REST API (machine surface)

Producers and hermes never touch the UI; they use the API with
`Authorization: Bearer <api_key>`. The item **type is part of the URL path**.
Scopes: `admin` implies all; `write` = submit; `read` = poll/ack/read.

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| GET    | `/health` | — | liveness check |
| GET    | `/api/discover` | read | self-describing manifest (types, schemas, examples, fetch + polling URLs) |
| GET    | `/api/types` | read | list types |
| POST   | `/api/types` | admin | create a type |
| GET    | `/api/types/{type}` | read | fetch a type |
| PUT    | `/api/types/{type}` | admin | update a type |
| DELETE | `/api/types/{type}` | admin | delete a type (409 if items exist) |
| POST   | `/api/item/{type}` | write | submit — **request body is the payload** |
| GET    | `/api/items` | read | cross-type feed: `?unread=&type=&since=&limit=` |
| GET    | `/api/item/{type}` | read | items of one type: `?unread=&since=&limit=` |
| GET    | `/api/item/{type}/{id}` | read | fetch one item |
| PATCH  | `/api/item/{type}/{id}` | read | mark read/unread `{"read": true}` |
| DELETE | `/api/item/{type}/{id}` | admin | delete one item |
| POST   | `/api/items/ack` | read | bulk mark read `{"ids":[...]}` |

Validation failures on submit return **422**; the UI/API map domain errors to
their HTTP status (missing/bad/revoked key → 401/403, not-found → 404,
delete-with-dependents → 409).

---

## 5. Design notes & opportunities

Things a designer should know about the current state:

- **Visual language is minimal**: a top nav, stat cards, data tables with
  read/unread + scope/status **tags**, simple stacked forms, and `<pre>` code
  blocks for JSON and curl snippets. There is no client-side JS framework;
  interactions are plain form POSTs with full-page reloads and native
  `confirm()` dialogs for destructive actions.
- **The queue is the heart of the product.** The Items screen is where the owner
  spends time; richer filtering, payload rendering, bulk actions, and live unread
  counts are natural areas to improve.
- **Trust & safety touchpoints**: the one-time token reveal, the destructive
  delete/revoke confirms, and the "unauthorized account" path are the moments
  where clarity matters most.
- **Self-describing by design**: types carry schemas and generate example
  payloads, which already power the per-type usage snippets and the `/api/discover`
  manifest — a designer can lean on that metadata for richer per-type views.
```