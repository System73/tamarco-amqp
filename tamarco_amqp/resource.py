import asyncio
import logging
from itertools import chain

from tamarco.core.tasks import TasksManager
from tamarco.resources.bases import IOResource
from tamarco.resources.bases import StatusCodes

from tamarco_amqp.connection import AMQPConnection


class AMQPResource(IOResource):
    depends_on = []
    loggers_names = ["tamarco.amqp"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("tamarco.amqp")
        self.amqp_connection = None
        self.task_manager = TasksManager()
        self.loop = asyncio.get_event_loop()

    async def get_rabbitmq_configuration(self):
        rabbitmq_config = {
            "host": await self.settings.get("host"),
            "port": await self.settings.get("port"),
            "vhost": await self.settings.get("vhost"),
            "user": await self.settings.get("user"),
            "password": await self.settings.get("password"),
            "connection_timeout": await self.settings.get("connection_timeout"),
            "queues_prefix": await self.settings.get("queues_prefix", ""),
        }
        return rabbitmq_config

    async def bind(self, *args, **kwargs):
        await super().bind(*args, **kwargs)
        self.task_manager.set_loop(self.microservice.loop)
        self.loop = self.microservice.loop

    async def connect_to_amqp(self):
        """Try to connect to the AMQP broker."""
        self._status = StatusCodes.CONNECTING
        rabbitmq_config = await self.get_rabbitmq_configuration()
        await self.set_queues_prefix_iostreams()
        self.amqp_connection = AMQPConnection(
            **rabbitmq_config, ioloop=self.loop, on_error_callback=self.on_error_callback
        )
        await self.amqp_connection.connect(rabbitmq_config["connection_timeout"])

    async def on_error_callback(self, exception):
        if self._status != StatusCodes.STOPPING:
            self.logger.critical(
                f"Received error callback from AMQP connection, reporting failed status in AMQP  "
                f"resource. Exception: {exception}"
            )
            self._status = StatusCodes.FAILED

    @property
    def io_streams(self):
        return tuple(chain(self.outputs.values(), self.inputs.values()))

    async def set_queues_prefix_iostreams(self):
        rabbitmq_config = await self.get_rabbitmq_configuration()
        prefix = rabbitmq_config["queues_prefix"]

        for io_elements in self.io_streams:
            io_elements.set_queues_prefix(prefix)
            self.logger.info(f"AMQP queues prefix: {prefix}")

    async def start(self):
        try:
            await self.connect_to_amqp()
        except ConnectionError:
            self.logger.critical("AMQP resource cannot connect to RabbitMQ. Reporting failed status", exc_info=True)
            self._status = StatusCodes.FAILED
        else:
            try:
                await self.amqp_connection.register(*self.io_streams)
            except Exception:
                self.logger.critical(
                    "Error registering handlers in AMQP resource. Reporting failed status", exc_info=True
                )
                self._status = StatusCodes.FAILED
            else:
                for input_element in self.inputs.values():
                    self.register_on_message_callback_trigger_task(input_element)
                await super().start()

    async def post_start(self):
        self.task_manager.start_all()
        await super().post_start()

    def register_on_message_callback_trigger_task(self, new_input):
        """Register a task that reads the messages from amqp. This task triggers others tasks.

        Args:
            new_input: AMQP input where to read messages.
        """
        input_name = new_input.name
        task_name = f"callback_trigger_{input_name}"
        if new_input.on_message_callback:
            self.task_manager.register_task(task_name, new_input.callback_trigger(self.task_manager))

    async def stop(self):
        self.logger.info(f"Stopping AMQP resource")
        if self._status == StatusCodes.STARTED:
            self._status = StatusCodes.STOPPING
            await self.amqp_connection.close()
        self.task_manager.stop_all()
        await super().stop()

    async def status(self):
        status = {"status": self._status}
        if self._status == StatusCodes.STARTED:
            connection_status = self.amqp_connection.is_connected()
            amqp_configuration = self.amqp_connection.conn_parameters
            inputs = [str(amqp_input) for amqp_input in self.inputs]
            outputs = [str(amqp_output) for amqp_output in self.outputs]
            status.update(
                {
                    "connection_status": connection_status,
                    "amqp_config": amqp_configuration,
                    "inputs": inputs,
                    "outputs": outputs,
                }
            )
        return status
