from typing import Any

from app.core.config import Settings
from app.messaging.topology import declare_topology_sync


class FakeChannel:
    def __init__(self) -> None:
        self.exchanges: dict[str, dict[str, Any]] = {}
        self.queues: dict[str, dict[str, Any]] = {}
        self.bindings: list[tuple[str, str, str]] = []

    def exchange_declare(self, exchange: str, exchange_type: str, durable: bool) -> None:
        self.exchanges[exchange] = {"type": exchange_type, "durable": durable}

    def queue_declare(
        self, queue: str, durable: bool, arguments: dict[str, str] | None = None
    ) -> None:
        self.queues[queue] = {"durable": durable, "arguments": arguments or {}}

    def queue_bind(self, queue: str, exchange: str, routing_key: str) -> None:
        self.bindings.append((queue, exchange, routing_key))


class TestDeclareTopologySync:
    def test_declares_durable_exchanges_and_queues(self) -> None:
        settings = Settings()
        channel = FakeChannel()

        declare_topology_sync(channel, settings)

        assert channel.exchanges[settings.crawl_exchange] == {"type": "direct", "durable": True}
        assert channel.exchanges[settings.crawl_dlx] == {"type": "direct", "durable": True}
        assert channel.queues[settings.crawl_queue]["durable"] is True
        assert channel.queues[settings.crawl_dlq]["durable"] is True

    def test_main_queue_dead_letters_into_dlx(self) -> None:
        settings = Settings()
        channel = FakeChannel()

        declare_topology_sync(channel, settings)

        assert channel.queues[settings.crawl_queue]["arguments"] == {
            "x-dead-letter-exchange": settings.crawl_dlx,
            "x-dead-letter-routing-key": settings.crawl_routing_key,
        }
        assert (
            settings.crawl_queue,
            settings.crawl_exchange,
            settings.crawl_routing_key,
        ) in channel.bindings
        assert (
            settings.crawl_dlq,
            settings.crawl_dlx,
            settings.crawl_routing_key,
        ) in channel.bindings
