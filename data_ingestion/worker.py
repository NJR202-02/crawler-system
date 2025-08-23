from celery import Celery

from data_ingestion.config import (
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    WORKER_USERNAME,
    WORKER_PASSWORD,
)

print(
    f"""
    RABBITMQ_HOST: {RABBITMQ_HOST}
    RABBITMQ_PORT: {RABBITMQ_PORT}
    WORKER_USERNAME: {WORKER_USERNAME}
    WORKER_PASSWORD: {WORKER_PASSWORD}
"""
)
app = Celery(
    "task",
    include=[
        "data_ingestion.tasks",
    ],
    # 指定 broker 為 rabbitmq
    # pyamqp://worker:worker@127.0.0.1:5672/
    broker=f"pyamqp://{WORKER_USERNAME}:{WORKER_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
)
