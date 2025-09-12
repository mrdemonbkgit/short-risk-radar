import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        self.app_name: str = os.getenv("APP_NAME", "short-risk-radar")
        self.env: str = os.getenv("ENV", "development")
        self.api_host: str = os.getenv("API_HOST", "0.0.0.0")
        self.api_port: int = int(os.getenv("API_PORT", "8000"))
        self.next_public_api_base: str = os.getenv("NEXT_PUBLIC_API_BASE", "http://localhost:8000")

        # External services
        self.redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.postgres_dsn: str = (
            f"postgresql+psycopg2://{os.getenv('POSTGRES_USER','postgres')}:{os.getenv('POSTGRES_PASSWORD','postgres')}@"
            f"{os.getenv('POSTGRES_HOST','localhost')}:{os.getenv('POSTGRES_PORT','5432')}/{os.getenv('POSTGRES_DB','short_risk')}"
        )

        # Exchange APIs
        self.binance_base_url: str = os.getenv("BINANCE_BASE_URL", "https://fapi.binance.com")
        self.binance_spot_base_url: str = os.getenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com")

        # Sampling intervals
        self.collect_interval_sec: int = int(os.getenv("COLLECT_INTERVAL_SEC", "10"))
        self.oi_refresh_sec: int = int(os.getenv("OI_REFRESH_SEC", "300"))
        self.funding_refresh_sec: int = int(os.getenv("FUNDING_REFRESH_SEC", "3600"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
