"""Authentication utilities for student and teacher authentication."""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field


# JWT constants
JWT_SECRET_KEY = "hhx-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
STUDENT_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _base64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_jwt(payload: dict[str, Any], expires_minutes: int | None = None) -> str:
    """Create a JWT token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload_with_exp = {**payload, "exp": int(expire.timestamp())}
    
    header_encoded = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_encoded = _base64url_encode(json.dumps(payload_with_exp, separators=(",", ":")).encode("utf-8"))
    
    signature_input = f"{header_encoded}.{payload_encoded}"
    signature = hmac.new(JWT_SECRET_KEY.encode("utf-8"), signature_input.encode("utf-8"), hashlib.sha256).digest()
    signature_encoded = _base64url_encode(signature)
    
    return f"{header_encoded}.{payload_encoded}.{signature_encoded}"


def decode_jwt(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="無效的令牌")
    
    header_encoded, payload_encoded, signature_encoded = parts
    
    signature_input = f"{header_encoded}.{payload_encoded}"
    expected_signature = hmac.new(
        JWT_SECRET_KEY.encode("utf-8"), 
        signature_input.encode("utf-8"), 
        hashlib.sha256
    ).digest()
    
    provided_signature = _base64url_decode(signature_encoded)
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise HTTPException(status_code=401, detail="無效的令牌")
    
    payload = json.loads(_base64url_decode(payload_encoded).decode("utf-8"))
    
    # Check expiration
    if "exp" in payload:
        if datetime.now(timezone.utc).timestamp() > payload["exp"]:
            raise HTTPException(status_code=401, detail="令牌已過期")
    
    return payload


def create_student_token(student_id: str, student_no: str, grade_id: str) -> str:
    """Create a JWT token for a student."""
    return create_jwt({
        "sub": student_id,
        "student_id": student_id,
        "student_no": student_no,
        "grade_id": grade_id,
        "role": "student",
    }, STUDENT_TOKEN_EXPIRE_MINUTES)


def create_teacher_token(teacher_id: str, school_id: str) -> str:
    """Create a JWT token for a teacher."""
    return create_jwt({
        "sub": teacher_id,
        "teacher_id": teacher_id,
        "school_id": school_id,
        "role": "teacher",
    }, ACCESS_TOKEN_EXPIRE_MINUTES)


class StudentLoginRequest(BaseModel):
    student_no: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=6, max_length=256)
