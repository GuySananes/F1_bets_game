"""Wires the pure scoring engine (app/scoring.py) to the DB: reads
predictions/results, scores them, and upserts points_log. Unlike
app/scoring.py this module does touch the DB — that's expected here.
"""

from typing import List

from sqlalchemy.orm import Session

from app.models import BonusPrediction, BonusResult, Event, PointsLog, Prediction, Result
from app.scoring import score_bonus_predictions, score_position_predictions


def _distinct_user_ids(db: Session, event_id: int, session_type: str) -> List[int]:
    user_ids = {
        row[0]
        for row in db.query(Prediction.user_id)
        .filter_by(event_id=event_id, session_type=session_type)
        .distinct()
        .all()
    }
    if session_type == "race":
        user_ids |= {
            row[0]
            for row in db.query(BonusPrediction.user_id).filter_by(event_id=event_id).distinct().all()
        }
    return list(user_ids)


def recompute_session_points(db: Session, event: Event, session_type: str) -> None:
    """Re-score every user's predictions for one session of an event and
    upsert points_log. Safe to call repeatedly (e.g. once after position
    results are entered, again after bonus results are entered for race)."""
    results = db.query(Result).filter_by(event_id=event.id, session_type=session_type).all()
    if not results:
        return  # nothing to score yet

    results_data = [{"position": r.actual_position, "driver_id": r.driver_id} for r in results]

    bonus_results_data = []
    if session_type == "race":
        bonus_results = db.query(BonusResult).filter_by(event_id=event.id).all()
        bonus_results_data = [
            {
                "bonus_type": br.bonus_type.value,
                "driver_id": br.driver_id,
                "bool_value": br.bool_value,
                "int_value": br.int_value,
            }
            for br in bonus_results
        ]

    for user_id in _distinct_user_ids(db, event.id, session_type):
        predictions = (
            db.query(Prediction)
            .filter_by(user_id=user_id, event_id=event.id, session_type=session_type)
            .all()
        )
        predictions_data = [{"position": p.predicted_position, "driver_id": p.driver_id} for p in predictions]
        position_score = score_position_predictions(predictions_data, results_data)

        if session_type == "race":
            bonus_predictions = (
                db.query(BonusPrediction).filter_by(user_id=user_id, event_id=event.id).all()
            )
            bonus_predictions_data = [
                {
                    "bonus_type": bp.bonus_type.value,
                    "driver_id": bp.driver_id,
                    "bool_value": bp.bool_value,
                    "int_value": bp.int_value,
                }
                for bp in bonus_predictions
            ]
            bonus_score = score_bonus_predictions(bonus_predictions_data, bonus_results_data)
            total = position_score["total"] + bonus_score["total"]
            detail = {"position": position_score["breakdown"], "bonus": bonus_score["breakdown"]}
        else:
            total = position_score["total"]
            detail = {"position": position_score["breakdown"]}

        existing = (
            db.query(PointsLog)
            .filter_by(user_id=user_id, event_id=event.id, session_type=session_type)
            .first()
        )
        if existing:
            existing.points = total
            existing.detail = detail
        else:
            db.add(
                PointsLog(
                    user_id=user_id,
                    event_id=event.id,
                    session_type=session_type,
                    points=total,
                    detail=detail,
                )
            )
    db.commit()
