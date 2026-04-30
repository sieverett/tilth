"""E2E test configuration."""

import os

# Set environment for the client library
os.environ.setdefault("TILTH_GATEWAY_URL", "http://localhost:8001")
os.environ.setdefault("TILTH_IDENTITY", "test-writer")
