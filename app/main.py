from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.dependencies import NeedsLogin
from app.routers import admin, auth, leaderboard, pages, predictions

app = FastAPI(title="F1 Prediction League")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(pages.router)
app.include_router(predictions.router)
app.include_router(leaderboard.router)


@app.exception_handler(NeedsLogin)
def needs_login_handler(request: Request, exc: NeedsLogin):
    return RedirectResponse(url=f"/login?next={exc.next_url}", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
