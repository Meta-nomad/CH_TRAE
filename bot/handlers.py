from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from services.symbol_finder import CoinNotFoundError, InsufficientDataError, SymbolFinderService
from utils.formatters import START_MESSAGE, format_result


logger = logging.getLogger(__name__)


def build_router(symbol_finder: SymbolFinderService) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        await message.answer(START_MESSAGE)

    @router.message(F.text)
    async def ticker_handler(message: Message) -> None:
        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            await message.answer(START_MESSAGE)
            return

        await message.bot.send_chat_action(message.chat.id, "typing")

        try:
            result = await symbol_finder.lookup(text)
        except CoinNotFoundError:
            await message.answer("Монета не найдена. Проверьте тикер.")
            return
        except InsufficientDataError:
            await message.answer("Недостаточно данных для определения самой длинной истории.")
            return
        except Exception:
            logger.exception("Unexpected lookup error for %s", text)
            await message.answer("Недостаточно данных для определения самой длинной истории.")
            return

        await message.answer(format_result(result))

    return router
