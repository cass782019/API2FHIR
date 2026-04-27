from __future__ import annotations

import logging

import pytest


@pytest.mark.unit
def test_configure_logging_json_does_not_raise() -> None:
    from core.logging import configure_logging

    configure_logging("DEBUG", "json")


@pytest.mark.unit
def test_configure_logging_console_does_not_raise() -> None:
    from core.logging import configure_logging

    configure_logging("INFO", "console")


@pytest.mark.unit
def test_configure_logging_sets_root_level_warning() -> None:
    from core.logging import configure_logging

    configure_logging("WARNING", "json")
    assert logging.getLogger().level == logging.WARNING


@pytest.mark.unit
def test_configure_logging_sets_root_level_debug() -> None:
    from core.logging import configure_logging

    configure_logging("DEBUG", "console")
    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.unit
def test_configure_logging_replaces_handlers() -> None:
    from core.logging import configure_logging

    configure_logging("INFO", "json")
    initial_count = len(logging.getLogger().handlers)
    configure_logging("DEBUG", "json")
    # Should not accumulate handlers on repeated calls
    assert len(logging.getLogger().handlers) == initial_count


@pytest.mark.unit
def test_request_id_var_default() -> None:
    from core.logging import request_id_var

    assert request_id_var.get() == "-"


@pytest.mark.unit
def test_request_id_var_set_and_reset() -> None:
    from core.logging import request_id_var

    token = request_id_var.set("req-test-123")
    try:
        assert request_id_var.get() == "req-test-123"
    finally:
        request_id_var.reset(token)

    assert request_id_var.get() == "-"


@pytest.mark.unit
def test_request_id_var_independent_per_context() -> None:
    import contextvars

    from core.logging import request_id_var

    results: list[str] = []

    def task() -> None:
        token = request_id_var.set("task-id-abc")
        try:
            results.append(request_id_var.get())
        finally:
            request_id_var.reset(token)

    ctx = contextvars.copy_context()
    ctx.run(task)
    assert results == ["task-id-abc"]
    # Original context unaffected
    assert request_id_var.get() == "-"
