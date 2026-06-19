from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    tg_api_id: int
    tg_api_hash: str
    tg_session_path: str = "session/userbot.session"

    chatwoot_base_url: str
    chatwoot_api_token: str
    chatwoot_account_id: int
    chatwoot_inbox_id: int

    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000

    database_path: str = "data/mappings.db"


settings = Settings()
