"""Token bucket rate limiter for API requests."""

import asyncio
import time


class RateLimiter:
    def __init__(self, rate: float, burst: int = 1, name: str = "default"):
        self.rate = rate
        self.burst = burst
        self.name = name
        self.tokens = float(burst)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.burst, self.tokens + elapsed / self.rate)
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait_time = (1 - self.tokens) * self.rate
                await asyncio.sleep(wait_time)

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass


class MultiRateLimiter:
    def __init__(self):
        self._limiters = {}

    def get_limiter(self, name: str, rate: float, burst: int = 1) -> RateLimiter:
        if name not in self._limiters:
            self._limiters[name] = RateLimiter(rate, burst, name)
        return self._limiters[name]


rate_limiters = MultiRateLimiter()
