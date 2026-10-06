"""TTLCache: cache assíncrono com TTL, single-flight por chave e clock injetável."""

import asyncio

import pytest

from gobus_mcp.cache import TTLCache


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CountingLoader:
    def __init__(self, value="v", *, delay: float = 0.0, error: Exception | None = None):
        self.value = value
        self.delay = delay
        self.error = error
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return f"{self.value}{self.calls}"


async def test_segunda_chamada_dentro_do_ttl_usa_cache():
    cache = TTLCache(clock=FakeClock())
    loader = CountingLoader()

    assert await cache.get_or_load("k", loader, ttl=60) == "v1"
    assert await cache.get_or_load("k", loader, ttl=60) == "v1"
    assert loader.calls == 1


async def test_expira_apos_ttl_com_clock_falso():
    clock = FakeClock()
    cache = TTLCache(clock=clock)
    loader = CountingLoader()

    assert await cache.get_or_load("k", loader, ttl=60) == "v1"
    clock.advance(59.9)
    assert await cache.get_or_load("k", loader, ttl=60) == "v1"
    clock.advance(0.2)
    assert await cache.get_or_load("k", loader, ttl=60) == "v2"
    assert loader.calls == 2


async def test_single_flight_chamadas_concorrentes_carregam_uma_vez():
    cache = TTLCache(clock=FakeClock())
    loader = CountingLoader(delay=0.01)

    results = await asyncio.gather(*(cache.get_or_load("k", loader, ttl=60) for _ in range(5)))

    assert results == ["v1"] * 5
    assert loader.calls == 1


async def test_chaves_diferentes_sao_independentes():
    cache = TTLCache(clock=FakeClock())
    a, b = CountingLoader("a"), CountingLoader("b")

    assert await cache.get_or_load("ka", a, ttl=60) == "a1"
    assert await cache.get_or_load(("kb", 1), b, ttl=60) == "b1"
    assert (a.calls, b.calls) == (1, 1)


async def test_excecao_nao_e_cacheada():
    cache = TTLCache(clock=FakeClock())
    failing = CountingLoader(error=RuntimeError("upstream caiu"))

    with pytest.raises(RuntimeError, match="upstream caiu"):
        await cache.get_or_load("k", failing, ttl=60)

    ok = CountingLoader()
    assert await cache.get_or_load("k", ok, ttl=60) == "v1"
    assert failing.calls == 1 and ok.calls == 1


async def test_excecao_compartilhada_entre_concorrentes_sem_recarregar():
    cache = TTLCache(clock=FakeClock())
    failing = CountingLoader(delay=0.01, error=RuntimeError("timeout"))

    results = await asyncio.gather(
        *(cache.get_or_load("k", failing, ttl=60) for _ in range(3)), return_exceptions=True
    )

    assert all(isinstance(r, RuntimeError) for r in results)
    assert failing.calls == 1


async def test_lider_cancelado_nao_trava_os_demais():
    cache = TTLCache(clock=FakeClock())
    slow = CountingLoader(delay=10)

    leader = asyncio.create_task(cache.get_or_load("k", slow, ttl=60))
    await asyncio.sleep(0)
    follower = asyncio.create_task(cache.get_or_load("k", CountingLoader("f"), ttl=60))
    await asyncio.sleep(0)
    leader.cancel()

    assert await asyncio.wait_for(follower, timeout=1) == "f1"
    with pytest.raises(asyncio.CancelledError):
        await leader


async def test_invalidate_por_chave_e_total():
    cache = TTLCache(clock=FakeClock())
    loader = CountingLoader()

    await cache.get_or_load("a", loader, ttl=60)
    await cache.get_or_load("b", loader, ttl=60)
    cache.invalidate("a")
    assert await cache.get_or_load("a", loader, ttl=60) == "v3"
    assert await cache.get_or_load("b", loader, ttl=60) == "v2"

    cache.invalidate()
    assert await cache.get_or_load("b", loader, ttl=60) == "v4"
