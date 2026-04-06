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
        self._hash_store: dict[str, dict[str, str]] = {}
        self._expires_at: dict[str, datetime] = {}

    def _is_expired(self, key: str) -> bool:
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return False
        if datetime.now(timezone.utc) < expires_at:
            return False
        self._store.pop(key, None)
        self._hash_store.pop(key, None)
        self._expires_at.pop(key, None)
        return True

    def set(self, key: str, value: str | int, ex: int | timedelta | None = None) -> bool:
        self._store[key] = str(value)
        self._hash_store.pop(key, None)
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
            if key in self._hash_store:
                del self._hash_store[key]
                deleted += 1
            self._expires_at.pop(key, None)
        return deleted

    def incr(self, key: str) -> int:
        if self._is_expired(key):
            raise KeyError(key)
        current = int(self._store.get(key, "0")) + 1
        self._store[key] = str(current)
        return current

    def expire(self, key: str, ex: int | timedelta) -> bool:
        if self._is_expired(key):
            return False
        if key not in self._store and key not in self._hash_store:
            return False
        ttl_seconds = int(ex.total_seconds()) if isinstance(ex, timedelta) else int(ex)
        self._expires_at[key] = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        return True

    def hset(self, key: str, mapping: dict[str, Any]) -> int:
        if self._is_expired(key):
            self._hash_store.pop(key, None)
        existing = self._hash_store.setdefault(key, {})
        self._store.pop(key, None)
        before = len(existing)
        existing.update({field: str(value) for field, value in mapping.items()})
        return len(existing) - before

    def hgetall(self, key: str) -> dict[str, str]:
        if self._is_expired(key):
            return {}
        return dict(self._hash_store.get(key, {}))

    def hset_field(self, key: str, field: str, value: str | int) -> bool:
        if self._is_expired(key):
            raise KeyError(key)
        mapping = self._hash_store.get(key)
        if mapping is None:
            raise KeyError(key)
        mapping[field] = str(value)
        return True

    def ttl(self, key: str) -> int:
        if self._is_expired(key):
            return -2
        if key not in self._store and key not in self._hash_store:
            return -2
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return -1
        return max(0, ceil((expires_at - datetime.now(timezone.utc)).total_seconds()))

    def force_expire(self, *keys: str) -> None:
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        for key in keys:
            if key in self._store or key in self._hash_store:
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


def _rate_limit_key(ip_address: str) -> str:
    return f"rl:{ip_address}"


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


def cache_document_share_token(token: str, data: dict[str, Any], ttl: int) -> None:
    client = get_redis_client()
    key = _share_key(token)
    serialized = {
        "document_id": str(data["document_id"]),
        "expires_at": str(data["expires_at"]),
        "max_views": "" if data.get("max_views") is None else str(data["max_views"]),
        "view_count": str(data.get("view_count", 0)),
        "preview_file_path": str(data["preview_file_path"]),
        "pdf_file_path": str(data["pdf_file_path"]),
        "masked_fields": json.dumps(data["masked_fields"]),
    }
    client.delete(key)
    client.hset(key, mapping=serialized)
    client.expire(key, ttl)


def get_cached_document_share_token(token: str) -> dict[str, Any] | None:
    client = get_redis_client()
    key = _share_key(token)
    try:
        mapping = client.hgetall(key)
    except (AttributeError, redis.RedisError):
        return None
    if not mapping:
        return None
    return {
        "document_id": mapping["document_id"],
        "expires_at": mapping["expires_at"],
        "max_views": int(mapping["max_views"]) if mapping.get("max_views") else None,
        "view_count": int(mapping.get("view_count", "0")),
        "preview_file_path": mapping["preview_file_path"],
        "pdf_file_path": mapping["pdf_file_path"],
        "masked_fields": json.loads(mapping["masked_fields"]),
    }


def set_cached_document_share_view_count(token: str, view_count: int) -> None:
    client = get_redis_client()
    key = _share_key(token)
    if isinstance(client, InMemoryRedisStore):
        client.hset_field(key, "view_count", view_count)
        return
    client.hset(key, mapping={"view_count": view_count})


def increment_rate_limit_window(ip_address: str, limit: int, ttl_seconds: int) -> int:
    client = get_redis_client()
    key = _rate_limit_key(ip_address)
    current = client.get(key)
    if current is None:
        client.set(key, 1, ex=ttl_seconds)
        return 1
    count = int(client.incr(key))
    if count > limit and hasattr(client, "ttl") and int(client.ttl(key)) < 0:
        client.expire(key, ttl_seconds)
    return count
