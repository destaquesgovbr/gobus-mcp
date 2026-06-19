def draft_press_release_prompt(topic: str, agency_key: str = "", limit: int = 5) -> list[dict]:
    """Rascunho de release de imprensa baseado em artigos existentes.

    Args:
        topic: Tema ou assunto do release (ex: "emprego formal", "vacinação")
        agency_key: Filtrar por agência (opcional)
        limit: Número de artigos de referência a usar
    """
    agency_filter = f" da agência `{agency_key}`" if agency_key else ""
    return [{
        "role": "user",
        "content": {"type": "text", "text": f"""Crie um rascunho de release de imprensa sobre **{topic}**{agency_filter}.

## Roteiro de produção

### 1. Pesquisa de base
Use `search_news` com query="{topic}"{f' e agency_key="{agency_key}"' if agency_key else ''} para encontrar os {limit} artigos mais relevantes.

### 2. Aprofundamento
Para os 3 artigos mais relevantes, use `get_article` para obter o conteúdo completo.

### 3. Síntese de fatos
Extraia:
- Dados e estatísticas mencionados
- Ações governamentais anunciadas
- Declarações de autoridades
- Impactos para a população

### 4. Rascunho do release
Escreva um release de imprensa com:
- **Título**: Objetivo, máx. 15 palavras
- **Lead**: Quem, o quê, quando, onde, por quê (1 parágrafo)
- **Corpo**: Dados e contexto (2-3 parágrafos)
- **Citação**: Autoridade relevante (marque com [VERIFICAR] se inferida)
- **Notas para editores**: Fontes e contato

**Importante:** Marque todo dado não confirmado com [VERIFICAR]. Mantenha linguagem oficial, objetiva e acessível."""}
    }]
