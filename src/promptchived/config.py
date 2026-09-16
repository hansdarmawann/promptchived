from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="PROMPTCHIVED_", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://promptchived:change-me@127.0.0.1:5432/promptchived"
    host: str = "127.0.0.1"
    port: int = 8765
    timezone: str = "Asia/Jakarta"
    embedding_model: str = "intfloat/multilingual-e5-small"
    model_cache: Path = Field(default=Path(".models"))
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16
    chunk_tokens: int = 400
    chunk_overlap: int = 50
    search_candidates: int = 100
    rrf_k: int = 60

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()

