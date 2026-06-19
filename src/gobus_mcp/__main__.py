import os

# Define FASTMCP_HOST/PORT ANTES de importar fastmcp — Settings e
# inicializado em tempo de importacao e le essas variaveis nesse momento.
# Cloud Run injeta PORT=8080; sem PORT assumimos modo stdio (sem HTTP).
_port = os.environ.get("PORT") or os.environ.get("FASTMCP_PORT")
if _port:
    os.environ.setdefault("FASTMCP_HOST", "0.0.0.0")
    os.environ.setdefault("FASTMCP_PORT", _port)

from gobus_mcp.server import main  # noqa: E402

main()
