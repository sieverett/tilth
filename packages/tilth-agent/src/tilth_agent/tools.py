"""Tool definitions and execution for the reasoning agent."""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("tilth.agent")

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "describe_schema",
        "description": (
            "Get the data model for the memory system. Returns available "
            "namespaces (scoped to your permissions), record fields, "
            "metadata fields, filterable keys, and the embedding model. "
            "Call this first to understand what data is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_records",
        "description": (
            "List record metadata (no content) for a namespace. Returns "
            "record IDs, sources, timestamps, and subject IDs. Use this "
            "to understand the population before searching."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list records from.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max records to return (default 100).",
                    "default": 100,
                },
            },
            "required": ["namespace"],
        },
    },
    {
        "name": "search_tilth",
        "description": (
            "Search organizational memory by semantic similarity. Returns "
            "full record content matching the query. Use natural-language "
            "queries — describe what you're looking for, not keywords."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language description of what to find.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results (1-10, default 5).",
                    "default": 5,
                },
                "filters": {
                    "type": "object",
                    "description": (
                        "Optional filters. Keys: severity, env, subject_id, trace_id."
                    ),
                    "properties": {
                        "subject_id": {"type": "string"},
                        "severity": {"type": "string"},
                        "env": {"type": "string"},
                        "trace_id": {"type": "string"},
                    },
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_to_tilth",
        "description": (
            "Write an analytical brief to organizational memory. Use this "
            "when you have a finding with evidence and a recommendation. "
            "The brief will be retrievable by other agents and humans."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The full brief text.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warn", "error"],
                    "description": "How urgent this finding is.",
                },
                "subject_id": {
                    "type": "string",
                    "description": "Optional: topic or ID this relates to.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save notes to your persistent memory for the next run. "
            "Include: confirmed hypotheses, rejected hypotheses, open "
            "questions, and what to investigate next time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Structured notes for your future self.",
                },
            },
            "required": ["content"],
        },
    },
]


class ToolExecutor:
    """Executes tool calls against the tilth gateway."""

    def __init__(
        self,
        gateway_url: str,
        identity: str,
        memory_path: Path,
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._identity = identity
        self._memory_path = memory_path
        self._client = httpx.Client(timeout=30.0)
        self._headers = {
            "x-workload-identity": identity,
            "Content-Type": "application/json",
        }

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool call, return the result as a string."""
        method = getattr(self, f"_tool_{tool_name}", None)
        if method is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        start = time.monotonic()
        result = method(tool_input)
        elapsed = time.monotonic() - start

        # Log tool call (hash the query if present)
        log_input = dict(tool_input)
        if "query" in log_input:
            log_input["query_hash"] = hashlib.sha256(
                log_input.pop("query").encode()
            ).hexdigest()[:16]

        log.info(
            "tool_call: %s input=%s elapsed=%.2fs",
            tool_name,
            json.dumps(log_input),
            elapsed,
        )

        return result

    def _tool_describe_schema(self, _input: dict[str, Any]) -> str:
        resp = self._client.get(
            f"{self._gateway_url}/schema",
            headers=self._headers,
        )
        if resp.status_code != 200:
            return json.dumps({"error": f"schema request failed: {resp.status_code}"})
        return resp.text

    def _tool_list_records(self, tool_input: dict[str, Any]) -> str:
        namespace = tool_input["namespace"]
        limit = tool_input.get("limit", 100)

        # Use Qdrant scroll directly via the query gateway's Qdrant
        # For now, use a broad search with a generic query
        resp = self._client.post(
            f"{self._gateway_url}/query",
            headers=self._headers,
            json={
                "query": f"records in {namespace}",
                "namespaces": [namespace],
                "top_k": min(limit, 20),
            },
        )
        if resp.status_code != 200:
            return json.dumps({"error": f"list request failed: {resp.status_code}"})

        results = resp.json().get("results", [])
        # Return metadata only, strip full content
        summaries = []
        for r in results:
            summaries.append({
                "id": r["id"],
                "source": r["source"],
                "namespace": r["namespace"],
                "ts": r["ts"],
                "subject_id": r.get("subject_id"),
                "score": r["score"],
                "content_preview": r["content"][:200] + "...",
            })

        return json.dumps({
            "count": len(summaries),
            "records": summaries,
        })

    def _tool_search_tilth(self, tool_input: dict[str, Any]) -> str:
        body: dict[str, Any] = {
            "query": tool_input["query"],
            "top_k": tool_input.get("top_k", 5),
        }
        if "filters" in tool_input and tool_input["filters"]:
            body["filters"] = tool_input["filters"]

        resp = self._client.post(
            f"{self._gateway_url}/query",
            headers=self._headers,
            json=body,
        )
        if resp.status_code != 200:
            return json.dumps({"error": f"search failed: {resp.status_code}"})

        return resp.text

    def _tool_write_to_tilth(self, tool_input: dict[str, Any]) -> str:
        from tilth import send

        kwargs: dict[str, Any] = {}
        if "severity" in tool_input:
            kwargs["severity"] = tool_input["severity"]
        if "subject_id" in tool_input:
            kwargs["subject_id"] = tool_input["subject_id"]

        send(
            tool_input["text"],
            namespace="analysis",
            **kwargs,
        )
        return json.dumps({"status": "written"})

    def _tool_save_memory(self, tool_input: dict[str, Any]) -> str:
        self._memory_path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_path.write_text(tool_input["content"])
        return json.dumps({"status": "saved"})

    def close(self) -> None:
        self._client.close()
