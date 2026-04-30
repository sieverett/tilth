# Decisions

Non-obvious choices made during design and implementation. Reviewers read
this to understand *why* without re-deriving it.

---

## 2026-04-29 — Library renamed from org-memory to tilth
**Spec:** all
**Choice:** All packages, imports, env vars, metrics, and tool names use `tilth` naming.
**Why:** Open-source PyPI library needs a distinct, short name.
**Reversibility:** hard — public API, PyPI package names, env vars

## 2026-04-29 — Three PyPI packages: tilth, tilth-server, tilth-mcp
**Spec:** AGENTS.md "Repository layout"
**Choice:** Ship as three independently installable packages via uv workspaces with hatchling build backend. Both gateways live in `tilth-server` with shared internals in `tilth_server._shared`.
**Why:** Most consumers only need the client (`pip install tilth`). Bundling FastAPI, Presidio, and Qdrant into the client would be hostile. Two gateways in one package avoids duplicating shared auth/policy/rate-limiting code and a fourth `tilth-server-common` package.
**Reversibility:** medium — splitting tilth-server into two packages later is mechanical

## 2026-04-29 — TILTH_IDENTITY env var for workload identity
**Spec:** 01-client-library.md, 05-e2e.md
**Choice:** The client library reads `TILTH_IDENTITY` and sets `x-workload-identity` header on every POST. This resolves the e2e auth gap: in docker-compose there's no mesh, so the env var is the identity source.
**Why:** The gateway requires `x-workload-identity`. In production, a mesh sidecar can inject/override it. In dev/test, the env var is the only mechanism. Without this, no e2e test can authenticate.
**Reversibility:** easy — the header name and source can change without touching the public API

## 2026-04-29 — Cut SIGHUP policy reload
**Spec:** 02-ingest-gateway.md, 03-query-gateway.md
**Choice:** Policy files are loaded at startup only. Restart to reload.
**Why:** For a single-replica v1 service that restarts in seconds, hot-reload adds thread-safety complexity on the policy dict and signal handling for near-zero benefit.
**Reversibility:** easy — add SIGHUP handler later if multi-replica needs it

## 2026-04-29 — Audit log to stdout instead of JSONL file
**Spec:** 03-query-gateway.md
**Choice:** Query audit logs are structured JSON emitted to stdout at INFO level, not appended to a file at `AUDIT_LOG_PATH`.
**Why:** Docker captures stdout. File-based logging requires volume mounts, logrotate, and disk monitoring — all operational overhead for no functional benefit. Same fields, same structure, zero infrastructure.
**Reversibility:** easy — swap the logging handler

## 2026-04-29 — Added trace_id to query gateway filter allowlist
**Spec:** 03-query-gateway.md
**Choice:** `trace_id` is a valid filter key for queries, alongside `severity`, `env`, and `subject_id`.
**Why:** Storing data you can't query is dead weight. `trace_id` is stored on every record; operators need to pull all records for a specific trace during debugging.
**Reversibility:** easy — removing a filter key is backwards-compatible

## 2026-04-29 — MCP server exposes severity, env, and subject_id filters
**Spec:** 04-mcp-server.md
**Choice:** The MCP tool accepts `severity`, `env`, and `subject_id` as filter parameters (not just `severity`). `trace_id` is not exposed to agents — it's available via the gateway HTTP API for programmatic use.
**Why:** Agents need `env` (to scope to prod vs staging) and `subject_id` (to scope to a specific customer) for practical queries. Omitting them forces agents to retrieve and filter client-side, wasting tokens. `trace_id` is an operator concern, not an agent concern.
**Reversibility:** easy — adding/removing tool parameters

## 2026-04-29 — Embedding model name stored in Qdrant collection metadata
**Spec:** 02-ingest-gateway.md, 03-query-gateway.md
**Choice:** On collection creation, store the embedding model name in Qdrant collection metadata. Both gateways check it on startup and refuse to start on mismatch.
**Why:** If ingest and query deploy with different `EMBED_MODEL` values, search silently returns garbage. This is the cheapest possible guard against model drift.
**Reversibility:** easy

## 2026-04-29 — Bounded batch writer queue (10,000 items)
**Spec:** 02-ingest-gateway.md
**Choice:** The batch writer's internal queue is bounded at `BATCH_QUEUE_MAX` (default 10,000). When full, the endpoint returns 503.
**Why:** Without a bound, sustained load with a slow/down Qdrant causes unbounded memory growth. Explicit 503 gives clients a signal to back off.
**Reversibility:** easy — change the default

## 2026-04-29 — content_hash field on every stored record
**Spec:** 02-ingest-gateway.md, 03-query-gateway.md, 04-mcp-server.md
**Choice:** The ingest gateway computes `sha256(scrubbed_text)[:16]` and stores it as `content_hash`. The query gateway and MCP server include it in results.
**Why:** Provides application-layer tamper detection for stored records. Stepping stone toward cryptographic signing (HMAC, asymmetric) in a future version. Zero cost to compute, makes every future provenance enhancement easier.
**Reversibility:** easy — it's an additive field

## 2026-04-29 — Merged CHEATSHEET.md into AGENTS.md
**Spec:** AGENTS.md
**Choice:** Deleted CHEATSHEET.md. Moved the "common traps" and "seven invariants" sections into AGENTS.md. Removed duplicated "when stuck" and build-order content.
**Why:** CHEATSHEET.md was almost entirely redundant with AGENTS.md. Three copies of the invariants (architecture.md, CHEATSHEET.md, partially in threat-model.md) will drift. Two authoritative locations remain: architecture.md (with rationale) and AGENTS.md (quick reference).
**Reversibility:** easy

## 2026-04-29 — Rewrote READING.md for open-source audience
**Spec:** READING.md
**Choice:** Stripped internal org references (Slack channels, internal URLs, web UI). Reframed for self-hosted deployments. Removed "Path 3: Web UI" (out of scope for v1).
**Why:** As an OSS project, docs referencing `#memory-platform` Slack and `internal.docs.your-org` URLs are confusing and useless.
**Reversibility:** easy

---

## Blockers

<!-- If something contradicts the spec or can't be resolved, log it here. -->

*None yet.*
