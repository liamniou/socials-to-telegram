import logging as log
import os
import re
import subprocess
import glob
import telebot

from dataclasses import dataclass, field
from urllib.parse import urlparse
from stats import track_url_success, track_url_failed


# Path to Instagram cookies file (Netscape format)
INSTAGRAM_COOKIES_PATH = os.getenv("INSTAGRAM_COOKIES_PATH", "/app/cookies.txt")


def extract_index(filepath):
    """
    Extract numeric index from filename for proper ordering.
    gallery-dl names files like: instagram_user_postid_1.jpg, instagram_user_postid_2.jpg
    """
    filename = os.path.basename(filepath)
    # Find the last number before the extension (e.g., _1.jpg -> 1)
    match = re.search(r'_(\d+)\.[^.]+$', filename)
    if match:
        return int(match.group(1))
    # Fallback: try to find any number in the filename
    numbers = re.findall(r'(\d+)', filename)
    if numbers:
        return int(numbers[-1])
    return 0


@dataclass
class ImagePost:
    url: str
    download_folder: str = field(init=False)
    
    def __post_init__(self):
        # Create unique folder for this post based on URL path
        post_id = urlparse(self.url).path.strip("/").replace("/", "_")
        self.download_folder = os.path.join("/tmp", f"gallery_{post_id}")
        os.makedirs(self.download_folder, exist_ok=True)


def download_images(post):
    """Download images using gallery-dl"""
    try:
        cmd = [
            "gallery-dl",
            "--dest", post.download_folder,
            # Use custom filename with zero-padded index for correct ordering
            "-o", "filename={num:>03}.{extension}",
            # Flatten directory structure
            "-o", "directory=[]",
        ]
        
        # Add cookies if available for Instagram authentication
        if os.path.exists(INSTAGRAM_COOKIES_PATH):
            cmd.extend(["--cookies", INSTAGRAM_COOKIES_PATH])
            log.info(f"Using cookies from {INSTAGRAM_COOKIES_PATH}")
        else:
            log.warning(f"No cookies file found at {INSTAGRAM_COOKIES_PATH}. Instagram may block the request.")
        
        cmd.append(post.url)
        
        log.info(f"Running gallery-dl command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        log.info(f"gallery-dl stdout: {result.stdout}")
        
        if result.returncode != 0:
            log.error(f"gallery-dl failed with code {result.returncode}")
            log.error(f"gallery-dl stderr: {result.stderr}")
            return {"status": "failed", "files": []}
        
        # Find all downloaded files
        downloaded_files = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.mp4", "*.mov"]:
            downloaded_files.extend(glob.glob(os.path.join(post.download_folder, "**", ext), recursive=True))
        
        if not downloaded_files:
            log.error(f"No files downloaded for {post.url}")
            log.error(f"Download folder contents: {os.listdir(post.download_folder) if os.path.exists(post.download_folder) else 'folder does not exist'}")
            return {"status": "failed", "files": []}
        
        # Sort files by numeric index to preserve original order
        sorted_files = sorted(downloaded_files, key=extract_index)
        log.info(f"Downloaded {len(sorted_files)} files: {sorted_files}")
        return {"status": "success", "files": sorted_files}
    
    except subprocess.TimeoutExpired:
        log.error(f"gallery-dl timed out for {post.url}")
        return {"status": "failed", "files": []}
    except Exception as e:
        log.error(f"Failed to download images from {post.url}. Error: {e}")
        return {"status": "failed", "files": []}


def download_and_send_images(bot_token, chat_id, message_id, status_message_id, url):
    """
    Download images and send them to Telegram chat.
    This function is called by RQ worker.
    """
    bot = telebot.TeleBot(bot_token, parse_mode="Markdown")
    
    post = ImagePost(url=url)
    result = download_images(post)
    
    if result["status"] == "success" and result["files"]:
        try:
            # Delete the downloading status message before sending
            if status_message_id:
                try:
                    bot.delete_message(chat_id, status_message_id)
                except Exception as e:
                    log.error(f"Failed to delete status message. Error: {e}")
            
            # Send files as media group if multiple, or single if one
            files = result["files"]
            
            if len(files) == 1:
                file_path = files[0]
                with open(file_path, "rb") as file:
                    if file_path.lower().endswith((".mp4", ".mov")):
                        bot.send_video(chat_id, file, reply_to_message_id=message_id)
                    else:
                        bot.send_photo(chat_id, file, reply_to_message_id=message_id)
            else:
                # Send as media group (max 10 items per group)
                for i in range(0, len(files), 10):
                    batch = files[i:i+10]
                    media_group = []
                    
                    for file_path in batch:
                        with open(file_path, "rb") as f:
                            file_data = f.read()
                        
                        if file_path.lower().endswith((".mp4", ".mov")):
                            media_group.append(telebot.types.InputMediaVideo(file_data))
                        else:
                            media_group.append(telebot.types.InputMediaPhoto(file_data))
                    
                    if media_group:
                        bot.send_media_group(
                            chat_id, 
                            media_group, 
                            reply_to_message_id=message_id if i == 0 else None
                        )
            
            track_url_success()
            log.info(f"Successfully sent {len(files)} file(s) from {url}")
            
        except Exception as e:
            log.error(f"Failed to send files to {chat_id}. Error: {e}")
            track_url_failed()
            if status_message_id:
                try:
                    bot.edit_message_text(
                        "Failed to upload the file(s). Probably too big.",
                        chat_id,
                        status_message_id
                    )
                except:
                    bot.send_message(chat_id, "Failed to upload the file(s). Probably too big.", reply_to_message_id=message_id)
    else:
        log.error(f"Downloading failed. Post: {url}")
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
        import shutil
        if os.path.exists(post.download_folder):
            shutil.rmtree(post.download_folder)
    except Exception as e:
        log.error(f"Failed to remove {post.download_folder}. Error: {e}")

