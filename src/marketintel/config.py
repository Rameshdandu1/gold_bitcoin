"""Environment-driven settings; live external services are OFF by default."""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Dual AI Market Intelligence"
    live_ingestion_enabled: bool = False
    ai_enabled: bool = False
    trading_enabled: bool = False

    delta_rest_url: str = "https://api.india.delta.exchange"
    delta_ws_url: str = "wss://public-socket.india.delta.exchange"
    btc_symbol: str = "BTCUSD"
    gold_symbol: str = "XAUTUSD"
    database_path: Path = Path("data/marketintel.sqlite3")
    data_max_age_seconds: int = Field(default=180, ge=15, le=3600)
    poll_seconds: int = Field(default=30, ge=10, le=600)
    min_reward_risk: float = Field(default=1.5, ge=1, le=20)
    max_ai_calls_per_day: int = Field(default=50, ge=0)

    openai_api_key: str = ""
    openai_model: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    coinglass_enabled: bool = False
    coinglass_api_key: str = ""
    coinglass_base_url: str = "https://open-api-v4.coinglass.com"

    @model_validator(mode="after")
    def block_execution(self) -> "Settings":
        if self.trading_enabled:
            raise ValueError("This research MVP must never enable TRADING_ENABLED")
        return self
