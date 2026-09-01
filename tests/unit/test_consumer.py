import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.core.enums import JobSource
from app.messaging.messages import CrawlJobMessage
from app.worker.consumer import CrawlConsumer
from app.worker.processor import ProcessOutcome


class FakeChannel:
    def __init__(self) -> None:
        self.acks: list[int] = []
        self.nacks: list[tuple[int, bool]] = []

    def basic_ack(self, delivery_tag: int) -> None:
        self.acks.append(delivery_tag)

    def basic_nack(self, delivery_tag: int, requeue: bool) -> None:
        self.nacks.append((delivery_tag, requeue))


class FakeProcessor:
    def __init__(self, outcome: ProcessOutcome | None = None, error: Exception | None = None):
        self.outcome = outcome
        self.error = error
        self.messages: list[CrawlJobMessage] = []

    def process(self, message: CrawlJobMessage) -> ProcessOutcome:
        self.messages.append(message)
        if self.error is not None:
            raise self.error
        assert self.outcome is not None
        return self.outcome


def build_consumer(processor: FakeProcessor) -> CrawlConsumer:
    return CrawlConsumer(Settings(), processor)  # type: ignore[arg-type]


def deliver(consumer: CrawlConsumer, channel: FakeChannel, body: bytes, tag: int = 7) -> None:
    method = SimpleNamespace(delivery_tag=tag)
    consumer._on_message(channel, method, None, body)


def message_body() -> bytes:
    return CrawlJobMessage(job_id=uuid.uuid4(), source=JobSource.HOCKEY).to_bytes()


class TestOnMessage:
    @pytest.mark.parametrize("outcome", [ProcessOutcome.COMPLETED, ProcessOutcome.SKIPPED])
    def test_ack_on_terminal_success(self, outcome: ProcessOutcome) -> None:
        processor = FakeProcessor(outcome=outcome)
        channel = FakeChannel()

        deliver(build_consumer(processor), channel, message_body())

        assert channel.acks == [7]
        assert channel.nacks == []

    def test_requeue_on_retry(self) -> None:
        processor = FakeProcessor(outcome=ProcessOutcome.RETRY)
        channel = FakeChannel()

        deliver(build_consumer(processor), channel, message_body())

        assert channel.acks == []
        assert channel.nacks == [(7, True)]

    def test_dead_letter_on_final_failure(self) -> None:
        processor = FakeProcessor(outcome=ProcessOutcome.FAILED)
        channel = FakeChannel()

        deliver(build_consumer(processor), channel, message_body())

        assert channel.nacks == [(7, False)]

    def test_invalid_payload_goes_to_dead_letter_without_processing(self) -> None:
        processor = FakeProcessor(outcome=ProcessOutcome.COMPLETED)
        channel = FakeChannel()
        body = json.dumps({"job_id": "not-a-uuid", "source": "unknown"}).encode()

        deliver(build_consumer(processor), channel, body)

        assert processor.messages == []
        assert channel.nacks == [(7, False)]

    def test_unexpected_processor_error_requeues_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        processor = FakeProcessor(error=RuntimeError("database is down"))
        channel = FakeChannel()
        consumer = build_consumer(processor)
        sleeps: list[float] = []
        monkeypatch.setattr(consumer, "_interruptible_sleep", sleeps.append)

        deliver(consumer, channel, message_body())

        assert channel.nacks == [(7, True)]
        assert sleeps, "expected a backoff sleep after unexpected errors"

    def test_message_payload_reaches_processor(self) -> None:
        processor = FakeProcessor(outcome=ProcessOutcome.COMPLETED)
        job_id = uuid.uuid4()
        body = CrawlJobMessage(job_id=job_id, source=JobSource.ALL).to_bytes()

        deliver(build_consumer(processor), FakeChannel(), body)

        assert processor.messages[0].job_id == job_id
        assert processor.messages[0].source == JobSource.ALL


def test_message_roundtrip_serialization() -> None:
    message = CrawlJobMessage(job_id=uuid.uuid4(), source=JobSource.OSCAR)

    decoded = CrawlJobMessage.model_validate_json(message.to_bytes())

    assert decoded == message
    payload: dict[str, Any] = json.loads(message.to_bytes())
    assert payload == {"job_id": str(message.job_id), "source": "oscar"}
