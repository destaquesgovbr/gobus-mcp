from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    graphql_url: str = "http://localhost:8000/graphql"
    graphql_api_key: str = ""
    request_timeout: float = 10.0
    log_level: str = "INFO"
    # Só para desenvolvimento (o Terraform nunca define): tools gobus_dev_preview_* com as
    # fixtures dos MCP Apps e CORS para o basic-host conectar do navegador no /mcp local.
    dev_preview: bool = False
    dev_fixtures: str = ""
    cors_origins: str = ""  # origens separadas por vírgula

    model_config = SettingsConfigDict(
        env_prefix="GOBUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
