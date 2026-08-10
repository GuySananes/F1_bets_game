from datetime import datetime, timedelta

from app.models import (
    BonusPrediction,
    BonusResult,
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

FUTURE = datetime.utcnow() + timedelta(days=30)


def make_admin_client(client):
    client.post("/auth/register", data={"username": "root", "password": "pw"})
    db = client.SessionLocal()
    try:
        user = db.query(User).filter_by(username="root").first()
        user.is_admin = True
        db.commit()
    finally:
        db.close()
    return client


def seed_season_with_race_data(client):
    """One season, one team, two drivers (one reserve), one fully-scored event
    (entries, predictions, results, bonuses, points), so reset has something to wipe."""
    db = client.SessionLocal()
    try:
        season = Season(year=2050, name="Test Season", default_grid_size=2, next_round_number=3)
        db.add(season)
        db.flush()
        team = Team(season_id=season.id, name="Test Team", color="#123456")
        db.add(team)
        db.flush()
        driver_a = Driver(
            season_id=season.id, team_id=team.id, name="Driver A",
            is_reserve=False, car_number=7, active=True,
        )
        driver_b = Driver(
            season_id=season.id, team_id=team.id, name="Driver B",
            is_reserve=True, car_number=None, active=False,
        )
        db.add_all([driver_a, driver_b])
        db.flush()

        event = Event(
            season_id=season.id, round_number=1, name="Test GP", has_sprint=False, grid_size=2,
            qualifying_start_time=FUTURE, race_start_time=FUTURE,
        )
        db.add(event)
        db.flush()

        db.add(EventEntry(event_id=event.id, driver_id=driver_a.id, is_substitute=False))
        db.commit()

        user = db.query(User).filter_by(username="root").first()
        db.add(
            Prediction(
                user_id=user.id, event_id=event.id, session_type=SessionType.race,
                predicted_position=1, driver_id=driver_a.id,
            )
        )
        db.add(Result(event_id=event.id, session_type=SessionType.race, actual_position=1, driver_id=driver_a.id))
        db.add(BonusPrediction(user_id=user.id, event_id=event.id, bonus_type="mvp", driver_id=driver_a.id))
        db.add(BonusResult(event_id=event.id, bonus_type="mvp", driver_id=driver_a.id))
        db.add(PointsLog(user_id=user.id, event_id=event.id, session_type=SessionType.race, points=25, detail={}))
        db.commit()

        return {
            "season_id": season.id,
            "team_id": team.id,
            "driver_a_id": driver_a.id,
            "driver_b_id": driver_b.id,
            "event_id": event.id,
        }
    finally:
        db.close()


def test_reset_season_deletes_all_race_data(client):
    make_admin_client(client)
    seeded = seed_season_with_race_data(client)

    response = client.post("/admin/season/reset", follow_redirects=False)

    assert response.status_code == 303
    db = client.SessionLocal()
    try:
        assert db.query(Event).filter_by(season_id=seeded["season_id"]).count() == 0
        assert db.query(EventEntry).filter_by(event_id=seeded["event_id"]).count() == 0
        assert db.query(Prediction).filter_by(event_id=seeded["event_id"]).count() == 0
        assert db.query(Result).filter_by(event_id=seeded["event_id"]).count() == 0
        assert db.query(BonusPrediction).filter_by(event_id=seeded["event_id"]).count() == 0
        assert db.query(BonusResult).filter_by(event_id=seeded["event_id"]).count() == 0
        assert db.query(PointsLog).filter_by(event_id=seeded["event_id"]).count() == 0
    finally:
        db.close()


def test_reset_season_keeps_teams_and_drivers_untouched(client):
    make_admin_client(client)
    seeded = seed_season_with_race_data(client)

    client.post("/admin/season/reset")

    db = client.SessionLocal()
    try:
        team = db.get(Team, seeded["team_id"])
        assert team is not None
        assert team.name == "Test Team"
        assert team.color == "#123456"

        driver_a = db.get(Driver, seeded["driver_a_id"])
        driver_b = db.get(Driver, seeded["driver_b_id"])
        assert driver_a is not None and driver_a.car_number == 7 and driver_a.active is True
        assert driver_b is not None and driver_b.is_reserve is True and driver_b.active is False
    finally:
        db.close()


def test_reset_season_resets_next_round_number(client):
    make_admin_client(client)
    seeded = seed_season_with_race_data(client)

    client.post("/admin/season/reset")

    db = client.SessionLocal()
    try:
        season = db.get(Season, seeded["season_id"])
        assert season.next_round_number == 1
    finally:
        db.close()


def test_reset_season_with_no_events_is_a_noop(client):
    make_admin_client(client)
    db = client.SessionLocal()
    try:
        season = Season(year=2050, name="Empty Season", default_grid_size=2)
        db.add(season)
        db.commit()
    finally:
        db.close()

    response = client.post("/admin/season/reset", follow_redirects=False)

    assert response.status_code == 303


def test_non_admin_cannot_reset_season(client):
    client.post("/auth/register", data={"username": "regular", "password": "pw"})
    db = client.SessionLocal()
    try:
        db.add(Season(year=2050, name="Test Season", default_grid_size=2))
        db.commit()
    finally:
        db.close()

    response = client.post("/admin/season/reset", follow_redirects=False)

    assert response.status_code == 403
