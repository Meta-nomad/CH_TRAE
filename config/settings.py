from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class Settings:
    bot_token: str
    cryptocompare_api_key: str | None
    coingecko_api_key: str | None
    cache_file: Path
    cache_ttl_seconds: int
    request_timeout_seconds: int
    max_candidates: int


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Переменная BOT_TOKEN не задана в .env")

    cache_ttl_hours = int(os.getenv("CACHE_TTL_HOURS", "24"))
    request_timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    max_candidates = int(os.getenv("MAX_CANDIDATES", "40"))

    return Settings(
        bot_token=bot_token,
        cryptocompare_api_key=os.getenv("CRYPTOCOMPARE_API_KEY", "").strip() or None,
        coingecko_api_key=os.getenv("COINGECKO_API_KEY", "").strip() or None,
        cache_file=BASE_DIR / "data" / "cache.json",
        cache_ttl_seconds=cache_ttl_hours * 3600,
        request_timeout_seconds=request_timeout_seconds,
        max_candidates=max_candidates,
    )
