"""Tests for shared policy module."""

import os
import tempfile

import pytest
from tilth_server._shared.policy import load_policy


class TestLoadPolicy:
    def test_load_valid_yaml(self) -> None:
        content = "checkout-svc:\n  - checkout\nsupport-bot:\n  - support\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(content)
            f.flush()
            policy = load_policy(f.name)

        os.unlink(f.name)
        assert policy == {
            "checkout-svc": {"checkout"},
            "support-bot": {"support"},
        }

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_policy("/nonexistent/path/policy.yaml")

    def test_caller_lookup(self) -> None:
        content = "svc-a:\n  - ns1\n  - ns2\nsvc-b:\n  - ns3\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(content)
            f.flush()
            policy = load_policy(f.name)

        os.unlink(f.name)
        assert policy["svc-a"] == {"ns1", "ns2"}
        assert "unknown" not in policy

    def test_multi_namespace_caller(self) -> None:
        content = "ops-shared:\n  - checkout\n  - support\n  - billing\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(content)
            f.flush()
            policy = load_policy(f.name)

        os.unlink(f.name)
        assert policy["ops-shared"] == {"checkout", "support", "billing"}
