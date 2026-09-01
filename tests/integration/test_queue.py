import time
import uuid
from typing import Any

import pika
import pytest

from app.core.config import Settings
from app.core.enums import JobSource
from app.messaging.messages import CrawlJobMessage
from app.messaging.publisher import CrawlJobPublisher
from app.messaging.topology import declare_topology_sync

pytestmark = pytest.mark.integration


def basic_get_with_retry(
    channel: Any, queue: str, *, timeout: float = 10.0, auto_ack: bool = True
) -> tuple[Any, Any, bytes]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        method, properties, body = channel.basic_get(queue, auto_ack=auto_ack)
        if method is not None:
            return method, properties, body
        time.sleep(0.1)
    raise AssertionError(f"No message arrived in queue {queue!r} within {timeout}s")


async def test_published_message_reaches_queue_with_persistence(
    integration_settings: Settings,
) -> None:
    publisher = CrawlJobPublisher(integration_settings)
    await publisher.connect()
    message = CrawlJobMessage(job_id=uuid.uuid4(), source=JobSource.HOCKEY)
    try:
        await publisher.publish(message)
    finally:
        await publisher.close()

    connection = pika.BlockingConnection(pika.URLParameters(integration_settings.rabbitmq_url))
    try:
        channel = connection.channel()
        _, properties, body = basic_get_with_retry(channel, integration_settings.crawl_queue)

        assert CrawlJobMessage.model_validate_json(body) == message
        assert properties.delivery_mode == 2
        assert properties.content_type == "application/json"
    finally:
        connection.close()


def test_rejected_message_is_routed_to_dead_letter_queue(
    integration_settings: Settings,
) -> None:
    connection = pika.BlockingConnection(pika.URLParameters(integration_settings.rabbitmq_url))
    try:
        channel = connection.channel()
        declare_topology_sync(channel, integration_settings)
        message = CrawlJobMessage(job_id=uuid.uuid4(), source=JobSource.OSCAR)
        channel.basic_publish(
            exchange=integration_settings.crawl_exchange,
            routing_key=integration_settings.crawl_routing_key,
            body=message.to_bytes(),
            properties=pika.BasicProperties(delivery_mode=2),
        )

        method, _, _ = basic_get_with_retry(
            channel, integration_settings.crawl_queue, auto_ack=False
        )
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        _, _, dead_body = basic_get_with_retry(channel, integration_settings.crawl_dlq)
        assert CrawlJobMessage.model_validate_json(dead_body) == message
    finally:
        connection.close()


def test_requeued_message_is_redelivered(integration_settings: Settings) -> None:
    connection = pika.BlockingConnection(pika.URLParameters(integration_settings.rabbitmq_url))
    try:
        channel = connection.channel()
        declare_topology_sync(channel, integration_settings)
        message = CrawlJobMessage(job_id=uuid.uuid4(), source=JobSource.ALL)
        channel.basic_publish(
            exchange=integration_settings.crawl_exchange,
            routing_key=integration_settings.crawl_routing_key,
            body=message.to_bytes(),
            properties=pika.BasicProperties(delivery_mode=2),
        )

        method, _, _ = basic_get_with_retry(
            channel, integration_settings.crawl_queue, auto_ack=False
        )
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        redelivered_method, _, body = basic_get_with_retry(
            channel, integration_settings.crawl_queue, auto_ack=True
        )
        assert redelivered_method.redelivered
        assert CrawlJobMessage.model_validate_json(body) == message
    finally:
        connection.close()
