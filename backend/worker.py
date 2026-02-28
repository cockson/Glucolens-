import os
import redis
from rq import Worker, Queue

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
conn = redis.from_url(REDIS_URL)

listen = ["default"]

if __name__ == "__main__":
    queues = [Queue(name, connection=conn) for name in listen]
    worker = Worker(queues, connection=conn)
    worker.work(with_scheduler=False)
