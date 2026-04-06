# Antigravity IDE Handoff

Read these first before making any decisions:

1. `CLAUDE.md`
2. `DOCUSHIELD_PRD.md`
3. the entire `.agent/` folder, especially:
   - `.agent/ROADMAP.md`
   - `.agent/GETSHITDONE.md`
   - `.agent/INDEX.md`

Then check the GitHub repository issues and milestones to verify what has already been completed from:
- Week 1
- Week 2
- some Week 3 issues

## Context

- This project is not at kickoff anymore.
- A significant amount of Week 1 and Week 2 work has already been completed.
- The project is already in Week 3.
- Some Week 3 work is also already done or in progress.
- Do not assume `.agent/INDEX.md` is fully up to date without verifying against the actual codebase and GitHub issues.

## What To Do First

- Read `CLAUDE.md`, `DOCUSHIELD_PRD.md`, and `.agent/*`
- Inspect the current codebase
- Check the GitHub repo issues, milestones, and closed/completed items
- Reconcile docs, code, and GitHub issue status before planning or implementing anything

## Current Repo Reality

- Week 1 foundations are already present in the repo
- Week 2 backend/core work is already present in the repo
- Week 3 has already started, and some Week 3 items are already implemented or underway

## Already Present In The Codebase

- FastAPI backend scaffold
- Expo Router mobile scaffold
- JWT auth routes and auth flow
- document upload flow
- document masking flow
- database models and migrations for core entities
- backend integration tests for auth/upload/mask
- mobile camera capture screen
- mobile processing loader / polling flow

## Your Task

Build a current status summary of the project using 3 sources together:

1. repo code
2. local project docs
3. GitHub issues/milestones

Identify:
- which Week 1 issues are already done
- which Week 2 issues are already done
- which Week 3 issues are already done
- which Week 3 issues are already done
- which issues remain open(week 4)

Explicitly note any mismatch between:
- `.agent/INDEX.md`
- `.agent/ROADMAP.md`
- actual code in the repo
- GitHub issue status

## Instruction Boundary

- Do not restart or re-plan already completed Week 1 and Week 2 work.
- Treat the project as already being in Week 3.
- Continue from the verified current state after reconciliation.

## Recent Backend Work Completed

- Previous task completed: secure vault CRUD for encrypted document storage.
  - Added AES-256-GCM file encryption and wrapped per-document keys with a PBKDF2-derived user key.
  - Added vault upload/list/download/delete routes in `backend/app/api/routes/vault.py`.
  - Updated `VaultItem` to store `filename`, `storage_path`, `encrypted_key`, and `nonce`.
  - Extended storage integration with delete support and added `backend/app/services/crypto_service.py`.
  - Added vault tests in `backend/tests/test_vault.py`.

- Current task completed: secure share-token flow for vault items with Redis TTL and QR code support.
  - Added `POST /vault/{id}/share` and public `GET /share/{token}` access.
  - Added Redis-backed share token storage with TTL and atomic Redis `INCR` view counters in `backend/app/services/redis_service.py`.
  - Added QR PNG generation as base64 in `backend/app/services/qr_service.py`.
  - Updated `ShareToken` persistence fields to include `user_id`, `created_at`, `expires_at`, and nullable `max_views`.
  - Refactored vault decryption so direct vault downloads and share-link downloads reuse the same retrieval path.
  - Added share tests in `backend/tests/test_share.py`.

- Follow-up completed: safe Alembic migration for the new vault/share schema.
  - Added `backend/alembic/versions/7f6b7d1c2e4a_archive_legacy_vault_and_upgrade_share.py`.
  - Migration archives old `vault_items` and `share_tokens` rows into `*_legacy_archive` tables before recreating the active runtime tables.
  - This is intentional because legacy vault rows do not contain a recoverable AES-GCM nonce, so keeping them active would cause decryption failures.
  - Updated `backend/alembic/env.py` to force imports from `backend/app` during migration execution and avoid the repo-root `app.py` collision.

- Latest backend work completed: Issue #30 public masked-document share endpoint.
  - Added a dedicated public share route in `backend/app/api/routes/share.py` and moved `/share/{token}` handling out of `backend/app/api/routes/vault.py`.
  - Added `backend/app/services/share_service.py` to keep the route thin and centralize:
    - IP rate limiting at `10 requests / minute` using Redis key format `rl:{ip}`
    - Redis-first token validation for document shares
    - atomic view-count increment logic for document shares
    - PostgreSQL persistence updates for `view_count`
    - masked response assembly with preview base64 and MinIO/local-storage presigned PDF URL
  - Updated `backend/app/api/routes/documents.py` so `/documents/{id}/masked-pdf` now materializes document share metadata for the returned `share_token`.
  - Extended `ShareToken` in `backend/app/models/vault.py` to support document-backed shares with:
    - nullable `document_id`
    - persisted `view_count`
    - persisted `masked_fields`
    - nullable `vault_item_id` so both vault-share and document-share records can coexist
  - Added the reverse relationship from `Document` to `ShareToken` in `backend/app/models/document.py`.
  - Extended `backend/app/services/redis_service.py` with hash-style in-memory Redis behavior needed for document share metadata caching.
  - Added Alembic migration `backend/alembic/versions/8c3d4b2a9f10_add_document_share_fields_to_share_tokens.py` for the new `share_tokens` columns/indexes.
  - Added integration-oriented coverage updates in:
    - `backend/tests/integration/test_mask_flow.py`
    - `backend/tests/integration/conftest.py`
    - `backend/tests/test_share.py`
  - Response shape for public masked shares is now:
    - `document`: base64-encoded masked preview image
    - `fields`: masked/precomputed field values only
    - `pdf_url`: presigned URL for the masked PDF
    - `expires_at`: share expiry timestamp
  - Important: the old vault share behavior still works, but `/share/{token}` now dispatches through the new share service and supports both legacy vault-share records and the new masked-document share records.

## Verification

- Ran `pytest backend/tests/test_share.py backend/tests/test_vault.py backend/tests/integration/test_auth_flow.py -q`
- Result: `11 passed`

- For Issue #30, `py_compile` passed for the modified backend modules.
- Full `pytest` against the auth-backed integration path stalled in this environment before reaching the new share code, so verification was done directly against an in-memory DB/Redis setup for the new share service logic.
- Direct verification confirmed:
  - valid masked share returns `200`
  - max views exceeded returns `403`
  - expired token returns `410`
  - the 11th request from the same IP returns `429`
