"""Authentication helpers for web sessions."""

import bcrypt
from itsdangerous import URLSafeTimedSerializer

from app.config import settings

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"uid": user_id}, salt="session")


def decode_session_token(token: str, max_age: int = 86400 * 30) -> int | None:
    try:
        data = serializer.loads(token, salt="session", max_age=max_age)
        return data.get("uid")
    except Exception:
        return None
