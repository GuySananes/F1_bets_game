from datetime import datetime, timedelta

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


def test_non_admin_user_redirected_from_admin_pages(client):
    client.post("/auth/register", data={"username": "regular", "password": "pw"})

    response = client.get("/admin/teams", follow_redirects=False)

    assert response.status_code == 403


def test_unauthenticated_visitor_redirected_to_login(client):
    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
