from typing import Any

from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractExchange

from app.core.config import Settings


def _queue_arguments(settings: Settings) -> dict[str, str]:
    return {
        "x-dead-letter-exchange": settings.crawl_dlx,
        "x-dead-letter-routing-key": settings.crawl_routing_key,
    }


def declare_topology_sync(channel: Any, settings: Settings) -> None:
    channel.exchange_declare(settings.crawl_dlx, exchange_type="direct", durable=True)
    channel.queue_declare(settings.crawl_dlq, durable=True)
    channel.queue_bind(
        settings.crawl_dlq, settings.crawl_dlx, routing_key=settings.crawl_routing_key
    )

    channel.exchange_declare(settings.crawl_exchange, exchange_type="direct", durable=True)
    channel.queue_declare(settings.crawl_queue, durable=True, arguments=_queue_arguments(settings))
    channel.queue_bind(
        settings.crawl_queue, settings.crawl_exchange, routing_key=settings.crawl_routing_key
    )


async def declare_topology_async(channel: AbstractChannel, settings: Settings) -> AbstractExchange:
    dlx = await channel.declare_exchange(settings.crawl_dlx, ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(settings.crawl_dlq, durable=True)
    await dlq.bind(dlx, routing_key=settings.crawl_routing_key)

    exchange = await channel.declare_exchange(
        settings.crawl_exchange, ExchangeType.DIRECT, durable=True
    )
    queue = await channel.declare_queue(
        settings.crawl_queue, durable=True, arguments=dict(_queue_arguments(settings))
    )
    await queue.bind(exchange, routing_key=settings.crawl_routing_key)
    return exchange
