"""Generates a random prediction for a user who didn't submit one in time.

Not pure like app/scoring.py (it needs a DB session to read the entered-driver
roster and existing submissions), but the actual randomization logic is kept
in small standalone functions so it can be unit tested without HTTP/admin
plumbing.
"""

import random
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import BonusPrediction, BonusType, Driver, Event, Prediction, SessionType, User
from app.prediction_constants import BONUS_FIELDS
from app.routers.predictions import get_entered_drivers, position_count_for


def generate_random_positions(
    entered_drivers: List[Driver], position_count: int, rng: random.Random
) -> dict:
    """Return {position: driver_id} covering positions 1..position_count,
    each with a distinct randomly-chosen entered driver."""
    shuffled = entered_drivers[:]
    rng.shuffle(shuffled)
    return {i + 1: shuffled[i].id for i in range(position_count)}


def generate_random_bonus_values(entered_drivers: List[Driver], rng: random.Random) -> dict:
    """Return {bonus_type: {driver_id|bool_value|int_value: ...}} with one
    randomly-chosen answer per BONUS_FIELDS entry."""
    entered_ids = [d.id for d in entered_drivers]
    values: dict = {}
    for bonus_type, _label, kind in BONUS_FIELDS:
        if kind == "driver":
            values[bonus_type] = {"driver_id": rng.choice(entered_ids)}
        elif kind == "bool":
            values[bonus_type] = {"bool_value": rng.choice([True, False])}
        elif kind == "int":
            values[bonus_type] = {"int_value": rng.randint(0, len(entered_drivers))}
    return values


def has_any_submission(db: Session, user_id: int, event_id: int, session_type: str) -> bool:
    has_positions = (
        db.query(Prediction.id)
        .filter_by(user_id=user_id, event_id=event_id, session_type=SessionType(session_type))
        .first()
        is not None
    )
    if has_positions:
        return True
    if session_type == "race":
        return (
            db.query(BonusPrediction.id).filter_by(user_id=user_id, event_id=event_id).first()
            is not None
        )
    return False


def users_missing_submission(
    db: Session, event: Event, session_type: str, include_admins: bool = False
) -> List[User]:
    query = db.query(User)
    if not include_admins:
        query = query.filter_by(is_admin=False)
    return [
        user
        for user in query.all()
        if not has_any_submission(db, user.id, event.id, session_type)
    ]


def generate_random_bet_for_user(
    db: Session,
    event: Event,
    session_type: str,
    user_id: int,
    rng: Optional[random.Random] = None,
) -> None:
    """Inserts fresh Prediction rows (and, for race, BonusPrediction rows)
    marked as auto-generated. Does not commit and does not check lock state
    — the caller is responsible for both."""
    rng = rng or random.Random()

    entered_drivers = get_entered_drivers(db, event)
    position_count = position_count_for(event, session_type, len(entered_drivers))

    db.query(Prediction).filter_by(
        user_id=user_id, event_id=event.id, session_type=SessionType(session_type)
    ).delete()
    positions = generate_random_positions(entered_drivers, position_count, rng)
    for position, driver_id in positions.items():
        db.add(
            Prediction(
                user_id=user_id,
                event_id=event.id,
                session_type=SessionType(session_type),
                predicted_position=position,
                driver_id=driver_id,
                is_auto_generated=True,
            )
        )

    if session_type == "race":
        db.query(BonusPrediction).filter_by(user_id=user_id, event_id=event.id).delete()
        bonus_values = generate_random_bonus_values(entered_drivers, rng)
        for bonus_type, values in bonus_values.items():
            db.add(
                BonusPrediction(
                    user_id=user_id,
                    event_id=event.id,
                    bonus_type=BonusType(bonus_type),
                    driver_id=values.get("driver_id"),
                    bool_value=values.get("bool_value"),
                    int_value=values.get("int_value"),
                    is_auto_generated=True,
                )
            )


def backfill_missing_predictions(
    db: Session,
    event: Event,
    session_type: str,
    include_admins: bool = False,
    rng: Optional[random.Random] = None,
) -> List[int]:
    """For a locked session, generates a random bet for every user who has
    no submission yet. No-ops (and returns []) if the session isn't locked."""
    if not event.is_locked(session_type):
        return []

    rng = rng or random.Random()
    missing_users = users_missing_submission(db, event, session_type, include_admins=include_admins)
    for user in missing_users:
        generate_random_bet_for_user(db, event, session_type, user.id, rng=rng)
    if missing_users:
        db.commit()
    return [user.id for user in missing_users]
