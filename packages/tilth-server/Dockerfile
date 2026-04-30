FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install .
# Ingest gateway entrypoint
CMD ["uvicorn", "tilth_server.ingest.app:app", "--host", "0.0.0.0", "--port", "8001"]
