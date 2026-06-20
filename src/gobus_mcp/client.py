import httpx


class GobusGraphQLError(Exception):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        msgs = "; ".join(str(e.get("message") or e) for e in errors)
        super().__init__(f"GraphQL errors: {msgs}")


class GobusGraphQLClient:
    """Thin async httpx wrapper para a GraphQL API do Destaques Gov.BR."""

    def __init__(self, url: str, api_key: str = "", timeout: float = 10.0):
        self._url = url
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = timeout

    async def execute(self, query: str, variables: dict | None = None) -> dict:
        """Executa query GraphQL e retorna data dict. Lança GobusGraphQLError em erros."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.post(self._url, json=payload, headers=self._headers)
            resp.raise_for_status()
        body = resp.json()
        if errors := body.get("errors"):
            raise GobusGraphQLError(errors)
        return body.get("data", {})
