import asyncio

import pytest
from pydantic import BaseModel

from trading_system_v3.actors.base import IsolatedActor


class _Req(BaseModel):
    n: int


class _Resp(BaseModel):
    doubled: int


class _EchoActor(IsolatedActor):
    def __init__(self):
        super().__init__(name="echo")
        self._private_counter = 0  # only mutated inside handle(), never exposed

    async def handle(self, request: _Req) -> _Resp:
        self._private_counter += 1
        return _Resp(doubled=request.n * 2)


@pytest.mark.asyncio
async def test_ask_round_trip():
    actor = _EchoActor()
    resp = await actor.ask(_Req(n=21))
    assert resp.doubled == 42
    await actor.stop()


@pytest.mark.asyncio
async def test_only_public_surface_is_ask_start_stop():
    actor = _EchoActor()
    public = {name for name in dir(actor) if not name.startswith("_")}
    assert public == {"ask", "start", "stop", "handle", "name"}


@pytest.mark.asyncio
async def test_processes_messages_serially_no_interleaving():
    actor = _EchoActor()
    results = await asyncio.gather(*[actor.ask(_Req(n=i)) for i in range(20)])
    assert [r.doubled for r in results] == [i * 2 for i in range(20)]
    assert actor._private_counter == 20
    await actor.stop()


@pytest.mark.asyncio
async def test_exception_in_handle_propagates_to_caller_not_actor_loop():
    class _Boom(IsolatedActor):
        async def handle(self, request):
            raise ValueError("boom")

    actor = _Boom(name="boom")
    with pytest.raises(ValueError, match="boom"):
        await actor.ask(_Req(n=1))
    # actor loop survives a handler exception and can still be asked again
    with pytest.raises(ValueError, match="boom"):
        await actor.ask(_Req(n=1))
    await actor.stop()
