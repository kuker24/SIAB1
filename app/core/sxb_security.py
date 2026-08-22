import base64
import hashlib
import hmac
import json
import os
import time
from typing import Dict, Any

from fastapi import Header, HTTPException
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from app.config import settings

# Helper to get Secret Key from settings or env
def get_app_secret() -> bytes:
    secret = os.getenv("APP_SECRET_KEY", settings.secret_key)
    # Ensure 32 bytes for AES-256
    return hashlib.sha256(secret.encode()).digest()

class SXBSecurity:
    @staticmethod
    def encrypt_data(data: Dict[str, Any]) -> str:
        """
        Encrypts a dictionary using AES-256-CBC.
        Returns base64 encoded string: IV + EncryptedData
        """
        key = get_app_secret()
        iv = os.urandom(16)

        # Prepare Cipher
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # Pad data
        padder = padding.PKCS7(128).padder()
        json_data = json.dumps(data).encode()
        padded_data = padder.update(json_data) + padder.finalize()

        # Encrypt
        encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()

        # Combine IV + Data and Base64 encode
        result = base64.b64encode(iv + encrypted_bytes).decode()
        return result

    @staticmethod
    def decrypt_data(encrypted_str: str) -> Dict[str, Any]:
        """
        Decrypts a base64 string (IV + EncryptedData) using AES-256-CBC.
        """
        try:
            key = get_app_secret()
            data_bytes = base64.b64decode(encrypted_str)

            # Extract IV (first 16 bytes)
            iv = data_bytes[:16]
            encrypted_payload = data_bytes[16:]

            # Decrypt
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(encrypted_payload) + decryptor.finalize()

            # Unpad
            unpadder = padding.PKCS7(128).unpadder()
            json_data = unpadder.update(padded_data) + unpadder.finalize()

            return json.loads(json_data.decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Decryption failed")

async def verify_app_signature(
    x_app_signature: str = Header(..., alias="X-App-Signature"),
    x_app_timestamp: str = Header(..., alias="X-App-Timestamp"),
    x_app_version: str = Header(..., alias="X-App-Version")
):
    """
    FastAPI Dependency to verify the Private Handshake.
    Signature = HMAC-SHA256(Timestamp, APP_SECRET_KEY)
    """
    try:
        # 1. Verify Timestamp (Prevent Replay Attacks - 5 min window)
        current_time = int(time.time())
        request_time = int(x_app_timestamp)
        if abs(current_time - request_time) > 300:
            raise HTTPException(status_code=403, detail="Request timestamp expired")

        # 2. Verify Message Signature
        key = get_app_secret()
        # Message to sign is just the timestamp (simple handshake)
        message = str(request_time).encode()

        expected_signature = hmac.new(key, message, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_signature.lower(), x_app_signature.lower()):
            raise HTTPException(status_code=403, detail="Invalid App Signature")

        # 3. Version Check (Semantic versioning)
        min_version = "1.0.0"
        try:
            app_ver = tuple(map(int, x_app_version.split('.')))
            min_ver = tuple(map(int, min_version.split('.')))
            if app_ver < min_ver:
                raise HTTPException(status_code=426, detail="App upgrade required")
        except ValueError:
            pass  # If version parse fails, allow through

        return True

    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid headers")
