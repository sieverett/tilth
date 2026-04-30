"""Load sales call transcripts into tilth memory.

Usage:
    python scripts/load_transcripts.py [--gateway-url URL] [--identity ID]

Reads all transcript markdown files from test-scenarios/sales-reasoning/transcripts/
and sends them to tilth via the client library.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

# Ensure the tilth package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "tilth" / "src"))


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from a markdown file."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    meta: dict[str, str] = {}
    for line in match.group(1).strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"')

    return meta, match.group(2).strip()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Load transcripts into tilth")
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("TILTH_GATEWAY_URL", "http://localhost:8001"),
    )
    parser.add_argument(
        "--identity",
        default=os.environ.get("TILTH_IDENTITY", "test-writer"),
    )
    parser.add_argument(
        "--transcripts-dir",
        default=str(
            Path(__file__).parent.parent
            / "test-scenarios"
            / "sales-reasoning"
            / "transcripts"
        ),
    )
    args = parser.parse_args()

    os.environ["TILTH_GATEWAY_URL"] = args.gateway_url
    os.environ["TILTH_IDENTITY"] = args.identity

    from tilth import send

    transcripts_dir = Path(args.transcripts_dir)
    files = sorted(transcripts_dir.rglob("*.md"))

    print(f"Found {len(files)} transcript files")
    print(f"Gateway: {args.gateway_url}")
    print(f"Identity: {args.identity}")
    print()

    loaded = 0
    for f in files:
        content = f.read_text()
        meta, body = parse_frontmatter(content)

        deal_id = meta.get("deal_id", "")
        rep = meta.get("rep", "")
        account = meta.get("account", "")
        day = meta.get("day", "")
        subject_id = f"deal-{deal_id}" if deal_id else ""

        # Build metadata
        kwargs: dict[str, str | int] = {}
        if subject_id:
            kwargs["subject_id"] = subject_id
        if meta.get("severity"):
            kwargs["severity"] = meta["severity"]

        send(
            body,
            namespace="sales",
            **kwargs,
        )
        loaded += 1

        if loaded % 10 == 0:
            print(f"  Sent {loaded}/{len(files)}...")

    print(f"\nSent {loaded} transcripts. Waiting for queue to drain...")
    time.sleep(5)
    print("Done.")


if __name__ == "__main__":
    main()
