from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_file = tempfile.NamedTemporaryFile(prefix="docushield_auth_", suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient

from app.main import app


def main() -> int:
    client = TestClient(app)
    email = "auth-test@example.com"
    password = "securepass123"

    register_response = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    print("register", register_response.status_code, register_response.json())

    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    print("login", login_response.status_code, login_response.json())
    tokens = login_response.json()
    refresh_token = tokens["refresh_token"]
    access_token = tokens["access_token"]

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    print("me", me_response.status_code, me_response.json())

    refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    print("refresh", refresh_response.status_code, refresh_response.json())

    invalid_refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid-token"},
    )
    print("invalid_refresh", invalid_refresh_response.status_code, invalid_refresh_response.json())

    logout_response = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    print("logout", logout_response.status_code, logout_response.json())

    post_logout_refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    print("post_logout_refresh", post_logout_refresh.status_code, post_logout_refresh.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
