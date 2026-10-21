from gobus_mcp.prompts import CITE_AS_LINKS, _int_arg


def draft_press_release_prompt(topic: str, agency_key: str = "", limit: int | str = 5) -> str:
    """Rascunho de release de imprensa baseado em artigos existentes.

    Args:
        topic: Tema ou assunto do release (ex: "emprego formal", "vacinação")
        agency_key: Filtrar por agência (opcional)
        limit: Número de artigos de referência a usar (default 5; limitado a 1–20)
    """
    limit = _int_arg(limit, 5, 1, 20)
    agency_filter = f" da agência `{agency_key}`" if agency_key else ""
    return f"""Crie um rascunho de release de imprensa sobre **{topic}**{agency_filter}.

## Roteiro de produção

### 1. Pesquisa de base
Use `gobus_search_news` com query="{topic}"{f' e agency_key="{agency_key}"' if agency_key else ""} para encontrar os {limit} artigos mais relevantes.

### 2. Aprofundamento
Para os 3 artigos mais relevantes, use `gobus_get_article` para obter o conteúdo completo.

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
- **Notas para editores**: Fontes (links dos artigos usados) e contato

{CITE_AS_LINKS}

**Importante:** Marque todo dado não confirmado com [VERIFICAR]. Mantenha linguagem oficial, objetiva e acessível."""
