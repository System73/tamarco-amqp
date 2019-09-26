import time
from unittest import mock

import pytest

from tamarco_amqp import settings
from tamarco_amqp.connection import AMQPConnection
from tamarco_amqp.input import AMQPPullInput, AMQPRequestInput, AMQPSubscriptionInput
from tests.functional.conftest import amqp_config


class ConnectionAsyncMock(mock.MagicMock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


def sleep_and_raise_socket_error(*args, **kargs):
    time.sleep(settings.CONNECTION_TIMEOUT_SECONDS)
    raise ConnectionError


@pytest.mark.asyncio
async def test_amqp_reconnection_fail(event_loop):
    with mock.patch(
        "tamarco_amqp.connection.AMQPConnection._connect_to_amqp_broker",
        new_callable=ConnectionAsyncMock,
        side_effect=sleep_and_raise_socket_error,
    ) as initialize:
        reconnect_timeout = 1
        connection = AMQPConnection(ioloop=event_loop)
        with pytest.raises(ConnectionError):
            await connection.connect(reconnect_timeout=reconnect_timeout)
        initialize.assert_called()
        assert not connection.is_connected()


@pytest.mark.asyncio
async def test_amqp_reconnection_success():
    connection = AMQPConnection(**amqp_config)
    await connection.connect(reconnect_timeout=20)

    assert connection.is_connected()
    await connection.close()
    assert not connection.is_connected()


@pytest.mark.asyncio
async def test_register_invalid_consumer(aconnection):
    def bad_consumer():
        pass

    with pytest.raises(Exception):
        await aconnection.register(bad_consumer)


@pytest.mark.asyncio
async def test_register_invalid_type(aconnection):
    with pytest.raises(Exception):
        await aconnection.register(1)


@pytest.mark.asyncio
async def test_register_input_twice(aconnection):
    @AMQPPullInput(queue="cat")
    async def cat_server(message):
        pass

    await aconnection.register(cat_server)
    with pytest.raises(Exception):
        await aconnection.register(cat_server)


@pytest.mark.asyncio
async def test_register_output_twice(aconnection, aoutput):
    with pytest.raises(Exception):
        await aconnection.register(aoutput)


@pytest.mark.asyncio
async def test_register_without_connecting():
    @AMQPPullInput(queue="cat")
    async def cat_consumer(message):
        pass

    conn = AMQPConnection(**amqp_config)
    await conn.register(cat_consumer)
    await conn.connect()
    assert cat_consumer in conn.inputs


@pytest.mark.asyncio
async def test_unregister_handler(aconnection):
    @AMQPPullInput(queue="cats")
    async def cat_consumer(message):
        pass

    await aconnection.register(cat_consumer)
    await aconnection.connect()

    assert cat_consumer in aconnection.inputs
    await aconnection.unregister(cat_consumer)
    assert cat_consumer not in aconnection.inputs


@pytest.mark.asyncio
async def test_unregister_handler_disconnected(aconnection):
    @AMQPPullInput(queue="cats")
    async def cat_consumer(message):
        pass

    await aconnection.register(cat_consumer)
    await aconnection.connect()
    await aconnection.close()
    await aconnection.unregister(cat_consumer)
    assert cat_consumer not in aconnection.inputs
    await aconnection.connect()


@pytest.mark.asyncio
async def test_register_request_response_input(aconnection):
    @AMQPRequestInput(queue="cats")
    async def cat_server(message):
        pass

    await aconnection.register(cat_server)
    assert cat_server in aconnection.inputs


@pytest.mark.asyncio
async def test_register_subscription_input(aconnection):
    @AMQPSubscriptionInput(queue="cats")
    async def cat_server(message):
        pass

    await aconnection.register(cat_server)
    assert cat_server in aconnection.inputs


@pytest.mark.asyncio
async def test_publish_without_connecting():
    with pytest.raises(Exception):
        conn = AMQPConnection()
        await conn._publish(None, None, None, None)


@pytest.mark.asyncio
async def test_bad_connection():
    incorrect_ip = "192.168.10.1"
    conn = AMQPConnection(host=incorrect_ip)
    with pytest.raises(ConnectionError):
        await conn.connect(reconnect_timeout=0)
