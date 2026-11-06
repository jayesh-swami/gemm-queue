from aio_pika.abc import AbstractChannel
from fastapi import Request


def get_mq_channel(request: Request) -> AbstractChannel:
    return request.app.state.mq_channel
