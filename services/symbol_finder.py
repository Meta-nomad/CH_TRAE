from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import inf

from services.cache import JsonFileCache
from services.coingecko import CoinGeckoService
from services.cryptocompare import CryptoCompareService
from services.exchanges import ExchangeRegistry
from utils.models import CoinIdentity, LookupResult, MarketCandidate
from utils.normalization import normalize_ticker, quote_order, quote_priority


class CoinNotFoundError(RuntimeError):
    pass


class InsufficientDataError(RuntimeError):
    pass


@dataclass(slots=True)
class HourlyQuality:
    gap_ratio: float
    flat_ratio: float
    samples: int


class SymbolFinderService:
    CACHE_VERSION = "v2"

    def __init__(
        self,
        *,
        coingecko: CoinGeckoService,
        cryptocompare: CryptoCompareService,
        exchange_registry: ExchangeRegistry,
        cache: JsonFileCache,
        max_candidates: int = 40,
    ) -> None:
        self._coingecko = coingecko
        self._cryptocompare = cryptocompare
        self._exchange_registry = exchange_registry
        self._cache = cache
        self._max_candidates = max_candidates

    async def lookup(self, ticker: str) -> LookupResult:
        normalized = normalize_ticker(ticker)
        if not normalized:
            raise CoinNotFoundError

        cache_key = f"{self.CACHE_VERSION}:{normalized}"
        cached = await self._cache.get(cache_key)
        if cached:
            return LookupResult.from_dict(cached)

        coin = await self._coingecko.resolve_coin(normalized)
        if not coin:
            raise CoinNotFoundError

        quotes = quote_order(coin.genesis_date)
        raw_candidates = await self._discover_candidates(coin, quotes)
        if not raw_candidates:
            raise InsufficientDataError

        await self._assess_candidates(raw_candidates)
        ranked = [item for item in raw_candidates if item.earliest_ts is not None]
        if not ranked:
            raise InsufficientDataError

        ranked.sort(key=lambda item: self._initial_sort_key(item, coin))
        earliest_ts = ranked[0].earliest_ts
        same_start = [item for item in ranked if item.earliest_ts == earliest_ts]
        if len(same_start) > 1:
            await self._score_quality(same_start)
            ranked.sort(key=lambda item: self._final_sort_key(item, coin))

        result = LookupResult(
            coin_name=coin.name,
            coin_symbol=coin.symbol,
            best=ranked[0],
            alternatives=ranked[1:4],
            selection_reason=self._build_selection_reason(coin, ranked),
        )
        await self._cache.set(cache_key, result.to_dict())
        return result

    async def _discover_candidates(self, coin: CoinIdentity, quotes: tuple[str, ...]) -> list[MarketCandidate]:
        merged: dict[tuple[str, str, str], MarketCandidate] = {}

        async def merge(items: list[MarketCandidate]) -> None:
            for candidate in items:
                key = (candidate.exchange_key, candidate.base, candidate.quote)
                existing = merged.get(key)
                if existing:
                    existing.merge(candidate)
                else:
                    merged[key] = candidate

        coingecko_task = self._coingecko.get_market_candidates(coin.coin_id, coin.symbol, quotes)
        exchange_task = self._exchange_registry.discover_pairs(coin.symbol, quotes)
        cc_task = self._cryptocompare.discover_pairs(coin.symbol, quotes) if self._cryptocompare.enabled else asyncio.sleep(0, result=[])
        discovered = await asyncio.gather(coingecko_task, exchange_task, cc_task)
        for items in discovered:
            await merge(items)

        candidates = list(merged.values())
        candidates.sort(key=lambda item: (quote_priority(item.quote, coin.genesis_date), item.exchange_name))
        return candidates[: self._max_candidates]

    async def _assess_candidates(self, candidates: list[MarketCandidate]) -> None:
        semaphore = asyncio.Semaphore(6)

        async def runner(candidate: MarketCandidate) -> None:
            async with semaphore:
                await self._assess_candidate(candidate)

        await asyncio.gather(*(runner(candidate) for candidate in candidates))

    async def _assess_candidate(self, candidate: MarketCandidate) -> None:
        earliest_candidates: list[tuple[int, str]] = []
        adapter = self._exchange_registry.get_adapter(candidate.exchange_key)

        if self._cryptocompare.enabled:
            cc_ts = await self._cryptocompare.get_earliest_daily(candidate)
            if cc_ts is not None:
                earliest_candidates.append((cc_ts, "cryptocompare"))

        if adapter is not None and candidate.exchange_symbol:
            exchange_ts = await adapter.get_earliest_daily(candidate)
            if exchange_ts is not None:
                earliest_candidates.append((exchange_ts, f"{candidate.exchange_key}_api"))

            volume_24h = await adapter.get_volume_24h(candidate)
            if volume_24h is not None:
                candidate.volume_24h = max(candidate.volume_24h or 0.0, volume_24h)

        if earliest_candidates:
            earliest_ts, source = min(earliest_candidates, key=lambda item: item[0])
            candidate.earliest_ts = earliest_ts
            candidate.earliest_source = source

    async def _score_quality(self, candidates: list[MarketCandidate]) -> None:
        tasks = [self._score_candidate_quality(candidate) for candidate in candidates]
        await asyncio.gather(*tasks)

    async def _score_candidate_quality(self, candidate: MarketCandidate) -> None:
        if candidate.earliest_ts is None:
            return

        adapter = self._exchange_registry.get_adapter(candidate.exchange_key)
        candles: list[dict[str, float]] = []
        if adapter is not None and candidate.exchange_symbol:
            candles = await adapter.get_hourly_segment(candidate, candidate.earliest_ts)
        if not candles and self._cryptocompare.enabled:
            candles = await self._cryptocompare.get_hourly_segment(candidate, candidate.earliest_ts)

        quality = self._measure_quality(candidate.earliest_ts, candles)
        if quality:
            candidate.hourly_gap_ratio = quality.gap_ratio
            candidate.flat_candle_ratio = quality.flat_ratio
            candidate.hourly_samples = quality.samples

    def _measure_quality(self, start_ts: int, candles: list[dict[str, float]], hours: int = 24 * 14) -> HourlyQuality | None:
        if not candles:
            return None

        seen: dict[int, dict[str, float]] = {}
        end_ts = start_ts + hours * 3600
        for candle in candles:
            ts = int(candle.get("timestamp", 0))
            if start_ts <= ts < end_ts:
                seen[ts] = candle

        if not seen:
            return None

        expected = hours
        gaps = 0
        flat = 0
        for index in range(expected):
            ts = start_ts + index * 3600
            candle = seen.get(ts)
            if candle is None:
                gaps += 1
                continue
            high = float(candle.get("high", 0) or 0)
            low = float(candle.get("low", 0) or 0)
            open_price = float(candle.get("open", 0) or 0)
            close_price = float(candle.get("close", 0) or 0)
            if high == low or (open_price == close_price == high == low):
                flat += 1

        sample_count = len(seen)
        return HourlyQuality(
            gap_ratio=gaps / expected,
            flat_ratio=flat / max(sample_count, 1),
            samples=sample_count,
        )

    def _initial_sort_key(self, candidate: MarketCandidate, coin: CoinIdentity) -> tuple[float, float, int, str]:
        volume = candidate.volume_24h or candidate.volume_usd or 0.0
        return (
            candidate.earliest_ts if candidate.earliest_ts is not None else inf,
            -volume,
            quote_priority(candidate.quote, coin.genesis_date),
            candidate.exchange_name,
        )

    def _final_sort_key(self, candidate: MarketCandidate, coin: CoinIdentity) -> tuple[float, float, float, float, int, str]:
        volume = candidate.volume_24h or candidate.volume_usd or 0.0
        gap = candidate.hourly_gap_ratio if candidate.hourly_gap_ratio is not None else 1.0
        flat = candidate.flat_candle_ratio if candidate.flat_candle_ratio is not None else 1.0
        return (
            candidate.earliest_ts if candidate.earliest_ts is not None else inf,
            gap,
            flat,
            -volume,
            quote_priority(candidate.quote, coin.genesis_date),
            candidate.exchange_name,
        )

    def _build_selection_reason(self, coin: CoinIdentity, ranked: list[MarketCandidate]) -> str | None:
        if not ranked:
            return None

        best = ranked[0]
        competitor = self._find_reference_candidate(best, ranked)
        if competitor is None:
            return None

        if best.earliest_ts is not None and competitor.earliest_ts is not None and best.earliest_ts != competitor.earliest_ts:
            delta_days = abs(best.earliest_ts - competitor.earliest_ts) // 86400
            if best.earliest_ts < competitor.earliest_ts:
                return (
                    f"{best.quote} выбран, потому что история начинается раньше, чем у "
                    f"{competitor.quote}, примерно на {delta_days} дн."
                )

        best_gap = best.hourly_gap_ratio if best.hourly_gap_ratio is not None else 1.0
        competitor_gap = competitor.hourly_gap_ratio if competitor.hourly_gap_ratio is not None else 1.0
        if abs(best_gap - competitor_gap) > 1e-9 and best_gap < competitor_gap:
            return (
                f"{best.quote} выбран, потому что при сопоставимой дате старта у него лучше "
                f"часовой график: меньше гэпов."
            )

        best_flat = best.flat_candle_ratio if best.flat_candle_ratio is not None else 1.0
        competitor_flat = competitor.flat_candle_ratio if competitor.flat_candle_ratio is not None else 1.0
        if abs(best_flat - competitor_flat) > 1e-9 and best_flat < competitor_flat:
            return (
                f"{best.quote} выбран, потому что при сопоставимой дате старта у него меньше "
                f"плоских свечей на часовом графике."
            )

        best_volume = best.volume_24h or best.volume_usd or 0.0
        competitor_volume = competitor.volume_24h or competitor.volume_usd or 0.0
        if best_volume > competitor_volume:
            return (
                f"{best.quote} выбран, потому что при близких истории и качестве графика "
                f"у него выше торговый объём."
            )

        if best.quote == "USDT":
            return "При полном равенстве выбран USDT как приоритетная котировка."

        if best.quote == "USD":
            return "USD выбран, потому что по итоговому сравнению он дал более сильный результат, чем USDT."

        return None

    def _find_reference_candidate(self, best: MarketCandidate, ranked: list[MarketCandidate]) -> MarketCandidate | None:
        if best.quote == "USD":
            return next((item for item in ranked[1:] if item.quote == "USDT"), ranked[1] if len(ranked) > 1 else None)
        if best.quote == "USDT":
            return next((item for item in ranked[1:] if item.quote == "USD"), ranked[1] if len(ranked) > 1 else None)
        return ranked[1] if len(ranked) > 1 else None
