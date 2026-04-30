"""Per-caller token bucket rate limiter."""

import threading
import time


class TokenBucket:
    """Thread-safe per-caller token bucket rate limiter.

    Args:
        rate: tokens per second (sustained rate).
        burst: maximum tokens (burst capacity).
    """

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._lock = threading.Lock()
        # {caller: (tokens, last_refill_time)}
        self._buckets: dict[str, tuple[float, float]] = {}

    def consume(self, caller: str) -> bool:
        """Try to consume one token for the given caller.

        Returns True if allowed, False if rate limited.
        """
        now = time.monotonic()
        with self._lock:
            if caller not in self._buckets:
                self._buckets[caller] = (self._burst - 1, now)
                return True

            tokens, last_refill = self._buckets[caller]
            elapsed = now - last_refill
            tokens = min(self._burst, tokens + elapsed * self._rate)
            last_refill = now

            if tokens >= 1.0:
                self._buckets[caller] = (tokens - 1, last_refill)
                return True
            else:
                self._buckets[caller] = (tokens, last_refill)
                return False
