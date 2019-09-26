import pytest
from tamarco.resources.basic.status.status_codes import StatusCodes

from tamarco_amqp.input import AMQPPullInput


async def settings_method():
    return {
        "host": "127.0.0.1",
        "port": 5672,
        "vhost": "/",
        "user": "microservice",
        "password": "1234",
        "connection_timeout": 10,
        "queues_prefix": "",
    }


@pytest.mark.asyncio
async def test_start_and_stop(amqp_resource):
    @AMQPPullInput(queue="cats", resource=amqp_resource)
    async def consume_cats(message):
        pass

    amqp_resource.get_rabbitmq_configuration = settings_method

    await amqp_resource.start()
    await amqp_resource.post_start()


@pytest.mark.asyncio
async def test_status_code_pre_start(amqp_resource):
    status = await amqp_resource.status()
    assert isinstance(status, dict)
    assert status == {"status": StatusCodes.NOT_STARTED}


@pytest.mark.asyncio
async def test_status_code_start(amqp_resource):
    @AMQPPullInput(queue="cats", resource=amqp_resource)
    async def consume_cats(message):
        pass

    amqp_resource.get_rabbitmq_configuration = settings_method

    await amqp_resource.start()
    status = await amqp_resource.status()

    assert isinstance(status, dict)
    assert status["status"] == StatusCodes.STARTED


@pytest.mark.asyncio
async def test_status_code_stop(amqp_resource):
    @AMQPPullInput(queue="cats", resource=amqp_resource)
    async def consume_cats(message):
        pass

    amqp_resource.get_rabbitmq_configuration = settings_method

    await amqp_resource.start()
    await amqp_resource.stop()
    status = await amqp_resource.status()

    assert isinstance(status, dict)
    assert status["status"] == StatusCodes.STOPPED
