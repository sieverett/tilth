"""Reference sketch — NOT the final implementation.

Shows the basic queue/worker/atexit pattern. Missing pieces the spec requires:
- Validation of text size, namespace, metadata keys
- Metrics integration
- VectorHandler logging adapter
- recording() test helper
- asend() async wrapper
- Proper shutdown sentinel handling
- Clear separation of public/private modules

Use this for the SHAPE of the worker thread, not as a starting point to copy.
"""

import os, queue, threading, httpx, atexit

_GATEWAY = os.environ.get("INGEST_GATEWAY_URL", "")
_q: queue.Queue = queue.Queue(maxsize=10_000)


def _worker():
    with httpx.Client(timeout=5.0) as client:
        while True:
            item = _q.get()
            if item is None:
                return
            try:
                client.post(f"{_GATEWAY}/ingest", json=item)
            except Exception:
                pass  # never raise into the caller
            finally:
                _q.task_done()


threading.Thread(target=_worker, daemon=True).start()
atexit.register(lambda: _q.put(None))


def send(text: str, **metadata):
    try:
        _q.put_nowait({"text": text, "metadata": metadata})
    except queue.Full:
        pass  # drop on overflow — never block the caller
