from gobus_mcp.tools.score_article import score_article


def _article(flesch=55.0, word_count=400, entities=None, agency="saude"):
    return {"article": {
        "uniqueId": "a1",
        "title": "Vacinação avança no país",
        "agency": agency,
        "agencyName": "Ministério da Saúde",
        "publishedAt": "2026-06-01T10:00:00Z",
        "features": {
            "readabilityFlesch": flesch,
            "wordCount": word_count,
            "entities": entities if entities is not None else [{"type": "ORG"}, {"type": "PER"}],
        },
    }}


def _benchmark(avg_flesch=40.0, avg_wc=420.0):
    return {"agencyAnalytics": [
        {"period": "2026-05-01", "agencyKey": "saude", "agencyName": "Ministério da Saúde",
         "articleCount": 100, "avgReadabilityFlesch": avg_flesch, "avgWordCount": avg_wc},
    ]}


async def test_score_article_retorna_nota_geral(fake_client):
    fake_client.set_responses([_article(), _benchmark()])
    result = await score_article("a1", fake_client)
    assert "Nota Geral" in result
    assert "/10" in result


async def test_flesch_alto_readability_score_alto(fake_client):
    fake_client.set_responses([_article(flesch=65.0), _benchmark()])
    result = await score_article("a1", fake_client)
    assert "**Legibilidade:** 10/10" in result


async def test_artigo_muito_longo_penaliza_conciseness(fake_client):
    # wordCount 1000 / benchmark 400 = 2.5 > 1.6 → conciseness 2
    fake_client.set_responses([
        _article(word_count=1000),
        _benchmark(avg_wc=400.0),
    ])
    result = await score_article("a1", fake_client)
    assert "**Concisão:** 2/10" in result


async def test_sem_features_retorna_aviso(fake_client):
    fake_client.set_response({"article": {
        "uniqueId": "a1", "title": "Sem features", "agency": "saude",
        "agencyName": "Ministério da Saúde", "publishedAt": "2026-06-01T10:00:00Z",
        "features": None,
    }})
    result = await score_article("a1", fake_client)
    assert "não disponíveis" in result.lower()


async def test_benchmark_agencia_incluido_no_output(fake_client):
    fake_client.set_responses([_article(), _benchmark(avg_flesch=40.0, avg_wc=420.0)])
    result = await score_article("a1", fake_client)
    assert "Benchmark" in result
    assert "40.0" in result
    assert "420" in result
