from datetime import datetime, timedelta

from app.models import BonusPrediction, Driver, Event, EventEntry, PointsLog, Prediction, Result, Season, SessionType, Team, User

PAST = datetime.utcnow() - timedelta(days=1)
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


def register(client, username, password="pw12345"):
    client.post("/auth/register", data={"username": username, "password": password})


def login(client, username, password):
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200


def seed_locked_event(client, start_time=PAST):
    db = client.SessionLocal()
    try:
        season = Season(year=2101, name="Admin Random Bet Season", default_grid_size=3)
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
            season_id=season.id, round_number=1, name="Admin GP", has_sprint=False, grid_size=3,
            qualifying_start_time=start_time, race_start_time=start_time,
        )
        db.add(event)
        db.flush()

        for driver_id in drivers.values():
            db.add(EventEntry(event_id=event.id, driver_id=driver_id, is_substitute=False))

        db.commit()
        return event.id, drivers
    finally:
        db.close()


def test_non_admin_cannot_view_missing_bets_page(client):
    register(client, "regular")
    event_id, _ = seed_locked_event(client)

    response = client.get(f"/admin/events/{event_id}/results/qualifying/missing-bets", follow_redirects=False)

    assert response.status_code == 403


def test_admin_can_generate_random_bet_for_missing_user(client):
    admin = make_admin_client(client)
    event_id, drivers = seed_locked_event(admin)
    register(client, "alice")
    db = client.SessionLocal()
    try:
        alice_id = db.query(User).filter_by(username="alice").first().id
    finally:
        db.close()

    login(admin, "root", "pw")
    page = admin.get(f"/admin/events/{event_id}/results/qualifying/missing-bets")
    assert page.status_code == 200
    assert "alice" in page.text

    response = admin.post(f"/admin/events/{event_id}/results/qualifying/random-bets/{alice_id}", follow_redirects=False)
    assert response.status_code == 303

    db = client.SessionLocal()
    try:
        rows = db.query(Prediction).filter_by(user_id=alice_id, event_id=event_id, session_type=SessionType.qualifying).all()
        assert len(rows) == 3
        assert all(r.is_auto_generated for r in rows)
    finally:
        db.close()


def test_generating_random_bet_twice_does_not_overwrite_real_submission(client):
    admin = make_admin_client(client)
    event_id, drivers = seed_locked_event(admin, start_time=FUTURE)
    register(client, "alice")
    db = client.SessionLocal()
    try:
        alice_id = db.query(User).filter_by(username="alice").first().id
        db.add(
            Prediction(
                user_id=alice_id, event_id=event_id, session_type=SessionType.qualifying,
                predicted_position=1, driver_id=drivers["A"],
            )
        )
        db.commit()
    finally:
        db.close()

    login(admin, "root", "pw")
    admin.post(f"/admin/events/{event_id}/results/qualifying/random-bets/{alice_id}")

    db = client.SessionLocal()
    try:
        rows = db.query(Prediction).filter_by(user_id=alice_id, event_id=event_id, session_type=SessionType.qualifying).all()
        assert len(rows) == 1
        assert rows[0].is_auto_generated is False
        assert rows[0].driver_id == drivers["A"]
    finally:
        db.close()


def test_bulk_randomize_fills_all_missing_and_recomputes_points(client):
    admin = make_admin_client(client)
    event_id, drivers = seed_locked_event(admin)
    register(client, "alice")
    register(client, "bob")

    db = client.SessionLocal()
    try:
        db.add(Result(event_id=event_id, session_type=SessionType.qualifying, actual_position=1, driver_id=drivers["A"]))
        db.add(Result(event_id=event_id, session_type=SessionType.qualifying, actual_position=2, driver_id=drivers["B"]))
        db.add(Result(event_id=event_id, session_type=SessionType.qualifying, actual_position=3, driver_id=drivers["C"]))
        db.commit()
    finally:
        db.close()

    login(admin, "root", "pw")
    response = admin.post(f"/admin/events/{event_id}/results/qualifying/random-bets/bulk", follow_redirects=False)
    assert response.status_code == 303

    db = client.SessionLocal()
    try:
        alice_id = db.query(User).filter_by(username="alice").first().id
        bob_id = db.query(User).filter_by(username="bob").first().id

        for user_id in (alice_id, bob_id):
            rows = db.query(Prediction).filter_by(user_id=user_id, event_id=event_id, session_type=SessionType.qualifying).all()
            assert len(rows) == 3
            assert all(r.is_auto_generated for r in rows)
            log = db.query(PointsLog).filter_by(user_id=user_id, event_id=event_id, session_type="qualifying").first()
            assert log is not None
    finally:
        db.close()
