# Build reproduzível: dependências instaladas a partir do poetry.lock.
# Etapa 1 (builder): Poetry cria /app/.venv só com o grupo main, sem o pacote raiz.
FROM python:3.12-slim AS builder

ENV POETRY_VERSION=2.0.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app
COPY pyproject.toml poetry.lock ./
# Falha o build se o lock estiver dessincronizado do pyproject.
RUN poetry check --lock && poetry install --only main --no-root --no-ansi

# Etapa 2 (runtime): só a venv e o código-fonte; o pacote é importado via PYTHONPATH.
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "-m", "gobus_mcp"]
