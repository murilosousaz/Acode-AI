import time
from collections import defaultdict, deque
from typing import Deque, Dict


class UserRateLimiter:
    """Limitador de requisições por usuário (janela deslizante), em memória.

    Pensado para evitar uso indevido/custos excessivos com a API da OpenAI
    em comandos que qualquer membro do servidor pode executar.

    Observação: por ser em memória, o estado não é compartilhado entre
    múltiplas instâncias/processos do bot. Para deploys com mais de uma
    réplica, considere mover o controle para o Redis/MongoDB.
    """

    def __init__(self, requests_limit: int = 5, window_seconds: int = 60):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def is_allowed(self, user_id: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        user_hits = self._hits[user_id]

        while user_hits and user_hits[0] < window_start:
            user_hits.popleft()

        if len(user_hits) >= self.requests_limit:
            return False

        user_hits.append(now)
        return True

    def seconds_until_next_slot(self, user_id: str) -> float:
        user_hits = self._hits.get(user_id)
        if not user_hits:
            return 0.0
        oldest = user_hits[0]
        remaining = self.window_seconds - (time.monotonic() - oldest)
        return max(0.0, remaining)
