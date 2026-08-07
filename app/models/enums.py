import enum


class SessionType(str, enum.Enum):
    qualifying = "qualifying"
    sprint = "sprint"
    race = "race"


class BonusType(str, enum.Enum):
    first_penalty = "first_penalty"
    first_pit = "first_pit"
    red_flag = "red_flag"
    safety_car = "safety_car"
    virtual_safety_car = "virtual_safety_car"
    classified_finishers = "classified_finishers"
    mvp = "mvp"
    fastest_lap = "fastest_lap"
