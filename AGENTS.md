# AGENTS.md

Operating guide for building tilth. Read fully before starting.

## Repository layout

```
tilth/
├── README.md
├── READING.md
├── AGENTS.md
├── DECISIONS.md
├── LICENSE
├── Makefile
├── docker-compose.yml
├── pyproject.toml                    # uv workspace root
├── uv.lock
│
├── docs/
│   ├── architecture.md
│   └── threat-model.md
│
├── config/
│   ├── write-policy.yaml
│   ├── read-policy.yaml
│   └── .env.example
│
├── reference/                        # sketches, not shipped code
│   ├── sketch_client.py
│   ├── sketch_ingest_gateway.py
│   ├── sketch_query_gateway.py
│   └── sketch_mcp_server.py
│
├── packages/
│   ├── tilth/                        # pip install tilth (client library)
│   │   ├── pyproject.toml
│   │   ├── src/tilth/
│   │   │   ├── __init__.py           # exports: send, asend, VectorHandler
│   │   │   ├── _client.py            # queue, worker, send logic
│   │   │   ├── _config.py            # env var reads
│   │   │   ├── _metrics.py           # counters, gauges
│   │   │   └── testing.py            # recording() helper
│   │   └── tests/
│   │
│   ├── tilth-server/                 # pip install tilth-server (gateways)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── src/tilth_server/
│   │   │   ├── __init__.py
│   │   │   ├── _shared/              # auth, policy, rate limiting, health
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── policy.py
│   │   │   │   ├── rate_limit.py
│   │   │   │   └── health.py
│   │   │   ├── ingest/               # ingest gateway
│   │   │   │   ├── __init__.py
│   │   │   │   ├── app.py
│   │   │   │   ├── scrubber.py
│   │   │   │   ├── batcher.py
│   │   │   │   └── models.py
│   │   │   └── query/                # query gateway
│   │   │       ├── __init__.py
│   │   │       ├── app.py
│   │   │       ├── filters.py
│   │   │       └── models.py
│   │   └── tests/
│   │
│   └── tilth-mcp/                    # pip install tilth-mcp (MCP server)
│       ├── pyproject.toml
│       ├── Dockerfile
│       ├── src/tilth_mcp/
│       │   ├── __init__.py
│       │   └── server.py
│       └── tests/
│
└── e2e/
    ├── test_end_to_end.py
    └── conftest.py
```

The two gateways share auth, policy loading, rate limiting, and health
endpoints via `tilth_server._shared`. They run as separate processes from
the same package — docker-compose starts two containers with different
entrypoints.

## Tooling baseline

- Python 3.11+. Pin `requires-python = ">=3.11"` in each `pyproject.toml`.
- `uv` workspaces. One root `pyproject.toml`, per-package `pyproject.toml`.
- `hatchling` as the build backend for all packages.
- `ruff` for lint + format. Configure once at the repo root.
- `mypy --strict` on all packages.
- `pytest` with `pytest-asyncio` for async tests.
- `httpx` for HTTP (sync and async).
- `pydantic` v2 for request/response models.
- `fastapi` for the gateways.
- `qdrant-client` for vector store access.
- `mcp` (the official Python SDK) for the MCP server.
- `presidio-analyzer` + `presidio-anonymizer` for PII scrubbing.

Don't add dependencies without a reason. Log additions in `DECISIONS.md`.

## How to work

### Start each spec by reading it fully

Each spec in `specs/` has: scope, interface, acceptance criteria, out-of-scope,
notes. Read all sections before writing code. Acceptance criteria are the bar;
out-of-scope items are traps.

### Test as you go, not at the end

For each module: write the interface, write a test, implement, verify the
test passes. The tests in each spec's acceptance criteria are the minimum.

### When a spec is ambiguous

Pick the simpler interpretation, implement it, and add an entry to
`DECISIONS.md`:

```markdown
## YYYY-MM-DD — [topic]
**Spec:** [which spec section was ambiguous]
**Choice:** [what you did]
**Why:** [briefly]
**Reversibility:** easy | medium | hard
```

### When something contradicts the spec

Stop. Don't silently change the architecture. Surface the contradiction in
`DECISIONS.md` under "Blockers" and proceed with the spec as written if you
can.

### When a test is hard to write

That usually means the design is wrong, not the test. Refactor the code to
be testable. The exception is integration points (HTTP, Qdrant, OpenAI) —
mock those at the boundary.

## Build order (do not deviate)

1. `tilth` (client library) — spec 01
2. `tilth-server` shared internals — prerequisite for specs 02-03
3. `tilth-server` ingest gateway — spec 02
4. `tilth-server` query gateway — spec 03
5. `tilth-mcp` — spec 04
6. e2e + docker-compose + Makefile — spec 05

## Conventions

### Code style

- Type hints everywhere. `mypy --strict` must pass.
- Prefer pydantic models over raw dicts for anything crossing a module boundary.
- Modules whose names start with `_` are private.
- Docstrings on public functions and classes. Skip on obvious internals.
- No `print()` in production code. Use `logging`.

### Error handling

- The client library never raises into caller code. Drop and metric instead.
- The gateways raise structured HTTP errors with status codes; don't leak
  internal exception details.
- Logs include enough context to debug but never include secrets or full
  request bodies.

### Async

- Gateways are async (FastAPI). Use `httpx.AsyncClient` and
  `qdrant_client.AsyncQdrantClient`.
- The client library is sync at the API surface with an `asend()` shim.
  The background worker is a sync thread — deliberate, since the library
  must work in services that aren't async.

### Configuration

- One config module per package. All env-var reads happen there.
- Required env vars fail loudly at startup with a clear message.
- Optional env vars have sensible defaults documented in the module.

### Tests

- Unit tests in `tests/` per package.
- Integration tests use real Qdrant via docker-compose.
- E2E tests bring up the whole stack and exercise it through the public API.
- No test depends on the network beyond localhost.

## Common traps

- **Don't add a "source" parameter to `send()`.** Source comes from caller
  identity at the gateway. Letting clients set it defeats the audit trail.
- **Don't make a read library.** There is no read library. Reads go through
  the gateway or MCP server.
- **Don't catch and re-raise `httpx` errors with the URL in the message.**
  Internal URLs in client-facing errors are an info leak.
- **Don't share Qdrant credentials between the two gateways.** Different
  permissions, different rotation schedules, different blast radius.
- **Don't skip the closing-tag escape in query results.** A poisoned record
  with `</retrieved_document>` in its text is a real injection vector.
- **Don't put the embedding model name in two places without detecting
  mismatch.** Store the model name in Qdrant collection metadata. Both
  gateways validate it matches on startup.

## The seven invariants

If you write code that breaks one of these, stop:

1. Caller identity is set server-side, never trusted from the client.
2. Namespace ACLs are enforced server-side.
3. Read and write permissions are independent.
4. The library never raises into caller code.
5. Retrieved content is wrapped in `<retrieved_document>` tags with provenance.
6. Metadata keys are allowlisted.
7. PII scrubbing runs on every write.

Full version with rationale: `docs/architecture.md`.

## Per-package checklist

Before considering a package "done":

- [ ] Public API matches the spec exactly
- [ ] All acceptance-criteria tests pass
- [ ] `mypy --strict` clean
- [ ] `ruff check` clean
- [ ] Coverage >80%
- [ ] Errors don't leak internal details
- [ ] No `print()`, no commented-out code
- [ ] DECISIONS.md updated for any non-obvious choice

## What "done" looks like for each spec

Every box in the acceptance criteria is verifiable by running a command.
`make test` passes. `mypy --strict` passes. `ruff check` passes.

## What to do when stuck

1. Re-read the relevant spec.
2. Look at `reference/` for a similar pattern.
3. Check `docs/threat-model.md` if it's a security question.
4. Make the simpler choice and log it in DECISIONS.md.
5. Leave a `TODO(unblock):` comment with a clear question, move on.

Don't block the whole project on one ambiguity.
