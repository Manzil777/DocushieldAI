# Security Audit Report

## 1. Authentication
- Password hashing: yes
- JWT usage: valid
- Observations
- Passwords are hashed with bcrypt before persistence; `backend/tests/security/test_auth_security.py` verifies they are not stored in plain text.
- Access tokens include `sub`, `type`, `iat`, `exp`, and `jti`, and invalid tokens are rejected with HTTP 401.

## 2. Token Management
- Expiry: present
- Refresh tokens: implemented
- Observations
- Access token TTL is driven by `ACCESS_TOKEN_EXPIRE_MINUTES`, and refresh token TTL is driven by `REFRESH_TOKEN_EXPIRE_DAYS`.
- Refresh tokens are tracked in Redis with an in-memory fallback, and expired refresh tokens are rejected even when a stored token record exists.

## 3. Encryption
- Data encryption: implemented for vault storage; delegated/plain storage for document uploads
- Key handling: env-based with insecure fallback defaults present
- Vault files use AES-GCM with a random document key, and the document key is encrypted with a PBKDF2-derived user key.
- JWT and MinIO secrets are environment-based in design, but `backend/app/core/config.py` still falls back to insecure defaults such as `change-me` and `minioadmin`.

## 4. Input Validation
- File upload validation
- `/documents/upload` rejects unsupported file types with HTTP 400 and rejects malformed image content with a controlled HTTP 400 response.
- No explicit upload size limit was found. The security test used a 2 MB malformed JPEG payload to confirm the API returned an error instead of crashing, but this is not true size enforcement.
- API validation behavior
- Malformed JSON requests to `/auth/login` return HTTP 422 validation errors instead of crashing the API.

## 5. Static Analysis (Bandit)
- Summary of findings
- `reports/bandit_report.json` was generated successfully. Bandit reported 319 total results, 0 high-severity issues, and 2 medium-severity issues.
- High/Medium issues (if any)
- Medium: `backend/app/services/ai/augmentation.py:86` (`B108`) flags probable insecure temp file/directory usage.
- Medium: `backend/app/services/ai/qr_validator.py:128` (`B314`) flags `xml.etree.ElementTree.fromstring` on untrusted XML data.

## 6. Risks & Limitations
- Missing features (rate limiting, etc.)
- No rate limiting or login throttling was found on the authentication endpoints.
- No explicit maximum upload size enforcement was found on document uploads.
- Known weaknesses
- `scripts/security_check.py` reported that required runtime secrets and storage/database env vars were not set in the current shell.
- Default MinIO credentials and JWT fallback values remain present in checked config files, which is unsafe if carried into non-development environments.
