from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

import redis

from app.core.config import REDIS_URL


class InMemoryRedisStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._expires_at: dict[str, datetime] = {}

    def _is_expired(self, key: str) -> bool:
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return False
        if datetime.now(timezone.utc) < expires_at:
            return False
        self._store.pop(key, None)
        self._expires_at.pop(key, None)
        return True

    def set(self, key: str, value: str | int, ex: int | timedelta | None = None) -> bool:
        self._store[key] = str(value)
        if ex is None:
            self._expires_at.pop(key, None)
        else:
            ttl_seconds = int(ex.total_seconds()) if isinstance(ex, timedelta) else int(ex)
            self._expires_at[key] = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        return True

    def get(self, key: str) -> str | None:
        if self._is_expired(key):
            return None
        return self._store.get(key)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            self._is_expired(key)
            if key in self._store:
                del self._store[key]
                deleted += 1
            self._expires_at.pop(key, None)
        return deleted

    def incr(self, key: str) -> int:
        if self._is_expired(key):
            raise KeyError(key)
        current = int(self._store.get(key, "0")) + 1
        self._store[key] = str(current)
        return current

    def ttl(self, key: str) -> int:
        if self._is_expired(key):
            return -2
        if key not in self._store:
            return -2
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return -1
        return max(0, ceil((expires_at - datetime.now(timezone.utc)).total_seconds()))

    def force_expire(self, *keys: str) -> None:
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        for key in keys:
            if key in self._store:
                self._expires_at[key] = expired_at


_fallback_store = InMemoryRedisStore()


def get_redis_client() -> redis.Redis | InMemoryRedisStore:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        client.ping()
        return client
    except redis.RedisError:
        return _fallback_store


def _share_key(token: str) -> str:
    return f"share:{token}"


def _views_key(token: str) -> str:
    return f"share:{token}:views"


def set_token(token: str, data: dict[str, Any], ttl: int) -> None:
    client = get_redis_client()
    client.set(_share_key(token), json.dumps(data), ex=ttl)
    client.set(_views_key(token), 0, ex=ttl)


def get_token(token: str) -> dict[str, Any] | None:
    value = get_redis_client().get(_share_key(token))
    if value is None:
        return None
    return json.loads(value)


def increment_views(token: str) -> int:
    try:
        return int(get_redis_client().incr(_views_key(token)))
    except (KeyError, redis.RedisError) as exc:
        raise ValueError("Share token has expired") from exc


def get_view_count(token: str) -> int:
    value = get_redis_client().get(_views_key(token))
    return 0 if value is None else int(value)


def get_token_ttl(token: str) -> int:
    client = get_redis_client()
    if hasattr(client, "ttl"):
        return int(client.ttl(_share_key(token)))
    return -2


def delete_token(token: str) -> None:
    get_redis_client().delete(_share_key(token), _views_key(token))
