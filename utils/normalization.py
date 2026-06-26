from __future__ import annotations

import re
from datetime import date

from utils.time_utils import USDT_LAUNCH_DATE


DEFAULT_QUOTES = ("USDT", "USD", "BTC", "USDC", "EUR", "ETH")
SYMBOL_ALIASES = {
    "XBT": "BTC",
    "XDG": "DOGE",
}

EXCHANGE_CATALOG: dict[str, dict[str, object]] = {
    "kraken": {
        "display": "Kraken",
        "tv": "KRAKEN",
        "cryptocompare": "Kraken",
        "aliases": {"kraken"},
    },
    "bitfinex": {
        "display": "Bitfinex",
        "tv": "BITFINEX",
        "cryptocompare": "Bitfinex",
        "aliases": {"bitfinex"},
    },
    "coinbase": {
        "display": "Coinbase",
        "tv": "COINBASE",
        "cryptocompare": "Coinbase",
        "aliases": {"coinbase", "coinbaseexchange", "coinbasepro", "gdax"},
    },
    "poloniex": {
        "display": "Poloniex",
        "tv": "POLONIEX",
        "cryptocompare": "Poloniex",
        "aliases": {"poloniex"},
    },
    "bittrex": {
        "display": "Bittrex",
        "tv": "BITTREX",
        "cryptocompare": "Bittrex",
        "aliases": {"bittrex"},
    },
    "bitstamp": {
        "display": "Bitstamp",
        "tv": "BITSTAMP",
        "cryptocompare": "Bitstamp",
        "aliases": {"bitstamp", "bitstampltd"},
    },
    "binance": {
        "display": "Binance",
        "tv": "BINANCE",
        "cryptocompare": "Binance",
        "aliases": {"binance", "binance2"},
    },
    "bybit": {
        "display": "Bybit",
        "tv": "BYBIT",
        "cryptocompare": "Bybit",
        "aliases": {"bybit"},
    },
    "okx": {
        "display": "OKX",
        "tv": "OKX",
        "cryptocompare": "OKX",
        "aliases": {"okx", "okex"},
    },
    "kucoin": {
        "display": "KuCoin",
        "tv": "KUCOIN",
        "cryptocompare": "KuCoin",
        "aliases": {"kucoin"},
    },
    "gateio": {
        "display": "Gate.io",
        "tv": "GATEIO",
        "cryptocompare": "Gateio",
        "aliases": {"gateio", "gate-io", "gate"},
    },
    "htx": {
        "display": "HTX",
        "tv": "HTX",
        "cryptocompare": "Huobi",
        "aliases": {"htx", "huobi", "huobiglobal"},
    },
    "mexc": {
        "display": "MEXC",
        "tv": "MEXC",
        "cryptocompare": "MEXC",
        "aliases": {"mexc", "mexcglobal"},
    },
}


def normalize_ticker(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", value or "")
    return cleaned.upper()


def normalize_asset_symbol(value: str) -> str:
    normalized = normalize_ticker(value)
    return SYMBOL_ALIASES.get(normalized, normalized)


def slugify_exchange(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def canonicalize_exchange_name(*values: str | None) -> tuple[str, str, str, str] | None:
    slugs = {slugify_exchange(value or "") for value in values if value}
    slugs.discard("")
    for key, meta in EXCHANGE_CATALOG.items():
        aliases = meta["aliases"]
        if any(slug in aliases for slug in slugs):
            return key, str(meta["display"]), str(meta["tv"]), str(meta["cryptocompare"])
    return None


def quote_order(coin_genesis_date: date | None) -> tuple[str, ...]:
    if coin_genesis_date and coin_genesis_date <= USDT_LAUNCH_DATE:
        return ("USD", "BTC", "USDT", "USDC", "EUR", "ETH")
    return ("USDT", "USD", "BTC", "USDC", "EUR", "ETH")


def quote_priority(quote: str, coin_genesis_date: date | None) -> int:
    order = quote_order(coin_genesis_date)
    try:
        return order.index(quote)
    except ValueError:
        return len(order) + 10
