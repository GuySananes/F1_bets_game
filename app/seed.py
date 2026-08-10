"""Seed a small fixture season, plus one admin user, for local dev and tests.

Season/grid: deliberately a small (3-team) grid rather than a full
real-world F1 field — this is the shared fixture used by tests going
forward, and its size is chosen to keep DNF ordering / top-10 qualifying
scenarios easy to reason about. Team and driver names are placeholders;
admins can rename them at any time (see CLAUDE.md: names are never assumed
stable).

Admin user: username "admin", so Phase 3's admin-only routes have someone
to log in as. Password comes from the ADMIN_SEED_PASSWORD env var, falling
back to a dev-only default — change it before this ever runs against
anything but a local dev DB.

Run with: python -m app.seed
"""

import os
from datetime import datetime, timedelta

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Driver, Event, EventEntry, Season, Team, User

ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "changeme123"


def seed_admin_user(db):
    existing = db.query(User).filter_by(username=ADMIN_USERNAME).first()
    if existing:
        print(f"Admin user '{ADMIN_USERNAME}' already seeded (id={existing.id}); skipping.")
        return

    password = os.getenv("ADMIN_SEED_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    admin = User(username=ADMIN_USERNAME, password_hash=hash_password(password), is_admin=True)
    db.add(admin)
    db.commit()
    print(f"Seeded admin user '{ADMIN_USERNAME}' (id={admin.id}).")


def seed_season(db):
    existing = db.query(Season).filter_by(year=2026).first()
    if existing:
        print(f"Season {existing.year} already seeded (id={existing.id}); skipping.")
        return

    season = Season(year=2026, name="2026 Fixture Season", default_grid_size=9)
    db.add(season)
    db.flush()

    team_names = ["Falcon Racing", "Orbit Motorsport", "Nova GP"]
    teams = []
    for name in team_names:
        team = Team(season_id=season.id, name=name)
        db.add(team)
        teams.append(team)
    db.flush()

    car_number = 1
    drivers = []
    for team in teams:
        for role, is_reserve in (("Driver 1", False), ("Driver 2", False), ("Reserve", True)):
            driver = Driver(
                season_id=season.id,
                team_id=team.id,
                name=f"{team.name} {role}",
                is_reserve=is_reserve,
                car_number=car_number,
                active=True,
            )
            db.add(driver)
            drivers.append(driver)
            car_number += 1
    db.flush()

    # Lock times 30 days out so the fixture event's predictions stay open for local
    # dev/testing regardless of when this script is run.
    qualifying_start = datetime.utcnow() + timedelta(days=29)
    sprint_start = datetime.utcnow() + timedelta(days=29, hours=12)
    race_start = datetime.utcnow() + timedelta(days=30)

    event = Event(
        season_id=season.id,
        round_number=1,
        name="Fixture Grand Prix",
        has_sprint=True,
        grid_size=6,
        qualifying_start_time=qualifying_start,
        sprint_start_time=sprint_start,
        race_start_time=race_start,
    )
    db.add(event)
    season.next_round_number = event.round_number + 1
    db.flush()

    primary_drivers = [d for d in drivers if not d.is_reserve]
    for driver in primary_drivers:
        db.add(EventEntry(event_id=event.id, driver_id=driver.id, is_substitute=False))

    db.commit()
    print(
        f"Seeded season {season.year} (id={season.id}) with {len(teams)} teams, "
        f"{len(drivers)} drivers, and event '{event.name}' (id={event.id})."
    )


def seed():
    db = SessionLocal()
    try:
        seed_admin_user(db)
        seed_season(db)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
