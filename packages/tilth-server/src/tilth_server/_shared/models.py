"""Model provider abstraction for embeddings and LLM calls.

Swap providers via env vars without changing application code.

Supported providers:
    - openai: standard OpenAI API
    - azure: Azure OpenAI
    - anthropic: Anthropic Claude

Embedding env vars:
    EMBED_PROVIDER: "openai" | "azure" (default: "openai")
    EMBED_MODEL: model or deployment name (default: "text-embedding-3-small")
    EMBED_DIM: vector dimension (default: 1536)

LLM env vars:
    LLM_PROVIDER: "openai" | "azure" | "anthropic" (default: "anthropic")
    LLM_MODEL: model name (default: "claude-sonnet-4-6")

Provider-specific env vars:
    openai: OPENAI_API_KEY
    azure: AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION
    anthropic: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol


# --- Embeddings ---


class EmbeddingClient(Protocol):
    """Protocol for embedding providers."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...


class OpenAIEmbeddings:
    """Standard OpenAI embeddings."""

    def __init__(self, model: str, dimension: int) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI()
        self._model = model
        self._dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(
            model=self._model, input=texts
        )
        return [e.embedding for e in resp.data]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension


class AzureEmbeddings:
    """Azure OpenAI embeddings."""

    def __init__(self, model: str, dimension: int) -> None:
        from openai import AsyncAzureOpenAI

        self._client = AsyncAzureOpenAI(
            api_key=os.environ["AZURE_API_KEY"],
            azure_endpoint=os.environ["AZURE_API_BASE"],
            api_version=os.environ.get("AZURE_API_VERSION", "2024-02-01"),
        )
        self._model = model
        self._dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(
            model=self._model, input=texts
        )
        return [e.embedding for e in resp.data]

    @property
    def model_name(self) -> str:
        return f"azure/{self._model}"

    @property
    def dimension(self) -> int:
        return self._dimension


_EMBED_PROVIDERS: dict[str, type[OpenAIEmbeddings | AzureEmbeddings]] = {
    "openai": OpenAIEmbeddings,
    "azure": AzureEmbeddings,
}


def create_embedding_client(
    provider: str | None = None,
    model: str | None = None,
    dimension: int | None = None,
) -> EmbeddingClient:
    """Create an embedding client from env vars or explicit args."""
    provider = provider or os.environ.get("EMBED_PROVIDER", "openai")
    model = model or os.environ.get("EMBED_MODEL", "text-embedding-3-small")
    dimension = dimension or int(os.environ.get("EMBED_DIM", "1536"))

    cls = _EMBED_PROVIDERS.get(provider)
    if cls is None:
        supported = ", ".join(sorted(_EMBED_PROVIDERS.keys()))
        raise ValueError(
            f"Unknown embedding provider: {provider!r}. "
            f"Supported: {supported}"
        )

    return cls(model=model, dimension=dimension)


# --- LLM ---


class LLMResponse:
    """Normalized LLM response across providers."""

    def __init__(
        self,
        content: list[dict[str, Any]],
        stop_reason: str,
        usage: dict[str, int],
    ) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage

    @property
    def text(self) -> str:
        """Extract text content from the response."""
        parts = [
            block["text"]
            for block in self.content
            if block.get("type") == "text"
        ]
        return "\n".join(parts)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """Extract tool use blocks from the response."""
        return [
            block for block in self.content if block.get("type") == "tool_use"
        ]


class LLMClient(Protocol):
    """Protocol for LLM providers."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...

    @property
    def model_name(self) -> str: ...


class AnthropicLLM:
    """Anthropic Claude."""

    def __init__(self, model: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic()
        self._model = model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system is not None:
            kwargs["system"] = system
        if tools is not None:
            kwargs["tools"] = tools

        resp = await self._client.messages.create(**kwargs)

        content = [block.model_dump() for block in resp.content]
        return LLMResponse(
            content=content,
            stop_reason=resp.stop_reason or "end_turn",
            usage={
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            },
        )

    @property
    def model_name(self) -> str:
        return self._model


class OpenAILLM:
    """OpenAI chat completions."""

    def __init__(self, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI()
        self._model = model

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert Anthropic-format messages to OpenAI format."""
        converted: list[dict[str, Any]] = []
        for msg in messages:
            role = msg["role"]
            content = msg.get("content")

            # Assistant messages with tool_use content blocks
            if role == "assistant" and isinstance(content, list):
                text_parts = [
                    b["text"] for b in content if b.get("type") == "text"
                ]
                tool_calls = [
                    {
                        "id": b["id"],
                        "type": "function",
                        "function": {
                            "name": b["name"],
                            "arguments": json.dumps(b.get("input", {})),
                        },
                    }
                    for b in content
                    if b.get("type") == "tool_use"
                ]
                oai_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                }
                if tool_calls:
                    oai_msg["tool_calls"] = tool_calls
                converted.append(oai_msg)

            # User messages with tool_result content blocks
            elif role == "user" and isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        converted.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        })
                    else:
                        converted.append({"role": "user", "content": str(block)})

            # Normal messages
            else:
                converted.append(msg)

        return converted

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        oai_messages = self._convert_messages(messages)
        if system is not None:
            oai_messages.insert(0, {"role": "system", "content": system})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": oai_messages,
            "max_completion_tokens": max_tokens,
        }
        if tools is not None:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                }
                for t in tools
            ]

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]

        content: list[dict[str, Any]] = []
        if choice.message.content:
            content.append({"type": "text", "text": choice.message.content})
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": json.loads(tc.function.arguments),
                    }
                )

        stop_reason = (
            "tool_use" if choice.finish_reason == "tool_calls" else "end_turn"
        )

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage={
                "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "output_tokens": (
                    resp.usage.completion_tokens if resp.usage else 0
                ),
            },
        )

    @property
    def model_name(self) -> str:
        return self._model


class AzureLLM:
    """Azure OpenAI chat completions."""

    def __init__(self, model: str) -> None:
        from openai import AsyncAzureOpenAI

        self._client = AsyncAzureOpenAI(
            api_key=os.environ["AZURE_API_KEY"],
            azure_endpoint=os.environ["AZURE_API_BASE"],
            api_version=os.environ.get("AZURE_API_VERSION", "2024-02-01"),
        )
        self._model = model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Reuse OpenAI's completion logic with Azure client
        oai = OpenAILLM.__new__(OpenAILLM)
        oai._client = self._client  # type: ignore[assignment]
        oai._model = self._model
        return await oai.complete(
            messages, system=system, tools=tools, max_tokens=max_tokens
        )

    @property
    def model_name(self) -> str:
        return f"azure/{self._model}"


_LLM_PROVIDERS: dict[
    str, type[AnthropicLLM | OpenAILLM | AzureLLM]
] = {
    "anthropic": AnthropicLLM,
    "openai": OpenAILLM,
    "azure": AzureLLM,
}


def create_llm_client(
    provider: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """Create an LLM client from env vars or explicit args."""
    provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")
    model = model or os.environ.get("LLM_MODEL", "claude-sonnet-4-6")

    cls = _LLM_PROVIDERS.get(provider)
    if cls is None:
        supported = ", ".join(sorted(_LLM_PROVIDERS.keys()))
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. "
            f"Supported: {supported}"
        )

    return cls(model=model)
