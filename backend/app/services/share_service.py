from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any
from uuid import UUID

import redis
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, or_, select, update
from sqlalchemy.orm import Session

from app.models import Document, ShareToken, User, VaultItem
from app.services.crypto_service import decrypt_file, decrypt_key, derive_user_key
from app.services.redis_service import (
    InMemoryRedisStore,
    delete_token,
    get_token,
    increment_views,
)
from app.services.storage_service import download_file, generate_presigned_url


logger = logging.getLogger(__name__)

DEFAULT_DOCUMENT_SHARE_TTL_SECONDS = 24 * 3600
DEFAULT_PRESIGNED_URL_TTL_SECONDS = 600
RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
DOCUMENT_SHARE_INCREMENT_LUA = """
local key = KEYS[1]
if redis.call("EXISTS", key) == 0 then
    return {-1, 0}
end
local max_views = redis.call("HGET", key, "max_views")
local current = tonumber(redis.call("HGET", key, "view_count") or "0")
if max_views and max_views ~= "" and current >= tonumber(max_views) then
    return {-2, current}
end
current = redis.call("HINCRBY", key, "view_count", 1)
return {current, 0}
"""
PII_FIELD_ALIASES = {
    "uid": "uid",
    "aadhaar_number": "uid",
    "dob": "dob",
    "name": "name",
    "address": "address",
    "gender": "gender",
}

RedisClient = redis.Redis | InMemoryRedisStore


class CacheTokenMissingError(RuntimeError):
    pass


class ShareViewsExceededError(RuntimeError):
    pass


def ensure_document_share_token(
    *,
    document: Document,
    token: str,
    db: Session,
    redis_client: RedisClient,
    ttl_seconds: int = DEFAULT_DOCUMENT_SHARE_TTL_SECONDS,
    max_views: int | None = None,
) -> ShareToken:
    if document.parent_document_id is None:
        raise ValueError("Only masked documents can be shared publicly")
    if not document.preview_file_path:
        raise ValueError("Masked document preview is missing")

    now = _utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)
    masked_fields = _build_masked_fields(document.extracted_fields)

    share_record = db.scalar(select(ShareToken).where(ShareToken.token == token))
    if share_record is None:
        share_record = ShareToken(
            user_id=document.user_id,
            document_id=document.id,
            vault_item_id=None,
            token=token,
            expires_at=expires_at,
            max_views=max_views,
            view_count=0,
            masked_fields=masked_fields,
        )
        db.add(share_record)
    else:
        was_expired = _normalize_datetime(share_record.expires_at) <= now
        share_record.user_id = document.user_id
        share_record.document_id = document.id
        share_record.vault_item_id = None
        share_record.expires_at = expires_at
        share_record.max_views = max_views
        share_record.masked_fields = masked_fields
        if was_expired:
            share_record.view_count = 0

    db.commit()
    db.refresh(share_record)

    try:
        _cache_document_share_record(redis_client, share_record, document, ttl_seconds)
    except Exception:
        logger.exception("Failed to cache document share token %s", token)

    return share_record


def get_shared_document_response(
    *,
    token: str,
    client_ip: str,
    db: Session,
    redis_client: RedisClient,
) -> dict[str, Any] | StreamingResponse:
    _enforce_rate_limit(redis_client, client_ip)

    share_record = db.scalar(select(ShareToken).where(ShareToken.token == token))
    if share_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share token not found")

    if share_record.document_id is not None:
        return _build_document_share_response(
            token=token,
            share_record=share_record,
            db=db,
            redis_client=redis_client,
        )

    return _build_legacy_vault_share_response(token=token, share_record=share_record, db=db)


def _build_document_share_response(
    *,
    token: str,
    share_record: ShareToken,
    db: Session,
    redis_client: RedisClient,
) -> dict[str, Any]:
    expires_at = _normalize_datetime(share_record.expires_at)
    if expires_at <= _utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share token has expired")

    document = db.get(Document, share_record.document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Masked document not found")

    if not document.preview_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Masked document preview not found")

    _increment_document_share_views(redis_client=redis_client, share_record=share_record, db=db, document=document)

    try:
        preview_bytes = download_file(document.preview_file_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Masked document preview not found") from exc
    except Exception as exc:
        logger.exception("Failed to load masked preview for document %s", document.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load masked document preview",
        ) from exc

    pdf_ttl_seconds = min(
        DEFAULT_PRESIGNED_URL_TTL_SECONDS,
        max(1, int((expires_at - _utcnow()).total_seconds())),
    )

    return {
        "document": base64.b64encode(preview_bytes).decode("ascii"),
        "fields": share_record.masked_fields or _build_masked_fields(document.extracted_fields),
        "pdf_url": generate_presigned_url(document.file_path, expires_in_seconds=pdf_ttl_seconds),
        "expires_at": expires_at.isoformat(),
    }


def _increment_document_share_views(
    *,
    redis_client: RedisClient,
    share_record: ShareToken,
    db: Session,
    document: Document,
) -> int:
    try:
        next_count = _increment_document_share_views_in_cache(redis_client, share_record.token)
    except CacheTokenMissingError:
        return _increment_document_share_views_in_db(
            db=db,
            share_record=share_record,
            redis_client=redis_client,
            document=document,
        )
    except ShareViewsExceededError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Share token view limit exceeded") from exc
    except redis.RedisError:
        logger.exception("Redis failed during share view increment for token %s", share_record.token)
        return _increment_document_share_views_in_db(
            db=db,
            share_record=share_record,
            redis_client=redis_client,
            document=document,
        )

    try:
        db.execute(
            update(ShareToken)
            .where(ShareToken.id == share_record.id)
            .values(
                view_count=case(
                    (ShareToken.view_count < next_count, next_count),
                    else_=ShareToken.view_count,
                )
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist share view count for token %s", share_record.token)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update share token",
        ) from exc

    share_record.view_count = max(share_record.view_count, next_count)
    return next_count


def _increment_document_share_views_in_cache(redis_client: RedisClient, token: str) -> int:
    key = _share_key(token)

    if isinstance(redis_client, InMemoryRedisStore):
        mapping = redis_client.hgetall(key)
        if not mapping:
            raise CacheTokenMissingError(token)
        max_views = int(mapping["max_views"]) if mapping.get("max_views") else None
        current = int(mapping.get("view_count", "0"))
        if max_views is not None and current >= max_views:
            raise ShareViewsExceededError(token)
        next_count = current + 1
        redis_client.hset_field(key, "view_count", next_count)
        return next_count

    result = redis_client.eval(DOCUMENT_SHARE_INCREMENT_LUA, 1, key)
    if not isinstance(result, list) or not result:
        raise CacheTokenMissingError(token)

    code = int(result[0])
    if code == -1:
        raise CacheTokenMissingError(token)
    if code == -2:
        raise ShareViewsExceededError(token)
    return code


def _increment_document_share_views_in_db(
    *,
    db: Session,
    share_record: ShareToken,
    redis_client: RedisClient,
    document: Document,
) -> int:
    now = _utcnow()
    if _normalize_datetime(share_record.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share token has expired")

    result = db.execute(
        update(ShareToken)
        .where(ShareToken.id == share_record.id)
        .where(ShareToken.expires_at > now)
        .where(or_(ShareToken.max_views.is_(None), ShareToken.view_count < ShareToken.max_views))
        .values(view_count=ShareToken.view_count + 1)
    )
    if result.rowcount != 1:
        db.rollback()
        db.refresh(share_record)
        if _normalize_datetime(share_record.expires_at) <= now:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share token has expired")
        if share_record.max_views is not None and share_record.view_count >= share_record.max_views:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Share token view limit exceeded")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share token not found")

    db.commit()
    db.refresh(share_record)

    ttl_seconds = max(1, int((_normalize_datetime(share_record.expires_at) - now).total_seconds()))
    try:
        _cache_document_share_record(redis_client, share_record, document, ttl_seconds)
    except Exception:
        logger.exception("Failed to refresh cache for share token %s after DB fallback", share_record.token)

    return share_record.view_count


def _cache_document_share_record(
    redis_client: RedisClient,
    share_record: ShareToken,
    document: Document,
    ttl_seconds: int,
) -> None:
    if not document.preview_file_path:
        raise ValueError("Masked document preview is missing")

    payload = {
        "document_id": str(document.id),
        "expires_at": _normalize_datetime(share_record.expires_at).isoformat(),
        "max_views": "" if share_record.max_views is None else str(share_record.max_views),
        "view_count": str(share_record.view_count),
        "preview_file_path": document.preview_file_path,
        "pdf_file_path": document.file_path,
        "masked_fields": json.dumps(share_record.masked_fields or _build_masked_fields(document.extracted_fields)),
    }
    key = _share_key(share_record.token)
    redis_client.delete(key)
    redis_client.hset(key, mapping=payload)
    redis_client.expire(key, ttl_seconds)


def _build_legacy_vault_share_response(
    *,
    token: str,
    share_record: ShareToken,
    db: Session,
) -> StreamingResponse:
    token_data = get_token(token)
    if token_data is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share token has expired")

    try:
        views = increment_views(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc

    max_views = token_data.get("max_views")
    if max_views is not None and views > int(max_views):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Share token view limit exceeded")

    item = db.get(VaultItem, UUID(str(token_data["vault_item_id"])))
    if item is None:
        delete_token(token)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vault item not found")

    owner = db.get(User, UUID(str(token_data["user_id"])))
    if owner is None or owner.id != item.user_id or share_record.user_id != owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share token not found")

    try:
        plaintext = _decrypt_vault_item(item, owner)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored vault file not found") from exc
    except ValueError as exc:
        logger.warning("Decryption failed for shared vault item %s", item.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to retrieve shared vault item %s", item.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shared vault item",
        ) from exc

    try:
        db.execute(
            update(ShareToken)
            .where(ShareToken.id == share_record.id)
            .values(
                view_count=case(
                    (ShareToken.view_count < views, views),
                    else_=ShareToken.view_count,
                )
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist legacy share view count for token %s", token)

    headers = {"Content-Disposition": f'attachment; filename="{item.filename}"'}
    return StreamingResponse(BytesIO(plaintext), media_type="application/octet-stream", headers=headers)


def _decrypt_vault_item(item: VaultItem, user: User) -> bytes:
    encrypted_file = download_file(item.storage_path)
    user_key = derive_user_key(user.hashed_password, str(user.id).encode("utf-8"))
    doc_key = decrypt_key(item.encrypted_key, user_key)
    return decrypt_file(encrypted_file, doc_key, item.nonce)


def _build_masked_fields(extracted_fields: dict[str, Any]) -> dict[str, str]:
    return {
        field_name: _mask_field_value(field_name, value)
        for field_name, value in extracted_fields.items()
    }


def _mask_field_value(field_name: str, value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    normalized = PII_FIELD_ALIASES.get(field_name.lower(), field_name.lower())
    if normalized == "uid":
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 4:
            return f"XXXX XXXX {digits[-4:]}"
        return "XXXX XXXX XXXX"
    if normalized == "dob":
        return "XX/XX/XXXX"
    if normalized == "name":
        parts = [part for part in text.split() if part]
        return " ".join(f"{part[0]}{'*' * max(0, len(part) - 1)}" for part in parts) or "REDACTED"
    if normalized == "gender":
        return f"{text[0]}{'*' * max(0, len(text) - 1)}"
    if normalized == "address":
        return "REDACTED"
    return "REDACTED"


def _enforce_rate_limit(redis_client: RedisClient, client_ip: str) -> None:
    key = f"rl:{client_ip}"
    current = redis_client.get(key)
    if current is None:
        redis_client.set(key, 1, ex=RATE_LIMIT_WINDOW_SECONDS)
        return

    count = int(redis_client.incr(key))
    if count > RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _share_key(token: str) -> str:
    return f"share:{token}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
