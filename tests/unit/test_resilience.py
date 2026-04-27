from __future__ import annotations

import pybreaker
import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_succeeds_after_two_failures() -> None:
    from connectors.resilience import retry_async

    call_count = 0

    @retry_async(attempts=3, wait_min=0, wait_max=0)
    async def flaky() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("temporary failure")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_reraises_after_all_attempts() -> None:
    from connectors.resilience import retry_async

    call_count = 0

    @retry_async(attempts=2, wait_min=0, wait_max=0)
    async def always_fails() -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("permanent failure")

    with pytest.raises(RuntimeError, match="permanent failure"):
        await always_fails()

    assert call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_first_attempt_succeeds_no_retry() -> None:
    from connectors.resilience import retry_async

    call_count = 0

    @retry_async(attempts=3, wait_min=0, wait_max=0)
    async def always_ok() -> int:
        nonlocal call_count
        call_count += 1
        return 42

    result = await always_ok()
    assert result == 42
    assert call_count == 1


@pytest.mark.unit
def test_circuit_breaker_opens_after_fail_max() -> None:
    # fail_max=2: first 2 calls raise IOError; circuit opens on 2nd failure.
    # The 3rd call raises CircuitBreakerError (circuit is already open).
    breaker = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=60, name="test-open")

    def fail() -> None:
        raise OSError("connection refused")

    # First call: IOError, count=1, closed.
    with pytest.raises(IOError):
        breaker.call(fail)
    # Second call: IOError triggers open transition → CircuitBreakerError.
    with pytest.raises((IOError, pybreaker.CircuitBreakerError)):
        breaker.call(fail)

    assert breaker.current_state == "open"


@pytest.mark.unit
def test_circuit_breaker_raises_open_error_when_open() -> None:
    breaker = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=60, name="test-open-error")

    def fail() -> None:
        raise OSError("connection refused")

    # Open the breaker (2 failures required).
    with pytest.raises(IOError):
        breaker.call(fail)
    with pytest.raises((IOError, pybreaker.CircuitBreakerError)):
        breaker.call(fail)

    # Circuit is open: further calls immediately raise CircuitBreakerError.
    with pytest.raises(pybreaker.CircuitBreakerError):
        breaker.call(fail)


@pytest.mark.unit
def test_circuit_breaker_resets_on_success() -> None:
    breaker = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=0, name="test-reset")

    def fail() -> None:
        raise OSError("error")

    def succeed() -> str:
        return "ok"

    # Open the breaker (2 failures).
    with pytest.raises(IOError):
        breaker.call(fail)
    with pytest.raises((IOError, pybreaker.CircuitBreakerError)):
        breaker.call(fail)

    assert breaker.current_state == "open"

    # Manually move to half-open by resetting the timeout
    breaker._state_storage.opened_at = None  # type: ignore[attr-defined]

    result = breaker.call(succeed)
    assert result == "ok"
    assert breaker.current_state == "closed"


@pytest.mark.unit
def test_fhir_circuit_breaker_is_configured() -> None:
    from connectors.resilience import fhir_circuit_breaker

    assert fhir_circuit_breaker.fail_max == 5
    assert fhir_circuit_breaker.reset_timeout == 60
