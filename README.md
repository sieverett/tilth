# tilth

Semantic memory for services. Fire-and-forget writes, vector search reads,
namespace-scoped access control.

Drop `tilth` into any service. Send text. Agents and tools retrieve it by
meaning. You don't manage credentials, embeddings, or vector stores.

```python
import tilth

tilth.send("Stripe returned card_declined for user 42",
           namespace="checkout", severity="warn")
```

---

## What this is for

Capturing events, decisions, customer interactions, incident notes, and other
semi-structured text that an agent might later retrieve by meaning rather
than by keyword. Think of it as semantic logging: the same shape as
`logger.info(...)`, but the destination is searchable by intent.

It is **not** a replacement for:

- **Application logs.** Keep using your normal logger for debugging, stack
  traces, and high-volume telemetry.
- **Metrics.** Numbers belong in your metrics system.
- **Primary data stores.** This is a derived, lossy, eventually-consistent
  index. Never rely on it as a system of record.

---

## Packages

Tilth ships as three independently installable PyPI packages:

| Package | Install | Purpose |
|---|---|---|
| `tilth` | `pip install tilth` | Client library. Fire-and-forget `tilth.send()`. |
| `tilth-server` | `pip install tilth-server` | Ingest + query gateways. |
| `tilth-mcp` | `pip install tilth-mcp` | MCP server for AI agents. |

Most services only need `tilth`. The server and MCP packages are for
operators running the infrastructure.

---

## Quick start

### Writing (any service)

```bash
pip install tilth
```

Set two environment variables:

```bash
TILTH_GATEWAY_URL=https://your-tilth-ingest-host
TILTH_IDENTITY=your-service-name
```

```python
import tilth

tilth.send("Customer requested refund for order #8821, cited shipping delay",
           namespace="support",
           severity="info",
           subject_id="cust_8821")
```

`send()` is fire-and-forget. It returns immediately, queues the record in the
background, and never raises into your code.

### Reading (agents and tools)

Reads go through the query gateway or the MCP server. There is intentionally
no read API in the client library. See [READING.md](./READING.md).

### Running the stack locally

```bash
git clone https://github.com/sieverett/tilth.git
cd tilth
make install
make up        # starts Qdrant + gateways via docker-compose
make e2e       # runs end-to-end tests
```

---

## Usage

### `tilth.send(text, *, namespace, **metadata)`

- `text` (str, required) — the content. Up to 32 KB.
- `namespace` (str, required) — which namespace to write to. Your service is
  authorized for a fixed set; writing outside it is silently dropped.
- `**metadata` — optional structured fields. Allowed keys: `env`, `severity`,
  `trace_id`, `subject_id`, `ttl_days`. Other keys cause a drop.

### `tilth.asend(text, *, namespace, **metadata)`

Async wrapper. Equivalent to `tilth.send()` — the queue submission is fast and
there's nothing to actually await. Exists so it composes with `asyncio.gather`.

### `VectorHandler(namespace, *, extra_metadata=None)`

`logging.Handler` subclass. `emit()` calls `tilth.send()`. Use sparingly —
most log lines are noise for semantic search.

```python
import logging
import tilth

handler = tilth.VectorHandler(namespace="checkout")
handler.setLevel(logging.WARNING)
logging.getLogger().addHandler(handler)
```

### Testing

```python
from tilth.testing import recording

def test_refund_logs_to_memory():
    with recording() as records:
        process_refund(order_id=8821)
    assert any("refund" in r.text for r in records)
    assert all(r.namespace == "support" for r in records)
```

`recording()` replaces the queue with an in-memory list. No network, no auth,
deterministic.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `TILTH_GATEWAY_URL` | *(required)* | Where to POST records. |
| `TILTH_IDENTITY` | unset | Workload identity sent as `x-workload-identity`. |
| `TILTH_QUEUE_SIZE` | `10000` | Max in-memory buffer before drop. |
| `TILTH_TIMEOUT_S` | `5.0` | Per-request HTTP timeout to the gateway. |
| `TILTH_DISABLE` | unset | Set to `1` to no-op all `tilth.send()` calls. |

---

## Failure modes

This library fails quietly so that a memory-store outage never becomes a
service outage:

- **Gateway unreachable** — records dropped, `tilth_dropped_total` incremented.
- **Queue full** — records dropped, same metric.
- **Process exit** — best-effort flush via `atexit` (2-second timeout).

If you need guaranteed delivery, you're using the wrong tool.

---

## Metrics

- `tilth_sent_total{namespace}` — accepted into the queue
- `tilth_dropped_total{reason}` — `queue_full` | `gateway_error` | `disabled` | `invalid`
- `tilth_queue_depth` — current buffer occupancy
- `tilth_flush_latency_seconds` — time from queue to gateway-accepted

---

## Architecture

See [architecture.md](./docs/architecture.md) for the full system design.

```
services ──tilth.send()──▶ ingest gateway ──▶ Qdrant ◀── query gateway ◀── MCP server ◀── agents
```

Three services, one vector store, one client library. Credentials don't sprawl.
Policy changes don't require redeploying 200 services. Readers and writers are
decoupled.

---

## License

MIT. See [LICENSE](./LICENSE).
