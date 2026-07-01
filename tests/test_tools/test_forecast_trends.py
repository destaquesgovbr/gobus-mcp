from gobus_mcp.tools.forecast_trends import forecast_trends


def _theme(label, code, growth, window=10, baseline=1.0):
    return {
        "themeLabel": label,
        "themeCode": code,
        "growthScore": growth,
        "windowCount": window,
        "baselineDailyAvg": baseline,
    }


def _row(md: str, label: str) -> str:
    """Retorna a linha da tabela que contém o rótulo do tema."""
    for line in md.splitlines():
        if label in line:
            return line
    return ""


async def test_tema_em_3_janelas_tem_confianca_alta(fake_client):
    r3 = {"trendingThemes": [_theme("Educação", "educacao", 3.0)]}
    r7 = {"trendingThemes": [_theme("Educação", "educacao", 2.0)]}
    r21 = {"trendingThemes": [_theme("Educação", "educacao", 1.5)]}
    fake_client.set_responses([r3, r7, r21])

    result = await forecast_trends(fake_client)

    row = _row(result, "Educação")
    assert "alta" in row


async def test_composite_score_ponderado(fake_client):
    # composite = 4.0*0.5 + 2.0*0.3 + 1.0*0.2 = 2.0 + 0.6 + 0.2 = 2.80
    r3 = {"trendingThemes": [_theme("Educação", "educacao", 4.0)]}
    r7 = {"trendingThemes": [_theme("Educação", "educacao", 2.0)]}
    r21 = {"trendingThemes": [_theme("Educação", "educacao", 1.0)]}
    fake_client.set_responses([r3, r7, r21])

    result = await forecast_trends(fake_client)

    row = _row(result, "Educação")
    assert "2.80" in row


async def test_momentum_acelerando_quando_3d_maior(fake_client):
    r3 = {"trendingThemes": [_theme("Saúde", "saude", 3.0)]}
    r7 = {"trendingThemes": [_theme("Saúde", "saude", 1.0)]}
    r21 = {"trendingThemes": []}
    fake_client.set_responses([r3, r7, r21])

    result = await forecast_trends(fake_client)

    row = _row(result, "Saúde")
    assert "acelerando" in row


async def test_momentum_desacelerando_quando_3d_menor(fake_client):
    r3 = {"trendingThemes": [_theme("Saúde", "saude", 1.0)]}
    r7 = {"trendingThemes": [_theme("Saúde", "saude", 3.0)]}
    r21 = {"trendingThemes": []}
    fake_client.set_responses([r3, r7, r21])

    result = await forecast_trends(fake_client)

    row = _row(result, "Saúde")
    assert "desacelerando" in row


async def test_retorna_top_n_temas(fake_client):
    r3 = {"trendingThemes": [
        _theme("Tema A", "a", 5.0),
        _theme("Tema B", "b", 4.0),
        _theme("Tema C", "c", 3.0),
        _theme("Tema D", "d", 2.0),
        _theme("Tema E", "e", 1.0),
    ]}
    r7 = {"trendingThemes": []}
    r21 = {"trendingThemes": []}
    fake_client.set_responses([r3, r7, r21])

    result = await forecast_trends(fake_client, limit=3)

    assert "Tema A" in result
    assert "Tema C" in result
    assert "Tema D" not in result
    assert "Tema E" not in result
