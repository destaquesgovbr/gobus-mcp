from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    graphql_url: str = "http://localhost:8000/graphql"
    graphql_api_key: str = ""
    request_timeout: float = 10.0
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="GOBUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
