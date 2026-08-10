from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE_NAME,
    create_session,
    delete_session,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.dependencies import require_user
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if db.query(User).filter_by(username=username).first() is not None:
        if next:
            # browser form submission: bounce back to the register page with an error
            return RedirectResponse(url=f"/register?error=1&next={next}", status_code=303)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")

    user = User(username=username, password_hash=hash_password(password), is_admin=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    session = create_session(db, user)

    if next:
        redirect = RedirectResponse(url=next, status_code=303)
        _set_session_cookie(redirect, session.token)
        return redirect

    _set_session_cookie(response, session.token)
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.post("/login")
def login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(username=username).first()
    if user is None or not verify_password(password, user.password_hash):
        if next:
            # browser form submission: bounce back to the login page with an error
            return RedirectResponse(url=f"/login?error=1&next={next}", status_code=303)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    session = create_session(db, user)

    if next:
        redirect = RedirectResponse(url=next, status_code=303)
        _set_session_cookie(redirect, session.token)
        return redirect

    _set_session_cookie(response, session.token)
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.post("/logout")
def logout(
    request: Request,
    _: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        delete_session(db, token)
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(SESSION_COOKIE_NAME)
    return redirect
