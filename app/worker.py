import logging as log
import os
import redis
import telebot

from rq import Worker
from video_processor import download_and_send_video
from image_processor import download_and_send_images


log.basicConfig(level=log.INFO, format="%(asctime)s %(levelname)s %(message)s")

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))

redis_conn = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)

if __name__ == "__main__":
    log.info("Starting RQ worker...")

    # rq 2.x removed the `Connection` context manager; pass `connection`
    # directly to Worker instead.
    worker = Worker(['default'], connection=redis_conn)
    worker.work()

