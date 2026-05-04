from __future__ import annotations

from typing import Any

import dramatiq
import structlog
from core.settings import settings
from dramatiq.brokers.redis import RedisBroker

log = structlog.get_logger(__name__)


class DlqMiddleware(dramatiq.Middleware):
    """Routes exhausted messages to the dead-letter queue actor."""

    def after_process_message(
        self,
        broker: Any,
        message: Any,
        *,
        result: object = None,
        exception: BaseException | None = None,
    ) -> None:
        if exception is None:
            return

        retries = message.options.get("retries", 0)
        try:
            actor = broker.get_actor(message.actor_name)
            max_retries = int(actor.options.get("max_retries", 3))
        except Exception:
            max_retries = 3

        if retries >= max_retries - 1:
            from worker.dlq_handler import handle_dead_letter

            job_id = str(message.args[0]) if message.args else "unknown"
            handle_dead_letter.send(job_id, f"{type(exception).__name__}: {exception}")


def configure_broker() -> RedisBroker:
    """Set up the Dramatiq broker with Redis and DLQ middleware."""
    broker = RedisBroker(url=settings.redis_url)  # type: ignore[no-untyped-call]
    broker.add_middleware(DlqMiddleware())
    dramatiq.set_broker(broker)

    from worker.actors import conversion as _  # noqa: F401

    return broker
