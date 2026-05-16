from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    db_user: str = "arb"
    db_password: str = "arb_secret"
    db_name: str = "ultra_arb"
    db_host: str = "localhost"
    db_port: int = 5432
    database_url: str = "postgresql+asyncpg://arb:arb_secret@localhost:5432/ultra_arb"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""

    # Trading mode
    paper_trade: bool = True

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True

    # Bybit
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_testnet: bool = True

    # Polymarket
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""
    polymarket_private_key: str = ""
    polymarket_sandbox: bool = True

    # Risk limits
    max_drawdown_pct: float = 2.0
    max_position_pct: float = 2.5
    max_concurrent_positions: int = 5
    vol_breaker_multiplier: float = 3.0

    # Web / deployment
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_api_url: str = ""  # used in OpenAPI docs / frontend builds

    # Financial Datasets (optional)
    financial_datasets_api_key: str = ""


settings = Settings()
