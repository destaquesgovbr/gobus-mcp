"""Prompts renderizados pelo servidor (``prompts/get``): uma mensagem de usuário em texto,
que só cita tools registradas, sempre com o prefixo ``gobus_``.

Os prompts devolvem ``str``: no fastmcp 3.4 um ``list[dict]`` quebra o ``prompts/get``
("messages[0] must be Message or str, got dict"). Por isso os testes renderizam pelo
``Client`` em memória, como o host faz, e não chamam as funções diretamente.
"""

import re

import pytest
from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.prompts import _int_arg

PROMPT_ARGS = {
    "prompt_monitor_agency": {
        "agency_key": "saude",
        "agency_name": "Ministério da Saúde",
        "days": "7",
    },
    "prompt_trace_entity": {
        "entity_name": "Lula",
        "entity_type": "PER",
        "date_from": "2024-01-01",
        "date_to": "2024-12-31",
    },
    "prompt_weekly_digest": {},
    "prompt_draft_press_release": {"topic": "vacinação", "agency_key": "saude", "limit": "5"},
}

REQUIRED_ARGS = {
    "prompt_monitor_agency": {"agency_key"},
    "prompt_trace_entity": {"entity_name"},
    "prompt_weekly_digest": set(),
    "prompt_draft_press_release": {"topic"},
}


async def render(name: str, args: dict[str, str]) -> str:
    """Renderiza o prompt pelo servidor e devolve o texto da mensagem única."""
    async with Client(server.mcp) as client:
        result = await client.get_prompt(name, args)

    assert len(result.messages) == 1, result.messages
    (message,) = result.messages
    assert message.role == "user"
    assert message.content.type == "text"
    return message.content.text


@pytest.fixture
async def tool_names() -> set[str]:
    async with Client(server.mcp) as client:
        return {t.name for t in await client.list_tools()}


async def test_lista_os_4_prompts_com_os_obrigatorios():
    async with Client(server.mcp) as client:
        prompts = await client.list_prompts()

    required = {p.name: {a.name for a in p.arguments or [] if a.required} for p in prompts}
    assert required == REQUIRED_ARGS


@pytest.mark.parametrize("name", list(PROMPT_ARGS))
async def test_prompt_renderiza_uma_mensagem_de_usuario(name):
    text = await render(name, PROMPT_ARGS[name])
    assert text.strip()


@pytest.mark.parametrize("name", list(PROMPT_ARGS))
async def test_prompt_cita_so_tools_gobus_existentes(name, tool_names):
    text = await render(name, PROMPT_ARGS[name])

    cited = set(re.findall(r"\bgobus_\w+", text))
    assert cited, "o prompt deve orientar o uso de ao menos uma tool"
    assert cited <= tool_names, f"tools inexistentes: {cited - tool_names}"
    for tool in tool_names:
        bare = tool.removeprefix("gobus_")
        assert not re.search(rf"(?<!gobus_)\b{bare}\b", text), f"'{bare}' sem o prefixo gobus_"


@pytest.mark.parametrize("name", list(PROMPT_ARGS))
async def test_prompt_nao_depende_de_campos_mortos(name):
    text = await render(name, PROMPT_ARGS[name])
    # viewCount 99,8% nulo e trendingScore 100% nulo (investigação de 05/10/2026)
    assert "view_count" not in text
    assert "trending_score" not in text


@pytest.mark.parametrize("days", [{"days": ""}, {}], ids=["vazio", "omitido"])
async def test_monitor_agency_sem_days_usa_1_dia(days):
    text = await render("prompt_monitor_agency", {"agency_key": "mec", **days})

    yesterday = closed_window(1, reference_date()).end.isoformat()
    assert f'date_from="{yesterday}", date_to="{yesterday}"' in text


async def test_draft_press_release_com_limit_vazio_usa_o_padrao():
    text = await render("prompt_draft_press_release", {"topic": "vacinação", "limit": ""})
    assert "os 5 artigos" in text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", 1),
        (None, 1),
        ("abc", 1),
        ("7.5", 1),
        ("7", 7),
        (" 7 ", 7),
        (7, 7),
        ("0", 1),
        ("-3", 1),
        ("99", 31),
    ],
)
def test_int_arg_cai_no_padrao_e_limita_a_faixa(value, expected):
    assert _int_arg(value, 1, 1, 31) == expected
