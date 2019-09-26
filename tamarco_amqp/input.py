import asyncio
import logging
import uuid

from tamarco.resources.bases import InputBase

from tamarco_amqp import settings

DELIVERY_PERSISTENT = 2  # make message persistent
DELIVERY_NO_PERSISTENT = 1  # make message no persistent

logger = logging.getLogger("tamarco.amqp")


class AMQPInputMixing(InputBase):
    def __init__(self, queue: str, *args, **kwargs):
        self.loop = None
        self.connection = None
        self.messages = None
        self.queues_prefix = ""
        self.queue = queue
        self.tag = str(uuid.uuid4())
        if "name" not in kwargs:
            kwargs["name"] = queue
        super().__init__(*args, **kwargs)

    def get_full_queue_name(self):
        return self.queues_prefix + self.queue_prefix + self.queue

    def set_queues_prefix(self, name):
        """Set deploy name queue prefix.

        Args:
            name (str): Name of the prefix.
        """
        if name != "":
            self.queues_prefix = f"{name}."

    def set_loop(self, loop):
        self.loop = loop
        self._initialize_messages_queue(loop)

    def _initialize_messages_queue(self, loop):
        self.messages = asyncio.Queue(loop=loop)

    def set_connection(self, connection):
        self.connection = connection

    async def callback_trigger(self, task_manager):
        """Open one task every time that a message is received.

        Args:
            task_manager: Task manager that manages the open tasks.
        """
        async for message in self:
            task_name = "message_handler_" + str(uuid.uuid4())
            if self.resource:
                task_manager.start_task(task_name, self.on_message_callback(self.resource.microservice, message))
            else:
                task_manager.start_task(task_name, self.on_message_callback(message))

    def decode_message(self, message):
        if self.codec:
            return self.codec.decode(message)
        else:
            return message

    def encode_message(self, message):
        if self.codec:
            return self.codec.encode(message)
        else:
            return message


class AsyncIterMixing:
    """Implement the asynchronous iterator interface for the inputs."""

    async def handle_delivery(self, channel, body, envelope, properties):
        await self.messages.put(body)

    async def __anext__(self):
        while True:
            try:
                message = await self.messages.get()
                decoded_message = self.decode_message(message)
                logger.debug(f"Consumed message from AMQPInput. Queue: {self.queue}. Message: {decoded_message}")
                return decoded_message
            except Exception:
                logger.warning(
                    f"Unexpected exception consuming message in AMQPInput. Queue: {self.queue}", exc_info=True
                )


class AsyncIterResponseMixing:
    """Implement the asynchronous iterator interface."""

    async def handle_delivery(self, channel, body, envelope, properties):
        await self.messages.put([body, properties])

    async def __anext__(self):
        while True:
            try:
                message, properties = await self.messages.get()
                decoded_message = self.decode_message(message)
                logger.debug(f"Consumed message from AMQPInput. Queue: {self.queue}. Message: {decoded_message}")
                response_handler = Response(self, properties)
                return decoded_message, response_handler
            except Exception:
                logger.warning(
                    f"Unexpected exception consuming message in AMQPInput. Queue: {self.queue}. " f"Message: {message}",
                    exc_info=True,
                )


class AMQPPullInput(AsyncIterMixing, AMQPInputMixing, InputBase):
    """Consumer of a Push Pull pattern.
    The subclasses should override the pull coroutine.
    """

    queue_prefix = settings.push_pull_queue_prefix


class AMQPSubscriptionInput(AsyncIterMixing, AMQPInputMixing, InputBase):
    """Consumer of a Publish Subscribe pattern.
    His subclasses should override the on_message coroutine.
    """

    queue_prefix = settings.publish_subscribe_queue_prefix


class Response:
    def __init__(self, new_input, properties):
        self._input = new_input
        self._properties = properties

    async def send_response(self, message):
        """Send the response to a request.

        Args:
            message: Response message.
        """
        encoded_message = self._input.encode_message(message)
        await self._input._send_response(
            channel=None, body=None, envelope=None, properties=self._properties, response=encoded_message
        )


class AMQPRequestInput(AMQPInputMixing, AsyncIterResponseMixing, InputBase):
    """Consumer of a Request Response pattern.
    His subclasses should override the serve coroutine.
    """

    queue_prefix = settings.request_response_queue_prefix

    async def _send_response(self, channel, body, envelope, properties, response):
        await self.connection._publish(
            exchange="",
            routing_key=properties.reply_to,
            body=response,
            properties={"correlation_id": properties.correlation_id},
        )

    async def callback_trigger(self, task_manager):
        """Open one task every time that one message is received."""
        async for message, response_handler in self:
            task_name = "message_handler_" + str(uuid.uuid4())
            if self.resource:
                task_manager.start_task(
                    task_name, self.on_message_callback(self.resource.microservice, message, response_handler)
                )
            else:
                task_manager.start_task(task_name, self.on_message_callback(message, response_handler))
