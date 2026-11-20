"""Asking another server, safely. GovWren reaches out only where it is configured to: webhooks,
a model registry, and an assistant's model server. Each call is bounded in time as a whole,
is read up to a limit, and follows no redirect, which could point anywhere and would carry
any key the request holds."""

from __future__ import annotations

import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A server that answers with a redirect is not followed."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(NoRedirect)


def read_within(answer: Any, limit: int, seconds: float) -> bytes:
    """Read an answer, refusing one that takes longer than ``seconds`` in all, however slowly
    it trickles in, or that is longer than ``limit`` bytes."""
    deadline = time.monotonic() + seconds
    parts: list[bytes] = []
    size = 0
    while size <= limit:
        if time.monotonic() > deadline:
            raise TimeoutError("The answer took too long.")
        part = answer.read(min(65_536, limit + 1 - size))
        if not part:
            break
        parts.append(part)
        size += len(part)
    if size > limit:
        raise ValueError("The answer is too long.")
    return b"".join(parts)


def within[T](seconds: float, call: Callable[[], T]) -> T:
    """Run a call that talks to another server, giving up after ``seconds`` in all. A
    server that answers a byte at a time cannot hold the caller, or the scheduled work
    behind it, for longer than that."""
    result: list[T] = []
    failure: list[BaseException] = []

    def run() -> None:
        try:
            result.append(call())
        except BaseException as exc:  # handed back to the caller below
            failure.append(exc)

    worker = threading.Thread(target=run, name="govwren-net", daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise TimeoutError(f"No answer within {seconds:g} seconds.")
    if failure:
        raise failure[0]
    return result[0]
