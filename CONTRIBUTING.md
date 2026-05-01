# Contributing

## Repository layout

```
tilth/
├── README.md
├── READING.md
├── CONTRIBUTING.md
├── DECISIONS.md
├── LICENSE
├── Makefile
├── docker-compose.yml
├── pyproject.toml                    # uv workspace root
│
├── docs/
│   ├── architecture.md
│   └── threat-model.md
│
├── config/
│   ├── write-policy.yaml
│   ├── read-policy.yaml
│   ├── stores.yaml                   # multi-store namespace routing
│   └── .env.example
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
│   │   │   ├── _shared/
│   │   │   │   ├── auth.py           # x-workload-identity extraction
│   │   │   │   ├── policy.py         # YAML policy loading
│   │   │   │   ├── rate_limit.py     # per-caller token bucket
│   │   │   │   ├── health.py         # /healthz and /metrics
│   │   │   │   ├── models.py         # embedding + LLM provider abstraction
│   │   │   │   └── store_router.py   # multi-store namespace routing
│   │   │   ├── ingest/
│   │   │   │   ├── __main__.py       # uvicorn entrypoint
│   │   │   │   ├── app.py            # FastAPI app factory
│   │   │   │   ├── scrubber.py       # Presidio PII scrubbing
│   │   │   │   ├── batcher.py        # async queue → embed → upsert
│   │   │   │   ├── chunker.py        # sentence-boundary text splitting
│   │   │   │   └── models.py         # Pydantic request/response
│   │   │   └── query/
│   │   │       ├── __main__.py       # uvicorn entrypoint
│   │   │       ├── app.py            # FastAPI app factory
│   │   │       ├── filters.py        # Qdrant filter + closing-tag escape
│   │   │       └── models.py         # Pydantic request/response + schema
│   │   └── tests/
│   │
│   ├── tilth-mcp/                    # pip install tilth-mcp (MCP server)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── src/tilth_mcp/
│   │   │   ├── __init__.py
│   │   │   ├── __main__.py
│   │   │   └── server.py
│   │   └── tests/
│   │
│   └── tilth-agent/                  # pip install tilth-agent (reasoning)
│       ├── pyproject.toml
│       ├── src/tilth_agent/
│       │   ├── __init__.py
│       │   ├── __main__.py
│       │   ├── reasoning.py          # agentic loop with tool use
│       │   ├── tools.py              # tool definitions + execution
│       │   ├── memory.py             # persistent agent memory
│       │   └── prompts/system.md     # reasoning framework
│       ├── config/okrs.yaml
│       ├── data/agent-memory.md
│       └── tests/
│
└── e2e/
    ├── test_end_to_end.py
    └── conftest.py
```

## Tooling

- Python 3.11+, `uv` workspaces, `hatchling` build backend.
- `ruff` for lint + format. `mypy --strict` for types.
- `pytest` with `pytest-asyncio`. `respx` for HTTP mocking.
- `qdrant-client` 1.17+ — uses `query_points()`, not `search()`.
- Auth mode: set `TILTH_AUTH_MODE=dev` (default, trusts `x-workload-identity`
  header) or `TILTH_AUTH_MODE=prod` (validates JWT from `Authorization:
  Bearer` header). In prod mode, `TILTH_JWT_SECRET` and optionally
  `TILTH_JWT_ALGORITHM` are required. See `.env.example`.

Don't add dependencies without a reason. Log additions in `DECISIONS.md`.

## Conventions

### Code style

- Type hints everywhere. `mypy --strict` must pass.
- Prefer pydantic models over raw dicts for anything crossing a module boundary.
- Modules whose names start with `_` are private.
- Docstrings on public functions and classes. Skip on obvious internals.
- No `print()` in production code. Use `logging`.

### Error handling

- The client library never raises into caller code. Drop and metric instead.
- The gateways raise structured HTTP errors; don't leak internal details.
- Logs include enough context to debug but never include secrets or
  full request bodies.

### Configuration

- One config module per package. All env-var reads happen there.
- Required env vars fail loudly at startup.
- Optional env vars have sensible defaults documented in the module.

### Tests

- Unit tests in `tests/` per package.
- Integration tests use real Qdrant via docker-compose.
- E2E tests bring up the whole stack via the public API.
- No test depends on the network beyond localhost.

## Common traps

- **Don't add a "source" parameter to `send()`.** Source comes from caller
  identity at the gateway.
- **Don't make a read library.** Reads go through the gateway or MCP server.
- **Don't catch and re-raise `httpx` errors with the URL in the message.**
  Internal URLs in client-facing errors are an info leak.
- **Don't share Qdrant credentials between the two gateways.**
- **Don't skip the closing-tag escape in query results.** A poisoned record
  with `</retrieved_document>` in text is an injection vector.

## The seven invariants

1. Caller identity is set server-side, never trusted from the client.
2. Namespace ACLs are enforced server-side.
3. Read and write permissions are independent.
4. The library never raises into caller code.
5. Retrieved content is wrapped in `<retrieved_document>` tags with provenance.
6. Metadata keys are allowlisted.
7. PII scrubbing runs on every write.

Full version with rationale: `docs/architecture.md`.

## Pull request checklist

- [ ] All tests pass (`make test`)
- [ ] `ruff check` clean
- [ ] Coverage >80%
- [ ] Errors don't leak internal details
- [ ] No `print()`, no commented-out code
- [ ] `DECISIONS.md` updated for any non-obvious choice
