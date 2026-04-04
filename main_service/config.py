from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_dns: str

    model_config = SettingsConfigDict(
        env_file="main_service/.env",
        env_file_encoding="utf-8"
    )

settings = Settings()