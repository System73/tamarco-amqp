import asyncio

from tamarco.codecs.json import JsonCodec
from tamarco.core.microservice import Microservice, task

from tamarco_amqp.input import AMQPSubscriptionInput
from tamarco_amqp.output import AMQPOutput
from tamarco_amqp.resource import AMQPResource


class MyMicroservice(Microservice):
    name = "amqp_example"
    extra_loggers_names = {name, "asyncio", "tamarco"}

    def __init__(self):
        super().__init__()
        self.settings.update_internal(
            {
                "system": {
                    "deploy_name": "test",
                    "logging": {"profile": "PRODUCTION"},
                    "resources": {
                        "amqp": {
                            "host": "127.0.0.1",
                            "port": 5672,
                            "vhost": "/",
                            "user": "microservice",
                            "password": "1234",
                            "connection_timeout": 10,
                        }
                    },
                }
            }
        )

    amqp = AMQPResource(outputs=[AMQPOutput(queue="cows", codec=JsonCodec)])

    @task
    async def produce_cows(self):
        cows_output = self.amqp.outputs["cows"]
        while True:
            await asyncio.sleep(1)
            message = {"cow": "MOOOO"}
            await cows_output.publish(message)
            self.logger.info(f"Sent message {message} to cows queue")

    @AMQPSubscriptionInput(resource=amqp, queue="cows", codec=JsonCodec)
    async def consume_messages(self, message):
        self.logger.info(f"Consumed message from cows queue: {message}")


def main():
    ms = MyMicroservice()
    ms.run()


if __name__ == "__main__":
    main()
