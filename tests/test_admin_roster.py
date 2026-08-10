from datetime import datetime, timedelta

from app.auth import verify_password
from app.models import Driver, Event, EventEntry, Prediction, Result, Season, SessionType, Team, User

FUTURE = datetime.utcnow() + timedelta(days=30)


def make_admin_client(client):
    """Register a user then promote it to admin, logged in on the given client."""
    client.post("/auth/register", data={"username": "root", "password": "pw"})
    db = client.SessionLocal()
    try:
        user = db.query(User).filter_by(username="root").first()
        user.is_admin = True
        db.commit()
    finally:
        db.close()
    return client


def seed_minimal_roster(client):
    """Create one season, one team, two drivers directly in the DB (bypassing the UI,
    since team/driver *creation* isn't an admin-UI feature — only editing is)."""
    db = client.SessionLocal()
    try:
        season = Season(year=2099, name="Test Season", default_grid_size=2)
        db.add(season)
        db.flush()
        team = Team(season_id=season.id, name="Original Team")
        db.add(team)
        db.flush()
        driver_a = Driver(season_id=season.id, team_id=team.id, name="Original Driver A", is_reserve=False, active=True)
        driver_b = Driver(season_id=season.id, team_id=team.id, name="Original Driver B", is_reserve=True, active=True)
        db.add_all([driver_a, driver_b])
        db.commit()
        db.refresh(team)
        db.refresh(driver_a)
        db.refresh(driver_b)
        return season.id, team.id, driver_a.id, driver_b.id
    finally:
        db.close()


def test_admin_can_rename_team_through_ui(client):
    make_admin_client(client)
    _, team_id, _, _ = seed_minimal_roster(client)

    response = client.post(f"/admin/teams/{team_id}", data={"name": "Renamed Team"})

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        team = db.get(Team, team_id)
        assert team.name == "Renamed Team"
    finally:
        db.close()


def test_admin_can_rename_and_flag_driver_through_ui(client):
    make_admin_client(client)
    _, _, driver_id, _ = seed_minimal_roster(client)

    response = client.post(
        f"/admin/drivers/{driver_id}",
        data={"name": "Renamed Driver", "is_reserve": "on", "active": "on"},
    )

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        driver = db.get(Driver, driver_id)
        assert driver.name == "Renamed Driver"
        assert driver.is_reserve is True
        assert driver.active is True
    finally:
        db.close()


def test_admin_can_deactivate_driver_through_ui(client):
    make_admin_client(client)
    _, _, driver_id, _ = seed_minimal_roster(client)

    # omitting the checkbox fields means unchecked, per standard HTML form semantics
    response = client.post(f"/admin/drivers/{driver_id}", data={"name": "Still Named"})

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        driver = db.get(Driver, driver_id)
        assert driver.is_reserve is False
        assert driver.active is False
    finally:
        db.close()


def test_admin_can_create_event_with_custom_grid_size(client):
    make_admin_client(client)
    seed_minimal_roster(client)

    response = client.post(
        "/admin/events",
        data={
            "round_number": 1,
            "name": "Test Grand Prix",
            "grid_size": 17,
            "has_sprint": "on",
            "qualifying_start_time": "2099-01-01T10:00",
            "sprint_start_time": "2099-01-01T14:00",
            "race_start_time": "2099-01-02T13:00",
        },
    )

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        event = db.query(Event).filter_by(name="Test Grand Prix").first()
        assert event is not None
        assert event.grid_size == 17  # never hardcoded — whatever the admin entered
        assert event.has_sprint is True
    finally:
        db.close()


def test_admin_can_set_event_entries_including_substitution(client):
    make_admin_client(client)
    season_id, team_id, driver_a_id, driver_b_id = seed_minimal_roster(client)

    db = client.SessionLocal()
    try:
        event = Event(
            season_id=season_id, round_number=1, name="GP", has_sprint=False, grid_size=1,
            qualifying_start_time=FUTURE, race_start_time=FUTURE,
        )
        db.add(event)
        db.commit()
        event_id = event.id
    finally:
        db.close()

    # driver B (reserve) subs in for driver A; driver A does not race this weekend
    response = client.post(
        f"/admin/events/{event_id}/entries",
        data={
            f"entered_{driver_b_id}": "on",
            f"sub_{driver_b_id}": "on",
            f"subfor_{driver_b_id}": str(driver_a_id),
        },
    )

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        entries = db.query(EventEntry).filter_by(event_id=event_id).all()
        assert len(entries) == 1
        assert entries[0].driver_id == driver_b_id
        assert entries[0].is_substitute is True
        assert entries[0].substituted_for_driver_id == driver_a_id
    finally:
        db.close()


def test_renaming_driver_mid_season_does_not_corrupt_past_event_data(client):
    make_admin_client(client)
    season_id, team_id, driver_a_id, _ = seed_minimal_roster(client)

    db = client.SessionLocal()
    try:
        event = Event(
            season_id=season_id, round_number=1, name="Past GP", has_sprint=False, grid_size=1,
            qualifying_start_time=FUTURE, race_start_time=FUTURE,
        )
        db.add(event)
        db.flush()
        db.add(EventEntry(event_id=event.id, driver_id=driver_a_id, is_substitute=False))
        db.add(
            Prediction(
                user_id=1, event_id=event.id, session_type=SessionType.race,
                predicted_position=1, driver_id=driver_a_id,
            )
        )
        db.add(
            Result(event_id=event.id, session_type=SessionType.race, actual_position=1, driver_id=driver_a_id)
        )
        db.commit()
        event_id = event.id
    finally:
        db.close()

    client.post(f"/admin/drivers/{driver_a_id}", data={"name": "Brand New Name"})

    db = client.SessionLocal()
    try:
        driver = db.get(Driver, driver_a_id)
        assert driver.name == "Brand New Name"

        # every row that referenced this driver by ID still resolves correctly
        entry = db.query(EventEntry).filter_by(event_id=event_id).first()
        prediction = db.query(Prediction).filter_by(event_id=event_id).first()
        result = db.query(Result).filter_by(event_id=event_id).first()
        assert entry.driver_id == driver_a_id
        assert prediction.driver_id == driver_a_id
        assert result.driver_id == driver_a_id
        # and since references are by ID, they now display under the new name
        assert entry.driver.name == "Brand New Name"
    finally:
        db.close()


def test_admin_can_reset_user_password(client):
    make_admin_client(client)
    client.post("/auth/register", data={"username": "target", "password": "original-password"})
    db = client.SessionLocal()
    try:
        target_id = db.query(User).filter_by(username="target").first().id
    finally:
        db.close()

    # switch back to the admin session before performing the reset
    client.post("/auth/login", data={"username": "root", "password": "pw"})

    response = client.post(f"/admin/users/{target_id}/reset-password")

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        target = db.get(User, target_id)
        assert verify_password("F1", target.password_hash)
        assert not verify_password("original-password", target.password_hash)
    finally:
        db.close()

    client.cookies.clear()
    login_response = client.post("/auth/login", data={"username": "target", "password": "F1"})
    assert login_response.status_code == 200


def test_non_admin_cannot_reset_user_password(client):
    client.post("/auth/register", data={"username": "regular", "password": "pw"})
    db = client.SessionLocal()
    try:
        target_id = db.query(User).filter_by(username="regular").first().id
    finally:
        db.close()

    response = client.post(f"/admin/users/{target_id}/reset-password", follow_redirects=False)

    assert response.status_code == 403


def test_non_admin_user_redirected_from_admin_pages(client):
    client.post("/auth/register", data={"username": "regular", "password": "pw"})

    response = client.get("/admin/teams", follow_redirects=False)

    assert response.status_code == 403


def test_unauthenticated_visitor_redirected_to_login(client):
    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_admin_can_create_team_through_ui(client):
    make_admin_client(client)
    seed_minimal_roster(client)

    response = client.post("/admin/teams", data={"name": "New Team"})

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        team = db.query(Team).filter_by(name="New Team").first()
        assert team is not None
    finally:
        db.close()


def test_admin_can_delete_team_with_no_drivers(client):
    make_admin_client(client)
    seed_minimal_roster(client)
    db = client.SessionLocal()
    try:
        empty_team = Team(season_id=db.query(Season).first().id, name="Empty Team")
        db.add(empty_team)
        db.commit()
        empty_team_id = empty_team.id
    finally:
        db.close()

    response = client.post(f"/admin/teams/{empty_team_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "error" not in response.headers["location"]
    db = client.SessionLocal()
    try:
        assert db.get(Team, empty_team_id) is None
    finally:
        db.close()


def test_admin_cannot_delete_team_with_drivers(client):
    make_admin_client(client)
    _, team_id, _, _ = seed_minimal_roster(client)

    response = client.post(f"/admin/teams/{team_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    db = client.SessionLocal()
    try:
        assert db.get(Team, team_id) is not None
    finally:
        db.close()


def test_admin_can_create_driver_through_ui(client):
    make_admin_client(client)
    _, team_id, _, _ = seed_minimal_roster(client)

    response = client.post(
        "/admin/drivers",
        data={"name": "Brand New Driver", "team_id": team_id, "active": "on"},
    )

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        driver = db.query(Driver).filter_by(name="Brand New Driver").first()
        assert driver is not None
        assert driver.team_id == team_id
        assert driver.is_reserve is False
        assert driver.active is True
    finally:
        db.close()


def test_admin_can_delete_driver_with_no_dependents(client):
    make_admin_client(client)
    _, _, driver_id, unused_driver_id = seed_minimal_roster(client)

    response = client.post(f"/admin/drivers/{unused_driver_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "error" not in response.headers["location"]
    db = client.SessionLocal()
    try:
        assert db.get(Driver, unused_driver_id) is None
    finally:
        db.close()


def test_admin_cannot_delete_driver_with_predictions(client):
    make_admin_client(client)
    season_id, _, driver_id, _ = seed_minimal_roster(client)

    db = client.SessionLocal()
    try:
        event = Event(
            season_id=season_id, round_number=1, name="GP", has_sprint=False, grid_size=1,
            qualifying_start_time=FUTURE, race_start_time=FUTURE,
        )
        db.add(event)
        db.flush()
        db.add(
            Prediction(
                user_id=1, event_id=event.id, session_type=SessionType.race,
                predicted_position=1, driver_id=driver_id,
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(f"/admin/drivers/{driver_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    db = client.SessionLocal()
    try:
        assert db.get(Driver, driver_id) is not None
    finally:
        db.close()


def test_new_events_get_auto_assigned_incrementing_round_numbers(client):
    make_admin_client(client)
    seed_minimal_roster(client)

    payload = {
        "name": "First Event",
        "grid_size": 2,
        "qualifying_start_time": "2099-01-01T10:00",
        "race_start_time": "2099-01-02T13:00",
    }
    client.post("/admin/events", data=payload)
    client.post("/admin/events", data={**payload, "name": "Second Event"})

    db = client.SessionLocal()
    try:
        first = db.query(Event).filter_by(name="First Event").first()
        second = db.query(Event).filter_by(name="Second Event").first()
        assert first.round_number == 1
        assert second.round_number == 2
    finally:
        db.close()


def test_admin_can_override_next_round_number_for_mid_season_start(client):
    make_admin_client(client)
    seed_minimal_roster(client)

    client.post("/admin/season/next-round-number", data={"next_round_number": 14})
    client.post(
        "/admin/events",
        data={
            "name": "Mid-season Event",
            "grid_size": 2,
            "qualifying_start_time": "2099-01-01T10:00",
            "race_start_time": "2099-01-02T13:00",
        },
    )

    db = client.SessionLocal()
    try:
        event = db.query(Event).filter_by(name="Mid-season Event").first()
        assert event.round_number == 14
        season = db.query(Season).first()
        assert season.next_round_number == 15
    finally:
        db.close()


def test_admin_can_delete_event_with_no_dependents(client):
    make_admin_client(client)
    season_id, _, _, _ = seed_minimal_roster(client)
    db = client.SessionLocal()
    try:
        event = Event(
            season_id=season_id, round_number=1, name="Unused GP", has_sprint=False, grid_size=1,
            qualifying_start_time=FUTURE, race_start_time=FUTURE,
        )
        db.add(event)
        db.commit()
        event_id = event.id
    finally:
        db.close()

    response = client.post(f"/admin/events/{event_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "error" not in response.headers["location"]
    db = client.SessionLocal()
    try:
        assert db.get(Event, event_id) is None
    finally:
        db.close()


def test_admin_cannot_delete_event_with_results(client):
    make_admin_client(client)
    season_id, _, driver_id, _ = seed_minimal_roster(client)
    db = client.SessionLocal()
    try:
        event = Event(
            season_id=season_id, round_number=1, name="Scored GP", has_sprint=False, grid_size=1,
            qualifying_start_time=FUTURE, race_start_time=FUTURE,
        )
        db.add(event)
        db.flush()
        db.add(
            Result(event_id=event.id, session_type=SessionType.race, actual_position=1, driver_id=driver_id)
        )
        db.commit()
        event_id = event.id
    finally:
        db.close()

    response = client.post(f"/admin/events/{event_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    db = client.SessionLocal()
    try:
        assert db.get(Event, event_id) is not None
    finally:
        db.close()
