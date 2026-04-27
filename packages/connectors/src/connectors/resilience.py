from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

import pybreaker
import tenacity

_T = TypeVar("_T")


# Pre-configured circuit breaker for FHIR service calls.
# Opens after 5 consecutive failures; resets after 60 s.
fhir_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="fhir",
)


def retry_async(
    *,
    attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    reraise: bool = True,
) -> Callable[[Callable[..., Coroutine[Any, Any, _T]]], Callable[..., Coroutine[Any, Any, _T]]]:
    """Decorator: retry an async function with exponential back-off.

    Args:
        attempts: Maximum number of total attempts (including first try).
        wait_min: Minimum wait between retries in seconds.
        wait_max: Maximum wait between retries in seconds.
        reraise: If True, re-raise the last exception after all retries.
    """
    return tenacity.retry(
        stop=tenacity.stop_after_attempt(attempts),
        wait=tenacity.wait_exponential(min=wait_min, max=wait_max),
        reraise=reraise,
        retry=tenacity.retry_if_exception_type(Exception),
    )


class AsyncCircuitBreaker:
    """Thin async wrapper around pybreaker.CircuitBreaker.

    pybreaker's ``call`` method is synchronous; this wrapper makes it
    awaitable so it can be used in async contexts without blocking the
    event loop.
    """

    def __init__(self, breaker: pybreaker.CircuitBreaker) -> None:
        self._breaker = breaker

    @property
    def current_state(self) -> str:
        return str(self._breaker.current_state)

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, _T]],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        """Execute *func* through the circuit breaker."""
        loop = asyncio.get_event_loop()
        result: _T = await loop.run_in_executor(
            None,
            lambda: self._breaker.call(asyncio.run, func(*args, **kwargs)),
        )
        return result
