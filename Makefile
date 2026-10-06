# Alvos de desenvolvimento. PY aponta para a venv do clone; PYTHONPATH=src garante que
# um worktree teste o próprio código (o install editável da venv aponta para o clone).
PY ?= .venv/bin/python3.12
PORT ?= 8000
MCPJAM ?= @mcpjam/cli@5.13.0
export PYTHONPATH := $(CURDIR)/src

.PHONY: docs-serve docs-build test lint ui ui-install ui-fixtures conformance

docs-serve:
	mkdocs serve --dev-addr=localhost:8001

docs-build:
	mkdocs build --strict

# Suíte rápida (sem os marcadores live e ui).
test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests && $(PY) -m ruff format --check src tests

# MCP Apps no mini-host headless (uma vez: make ui-install).
ui-install:
	$(PY) -m playwright install chromium

ui:
	$(PY) -m pytest -q -m ui

# Regera tests/fixtures/ui/<app>/<estado>.json depois de mudar builder, render ou payload.
ui-fixtures:
	$(PY) -m tests.fixtures.ui.build

# MCPJam apps conformance contra o servidor local em HTTP (GraphQL num endereço morto: os
# resources ui:// são estáticos e a checagem não chama tools). Uma linha só: cada linha
# de receita roda num shell próprio.
conformance:
	PORT=$(PORT) GOBUS_GRAPHQL_URL=http://127.0.0.1:9/graphql $(PY) -m gobus_mcp & pid=$$!; trap 'kill $$pid 2>/dev/null' EXIT; until curl -s -o /dev/null http://127.0.0.1:$(PORT)/mcp; do kill -0 $$pid 2>/dev/null || exit 1; sleep 0.5; done; npx -y $(MCPJAM) apps conformance --url http://127.0.0.1:$(PORT)/mcp
