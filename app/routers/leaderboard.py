from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_login_page
from app.models import Driver, Event, PointsLog, Season, User
from app.templating import templates

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("")
def season_leaderboard(
    request: Request,
    current_user: User = Depends(require_login_page),
    db: Session = Depends(get_db),
):
    season = db.query(Season).order_by(Season.year.desc()).first()
    rows = []
    if season is not None:
        event_ids = [e.id for e in db.query(Event).filter_by(season_id=season.id).all()]
        users = {u.id: u for u in db.query(User).all()}
        totals = defaultdict(int)
        if event_ids:
            for points_log in db.query(PointsLog).filter(PointsLog.event_id.in_(event_ids)).all():
                totals[points_log.user_id] += points_log.points
        rows = sorted(
            (
                {"user": users[user_id], "total": total}
                for user_id, total in totals.items()
                if user_id in users
            ),
            key=lambda r: r["total"],
            reverse=True,
        )
    return templates.TemplateResponse(
        request, "leaderboard/season.html", {"current_user": current_user, "season": season, "rows": rows}
    )


@router.get("/{event_id}")
def event_leaderboard(
    event_id: int,
    request: Request,
    current_user: User = Depends(require_login_page),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    users = {u.id: u for u in db.query(User).all()}
    by_user = defaultdict(list)
    for points_log in db.query(PointsLog).filter_by(event_id=event_id).all():
        by_user[points_log.user_id].append(points_log)

    rows = []
    for user_id, logs in by_user.items():
        if user_id not in users:
            continue
        by_session = {log.session_type.value: log for log in logs}
        rows.append({"user": users[user_id], "total": sum(log.points for log in logs), "by_session": by_session})
    rows.sort(key=lambda r: r["total"], reverse=True)

    sessions = ["qualifying", "race"]
    if event.has_sprint:
        sessions.insert(1, "sprint")

    driver_names = {d.id: d.name for d in db.query(Driver).filter_by(season_id=event.season_id).all()}

    return templates.TemplateResponse(
        request,
        "leaderboard/event.html",
        {
            "current_user": current_user,
            "event": event,
            "rows": rows,
            "sessions": sessions,
            "driver_names": driver_names,
        },
    )
