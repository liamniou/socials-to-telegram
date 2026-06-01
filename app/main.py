import logging as log
import os
import signal
import sys
import redis
import telebot

from rq import Queue
from urlextract import URLExtract
from video_processor import download_and_send_video
from image_processor import download_and_send_images
from stats import track_user, track_url_requested


bot = telebot.TeleBot(
    os.getenv("TELEGRAM_BOT_TOKEN"),
    threaded=False,
    parse_mode="Markdown",
)
extractor = URLExtract()

# Redis connection
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_conn = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)
queue = Queue('default', connection=redis_conn)


def signal_handler(signal_number):
    log.info(f"Received signal {signal_number}. Trying to end tasks and exit...")
    bot.stop_polling()
    sys.exit(0)


def is_instagram_post(url):
    """Check if URL is an Instagram post (contains /p/)"""
    return "instagram.com/p/" in url


@bot.message_handler(func=lambda m: m.text is not None and extractor.find_urls(m.text))
def echo_all(message):
    # Track unique user
    track_user(message.from_user.id)
    
    for url in extractor.find_urls(message.text):
        if any(x in url for x in ["tiktok.com", "instagram.com", "twitter.com", "youtube.com"]):
            # Track URL request
            track_url_requested(url)
            
            status_message = None
            try:
                status_message = bot.reply_to(message, "Got your message. Downloading...")
            except Exception as e:
                log.error(f"Failed to reply to {message.chat.id}. Error: {e}")
                return

            # Choose processor based on URL type
            if is_instagram_post(url):
                processor_func = download_and_send_images
            else:
                processor_func = download_and_send_video

            # Enqueue the job to be processed by worker
            try:
                job = queue.enqueue(
                    processor_func,
                    os.getenv("TELEGRAM_BOT_TOKEN"),
                    message.chat.id,
                    message.message_id,
                    status_message.message_id if status_message else None,
                    url,
                    job_timeout='10m'  # 10 minutes timeout for large videos
                )
                log.info(f"Job {job.id} enqueued for URL: {url}")
            except Exception as e:
                log.error(f"Failed to enqueue job for {url}. Error: {e}")
                if status_message:
                    try:
                        bot.edit_message_text(
                            "Failed to queue download. Try again later.",
                            message.chat.id,
                            status_message.message_id
                        )
                    except:
                        bot.reply_to(message, "Failed to queue download. Try again later.")


# Log other messages to console
@bot.message_handler(func=lambda m: True)
def log_message(message):
    log.info(f"Received message: {message.text}")


def main():
    log.basicConfig(level=log.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("Bot was started.")
    signal.signal(signal.SIGINT, signal_handler)
    log.info("Starting bot polling...")
    try:
        # infinity_polling handles transient network errors (read timeouts,
        # 429 rate limits, connection resets) internally instead of raising
        # and letting the process exit, which previously caused Docker to
        # restart the container on every Telegram API hiccup.
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except Exception as e:
        log.error(f"Bot polling stopped unexpectedly. Error: {e}")


if __name__ == "__main__":
    main()
