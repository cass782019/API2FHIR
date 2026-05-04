from __future__ import annotations

# StubBroker must be set before any worker module is imported.
import dramatiq
from dramatiq.brokers.stub import StubBroker

_stub_broker = StubBroker()
dramatiq.set_broker(_stub_broker)

import json  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def reset_broker() -> None:
    _stub_broker.flush_all()


@pytest.fixture
def mock_redis() -> MagicMock:
    r = MagicMock()
    r.set.return_value = True
    return r


@pytest.mark.unit
def test_handle_dead_letter_saves_failed_status(mock_redis: MagicMock) -> None:
    mock_redis.exists.return_value = 0  # no payload stored

    with patch("worker.dlq_handler._redis_client", return_value=mock_redis):
        from worker.dlq_handler import handle_dead_letter

        handle_dead_letter("job1", "RuntimeError: timeout")

    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "worker:result:job1"
    saved = json.loads(call_args[0][1])
    assert saved["status"] == "failed"
    assert "RuntimeError" in saved["error"]


@pytest.mark.unit
def test_handle_dead_letter_status_is_failed(mock_redis: MagicMock) -> None:
    mock_redis.exists.return_value = 0

    with patch("worker.dlq_handler._redis_client", return_value=mock_redis):
        from worker.dlq_handler import handle_dead_letter

        handle_dead_letter("job2", "some error")

    call_args = mock_redis.set.call_args
    saved = json.loads(call_args[0][1])
    assert saved["status"] == "failed"


@pytest.mark.unit
def test_handle_dead_letter_replayable_true_when_payload_exists(mock_redis: MagicMock) -> None:
    """DLQ sets replayable=True when worker:payload:{job_id} exists in Redis."""
    mock_redis.exists.return_value = 1  # payload present

    with patch("worker.dlq_handler._redis_client", return_value=mock_redis):
        from worker.dlq_handler import handle_dead_letter

        handle_dead_letter("job_replay", "RuntimeError: oops")

    call_args = mock_redis.set.call_args
    saved = json.loads(call_args[0][1])
    assert saved["replayable"] is True


@pytest.mark.unit
def test_handle_dead_letter_replayable_false_when_no_payload(mock_redis: MagicMock) -> None:
    """DLQ sets replayable=False when worker:payload:{job_id} is absent."""
    mock_redis.exists.return_value = 0

    with patch("worker.dlq_handler._redis_client", return_value=mock_redis):
        from worker.dlq_handler import handle_dead_letter

        handle_dead_letter("job_no_payload", "some error")

    call_args = mock_redis.set.call_args
    saved = json.loads(call_args[0][1])
    assert saved["replayable"] is False


@pytest.mark.unit
def test_dlq_middleware_sends_after_max_retries() -> None:
    from worker.main import DlqMiddleware

    middleware = DlqMiddleware()
    broker = MagicMock()
    actor = MagicMock()
    actor.options = {"max_retries": 3}
    broker.get_actor.return_value = actor

    message = MagicMock()
    message.options = {"retries": 2}  # 3rd attempt (0-indexed) = last retry
    message.args = ("job123",)
    message.actor_name = "convert_spec_actor"

    with patch("worker.dlq_handler.handle_dead_letter") as mock_dlq:
        middleware.after_process_message(
            broker, message, exception=ValueError("timeout")
        )

    mock_dlq.send.assert_called_once_with("job123", "ValueError: timeout")


@pytest.mark.unit
def test_dlq_middleware_no_send_on_success() -> None:
    from worker.main import DlqMiddleware

    middleware = DlqMiddleware()
    broker = MagicMock()
    message = MagicMock()

    with patch("worker.dlq_handler.handle_dead_letter") as mock_dlq:
        middleware.after_process_message(broker, message, result="ok", exception=None)

    mock_dlq.send.assert_not_called()


@pytest.mark.unit
def test_dlq_middleware_no_send_before_max_retries() -> None:
    from worker.main import DlqMiddleware

    middleware = DlqMiddleware()
    broker = MagicMock()
    actor = MagicMock()
    actor.options = {"max_retries": 3}
    broker.get_actor.return_value = actor

    message = MagicMock()
    message.options = {"retries": 0}  # first failure, 2 retries remain
    message.args = ("job456",)
    message.actor_name = "convert_spec_actor"

    with patch("worker.dlq_handler.handle_dead_letter") as mock_dlq:
        middleware.after_process_message(
            broker, message, exception=RuntimeError("network error")
        )

    mock_dlq.send.assert_not_called()


@pytest.mark.unit
def test_dlq_middleware_sends_on_exactly_third_failure() -> None:
    """Gate 7: DLQ receives after 3 failures (retries index 2 with max_retries=3)."""
    from worker.main import DlqMiddleware

    middleware = DlqMiddleware()
    broker = MagicMock()
    actor = MagicMock()
    actor.options = {"max_retries": 3}
    broker.get_actor.return_value = actor

    with patch("worker.dlq_handler.handle_dead_letter") as mock_dlq:
        for retry_index in range(3):
            message = MagicMock()
            message.options = {"retries": retry_index}
            message.args = ("job789",)
            message.actor_name = "convert_spec_actor"
            middleware.after_process_message(
                broker, message, exception=OSError("fail")
            )

    # Only the third failure (retries=2) should trigger the DLQ
    mock_dlq.send.assert_called_once()
    assert mock_dlq.send.call_args[0][0] == "job789"


@pytest.mark.unit
def test_dlq_middleware_fallback_max_retries_is_3() -> None:
    """Fallback para actors sem max_retries declarado deve ser 3, não 21."""
    from worker.main import DlqMiddleware

    middleware = DlqMiddleware()
    broker = MagicMock()
    actor = MagicMock()
    actor.options = {}  # sem max_retries declarado
    broker.get_actor.return_value = actor

    message = MagicMock()
    message.args = ("job-fallback",)
    message.actor_name = "unknown_actor"

    # retries=1 → ainda não no limite (fallback=3, limite em retries=2)
    message.options = {"retries": 1}
    with patch("worker.dlq_handler.handle_dead_letter") as mock_dlq:
        middleware.after_process_message(broker, message, exception=RuntimeError("x"))
    mock_dlq.send.assert_not_called()

    # retries=2 → terceira falha com fallback=3, deve disparar DLQ
    message.options = {"retries": 2}
    with patch("worker.dlq_handler.handle_dead_letter") as mock_dlq:
        middleware.after_process_message(broker, message, exception=RuntimeError("x"))
    mock_dlq.send.assert_called_once()
