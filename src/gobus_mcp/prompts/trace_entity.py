def trace_entity_prompt(entity_name: str, entity_type: str = "", date_from: str = "", date_to: str = "") -> list[dict]:
    """Trajetória completa de uma entidade ao longo do tempo.

    Args:
        entity_name: Nome ou alias da entidade
        entity_type: Tipo — ORG, PER, LOC, EVENT, POLICY, LAW (opcional)
        date_from: Data de início ISO (opcional)
        date_to: Data de fim ISO (opcional)
    """
    type_filter = f" do tipo {entity_type}" if entity_type else ""
    period = f" de {date_from}" if date_from else ""
    period += f" a {date_to}" if date_to else ""
    return [{
        "role": "user",
        "content": {"type": "text", "text": f"""Trace a trajetória completa de **{entity_name}**{type_filter}{period} no portal Gov.BR.

## Roteiro de análise

### 1. Identificação da entidade
Use `resolve_entity` com query="{entity_name}"{f' e entity_type="{entity_type}"' if entity_type else ''} para encontrar o ID canônico.

### 2. Perfil e cobertura temporal
Use `get_entity_profile` com o entity_name encontrado{f', date_from="{date_from}"' if date_from else ''}{f', date_to="{date_to}"' if date_to else ''} para ver a série temporal de menções.

### 3. Rede de relacionamentos
Use `get_entity_network` com o entityId canônico e depth=2 para mapear as entidades conectadas.

### 4. Artigos âncoras
Use `search_news` com o nome da entidade para encontrar as publicações mais relevantes. Use `get_article` nos 3 mais relevantes para extrair detalhes.

### 5. Linha do tempo narrativa
Com base nos dados, construa:
- **Contexto inicial:** Quando e como a entidade apareceu no portal
- **Momentos-chave:** Picos de cobertura e possíveis causas
- **Rede institucional:** Com quem/o quê a entidade aparece associada
- **Estado atual:** Tendência recente de cobertura
- **Conclusão:** Relevância desta entidade no contexto do governo federal

**Formato:** Relatório estruturado em português, com dados concretos (datas, contagens, nomes de agências)."""}
    }]
