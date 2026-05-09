"""
In-memory cache simulating Redis (qr_token → original_url).
In production this would be replaced with redis-py pointing at a Redis cluster.
Cache key: qr_token  |  Value: original_url string
"""
import time
from typing import Any, Optional


class InMemoryCache:
    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (value, time.monotonic() + ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


# Module-level singleton — swap for Redis client in production
cache = InMemoryCache(default_ttl=300)
