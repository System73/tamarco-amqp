import asyncio
import builtins
import logging
import time
from asyncio import Future, TimeoutError

import aioamqp
from aioamqp.protocol import OPEN

from tamarco_amqp.input import AMQPPullInput, AMQPRequestInput, AMQPSubscriptionInput
from tamarco_amqp.output import AMQPGenericOutput, AMQPOutput
from tamarco_amqp.settings import CONNECTION_TIMEOUT_SECONDS, RECONNECTION_TIMEOUT_SECONDS

logger = logging.getLogger("tamarco.amqp")


class AMQPConnection:
    """Handle the connection with the AMQP broker."""

    def __init__(
        self,
        host="127.0.0.1",
        port=5672,
        user="guest",
        password="guest",
        vhost="/",
        ioloop=None,
        on_error_callback=None,
        *args,
        **kwargs,
    ):
        """
        Args:
            host: IP or fqdn of the AMQP Broker.
            port: Port of the AMQP Broker.
            user: Username to register in the AMQP Broker.
            password: Password to register in the AMQP Broker.
            vhost: Virtual host to use in the AMQP Broker.
            ioloop: Asyncio loop if needed, the default is asyncio current loop.
        """
        self.loop = ioloop if ioloop else asyncio.get_event_loop()

        self.conn_parameters = {
            "host": str(host),
            "user": str(user),
            "port": port,
            "password": str(password),
            "virtual_host": str(vhost),
        }

        self._transport = None
        self._protocol = None
        self._channel = None
        self._delivery_tag = 0
        self._confirmation_future = {}
        self.inputs = []
        self._close_future = Future()
        self.on_error_callback = on_error_callback

    def is_connected(self):
        """Return true if the connection is open, else False."""
        return (
            self._protocol is not None
            and self._protocol.state == OPEN
            and self._channel is not None
            and self._channel.is_open
        )

    async def register(self, *io_streams):
        """Initialize the streams.

        Args:
            io_streams: Handlers classes that we want to register.
        """
        for io_stream in io_streams:
            logger.info(f"Registering AMQP handler: {io_stream}")
            if isinstance(io_stream, (AMQPPullInput, AMQPSubscriptionInput, AMQPRequestInput)):
                io_stream.set_connection(self)
                io_stream.set_loop(self.loop)
                if io_stream not in self.inputs:
                    self.inputs.append(io_stream)
                else:
                    raise Exception(f"IO stream {io_stream} already registered")
            elif isinstance(io_stream, (AMQPOutput, AMQPGenericOutput)):
                io_stream.set_connection(self)
                await io_stream.initialize()
            else:
                logger.error(f"Invalid IO stream: {io_stream}. Type: {type(io_stream)}")
                raise Exception(f"Invalid IO stream: {io_stream}")

        if self.is_connected():
            await self._declare_queues(io_streams)

    async def unregister(self, *handlers):
        """Unregister the handlers.
        Once unregistered they stop consuming messages.

        Args:
            handlers: Handlers classes to unregister.
        """
        for handler in handlers:
            logger.info(f"Unregistering AMQP handler: {handler}")
            self.inputs.remove(handler)

        if self.is_connected():
            await self._delete_consumers(handlers)

    async def _publish(self, exchange, routing_key, body, properties):
        if self._protocol is None or not self._protocol.state == OPEN:
            raise ConnectionError("Trying to publish without connection")

        _properties = {"content_type": "text/plain"}
        _properties.update(properties)

        result = await self._channel.basic_publish(
            payload=body, exchange_name=exchange, routing_key=routing_key, properties=_properties
        )

        return result

    async def close(self):
        """Close the connection with the broker.
        The coroutine ends when the connection is closed.
        """
        logger.info("Closing AMQP connection")
        await self._protocol.close()
        self._transport.close()

    async def connect(self, reconnect_timeout=None):
        """Connect to the AMQP servers.

        Args:
            reconnect_timeout: Timeout in seconds.
        """
        reconnect_timeout = reconnect_timeout if reconnect_timeout is not None else RECONNECTION_TIMEOUT_SECONDS
        if reconnect_timeout:
            await self._reconnect(reconnect_timeout)
        else:
            await self._connect_to_amqp_broker()

    async def _connect_to_amqp_broker(self):
        """Connect to the broker, and creates the exchanges and queues needed by the handlers registered at the moment
        of connection.

        Raises:
            ConnectionError:
        """
        try:
            self._transport, self._protocol = await asyncio.wait_for(
                aioamqp.connect(
                    host=self.conn_parameters["host"],
                    port=self.conn_parameters["port"],
                    login=self.conn_parameters["user"],
                    password=self.conn_parameters["password"],
                    virtualhost=self.conn_parameters["virtual_host"],
                    on_error=self.on_error_callback,
                ),
                CONNECTION_TIMEOUT_SECONDS,
            )
        except (aioamqp.AmqpClosedConnection, TimeoutError, builtins.ConnectionError, OSError):
            logger.critical(f"Error connecting to the AMQP broker")
            raise ConnectionError
        else:
            logger.info(f"Connected to AMQP host: {self.conn_parameters['host']}")

            self._channel = await self._protocol.channel()
            logger.info("AMQP channel created")
            await self._declare_queues(self.inputs)
            logger.info("AMQP queues declared")

    async def _reconnect(self, reconnect_timeout):
        """When the library can't connect to AMQP broker it tries to reconnect.

        Args:
            reconnect_timeout (int): Maximum time that the library tries to reconnect.

        Raises:
            ConnectionError:
        """
        connection_open = False
        begin_time = time.time()
        while (time.time() - begin_time) < reconnect_timeout:
            try:
                url = f"{self.conn_parameters['host']}:{self.conn_parameters['port']}"
                logger.debug(f"Connecting to the AMQP broker with URL: {url}")
                await self._connect_to_amqp_broker()
                logger.info("Connected to AMQP")
                connection_open = True
                break

            except ConnectionError:
                time_elapsed = time.time() - begin_time
                logger.warning(
                    f"Reconnection to the AMQP broker failed. Timeout: {reconnect_timeout}. Time elapsed: "
                    f"{time_elapsed}"
                )
        if not connection_open:
            logger.critical("Maximum of connection attempts with the AMQP resource reached. Closing the server")
            raise ConnectionError

    async def _declare_push_pull(self, amqp_input):
        """Declare the queues and exchanges necessaries for a Push Pull communication.

        Args:
            amqp_input: PullHandler that we are going to declare its queues and exchanges.
        """
        await self._channel.queue_declare(
            queue_name=amqp_input.get_full_queue_name(), durable=True, exclusive=False, auto_delete=False
        )
        await self._channel.basic_consume(
            callback=amqp_input.handle_delivery,
            queue_name=amqp_input.get_full_queue_name(),
            no_ack=True,
            consumer_tag=amqp_input.tag,
        )

    async def _declare_publish_subscribe(self, amqp_input):
        """Declare the queues and exchanges necessaries for a Publish Subscribe communication.

        Args:
            amqp_input: SubscriptionHandler that we are going to declare its queues and exchanges.
        """
        await self._channel.exchange_declare(exchange_name=amqp_input.get_full_queue_name(), type_name="fanout")

        # private queue for the handler without name, binded to the exchange
        queue = await self._channel.queue_declare(exclusive=True)

        queue_name = queue["queue"]

        await self._channel.queue_bind(
            exchange_name=amqp_input.get_full_queue_name(), queue_name=queue_name, routing_key=""
        )

        await self._channel.basic_consume(
            callback=amqp_input.handle_delivery, queue_name=queue_name, no_ack=True, consumer_tag=amqp_input.tag
        )

    async def _declare_request_response(self, amqp_input):
        """Declare the queues and exchanges necessaries for a Request Response communication.

        Args:
            amqp_input: RequestHandler that we are going to declare its queues and exchanges.
        """
        await self._channel.queue_declare(queue_name=amqp_input.get_full_queue_name())

        await self._channel.basic_qos(prefetch_count=1, prefetch_size=0, connection_global=False)

        await self._channel.basic_consume(
            callback=amqp_input.handle_delivery,
            queue_name=amqp_input.get_full_queue_name(),
            no_ack=True,
            consumer_tag=amqp_input.tag,
        )

    async def _declare_queues(self, inputs):
        """
        Args:
            inputs: List of Handlers to be declared.
        """
        for handler in inputs:
            logger.info(f"Declaring AMQP queues of the handler: {handler}")
            if issubclass(handler.__class__, AMQPPullInput):
                await self._declare_push_pull(handler)

            elif issubclass(handler.__class__, AMQPRequestInput):
                await self._declare_request_response(handler)

            elif issubclass(handler.__class__, AMQPSubscriptionInput):  # pragma: no cover
                await self._declare_publish_subscribe(handler)

    async def _delete_consumers(self, handlers):
        """
        Args:
            handlers: List of Handlers to cancel his subscriptions.
        """
        for handler in handlers:
            logger.info(f"Deleting AMQP consumer of the handler: {handler}")
            await self._channel.basic_cancel(consumer_tag=handler.tag, no_wait=False)
