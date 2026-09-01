import uuid
from types import SimpleNamespace

import pytest
from aio_pika import DeliveryMode

from app.core.config import Settings
from app.core.enums import JobSource
from app.core.exceptions import PublishError
from app.messaging.messages import CrawlJobMessage
from app.messaging.publisher import CrawlJobPublisher


class FakeExchange:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[tuple[object, str]] = []

    async def publish(self, message: object, routing_key: str) -> None:
        if self.error is not None:
            raise self.error
        self.published.append((message, routing_key))


def sample_message() -> CrawlJobMessage:
    return CrawlJobMessage(job_id=uuid.uuid4(), source=JobSource.HOCKEY)


class TestPublish:
    async def test_publish_before_connect_raises(self) -> None:
        publisher = CrawlJobPublisher(Settings())

        with pytest.raises(PublishError, match="not connected"):
            await publisher.publish(sample_message())

    async def test_message_is_persistent_json_with_routing_key(self) -> None:
        settings = Settings()
        publisher = CrawlJobPublisher(settings)
        exchange = FakeExchange()
        publisher._exchange = exchange  # type: ignore[assignment]
        message = sample_message()

        await publisher.publish(message)

        amqp_message, routing_key = exchange.published[0]
        assert routing_key == settings.crawl_routing_key
        assert amqp_message.content_type == "application/json"  # type: ignore[attr-defined]
        assert amqp_message.delivery_mode == DeliveryMode.PERSISTENT  # type: ignore[attr-defined]
        assert CrawlJobMessage.model_validate_json(amqp_message.body) == message  # type: ignore[attr-defined]

    async def test_broker_error_becomes_publish_error(self) -> None:
        publisher = CrawlJobPublisher(Settings())
        publisher._exchange = FakeExchange(error=TimeoutError("broker slow"))  # type: ignore[assignment]

        with pytest.raises(PublishError, match="broker slow"):
            await publisher.publish(sample_message())


class TestPing:
    async def test_ping_false_without_connection(self) -> None:
        assert await CrawlJobPublisher(Settings()).ping() is False

    async def test_ping_reflects_connection_state(self) -> None:
        publisher = CrawlJobPublisher(Settings())
        publisher._connection = SimpleNamespace(is_closed=False)  # type: ignore[assignment]
        assert await publisher.ping() is True

        publisher._connection = SimpleNamespace(is_closed=True)  # type: ignore[assignment]
        assert await publisher.ping() is False
