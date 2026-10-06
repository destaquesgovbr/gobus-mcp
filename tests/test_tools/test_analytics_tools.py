import pytest

from gobus_mcp.tools.detect_trends import _TRENDING_QUERY, detect_trends
from gobus_mcp.tools.get_agency_analytics import get_agency_analytics
from tests.conftest import FakeGraphQLClient, route_catalog


class TestGetAgencyAnalytics:
    @pytest.mark.asyncio
    async def test_retorna_metricas_formatadas(self):
        client = FakeGraphQLClient()
        client.set_response(
            {
                "agencyAnalytics": [
                    {
                        "period": "2024-01",
                        "agencyKey": "mec",
                        "agencyName": "Ministério da Educação",
                        "articleCount": 45,
                        "avgSentimentScore": 0.62,
                        "pctPositive": 0.71,
                        "pctNegative": 0.08,
                        "avgReadabilityFlesch": 65.0,
                        "avgWordCount": 380.0,
                    }
                ]
            }
        )
        result = await get_agency_analytics(["mec"], "2024-01-01", "2024-01-31", client, "MONTH")
        assert "Ministério da Educação" in result
        assert "45" in result
        assert "pos" in result.lower()
        assert "médio" in result.lower()

    @pytest.mark.asyncio
    async def test_sem_dados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"agencyAnalytics": []})
        result = await get_agency_analytics(["xyz"], "2024-01-01", "2024-01-31", client)
        assert "Nenhum" in result

    @pytest.mark.asyncio
    async def test_legibilidade_exibe_score_numerico(self):
        """Flesch score numérico deve aparecer além do label."""
        client = FakeGraphQLClient()
        client.set_response(
            {
                "agencyAnalytics": [
                    {
                        "period": "2026-06",
                        "agencyKey": "mec",
                        "agencyName": "MEC",
                        "articleCount": 10,
                        "avgSentimentScore": 0.1,
                        "pctPositive": 0.3,
                        "pctNegative": 0.1,
                        "avgReadabilityFlesch": 72.5,
                        "avgWordCount": 380.0,
                    }
                ]
            }
        )
        result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
        assert "72.5" in result
        assert "médio" in result.lower()  # faixa única 50–75 (antes: "fácil" acima de 70)

    @pytest.mark.asyncio
    async def test_exibe_pct_negativo(self):
        """pctNegative deve aparecer no output."""
        client = FakeGraphQLClient()
        client.set_response(
            {
                "agencyAnalytics": [
                    {
                        "period": "2026-06",
                        "agencyKey": "mec",
                        "agencyName": "MEC",
                        "articleCount": 10,
                        "avgSentimentScore": 0.1,
                        "pctPositive": 0.3,
                        "pctNegative": 0.12,
                        "avgReadabilityFlesch": 65.0,
                        "avgWordCount": 300.0,
                    }
                ]
            }
        )
        result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
        assert "12%" in result or "neg" in result.lower()

    @pytest.mark.asyncio
    async def test_exibe_avg_word_count(self):
        """avgWordCount deve aparecer no output."""
        client = FakeGraphQLClient()
        client.set_response(
            {
                "agencyAnalytics": [
                    {
                        "period": "2026-06",
                        "agencyKey": "mec",
                        "agencyName": "MEC",
                        "articleCount": 10,
                        "avgSentimentScore": 0.1,
                        "pctPositive": 0.3,
                        "pctNegative": 0.05,
                        "avgReadabilityFlesch": 65.0,
                        "avgWordCount": 420.0,
                    }
                ]
            }
        )
        result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
        assert "420" in result


THEMES = [
    {
        # w=42 em 7 dias; baseline (28 dias, inclui a janela) = 3,0/dia → b_prev = 42
        "themeLabel": "Saúde",
        "themeCode": None,
        "windowCount": 42,
        "baselineDailyAvg": 3.0,
        "growthScore": 2.0,
        "topArticles": [
            {
                "uniqueId": "a1",
                "title": "T1",
                "agencyName": "Ministério da Saúde",
                "publishedAt": "2026-06-01",
                "trendingScore": None,
            },
            {
                "uniqueId": "a2",
                "title": "T2",
                "agencyName": "SECOM",
                "publishedAt": "2026-06-02",
                "trendingScore": None,
            },
        ],
    },
    {
        # baseline = só a janela: tema novo
        "themeLabel": "Educação",
        "themeCode": None,
        "windowCount": 21,
        "baselineDailyAvg": 0.75,
        "growthScore": 4.0,
        "topArticles": [],
    },
]


def _route_trends(client, themes, *, classified=900, total=1000):
    route_catalog(client)
    client.route("TrendingThemes", {"trendingThemes": themes})
    client.route(
        "ThemeCoverage",
        {
            "topThemes": [{"label": "Saúde", "count": classified}] if classified else [],
            "analyticsKpis": {"total": total},
        },
    )
    return client


class TestDetectTrends:
    async def test_pede_baseline_e_converte_o_limiar(self, fake_client):
        _route_trends(fake_client, THEMES)

        await detect_trends(fake_client, growth_threshold=1.5)

        assert "baselineDailyAvg" in _TRENDING_QUERY
        (variables,) = fake_client.calls("TrendingThemes")
        assert variables["growthThreshold"] == pytest.approx(1.3333, abs=1e-4)
        assert variables["windowDays"] == 7 and variables["baselineDays"] == 28

    async def test_nunca_envia_limiar_zero(self, fake_client):
        _route_trends(fake_client, THEMES)

        result = await detect_trends(fake_client, growth_threshold=0)

        (variables,) = fake_client.calls("TrendingThemes")
        assert variables["growthThreshold"] >= 1.0
        assert "1.0×" in result

    async def test_mostra_razao_sem_sobreposicao_e_growth_da_api(self, fake_client):
        _route_trends(fake_client, THEMES)

        result = await detect_trends(fake_client)

        saude = next(line for line in result.splitlines() if "Saúde" in line)
        assert "3.0×" in saude  # razão real ((42+1)/7)/((42+1)/21)
        assert "2.0" in saude  # growthScore da API (baseline sobreposto)
        educacao = next(line for line in result.splitlines() if "Educação" in line)
        assert "novo" in educacao.lower()

    async def test_exibe_agencias_e_artigos_por_tema(self, fake_client):
        _route_trends(fake_client, THEMES)

        result = await detect_trends(fake_client)

        assert "Ministério da Saúde" in result and "SECOM" in result
        assert "T1" in result and "`a1`" in result

    async def test_sem_temas_com_cobertura_baixa_avisa_indisponivel(self, fake_client):
        _route_trends(fake_client, [], classified=0, total=930)

        result = await detect_trends(fake_client)

        assert "Nenhum tema em crescimento" not in result
        assert "Temas: indisponível" in result
        assert "26/09/2026" in result

    async def test_sem_temas_com_cobertura_ok(self, fake_client):
        _route_trends(fake_client, [])

        result = await detect_trends(fake_client)

        assert "Nenhum tema em crescimento" in result

    async def test_agency_key_validado_e_passado(self, fake_client):
        _route_trends(fake_client, [])

        await detect_trends(fake_client, agency_key="saude")
        bad = await detect_trends(fake_client, agency_key="ms")

        (variables,) = fake_client.calls("TrendingThemes")
        assert variables["agencyKey"] == "saude"
        assert "saude" in bad  # sugestão, sem nova consulta

    async def test_baseline_menor_que_janela_e_erro(self, fake_client):
        _route_trends(fake_client, THEMES)

        result = await detect_trends(fake_client, window_days=28, baseline_days=7)

        assert "baseline_days" in result
        assert fake_client.calls("TrendingThemes") == []


# ── null ≠ 0, faixa única, nomes do catálogo e validação ────────────────────


def _metrics(**overrides):
    row = {
        "period": "2026-09-01 00:00:00+00",
        "agencyKey": "mec",
        "agencyName": "MEC",
        "articleCount": 10,
        "avgSentimentScore": 0.1,
        "pctPositive": 0.3,
        "pctNegative": 0.1,
        "avgReadabilityFlesch": 40.0,
        "avgWordCount": 380.0,
    }
    row.update(overrides)
    return row


def _route_analytics(client, rows):
    route_catalog(client)
    client.route("AgencyAnalytics", {"agencyAnalytics": rows})
    return client


async def test_analytics_sentimento_nulo_fica_indisponivel_sem_pct_zero(fake_client):
    _route_analytics(fake_client, [_metrics(avgSentimentScore=None, pctPositive=0.0)])

    result = await get_agency_analytics(["mec"], "2026-09-01", "2026-09-30", fake_client)

    assert "sentimento indisponível" in result
    assert "0% pos" not in result


async def test_analytics_flesch_e_palavras_nulos_ficam_indisponiveis(fake_client):
    _route_analytics(fake_client, [_metrics(avgReadabilityFlesch=None, avgWordCount=None)])

    result = await get_agency_analytics(["mec"], "2026-09-01", "2026-09-30", fake_client)

    assert "legibilidade indisponível" in result
    assert "0.0" not in result
    assert "Legibilidade (Flesch): indisponível" in result  # aviso de dado no topo


@pytest.mark.parametrize(
    ("flesch", "expected"),
    [(72.5, "72.5 (médio)"), (-5.0, "0.0 (muito difícil; valor bruto -5.0)"), (0.0, "0.0")],
)
async def test_analytics_flesch_na_faixa_unica(fake_client, flesch, expected):
    _route_analytics(fake_client, [_metrics(avgReadabilityFlesch=flesch)])

    result = await get_agency_analytics(["mec"], "2026-09-01", "2026-09-30", fake_client)

    assert f"legibilidade {expected}" in result


async def test_analytics_nomes_do_catalogo_e_periodo_formatado(fake_client):
    _route_analytics(fake_client, [_metrics()])

    result = await get_agency_analytics(["mec"], "2026-09-01", "2026-09-30", fake_client)

    assert "Ministério da Educação" in result
    assert "## 2026-09-01" in result
    assert "00:00:00" not in result


async def test_analytics_sem_dados_sugere_codigo(fake_client):
    _route_analytics(fake_client, [])

    result = await get_agency_analytics(["ms"], "2026-09-01", "2026-09-30", fake_client)

    assert "saude" in result


def test_docstring_usa_codigos_validos():
    assert '"ms"' not in get_agency_analytics.__doc__
    assert '"saude"' in get_agency_analytics.__doc__


@pytest.mark.parametrize(
    ("granularity", "sent_to"),
    [("MONTH", "2026-10-01"), ("week", "2026-10-01"), ("DAY", "2026-09-30")],
)
async def test_analytics_date_to_inclusivo_em_toda_granularidade(fake_client, granularity, sent_to):
    # MONTH/WEEK: a API trata dateTo como exclusivo (00:00) → a tool soma 1 dia
    _route_analytics(fake_client, [_metrics()])

    result = await get_agency_analytics(
        ["mec"], "2026-09-01", "2026-09-30", fake_client, granularity
    )

    (call,) = fake_client.calls("AgencyAnalytics")
    assert (call["dateFrom"], call["dateTo"]) == ("2026-09-01", sent_to)
    assert "2026-09-01 → 2026-09-30" in result  # o cabeçalho mostra o período pedido


async def test_analytics_date_to_invalida_segue_para_a_api(fake_client):
    _route_analytics(fake_client, [])

    await get_agency_analytics(["mec"], "2026-09-01", "30/09/2026", fake_client)

    (call,) = fake_client.calls("AgencyAnalytics")
    assert call["dateTo"] == "30/09/2026"
