import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from attackscope.core.config import Settings
from attackscope.core.errors import ServiceError
from attackscope.storage.store import Store


@dataclass
class SourceUsage:
    tokens: float
    updated: float
    active: int = 0


class Runtime:
    def __init__(
        self, store: Store, settings: Settings, monotonic: Callable[[], float] = time.monotonic
    ) -> None:
        self.store = store
        self.settings = settings
        self.monotonic = monotonic
        self.slots = threading.BoundedSemaphore(settings.max_api_concurrency)
        self.lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.usage: dict[str, SourceUsage] = {}

    def cached(self, key: str, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        now = self.monotonic()
        with self.cache_lock:
            item = self.cache.get(key)
            if item is not None and now - item[0] < 10:
                self.cache.move_to_end(key)
                return item[1]
        result = compute()
        with self.cache_lock:
            self.cache[key] = (self.monotonic(), result)
            self.cache.move_to_end(key)
            while len(self.cache) > 32:
                self.cache.popitem(last=False)
        return result

    @contextmanager
    def source_slot(self, source_id: str) -> Iterator[None]:
        with self.lock:
            now = self.monotonic()
            usage = self.usage.setdefault(
                source_id, SourceUsage(float(self.settings.source_burst), now)
            )
            usage.tokens = min(
                float(self.settings.source_burst),
                usage.tokens
                + max(0, now - usage.updated) * self.settings.source_requests_per_second,
            )
            usage.updated = now
            if usage.active >= self.settings.source_concurrency or usage.tokens < 1:
                raise ServiceError(429, "source_limit", "Source limit exceeded; retry later")
            usage.tokens -= 1
            usage.active += 1
        try:
            yield
        finally:
            with self.lock:
                usage.active -= 1
