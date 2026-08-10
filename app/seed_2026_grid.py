"""Upsert the real 2026 F1 teams/drivers grid into the current season.

Unlike app/seed.py (which seeds a deliberately small placeholder fixture for
tests), this populates the actual 11-team, 22-driver 2026 grid used by the
live app. It matches existing teams/drivers by name where possible (so
roster entries already made through the admin UI are updated in place, not
duplicated) and creates anything missing.

Colors for Audi and Cadillac are best estimates, not confirmed official
livery hex codes, since both are new F1 entrants for 2026 — update them in
the admin UI once real liveries are announced.

Run with: python -m app.seed_2026_grid
"""

from app.database import SessionLocal
from app.models import Driver, Season, Team

GRID = [
    {"team": "McLaren", "color": "#FF8000", "drivers": ["Lando Norris", "Oscar Piastri"]},
    {"team": "Ferrari", "color": "#E80020", "drivers": ["Lewis Hamilton", "Charles Leclerc"]},
    {"team": "Red Bull Racing", "color": "#3671C6", "drivers": ["Max Verstappen", "Isack Hadjar"]},
    {"team": "Mercedes", "color": "#27F4D2", "drivers": ["George Russell", "Kimi Antonelli"]},
    {"team": "Aston Martin", "color": "#229971", "drivers": ["Fernando Alonso", "Lance Stroll"]},
    {"team": "Alpine", "color": "#0090FF", "drivers": ["Pierre Gasly", "Franco Colapinto"]},
    {"team": "Williams", "color": "#64C4FF", "drivers": ["Alex Albon", "Carlos Sainz"]},
    {"team": "Racing Bulls", "color": "#6692FF", "drivers": ["Liam Lawson", "Arvid Lindblad"]},
    {"team": "Haas", "color": "#B6BABD", "drivers": ["Esteban Ocon", "Oliver Bearman"]},
    {"team": "Audi", "color": "#BB0A30", "drivers": ["Nico Hülkenberg", "Gabriel Bortoleto"]},
    {"team": "Cadillac", "color": "#0A0A0A", "drivers": ["Sergio Pérez", "Valtteri Bottas"]},
]

# Existing team names in the DB that should be treated as the same team
# under a new/canonical name (rather than creating a duplicate).
TEAM_ALIASES = {
    "Red Bull": "Red Bull Racing",
}

# Existing driver names that should be corrected in place.
DRIVER_ALIASES = {
    "Isak Hadjar": "Isack Hadjar",
}


def seed_grid(db):
    season = db.query(Season).order_by(Season.year.desc()).first()
    if season is None:
        raise RuntimeError("No season exists yet — run app.seed first.")

    teams_by_name = {team.name: team for team in db.query(Team).filter_by(season_id=season.id).all()}
    for old_name, new_name in TEAM_ALIASES.items():
        if old_name in teams_by_name and new_name not in teams_by_name:
            teams_by_name[old_name].name = new_name
            teams_by_name[new_name] = teams_by_name.pop(old_name)

    drivers_by_key = {
        (d.team_id, d.name): d for d in db.query(Driver).filter_by(season_id=season.id).all()
    }
    for old_name, new_name in DRIVER_ALIASES.items():
        for (team_id, name), driver in list(drivers_by_key.items()):
            if name == old_name:
                driver.name = new_name
                drivers_by_key[(team_id, new_name)] = drivers_by_key.pop((team_id, name))

    teams_created = teams_updated = 0
    drivers_created = drivers_updated = 0

    for entry in GRID:
        team = teams_by_name.get(entry["team"])
        if team is None:
            team = Team(season_id=season.id, name=entry["team"], color=entry["color"])
            db.add(team)
            db.flush()
            teams_by_name[entry["team"]] = team
            teams_created += 1
        elif team.color != entry["color"]:
            team.color = entry["color"]
            teams_updated += 1

        for driver_name in entry["drivers"]:
            driver = drivers_by_key.get((team.id, driver_name))
            if driver is None:
                driver = Driver(
                    season_id=season.id,
                    team_id=team.id,
                    name=driver_name,
                    is_reserve=False,
                    active=True,
                )
                db.add(driver)
                drivers_by_key[(team.id, driver_name)] = driver
                drivers_created += 1
            elif not driver.active or driver.is_reserve:
                driver.active = True
                driver.is_reserve = False
                drivers_updated += 1

    db.commit()
    print(
        f"Grid synced for season {season.year} (id={season.id}): "
        f"{teams_created} teams created, {teams_updated} teams updated, "
        f"{drivers_created} drivers created, {drivers_updated} drivers updated."
    )


def seed():
    db = SessionLocal()
    try:
        seed_grid(db)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
