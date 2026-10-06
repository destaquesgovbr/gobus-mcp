"""Cache assíncrono em memória com TTL e single-flight por chave.

Uso típico (catálogo de agências, snapshot de atividade, contexto de entidade):

    cache = TTLCache()
    data = await cache.get_or_load(("agencies",), lambda: client.execute(Q), ttl=86_400)

- **Single-flight:** chamadas concorrentes para a mesma chave aguardam uma única carga.
  Se a carga falha, todas as que estavam esperando recebem a mesma exceção.
- **Exceção não é cacheada:** a próxima chamada depois de uma falha carrega de novo.
- **Clock injetável** (``time.monotonic`` por padrão) para testar a expiração sem sleep.

O Cloud Run roda com uma instância por vez; o cache é por processo, sem coordenação.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    """Cache TTL assíncrono, single-flight por chave."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[Hashable, tuple[float, Any]] = {}  # chave → (expira_em, valor)
        self._inflight: dict[Hashable, asyncio.Future[Any]] = {}

    async def get_or_load(self, key: Hashable, loader: Callable[[], Awaitable[T]], ttl: float) -> T:
        """Valor em cache para ``key``; se ausente ou expirado, carrega com ``loader()``."""
        loop = asyncio.get_running_loop()
        while True:
            entry = self._entries.get(key)
            if entry is not None and entry[0] > self._clock():
                return entry[1]
            pending = self._inflight.get(key)
            if pending is None or pending.get_loop() is not loop:
                break  # ninguém carregando (ou carga órfã de outro event loop)
            # asyncio.wait não propaga a exceção nem cancela a carga se *este* chamador
            # for cancelado; a carga do líder segue para os demais.
            await asyncio.wait({pending})
            if pending.cancelled():
                continue  # o líder foi cancelado: tenta de novo (talvez virando líder)
            return pending.result()  # levanta a exceção da carga, se houve

        future: asyncio.Future[Any] = loop.create_future()
        self._inflight[key] = future
        try:
            value = await loader()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # marca como lida: sem aviso se ninguém estava esperando
            raise
        else:
            self._entries[key] = (self._clock() + ttl, value)
            future.set_result(value)
            return value
        finally:
            if self._inflight.get(key) is future:
                del self._inflight[key]

    def invalidate(self, key: Hashable | None = None) -> None:
        """Descarta ``key`` (ou tudo, sem argumento). Cargas em andamento não são afetadas."""
        if key is None:
            self._entries.clear()
        else:
            self._entries.pop(key, None)
