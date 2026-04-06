from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import APP_BASE_URL
from app.models import ShareToken, User, VaultItem
from app.services.auth_service import get_current_user, get_db
from app.services.crypto_service import (
    decrypt_file,
    decrypt_key,
    derive_user_key,
    encrypt_file,
    encrypt_key,
    generate_doc_key,
)
from app.services.qr_service import generate_qr_base64
from app.services.redis_service import delete_token, set_token
from app.services.storage_service import delete_file, download_file, upload_file


router = APIRouter(prefix="/vault", tags=["vault"])
logger = logging.getLogger(__name__)
DEFAULT_SHARE_TTL_HOURS = 24
MAX_SHARE_TTL_HOURS = 168


class ShareTokenCreateRequest(BaseModel):
    ttl_hours: int = Field(default=DEFAULT_SHARE_TTL_HOURS, ge=1, le=MAX_SHARE_TTL_HOURS)
    max_views: int | None = Field(default=None, ge=1)


def _parse_uuid(value: str, detail: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


def _load_user(db: Session, current_user: str) -> User:
    user_id = _parse_uuid(current_user, "Invalid authentication token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _get_vault_item(db: Session, item_id: str) -> VaultItem:
    vault_id = _parse_uuid(item_id, "Invalid vault item ID")
    item = db.get(VaultItem, vault_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vault item not found")
    return item


def _require_owner(item: VaultItem, user: User) -> None:
    if item.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this vault item")


def _decrypt_vault_item(item: VaultItem, user: User) -> bytes:
    encrypted_file = download_file(item.storage_path)
    user_key = derive_user_key(user.hashed_password, str(user.id).encode("utf-8"))
    doc_key = decrypt_key(item.encrypted_key, user_key)
    return decrypt_file(encrypted_file, doc_key, item.nonce)


def _build_file_response(plaintext: bytes, filename: str) -> StreamingResponse:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(BytesIO(plaintext), media_type="application/octet-stream", headers=headers)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_vault_item(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = _load_user(db, current_user)
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    item_id = uuid4()
    doc_key = generate_doc_key()
    user_key = derive_user_key(user.hashed_password, str(user.id).encode("utf-8"))

    try:
        ciphertext, nonce = encrypt_file(file_bytes, doc_key)
        encrypted_key = encrypt_key(doc_key, user_key)
    except Exception as exc:
        logger.exception("Failed to encrypt vault item for user %s", user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to encrypt file") from exc

    storage_path = f"vault/{user.id}/{item_id}.enc"

    try:
        upload_file(ciphertext, storage_path, content_type="application/octet-stream")
    except Exception as exc:
        logger.exception("Failed to store vault item %s", item_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to store encrypted file") from exc

    vault_item = VaultItem(
        id=item_id,
        user_id=user.id,
        filename=file.filename,
        storage_path=storage_path,
        encrypted_key=encrypted_key,
        nonce=nonce,
    )
    try:
        db.add(vault_item)
        db.commit()
        db.refresh(vault_item)
    except Exception as exc:
        db.rollback()
        try:
            delete_file(storage_path)
        except Exception:
            logger.warning("Failed to clean up orphaned vault blob %s", storage_path)
        logger.exception("Failed to persist vault item %s", item_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save vault metadata") from exc

    return {
        "id": str(vault_item.id),
        "filename": vault_item.filename,
        "storage_path": vault_item.storage_path,
    }


@router.get("/")
def list_vault_items(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    user = _load_user(db, current_user)
    items = (
        db.query(VaultItem)
        .filter(VaultItem.user_id == user.id)
        .order_by(VaultItem.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(item.id),
            "filename": item.filename,
            "storage_path": item.storage_path,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


@router.get("/{id}")
def get_vault_item(
    id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user = _load_user(db, current_user)
    item = _get_vault_item(db, id)
    _require_owner(item, user)

    try:
        plaintext = _decrypt_vault_item(item, user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored vault file not found") from exc
    except ValueError as exc:
        logger.warning("Decryption failed for vault item %s", item.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to retrieve vault item %s", item.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve vault item") from exc

    return _build_file_response(plaintext, item.filename)


@router.post("/{id}/share", status_code=status.HTTP_201_CREATED)
def create_share_token(
    id: str,
    payload: ShareTokenCreateRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = _load_user(db, current_user)
    item = _get_vault_item(db, id)
    _require_owner(item, user)

    token = str(uuid4())
    ttl_seconds = payload.ttl_hours * 3600
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    share_url = f"{APP_BASE_URL.rstrip('/')}/share/{token}"

    try:
        set_token(
            token,
            {
                "vault_item_id": str(item.id),
                "user_id": str(user.id),
                "max_views": payload.max_views,
            },
            ttl_seconds,
        )
    except Exception as exc:
        logger.exception("Failed to store share token %s in redis", token)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create share token") from exc

    share_token = ShareToken(
        user_id=user.id,
        vault_item_id=item.id,
        token=token,
        expires_at=expires_at,
        max_views=payload.max_views,
    )
    try:
        db.add(share_token)
        db.commit()
    except Exception as exc:
        db.rollback()
        delete_token(token)
        logger.exception("Failed to persist share token %s", token)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save share token") from exc

    return {
        "token": token,
        "share_url": share_url,
        "qr_code": generate_qr_base64(share_url),
        "expires_at": expires_at.isoformat(),
    }


@router.delete("/{id}")
def delete_vault_item(
    id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = _load_user(db, current_user)
    item = _get_vault_item(db, id)
    _require_owner(item, user)

    for share_token in item.share_tokens:
        delete_token(share_token.token)

    try:
        delete_file(item.storage_path)
    except FileNotFoundError:
        logger.warning("Vault file already missing for item %s", item.id)
    except Exception as exc:
        logger.exception("Failed to delete stored vault file %s", item.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete vault item") from exc

    db.delete(item)
    db.commit()
    return {"message": "Vault item deleted successfully"}
