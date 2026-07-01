from gobus_mcp.tools.detect_anomalies import detect_anomalies


def _section(md: str, header: str) -> str:
    """Extrai o corpo de uma seção `### {header}` do Markdown."""
    for part in md.split("### "):
        if part.startswith(header):
            return part
    return ""


def _theme(label, code, growth, window=10, baseline=1.0):
    return {
        "themeLabel": label,
        "themeCode": code,
        "growthScore": growth,
        "windowCount": window,
        "baselineDailyAvg": baseline,
    }


def _entity(name, volume_ratio, window_agencies, entity_id="Q1", etype="ORG"):
    return {
        "entityId": entity_id,
        "canonicalName": name,
        "type": etype,
        "trendingScore": 0.0,
        "volumeRatio": volume_ratio,
        "windowCount": 30,
        "windowAgencies": window_agencies,
    }


async def test_pico_sustentado_quando_tema_em_ambas_as_janelas(fake_client):
    themes_3d = {"trendingThemes": [
        _theme("Saúde Digital", "saude_digital", 2.5),
        _theme("Educação", "educacao", 1.8),
    ]}
    themes_7d = {"trendingThemes": [
        _theme("Saúde Digital", "saude_digital", 2.1),
        _theme("Defesa", "defesa", 1.6),
    ]}
    entities = {"trendingEntities": []}
    fake_client.set_responses([themes_3d, themes_7d, entities])

    result = await detect_anomalies(fake_client)

    picos = _section(result, "Picos Sustentados")
    assert "Saúde Digital" in picos
    # Temas que só aparecem numa janela não são pico sustentado
    assert "Educação" not in picos
    assert "Defesa" not in picos


async def test_silencio_concentrado_alto_volume_poucas_agencias(fake_client):
    themes = {"trendingThemes": []}
    entities = {"trendingEntities": [
        _entity("Ministério X", volume_ratio=4.5, window_agencies=2),
    ]}
    fake_client.set_responses([themes, themes, entities])

    result = await detect_anomalies(fake_client)  # sensitivity medium (>3.0, <5)

    conc = _section(result, "Cobertura Concentrada")
    assert "Ministério X" in conc


async def test_sensitivity_high_threshold_mais_baixo(fake_client):
    themes = {"trendingThemes": []}
    entities = {"trendingEntities": [
        _entity("Órgão Y", volume_ratio=2.5, window_agencies=6),
    ]}

    # medium: 2.5 não passa de 3.0 → não concentrado
    fake_client.set_responses([themes, themes, entities])
    res_med = await detect_anomalies(fake_client, sensitivity="medium")
    assert "Órgão Y" not in _section(res_med, "Cobertura Concentrada")

    # high: threshold mais baixo (>2.0, <8) → concentrado
    fake_client.set_responses([themes, themes, entities])
    res_high = await detect_anomalies(fake_client, sensitivity="high")
    assert "Órgão Y" in _section(res_high, "Cobertura Concentrada")


async def test_sem_anomalias_retorna_tendencias_normais(fake_client):
    themes_3d = {"trendingThemes": [_theme("Agricultura", "agro", 1.5)]}
    themes_7d = {"trendingThemes": [_theme("Turismo", "turismo", 1.4)]}
    entities = {"trendingEntities": [
        _entity("Entidade Comum", volume_ratio=1.2, window_agencies=12),
    ]}
    fake_client.set_responses([themes_3d, themes_7d, entities])

    result = await detect_anomalies(fake_client)

    assert "### Tendências Normais" in result
    assert "Entidade Comum" in _section(result, "Tendências Normais")


async def test_retorna_markdown_com_secoes(fake_client):
    themes = {"trendingThemes": []}
    entities = {"trendingEntities": []}
    fake_client.set_responses([themes, themes, entities])

    result = await detect_anomalies(fake_client)

    assert "## Detector de Anomalias Comunicacionais" in result
    assert "### Picos Sustentados" in result
    assert "### Cobertura Concentrada" in result
    assert "### Tendências Normais" in result
