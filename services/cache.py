from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any


class JsonFileCache:
    def __init__(self, file_path: Path, ttl_seconds: int) -> None:
        self._file_path = file_path
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            payload = await asyncio.to_thread(self._read)
            record = payload.get(key)
            if not record:
                return None
            if record.get("expires_at", 0) <= time.time():
                payload.pop(key, None)
                await asyncio.to_thread(self._write, payload)
                return None
            return record.get("value")

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            payload = await asyncio.to_thread(self._read)
            payload[key] = {
                "expires_at": time.time() + self._ttl_seconds,
                "value": value,
            }
            await asyncio.to_thread(self._write, payload)

    def _read(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return {}
        with self._file_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, payload: dict[str, Any]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
