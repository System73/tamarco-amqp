import subprocess
from time import sleep

import pytest
from tamarco.core.tasks import TasksManager

from tamarco_amqp.connection import AMQPConnection
from tamarco_amqp.output import AMQPGenericOutput
from tamarco_amqp.resource import AMQPResource

amqp_config = {
    "host": "127.0.0.1",
    "port": "5672",
    "vhost": "/",
    "user": "microservice",
    "password": "1234",
    "connection_timeout": "10",
    "queues_prefix": "prefix",
}


@pytest.fixture
def settings():
    return {"system": {"resources": {"amqp": amqp_config}}}


@pytest.fixture
def aconnection(event_loop):
    connection = AMQPConnection(ioloop=event_loop, **amqp_config)
    coroutine = connection.connect()
    event_loop.run_until_complete(coroutine)
    yield connection
    coroutine = connection.close()
    event_loop.run_until_complete(coroutine)


@pytest.fixture
def aoutput(aconnection, event_loop):
    output = AMQPGenericOutput()
    coro = aconnection.register(output)
    event_loop.run_until_complete(coro)
    yield output
    output.connection = None


@pytest.fixture
def task_manager(event_loop):
    task_manager = TasksManager()
    task_manager.set_loop(event_loop)
    yield task_manager
    task_manager.stop_all()


@pytest.fixture
def amqp_resource(event_loop):
    amqp_resource = AMQPResource()
    amqp_resource.task_manager.set_loop(event_loop)
    amqp_resource.loop = event_loop
    yield amqp_resource
    event_loop.run_until_complete(amqp_resource.stop())


def local_command(command):
    print(f"\nLaunching command: {command}")
    process = subprocess.Popen(command, shell=True)
    return_code = process.wait()
    return process, return_code


def docker_compose_up():
    print("Bringing up the docker compose")
    command = f"docker-compose up -d"
    _, return_code = local_command(command)
    if return_code != 0:
        pytest.fail(msg="Failed setting up the containers.")


def docker_compose_down():
    print("Removing all containers")
    command = f"docker-compose kill && docker-compose down"
    _, return_code = local_command(command)
    if return_code != 0:
        print("Warning: Error stopping all the containers.")
    else:
        print("Removed docker containers.")


@pytest.fixture(scope="session", autouse=True)
def docker_compose():
    docker_compose_up()
    sleep(4)
    yield
    docker_compose_down()
