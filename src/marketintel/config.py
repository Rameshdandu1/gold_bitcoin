"""Environment-driven settings; live external services are OFF by default."""

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Dual AI Market Intelligence"
    live_ingestion_enabled: bool = False
    ai_enabled: bool = False
    trading_enabled: bool = False
    alerts_enabled: bool = False

    delta_rest_url: str = "https://api.india.delta.exchange"
    delta_ws_url: str = "wss://public-socket.india.delta.exchange"
    btc_symbol: str = "BTCUSD"
    gold_symbol: str = "XAUTUSD"
    database_path: Path = Path("data/marketintel.sqlite3")
    data_max_age_seconds: int = Field(default=180, ge=15, le=3600)
    delta_book_max_age_seconds: float = Field(default=10, ge=1, le=120)
    delta_discovery_refresh_seconds: int = Field(default=300, ge=30, le=3600)
    delta_discovery_max_age_seconds: int = Field(default=900, ge=30, le=86400)
    delta_reconciliation_max_age_seconds: int = Field(default=180, ge=15, le=3600)
    poll_seconds: int = Field(default=30, ge=10, le=600)
    min_reward_risk: float = Field(default=1.5, ge=1, le=20)
    max_ai_calls_per_day: int = Field(default=50, ge=0)
    ai_total_deadline_seconds: int = Field(default=90, ge=5, le=600)
    ai_attempt_timeout_seconds: float = Field(default=25, ge=1, le=120)
    ai_queue_max_age_seconds: int = Field(default=120, ge=5, le=3600)
    ai_job_lease_seconds: int = Field(default=120, ge=30, le=900)
    ai_max_attempts_per_provider: int = Field(default=2, ge=1, le=5)
    ai_max_output_tokens: int = Field(default=650, ge=64, le=4096)
    ai_max_input_tokens: int = Field(default=30_000, ge=1000, le=200_000)
    ai_provider_call_limit_per_day: int = Field(default=25, ge=0)
    ai_total_call_limit_per_day: int = Field(default=50, ge=0)
    ai_total_cost_limit_microusd_per_day: int = Field(default=0, ge=0)
    openai_input_microusd_per_million_tokens: int | None = Field(default=None, ge=0)
    openai_output_microusd_per_million_tokens: int | None = Field(default=None, ge=0)
    anthropic_input_microusd_per_million_tokens: int | None = Field(default=None, ge=0)
    anthropic_output_microusd_per_million_tokens: int | None = Field(default=None, ge=0)
    risk_fee_bps: str = ""
    risk_slippage_bps: str = ""
    risk_maximum_entry_drift_bps: str = "10"
    risk_maximum_spread_bps: str = "10"
    risk_minimum_net_reward_risk: str = "1.5"

    openai_api_key: str = ""
    openai_model: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    operator_auth_enabled: bool = True
    operator_username: str = ""
    operator_password: SecretStr = SecretStr("")
    cors_allowed_origins_csv: str = "http://127.0.0.1:5173,http://localhost:5173"
    slack_bot_token: SecretStr = SecretStr("")
    slack_channel_id: str = ""
    alert_max_attempts: int = Field(default=3, ge=1, le=10)
    alert_lease_seconds: int = Field(default=30, ge=5, le=300)
    coinglass_enabled: bool = False
    coinglass_api_key: str = ""
    coinglass_base_url: str = "https://open-api-v4.coinglass.com"
    coinglass_plan: str = Field(
        default="HOBBYIST", pattern="^(HOBBYIST|STARTUP|STANDARD|PROFESSIONAL|ENTERPRISE)$"
    )

    @model_validator(mode="after")
    def block_execution(self) -> "Settings":
        if self.trading_enabled:
            raise ValueError("This research MVP must never enable TRADING_ENABLED")
        return self
