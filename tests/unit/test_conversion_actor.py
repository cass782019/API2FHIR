from __future__ import annotations

# StubBroker must be set before any worker module is imported so that the
# @dramatiq.actor decorator can register actors at decoration time.
import dramatiq
from dramatiq.brokers.stub import StubBroker

_stub_broker = StubBroker()
dramatiq.set_broker(_stub_broker)

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def reset_broker() -> None:
    _stub_broker.flush_all()


@pytest.fixture
def mock_redis() -> MagicMock:
    r = MagicMock()
    r.set.return_value = True  # NX acquired on first call
    r.delete.return_value = 1
    return r


@pytest.mark.unit
def test_actor_calls_convert_with_correct_args(mock_redis: MagicMock) -> None:
    bundle = {"resourceType": "Bundle", "id": "b1"}

    with (
        patch("worker.actors.conversion._redis_client", return_value=mock_redis),
        patch("worker.actors.conversion.parse_spec"),
        patch("worker.actors.conversion.fhir_service_convert", new=AsyncMock(return_value=bundle)),
        patch("worker.actors.conversion.anthropic.AsyncAnthropic"),
    ):
        from worker.actors.conversion import convert_spec_actor

        convert_spec_actor("job1", "openapi: '3.0.0'")

    # Lock acquired and result stored
    mock_redis.set.assert_called()


@pytest.mark.unit
def test_actor_idempotency_skips_duplicate_job(mock_redis: MagicMock) -> None:
    mock_redis.set.return_value = None  # NX not acquired — job already running

    with (
        patch("worker.actors.conversion._redis_client", return_value=mock_redis),
        patch("worker.actors.conversion.fhir_service_convert", new=AsyncMock()) as mock_convert,
    ):
        from worker.actors.conversion import convert_spec_actor

        convert_spec_actor("job_dup", "openapi: '3.0.0'")

    mock_convert.assert_not_called()


@pytest.mark.unit
def test_actor_saves_result_on_success(mock_redis: MagicMock) -> None:
    bundle = {"resourceType": "Bundle"}

    with (
        patch("worker.actors.conversion._redis_client", return_value=mock_redis),
        patch("worker.actors.conversion.parse_spec"),
        patch("worker.actors.conversion.fhir_service_convert", new=AsyncMock(return_value=bundle)),
        patch("worker.actors.conversion.anthropic.AsyncAnthropic"),
    ):
        from worker.actors.conversion import convert_spec_actor

        convert_spec_actor("job2", "spec: v1")

    calls = [str(c) for c in mock_redis.set.call_args_list]
    assert any("worker:result:job2" in c for c in calls)


@pytest.mark.unit
def test_actor_releases_lock_on_failure(mock_redis: MagicMock) -> None:
    with (
        patch("worker.actors.conversion._redis_client", return_value=mock_redis),
        patch("worker.actors.conversion.parse_spec", side_effect=RuntimeError("parse error")),
    ):
        from worker.actors.conversion import convert_spec_actor

        with pytest.raises(RuntimeError, match="parse error"):
            convert_spec_actor("job3", "bad spec")

    mock_redis.delete.assert_called_once_with("worker:lock:job3")


@pytest.mark.unit
def test_actor_propagates_exception_for_retry(mock_redis: MagicMock) -> None:
    with (
        patch("worker.actors.conversion._redis_client", return_value=mock_redis),
        patch("worker.actors.conversion.parse_spec", side_effect=ValueError("spec invalid")),
    ):
        from worker.actors.conversion import convert_spec_actor

        with pytest.raises(ValueError, match="spec invalid"):
            convert_spec_actor("job4", "invalid")
