from __future__ import annotations

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AES_KEY_BYTES = 32
GCM_NONCE_BYTES = 12
PBKDF2_ITERATIONS = 100_000


def generate_doc_key() -> bytes:
    return os.urandom(AES_KEY_BYTES)


def derive_user_key(password_hash: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password_hash.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=AES_KEY_BYTES,
    )


def encrypt_file(data: bytes, key: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(GCM_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return ciphertext, nonce


def decrypt_file(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError("Failed to decrypt file") from exc


def encrypt_key(doc_key: bytes, user_key: bytes) -> bytes:
    nonce = os.urandom(GCM_NONCE_BYTES)
    ciphertext = AESGCM(user_key).encrypt(nonce, doc_key, None)
    return nonce + ciphertext


def decrypt_key(enc_key: bytes, user_key: bytes) -> bytes:
    if len(enc_key) <= GCM_NONCE_BYTES:
        raise ValueError("Encrypted key payload is malformed")

    nonce = enc_key[:GCM_NONCE_BYTES]
    ciphertext = enc_key[GCM_NONCE_BYTES:]
    try:
        return AESGCM(user_key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError("Failed to decrypt document key") from exc
