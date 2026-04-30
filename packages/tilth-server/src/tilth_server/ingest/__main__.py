"""Entrypoint for the ingest gateway."""

import os

import uvicorn

from tilth_server._shared.models import create_embedding_client
from tilth_server.ingest.app import create_app
from tilth_server.ingest.scrubber import create_analyzer, create_anonymizer


def main() -> None:
    policy_path = os.environ.get(
        "WRITE_POLICY_PATH", "/etc/tilth/write-policy.yaml"
    )
    collection_name = os.environ.get("COLLECTION_NAME", "tilth")

    # Lazy imports to avoid loading at module level
    from qdrant_client import AsyncQdrantClient

    qdrant = AsyncQdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY"),
    )

    embedding_client = create_embedding_client()
    analyzer = create_analyzer()
    anonymizer = create_anonymizer()

    app = create_app(
        policy_path=policy_path,
        qdrant_client=qdrant,
        embedding_client=embedding_client,
        analyzer=analyzer,
        anonymizer=anonymizer,
        collection_name=collection_name,
    )

    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
