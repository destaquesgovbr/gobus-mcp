def weekly_digest_prompt() -> list[dict]:
    """Boletim semanal para o cidadão — o que o governo fez esta semana."""
    return [{
        "role": "user",
        "content": {"type": "text", "text": """Crie um boletim semanal acessível sobre o que o governo federal publicou esta semana.

## Roteiro de produção

### 1. Temas em alta
Use `detect_trends` com window_days=7 e baseline_days=28 para identificar os temas mais relevantes da semana.

### 2. Artigos mais vistos
Use `search_news` com query="*" (ou vazio, se aceitar) ordenado por view_count para encontrar os artigos mais populares da semana.

### 3. Notícias representativas
Para os 3 temas em maior crescimento, use `search_news` com o nome do tema para encontrar exemplos concretos. Use `get_article` nos 2 mais relevantes de cada tema.

> **Dica de paralelismo:** Para os temas retornados por `detect_trends` (step 1),
> as chamadas `search_news` de cada tema (step 3) são independentes entre si
> e podem ser executadas em paralelo.

### 4. Boletim em linguagem cidadã
Escreva um boletim de 400-500 palavras com:

**Título:** "O que o governo fez esta semana" (com data)

**Destaques da semana:** 3-5 pontos principais em linguagem simples (nível ensino médio)

**O mais visto:** Os 3 artigos que o público mais acessou, com 2-3 linhas cada.

**Temas emergentes:** O que está crescendo no governo esta semana e por quê pode importar para o cidadão.

**Para saber mais:** Links para os artigos mais relevantes.

**Formato:** Linguagem simples, direta, sem jargão técnico. Adequada para ser publicada em redes sociais ou newsletter."""}
    }]
