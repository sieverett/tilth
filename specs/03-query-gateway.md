# Spec 03: Query gateway (`tilth-server`, query)

## Scope

A FastAPI service that serves reads from agents, dashboards, and tools.
Enforces namespace ACLs server-side, audits queries via structured logging,
and wraps results in injection-resistant framing. Part of the `tilth-server`
package, deployed as its own container.

## Interface

### Endpoint

```
POST /query
Content-Type: application/json
x-workload-identity: <caller-id>

Request body:
{
  "query": "string, 1..4096 bytes",
  "namespaces": ["..."],     // optional; subset of authorized
  "top_k": 5,                // 1..20, default 5
  "filters": {               // optional
    "severity": "...",       // allowed key
    "env": "...",            // allowed key
    "subject_id": "...",     // allowed key
    "trace_id": "..."        // allowed key
  }
}

Response (200):
{
  "results": [
    {
      "id": "uuid",
      "score": 0.83,
      "source": "checkout-svc",
      "namespace": "checkout",
      "ts": 1714435200.0,
      "content_hash": "a9f3c2e1b4d5f678",
      "request_id": "uuid",
      "client_ip": "10.0.1.42",
      "user_agent": "tilth/0.1.0",
      "content": "<retrieved_document source=\"checkout-svc\" ts=\"1714435200.0\">\n...\n</retrieved_document>"
    }
  ]
}

Errors:
  401 — missing/unknown caller identity
  403 — caller requested namespaces they're not authorized for
  400 — invalid body (size, schema, disallowed filter key)
  429 — rate limited
```

### Schema

```
GET /schema
{
  "namespaces": ["checkout", "support", "billing"],
  "record_fields": {
    "text": "string — the record content",
    "source": "string — who wrote it (gateway-set)",
    "namespace": "string — logical partition",
    "ts": "float — unix timestamp (gateway-set)",
    "content_hash": "string — sha256 prefix of scrubbed text (gateway-set)",
    "request_id": "string — per-request UUID (gateway-set)",
    "client_ip": "string — caller IP (gateway-set)",
    "user_agent": "string — caller user-agent (gateway-set)"
  },
  "metadata_fields": {
    "severity": "info | warn | error",
    "env": "prod | staging | dev",
    "trace_id": "string — correlation ID",
    "subject_id": "string — entity ID (deal, customer, etc.)",
    "ttl_days": "integer — retention hint"
  },
  "filterable_keys": ["severity", "env", "subject_id", "trace_id"],
  "embed_model": "text-embedding-3-small"
}
```

Generated from the gateway's own validation code and read-policy. The
`namespaces` list reflects the caller's authorized namespaces (derived
from the `x-workload-identity` header and the read-policy). No auth
required — the schema is not sensitive, but namespace visibility is
scoped to the caller.

### Health and metrics

```
GET /healthz       → { "ok": true }
GET /metrics       → prometheus format
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `QDRANT_URL` | required | |
| `QDRANT_API_KEY` | required | (separate creds from ingest gateway) |
| `EMBED_PROVIDER` | `openai` | Embedding provider: `openai` or `azure`. When `azure`, requires `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION`. When `openai`, requires `OPENAI_API_KEY`. |
| `COLLECTION_NAME` | `tilth` | Must match ingest gateway. |
| `EMBED_MODEL` | `text-embedding-3-small` | Must match ingest gateway. |
| `MAX_TOP_K` | `20` | Hard cap on result count. |
| `MAX_QUERY_BYTES` | `4096` | |
| `READ_POLICY_PATH` | `/etc/tilth/read-policy.yaml` | |
| `STORES_CONFIG_PATH` | `/etc/tilth/stores.yaml` | YAML file mapping namespaces to Qdrant collections via store_router. When caller's namespaces span multiple collections, the gateway fans out queries across stores. |

### Read policy file format

```yaml
# read-policy.yaml — separate from write-policy.yaml
support-agent:
  - support
  - billing
ops-copilot:
  - checkout
  - support
  - billing
dev-stdio-user:
  - checkout
  - support
  - billing
```

Note: `dev-stdio-user` is included for local dev with the MCP server
in stdio mode.

### Allowed filter keys

`severity`, `env`, `subject_id`, `trace_id`. This is a superset of what
the MCP server exposes — the MCP server uses a subset for simplicity,
but the gateway supports all four for programmatic consumers.

## Behavior

### Per-request handling

1. Read `x-workload-identity`. Missing → 401. Unknown to read policy → 401.
2. Validate body against pydantic schema. Failure → 400.
3. Compute effective namespaces:
   - If `body.namespaces is None`: use all permitted for this caller.
   - Else: requested = set(body.namespaces); denied = requested - permitted.
     If denied is non-empty → 403 with `{"denied": sorted(denied)}`.
     Else: effective = sorted(requested).
4. Validate filter keys against allowlist (`severity`, `env`, `subject_id`,
   `trace_id`). Disallowed key → 400.
5. Embed `body.query` via OpenAI.
6. Build a Qdrant `Filter`:
   - `must`: `namespace IN effective`.
   - `must`: each filter key/value as `MatchValue`.
7. Query Qdrant via `qdrant_client.query_points()`: `collection_name`,
   `query=query_vector`, `query_filter`, `limit=body.top_k`,
   `with_payload=True`.
8. For each hit, build a result dict:
   ```python
   # Escape closing tags in text to prevent injection
   safe_text = hit.payload["text"].replace(
       "</retrieved_document>", "</retrieved_document_>"
   )

   {
     "id": str(hit.id),
     "score": hit.score,
     "source": hit.payload["source"],
     "namespace": hit.payload["namespace"],
     "ts": hit.payload["ts"],
     "content_hash": hit.payload.get("content_hash"),
     "request_id": hit.payload.get("request_id"),
     "client_ip": hit.payload.get("client_ip"),
     "user_agent": hit.payload.get("user_agent"),
     "chunk_group_id": hit.payload.get("chunk_group_id"),
     "chunk_index": hit.payload.get("chunk_index"),
     "chunk_total": hit.payload.get("chunk_total"),
     "content": (
       f'<retrieved_document source="{hit.payload["source"]}" '
       f'ts="{hit.payload["ts"]}">\n'
       f'{safe_text}\n'
       f'</retrieved_document>'
     ),
   }
   ```
9. Audit log: emit a structured JSON log line at INFO level to stdout:
   ```json
   {
     "event": "query",
     "ts": 1714435200.0,
     "caller": "...",
     "query_hash": "first 16 hex of sha256(query)",
     "namespaces": ["..."],
     "filters": {"..."},
     "n_results": 5
   }
   ```
   Do NOT log the raw query or raw results — both may be sensitive.
10. Return 200 with `{"results": [...]}`.

### Rate limiting

Per-caller token bucket: 30 requests per second sustained, 60 burst.
Reads are tighter than writes because reads are the bigger exfil risk.
On exceeded → 429.

Implemented in `tilth_server._shared.rate_limit`, shared with the
ingest gateway.

### Startup / shutdown

Same shape as ingest gateway. Load read policy at startup; fail to start
if missing or invalid. Verify Qdrant collection's stored embedding model
matches `EMBED_MODEL`; refuse to start on mismatch.

### Content escaping

The `<retrieved_document>` tags use the stored `source` and `ts` values.
Both are gateway-set on write, so they're trusted.

If `text` contains literal `</retrieved_document>` strings, that's a
potential injection vector. Replace any occurrences with
`</retrieved_document_>` before wrapping. Document this in code comments.

## Acceptance criteria

- [ ] `docker build` succeeds.
- [ ] `mypy --strict` passes.
- [ ] `ruff check` passes.
- [ ] `pytest` passes with >80% coverage.
- [ ] A test asserts an unknown caller → 401.
- [ ] A test asserts a caller requesting an unauthorized namespace → 403
      with the denied set in the body.
- [ ] A test asserts that omitting `namespaces` returns results from all
      authorized namespaces and *only* those.
- [ ] A test asserts that a poisoned record containing
      `</retrieved_document>` in `text` has the closing tag escaped in the
      response.
- [ ] A test asserts disallowed filter keys → 400.
- [ ] A test asserts `top_k > 20` → 400.
- [ ] A test asserts `trace_id` can be used as a filter key.
- [ ] A test asserts a structured JSON audit log line is emitted to stdout
      per request, with `query_hash` (not the raw query) and the resolved
      namespaces.
- [ ] A test asserts `content_hash` is included in each result.
- [ ] An integration test against a Qdrant with seeded data asserts that
      the namespace filter is actually applied (e.g., a record in
      `billing` is not returned for a caller restricted to `support`,
      even when it's the most semantically similar match).
- [ ] An integration test asserts every result has a `<retrieved_document>`
      wrapper with `source` and `ts` attributes.
- [ ] `GET /schema` returns the data model with namespaces scoped to the
      caller's read-policy permissions.
- [ ] A test asserts `/schema` includes `record_fields`, `metadata_fields`,
      `filterable_keys`, and `embed_model`.
- [ ] A test asserts `/schema` namespaces differ per caller identity.

## Out of scope

- Reranking. Vector search results returned as-is.
- Hybrid search (BM25 + dense). Vector only for v1.
- Pagination. `top_k` cap is the answer for v1.
- Embedding cache. Each query is a fresh embedding call.
- Result caching across callers. Not safe — different callers see different
  namespaces.
- The `delete_by_subject` admin endpoint. Post-v1.
- File-based audit log. Structured logging to stdout is sufficient.

## Notes

The query hash is 16 hex chars of sha256 — short enough to grep, long
enough to deduplicate, not reversible. Don't shorten further.

The 403 response includes the denied namespace names. This is a deliberate
trade-off: it helps legitimate callers debug misconfiguration at the cost
of revealing namespace existence to attackers. Since namespace names are
not secret (they're in the write/read policy files and documentation), this
is acceptable.

`reference/sketch_query_gateway.py` shows the basic structure. **Known
divergences from this spec:** audit log uses `log.info` instead of structured
JSON, missing closing-tag escape, filter validation not in pydantic model,
uses module-level globals instead of app state, missing `trace_id` in filter
allowlist, missing `content_hash` in results.
