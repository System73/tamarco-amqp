import logging
import uuid
from asyncio import Future, wait_for

from tamarco.resources.bases import OutputBase

from tamarco_amqp.settings import (
    REQUEST_TIMEOUT_SECONDS,
    publish_subscribe_queue_prefix,
    push_pull_queue_prefix,
    request_response_queue_prefix,
)

DELIVERY_PERSISTENT = 2  # make message persistent
DELIVERY_NO_PERSISTENT = 1  # make message no persistent

logger = logging.getLogger("tamarco.amqp")


class ClientPatternsMixin:
    """Implement all the clients patterns."""

    responses = {}

    def __init__(self, *args, **kwargs):
        self.connection = None
        self.queues_prefix = ""
        super().__init__(*args, **kwargs)

    def set_queues_prefix(self, name):
        """Set deploy name queue prefix.

        Args:
            name (str): Name of the prefix.
        """
        if name != "":
            self.queues_prefix = f"{name}."

    def set_connection(self, connection):
        if not self.connection:
            self.connection = connection
        else:
            raise Exception("The output already have a connection")

    async def _initialize_response_queue(self):
        """Initialize the queue for the response of the request.
        Internal method to implement the request response pattern.
        """
        result = await self.connection._channel.queue_declare(exclusive=True)

        self.callback_queue = result["queue"]

        await self.connection._channel.basic_consume(
            callback=self._on_response, no_ack=True, queue_name=self.callback_queue
        )

    async def _on_response(self, channel, body, envelope, properties):
        """Handle the response of the request response pattern.
        It is a handler of the response queue, when the response arrives sets the result to the proper future that its
        returned by the request.
        """
        try:
            future = self.responses[properties.correlation_id]
        except KeyError:
            logger.warning(f"Received not expected request response with id {properties.correlation_id}")
        else:
            if not future.cancelled():
                future.set_result(body)
            else:
                logger.warning(f"Request response future {future} cancelled. Getting result now")
            del self.responses[properties.correlation_id]

    async def push(self, message: str, queue: str, codec=None):
        """Implementation of the push pattern.

        Args:
            message: message to push.
            queue: queue name where the message should be pushed.
        """
        encoded_message = self.encode_message(message, codec=codec)
        routing_key = self.queues_prefix + push_pull_queue_prefix + queue
        logger.debug(f"Pushing message {message} to {routing_key}")
        await self.connection._publish(
            exchange="",
            routing_key=routing_key,
            body=encoded_message,
            properties={"delivery_mode": DELIVERY_PERSISTENT},
        )

    async def publish(self, message: str, queue: str, codec=None):
        """Implementation of the publish pattern.

        Args:
            message: Message to publish.
            queue: Queue name where the message should be published.
        """
        encoded_message = self.encode_message(message, codec=codec)
        exchange = self.queues_prefix + publish_subscribe_queue_prefix + queue
        logger.debug(f"Publishing message {message} to {exchange}")
        await self.connection._publish(
            exchange=exchange,
            routing_key="",
            body=encoded_message,
            properties={"delivery_mode": DELIVERY_NO_PERSISTENT},
        )

    async def request(self, message: str, queue: str, codec=None):
        """Implementation of the request pattern.

        Args:
            message: Message with the request.
            queue: Queue name where the request should be send.

        Returns:
            str: Response.

        Raises:
            TimeoutError: Timeout of the response.
        """
        request_id = str(uuid.uuid4())
        routing_key = self.queues_prefix + request_response_queue_prefix + queue
        logger.debug(f"Request message {message} to {routing_key}")
        encoded_message = self.encode_message(message, codec=codec)
        await self.connection._publish(
            exchange="",
            routing_key=routing_key,
            properties={"reply_to": self.callback_queue, "correlation_id": request_id},
            body=encoded_message,
        )
        future = Future()
        self.responses[request_id] = future
        response = await wait_for(future, REQUEST_TIMEOUT_SECONDS)
        decoded_response = self.decode_message(response, codec=codec)
        return decoded_response

    def encode_message(self, message, codec=None):
        if codec:
            codec_to_use = codec
        elif self.codec:
            codec_to_use = self.codec
        else:
            return message
        try:
            return codec_to_use.encode(message)
        except Exception:
            logger.warning(f"Unexpected exception encoding the message {message} in AMQP client", exc_info=True)
            raise

    def decode_message(self, message, codec=None):
        if codec:
            codec_to_use = codec
        elif self.codec:
            codec_to_use = self.codec
        else:
            return message
        try:
            return codec_to_use.decode(message)
        except Exception:
            logger.warning(f"Unexpected exception decoding the message {message} in AMQP client", exc_info=True)
            raise


class AMQPOutput(ClientPatternsMixin, OutputBase):
    queue = None

    def __init__(self, queue, *args, **kwargs):
        self.queue = queue
        if "name" not in kwargs:
            kwargs["name"] = queue
        super().__init__(*args, **kwargs)

    async def initialize(self):
        """Initialize the queues needed by this client."""
        await self._initialize_response_queue()

    def get_full_queue_name(self):
        return self.queues_prefix + self.queue

    async def push(self, message):
        await super().push(message, queue=self.queue)

    async def publish(self, message):
        await super().publish(message, queue=self.queue)

    async def request(self, message):
        response = await super().request(message, queue=self.queue)
        return response


class AMQPGenericOutput(ClientPatternsMixin, OutputBase):
    """Output where you can change."""

    def __init__(self, *args, **kwargs):
        kwargs["name"] = "generic"
        super().__init__(*args, **kwargs)

    async def initialize(self):
        """Initialize the queues needed by this client."""
        pass

    async def request(self, message, queue):
        raise NotImplementedError(
            "The Generic output can't be used with the request response pattern. Use the " "standard AMQPOutput"
        )
