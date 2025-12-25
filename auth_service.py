import bcrypt
from jose import jwt
from datetime import datetime, timedelta
from fastapi import Request, HTTPException
from functools import wraps

SECRET_KEY = "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_token(coach_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {
        "coach_id": coach_id,
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except:
        return None

def get_current_coach_id(request: Request) -> int | None:
    token = request.cookies.get("session_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return payload.get("coach_id")