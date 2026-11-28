from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from ONEPOINT_* environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ONEPOINT_", extra="ignore")

    # Required: no default on purpose, so a missing secret fails loudly at startup.
    secret_key: str = Field(min_length=32)

    database_url: str = "sqlite:///./onepoint.db"

    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # Same constants the Android client hard-coded for its preview. The server is
    # now the single source of truth; the app's preview must match these.
    usd_to_sll: Decimal = Decimal("22.5")
    network_fee: Decimal = Decimal("0.01")  # SLL <-> SLL between mobile-money networks
    usd_fee: Decimal = Decimal("0.02")  # any conversion involving USD

    # POST /wallets/top-up credits money out of thin air. Fine for a demo/ledger
    # prototype, never for production: set to false once real funding exists.
    allow_simulated_topup: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
