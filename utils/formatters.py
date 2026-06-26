from __future__ import annotations

from utils.models import LookupResult


def build_tradingview_link(symbol: str) -> str:
    encoded = symbol.replace(":", "%3A")
    return f"https://www.tradingview.com/chart/?symbol={encoded}"


def format_result(result: LookupResult) -> str:
    best = result.best
    lines = [
        f"Монета: {result.coin_symbol}",
        "",
        f"Рекомендуемый символ TradingView:",
        best.tv_symbol,
        "",
        "Биржа:",
        best.exchange_name,
        "",
        "Дата начала истории:",
        best.start_date or "не удалось определить",
        "",
        "Ссылка:",
        build_tradingview_link(best.tv_symbol),
    ]

    if best.hourly_gap_ratio is not None and best.flat_candle_ratio is not None:
        lines.extend(
            [
                "",
                "Качество часового графика:",
                (
                    f"разрывы {best.hourly_gap_ratio:.1%}, "
                    f"плоские свечи {best.flat_candle_ratio:.1%}, "
                    f"сэмплов {best.hourly_samples}"
                ),
            ]
        )

    if result.alternatives:
        lines.extend(["", "Альтернативы:"])
        for item in result.alternatives[:3]:
            lines.append(item.tv_symbol)

    return "\n".join(lines)


START_MESSAGE = (
    "Отправьте тикер монеты:\n\n"
    "BTC\n"
    "ETH\n"
    "ZEC\n"
    "DOGE\n"
    "SOL\n\n"
    "Я найду биржу с самой длинной историей цены для TradingView."
)
