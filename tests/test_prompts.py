"""Prompts: só citam tools registradas, sempre com o prefixo ``gobus_``."""

import re

import pytest
from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.prompts.draft_press_release import draft_press_release_prompt
from gobus_mcp.prompts.monitor_agency import monitor_agency_prompt
from gobus_mcp.prompts.trace_entity import trace_entity_prompt
from gobus_mcp.prompts.weekly_digest import weekly_digest_prompt

PROMPTS = {
    "monitor_agency": lambda: monitor_agency_prompt("saude", "Ministério da Saúde", 7),
    "trace_entity": lambda: trace_entity_prompt("Lula", "PER", "2024-01-01", "2024-12-31"),
    "weekly_digest": weekly_digest_prompt,
    "draft_press_release": lambda: draft_press_release_prompt("vacinação", "saude", 5),
}


def _text(messages: list[dict]) -> str:
    return "\n".join(m["content"]["text"] for m in messages)


@pytest.fixture
async def tool_names() -> set[str]:
    async with Client(server.mcp) as client:
        return {t.name for t in await client.list_tools()}


@pytest.mark.parametrize("name", list(PROMPTS))
async def test_prompt_cita_so_tools_gobus_existentes(name, tool_names):
    text = _text(PROMPTS[name]())

    cited = set(re.findall(r"\bgobus_\w+", text))
    assert cited, "o prompt deve orientar o uso de ao menos uma tool"
    assert cited <= tool_names, f"tools inexistentes: {cited - tool_names}"
    for tool in tool_names:
        bare = tool.removeprefix("gobus_")
        assert not re.search(rf"(?<!gobus_)\b{bare}\b", text), f"'{bare}' sem o prefixo gobus_"


@pytest.mark.parametrize("name", list(PROMPTS))
def test_prompt_nao_depende_de_campos_mortos(name):
    text = _text(PROMPTS[name]())
    # viewCount 99,8% nulo e trendingScore 100% nulo (investigação de 05/10/2026)
    assert "view_count" not in text
    assert "trending_score" not in text
