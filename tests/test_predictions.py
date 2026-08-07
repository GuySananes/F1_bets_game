from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import BonusPrediction, Driver, Event, EventEntry, Prediction, Season, Team

FUTURE = datetime.utcnow() + timedelta(days=30)
PAST = datetime.utcnow() - timedelta(days=1)


def register_and_login(client, username="alice", password="pw12345"):
    response = client.post("/auth/register", data={"username": username, "password": password})
    assert response.status_code == 201
    return client


def seed_event(
    client,
    grid_size=6,
    has_sprint=True,
    qualifying_start=FUTURE,
    sprint_start=FUTURE,
    race_start=FUTURE,
    num_drivers=None,
):
    num_drivers = num_drivers if num_drivers is not None else grid_size
    db = client.SessionLocal()
    try:
        season = Season(year=2099, name="Test Season", default_grid_size=grid_size)
        db.add(season)
        db.flush()
        team = Team(season_id=season.id, name="Test Team")
        db.add(team)
        db.flush()

        driver_ids = []
        for i in range(num_drivers):
            driver = Driver(season_id=season.id, team_id=team.id, name=f"Driver {i}", is_reserve=False, active=True)
            db.add(driver)
            db.flush()
            driver_ids.append(driver.id)

        event = Event(
            season_id=season.id,
            round_number=1,
            name="Test GP",
            has_sprint=has_sprint,
            grid_size=grid_size,
            qualifying_start_time=qualifying_start,
            sprint_start_time=sprint_start if has_sprint else None,
            race_start_time=race_start,
        )
        db.add(event)
        db.flush()

        for driver_id in driver_ids:
            db.add(EventEntry(event_id=event.id, driver_id=driver_id, is_substitute=False))

        db.commit()
        return event.id, driver_ids
    finally:
        db.close()


def test_qualifying_form_lists_only_entered_drivers(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    response = client.get(f"/predict/{event_id}/qualifying")

    assert response.status_code == 200
    for driver_id in driver_ids:
        assert f'value="{driver_id}"' in response.text


def test_submit_valid_qualifying_predictions_persists(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    data = {f"position_{i + 1}": str(driver_ids[i]) for i in range(6)}
    response = client.post(f"/predict/{event_id}/qualifying", data=data)

    assert response.status_code == 200  # followed the redirect to the overview page
    db = client.SessionLocal()
    try:
        predictions = db.query(Prediction).filter_by(event_id=event_id, session_type="qualifying").all()
        assert len(predictions) == 6
        assert {p.driver_id for p in predictions} == set(driver_ids)
    finally:
        db.close()


def test_duplicate_driver_across_positions_rejected(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    data = {f"position_{i + 1}": str(driver_ids[0]) for i in range(6)}
    response = client.post(f"/predict/{event_id}/qualifying", data=data)

    assert response.status_code == 400
    assert "only be picked for one position" in response.text

    db = client.SessionLocal()
    try:
        assert db.query(Prediction).filter_by(event_id=event_id).count() == 0
    finally:
        db.close()


def test_incomplete_predictions_rejected(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    data = {f"position_{i + 1}": str(driver_ids[i]) for i in range(5)}  # missing position 6
    response = client.post(f"/predict/{event_id}/qualifying", data=data)

    assert response.status_code == 400
    assert "must have a driver selected" in response.text


def test_resubmitting_predictions_replaces_previous_ones(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    first = {f"position_{i + 1}": str(driver_ids[i]) for i in range(6)}
    client.post(f"/predict/{event_id}/qualifying", data=first)

    reversed_ids = list(reversed(driver_ids))
    second = {f"position_{i + 1}": str(reversed_ids[i]) for i in range(6)}
    client.post(f"/predict/{event_id}/qualifying", data=second)

    db = client.SessionLocal()
    try:
        predictions = db.query(Prediction).filter_by(event_id=event_id, session_type="qualifying").all()
        assert len(predictions) == 6
        by_position = {p.predicted_position: p.driver_id for p in predictions}
        assert by_position[1] == reversed_ids[0]
    finally:
        db.close()


def test_locked_session_rejects_submission(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6, qualifying_start=PAST)

    data = {f"position_{i + 1}": str(driver_ids[i]) for i in range(6)}
    response = client.post(f"/predict/{event_id}/qualifying", data=data)

    assert response.status_code == 403
    db = client.SessionLocal()
    try:
        assert db.query(Prediction).filter_by(event_id=event_id).count() == 0
    finally:
        db.close()


def test_locked_session_form_is_read_only(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6, qualifying_start=PAST)

    response = client.get(f"/predict/{event_id}/qualifying")

    assert response.status_code == 200
    assert "locked" in response.text.lower()
    assert "<select" not in response.text  # no editable form controls


def test_sprint_session_404s_when_event_has_no_sprint(client):
    register_and_login(client)
    event_id, _ = seed_event(client, grid_size=6, has_sprint=False)

    response = client.get(f"/predict/{event_id}/sprint")

    assert response.status_code == 404


def test_race_session_uses_full_grid_size(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    response = client.get(f"/predict/{event_id}/race")

    for i in range(1, 7):
        assert f'name="position_{i}"' in response.text
    assert f'name="position_7"' not in response.text


def test_qualifying_position_count_capped_at_entered_driver_count(client):
    # only 6 drivers entered even though "top 10" is the normal rule
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    response = client.get(f"/predict/{event_id}/qualifying")

    for i in range(1, 7):
        assert f'name="position_{i}"' in response.text
    assert 'name="position_7"' not in response.text


def test_qualifying_position_count_capped_at_ten_with_larger_grid(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=15, num_drivers=15)

    response = client.get(f"/predict/{event_id}/qualifying")

    for i in range(1, 11):
        assert f'name="position_{i}"' in response.text
    assert 'name="position_11"' not in response.text


def test_submit_all_bonus_types(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    data = {
        "first_penalty": str(driver_ids[0]),
        "first_pit": str(driver_ids[1]),
        "red_flag": "true",
        "safety_car": "false",
        "virtual_safety_car": "true",
        "classified_finishers": "5",
        "mvp": str(driver_ids[2]),
        "fastest_lap": str(driver_ids[3]),
    }
    response = client.post(f"/predict/{event_id}/bonuses", data=data)

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        bonuses = db.query(BonusPrediction).filter_by(event_id=event_id).all()
        assert len(bonuses) == 8
        by_type = {b.bonus_type.value: b for b in bonuses}
        assert by_type["classified_finishers"].int_value == 5
        assert by_type["red_flag"].bool_value is True
        assert by_type["mvp"].driver_id == driver_ids[2]
    finally:
        db.close()


def test_bonus_predictions_locked_when_race_locked(client):
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6, race_start=PAST)

    data = {
        "first_penalty": str(driver_ids[0]),
        "first_pit": str(driver_ids[1]),
        "red_flag": "true",
        "safety_car": "false",
        "virtual_safety_car": "true",
        "classified_finishers": "5",
        "mvp": str(driver_ids[2]),
        "fastest_lap": str(driver_ids[3]),
    }
    response = client.post(f"/predict/{event_id}/bonuses", data=data)

    assert response.status_code == 403


def test_db_level_unique_constraint_blocks_duplicate_position(client):
    # form-level validation is enforced by the route; this confirms the DB
    # constraint (added in Phase 1) is also actually active as a backstop
    register_and_login(client)
    event_id, driver_ids = seed_event(client, grid_size=6)

    db = client.SessionLocal()
    try:
        from app.models import User

        user = db.query(User).filter_by(username="alice").first()
        db.add(Prediction(user_id=user.id, event_id=event_id, session_type="qualifying", predicted_position=1, driver_id=driver_ids[0]))
        db.commit()
        db.add(Prediction(user_id=user.id, event_id=event_id, session_type="qualifying", predicted_position=1, driver_id=driver_ids[1]))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_unauthenticated_user_redirected_to_login(client):
    event_id, _ = seed_event(client, grid_size=6)

    response = client.get(f"/predict/{event_id}/qualifying", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
