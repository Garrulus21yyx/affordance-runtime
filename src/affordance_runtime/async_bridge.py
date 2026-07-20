"""Run an awaitable from synchronous, event-loop-owning integrations."""

from __future__ import annotations

import asyncio
from threading import Thread
from typing import Awaitable, TypeVar

T = TypeVar("T")


def resolve_awaitable(awaitable: Awaitable[T]) -> T:
    """Resolve on a dedicated loop without borrowing a Sync Playwright loop.

    Browser sessions using Playwright's synchronous API own the calling thread.
    LM calls are isolated to a separate event-loop thread so the browser never
    crosses thread boundaries while an async planner remains supported.
    """

    result: list[T] = []
    failure: list[BaseException] = []

    async def complete() -> T:
        return await awaitable

    def runner() -> None:
        try:
            result.append(asyncio.run(complete()))
        except BaseException as exc:  # preserve the original planner failure
            failure.append(exc)

    thread = Thread(target=runner, name="affordance-awaitable", daemon=False)
    thread.start()
    thread.join()
    if failure:
        raise failure[0]
    return result[0]
