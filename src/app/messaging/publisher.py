from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection
from aio_pika.exceptions import AMQPException

from app.core.config import Settings
from app.core.exceptions import PublishError
from app.core.logging import get_logger
from app.messaging.messages import CrawlJobMessage
from app.messaging.topology import declare_topology_async

logger = get_logger(__name__)


class SupportsPublish(Protocol):
    async def publish(self, message: CrawlJobMessage) -> None: ...


class CrawlJobPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        channel = await self._connection.channel()
        self._exchange = await declare_topology_async(channel, self.settings)
        logger.info("publisher_connected", exchange=self.settings.crawl_exchange)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._exchange = None

    async def publish(self, message: CrawlJobMessage) -> None:
        if self._exchange is None:
            raise PublishError("Publisher is not connected")

        amqp_message = aio_pika.Message(
            body=message.to_bytes(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        try:
            await self._exchange.publish(amqp_message, routing_key=self.settings.crawl_routing_key)
        except (AMQPException, ConnectionError, TimeoutError) as exc:
            raise PublishError(f"Failed to publish crawl job message: {exc}") from exc

    async def ping(self) -> bool:
        return self._connection is not None and not self._connection.is_closed
