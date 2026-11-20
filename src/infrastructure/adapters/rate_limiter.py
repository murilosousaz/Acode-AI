import time
from collections import deque
from typing import Deque, Dict, NamedTuple


class RateLimitResult(NamedTuple):
    allowed: bool
    retry_after: float  # segundos até liberar um novo slot (0 se permitido)


class SlidingWindowRateLimiter:
    """Limitador de requisições por chave (ex.: IP do cliente), janela
    deslizante, em memória.

    Por ser em memória, o estado não é compartilhado entre processos/réplicas
    da API. Em deploys com mais de uma réplica, mova o controle para o Redis.
    """

    _SWEEP_EVERY = 1000  # chamadas entre varreduras de chaves inativas

    def __init__(self, requests_limit: int = 5, window_seconds: int = 60):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        self._calls = 0

    def check(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        self._calls += 1
        if self._calls % self._SWEEP_EVERY == 0:
            self._sweep(now)

        hits = self._hits.setdefault(key, deque())
        self._prune(hits, now)

        if len(hits) >= self.requests_limit:
            retry_after = max(0.0, self.window_seconds - (now - hits[0]))
            return RateLimitResult(False, retry_after)

        hits.append(now)
        return RateLimitResult(True, 0.0)

    def _prune(self, hits: Deque[float], now: float) -> None:
        window_start = now - self.window_seconds
        while hits and hits[0] < window_start:
            hits.popleft()

    def _sweep(self, now: float) -> None:
        """Remove chaves sem hits recentes, para a memória não crescer sem fim."""
        for key in list(self._hits):
            self._prune(self._hits[key], now)
            if not self._hits[key]:
                del self._hits[key]
