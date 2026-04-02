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
- which Week 3 issues are in progress
- which issues remain open

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

## Verification

- Ran `pytest backend/tests/test_share.py backend/tests/test_vault.py backend/tests/integration/test_auth_flow.py -q`
- Result: `11 passed`
