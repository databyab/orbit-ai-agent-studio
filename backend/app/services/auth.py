import hmac
import hashlib
import time
from typing import Optional
from fastapi import Header, HTTPException, status
import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()

def verify_hmac_identity(user_id: str, user_hash: str, secret_key: str) -> bool:
    """
    Verifies user identity hash generated via:
    user_hash = hmac_sha256(user_id, secret_key)
    Timing-attack safe comparison via hmac.compare_digest.
    """
    if not user_id or not user_hash or not secret_key:
        return False
    expected = hmac.new(secret_key.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, user_hash)

class SlidingWindowRateLimiter:
    """
    Implements Chatbase's sliding-window rate limit:
    1,000 requests per 10-second sliding window per API key/IP.
    """
    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis = redis_client

    async def check_rate_limit(self, identifier: str, limit: int = 1000, window: int = 10) -> dict:
        if not self.redis:
            # Fallback if redis is disabled in dev
            return {"allowed": True, "remaining": limit, "reset": int(time.time()) + window}

        now = time.time()
        key = f"ratelimit:{identifier}"
        clear_before = now - window

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, clear_before)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window + 5)
        results = await pipe.execute()

        request_count = results[2]
        remaining = max(0, limit - request_count)
        reset_time = int(now) + window

        if request_count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. 1,000 requests per 10 seconds allowed.",
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(window)
                }
            )

        return {
            "allowed": True,
            "limit": limit,
            "remaining": remaining,
            "reset": reset_time
        }
