from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE_NAME, get_user_for_session_token
from app.database import get_db
from app.models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return get_user_for_session_token(db, token)


def require_user(current_user: Optional[User] = Depends(get_current_user)) -> User:
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return current_user


def require_admin(current_user: User = Depends(require_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


class NeedsLogin(Exception):
    """Raised by page routes (not JSON API routes) to send the browser to /login."""

    def __init__(self, next_url: str):
        self.next_url = next_url


def require_login_page(request: Request, db: Session = Depends(get_db)) -> User:
    """Like require_user, but for server-rendered pages: redirects to /login
    instead of returning a bare 401 JSON body when not authenticated."""
    current_user = get_current_user(request, db)
    if current_user is None:
        raise NeedsLogin(next_url=request.url.path)
    return current_user


def require_admin_page(current_user: User = Depends(require_login_page)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
