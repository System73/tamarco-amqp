import asyncio

import pytest
from tamarco.codecs.json import JsonCodec

from tamarco_amqp.input import AMQPPullInput, AMQPRequestInput, AMQPSubscriptionInput
from tamarco_amqp.output import AMQPOutput


@pytest.mark.asyncio
async def test_output_publish(event_loop, aconnection, task_manager):
    message_received_future = asyncio.Future(loop=event_loop)
    queue = "cats"

    @AMQPSubscriptionInput(queue=queue)
    async def consume_cats(message):
        message_received_future.set_result(message)

    output = AMQPOutput(queue=queue)

    await aconnection.register(consume_cats, output)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "test message"
    await output.publish(message)
    await asyncio.wait_for(message_received_future, 1, loop=event_loop)


@pytest.mark.skip(reason="Failing randomly only in the CI.")
@pytest.mark.asyncio
async def test_output_push(event_loop, aconnection, task_manager):
    message_received_future = asyncio.Future(loop=event_loop)
    queue = "cats"

    @AMQPPullInput(queue=queue)
    async def consume_cats(message):
        message_received_future.set_result(message)

    output = AMQPOutput(queue=queue)

    await aconnection.register(consume_cats, output)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "test message"
    await output.push(message)
    await asyncio.wait_for(message_received_future, 1, loop=event_loop)


@pytest.mark.asyncio
async def test_output_request(event_loop, aconnection, task_manager):
    queue = "cats"

    @AMQPRequestInput(queue=queue)
    async def consume_cats(message, response):
        await response.send_response(message)

    output = AMQPOutput(queue=queue)

    await aconnection.register(consume_cats, output)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "test message"
    response = await output.request(message)
    assert response


@pytest.mark.asyncio
async def test_output_request_with_codec(aconnection, task_manager):
    queue = "cats"

    @AMQPRequestInput(queue=queue, codec=JsonCodec)
    async def consume_cats(message, response):
        await response.send_response(message)

    output = AMQPOutput(queue=queue, codec=JsonCodec)

    await aconnection.register(consume_cats, output)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = {"message": "test"}
    response = await output.request(message)
    assert response


@pytest.mark.skip(reason="Failing randomly only in the CI.")
@pytest.mark.asyncio
async def test_generic_output_push(event_loop, aoutput, aconnection, task_manager):
    message_received_future = asyncio.Future(loop=event_loop)
    queue = "cats"

    @AMQPPullInput(queue=queue)
    async def consume_cats(message):
        message_received_future.set_result(message)

    await aconnection.register(consume_cats)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "meow"
    await aoutput.push(message, queue)

    await asyncio.wait_for(message_received_future, 1, loop=event_loop)


@pytest.mark.asyncio
async def test_generic_output_publish(event_loop, aoutput, aconnection, task_manager):
    message_received_future = asyncio.Future(loop=event_loop)
    queue = "cats"

    @AMQPSubscriptionInput(queue=queue)
    async def consume_cats(message):
        message_received_future.set_result(message)

    await aconnection.register(consume_cats)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "meow"
    await aoutput.publish(message, queue)

    await asyncio.wait_for(message_received_future, 1, loop=event_loop)
