from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


async def wait_until(
    pilot: Any,
    predicate: Callable[[], bool],
    timeout: float = 5.0,
    message: str = "Timed out waiting for condition",
) -> None:
    """Loop pilot.pause(0.05) until predicate() is true or raise AssertionError."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        await pilot.pause(0.05)


async def wait_for_screen(
    pilot: Any,
    app: Any,
    screen_cls: type[Any],
    timeout: float = 5.0,
) -> None:
    """Wait until app.screen is an instance of screen_cls and is mounted."""
    await wait_until(
        pilot,
        lambda: isinstance(app.screen, screen_cls) and app.screen.is_mounted,
        timeout=timeout,
        message=f"Timed out waiting for mounted {screen_cls.__name__}",
    )
