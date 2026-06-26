from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from utils.time_utils import parse_iso_date, timestamp_to_date_string


@dataclass(slots=True)
class CoinIdentity:
    coin_id: str
    symbol: str
    name: str
    genesis_date: date | None = None


@dataclass(slots=True)
class MarketCandidate:
    exchange_key: str
    exchange_name: str
    tv_exchange: str
    cryptocompare_exchange: str
    base: str
    quote: str
    exchange_symbol: str | None = None
    discovery_sources: set[str] = field(default_factory=set)
    volume_usd: float | None = None
    earliest_ts: int | None = None
    earliest_source: str | None = None
    hourly_gap_ratio: float | None = None
    flat_candle_ratio: float | None = None
    hourly_samples: int = 0
    volume_24h: float | None = None

    @property
    def tv_symbol(self) -> str:
        return f"{self.tv_exchange}:{self.base}{self.quote}"

    @property
    def start_date(self) -> str | None:
        return timestamp_to_date_string(self.earliest_ts)

    def merge(self, other: "MarketCandidate") -> None:
        self.discovery_sources.update(other.discovery_sources)
        if not self.exchange_symbol and other.exchange_symbol:
            self.exchange_symbol = other.exchange_symbol
        if other.volume_usd is not None:
            self.volume_usd = max(self.volume_usd or 0.0, other.volume_usd)
        if other.volume_24h is not None:
            self.volume_24h = max(self.volume_24h or 0.0, other.volume_24h)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange_key": self.exchange_key,
            "exchange_name": self.exchange_name,
            "tv_exchange": self.tv_exchange,
            "cryptocompare_exchange": self.cryptocompare_exchange,
            "base": self.base,
            "quote": self.quote,
            "exchange_symbol": self.exchange_symbol,
            "discovery_sources": sorted(self.discovery_sources),
            "volume_usd": self.volume_usd,
            "earliest_ts": self.earliest_ts,
            "earliest_source": self.earliest_source,
            "hourly_gap_ratio": self.hourly_gap_ratio,
            "flat_candle_ratio": self.flat_candle_ratio,
            "hourly_samples": self.hourly_samples,
            "volume_24h": self.volume_24h,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MarketCandidate":
        return cls(
            exchange_key=payload["exchange_key"],
            exchange_name=payload["exchange_name"],
            tv_exchange=payload["tv_exchange"],
            cryptocompare_exchange=payload["cryptocompare_exchange"],
            base=payload["base"],
            quote=payload["quote"],
            exchange_symbol=payload.get("exchange_symbol"),
            discovery_sources=set(payload.get("discovery_sources", [])),
            volume_usd=payload.get("volume_usd"),
            earliest_ts=payload.get("earliest_ts"),
            earliest_source=payload.get("earliest_source"),
            hourly_gap_ratio=payload.get("hourly_gap_ratio"),
            flat_candle_ratio=payload.get("flat_candle_ratio"),
            hourly_samples=int(payload.get("hourly_samples", 0)),
            volume_24h=payload.get("volume_24h"),
        )


@dataclass(slots=True)
class LookupResult:
    coin_name: str
    coin_symbol: str
    best: MarketCandidate
    alternatives: list[MarketCandidate]
    selection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "coin_name": self.coin_name,
            "coin_symbol": self.coin_symbol,
            "best": self.best.to_dict(),
            "alternatives": [item.to_dict() for item in self.alternatives],
            "selection_reason": self.selection_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LookupResult":
        return cls(
            coin_name=payload["coin_name"],
            coin_symbol=payload["coin_symbol"],
            best=MarketCandidate.from_dict(payload["best"]),
            alternatives=[MarketCandidate.from_dict(item) for item in payload.get("alternatives", [])],
            selection_reason=payload.get("selection_reason"),
        )


def coin_from_payload(payload: dict[str, Any]) -> CoinIdentity:
    return CoinIdentity(
        coin_id=payload["coin_id"],
        symbol=payload["symbol"],
        name=payload["name"],
        genesis_date=parse_iso_date(payload.get("genesis_date")),
    )
