import asyncio
import json

import pytest
from tamarco.codecs.json import JsonCodec

from tamarco_amqp.input import AMQPPullInput, AMQPRequestInput, AMQPSubscriptionInput
from tamarco_amqp.output import AMQPOutput


def test_encode_message_string():
    input_msg = AMQPRequestInput(queue="cats")
    message = "string message"
    encoded_message = input_msg.encode_message(message)
    assert message == encoded_message


def test_encode_message_json():
    input_msg = AMQPRequestInput(queue="cats", codec=JsonCodec)
    json_message = {"message": "json_message"}
    encoded_message = input_msg.encode_message(json_message)

    assert json_message == json.loads(encoded_message)


def test_decode_message_string():
    input_msg = AMQPRequestInput(queue="cats")
    message = "string message"
    encoded_message = input_msg.decode_message(message)
    assert message == encoded_message


def test_decode_message_json():
    input_msg = AMQPRequestInput(queue="cats", codec=JsonCodec)
    json_message = json.dumps({"message": "json_message"})
    encoded_message = input_msg.decode_message(json_message)

    assert json.loads(json_message) == encoded_message


@pytest.mark.parametrize("AMQPInput", [AMQPRequestInput, AMQPRequestInput, AMQPSubscriptionInput])
def test_get_full_queue_name(AMQPInput):
    input_msg = AMQPInput(queue="cats")
    full_queue_name = input_msg.get_full_queue_name()
    assert isinstance(full_queue_name, str)
    assert input_msg.queue in full_queue_name
    assert input_msg.queue_prefix in full_queue_name


def test_set_loop():
    loop = asyncio.get_event_loop()
    input_msg = AMQPSubscriptionInput(queue="cats")
    input_msg.set_loop(loop)
    assert input_msg.loop is loop
    assert input_msg.messages


def test_set_connection(aconnection):
    input_msg = AMQPSubscriptionInput(queue="cats")
    input_msg.set_connection(aconnection)
    assert input_msg.connection is aconnection


@pytest.mark.asyncio
async def test_input_subscription_async_iterator(event_loop, aconnection, aoutput, task_manager):
    message_received_future = asyncio.Future(loop=event_loop)
    queue = "cats"

    @AMQPSubscriptionInput(queue=queue)
    async def consume_cats(message):
        message_received_future.set_result(message)

    await aconnection.register(consume_cats)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "test message"
    await aoutput.publish(message, queue)

    await asyncio.wait_for(message_received_future, 1, loop=event_loop)


@pytest.mark.skip(reason="Failing randomly only in the CI.")
@pytest.mark.asyncio
async def test_input_pull_async_iterator(event_loop, aconnection, aoutput, task_manager):
    message_received_future = asyncio.Future(loop=event_loop)
    queue = "cats"

    @AMQPPullInput(queue=queue)
    async def consume_cats(message):
        message_received_future.set_result(message)

    await aconnection.register(consume_cats)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "test message"
    await asyncio.sleep(1)
    await aoutput.push(message, queue)

    await asyncio.wait_for(message_received_future, 1, loop=event_loop)


@pytest.mark.asyncio
async def test_input_request_async_iterator(aconnection, task_manager):
    queue = "cats"

    @AMQPRequestInput(queue=queue)
    async def consume_cats(message, response):
        await response.send_response(message)

    output = AMQPOutput(queue=queue)

    await aconnection.register(consume_cats, output)
    task_manager.start_task("consumer", consume_cats.callback_trigger(task_manager))

    message = "test message"
    await asyncio.wait_for(output.request(message), 1)
