from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import get_db
from app.dependencies import require_admin, require_admin_page
from app.models import (
    BonusPrediction,
    BonusResult,
    BonusType,
    Driver,
    Event,
    EventEntry,
    PointsLog,
    Prediction,
    Result,
    Season,
    SessionType,
    Team,
    User,
)
from app.points import recompute_session_points
from app.prediction_constants import BONUS_FIELDS, SESSION_LABELS
from app.random_bet import (
    backfill_missing_predictions,
    generate_random_bet_for_user,
    has_any_submission,
    users_missing_submission,
)
from app.routers.predictions import get_entered_drivers
from app.scoring import order_dnf_drivers
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
def ping(current_user: User = Depends(require_admin)):
    return {"pong": True, "admin": current_user.username}


def get_current_season(db: Session) -> Season:
    season = db.query(Season).order_by(Season.year.desc()).first()
    if season is None:
        raise HTTPException(status_code=404, detail="No season exists yet")
    return season


@router.get("/")
def dashboard(
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    season = get_current_season(db)
    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"current_user": current_user, "season": season}
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

RESET_PASSWORD_DEFAULT = "F1"


@router.get("/users")
def list_users(
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse(
        request, "admin/users.html", {"current_user": current_user, "users": users}
    )


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(RESET_PASSWORD_DEFAULT)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

@router.get("/teams")
def list_teams(
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
    error: Optional[str] = None,
):
    season = get_current_season(db)
    teams = db.query(Team).filter_by(season_id=season.id).order_by(Team.name).all()
    return templates.TemplateResponse(
        request,
        "admin/teams.html",
        {"current_user": current_user, "season": season, "teams": teams, "error": error},
    )


@router.post("/teams")
def create_team(
    name: str = Form(...),
    color: Optional[str] = Form(None),
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    season = get_current_season(db)
    db.add(Team(season_id=season.id, name=name, color=color or None))
    db.commit()
    return RedirectResponse(url="/admin/teams", status_code=303)


@router.post("/teams/{team_id}")
def update_team(
    team_id: int,
    name: str = Form(...),
    color: Optional[str] = Form(None),
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    team.name = name
    team.color = color or None
    db.commit()
    return RedirectResponse(url="/admin/teams", status_code=303)


@router.post("/teams/{team_id}/delete")
def delete_team(
    team_id: int,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    if db.query(Driver).filter_by(team_id=team_id).first() is not None:
        return RedirectResponse(
            url="/admin/teams?error=Cannot+delete+a+team+with+drivers+on+its+roster.+Remove+its+drivers+first.",
            status_code=303,
        )

    db.delete(team)
    db.commit()
    return RedirectResponse(url="/admin/teams", status_code=303)


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------

@router.get("/drivers")
def list_drivers(
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
    error: Optional[str] = None,
):
    season = get_current_season(db)
    drivers = (
        db.query(Driver)
        .filter_by(season_id=season.id)
        .join(Team)
        .order_by(Team.name, Driver.name)
        .all()
    )
    teams = db.query(Team).filter_by(season_id=season.id).order_by(Team.name).all()
    return templates.TemplateResponse(
        request,
        "admin/drivers.html",
        {"current_user": current_user, "season": season, "drivers": drivers, "teams": teams, "error": error},
    )


@router.post("/drivers")
def create_driver(
    name: str = Form(...),
    team_id: int = Form(...),
    is_reserve: Optional[str] = Form(None),
    active: Optional[str] = Form(None),
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    db.add(
        Driver(
            season_id=team.season_id,
            team_id=team_id,
            name=name,
            is_reserve=bool(is_reserve),
            active=bool(active) if active is not None else True,
        )
    )
    db.commit()
    return RedirectResponse(url="/admin/drivers", status_code=303)


@router.post("/drivers/{driver_id}")
def update_driver(
    driver_id: int,
    name: str = Form(...),
    is_reserve: Optional[str] = Form(None),
    active: Optional[str] = Form(None),
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver.name = name
    driver.is_reserve = bool(is_reserve)
    driver.active = bool(active)
    db.commit()
    return RedirectResponse(url="/admin/drivers", status_code=303)


@router.post("/drivers/{driver_id}/delete")
def delete_driver(
    driver_id: int,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")

    has_dependents = any(
        [
            db.query(Prediction).filter_by(driver_id=driver_id).first() is not None,
            db.query(Result).filter_by(driver_id=driver_id).first() is not None,
            db.query(BonusPrediction).filter_by(driver_id=driver_id).first() is not None,
            db.query(BonusResult).filter_by(driver_id=driver_id).first() is not None,
            db.query(EventEntry).filter_by(driver_id=driver_id).first() is not None,
            db.query(EventEntry).filter_by(substituted_for_driver_id=driver_id).first() is not None,
        ]
    )
    if has_dependents:
        return RedirectResponse(
            url="/admin/drivers?error=Cannot+delete+a+driver+with+predictions%2C+results%2C+or+event+entries+on+record.",
            status_code=303,
        )

    db.delete(driver)
    db.commit()
    return RedirectResponse(url="/admin/drivers", status_code=303)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@router.get("/events")
def list_events(
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
    error: Optional[str] = None,
):
    season = get_current_season(db)
    events = db.query(Event).filter_by(season_id=season.id).order_by(Event.round_number).all()
    return templates.TemplateResponse(
        request,
        "admin/events.html",
        {"current_user": current_user, "season": season, "events": events, "error": error},
    )


@router.post("/events")
def create_event(
    name: str = Form(...),
    round_number: Optional[int] = Form(None),
    has_sprint: Optional[str] = Form(None),
    grid_size: int = Form(...),
    qualifying_start_time: str = Form(...),
    race_start_time: str = Form(...),
    sprint_start_time: Optional[str] = Form(None),
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    season = get_current_season(db)
    is_sprint = bool(has_sprint)
    resolved_round_number = round_number if round_number is not None else season.next_round_number
    event = Event(
        season_id=season.id,
        round_number=resolved_round_number,
        name=name,
        has_sprint=is_sprint,
        grid_size=grid_size,
        qualifying_start_time=datetime.fromisoformat(qualifying_start_time),
        race_start_time=datetime.fromisoformat(race_start_time),
        sprint_start_time=datetime.fromisoformat(sprint_start_time) if (is_sprint and sprint_start_time) else None,
    )
    season.next_round_number = resolved_round_number + 1
    db.add(event)
    db.flush()

    # Default every active, non-reserve driver on the season roster into the
    # entry list so the admin doesn't have to manually check each one in —
    # substitutions/no-shows can still be adjusted from the entries page.
    default_drivers = db.query(Driver).filter_by(season_id=season.id, is_reserve=False, active=True).all()
    for driver in default_drivers:
        db.add(EventEntry(event_id=event.id, driver_id=driver.id, is_substitute=False))

    db.commit()
    return RedirectResponse(url="/admin/events", status_code=303)


@router.post("/season/next-round-number")
def set_next_round_number(
    next_round_number: int = Form(...),
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    season = get_current_season(db)
    season.next_round_number = next_round_number
    db.commit()
    return RedirectResponse(url="/admin/events", status_code=303)


@router.post("/events/{event_id}/delete")
def delete_event(
    event_id: int,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    has_dependents = any(
        [
            db.query(Prediction).filter_by(event_id=event_id).first() is not None,
            db.query(Result).filter_by(event_id=event_id).first() is not None,
            db.query(BonusPrediction).filter_by(event_id=event_id).first() is not None,
            db.query(BonusResult).filter_by(event_id=event_id).first() is not None,
            db.query(PointsLog).filter_by(event_id=event_id).first() is not None,
        ]
    )
    if has_dependents:
        return RedirectResponse(
            url="/admin/events?error=Cannot+delete+an+event+with+predictions%2C+results%2C+or+points+on+record.",
            status_code=303,
        )

    db.delete(event)
    db.commit()
    return RedirectResponse(url="/admin/events", status_code=303)


@router.get("/events/{event_id}/entries")
def event_entries(
    event_id: int,
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    season_drivers = (
        db.query(Driver)
        .filter_by(season_id=event.season_id)
        .join(Team)
        .order_by(Team.name, Driver.name)
        .all()
    )
    entries_by_driver = {e.driver_id: e for e in event.entries}
    primary_drivers = [d for d in season_drivers if not d.is_reserve]

    return templates.TemplateResponse(
        request,
        "admin/event_entries.html",
        {
            "current_user": current_user,
            "event": event,
            "season_drivers": season_drivers,
            "entries_by_driver": entries_by_driver,
            "primary_drivers": primary_drivers,
        },
    )


@router.post("/events/{event_id}/entries")
async def update_event_entries(
    event_id: int,
    request: Request,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    form = await request.form()
    season_drivers = db.query(Driver).filter_by(season_id=event.season_id).all()

    db.query(EventEntry).filter_by(event_id=event_id).delete()

    for driver in season_drivers:
        if not form.get(f"entered_{driver.id}"):
            continue
        is_substitute = bool(form.get(f"sub_{driver.id}"))
        substituted_for_raw = form.get(f"subfor_{driver.id}")
        substituted_for_id = int(substituted_for_raw) if is_substitute and substituted_for_raw else None
        db.add(
            EventEntry(
                event_id=event_id,
                driver_id=driver.id,
                is_substitute=is_substitute,
                substituted_for_driver_id=substituted_for_id,
            )
        )

    db.commit()
    return RedirectResponse(url=f"/admin/events/{event_id}/entries", status_code=303)


# ---------------------------------------------------------------------------
# Season reset
# ---------------------------------------------------------------------------

@router.get("/season/reset")
def season_reset_form(
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    season = get_current_season(db)
    event_count = db.query(Event).filter_by(season_id=season.id).count()
    return templates.TemplateResponse(
        request,
        "admin/season_reset.html",
        {"current_user": current_user, "season": season, "event_count": event_count},
    )


@router.post("/season/reset")
def reset_season(
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    """Wipes all race data (events, entries, predictions, results, bonuses, points)
    for the current season but keeps its teams and drivers as-is."""
    season = get_current_season(db)
    event_ids = [e.id for e in db.query(Event).filter_by(season_id=season.id).all()]

    if event_ids:
        db.query(PointsLog).filter(PointsLog.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(BonusResult).filter(BonusResult.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(BonusPrediction).filter(BonusPrediction.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Result).filter(Result.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Prediction).filter(Prediction.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(EventEntry).filter(EventEntry.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Event).filter(Event.id.in_(event_ids)).delete(synchronize_session=False)

    season.next_round_number = 1
    db.commit()
    return RedirectResponse(url="/admin/events", status_code=303)


# ---------------------------------------------------------------------------
# Results entry
# ---------------------------------------------------------------------------

def get_event_or_404(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/events/{event_id}/results")
def results_hub(
    event_id: int,
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    sessions = ["qualifying", "race"]
    if event.has_sprint:
        sessions.insert(1, "sprint")

    for s in sessions:
        backfill_missing_predictions(db, event, s)

    session_info = [
        {
            "session_type": s,
            "label": SESSION_LABELS[s],
            "entered": db.query(Result).filter_by(event_id=event_id, session_type=s).first() is not None,
        }
        for s in sessions
    ]
    bonuses_entered = db.query(BonusResult).filter_by(event_id=event_id).first() is not None

    return templates.TemplateResponse(
        request,
        "admin/results_hub.html",
        {
            "current_user": current_user,
            "event": event,
            "sessions": session_info,
            "bonuses_entered": bonuses_entered,
        },
    )


@router.get("/events/{event_id}/results/bonuses")
def bonus_results_form(
    event_id: int,
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    entered_drivers = get_entered_drivers(db, event)
    existing = db.query(BonusResult).filter_by(event_id=event_id).all()
    existing_by_type = {b.bonus_type.value: b for b in existing}

    return templates.TemplateResponse(
        request,
        "admin/results_bonus_form.html",
        {
            "current_user": current_user,
            "event": event,
            "entered_drivers": entered_drivers,
            "bonus_fields": BONUS_FIELDS,
            "existing_by_type": existing_by_type,
            "error": None,
        },
    )


@router.post("/events/{event_id}/results/bonuses")
async def submit_bonus_results(
    event_id: int,
    request: Request,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    entered_drivers = get_entered_drivers(db, event)
    entered_ids = {d.id for d in entered_drivers}

    form = await request.form()
    error = None
    parsed = {}

    for bonus_type, _label, kind in BONUS_FIELDS:
        raw = form.get(bonus_type)
        if not raw:
            error = f"'{bonus_type}' must be answered."
            break
        if kind == "driver":
            driver_id = int(raw)
            if driver_id not in entered_ids:
                error = "Selected driver is not entered for this event."
                break
            parsed[bonus_type] = {"driver_id": driver_id}
        elif kind == "bool":
            parsed[bonus_type] = {"bool_value": raw == "true"}
        elif kind == "int":
            try:
                parsed[bonus_type] = {"int_value": int(raw)}
            except ValueError:
                error = f"'{bonus_type}' must be a number."
                break

    if error is not None:
        existing = db.query(BonusResult).filter_by(event_id=event_id).all()
        existing_by_type = {b.bonus_type.value: b for b in existing}
        return templates.TemplateResponse(
            request,
            "admin/results_bonus_form.html",
            {
                "current_user": _,
                "event": event,
                "entered_drivers": entered_drivers,
                "bonus_fields": BONUS_FIELDS,
                "existing_by_type": existing_by_type,
                "error": error,
            },
            status_code=400,
        )

    db.query(BonusResult).filter_by(event_id=event_id).delete()
    for bonus_type, values in parsed.items():
        db.add(
            BonusResult(
                event_id=event_id,
                bonus_type=BonusType(bonus_type),
                driver_id=values.get("driver_id"),
                bool_value=values.get("bool_value"),
                int_value=values.get("int_value"),
            )
        )
    db.commit()

    backfill_missing_predictions(db, event, "race")
    recompute_session_points(db, event, "race")

    return RedirectResponse(url=f"/admin/events/{event_id}/results", status_code=303)


@router.get("/events/{event_id}/results/{session_type}/missing-bets")
def session_missing_bets(
    event_id: int,
    session_type: str,
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    if session_type not in SESSION_LABELS:
        raise HTTPException(status_code=404, detail="Unknown session type")
    if session_type == "sprint" and not event.has_sprint:
        raise HTTPException(status_code=404, detail="This event has no sprint session")

    users = db.query(User).order_by(User.username).all()
    auto_generated_user_ids = {
        row[0]
        for row in db.query(Prediction.user_id)
        .filter_by(event_id=event_id, session_type=session_type, is_auto_generated=True)
        .distinct()
        .all()
    }
    submitted_user_ids = {
        user.id
        for user in users
        if user.id not in auto_generated_user_ids
        and has_any_submission(db, user.id, event_id, session_type)
    }

    return templates.TemplateResponse(
        request,
        "admin/session_missing_bets.html",
        {
            "current_user": current_user,
            "event": event,
            "session_type": session_type,
            "label": SESSION_LABELS[session_type],
            "locked": event.is_locked(session_type),
            "users": users,
            "submitted_user_ids": submitted_user_ids,
            "auto_generated_user_ids": auto_generated_user_ids,
            "missing_users": [
                u for u in users
                if u.id not in submitted_user_ids and u.id not in auto_generated_user_ids
            ],
        },
    )


@router.post("/events/{event_id}/results/{session_type}/random-bets/bulk")
def bulk_random_bets(
    event_id: int,
    session_type: str,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    if session_type not in SESSION_LABELS:
        raise HTTPException(status_code=404, detail="Unknown session type")
    if session_type == "sprint" and not event.has_sprint:
        raise HTTPException(status_code=404, detail="This event has no sprint session")

    backfill_missing_predictions(db, event, session_type, include_admins=True)
    recompute_session_points(db, event, session_type)

    return RedirectResponse(
        url=f"/admin/events/{event_id}/results/{session_type}/missing-bets", status_code=303
    )


@router.post("/events/{event_id}/results/{session_type}/random-bets/{user_id}")
def single_random_bet(
    event_id: int,
    session_type: str,
    user_id: int,
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    if session_type not in SESSION_LABELS:
        raise HTTPException(status_code=404, detail="Unknown session type")
    if session_type == "sprint" and not event.has_sprint:
        raise HTTPException(status_code=404, detail="This event has no sprint session")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not has_any_submission(db, user_id, event_id, session_type):
        generate_random_bet_for_user(db, event, session_type, user_id)
        db.commit()
        recompute_session_points(db, event, session_type)

    return RedirectResponse(
        url=f"/admin/events/{event_id}/results/{session_type}/missing-bets", status_code=303
    )


@router.get("/events/{event_id}/results/{session_type}")
def session_results_form(
    event_id: int,
    session_type: str,
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    if session_type not in SESSION_LABELS:
        raise HTTPException(status_code=404, detail="Unknown session type")
    if session_type == "sprint" and not event.has_sprint:
        raise HTTPException(status_code=404, detail="This event has no sprint session")

    entered_drivers = get_entered_drivers(db, event)
    existing_results = db.query(Result).filter_by(event_id=event_id, session_type=session_type).all()
    existing_by_driver = {r.driver_id: r for r in existing_results}

    return templates.TemplateResponse(
        request,
        "admin/results_race_form.html" if session_type == "race" else "admin/results_position_form.html",
        {
            "current_user": current_user,
            "event": event,
            "session_type": session_type,
            "label": SESSION_LABELS[session_type],
            "entered_drivers": entered_drivers,
            "existing_by_driver": existing_by_driver,
            "error": None,
        },
    )


@router.post("/events/{event_id}/results/{session_type}")
async def submit_session_results(
    event_id: int,
    session_type: str,
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    if session_type not in SESSION_LABELS:
        raise HTTPException(status_code=404, detail="Unknown session type")
    if session_type == "sprint" and not event.has_sprint:
        raise HTTPException(status_code=404, detail="This event has no sprint session")

    entered_drivers = get_entered_drivers(db, event)
    entered_ids = {d.id for d in entered_drivers}

    form = await request.form()
    error = None

    if session_type == "race":
        finisher_positions = []  # (position, driver_id)
        dnf_list = []  # {"driver_id":..., "retired_at":...}

        for driver in entered_drivers:
            is_dnf = bool(form.get(f"dnf_{driver.id}"))
            if is_dnf:
                retired_raw = form.get(f"retired_at_{driver.id}")
                if not retired_raw:
                    error = f"Retirement order missing for {driver.name}."
                    break
                dnf_list.append({"driver_id": driver.id, "retired_at": int(retired_raw)})
            else:
                position_raw = form.get(f"position_{driver.id}")
                if not position_raw:
                    error = f"Finishing position missing for {driver.name}."
                    break
                finisher_positions.append((int(position_raw), driver.id))

        if error is None and len({p for p, _ in finisher_positions}) != len(finisher_positions):
            error = "Finishing positions must be unique among classified drivers."

        if error is None:
            finisher_positions.sort(key=lambda pair: pair[0])
            finisher_ids = [driver_id for _, driver_id in finisher_positions]
            classification = order_dnf_drivers(finisher_ids, dnf_list)
        else:
            classification = None
    else:
        classification = []
        seen_positions = set()
        for driver in entered_drivers:
            position_raw = form.get(f"position_{driver.id}")
            if not position_raw:
                error = f"Finishing position missing for {driver.name}."
                break
            position = int(position_raw)
            if position in seen_positions:
                error = "Finishing positions must be unique."
                break
            seen_positions.add(position)
            classification.append({"position": position, "driver_id": driver.id, "dnf": False})

    if error is not None or classification is None:
        existing_results = db.query(Result).filter_by(event_id=event_id, session_type=session_type).all()
        existing_by_driver = {r.driver_id: r for r in existing_results}
        return templates.TemplateResponse(
            request,
            "admin/results_race_form.html" if session_type == "race" else "admin/results_position_form.html",
            {
                "current_user": current_user,
                "event": event,
                "session_type": session_type,
                "label": SESSION_LABELS[session_type],
                "entered_drivers": entered_drivers,
                "existing_by_driver": existing_by_driver,
                "error": error or "Could not record results.",
            },
            status_code=400,
        )

    db.query(Result).filter_by(event_id=event_id, session_type=session_type).delete()
    for entry in classification:
        db.add(
            Result(
                event_id=event_id,
                session_type=SessionType(session_type),
                actual_position=entry["position"],
                driver_id=entry["driver_id"],
                dnf=entry["dnf"],
            )
        )
    db.commit()

    backfill_missing_predictions(db, event, session_type)
    recompute_session_points(db, event, session_type)

    return RedirectResponse(url=f"/admin/events/{event_id}/results", status_code=303)
