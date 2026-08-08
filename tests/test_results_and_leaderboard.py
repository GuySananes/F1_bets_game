from datetime import datetime, timedelta

from app.models import (
    BonusPrediction,
    Driver,
    Event,
    EventEntry,
    PointsLog,
    Prediction,
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


def register(client, username, password="pw12345"):
    client.post("/auth/register", data={"username": username, "password": password})


def login(client, username, password):
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200


def build_scenario(client):
    """3 drivers (A, B, C), one event (no sprint), two non-admin users (alice, bob)
    with hand-calculable predictions for qualifying + race + bonuses."""
    db = client.SessionLocal()
    try:
        season = Season(year=2098, name="Hand-Calc Season", default_grid_size=3)
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
            name="Hand-Calc GP",
            has_sprint=False,
            grid_size=3,
            qualifying_start_time=FUTURE,
            race_start_time=FUTURE,
        )
        db.add(event)
        db.flush()

        for driver_id in drivers.values():
            db.add(EventEntry(event_id=event.id, driver_id=driver_id, is_substitute=False))

        db.commit()
        event_id = event.id
    finally:
        db.close()

    register(client, "alice")
    register(client, "bob")

    db = client.SessionLocal()
    try:
        alice_id = db.query(User).filter_by(username="alice").first().id
        bob_id = db.query(User).filter_by(username="bob").first().id

        # --- qualifying predictions ---
        alice_quali = {1: "A", 2: "C", 3: "B"}
        bob_quali = {1: "B", 2: "A", 3: "C"}
        for pos, name in alice_quali.items():
            db.add(Prediction(user_id=alice_id, event_id=event_id, session_type=SessionType.qualifying, predicted_position=pos, driver_id=drivers[name]))
        for pos, name in bob_quali.items():
            db.add(Prediction(user_id=bob_id, event_id=event_id, session_type=SessionType.qualifying, predicted_position=pos, driver_id=drivers[name]))

        # --- race predictions ---
        alice_race = {1: "A", 2: "B", 3: "C"}
        bob_race = {1: "C", 2: "A", 3: "B"}
        for pos, name in alice_race.items():
            db.add(Prediction(user_id=alice_id, event_id=event_id, session_type=SessionType.race, predicted_position=pos, driver_id=drivers[name]))
        for pos, name in bob_race.items():
            db.add(Prediction(user_id=bob_id, event_id=event_id, session_type=SessionType.race, predicted_position=pos, driver_id=drivers[name]))

        # --- bonus predictions ---
        alice_bonus = {
            "first_penalty": {"driver_id": drivers["A"]},
            "first_pit": {"driver_id": drivers["C"]},
            "red_flag": {"bool_value": True},
            "safety_car": {"bool_value": False},
            "virtual_safety_car": {"bool_value": False},
            "classified_finishers": {"int_value": 1},
            "mvp": {"driver_id": drivers["A"]},
            "fastest_lap": {"driver_id": drivers["B"]},
        }
        bob_bonus = {
            "first_penalty": {"driver_id": drivers["B"]},
            "first_pit": {"driver_id": drivers["B"]},
            "red_flag": {"bool_value": False},
            "safety_car": {"bool_value": True},
            "virtual_safety_car": {"bool_value": True},
            "classified_finishers": {"int_value": 2},
            "mvp": {"driver_id": drivers["C"]},
            "fastest_lap": {"driver_id": drivers["C"]},
        }
        for bonus_type, values in alice_bonus.items():
            db.add(BonusPrediction(user_id=alice_id, event_id=event_id, bonus_type=bonus_type, **values))
        for bonus_type, values in bob_bonus.items():
            db.add(BonusPrediction(user_id=bob_id, event_id=event_id, bonus_type=bonus_type, **values))

        db.commit()
    finally:
        db.close()

    return event_id, drivers, alice_id, bob_id


def enter_qualifying_results(client, event_id, drivers):
    data = {
        f"position_{drivers['A']}": "1",
        f"position_{drivers['B']}": "2",
        f"position_{drivers['C']}": "3",
    }
    response = client.post(f"/admin/events/{event_id}/results/qualifying", data=data)
    assert response.status_code == 200


def enter_race_results(client, event_id, drivers):
    # A finishes P1; B and C both DNF (C retired first at lap 10, B retired later at lap 20)
    data = {
        f"position_{drivers['A']}": "1",
        f"dnf_{drivers['B']}": "on",
        f"retired_at_{drivers['B']}": "20",
        f"dnf_{drivers['C']}": "on",
        f"retired_at_{drivers['C']}": "10",
    }
    response = client.post(f"/admin/events/{event_id}/results/race", data=data)
    assert response.status_code == 200


def enter_bonus_results(client, event_id, drivers):
    data = {
        "first_penalty": str(drivers["A"]),
        "first_pit": str(drivers["B"]),
        "red_flag": "true",
        "safety_car": "false",
        "virtual_safety_car": "true",
        "classified_finishers": "1",
        "mvp": str(drivers["A"]),
        "fastest_lap": str(drivers["C"]),
    }
    response = client.post(f"/admin/events/{event_id}/results/bonuses", data=data)
    assert response.status_code == 200


def test_qualifying_results_entry_computes_expected_points(client):
    admin = make_admin_client(client)
    event_id, drivers, alice_id, bob_id = build_scenario(client)
    login(client, "root", "pw")

    enter_qualifying_results(admin, event_id, drivers)

    db = client.SessionLocal()
    try:
        alice_log = db.query(PointsLog).filter_by(user_id=alice_id, event_id=event_id, session_type="qualifying").first()
        bob_log = db.query(PointsLog).filter_by(user_id=bob_id, event_id=event_id, session_type="qualifying").first()
        # alice: A exact(3) + C off-by-one(1) + B off-by-one(1) = 5
        assert alice_log.points == 5
        # bob: B off-by-one(1) + A off-by-one(1) + C exact(3) = 5
        assert bob_log.points == 5
    finally:
        db.close()


def test_race_results_with_dnf_computes_expected_classification_and_points(client):
    admin = make_admin_client(client)
    event_id, drivers, alice_id, bob_id = build_scenario(client)
    login(client, "root", "pw")

    enter_race_results(admin, event_id, drivers)

    db = client.SessionLocal()
    try:
        from app.models import Result

        results = {r.driver_id: r for r in db.query(Result).filter_by(event_id=event_id, session_type="race").all()}
        assert results[drivers["A"]].actual_position == 1
        assert results[drivers["A"]].dnf is False
        assert results[drivers["C"]].actual_position == 3  # retired first -> last
        assert results[drivers["C"]].dnf is True
        assert results[drivers["B"]].actual_position == 2  # retired second -> second-to-last
        assert results[drivers["B"]].dnf is True

        alice_log = db.query(PointsLog).filter_by(user_id=alice_id, event_id=event_id, session_type="race").first()
        bob_log = db.query(PointsLog).filter_by(user_id=bob_id, event_id=event_id, session_type="race").first()
        # alice predicted A/B/C exactly matching the real classification -> 3+3+3 = 9
        assert alice_log.points == 9
        # bob: C@1(actual 3, diff2->0) + A@2(actual1, diff1->1) + B@3(actual2, diff1->1) = 2
        assert bob_log.points == 2
    finally:
        db.close()


def test_bonus_results_combine_into_race_points_log(client):
    admin = make_admin_client(client)
    event_id, drivers, alice_id, bob_id = build_scenario(client)
    login(client, "root", "pw")

    enter_race_results(admin, event_id, drivers)
    enter_bonus_results(admin, event_id, drivers)

    db = client.SessionLocal()
    try:
        alice_log = db.query(PointsLog).filter_by(user_id=alice_id, event_id=event_id, session_type="race").first()
        bob_log = db.query(PointsLog).filter_by(user_id=bob_id, event_id=event_id, session_type="race").first()
        # alice bonus: first_penalty(5)+first_pit(0)+red_flag(3)+safety_car(3)+vsc(0)+finishers(3)+mvp(3)+fastest_lap(0) = 17
        # + race position points (9) = 26
        assert alice_log.points == 9 + 17
        # bob bonus: first_penalty(0)+first_pit(5)+red_flag(0)+safety_car(0)+vsc(3)+finishers(0)+mvp(0)+fastest_lap(3) = 11
        # + race position points (2) = 13
        assert bob_log.points == 2 + 11
        assert "bonus" in alice_log.detail
        assert len(alice_log.detail["bonus"]) == 8
    finally:
        db.close()


def test_leaderboard_matches_hand_calculated_totals(client):
    admin = make_admin_client(client)
    event_id, drivers, alice_id, bob_id = build_scenario(client)
    login(client, "root", "pw")

    enter_qualifying_results(admin, event_id, drivers)
    enter_race_results(admin, event_id, drivers)
    enter_bonus_results(admin, event_id, drivers)

    # alice: qualifying 5 + race (9 + 17) = 31
    # bob:   qualifying 5 + race (2 + 11) = 18
    response = client.get("/leaderboard")
    assert response.status_code == 200
    text = response.text

    alice_pos = text.find("alice")
    bob_pos = text.find("bob")
    assert alice_pos != -1 and bob_pos != -1
    assert alice_pos < bob_pos  # alice (31) ranked above bob (18)
    assert "31" in text
    assert "18" in text

    event_response = client.get(f"/leaderboard/{event_id}")
    assert event_response.status_code == 200
    event_text = event_response.text
    assert "31" in event_text
    assert "18" in event_text


def test_predict_overview_links_to_results_and_shows_my_points(client):
    admin = make_admin_client(client)
    event_id, drivers, alice_id, bob_id = build_scenario(client)
    login(client, "root", "pw")

    login(client, "alice", "pw12345")
    before = client.get(f"/predict/{event_id}")
    assert before.status_code == 200
    assert f'href="/leaderboard/{event_id}"' in before.text
    assert "Not scored yet" in before.text

    login(client, "root", "pw")
    enter_qualifying_results(admin, event_id, drivers)

    login(client, "alice", "pw12345")
    after = client.get(f"/predict/{event_id}")
    assert after.status_code == 200
    assert "5 pts" in after.text  # alice's qualifying points from build_scenario


def test_event_leaderboard_shows_empty_state_before_results(client):
    event_id, drivers, alice_id, bob_id = build_scenario(client)

    login(client, "alice", "pw12345")
    response = client.get(f"/leaderboard/{event_id}")

    assert response.status_code == 200
    assert "No results entered yet" in response.text


def test_event_leaderboard_shows_your_points_summary(client):
    admin = make_admin_client(client)
    event_id, drivers, alice_id, bob_id = build_scenario(client)
    login(client, "root", "pw")

    enter_qualifying_results(admin, event_id, drivers)

    login(client, "alice", "pw12345")
    response = client.get(f"/leaderboard/{event_id}")

    assert response.status_code == 200
    assert "Your points" in response.text
    assert "5" in response.text


def test_non_admin_cannot_enter_results(client):
    register(client, "regular")
    event_id, drivers, _, _ = build_scenario(client)

    response = client.post(
        f"/admin/events/{event_id}/results/qualifying",
        data={f"position_{drivers['A']}": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 403
