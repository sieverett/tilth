FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install .
CMD ["python", "-m", "tilth_mcp"]
