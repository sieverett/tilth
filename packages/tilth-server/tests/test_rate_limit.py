"""Tests for shared rate limiting module."""

import time

from tilth_server._shared.rate_limit import TokenBucket


class TestTokenBucket:
    def test_under_limit_passes(self) -> None:
        bucket = TokenBucket(rate=10.0, burst=20)
        for _ in range(10):
            assert bucket.consume("caller-a") is True

    def test_over_limit_rejects(self) -> None:
        bucket = TokenBucket(rate=1.0, burst=2)
        assert bucket.consume("caller-a") is True
        assert bucket.consume("caller-a") is True
        assert bucket.consume("caller-a") is False

    def test_separate_callers_independent(self) -> None:
        bucket = TokenBucket(rate=1.0, burst=1)
        assert bucket.consume("caller-a") is True
        assert bucket.consume("caller-b") is True
        assert bucket.consume("caller-a") is False
        assert bucket.consume("caller-b") is False

    def test_tokens_refill_over_time(self) -> None:
        bucket = TokenBucket(rate=100.0, burst=1)
        assert bucket.consume("caller-a") is True
        assert bucket.consume("caller-a") is False
        # Manually advance the bucket's last refill time
        bucket._buckets["caller-a"] = (1.0, time.monotonic() - 0.1)
        assert bucket.consume("caller-a") is True
