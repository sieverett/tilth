"""YAML policy file loading for namespace ACLs."""

import yaml


def load_policy(path: str) -> dict[str, set[str]]:
    """Load a YAML policy file mapping caller IDs to permitted namespaces.

    Raises FileNotFoundError if the file doesn't exist.
    Raises ValueError if the file content is invalid.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"policy file {path} must be a YAML mapping")

    policy: dict[str, set[str]] = {}
    for caller, namespaces in raw.items():
        if not isinstance(namespaces, list):
            raise ValueError(
                f"policy entry for {caller} must be a list of namespaces"
            )
        policy[str(caller)] = set(str(ns) for ns in namespaces)

    return policy
