from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_flow_lifecycle(async_client: AsyncClient) -> None:
    register_response = await async_client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "strongpass123"},
    )
    assert register_response.status_code == 200
    assert register_response.json() == {"message": "User registered successfully"}

    unauthorized_response = await async_client.get("/auth/me")
    assert unauthorized_response.status_code == 401
    assert unauthorized_response.json()["detail"] == "Missing authentication token"

    login_response = await async_client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "strongpass123"},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["token_type"] == "bearer"
    assert login_payload["access_token"]
    assert login_payload["refresh_token"]

    protected_response = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert protected_response.status_code == 200
    protected_payload = protected_response.json()
    assert protected_payload["user_id"]

    refresh_response = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.json()
    assert refresh_payload["token_type"] == "bearer"
    assert refresh_payload["access_token"]
    assert refresh_payload["access_token"] != login_payload["access_token"]

    logout_response = await async_client.post(
        "/auth/logout",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert logout_response.status_code == 200
    assert logout_response.json() == {"message": "Logged out successfully"}

    revoked_refresh_response = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert revoked_refresh_response.status_code == 401
    assert revoked_refresh_response.json()["detail"] == "Refresh token is not active"


@pytest.mark.asyncio
async def test_invalid_login_credentials_are_rejected(async_client: AsyncClient) -> None:
    register_response = await async_client.post(
        "/auth/register",
        json={"email": "wrongpass@example.com", "password": "strongpass123"},
    )
    assert register_response.status_code == 200

    login_response = await async_client.post(
        "/auth/login",
        json={"email": "wrongpass@example.com", "password": "badpass123"},
    )
    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid credentials"
