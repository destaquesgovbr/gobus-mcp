FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ ./src/

ENV PYTHONPATH=/app/src
EXPOSE 8080

CMD ["python", "-m", "gobus_mcp"]
