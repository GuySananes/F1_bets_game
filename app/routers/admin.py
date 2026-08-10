from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import get_db
from app.dependencies import require_admin, require_admin_page
from app.models import BonusResult, BonusType, Driver, Event, EventEntry, Result, Season, SessionType, Team, User
from app.points import recompute_session_points
from app.prediction_constants import BONUS_FIELDS, SESSION_LABELS
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
):
    season = get_current_season(db)
    teams = db.query(Team).filter_by(season_id=season.id).order_by(Team.name).all()
    return templates.TemplateResponse(
        request, "admin/teams.html", {"current_user": current_user, "season": season, "teams": teams}
    )


@router.post("/teams/{team_id}")
def update_team(
    team_id: int,
    name: str = Form(...),
    _: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    team.name = name
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
):
    season = get_current_season(db)
    drivers = (
        db.query(Driver)
        .filter_by(season_id=season.id)
        .join(Team)
        .order_by(Team.name, Driver.name)
        .all()
    )
    return templates.TemplateResponse(
        request, "admin/drivers.html", {"current_user": current_user, "season": season, "drivers": drivers}
    )


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


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@router.get("/events")
def list_events(
    request: Request,
    current_user: User = Depends(require_admin_page),
    db: Session = Depends(get_db),
):
    season = get_current_season(db)
    events = db.query(Event).filter_by(season_id=season.id).order_by(Event.round_number).all()
    return templates.TemplateResponse(
        request, "admin/events.html", {"current_user": current_user, "season": season, "events": events}
    )


@router.post("/events")
def create_event(
    round_number: int = Form(...),
    name: str = Form(...),
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
    event = Event(
        season_id=season.id,
        round_number=round_number,
        name=name,
        has_sprint=is_sprint,
        grid_size=grid_size,
        qualifying_start_time=datetime.fromisoformat(qualifying_start_time),
        race_start_time=datetime.fromisoformat(race_start_time),
        sprint_start_time=datetime.fromisoformat(sprint_start_time) if (is_sprint and sprint_start_time) else None,
    )
    db.add(event)
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

    recompute_session_points(db, event, "race")

    return RedirectResponse(url=f"/admin/events/{event_id}/results", status_code=303)


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

    recompute_session_points(db, event, session_type)

    return RedirectResponse(url=f"/admin/events/{event_id}/results", status_code=303)
