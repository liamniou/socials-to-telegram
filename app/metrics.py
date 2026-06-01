import logging as log
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import (
    generate_latest,
    CONTENT_TYPE_LATEST,
    Gauge,
    Counter,
    REGISTRY,
)
import redis
from rq import Queue
from rq.job import Job
from rq.registry import FinishedJobRegistry, FailedJobRegistry, StartedJobRegistry
from stats import get_stats


log.basicConfig(level=log.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Redis connection
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_conn = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)

# Prometheus metrics - Queue metrics
queue_size = Gauge(
    "socials_to_telegram_queue_size",
    "Number of jobs waiting in the queue"
)
jobs_started = Gauge(
    "socials_to_telegram_jobs_started",
    "Number of jobs currently being processed"
)
jobs_finished = Gauge(
    "socials_to_telegram_jobs_finished_total",
    "Total number of successfully finished jobs"
)
jobs_failed = Gauge(
    "socials_to_telegram_jobs_failed_total",
    "Total number of failed jobs"
)
workers_count = Gauge(
    "socials_to_telegram_workers",
    "Number of active workers"
)
redis_connected = Gauge(
    "socials_to_telegram_redis_connected",
    "Whether Redis is connected (1=yes, 0=no)"
)

# Prometheus metrics - Bot stats
unique_users = Gauge(
    "socials_to_telegram_unique_users",
    "Number of unique users who used the bot"
)
urls_processed = Gauge(
    "socials_to_telegram_urls_processed_total",
    "Total number of URLs requested for processing"
)
urls_success = Gauge(
    "socials_to_telegram_urls_success_total",
    "Total number of successfully processed URLs"
)
urls_failed = Gauge(
    "socials_to_telegram_urls_failed_total",
    "Total number of failed URL processing attempts"
)
urls_by_platform = Gauge(
    "socials_to_telegram_urls_by_platform",
    "Number of URLs processed by platform",
    ["platform"]
)


def collect_metrics():
    """Collect metrics from RQ and Redis"""
    try:
        # Check Redis connection
        redis_conn.ping()
        redis_connected.set(1)
        
        queue = Queue('default', connection=redis_conn)
        
        # Queue size
        queue_size.set(len(queue))
        
        # Started jobs (currently processing)
        started_registry = StartedJobRegistry(queue=queue)
        jobs_started.set(len(started_registry))
        
        # Finished jobs
        finished_registry = FinishedJobRegistry(queue=queue)
        jobs_finished.set(len(finished_registry))
        
        # Failed jobs
        failed_registry = FailedJobRegistry(queue=queue)
        jobs_failed.set(len(failed_registry))
        
        # Workers count
        from rq import Worker
        workers = Worker.all(connection=redis_conn)
        workers_count.set(len(workers))
        
        # Bot statistics
        stats = get_stats()
        unique_users.set(stats["unique_users"])
        urls_processed.set(stats["urls_processed"])
        urls_success.set(stats["urls_success"])
        urls_failed.set(stats["urls_failed"])
        
        # URLs by platform
        for platform, count in stats["urls_by_platform"].items():
            urls_by_platform.labels(platform=platform).set(int(count))
        
    except redis.ConnectionError:
        redis_connected.set(0)
        log.error("Failed to connect to Redis")
    except Exception as e:
        log.error(f"Error collecting metrics: {e}")


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            collect_metrics()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest(REGISTRY))
        elif self.path == "/health":
            try:
                redis_conn.ping()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            except:
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Redis connection failed")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress access logs for cleaner output
        pass


def main():
    port = int(os.getenv("METRICS_PORT", 9090))
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    log.info(f"Metrics server started on port {port}")
    log.info(f"  /metrics - Prometheus metrics")
    log.info(f"  /health  - Health check")
    server.serve_forever()


if __name__ == "__main__":
    main()

