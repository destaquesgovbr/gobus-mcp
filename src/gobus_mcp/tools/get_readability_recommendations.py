import datetime

from gobus_mcp.client import GobusGraphQLClient

_ACTIVE_AGENCIES = [
    "agencia_brasil", "secom", "saude", "mec", "fazenda", "trabalho", "mj",
    "defesa", "mre", "planejamento", "cgcom", "cgu", "agu", "tcu", "planalto",
    "mcom", "ibge", "anp", "inss", "caixa",
]

_ANALYTICS_QUERY = """
query AgencyAnalytics(
    $agencies: [String!]!
    $dateFrom: String!
    $dateTo: String!
    $granularity: Granularity!
) {
    agencyAnalytics(
        agencies: $agencies
        dateFrom: $dateFrom
        dateTo: $dateTo
        granularity: $granularity
    ) {
        period
        agencyKey
        agencyName
        articleCount
        avgReadabilityFlesch
        avgWordCount
    }
}
"""

_SEARCH_QUERY = """
query SearchNews($query: String!, $agencies: [String!]!, $limit: Int!) {
    search(query: $query, filter: {agencies: $agencies}, limit: $limit) {
        articles {
            uniqueId
            title
            agencyName
            agency
            publishedAt
            summary
            url
            features { trendingScore viewCount }
        }
        found
        page
    }
}
"""


def _flesch_label(flesch: float) -> str:
    """Classifica o índice Flesch em nível de dificuldade de leitura."""
    if flesch < 0:
        return "⚠️ abaixo do piso"
    elif flesch < 25:
        return "muito difícil"
    elif flesch < 50:
        return "difícil"
    elif flesch < 75:
        return "médio"
    else:
        return "fácil"


def _recommendations(flesch: float) -> list[str]:
    """Gera 3 recomendações de estilo priorizadas pelo nível Flesch."""
    if flesch < 0:
        return [
            "1. **Quebrar parágrafos longos:** Limite cada parágrafo a 3 frases. Frases longas são o principal fator negativo no índice Flesch.",
            "2. **Substituir jargão técnico:** Identifique termos técnicos obrigatórios e adicione explicações entre parênteses na primeira ocorrência.",
            "3. **Voz ativa:** Converta orações na voz passiva para voz ativa — reduz o número de sílabas e aumenta a clareza.",
        ]
    elif flesch < 25:
        return [
            "1. **Reduzir comprimento das frases:** Meta: máximo 20 palavras por frase. Cada ponto final melhora o Flesch.",
            "2. **Palavras simples:** Prefira 'fazer' a 'realizar', 'ver' a 'verificar', 'dizer' a 'declarar'.",
            "3. **Lead direto:** Coloque a informação principal na primeira frase — o quê, quem, quando.",
        ]
    elif flesch < 50:
        return [
            "1. **Frases mais curtas:** Você está próximo da meta ≥50. Divida frases com mais de 25 palavras.",
            "2. **Vocabulário acessível:** Revise os 10 termos mais frequentes e substitua os mais complexos.",
            "3. **Revisão para cidadão:** Teste seu texto com um leitor sem formação técnica antes de publicar.",
        ]
    else:
        return [
            "1. **Mantenha o padrão:** Seu índice já atinge a meta (≥50). Continue priorizando frases curtas.",
            "2. **Consistência:** Garanta que todos os comunicadores sigam o mesmo guia de estilo.",
            "3. **Monitore regressões:** Acompanhe o Flesch mensalmente — publicações técnicas tendem a puxar o índice para baixo.",
        ]


async def get_readability_recommendations(
    agency_key: str | None,
    client: GobusGraphQLClient,
    days: int = 90,
    limit: int = 10,
) -> str:
    """Diagnóstico de legibilidade por agência com recomendações de estilo.

    Args:
        agency_key: Chave da agência (ex: "cgu") — se None, retorna ranking geral.
        client: Cliente GraphQL.
        days: Janela de análise em dias (default 90).
        limit: Máximo de agências no ranking geral (default 10).

    Returns:
        Markdown com ranking geral OU diagnóstico da agência + 3 recomendações.
    """
    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=days)).isoformat()
    date_to = today.isoformat()

    if not agency_key:
        # ── Modo ranking geral ─────────────────────────────────────────────────
        data = await client.execute(_ANALYTICS_QUERY, {
            "agencies": _ACTIVE_AGENCIES,
            "dateFrom": date_from,
            "dateTo": date_to,
            "granularity": "MONTH",
        })
        rows = data.get("agencyAnalytics") or []

        if not rows:
            return "Nenhum dado de legibilidade encontrado para o período."

        # Agrupa por agência (média ponderada por artigos quando há múltiplos períodos)
        by_agency: dict[str, dict] = {}
        for row in rows:
            key = row.get("agencyKey") or ""
            if key not in by_agency:
                by_agency[key] = {
                    "agencyName": row.get("agencyName") or key,
                    "totalArticles": 0,
                    "fleschSum": 0.0,
                }
            count = row.get("articleCount") or 0
            flesch = row.get("avgReadabilityFlesch") or 0.0
            by_agency[key]["totalArticles"] += count
            by_agency[key]["fleschSum"] += flesch * count

        ranked = []
        for key, agg in by_agency.items():
            total = agg["totalArticles"]
            avg_flesch = agg["fleschSum"] / total if total > 0 else 0.0
            ranked.append({
                "agencyName": agg["agencyName"],
                "flesch": avg_flesch,
                "count": total,
            })

        ranked.sort(key=lambda r: r["flesch"], reverse=True)
        ranked = ranked[:limit]

        lines = [
            f"# Ranking de Legibilidade (últimos {days} dias)\n",
            "| # | Agência | Flesch | Nível | Artigos |",
            "|---|---------|--------|-------|---------|",
        ]
        for i, item in enumerate(ranked, 1):
            label = _flesch_label(item["flesch"])
            lines.append(
                f"| {i} | {item['agencyName']} | {item['flesch']:.1f} | {label} | {item['count']} |"
            )

        lines.append("\n**Meta:** ≥50 para serviço ao cidadão · ≥30 para institucional")
        lines.append("**Benchmark interno:** Agência Brasil (~33.5) — melhor índice atual entre as agências.")
        return "\n".join(lines)

    else:
        # ── Modo diagnóstico de agência específica ─────────────────────────────
        analytics_data = await client.execute(_ANALYTICS_QUERY, {
            "agencies": [agency_key],
            "dateFrom": date_from,
            "dateTo": date_to,
            "granularity": "MONTH",
        })
        rows = analytics_data.get("agencyAnalytics") or []

        articles_data = await client.execute(_SEARCH_QUERY, {
            "query": "",
            "agencies": [agency_key],
            "limit": 3,
        })
        articles = (articles_data.get("search") or {}).get("articles") or []

        if not rows:
            return (
                f"Sem dados para a agência `{agency_key}` nos últimos {days} dias. "
                "Verifique a chave da agência ou tente um período maior."
            )

        # Agrega múltiplos períodos em um único valor médio
        total_count = sum(r.get("articleCount") or 0 for r in rows)
        if total_count > 0:
            flesch = sum(
                (r.get("avgReadabilityFlesch") or 0.0) * (r.get("articleCount") or 0)
                for r in rows
            ) / total_count
            avg_wc = sum(
                (r.get("avgWordCount") or 0.0) * (r.get("articleCount") or 0)
                for r in rows
            ) / total_count
        else:
            flesch = rows[0].get("avgReadabilityFlesch") or 0.0
            avg_wc = rows[0].get("avgWordCount") or 0.0

        name = rows[0].get("agencyName") or agency_key
        label = _flesch_label(flesch)

        lines = [
            f"# Diagnóstico de Legibilidade: {name}\n",
            f"**Flesch médio:** {flesch:.1f} ({label}) · "
            f"**Artigos analisados:** {total_count} · "
            f"**Palavras/artigo:** {avg_wc:.0f}\n",
        ]

        if articles:
            lines.append("## Artigos de Exemplo\n")
            for art in articles[:3]:
                title = art.get("title", "Sem título")
                date = (art.get("publishedAt") or "")[:10]
                url = art.get("url", "")
                lines.append(f"- [{title}]({url}) — {date}")
            lines.append("")

        lines.append("## Recomendações de Estilo\n")
        lines.extend(_recommendations(flesch))

        return "\n".join(lines)
