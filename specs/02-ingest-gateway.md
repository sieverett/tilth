# Spec 02: Ingest gateway (`tilth-server`, ingest)

## Scope

A FastAPI service that receives writes from the client library, scrubs PII,
batches embeddings, and upserts to Qdrant. The only service that holds a
Qdrant write credential. Part of the `tilth-server` package, deployed as
its own container.

## Interface

### Endpoint

```
POST /ingest
Content-Type: application/json
x-workload-identity: <caller-id>    (header, set by client / mesh / proxy)

Request body:
{
  "text": "string, 1..32768 bytes",
  "namespace": "string",
  "metadata": {
    "env": "...",        // optional
    "severity": "...",   // optional
    "trace_id": "...",   // optional
    "subject_id": "...", // optional
    "ttl_days": 30       // optional, int
  }
}

Response (202):
{ "status": "accepted" }

Errors:
  401 — missing/unknown caller identity
  403 — caller not authorized for namespace
  400 — invalid body (size, schema, disallowed metadata key)
  429 — rate limited
  503 — batch writer queue full (back off)
```

### Health

```
GET /healthz
{ "ok": true, "queue_depth": <int> }
```

### Metrics

```
GET /metrics
(prometheus format)
```

### Configuration (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `QDRANT_URL` | required | Qdrant base URL. |
| `QDRANT_API_KEY` | required | Qdrant API key. |
| `OPENAI_API_KEY` | required | For embedding API. |
| `COLLECTION_NAME` | `tilth` | Qdrant collection. |
| `EMBED_MODEL` | `text-embedding-3-small` | Must match query gateway. |
| `EMBED_DIM` | `1536` | Vector dimension. |
| `BATCH_SIZE` | `64` | Max records per embedding call. |
| `BATCH_WINDOW_MS` | `200` | Max wait before flushing partial batch. |
| `BATCH_QUEUE_MAX` | `10000` | Max items in the batch writer's internal queue. |
| `MAX_TEXT_BYTES` | `32768` | Same limit as client. |
| `WRITE_POLICY_PATH` | `/etc/tilth/write-policy.yaml` | YAML file mapping caller→namespaces. |

### Write policy file format

```yaml
# write-policy.yaml
checkout-svc:
  - checkout
support-bot:
  - support
billing-job:
  - billing
ops-shared:
  - checkout
  - support
  - billing
```

Loaded at startup. If the file is missing, the service refuses to start
with a clear error message. To reload policy, restart the service.

## Behavior

### Per-request handling

1. Read `x-workload-identity` header. If missing or empty → 401.
2. Look up caller in the write policy. If absent → 401 (treat unknown
   callers as unauthenticated, not unauthorized — fewer signals to attackers).
3. Validate body against pydantic schema (text length, namespace non-empty,
   metadata keys in allowlist). Schema failures → 400 with field path.
4. Check `body.namespace` ∈ allowed namespaces for this caller. Else → 403.
5. Run Presidio scrubber on `body.text`. Replace findings with type tokens
   (e.g., `<EMAIL_ADDRESS>`).
6. Compute `content_hash`: first 16 hex characters of `sha256(scrubbed_text)`.
7. Build the payload (see data model in architecture doc):
   ```python
   {
     "text": scrubbed_text,
     "source": caller,           # from header, never from body
     "namespace": body.namespace,
     "ts": time.time(),
     "content_hash": content_hash,
     **body.metadata,
   }
   ```
8. Submit to the batch writer's queue.
   - If queue is full → return 503 with `{"error": "service overloaded, retry later"}`.
9. Return 202.

### Batch writer

A single async task running for the lifetime of the service. Loop:

1. Pull one item from the queue (blocking).
2. Start a deadline at `now + BATCH_WINDOW_MS`.
3. Pull more items (non-blocking with timeout) until either:
   - `BATCH_SIZE` items collected, or
   - deadline reached.
4. Call OpenAI embeddings on the batch of texts (one API call).
5. Build `PointStruct(id=uuid, vector=embedding, payload=item.payload)`.
6. `qdrant.upsert(collection_name, points)` (one API call).
7. Observe metrics: batch size, embed latency, upsert latency.
8. On any exception in steps 4–6: log, increment `flush_failed_total`,
   continue. Records in the failed batch are lost. (Acceptable for v1;
   logged so it's visible.)

The batch writer's internal queue is bounded at `BATCH_QUEUE_MAX` items.
This prevents unbounded memory growth if Qdrant is slow or down.

### Startup

1. Load and validate the write policy file. Refuse to start on errors.
2. Connect to Qdrant. Create the collection if it doesn't exist
   (idempotent). Store embedding model name in collection metadata.
   If collection exists, verify the stored model name matches
   `EMBED_MODEL`. Refuse to start on mismatch.
3. Initialize Presidio analyzer and anonymizer engines. Load spaCy model.
   Refuse to start if model loading fails.
4. Start the batch writer task.
5. Bind the FastAPI app.

### Shutdown

1. Stop accepting new requests.
2. Wait up to 5 seconds for the batch writer to drain its queue.
3. Close the Qdrant client and HTTP clients cleanly.

### Rate limiting

Per-caller token bucket: 100 requests per second sustained, 200 burst.
On exceeded → 429. In-memory implementation; multi-replica distributed
limiting is post-v1.

Implemented in `tilth_server._shared.rate_limit` and shared with the
query gateway.

## Acceptance criteria

- [ ] `docker build` from `packages/tilth-server/Dockerfile` succeeds.
- [ ] `mypy --strict packages/tilth-server/src` passes.
- [ ] `ruff check packages/tilth-server` passes.
- [ ] `pytest packages/tilth-server/tests` passes with >80% coverage.
- [ ] A test asserts a missing `x-workload-identity` header → 401.
- [ ] A test asserts a caller writing outside their permitted namespaces → 403.
- [ ] A test asserts a request with `metadata={"foo": "bar"}` (disallowed key) → 400.
- [ ] A test asserts text >32KB → 400.
- [ ] A test asserts an email in `text` is replaced with a Presidio token
      before being passed to the batch writer.
- [ ] A test asserts the request body's `source` field, if any, is ignored —
      the stored `source` is always the verified caller identity.
- [ ] A test asserts `content_hash` is present in the stored payload and
      matches sha256 of the scrubbed text (first 16 hex).
- [ ] A test asserts that when the batch writer queue is full, the endpoint
      returns 503 (not 202).
- [ ] An integration test against a real Qdrant (via docker-compose) asserts
      that 100 records POSTed are all upserted within 5 seconds.
- [ ] An integration test asserts that 1000 concurrent POSTs result in
      fewer than 20 embedding API calls (verifying batching works).
- [ ] A test asserts that an OpenAI embedding API failure is logged and
      `flush_failed_total` increments, but the service keeps running.
- [ ] A test asserts that startup fails if the Qdrant collection has a
      different embedding model in its metadata.
- [ ] `GET /healthz` returns 200 with a queue depth.
- [ ] `GET /metrics` returns Prometheus-format metrics.

## Out of scope

- Real auth integration. Trust the `x-workload-identity` header.
- Multi-replica deployment. Single replica is fine for v1.
- Persistent queue (Redis, Kafka). In-process queue is fine for v1.
- TTL enforcement. Honor the `ttl_days` field by storing it; sweeper is post-v1.
- Right-to-erasure endpoint. Post-v1.
- SIGHUP-based policy reload. Restart to reload.
- Audit log of writes. Standard request logging is sufficient for v1.

## Notes

PII scrubbing uses Presidio with the following entities: `EMAIL_ADDRESS`,
`CREDIT_CARD`, `US_SSN`, `PHONE_NUMBER`, `IP_ADDRESS`, `IBAN_CODE`.
Language: `en`. spaCy model: `en_core_web_lg` (pin in Dockerfile).
Configure the analyzer once at startup in the lifespan handler; reuse for
all requests. Presidio is slow on first call; warm it during startup.

The `flush_failed_total` metric is the most important alarm in this service.
Any sustained nonzero rate means data is being lost. Page on it.

`reference/sketch_ingest_gateway.py` shows the basic structure. **Known
divergences from this spec:** queue-full returns 202 instead of 503,
Presidio initializes at module scope, policy is inline dict, no health/metrics
endpoints, no rate limiting, no content_hash, no bounded batch queue.
