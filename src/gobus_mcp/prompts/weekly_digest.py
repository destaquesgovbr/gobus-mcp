def weekly_digest_prompt() -> list[dict]:
    """Boletim semanal para o cidadão — o que o governo fez esta semana."""
    return [
        {
            "role": "user",
            "content": {
                "type": "text",
                "text": """Crie um boletim semanal acessível sobre o que o governo federal publicou esta semana.

## Roteiro de produção

### 1. Temas em alta
Use `gobus_detect_trends` com window_days=7 e baseline_days=28 para identificar os temas mais relevantes da semana.

### 2. Panorama da semana
Use `gobus_get_agency_summary` para as 2 ou 3 agências que mais aparecem nos temas do passo 1 e obtenha volume e temas em alta de cada uma.

### 3. Notícias representativas
Para os 3 temas em maior crescimento, use `gobus_search_news` com o nome do tema para encontrar exemplos concretos. Use `gobus_get_article` nos 2 mais relevantes de cada tema.

> **Dica de paralelismo:** Para os temas retornados por `gobus_detect_trends` (step 1),
> as chamadas `gobus_search_news` de cada tema (step 3) são independentes entre si
> e podem ser executadas em paralelo.

### 4. Boletim em linguagem cidadã
Escreva um boletim de 400-500 palavras com:

**Título:** "O que o governo fez esta semana" (com data)

**Destaques da semana:** 3-5 pontos principais em linguagem simples (nível ensino médio)

**Quem mais publicou:** As agências do passo 2 e seus temas, com 2-3 linhas cada.

**Temas emergentes:** O que está crescendo no governo esta semana e por quê pode importar para o cidadão.

**Para saber mais:** Links para os artigos mais relevantes.

**Formato:** Linguagem simples, direta, sem jargão técnico. Adequada para ser publicada em redes sociais ou newsletter.""",
            },
        }
    ]
