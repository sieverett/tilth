# Spec 01: Client library (`tilth`)

## Scope

A Python package services import to send text to the shared memory store.
Single-import, fire-and-forget, non-blocking, no vector store credentials.

This is what every team will install with `pip install tilth`. It's the
most-touched code in the whole system; treat it accordingly.

## Interface

### Public API

```python
from tilth import send, asend, VectorHandler

send(text: str, *, namespace: str, **metadata) -> None
async asend(text: str, *, namespace: str, **metadata) -> None
VectorHandler(namespace: str, *, extra_metadata: dict | None = None)  # logging.Handler
```

### Test API (public, in a submodule)

```python
from tilth.testing import recording

with recording() as records:
    send("...", namespace="checkout")
# records is a list of Recorded(text, namespace, metadata)
```

### Configuration (env vars only)

| Variable | Default | Purpose |
|---|---|---|
| `TILTH_GATEWAY_URL` | required | Base URL of the ingest gateway. |
| `TILTH_IDENTITY` | unset | Workload identity sent as `x-workload-identity` header. |
| `TILTH_QUEUE_SIZE` | `10000` | Max in-memory buffer before drop. |
| `TILTH_TIMEOUT_S` | `5.0` | HTTP timeout per request to gateway. |
| `TILTH_DISABLE` | unset | If `1`, all sends become no-ops. |

### Allowed metadata keys

Hardcoded set: `env`, `severity`, `trace_id`, `subject_id`, `ttl_days`.
Other keys cause the record to be dropped with a debug log and a metric
increment. This matches the gateway's allowlist exactly.

### Constraints

- `text` max 256 KB after UTF-8 encoding.
- Oversized text is dropped with a WARNING log.
- Empty `text` or empty `namespace` → drop, increment `tilth_dropped_total{reason="invalid"}`.
- Anything outside the allowed metadata keys → drop, same reason.

## Behavior

### `send(text, *, namespace, **metadata)`

1. If `TILTH_DISABLE=1`, increment `tilth_dropped_total{reason="disabled"}` and return.
2. Validate `text`, `namespace`, `metadata`. On failure, increment
   `tilth_dropped_total{reason="invalid"}` and return.
3. Lazily start the background worker thread on first call.
4. Build a payload `{"text": text, "namespace": namespace, "metadata": metadata}`.
5. Try `queue.put_nowait((monotonic_time, payload))`.
   - On success: increment `tilth_sent_total{namespace=namespace}`, update `tilth_queue_depth`.
   - On `queue.Full`: increment `tilth_dropped_total{reason="queue_full"}`. Don't block.
6. Return.

**Never raises.** Wrap the whole function body in a try/except with a
fallback that increments `tilth_dropped_total{reason="invalid"}` for unexpected errors.

### Background worker

A single daemon thread, started lazily on first `send()` call. Behavior:

1. `httpx.Client` with `TILTH_TIMEOUT_S` timeout.
2. Loop forever:
   - Pull `(t0, payload)` from queue (blocking).
   - If item is the shutdown sentinel, return.
   - POST to `f"{TILTH_GATEWAY_URL}/ingest"` with the payload as JSON.
   - Set `x-workload-identity` header from `TILTH_IDENTITY` if configured.
   - On success (2xx): observe `tilth_flush_latency_seconds` with `monotonic() - t0`.
   - On 4xx/5xx or `httpx.RequestError`: increment `tilth_dropped_total{reason="gateway_error"}`,
     log at debug level. Do not retry — drops are acceptable, blocking the worker is not.
3. Catch all exceptions in the loop; log at debug; continue. The worker thread must never die.

### Shutdown

Register an `atexit` handler that:

1. Pushes a shutdown sentinel onto the queue.
2. Calls `queue.join()` with a 2-second timeout.
3. Returns regardless. Never blocks the process indefinitely.

### `asend(text, *, namespace, **metadata)`

Thin async wrapper. Calls `send()` synchronously — the queue submission
is fast (microseconds) and there's nothing to actually await. Exists so it
composes with `asyncio.gather`.

### `VectorHandler`

Subclass of `logging.Handler`. `emit(record)` formats the record and calls
`send()` with `namespace=self._namespace`, `severity=record.levelname.lower()`,
plus any `extra_metadata`. Must follow the stdlib contract — never raise from
`emit`; on error call `self.handleError(record)`.

### `recording()` test helper

Context manager that monkey-patches `send` (at both `tilth.send` and
`tilth._client.send`) with a function that appends to an in-memory list.
Yields the list. Restores on exit. The worker thread is never started.

## Acceptance criteria

- [ ] `pip install -e packages/tilth` succeeds.
- [ ] `from tilth import send` works without setting any env vars
      (deferred validation; warning logged on first call).
- [ ] `mypy --strict packages/tilth/src` passes.
- [ ] `ruff check packages/tilth` passes.
- [ ] `pytest packages/tilth/tests` passes with >80% coverage.
- [ ] A test asserts `send()` returns `None` when the gateway URL is invalid
      (no exception raised).
- [ ] A test asserts that sending 20,000 records with `TILTH_QUEUE_SIZE=100` drops
      ~19,900 of them with `tilth_dropped_total{reason="queue_full"}` incremented.
- [ ] A test asserts disallowed metadata keys cause a drop with
      `reason="invalid"`.
- [ ] A test asserts text >256KB is dropped with `reason="invalid"`.
- [ ] A test asserts `TILTH_DISABLE=1` causes all sends to drop with
      `reason="disabled"` and the worker thread is never started.
- [ ] A test asserts `recording()` captures sends in-process without
      starting the worker.
- [ ] A test asserts `VectorHandler` doesn't raise when `send()` would drop.
- [ ] An integration test against a fake HTTP server (e.g., `respx` or a
      local `aiohttp` test server) asserts that `send()` results in a POST
      to `/ingest` with the expected body within 1 second.
- [ ] An integration test asserts the `x-workload-identity` header is set
      from `TILTH_IDENTITY` on every POST.

## Out of scope

- Retry logic. Drop on first failure.
- Any read functionality. This package is write-only.
- Persistence across process restarts. The queue is in-memory only.
- Compression. Records are small; the gateway is local.
- Custom embedding or any business logic. The library is dumb.

## Notes

The README in the repo root is the user-facing doc for this library. The
library should match that contract exactly. If you find a mismatch, the
README wins — update the spec or the code, not the README.

The `reference/sketch_client.py` file shows a working sketch of the
queue/worker mechanics. **Do not copy it verbatim** — it has known
divergences from this spec (see DECISIONS.md for the full list). Use it
for the shape of the worker thread only.
