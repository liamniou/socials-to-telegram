import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from video_processor import Video, download_video

# Small, stable, public domain MP4 used as a download smoke test for yt-dlp.
TEST_VIDEO_URL = "https://download.samplelib.com/mp4/sample-5s.mp4"


def test_download_test_video(tmp_path):
    video = Video(url=TEST_VIDEO_URL)
    video.download_folder = str(tmp_path)
    video.download_path = os.path.join(str(tmp_path), video.filename) + "." + video.format

    download_video(video)

    assert os.path.exists(video.download_path), "yt-dlp did not download the test video"
    assert os.path.getsize(video.download_path) > 0, "Downloaded video is empty"
