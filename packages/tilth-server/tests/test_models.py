"""Tests for the model provider abstraction (embeddings + LLM)."""

import os
from unittest.mock import patch

import pytest

from tilth_server._shared.models import (
    AnthropicLLM,
    AzureEmbeddings,
    AzureLLM,
    LLMResponse,
    OpenAIEmbeddings,
    OpenAILLM,
    create_embedding_client,
    create_llm_client,
)


# --- Embedding tests ---


class TestCreateEmbeddingClient:
    def test_defaults_to_openai(self) -> None:
        os.environ.pop("EMBED_PROVIDER", None)
        with patch(
            "tilth_server._shared.models.OpenAIEmbeddings.__init__",
            return_value=None,
        ):
            client = create_embedding_client()
            assert isinstance(client, OpenAIEmbeddings)

    def test_azure_provider(self) -> None:
        os.environ["AZURE_API_KEY"] = "test"
        os.environ["AZURE_API_BASE"] = "https://test.openai.azure.com"
        with patch(
            "tilth_server._shared.models.AzureEmbeddings.__init__",
            return_value=None,
        ):
            client = create_embedding_client(provider="azure")
            assert isinstance(client, AzureEmbeddings)
        os.environ.pop("AZURE_API_KEY", None)
        os.environ.pop("AZURE_API_BASE", None)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            create_embedding_client(provider="bad")

    def test_explicit_args_override_env(self) -> None:
        os.environ["EMBED_PROVIDER"] = "azure"
        with patch(
            "tilth_server._shared.models.OpenAIEmbeddings.__init__",
            return_value=None,
        ):
            client = create_embedding_client(
                provider="openai", model="custom", dimension=512
            )
            assert isinstance(client, OpenAIEmbeddings)
        os.environ.pop("EMBED_PROVIDER", None)


class TestEmbeddingModelName:
    def test_openai_no_prefix(self) -> None:
        with patch(
            "tilth_server._shared.models.OpenAIEmbeddings.__init__",
            return_value=None,
        ):
            client = OpenAIEmbeddings(
                model="text-embedding-3-small", dimension=1536
            )
            client._model = "text-embedding-3-small"
            assert client.model_name == "text-embedding-3-small"

    def test_azure_has_prefix(self) -> None:
        with patch(
            "tilth_server._shared.models.AzureEmbeddings.__init__",
            return_value=None,
        ):
            client = AzureEmbeddings(
                model="text-embedding-3-small", dimension=1536
            )
            client._model = "text-embedding-3-small"
            assert client.model_name == "azure/text-embedding-3-small"


# --- LLM tests ---


class TestCreateLLMClient:
    def test_defaults_to_anthropic(self) -> None:
        os.environ.pop("LLM_PROVIDER", None)
        with patch(
            "tilth_server._shared.models.AnthropicLLM.__init__",
            return_value=None,
        ):
            client = create_llm_client()
            assert isinstance(client, AnthropicLLM)

    def test_openai_provider(self) -> None:
        with patch(
            "tilth_server._shared.models.OpenAILLM.__init__",
            return_value=None,
        ):
            client = create_llm_client(provider="openai")
            assert isinstance(client, OpenAILLM)

    def test_azure_provider(self) -> None:
        os.environ["AZURE_API_KEY"] = "test"
        os.environ["AZURE_API_BASE"] = "https://test.openai.azure.com"
        with patch(
            "tilth_server._shared.models.AzureLLM.__init__",
            return_value=None,
        ):
            client = create_llm_client(provider="azure")
            assert isinstance(client, AzureLLM)
        os.environ.pop("AZURE_API_KEY", None)
        os.environ.pop("AZURE_API_BASE", None)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_client(provider="bad")

    def test_explicit_args_override_env(self) -> None:
        os.environ["LLM_PROVIDER"] = "openai"
        with patch(
            "tilth_server._shared.models.AnthropicLLM.__init__",
            return_value=None,
        ):
            client = create_llm_client(provider="anthropic", model="claude-opus-4-6")
            assert isinstance(client, AnthropicLLM)
        os.environ.pop("LLM_PROVIDER", None)


class TestLLMModelName:
    def test_anthropic_no_prefix(self) -> None:
        with patch(
            "tilth_server._shared.models.AnthropicLLM.__init__",
            return_value=None,
        ):
            client = AnthropicLLM(model="claude-sonnet-4-6")
            client._model = "claude-sonnet-4-6"
            assert client.model_name == "claude-sonnet-4-6"

    def test_azure_has_prefix(self) -> None:
        os.environ["AZURE_API_KEY"] = "test"
        os.environ["AZURE_API_BASE"] = "https://test.openai.azure.com"
        with patch(
            "tilth_server._shared.models.AzureLLM.__init__",
            return_value=None,
        ):
            client = AzureLLM(model="gpt-4o")
            client._model = "gpt-4o"
            assert client.model_name == "azure/gpt-4o"
        os.environ.pop("AZURE_API_KEY", None)
        os.environ.pop("AZURE_API_BASE", None)


class TestLLMResponse:
    def test_text_extraction(self) -> None:
        resp = LLMResponse(
            content=[
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "world"},
            ],
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 5},
        )
        assert resp.text == "hello\nworld"

    def test_tool_calls_extraction(self) -> None:
        resp = LLMResponse(
            content=[
                {"type": "text", "text": "searching..."},
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "search_tilth",
                    "input": {"query": "failures"},
                },
            ],
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 5},
        )
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["name"] == "search_tilth"

    def test_empty_content(self) -> None:
        resp = LLMResponse(
            content=[], stop_reason="end_turn",
            usage={"input_tokens": 0, "output_tokens": 0},
        )
        assert resp.text == ""
        assert resp.tool_calls == []
