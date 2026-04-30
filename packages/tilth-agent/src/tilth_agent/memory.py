"""Agent memory — persistent state across runs."""

from pathlib import Path


def load_memory(path: Path) -> str | None:
    """Load agent memory from disk. Returns None if no prior memory."""
    if path.exists():
        content = path.read_text().strip()
        return content if content else None
    return None
