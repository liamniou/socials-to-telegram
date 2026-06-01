"""
Shared statistics module for tracking bot metrics in Redis.
"""
import os
import redis
from urllib.parse import urlparse

# Redis keys
STATS_PREFIX = "socials_to_telegram:stats:"
UNIQUE_USERS_KEY = f"{STATS_PREFIX}unique_users"
URLS_PROCESSED_KEY = f"{STATS_PREFIX}urls_processed"
URLS_SUCCESS_KEY = f"{STATS_PREFIX}urls_success"
URLS_FAILED_KEY = f"{STATS_PREFIX}urls_failed"
URLS_BY_PLATFORM_KEY = f"{STATS_PREFIX}urls_by_platform"


def get_redis_connection():
    """Get Redis connection using environment variables."""
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    return redis.Redis(host=redis_host, port=redis_port, decode_responses=True)


def track_user(user_id: int):
    """Track a unique user."""
    try:
        conn = get_redis_connection()
        conn.sadd(UNIQUE_USERS_KEY, str(user_id))
    except Exception:
        pass  # Don't fail on stats errors


def track_url_requested(url: str):
    """Track a URL that was requested for processing."""
    try:
        conn = get_redis_connection()
        conn.incr(URLS_PROCESSED_KEY)
        
        # Track by platform
        platform = get_platform(url)
        if platform:
            conn.hincrby(URLS_BY_PLATFORM_KEY, platform, 1)
    except Exception:
        pass


def track_url_success():
    """Track a successfully processed URL."""
    try:
        conn = get_redis_connection()
        conn.incr(URLS_SUCCESS_KEY)
    except Exception:
        pass


def track_url_failed():
    """Track a failed URL processing."""
    try:
        conn = get_redis_connection()
        conn.incr(URLS_FAILED_KEY)
    except Exception:
        pass


def get_platform(url: str) -> str:
    """Extract platform name from URL."""
    domain = urlparse(url).netloc.lower()
    if "tiktok" in domain:
        return "tiktok"
    elif "instagram" in domain:
        return "instagram"
    elif "twitter" in domain or "x.com" in domain:
        return "twitter"
    elif "youtube" in domain or "youtu.be" in domain:
        return "youtube"
    return "other"


def get_stats() -> dict:
    """Get all statistics."""
    try:
        conn = get_redis_connection()
        return {
            "unique_users": conn.scard(UNIQUE_USERS_KEY) or 0,
            "urls_processed": int(conn.get(URLS_PROCESSED_KEY) or 0),
            "urls_success": int(conn.get(URLS_SUCCESS_KEY) or 0),
            "urls_failed": int(conn.get(URLS_FAILED_KEY) or 0),
            "urls_by_platform": conn.hgetall(URLS_BY_PLATFORM_KEY) or {},
        }
    except Exception:
        return {
            "unique_users": 0,
            "urls_processed": 0,
            "urls_success": 0,
            "urls_failed": 0,
            "urls_by_platform": {},
        }

