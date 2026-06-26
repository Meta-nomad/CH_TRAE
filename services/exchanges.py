from __future__ import annotations

import asyncio
from abc import ABC
from datetime import datetime, timezone
from typing import Any

from services.http import HTTPClient, HTTPClientError
from utils.models import MarketCandidate
from utils.normalization import DEFAULT_QUOTES, canonicalize_exchange_name, normalize_asset_symbol
from utils.time_utils import timestamp_to_iso8601, utc_day_start


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BaseExchangeAdapter(ABC):
    exchange_key: str
    exchange_name: str
    tv_exchange: str
    cryptocompare_exchange: str

    def __init__(self, http: HTTPClient) -> None:
        self.http = http
        self._pairs_cache: list[tuple[str, str, str]] | None = None
        self._cache_lock = asyncio.Lock()

    async def discover_pairs(self, base: str, quotes: tuple[str, ...] = DEFAULT_QUOTES) -> list[MarketCandidate]:
        supported_pairs = await self._load_pairs()
        normalized_quotes = set(quotes)
        results: list[MarketCandidate] = []
        for pair_base, pair_quote, exchange_symbol in supported_pairs:
            if pair_base != base or pair_quote not in normalized_quotes:
                continue
            results.append(
                MarketCandidate(
                    exchange_key=self.exchange_key,
                    exchange_name=self.exchange_name,
                    tv_exchange=self.tv_exchange,
                    cryptocompare_exchange=self.cryptocompare_exchange,
                    base=pair_base,
                    quote=pair_quote,
                    exchange_symbol=exchange_symbol,
                    discovery_sources={"exchange_api"},
                )
            )
        return results

    async def _load_pairs(self) -> list[tuple[str, str, str]]:
        async with self._cache_lock:
            if self._pairs_cache is None:
                self._pairs_cache = await self.fetch_pairs()
            return self._pairs_cache

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        return []

    async def get_earliest_daily(self, candidate: MarketCandidate) -> int | None:
        return None

    async def get_hourly_segment(
        self,
        candidate: MarketCandidate,
        start_ts: int,
        hours: int = 24 * 14,
    ) -> list[dict[str, float]]:
        return []

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        return None


class BinanceAdapter(BaseExchangeAdapter):
    exchange_key = "binance"
    exchange_name = "Binance"
    tv_exchange = "BINANCE"
    cryptocompare_exchange = "Binance"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api.binance.com/api/v3/exchangeInfo", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload.get("symbols", []):
            if item.get("status") != "TRADING":
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("baseAsset", "")),
                    normalize_asset_symbol(item.get("quoteAsset", "")),
                    item.get("symbol", ""),
                )
            )
        return pairs

    async def get_earliest_daily(self, candidate: MarketCandidate) -> int | None:
        try:
            payload = await self.http.get_json(
                "https://api.binance.com/api/v3/klines",
                params={
                    "symbol": candidate.exchange_symbol,
                    "interval": "1d",
                    "limit": 1,
                    "startTime": 0,
                },
            )
        except HTTPClientError:
            return None
        if not payload:
            return None
        return int(payload[0][0] / 1000)

    async def get_hourly_segment(self, candidate: MarketCandidate, start_ts: int, hours: int = 24 * 14) -> list[dict[str, float]]:
        try:
            payload = await self.http.get_json(
                "https://api.binance.com/api/v3/klines",
                params={
                    "symbol": candidate.exchange_symbol,
                    "interval": "1h",
                    "limit": min(hours, 1000),
                    "startTime": start_ts * 1000,
                },
            )
        except HTTPClientError:
            return []
        candles: list[dict[str, float]] = []
        for row in payload:
            candles.append(
                {
                    "timestamp": int(row[0] / 1000),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[7]),
                }
            )
        return candles

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": candidate.exchange_symbol},
            )
        except HTTPClientError:
            return None
        return _safe_float(payload.get("quoteVolume"))


class MEXCAdapter(BinanceAdapter):
    exchange_key = "mexc"
    exchange_name = "MEXC"
    tv_exchange = "MEXC"
    cryptocompare_exchange = "MEXC"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api.mexc.com/api/v3/exchangeInfo", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload.get("symbols", []):
            if item.get("status") != "1" and item.get("status") != "TRADING":
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("baseAsset", "")),
                    normalize_asset_symbol(item.get("quoteAsset", "")),
                    item.get("symbol", ""),
                )
            )
        return pairs

    async def get_earliest_daily(self, candidate: MarketCandidate) -> int | None:
        try:
            payload = await self.http.get_json(
                "https://api.mexc.com/api/v3/klines",
                params={
                    "symbol": candidate.exchange_symbol,
                    "interval": "1d",
                    "limit": 1,
                    "startTime": 0,
                },
            )
        except HTTPClientError:
            return None
        if not payload:
            return None
        return int(payload[0][0] / 1000)

    async def get_hourly_segment(self, candidate: MarketCandidate, start_ts: int, hours: int = 24 * 14) -> list[dict[str, float]]:
        try:
            payload = await self.http.get_json(
                "https://api.mexc.com/api/v3/klines",
                params={
                    "symbol": candidate.exchange_symbol,
                    "interval": "1h",
                    "limit": min(hours, 1000),
                    "startTime": start_ts * 1000,
                },
            )
        except HTTPClientError:
            return []
        candles: list[dict[str, float]] = []
        for row in payload:
            candles.append(
                {
                    "timestamp": int(row[0] / 1000),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[7]),
                }
            )
        return candles

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                "https://api.mexc.com/api/v3/ticker/24hr",
                params={"symbol": candidate.exchange_symbol},
            )
        except HTTPClientError:
            return None
        return _safe_float(payload.get("quoteVolume"))


class BitfinexAdapter(BaseExchangeAdapter):
    exchange_key = "bitfinex"
    exchange_name = "Bitfinex"
    tv_exchange = "BITFINEX"
    cryptocompare_exchange = "Bitfinex"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange", retries=3)
        raw_pairs = payload[0] if payload else []
        pairs: list[tuple[str, str, str]] = []
        quote_order = sorted(DEFAULT_QUOTES, key=len, reverse=True)
        for item in raw_pairs:
            pair = str(item)
            normalized = pair.replace(":", "")
            for quote in quote_order:
                if normalized.endswith(quote):
                    base = normalize_asset_symbol(normalized[: -len(quote)])
                    if not base:
                        continue
                    pairs.append((base, quote, pair))
                    break
        return pairs

    def _api_symbol(self, exchange_symbol: str) -> str:
        return f"t{exchange_symbol}"

    async def get_earliest_daily(self, candidate: MarketCandidate) -> int | None:
        try:
            payload = await self.http.get_json(
                f"https://api-pub.bitfinex.com/v2/candles/trade:1D:{self._api_symbol(candidate.exchange_symbol or '')}/hist",
                params={"limit": 1, "sort": 1},
            )
        except HTTPClientError:
            return None
        if not payload:
            return None
        return int(payload[0][0] / 1000)

    async def get_hourly_segment(self, candidate: MarketCandidate, start_ts: int, hours: int = 24 * 14) -> list[dict[str, float]]:
        try:
            payload = await self.http.get_json(
                f"https://api-pub.bitfinex.com/v2/candles/trade:1h:{self._api_symbol(candidate.exchange_symbol or '')}/hist",
                params={"limit": min(hours, 1000), "sort": 1, "start": start_ts * 1000},
            )
        except HTTPClientError:
            return []
        candles: list[dict[str, float]] = []
        for row in payload:
            candles.append(
                {
                    "timestamp": int(row[0] / 1000),
                    "open": float(row[1]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "close": float(row[2]),
                    "volume": float(row[5]),
                }
            )
        return candles

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                f"https://api-pub.bitfinex.com/v2/ticker/{self._api_symbol(candidate.exchange_symbol or '')}"
            )
        except HTTPClientError:
            return None
        if not payload or len(payload) < 8:
            return None
        return _safe_float(payload[7])


class BitstampAdapter(BaseExchangeAdapter):
    exchange_key = "bitstamp"
    exchange_name = "Bitstamp"
    tv_exchange = "BITSTAMP"
    cryptocompare_exchange = "Bitstamp"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://www.bitstamp.net/api/v2/trading-pairs-info/", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload:
            name = item.get("name", "")
            if "/" not in name:
                continue
            base, quote = name.split("/", 1)
            pairs.append((normalize_asset_symbol(base), normalize_asset_symbol(quote), item.get("url_symbol", "")))
        return pairs

    async def _has_daily_data(self, symbol: str, day_ts: int) -> bool:
        try:
            payload = await self.http.get_json(
                f"https://www.bitstamp.net/api/v2/ohlc/{symbol}/",
                params={"step": 86400, "limit": 1, "start": day_ts, "end": day_ts + 86400},
            )
        except HTTPClientError:
            return False
        return bool(((payload or {}).get("data") or {}).get("ohlc"))

    async def get_earliest_daily(self, candidate: MarketCandidate) -> int | None:
        symbol = candidate.exchange_symbol or ""
        low = utc_day_start(1262304000)
        high = utc_day_start(int(datetime.now(tz=timezone.utc).timestamp()))
        earliest: int | None = None
        while low <= high:
            mid = utc_day_start(((low + high) // 2))
            exists = await self._has_daily_data(symbol, mid)
            if exists:
                earliest = mid
                high = mid - 86400
            else:
                low = mid + 86400
        return earliest

    async def get_hourly_segment(self, candidate: MarketCandidate, start_ts: int, hours: int = 24 * 14) -> list[dict[str, float]]:
        try:
            payload = await self.http.get_json(
                f"https://www.bitstamp.net/api/v2/ohlc/{candidate.exchange_symbol or ''}/",
                params={"step": 3600, "limit": min(hours, 1000), "start": start_ts, "end": start_ts + hours * 3600},
            )
        except HTTPClientError:
            return []
        rows = (((payload or {}).get("data") or {}).get("ohlc")) or []
        candles: list[dict[str, float]] = []
        for row in rows:
            candles.append(
                {
                    "timestamp": int(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
        candles.sort(key=lambda item: item["timestamp"])
        return candles

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                f"https://www.bitstamp.net/api/v2/ticker/{candidate.exchange_symbol or ''}/"
            )
        except HTTPClientError:
            return None
        return _safe_float(payload.get("volume"))


class CoinbaseAdapter(BaseExchangeAdapter):
    exchange_key = "coinbase"
    exchange_name = "Coinbase"
    tv_exchange = "COINBASE"
    cryptocompare_exchange = "Coinbase"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api.exchange.coinbase.com/products", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload:
            if item.get("status") != "online":
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("base_currency", "")),
                    normalize_asset_symbol(item.get("quote_currency", "")),
                    item.get("id", ""),
                )
            )
        return pairs

    async def _has_daily_data(self, product_id: str, day_ts: int) -> bool:
        try:
            payload = await self.http.get_json(
                f"https://api.exchange.coinbase.com/products/{product_id}/candles",
                params={
                    "granularity": 86400,
                    "start": timestamp_to_iso8601(day_ts),
                    "end": timestamp_to_iso8601(day_ts + 86400),
                },
            )
        except HTTPClientError:
            return False
        return bool(payload)

    async def get_earliest_daily(self, candidate: MarketCandidate) -> int | None:
        product_id = candidate.exchange_symbol or ""
        low = utc_day_start(1325376000)
        high = utc_day_start(int(datetime.now(tz=timezone.utc).timestamp()))
        earliest: int | None = None
        while low <= high:
            mid = utc_day_start((low + high) // 2)
            exists = await self._has_daily_data(product_id, mid)
            if exists:
                earliest = mid
                high = mid - 86400
            else:
                low = mid + 86400
        return earliest

    async def get_hourly_segment(self, candidate: MarketCandidate, start_ts: int, hours: int = 24 * 14) -> list[dict[str, float]]:
        chunks: list[dict[str, float]] = []
        current = start_ts
        remaining = hours
        while remaining > 0:
            chunk_hours = min(remaining, 300)
            try:
                payload = await self.http.get_json(
                    f"https://api.exchange.coinbase.com/products/{candidate.exchange_symbol or ''}/candles",
                    params={
                        "granularity": 3600,
                        "start": timestamp_to_iso8601(current),
                        "end": timestamp_to_iso8601(current + chunk_hours * 3600),
                    },
                )
            except HTTPClientError:
                break
            for row in payload:
                chunks.append(
                    {
                        "timestamp": int(row[0]),
                        "low": float(row[1]),
                        "high": float(row[2]),
                        "open": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                )
            current += chunk_hours * 3600
            remaining -= chunk_hours
        chunks.sort(key=lambda item: item["timestamp"])
        return chunks

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                f"https://api.exchange.coinbase.com/products/{candidate.exchange_symbol or ''}/stats"
            )
        except HTTPClientError:
            return None
        return _safe_float(payload.get("volume"))


class KrakenAdapter(BaseExchangeAdapter):
    exchange_key = "kraken"
    exchange_name = "Kraken"
    tv_exchange = "KRAKEN"
    cryptocompare_exchange = "Kraken"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api.kraken.com/0/public/AssetPairs", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for info in payload.get("result", {}).values():
            if info.get("status") != "online":
                continue
            altname = info.get("altname", "")
            base = normalize_asset_symbol(info.get("base", "").lstrip("XZ"))
            quote = normalize_asset_symbol(info.get("quote", "").lstrip("XZ"))
            pairs.append((base, quote, altname))
        return pairs

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                "https://api.kraken.com/0/public/Ticker",
                params={"pair": candidate.exchange_symbol},
            )
        except HTTPClientError:
            return None
        if payload.get("error"):
            return None
        result = payload.get("result", {})
        if not result:
            return None
        ticker = next(iter(result.values()))
        volume = ticker.get("v", [])
        if len(volume) < 2:
            return None
        return _safe_float(volume[1])


class KuCoinAdapter(BaseExchangeAdapter):
    exchange_key = "kucoin"
    exchange_name = "KuCoin"
    tv_exchange = "KUCOIN"
    cryptocompare_exchange = "KuCoin"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api.kucoin.com/api/v2/symbols", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload.get("data", []):
            if not item.get("enableTrading"):
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("baseCurrency", "")),
                    normalize_asset_symbol(item.get("quoteCurrency", "")),
                    item.get("symbol", ""),
                )
            )
        return pairs

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                "https://api.kucoin.com/api/v1/market/stats",
                params={"symbol": candidate.exchange_symbol},
            )
        except HTTPClientError:
            return None
        return _safe_float((payload.get("data") or {}).get("volValue"))


class OKXAdapter(BaseExchangeAdapter):
    exchange_key = "okx"
    exchange_name = "OKX"
    tv_exchange = "OKX"
    cryptocompare_exchange = "OKX"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://www.okx.com/api/v5/public/instruments", params={"instType": "SPOT"}, retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload.get("data", []):
            if item.get("state") != "live":
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("baseCcy", "")),
                    normalize_asset_symbol(item.get("quoteCcy", "")),
                    item.get("instId", ""),
                )
            )
        return pairs

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json("https://www.okx.com/api/v5/market/ticker", params={"instId": candidate.exchange_symbol})
        except HTTPClientError:
            return None
        rows = payload.get("data", [])
        if not rows:
            return None
        return _safe_float(rows[0].get("volCcy24h"))


class BybitAdapter(BaseExchangeAdapter):
    exchange_key = "bybit"
    exchange_name = "Bybit"
    tv_exchange = "BYBIT"
    cryptocompare_exchange = "Bybit"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json(
            "https://api.bybit.com/v5/market/instruments-info",
            params={"category": "spot", "limit": 1000},
            retries=3,
        )
        pairs: list[tuple[str, str, str]] = []
        for item in ((payload.get("result") or {}).get("list") or []):
            if item.get("status") != "Trading":
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("baseCoin", "")),
                    normalize_asset_symbol(item.get("quoteCoin", "")),
                    item.get("symbol", ""),
                )
            )
        return pairs

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                "https://api.bybit.com/v5/market/tickers",
                params={"category": "spot", "symbol": candidate.exchange_symbol},
            )
        except HTTPClientError:
            return None
        rows = ((payload.get("result") or {}).get("list")) or []
        if not rows:
            return None
        return _safe_float(rows[0].get("turnover24h"))


class GateIOAdapter(BaseExchangeAdapter):
    exchange_key = "gateio"
    exchange_name = "Gate.io"
    tv_exchange = "GATEIO"
    cryptocompare_exchange = "Gateio"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api.gateio.ws/api/v4/spot/currency_pairs", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload:
            if item.get("trade_status") != "tradable":
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("base", "")),
                    normalize_asset_symbol(item.get("quote", "")),
                    item.get("id", ""),
                )
            )
        return pairs

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                "https://api.gateio.ws/api/v4/spot/tickers",
                params={"currency_pair": candidate.exchange_symbol},
            )
        except HTTPClientError:
            return None
        if not payload:
            return None
        return _safe_float(payload[0].get("quote_volume"))


class HTXAdapter(BaseExchangeAdapter):
    exchange_key = "htx"
    exchange_name = "HTX"
    tv_exchange = "HTX"
    cryptocompare_exchange = "Huobi"

    async def fetch_pairs(self) -> list[tuple[str, str, str]]:
        payload = await self.http.get_json("https://api.huobi.pro/v1/common/symbols", retries=3)
        pairs: list[tuple[str, str, str]] = []
        for item in payload.get("data", []):
            if item.get("state") != "online":
                continue
            pairs.append(
                (
                    normalize_asset_symbol(item.get("bc", "")),
                    normalize_asset_symbol(item.get("qc", "")),
                    item.get("symbol", ""),
                )
            )
        return pairs

    async def get_volume_24h(self, candidate: MarketCandidate) -> float | None:
        try:
            payload = await self.http.get_json(
                "https://api.huobi.pro/market/detail/merged",
                params={"symbol": candidate.exchange_symbol},
            )
        except HTTPClientError:
            return None
        tick = payload.get("tick") or {}
        return _safe_float(tick.get("vol"))


class ExchangeRegistry:
    def __init__(self, http: HTTPClient) -> None:
        self._adapters: dict[str, BaseExchangeAdapter] = {
            adapter.exchange_key: adapter
            for adapter in [
                BinanceAdapter(http),
                BitfinexAdapter(http),
                BitstampAdapter(http),
                CoinbaseAdapter(http),
                KrakenAdapter(http),
                KuCoinAdapter(http),
                OKXAdapter(http),
                BybitAdapter(http),
                GateIOAdapter(http),
                HTXAdapter(http),
                MEXCAdapter(http),
            ]
        }

    async def discover_pairs(self, base: str, quotes: tuple[str, ...]) -> list[MarketCandidate]:
        tasks = [adapter.discover_pairs(base, quotes) for adapter in self._adapters.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[MarketCandidate] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            merged.extend(result)
        return merged

    def get_adapter(self, exchange_key: str) -> BaseExchangeAdapter | None:
        return self._adapters.get(exchange_key)
