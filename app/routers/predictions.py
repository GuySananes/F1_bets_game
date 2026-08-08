from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_login_page
from app.models import (
    BonusPrediction,
    BonusType,
    Driver,
    Event,
    PointsLog,
    Prediction,
    Season,
    SessionType,
    Team,
    User,
)
from app.prediction_constants import BONUS_FIELDS, SESSION_LABELS
from app.templating import templates

router = APIRouter(prefix="/predict", tags=["predictions"])


def get_event_or_404(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def get_entered_drivers(db: Session, event: Event) -> List[Driver]:
    driver_ids = [entry.driver_id for entry in event.entries]
    if not driver_ids:
        return []
    return (
        db.query(Driver)
        .filter(Driver.id.in_(driver_ids))
        .join(Team)
        .order_by(Team.name, Driver.name)
        .all()
    )


def position_count_for(event: Event, session_type: str, entered_count: int) -> int:
    if session_type == "qualifying":
        # spec rule is always "top 10" — capped at how many cars are actually
        # entered so small fixtures (fewer than 10 cars) don't ask for the impossible
        return min(10, entered_count)
    return event.grid_size


def validate_session_type(event: Event, session_type: str) -> None:
    if session_type not in SESSION_LABELS:
        raise HTTPException(status_code=404, detail="Unknown session type")
    if session_type == "sprint" and not event.has_sprint:
        raise HTTPException(status_code=404, detail="This event has no sprint session")


@router.get("")
def list_events(
    request: Request,
    current_user: User = Depends(require_login_page),
    db: Session = Depends(get_db),
):
    season = db.query(Season).order_by(Season.year.desc()).first()
    events = (
        db.query(Event).filter_by(season_id=season.id).order_by(Event.round_number).all()
        if season
        else []
    )
    return templates.TemplateResponse(
        request, "predict/events_list.html", {"current_user": current_user, "events": events}
    )


@router.get("/{event_id}")
def overview(
    event_id: int,
    request: Request,
    current_user: User = Depends(require_login_page),
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
            "start_time": event.start_time_for(s),
            "locked": event.is_locked(s),
        }
        for s in sessions
    ]

    my_logs = db.query(PointsLog).filter_by(user_id=current_user.id, event_id=event_id).all()
    my_points = sum(log.points for log in my_logs) if my_logs else None

    return templates.TemplateResponse(
        request,
        "predict/overview.html",
        {
            "current_user": current_user,
            "event": event,
            "sessions": session_info,
            "my_points": my_points,
        },
    )


def get_existing_bonus_by_type(db: Session, current_user: User, event_id: int) -> dict:
    existing = (
        db.query(BonusPrediction).filter_by(user_id=current_user.id, event_id=event_id).all()
    )
    return {b.bonus_type.value if hasattr(b.bonus_type, "value") else b.bonus_type: b for b in existing}


def parse_bonus_fields(form, entered_ids: set) -> tuple[dict, Optional[str]]:
    parsed = {}
    for bonus_type, _label, kind in BONUS_FIELDS:
        raw = form.get(bonus_type)
        if not raw:
            return parsed, f"'{bonus_type}' must be answered."
        if kind == "driver":
            driver_id = int(raw)
            if driver_id not in entered_ids:
                return parsed, "Selected driver is not entered for this event."
            parsed[bonus_type] = {"driver_id": driver_id}
        elif kind == "bool":
            parsed[bonus_type] = {"bool_value": raw == "true"}
        elif kind == "int":
            try:
                parsed[bonus_type] = {"int_value": int(raw)}
            except ValueError:
                return parsed, f"'{bonus_type}' must be a number."
    return parsed, None


@router.get("/{event_id}/{session_type}")
def session_form(
    event_id: int,
    session_type: str,
    request: Request,
    current_user: User = Depends(require_login_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    validate_session_type(event, session_type)

    entered_drivers = get_entered_drivers(db, event)
    position_count = position_count_for(event, session_type, len(entered_drivers))

    existing = (
        db.query(Prediction)
        .filter_by(user_id=current_user.id, event_id=event_id, session_type=SessionType(session_type))
        .all()
    )
    selected_by_position = {p.predicted_position: p.driver_id for p in existing}

    show_bonuses = session_type == "race"
    context = {
        "current_user": current_user,
        "event": event,
        "session_type": session_type,
        "label": SESSION_LABELS[session_type],
        "locked": event.is_locked(session_type),
        "positions": list(range(1, position_count + 1)),
        "entered_drivers": entered_drivers,
        "selected_by_position": selected_by_position,
        "error": None,
        "show_bonuses": show_bonuses,
    }
    if show_bonuses:
        context["bonus_fields"] = BONUS_FIELDS
        context["existing_bonus_by_type"] = get_existing_bonus_by_type(db, current_user, event_id)

    return templates.TemplateResponse(request, "predict/session_form.html", context)


@router.post("/{event_id}/{session_type}")
async def submit_session(
    event_id: int,
    session_type: str,
    request: Request,
    current_user: User = Depends(require_login_page),
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    validate_session_type(event, session_type)

    if event.is_locked(session_type):
        raise HTTPException(status_code=403, detail="Predictions for this session are locked")

    show_bonuses = session_type == "race"
    entered_drivers = get_entered_drivers(db, event)
    entered_ids = {d.id for d in entered_drivers}
    position_count = position_count_for(event, session_type, len(entered_drivers))

    form = await request.form()
    selected_by_position = {}
    error = None

    for position in range(1, position_count + 1):
        raw = form.get(f"position_{position}")
        if not raw:
            error = "Every position must have a driver selected."
            break
        driver_id = int(raw)
        if driver_id not in entered_ids:
            error = "Selected driver is not entered for this event."
            break
        selected_by_position[position] = driver_id

    if error is None and len(set(selected_by_position.values())) != len(selected_by_position):
        error = "Each driver can only be picked for one position."

    parsed_bonuses: dict = {}
    if error is None and show_bonuses:
        parsed_bonuses, error = parse_bonus_fields(form, entered_ids)

    if error is not None:
        context = {
            "current_user": current_user,
            "event": event,
            "session_type": session_type,
            "label": SESSION_LABELS[session_type],
            "locked": False,
            "positions": list(range(1, position_count + 1)),
            "entered_drivers": entered_drivers,
            "selected_by_position": selected_by_position,
            "error": error,
            "show_bonuses": show_bonuses,
        }
        if show_bonuses:
            context["bonus_fields"] = BONUS_FIELDS
            context["existing_bonus_by_type"] = get_existing_bonus_by_type(db, current_user, event_id)
        return templates.TemplateResponse(
            request, "predict/session_form.html", context, status_code=400,
        )

    db.query(Prediction).filter_by(
        user_id=current_user.id, event_id=event_id, session_type=SessionType(session_type)
    ).delete()
    for position, driver_id in selected_by_position.items():
        db.add(
            Prediction(
                user_id=current_user.id,
                event_id=event_id,
                session_type=SessionType(session_type),
                predicted_position=position,
                driver_id=driver_id,
            )
        )

    if show_bonuses:
        db.query(BonusPrediction).filter_by(user_id=current_user.id, event_id=event_id).delete()
        for bonus_type, values in parsed_bonuses.items():
            db.add(
                BonusPrediction(
                    user_id=current_user.id,
                    event_id=event_id,
                    bonus_type=BonusType(bonus_type),
                    driver_id=values.get("driver_id"),
                    bool_value=values.get("bool_value"),
                    int_value=values.get("int_value"),
                )
            )

    db.commit()

    return RedirectResponse(url=f"/predict/{event_id}", status_code=303)
