import signal
from collections.abc import Iterator

import pytest

from app.worker import main as worker_main
from app.worker.consumer import CrawlConsumer


@pytest.fixture
def _restore_signal_handlers() -> Iterator[None]:
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    yield
    signal.signal(signal.SIGTERM, previous_term)
    signal.signal(signal.SIGINT, previous_int)


@pytest.mark.usefixtures("_restore_signal_handlers")
def test_main_wires_consumer_and_handles_shutdown_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[CrawlConsumer] = []
    monkeypatch.setattr(CrawlConsumer, "run", lambda self: started.append(self))

    worker_main.main()

    assert len(started) == 1
    term_handler = signal.getsignal(signal.SIGTERM)
    assert callable(term_handler)
    assert signal.getsignal(signal.SIGINT) is term_handler

    term_handler(signal.SIGTERM, None)
    assert started[0]._stopping is True
