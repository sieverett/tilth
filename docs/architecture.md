# Architecture

## The shape

```
┌──────────────┐         ┌──────────────────┐         ┌─────────────┐
│  service A   │─send()─▶│ ingest gateway   │─writes─▶│   Qdrant    │
│  service B   │         │  (tilth-server)  │         │ (vector DB) │
│  service C   │         └──────────────────┘         └─────────────┘
└──────────────┘                                              ▲
                                                              │ reads
                         ┌──────────────────┐                 │
                         │  query gateway   │─────────────────┘
                         │  (tilth-server)  │
                         └──────────────────┘
                                  ▲
                                  │ HTTP
                         ┌──────────────────┐
                         │   MCP server     │◀─── agents (Claude, etc.)
                         │   (tilth-mcp)    │
                         └──────────────────┘
```

Three services, one vector store, one client library. All in one repo,
shipped as three PyPI packages.

## Components

### Client library (`tilth`)

A single-import Python package services use to send text. Fire-and-forget,
non-blocking, credential-free. Buffered in-process; a background thread
POSTs to the ingest gateway.

**Key property:** importing it has minimal side effects, calling `send()`
never raises into caller code, and a gateway outage cannot take down a
calling service.

### Ingest gateway (`tilth-server`, ingest)

Receives writes from the client library. Authenticates the caller, scrubs
PII, validates the namespace and metadata, chunks text >32KB at sentence
boundaries, batches embeddings, and upserts to Qdrant. Supports multiple
embedding providers via `EMBED_PROVIDER` (OpenAI, Azure).

**Key property:** the gateway is the *only* service that holds a Qdrant
write credential. The library has no credentials. Rotating Qdrant access
touches one service.

### Query gateway (`tilth-server`, query)

Receives reads from MCP server, dashboards, and other tools. Enforces
per-caller namespace ACLs server-side, caps result sizes, audits queries
via structured logging, and wraps results in injection-resistant framing.
Supports multiple embedding providers via `EMBED_PROVIDER` (OpenAI, Azure).

In prod mode (`TILTH_AUTH_MODE=prod`), caller identity is derived from a
validated JWT (`Authorization: Bearer` header) rather than the
`x-workload-identity` header. Mutation endpoints (`DELETE /records/{id}`,
`PATCH /records/{id}`) require the `admin` role in the JWT claims.

**Key property:** the namespace filter is appended to every query
unconditionally based on caller identity. A reader cannot bypass it by
passing parameters.

### MCP server (`tilth-mcp`)

Exposes `search_tilth` to MCP-aware agents. Translates MCP tool calls
into HTTP requests against the query gateway. Forwards the verified caller
identity from its transport-layer auth. The MCP server is read/write
only — `delete_tilth_record` and `update_tilth_record` tools have been
removed. Agents that need to delete or update records must go through the
gateway API with admin credentials.

**Key property:** the MCP server is a thin proxy. All policy lives in the
query gateway. Adding new front doors doesn't require duplicating policy.

### Reasoning agent (`tilth-agent`)

A standalone Python package that runs a Claude/GPT tool-use loop. Reads
from tilth via the query gateway, writes findings back via the ingest
gateway. Maintains persistent memory across runs via a local file. Uses
the tilth-server model abstraction (`_shared/models.py`) for LLM provider
selection.

## Invariants

These must hold across all components. If you find yourself building
something that breaks one, stop and re-read the threat model.

1. **Caller identity is set server-side, never trusted from the client.**
   In dev mode, the library sends `x-workload-identity` from
   `TILTH_IDENTITY`, and the gateway treats it as a claim validated against
   the policy table. In prod mode, identity is derived from a validated JWT
   subject claim. The MCP server forwards the verified transport identity,
   not agent arguments.

2. **Namespace ACLs are enforced server-side.** Both gateways have a policy
   table mapping caller to permitted namespaces. Requests are intersected
   with permissions. Empty intersections return 403.

3. **Read and write permissions are independent.** A service can write to
   `checkout` without being able to read it back. Most services are
   write-only.

4. **The library never raises into caller code.** Validation failures,
   queue overflow, gateway errors — all become metric increments and
   debug logs. Callers see no exceptions from `send()`.

5. **Retrieved content is wrapped in `<retrieved_document>` tags with
   provenance.** Every response from the query gateway and MCP server
   carries this wrapping. Consumers do not strip it before passing to LLMs.

6. **Metadata keys are allowlisted.** Both client-side and server-side
   validate against a fixed set: `env`, `severity`, `trace_id`,
   `subject_id`, `ttl_days`. Unknown keys are rejected.

7. **PII scrubbing runs on every write.** The ingest gateway runs Presidio
   over `text` before writing. False negatives are expected; the scrubber
   is a safety net, not a license to log PII.

## Data model

Each record stored in Qdrant has:

| Field | Source | Purpose |
|---|---|---|
| `id` | gateway-assigned UUID | unique key |
| `vector` | embedding of `text` | similarity search |
| `text` | client (after scrubbing) | the content |
| `source` | gateway (from caller identity) | who wrote it |
| `namespace` | client (validated against policy) | logical partition |
| `ts` | gateway | unix timestamp of write |
| `content_hash` | gateway (sha256 of scrubbed text, first 16 hex) | integrity verification |
| `request_id` | gateway-assigned UUID | per-request tracing |
| `client_ip` | gateway (from request) | entity fingerprinting |
| `user_agent` | gateway (from request header) | client version tracking |
| `severity` | client metadata | optional: info/warn/error |
| `env` | client metadata | optional: prod/staging/dev |
| `trace_id` | client metadata | optional: correlation |
| `subject_id` | client metadata | optional: customer/user/etc. |
| `ttl_days` | client metadata | optional: retention hint |
| `chunk_group_id` | gateway (when chunked) | linking chunks of split text |
| `chunk_index` | gateway (when chunked) | linking chunks of split text |
| `chunk_total` | gateway (when chunked) | linking chunks of split text |

`source`, `ts`, `content_hash`, `request_id`, `client_ip`, and `user_agent`
are immutable and gateway-set. Client-
supplied fields are validated server-side regardless of whether the client
also validates.

### Embedding model tracking

The embedding model name is stored in the Qdrant collection metadata at
creation time. Both gateways read it on startup and refuse to start if it
doesn't match their configured `EMBED_MODEL`. This prevents silent search
degradation from model drift between ingest and query.

## Why this shape

**Credentials don't sprawl.** Every importer of the client library is a
potential credential leak. By making the library credential-free and
putting auth at the gateway, we centralize the surface.

**Policy can change without redeploying everything.** Adding a namespace,
tightening a filter, or rotating a credential is a gateway change. The
200 services that import the library don't notice.

**The reader and writer are decoupled.** Most services write but don't
read. Splitting into two gateways with independent policy tables makes
that natural — read access is granted only where genuinely needed.

## What's deliberately not here (v1)

- ~~A real auth integration. v1 trusts a transport header; production needs
  mesh mTLS or OAuth.~~ JWT auth is now available via `TILTH_AUTH_MODE=prod`.
- A reranker. Vector search alone returns acceptable but not great results.
- TTL enforcement. Records live forever until explicitly deleted.
- A `delete_by_subject` admin endpoint for right-to-erasure.
- A web UI for humans.
- Multi-region or HA deployment.
- Cryptographic signing of records (content hash is a stepping stone).

These are noted in the relevant specs as out-of-scope. Don't build them.
