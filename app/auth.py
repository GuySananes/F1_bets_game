import secrets
from datetime import datetime, timedelta
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models import User, UserSession

SESSION_COOKIE_NAME = "session_token"
SESSION_LIFETIME = timedelta(days=30)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_session(db: Session, user: User) -> UserSession:
    session = UserSession(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.utcnow() + SESSION_LIFETIME,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_user_for_session_token(db: Session, token: str) -> Optional[User]:
    if not token:
        return None
    session = db.get(UserSession, token)
    if session is None:
        return None
    if session.expires_at < datetime.utcnow():
        db.delete(session)
        db.commit()
        return None
    return db.get(User, session.user_id)


def delete_session(db: Session, token: str) -> None:
    session = db.get(UserSession, token)
    if session is not None:
        db.delete(session)
        db.commit()
