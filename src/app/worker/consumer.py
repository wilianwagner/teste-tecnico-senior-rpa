import time
from typing import Any

import pika
import pika.exceptions
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.messaging.messages import CrawlJobMessage
from app.messaging.topology import declare_topology_sync
from app.worker.processor import JobProcessor, ProcessOutcome

logger = get_logger(__name__)

RECONNECT_DELAY_SECONDS = 5.0
ERROR_BACKOFF_SECONDS = 1.0


class CrawlConsumer:
    def __init__(self, settings: Settings, processor: JobProcessor) -> None:
        self.settings = settings
        self.processor = processor
        self._stopping = False
        self._connection: pika.BlockingConnection | None = None
        self._channel: Any = None

    def request_stop(self) -> None:
        self._stopping = True
        connection, channel = self._connection, self._channel
        if connection is not None and connection.is_open and channel is not None:
            connection.add_callback_threadsafe(channel.stop_consuming)

    def run(self) -> None:
        while not self._stopping:
            try:
                self._consume()
            except pika.exceptions.AMQPError as exc:
                logger.warning("broker_connection_error", error=str(exc))
                self._interruptible_sleep(RECONNECT_DELAY_SECONDS)
        logger.info("worker_stopped")

    def _consume(self) -> None:
        connection = pika.BlockingConnection(pika.URLParameters(self.settings.rabbitmq_url))
        self._connection = connection
        channel = connection.channel()
        self._channel = channel

        try:
            declare_topology_sync(channel, self.settings)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=self.settings.crawl_queue, on_message_callback=self._on_message
            )
            logger.info("worker_consuming", queue=self.settings.crawl_queue)
            channel.start_consuming()
        finally:
            self._channel = None
            self._connection = None
            if connection.is_open:
                connection.close()

    def _on_message(self, channel: Any, method: Any, properties: Any, body: bytes) -> None:
        try:
            message = CrawlJobMessage.model_validate_json(body)
        except ValidationError as exc:
            logger.error("invalid_message_discarded", error=str(exc))
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        try:
            outcome = self.processor.process(message)
        except Exception:
            logger.exception("unexpected_processing_error", job_id=str(message.job_id))
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            self._interruptible_sleep(ERROR_BACKOFF_SECONDS)
            return

        logger.info("message_processed", job_id=str(message.job_id), outcome=outcome.value)
        if outcome in (ProcessOutcome.COMPLETED, ProcessOutcome.SKIPPED):
            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif outcome == ProcessOutcome.RETRY:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        else:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def _interruptible_sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self._stopping and time.monotonic() < deadline:
            time.sleep(0.2)
