"""Prompts renderizados pelo servidor (``prompts/get``): uma mensagem de usuário em texto,
que só cita tools registradas, sempre com o prefixo ``gobus_``.

Os prompts devolvem ``str``: no fastmcp 3.4 um ``list[dict]`` quebra o ``prompts/get``
("messages[0] must be Message or str, got dict"). Por isso os testes de forma renderizam
pelo ``Client`` em memória, como o host faz; só os que dependem de data chamam a função
direto, com ``today`` injetado.
"""

import re
from datetime import date

import pytest
from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.prompts import _int_arg
from gobus_mcp.prompts.monitor_agency import monitor_agency_prompt
from gobus_mcp.prompts.trace_entity import trace_entity_prompt
from gobus_mcp.prompts.weekly_digest import weekly_digest_prompt

D_2110 = date(2026, 10, 21)  # quarta-feira, no defeso eleitoral (04/07–25/10/2026)

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
    assert "limit=5" in text


async def test_draft_press_release_passa_o_limit_para_a_busca():
    # pós-merge do #12: o limit só aparecia no texto, a chamada usava o padrão da tool (10)
    text = await render(
        "prompt_draft_press_release", {"topic": "vacinação", "agency_key": "saude", "limit": "12"}
    )
    assert 'gobus_search_news(query="vacinação", agency_key="saude", limit=12)' in text
    assert "Para os 3 artigos mais relevantes" in text


@pytest.mark.parametrize(
    ("limit", "step2"),
    [("1", "Para o artigo encontrado"), ("2", "Para os 2 artigos encontrados")],
)
async def test_draft_press_release_passo_2_acompanha_o_limit(limit, step2):
    text = await render("prompt_draft_press_release", {"topic": "vacinação", "limit": limit})
    assert f'gobus_search_news(query="vacinação", limit={limit})' in text
    assert step2 in text
    assert "os 3 artigos" not in text


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


@pytest.mark.parametrize("name", list(PROMPT_ARGS))
async def test_prompt_pede_citacao_com_link_markdown(name):
    text = await render(name, PROMPT_ARGS[name])
    assert "[título](url)" in text


@pytest.mark.parametrize(
    ("days", "date_from", "date_to"),
    [(1, "2026-10-20", "2026-10-20"), (7, "2026-10-14", "2026-10-20")],
)
def test_monitor_agency_escreve_as_chamadas_com_a_janela_fechada(days, date_from, date_to):
    text = monitor_agency_prompt("mec", "Ministério da Educação", days, today=D_2110)

    assert (
        f'gobus_search_news(query="*", agency_key="mec", '
        f'date_from="{date_from}", date_to="{date_to}"'
    ) in text
    assert (
        f'gobus_get_agency_analytics(agencies=["mec"], '
        f'date_from="{date_from}", date_to="{date_to}", granularity="DAY")'
    ) in text


def test_monitor_agency_avisa_quando_a_janela_cai_no_defeso():
    text = monitor_agency_prompt("mec", days=1, today=D_2110)
    assert "defeso eleitoral" in text.lower()
    assert "04/07/2026 a 25/10/2026" in text


def test_monitor_agency_avisa_quando_a_janela_cai_na_recuperacao():
    text = monitor_agency_prompt("mec", days=1, today=date(2026, 11, 10))
    assert "recuperação" in text.lower()
    assert "29/11/2026" in text
    assert "04/07/2026 a 25/10/2026" not in text


def test_monitor_agency_fora_do_defeso_nao_avisa():
    text = monitor_agency_prompt("mec", days=7, today=date(2027, 1, 15)).lower()
    assert "defeso" not in text
    assert "recuperação" not in text


def test_trace_entity_pede_rede_rasa_e_limitada():
    text = trace_entity_prompt("Lula", "PER")
    assert "depth=1, max_nodes=15" in text
    assert "depth=2" not in text


def test_trace_entity_descreve_a_rede_centrada_e_nao_a_antiga_de_centenas_de_nos():
    # a rede é centrada no foco (graphql-api#32, gobus#13): o 2º grau tem ≤ 5 entidades por
    # vizinho; o texto antigo justificava o depth=1 com "centenas de nós"
    text = trace_entity_prompt("Pé-de-Meia")
    assert "centenas de nós" not in text
    assert "centrada na entidade" in text
    assert "associação" in text
    assert "Para explorar" in text  # o rodapé da rede sugere o segundo grau


def test_weekly_digest_traz_a_semana_fechada_no_titulo_e_nas_buscas():
    text = weekly_digest_prompt(today=D_2110)

    title = next(line for line in text.splitlines() if line.startswith("**Título:**"))
    assert "14/10 a 20/10/2026" in title
    assert 'date_from="2026-10-14", date_to="2026-10-20"' in text
    assert "defeso eleitoral" in text.lower()
