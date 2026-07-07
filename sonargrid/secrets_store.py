from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from .discovery import now

KEY_PATH = Path(os.environ.get("SONARGRID_SECRET_KEY_FILE", "sonargrid.key"))


def get_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = secrets.token_bytes(32)
    KEY_PATH.write_bytes(key)
    os.chmod(KEY_PATH, 0o600)
    return key


def set_secret(conn, name: str, value: str) -> None:
    payload = encrypt(value, get_key())
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (f"secret.{name}", payload),
    )
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (f"secret_meta.{name}.updated_at", now()),
    )


def get_secret(conn, name: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (f"secret.{name}",)).fetchone()
    if not row:
        return None
    return decrypt(row["value"], get_key())


def has_secret(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM settings WHERE key = ?", (f"secret.{name}",)).fetchone() is not None


def encrypt(value: str, key: bytes) -> str:
    nonce = secrets.token_bytes(16)
    plain = value.encode()
    cipher = xor_stream(plain, key, nonce)
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return base64.b64encode(json.dumps({
        "nonce": base64.b64encode(nonce).decode(),
        "cipher": base64.b64encode(cipher).decode(),
        "tag": base64.b64encode(tag).decode(),
    }).encode()).decode()


def decrypt(payload: str, key: bytes) -> str:
    data = json.loads(base64.b64decode(payload.encode()).decode())
    nonce = base64.b64decode(data["nonce"])
    cipher = base64.b64decode(data["cipher"])
    tag = base64.b64decode(data["tag"])
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("secret authentication failed")
    return xor_stream(cipher, key, nonce).decode()


def xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out))
