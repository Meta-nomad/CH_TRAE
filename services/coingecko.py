from __future__ import annotations

from typing import Any

from services.http import HTTPClient, HTTPClientError
from utils.models import CoinIdentity, MarketCandidate
from utils.normalization import DEFAULT_QUOTES, canonicalize_exchange_name, normalize_asset_symbol, normalize_ticker
from utils.time_utils import parse_iso_date


class CoinGeckoService:
    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self, http: HTTPClient, api_key: str | None = None) -> None:
        self._http = http
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"x-cg-demo-api-key": self._api_key}

    async def resolve_coin(self, ticker: str) -> CoinIdentity | None:
        normalized = normalize_ticker(ticker)
        try:
            payload = await self._http.get_json(
                f"{self.BASE_URL}/search",
                params={"query": normalized},
                headers=self._headers(),
                retries=4,
            )
        except HTTPClientError:
            return None

        coins = payload.get("coins", [])
        exact = [coin for coin in coins if normalize_ticker(coin.get("symbol", "")) == normalized]
        if not exact:
            return None

        exact.sort(
            key=lambda item: (
                item.get("market_cap_rank") is None,
                item.get("market_cap_rank") or 10**9,
                item.get("name", ""),
            )
        )
        coin_id = exact[0]["id"]

        try:
            details = await self._http.get_json(
                f"{self.BASE_URL}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
                headers=self._headers(),
                retries=4,
            )
        except HTTPClientError:
            details = exact[0]

        return CoinIdentity(
            coin_id=coin_id,
            symbol=normalize_asset_symbol(details.get("symbol", normalized)),
            name=details.get("name") or exact[0].get("name") or normalized,
            genesis_date=parse_iso_date(details.get("genesis_date")),
        )

    async def get_market_candidates(
        self,
        coin_id: str,
        base_symbol: str,
        allowed_quotes: tuple[str, ...] = DEFAULT_QUOTES,
    ) -> list[MarketCandidate]:
        candidates: list[MarketCandidate] = []

        for page in range(1, 6):
            try:
                payload = await self._http.get_json(
                    f"{self.BASE_URL}/coins/{coin_id}/tickers",
                    params={"page": page, "per_page": 250},
                    headers=self._headers(),
                    retries=4,
                )
            except HTTPClientError:
                break

            tickers = payload.get("tickers", [])
            if not tickers:
                break

            for ticker in tickers:
                base = normalize_asset_symbol(ticker.get("base", ""))
                quote = normalize_asset_symbol(ticker.get("target", ""))
                if base != base_symbol or quote not in allowed_quotes:
                    continue

                market = ticker.get("market") or {}
                exchange_data = canonicalize_exchange_name(
                    market.get("identifier"),
                    market.get("name"),
                )
                if not exchange_data:
                    continue

                exchange_key, exchange_name, tv_exchange, cryptocompare_exchange = exchange_data
                volume_usd = None
                converted_volume = ticker.get("converted_volume") or {}
                if isinstance(converted_volume, dict):
                    raw_volume = converted_volume.get("usd")
                    if raw_volume is not None:
                        try:
                            volume_usd = float(raw_volume)
                        except (TypeError, ValueError):
                            volume_usd = None

                candidates.append(
                    MarketCandidate(
                        exchange_key=exchange_key,
                        exchange_name=exchange_name,
                        tv_exchange=tv_exchange,
                        cryptocompare_exchange=cryptocompare_exchange,
                        base=base,
                        quote=quote,
                        discovery_sources={"coingecko"},
                        volume_usd=volume_usd,
                    )
                )

            if len(tickers) < 250:
                break

        return candidates
