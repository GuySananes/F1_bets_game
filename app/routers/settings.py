from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.database import get_db
from app.dependencies import require_login_page
from app.models import User
from app.templating import templates

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/")
def settings_page(
    request: Request,
    current_user: User = Depends(require_login_page),
    error: Optional[str] = None,
    success: Optional[str] = None,
):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"current_user": current_user, "error": error, "success": success},
    )


@router.post("/")
def update_settings(
    request: Request,
    current_password: str = Form(...),
    new_username: str = Form(""),
    new_password: str = Form(""),
    current_user: User = Depends(require_login_page),
    db: Session = Depends(get_db),
):
    error = None
    success = None

    if not verify_password(current_password, current_user.password_hash):
        error = "Current password is incorrect."
    elif not new_username.strip() and not new_password:
        error = "Enter a new username or a new password to change something."
    else:
        new_username = new_username.strip()
        if new_username and new_username != current_user.username:
            existing = db.query(User).filter(User.username == new_username, User.id != current_user.id).first()
            if existing is not None:
                error = "That username is already taken."
            else:
                current_user.username = new_username

        if error is None and new_password:
            current_user.password_hash = hash_password(new_password)

        if error is None:
            db.commit()
            db.refresh(current_user)
            success = "Settings updated."

    return templates.TemplateResponse(
        request,
        "settings.html",
        {"current_user": current_user, "error": error, "success": success},
        status_code=400 if error else 200,
    )
