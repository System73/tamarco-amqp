# tamarco-amqp

[![Build Status](https://travis-ci.com/System73/tamarco-amqp.svg?branch=master)](https://travis-ci.com/System73/tamarco-amqp)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=System73_tamarco-amqp&metric=coverage)](https://sonarcloud.io/dashboard?id=System73_tamarco-amqp)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=System73_tamarco-amqp&metric=alert_status)](https://sonarcloud.io/dashboard?id=System73_tamarco-amqp)

AMQP resource for Tamarco microservice framework.

## Settings

This resource depends on the following configuration schema:

```yaml
    system:
        resources:
            amqp:
                host: 127.0.0.1
                port: 5672
                vhost: /
                user: microservice
                password: 1234
                connection_timeout: 10
                queues_prefix: "prefix"
```

## Inputs and outputs

The inputs and outputs need to be declared in the resource.

Three different communication patterns can be used.

A specific input is required for each message pattern, but the same output is valid for all message patterns. Each message pattern has a different method in the output.

With the JsonCodec the input and the output are directly Python dictionaries.

### Publish-subscribe pattern

In the pub-sub pattern a message reaches all the services subscribed to the queue. It can be used to notify events to anyone who needs it.

#### Input

The `AMQPSubscriptionInput` can be used as a decorator.

```python
class AmqpMicroservice():
    amqp = AMQPResource()

    @AMQPSubscriptionInput(resource=amqp, queue='cows', codec=JsonCodec)
    async def consume_messages(self, message):
        self.logger.info(f'Consumed message from cows subscription queue: {message}')
```

Or as a async iterator:

```python
class AmqpMicroservice():
    cows_input = AMQPSubscriptionInput(queue='cows', codec=JsonCodec)
    amqp = AMQPResource(inputs=[cows_input])

    @task
    async def consume_cows(self):
        async for message in self.cows_input:
            self.logger.info(f'Consumed message from cows subscription queue: {message}')
```

#### Output

Use the `publish` method of the output.

```python
class AmqpMicroservice():
    cows_output = AMQPOutput(queue='cows', codec=JsonCodec)
    amqp = AMQPResource(outputs=[cows_output])

    @task_timer(interval=1000, autostart=True)
    async def metric_producer(self):
        await cows_output.publish({'my_json_message': 'to_cow_queue'})
```

### Push-pull pattern

The push-pull pattern is a work queue where each message is only pulled by one of the services subscribed to the queue. Commonly used to distribute the work in a pull of instances.

#### Input

`AMQPPullInput` is used to declare a input pull queue, and example used as decorator: 

```python
class AmqpMicroservice():
    amqp = AMQPResource()

    @AMQPPullInput(resource=amqp, queue='cows', codec=JsonCodec)
    async def consume_messages(self, message):
        self.logger.info(f'Consumed message from cows pull queue: {message}')
```

It can be used as an async iterator in the same way that the pub/sub pattern.

#### Output 

Use the `push` method of the `AMQPOutput`. In the following

```python
class AmqpMicroservice():
    cows_output = AMQPOutput(queue='cows', codec=JsonCodec)
    amqp = AMQPResource(outputs=[cows_output])

    @task_timer(interval=1000, autostart=True)
    async def metric_producer(self):
        await cows_output.push({'my_json_message': 'to_cow_queue'})
```

### Request-response pattern

In the request-response pattern each request is handled by one of the instances subscribed to the queue and unlike the other patterns, each request has an answer. 

#### Input 

`AMQPRequestInput` is used to declare a input request response queue. An example used as decorator:

```python
class AmqpMicroservice():
    amqp = AMQPResource()

    @AMQPRequestInput(resource=amqp, queue='cows', codec=JsonCodec)
    async def consume_messages(self, message, response_handler):
        self.logger.info(f'Consumed message from cows queue: {message}')
        await response_handler.send_response({'cows': 'response'})
```

In this case the handler takes two input objects, and one of them send the response.

#### Output

The output is like the rest of them but it returns a response.

```python
class AmqpMicroservice():
    cows_output = AMQPOutput(queue='cows', codec=JsonCodec)
    amqp = AMQPResource()

    @task_timer(interval=1000, autostart=True)
    async def request_response(self):
        message = {'cow': 'MOOOO'}
        response = await cows_output.request(message)
        self.logger.info(f'Response from cows queue: {response}')
```

## How to run the examples

To run them you just need to launch the docker-compose, install the requirements and run it.

```python3
pip install -r examples/requirements.txt
docker-compose up -d
python examples/microservice_stream_input.py
```
