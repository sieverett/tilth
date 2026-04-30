"""Entrypoint for the query gateway."""

import os

import uvicorn

from tilth_server._shared.models import create_embedding_client
from tilth_server.query.app import create_app


def main() -> None:
    policy_path = os.environ.get(
        "READ_POLICY_PATH", "/etc/tilth/read-policy.yaml"
    )
    collection_name = os.environ.get("COLLECTION_NAME", "tilth")

    from qdrant_client import AsyncQdrantClient

    qdrant = AsyncQdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY"),
    )

    embedding_client = create_embedding_client()

    app = create_app(
        policy_path=policy_path,
        qdrant_client=qdrant,
        embedding_client=embedding_client,
        collection_name=collection_name,
    )

    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
