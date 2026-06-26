from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class HTTPClientError(RuntimeError):
    pass


class HTTPClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 3,
        acceptable_statuses: set[int] | None = None,
    ) -> Any:
        acceptable_statuses = acceptable_statuses or set()
        merged_headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (TradingViewHistoryBot/1.0)",
        }
        if headers:
            merged_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers=merged_headers,
                ) as response:
                    if response.status in acceptable_statuses:
                        return None
                    if response.status in {429, 500, 502, 503, 504} and attempt < retries - 1:
                        retry_after = response.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else 1.5 * (attempt + 1)
                        await asyncio.sleep(delay)
                        continue
                    if response.status >= 400:
                        body = await response.text()
                        raise HTTPClientError(f"{response.status} {url}: {body[:200]}")
                    return await response.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, HTTPClientError) as exc:
                last_error = exc
                if attempt >= retries - 1:
                    raise HTTPClientError(str(exc)) from exc
                await asyncio.sleep(1.2 * (attempt + 1))
        raise HTTPClientError(str(last_error or "Неизвестная ошибка HTTP"))
