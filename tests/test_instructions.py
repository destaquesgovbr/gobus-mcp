"""Instruções do servidor (``initialize.instructions``): curtas, em pt-BR, só com tools
registradas e com as datas do defeso vindas do ``calendario``."""

import re

from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.calendario import BLACKOUTS
from gobus_mcp.instructions import SERVER_INSTRUCTIONS

MAX_BYTES = 1536


async def test_initialize_entrega_as_instrucoes():
    async with Client(server.mcp) as client:
        instructions = client.initialize_result.instructions

    assert instructions == SERVER_INSTRUCTIONS


def test_instrucoes_cabem_em_1_5_kb():
    assert len(SERVER_INSTRUCTIONS.encode()) <= MAX_BYTES


def test_instrucoes_orientam_entidade_links_e_ausencia_de_dado():
    assert "gobus_resolve_entity" in SERVER_INSTRUCTIONS
    assert "[título](url)" in SERVER_INSTRUCTIONS
    assert "gobus_get_article" in SERVER_INSTRUCTIONS
    assert "gobus://health/pipelines" in SERVER_INSTRUCTIONS
    assert "indisponível" in SERVER_INSTRUCTIONS


def test_instrucoes_trazem_o_defeso_do_calendario():
    for period in BLACKOUTS:
        assert period.start.strftime("%d/%m") in SERVER_INSTRUCTIONS
        assert period.end.strftime("%d/%m/%Y") in SERVER_INSTRUCTIONS
        assert period.recovery_until.strftime("%d/%m") in SERVER_INSTRUCTIONS


async def test_instrucoes_citam_so_tools_registradas():
    async with Client(server.mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    cited = set(re.findall(r"\bgobus_\w+", SERVER_INSTRUCTIONS))
    assert cited <= tools, cited - tools
