import random
from datetime import datetime, timedelta

from app.models import BonusPrediction, Driver, Event, EventEntry, Prediction, Season, SessionType, Team, User
from app.random_bet import (
    backfill_missing_predictions,
    generate_random_bet_for_user,
    generate_random_bonus_values,
    generate_random_positions,
    has_any_submission,
)
from app.prediction_constants import BONUS_FIELDS

PAST = datetime.utcnow() - timedelta(days=1)
FUTURE = datetime.utcnow() + timedelta(days=30)


class FakeDriver:
    def __init__(self, id):
        self.id = id


def test_generate_random_positions_covers_all_positions_exactly_once():
    drivers = [FakeDriver(i) for i in range(1, 6)]
    positions = generate_random_positions(drivers, 3, random.Random(42))

    assert set(positions.keys()) == {1, 2, 3}
    assert len(set(positions.values())) == 3
    assert all(driver_id in {1, 2, 3, 4, 5} for driver_id in positions.values())


def test_generate_random_bonus_values_answers_every_bonus_field():
    drivers = [FakeDriver(i) for i in range(1, 4)]
    values = generate_random_bonus_values(drivers, random.Random(1))

    assert set(values.keys()) == {bt for bt, _label, _kind in BONUS_FIELDS}
    for bonus_type, _label, kind in BONUS_FIELDS:
        entry = values[bonus_type]
        if kind == "driver":
            assert entry["driver_id"] in {1, 2, 3}
        elif kind == "bool":
            assert isinstance(entry["bool_value"], bool)
        elif kind == "int":
            assert isinstance(entry["int_value"], int)
            assert 0 <= entry["int_value"] <= 3


def _seed_event(db, has_sprint=False, start_time=PAST):
    season = Season(year=2100, name="Random Bet Season", default_grid_size=3)
    db.add(season)
    db.flush()
    team = Team(season_id=season.id, name="Solo Team")
    db.add(team)
    db.flush()

    drivers = {}
    for name in ("A", "B", "C"):
        driver = Driver(season_id=season.id, team_id=team.id, name=name, is_reserve=False, active=True)
        db.add(driver)
        db.flush()
        drivers[name] = driver.id

    event = Event(
        season_id=season.id,
        round_number=1,
        name="Random Bet GP",
        has_sprint=has_sprint,
        grid_size=3,
        qualifying_start_time=start_time,
        race_start_time=start_time,
        sprint_start_time=start_time if has_sprint else None,
    )
    db.add(event)
    db.flush()

    for driver_id in drivers.values():
        db.add(EventEntry(event_id=event.id, driver_id=driver_id, is_substitute=False))

    db.commit()
    return event, drivers


def _seed_user(db, username, is_admin=False):
    user = User(username=username, password_hash="x", is_admin=is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_generate_random_bet_for_user_creates_position_and_bonus_rows_for_race(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db)
        user = _seed_user(db, "alice")

        generate_random_bet_for_user(db, event, "race", user.id, rng=random.Random(7))
        db.commit()

        predictions = db.query(Prediction).filter_by(user_id=user.id, event_id=event.id, session_type=SessionType.race).all()
        bonuses = db.query(BonusPrediction).filter_by(user_id=user.id, event_id=event.id).all()

        assert len(predictions) == 3
        assert all(p.is_auto_generated for p in predictions)
        assert len(bonuses) == len(BONUS_FIELDS)
        assert all(b.is_auto_generated for b in bonuses)
    finally:
        db.close()


def test_generate_random_bet_for_user_qualifying_only_creates_positions_no_bonuses(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db)
        user = _seed_user(db, "alice")

        generate_random_bet_for_user(db, event, "qualifying", user.id, rng=random.Random(7))
        db.commit()

        predictions = db.query(Prediction).filter_by(user_id=user.id, event_id=event.id, session_type=SessionType.qualifying).all()
        bonuses = db.query(BonusPrediction).filter_by(user_id=user.id, event_id=event.id).all()

        assert len(predictions) == 3
        assert len(bonuses) == 0
    finally:
        db.close()


def test_backfill_missing_predictions_skips_users_with_existing_submission(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db)
        submitted_user = _seed_user(db, "alice")
        missing_user = _seed_user(db, "bob")

        db.add(
            Prediction(
                user_id=submitted_user.id, event_id=event.id, session_type=SessionType.qualifying,
                predicted_position=1, driver_id=drivers["A"],
            )
        )
        db.commit()

        backfilled = backfill_missing_predictions(db, event, "qualifying")

        assert backfilled == [missing_user.id]
        submitted_rows = db.query(Prediction).filter_by(user_id=submitted_user.id, event_id=event.id, session_type=SessionType.qualifying).all()
        assert len(submitted_rows) == 1
        assert submitted_rows[0].is_auto_generated is False

        missing_rows = db.query(Prediction).filter_by(user_id=missing_user.id, event_id=event.id, session_type=SessionType.qualifying).all()
        assert len(missing_rows) == 3
        assert all(p.is_auto_generated for p in missing_rows)
    finally:
        db.close()


def test_backfill_missing_predictions_noop_before_lock(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db, start_time=FUTURE)
        _seed_user(db, "alice")

        backfilled = backfill_missing_predictions(db, event, "qualifying")

        assert backfilled == []
        assert db.query(Prediction).count() == 0
    finally:
        db.close()


def test_backfill_missing_predictions_excludes_admins_by_default(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db)
        admin = _seed_user(db, "root", is_admin=True)
        regular = _seed_user(db, "alice")

        backfilled = backfill_missing_predictions(db, event, "qualifying")

        assert admin.id not in backfilled
        assert regular.id in backfilled
    finally:
        db.close()


def test_backfill_missing_predictions_include_admins_flag(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db)
        admin = _seed_user(db, "root", is_admin=True)

        backfilled = backfill_missing_predictions(db, event, "qualifying", include_admins=True)

        assert admin.id in backfilled
    finally:
        db.close()


def test_backfill_only_fills_session_missing_not_other_sessions(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db)
        user = _seed_user(db, "alice")

        db.add(
            Prediction(
                user_id=user.id, event_id=event.id, session_type=SessionType.qualifying,
                predicted_position=1, driver_id=drivers["A"],
            )
        )
        db.commit()

        backfill_missing_predictions(db, event, "race")

        quali_rows = db.query(Prediction).filter_by(user_id=user.id, event_id=event.id, session_type=SessionType.qualifying).all()
        race_rows = db.query(Prediction).filter_by(user_id=user.id, event_id=event.id, session_type=SessionType.race).all()
        assert len(quali_rows) == 1
        assert quali_rows[0].is_auto_generated is False
        assert len(race_rows) == 3
        assert all(p.is_auto_generated for p in race_rows)
    finally:
        db.close()


def test_has_any_submission_checks_bonus_predictions_for_race(client):
    db = client.SessionLocal()
    try:
        event, drivers = _seed_event(db)
        user = _seed_user(db, "alice")

        assert has_any_submission(db, user.id, event.id, "race") is False

        db.add(
            BonusPrediction(
                user_id=user.id, event_id=event.id, bonus_type="mvp", driver_id=drivers["A"],
            )
        )
        db.commit()

        assert has_any_submission(db, user.id, event.id, "race") is True
    finally:
        db.close()
