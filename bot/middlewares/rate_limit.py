import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.utils.constants import RATE_LIMIT_BURST, RATE_LIMIT_RATE

_BUCKET_EVICTION_AGE = 3600  # 1 hour
_LIGHTWEIGHT_COMMANDS = frozenset({
    "/mood", "/diary", "/start", "/help", "/cancel", "/skip",
    "/reset", "/techniques",
})


class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self) -> None:
        self.tokens = RATE_LIMIT_BURST
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(RATE_LIMIT_BURST, self.tokens + elapsed * RATE_LIMIT_RATE)
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._buckets: dict[int, _Bucket] = {}

    def _evict_stale_buckets(self) -> None:
        now = time.monotonic()
        stale = [
            uid for uid, b in self._buckets.items()
            if now - b.last_refill > _BUCKET_EVICTION_AGE
        ]
        for uid in stale:
            del self._buckets[uid]

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if event.from_user is None:
            return None

        if event.text and event.text.split()[0].split("@")[0] in _LIGHTWEIGHT_COMMANDS:
            return await handler(event, data)

        self._evict_stale_buckets()

        user_id = event.from_user.id
        bucket = self._buckets.setdefault(user_id, _Bucket())
        if not bucket.consume():
            await event.answer(
                "⏳ Подожди немного, я ещё обрабатываю предыдущий запрос."
            )
            return None
        return await handler(event, data)
