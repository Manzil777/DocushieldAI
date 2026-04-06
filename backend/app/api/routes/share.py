from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.services.auth_service import get_db
from app.services.redis_service import InMemoryRedisStore, get_redis_client
from app.services.share_service import get_shared_document_response

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


router = APIRouter(tags=["share"])


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/share/{token}")
def access_shared_document(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    redis_client: "redis.Redis | InMemoryRedisStore" = Depends(get_redis_client),
):
    return get_shared_document_response(
        token=token,
        client_ip=_get_client_ip(request),
        db=db,
        redis_client=redis_client,
    )
