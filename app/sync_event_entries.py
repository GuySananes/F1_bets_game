"""Backfill missing event_entries for active, non-reserve drivers.

Roster changes (adding a team/driver, or activating a reserve) don't
automatically add that driver to events created before the change — an
event's entered-driver list lives entirely in event_entries, which is what
the predict pages and admin results forms read from. Without an entry, a
driver simply doesn't appear there.

This adds a plain (non-substitute) entry for any active, non-reserve driver
missing one on a given event. It never touches entries that already exist,
so substitutions and drivers an admin intentionally left out are untouched.

Run with: python -m app.sync_event_entries
"""

from app.database import SessionLocal
from app.models import Driver, Event, EventEntry


def sync_entries(db):
    events = db.query(Event).all()
    created = 0

    for event in events:
        existing_driver_ids = {e.driver_id for e in event.entries}
        primary_drivers = (
            db.query(Driver)
            .filter_by(season_id=event.season_id, is_reserve=False, active=True)
            .all()
        )
        for driver in primary_drivers:
            if driver.id in existing_driver_ids:
                continue
            db.add(EventEntry(event_id=event.id, driver_id=driver.id, is_substitute=False))
            created += 1

    db.commit()
    print(f"Added {created} missing event_entries across {len(events)} events.")


def sync():
    db = SessionLocal()
    try:
        sync_entries(db)
    finally:
        db.close()


if __name__ == "__main__":
    sync()
