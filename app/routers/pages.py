from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.templating import templates

router = APIRouter(tags=["pages"])


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    current_user: Optional[User] = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login")
    if current_user.is_admin:
        return RedirectResponse(url="/admin")
    return RedirectResponse(url="/predict")


@router.get("/login")
def login_page(request: Request, next: str = "/admin", error: Optional[str] = None):
    return templates.TemplateResponse(
        request, "login.html", {"next": next, "error": error}
    )
