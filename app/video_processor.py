import logging as log
import os
import telebot

from dataclasses import dataclass, field
from urllib.parse import urlparse
from yt_dlp import YoutubeDL
from stats import track_url_success, track_url_failed


@dataclass
class Video:
    url: str
    download_folder: str = field(init=False, default="/tmp")
    format: str = field(init=False, default="mp4")
    filename: str = field(init=False)
    download_path: str = field(init=False)

    def __post_init__(self):
        self.filename = urlparse(self.url).path[1:].replace("/", "")
        self.download_path = os.path.join(self.download_folder, self.filename) + "." + self.format


def download_video(video):
    try:
        ydl_opts = {
            'format': video.format,
            'outtmpl': video.download_path,
            'cookiefile': '/app/cookies.txt',
        }

        with YoutubeDL(ydl_opts) as ydl:
            video_info = ydl.extract_info(video.url, download=False)
            ydl.download(video.url)
        return {
            "status": "success",
            "width": video_info["width"],
            "height": video_info["height"],
            "duration": video_info["duration"],
        }
    except Exception as e:
        log.error(f"Failed to download video from {video.url}. Error: {e}")
        return {"status": "failed"}


def download_and_send_video(bot_token, chat_id, message_id, status_message_id, url):
    """
    Download video and send it to Telegram chat.
    This function is called by RQ worker.
    """
    bot = telebot.TeleBot(bot_token, parse_mode="Markdown")
    
    video = Video(url=url)
    video_metadata = download_video(video)

    if video_metadata["status"] == "success" and os.path.exists(video.download_path):
        with open(video.download_path, "rb") as file:
            try:
                # Delete the downloading status message before sending video
                if status_message_id:
                    try:
                        bot.delete_message(chat_id, status_message_id)
                    except Exception as e:
                        log.error(f"Failed to delete status message. Error: {e}")
                
                result = bot.send_video(
                    chat_id, file,
                    width=video_metadata["width"],
                    height=video_metadata["height"],
                    duration=video_metadata["duration"],
                    reply_to_message_id=message_id,
                )
                track_url_success()
                log.info(f"Video sent successfully: {result}")
            except Exception as e:
                log.error(f"Failed to send {file} to {chat_id}. Error: {e}")
                track_url_failed()
                if status_message_id:
                    try:
                        bot.edit_message_text(
                            "Failed to upload the file. Probably it's too big",
                            chat_id,
                            status_message_id
                        )
                    except:
                        bot.send_message(chat_id, "Failed to upload the file. Probably it's too big", reply_to_message_id=message_id)
    else:
        log.error(f"Downloading failed. Video: {video.url}")
        track_url_failed()
        if status_message_id:
            try:
                bot.edit_message_text(
                    "Downloading failed. Try again later.",
                    chat_id,
                    status_message_id
                )
            except:
                bot.send_message(chat_id, "Downloading failed. Try again later.", reply_to_message_id=message_id)
        else:
            bot.send_message(chat_id, "Downloading failed. Try again later.", reply_to_message_id=message_id)

    # Cleanup
    try:
        if os.path.exists(video.download_path):
            os.remove(video.download_path)
    except Exception as e:
        log.error(f"Failed to remove {video.download_path}. Error: {e}")

