from __future__ import annotations

from typing import Any

from services.http import HTTPClient, HTTPClientError
from utils.models import MarketCandidate
from utils.normalization import canonicalize_exchange_name


class CryptoCompareService:
    BASE_URL = "https://min-api.cryptocompare.com/data"

    def __init__(self, http: HTTPClient, api_key: str | None) -> None:
        self._http = http
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _params(self, **kwargs: Any) -> dict[str, Any]:
        if not self._api_key:
            return kwargs
        return {**kwargs, "api_key": self._api_key}

    async def discover_pairs(self, base: str, quotes: tuple[str, ...]) -> list[MarketCandidate]:
        if not self.enabled:
            return []

        results: list[MarketCandidate] = []
        for quote in quotes:
            try:
                payload = await self._http.get_json(
                    f"{self.BASE_URL}/all/exchanges",
                    params=self._params(fsym=base, tsym=quote),
                    retries=3,
                )
            except HTTPClientError:
                continue

            if not isinstance(payload, dict):
                continue

            for exchange_name in payload.keys():
                exchange_data = canonicalize_exchange_name(exchange_name)
                if not exchange_data:
                    continue
                exchange_key, display_name, tv_exchange, cryptocompare_exchange = exchange_data
                results.append(
                    MarketCandidate(
                        exchange_key=exchange_key,
                        exchange_name=display_name,
                        tv_exchange=tv_exchange,
                        cryptocompare_exchange=cryptocompare_exchange,
                        base=base,
                        quote=quote,
                        discovery_sources={"cryptocompare"},
                    )
                )
        return results

    async def get_earliest_daily(self, candidate: MarketCandidate) -> int | None:
        if not self.enabled:
            return None

        try:
            payload = await self._http.get_json(
                f"{self.BASE_URL}/v2/histoday",
                params=self._params(
                    fsym=candidate.base,
                    tsym=candidate.quote,
                    e=candidate.cryptocompare_exchange,
                    allData="true",
                    tryConversion="false",
                    limit=2000,
                ),
                retries=3,
            )
        except HTTPClientError:
            return None

        data = ((payload or {}).get("Data") or {}).get("Data") or []
        if not data:
            return None
        first = data[0]
        try:
            return int(first["time"])
        except (KeyError, TypeError, ValueError):
            return None

    async def get_hourly_segment(
        self,
        candidate: MarketCandidate,
        start_ts: int,
        hours: int = 24 * 14,
    ) -> list[dict[str, float]]:
        if not self.enabled:
            return []

        try:
            payload = await self._http.get_json(
                f"{self.BASE_URL}/v2/histohour",
                params=self._params(
                    fsym=candidate.base,
                    tsym=candidate.quote,
                    e=candidate.cryptocompare_exchange,
                    allData="true",
                    tryConversion="false",
                    limit=2000,
                ),
                retries=3,
            )
        except HTTPClientError:
            return []

        rows = ((payload or {}).get("Data") or {}).get("Data") or []
        end_ts = start_ts + hours * 3600
        candles: list[dict[str, float]] = []
        for row in rows:
            try:
                ts = int(row["time"])
            except (KeyError, TypeError, ValueError):
                continue
            if ts < start_ts or ts >= end_ts:
                continue
            candles.append(
                {
                    "timestamp": ts,
                    "open": float(row.get("open", 0) or 0),
                    "high": float(row.get("high", 0) or 0),
                    "low": float(row.get("low", 0) or 0),
                    "close": float(row.get("close", 0) or 0),
                    "volume": float(row.get("volumeto", 0) or 0),
                }
            )
        return candles
