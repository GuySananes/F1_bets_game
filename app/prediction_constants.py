"""Shared between the user-facing predictions UI and admin results entry,
since both render the same set of session/bonus fields."""

SESSION_LABELS = {"qualifying": "Qualifying", "sprint": "Sprint", "race": "Race"}

BONUS_FIELDS = [
    ("first_penalty", "First driver to receive a penalty", "driver"),
    ("first_pit", "First driver to pit", "driver"),
    ("red_flag", "Red flag shown", "bool"),
    ("safety_car", "Safety car deployed", "bool"),
    ("virtual_safety_car", "Virtual safety car deployed", "bool"),
    ("classified_finishers", "Number of classified finishers", "int"),
    ("mvp", "MVP driver of the race", "driver"),
    ("fastest_lap", "Fastest lap driver", "driver"),
]
