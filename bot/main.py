from __future__ import annotations

import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher

from bot.handlers import build_router
from config.settings import load_settings
from services.cache import JsonFileCache
from services.coingecko import CoinGeckoService
from services.cryptocompare import CryptoCompareService
from services.exchanges import ExchangeRegistry
from services.http import HTTPClient
from services.symbol_finder import SymbolFinderService


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    settings = load_settings()

    timeout = aiohttp.ClientTimeout(total=settings.request_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        http = HTTPClient(session)
        cache = JsonFileCache(settings.cache_file, settings.cache_ttl_seconds)
        coingecko = CoinGeckoService(http, settings.coingecko_api_key)
        cryptocompare = CryptoCompareService(http, settings.cryptocompare_api_key)
        exchange_registry = ExchangeRegistry(http)
        symbol_finder = SymbolFinderService(
            coingecko=coingecko,
            cryptocompare=cryptocompare,
            exchange_registry=exchange_registry,
            cache=cache,
            max_candidates=settings.max_candidates,
        )

        bot = Bot(settings.bot_token)
        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(symbol_finder))

        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
