"""Pure scoring engine — no DB or FastAPI imports.

All functions take plain dicts/lists and return plain dicts/lists so they
are trivially unit-testable. See .claude/skills/f1-scoring-rules/SKILL.md
for the rules this implements.
"""

BONUS_POINTS = {
    "first_penalty": 5,
    "first_pit": 5,
    "red_flag": 3,
    "safety_car": 3,
    "virtual_safety_car": 3,
    "classified_finishers": 3,
    "mvp": 3,
    "fastest_lap": 3,
}


def score_position_predictions(predictions, results):
    """Score position predictions (qualifying, sprint, or race).

    predictions: list of {"position": int, "driver_id": Any}
    results: list of {"position": int, "driver_id": Any} — the actual
        classification, one entry per driver (DNF positions already
        resolved via order_dnf_drivers if applicable).

    Each predicted position is scored independently against where that
    predicted driver actually finished:
      - exact position match -> 3
      - off by exactly one -> 1
      - otherwise (including a driver with no result) -> 0
    """
    actual_position_by_driver = {r["driver_id"]: r["position"] for r in results}

    breakdown = []
    total = 0
    for prediction in predictions:
        driver_id = prediction["driver_id"]
        predicted_position = prediction["position"]
        actual_position = actual_position_by_driver.get(driver_id)

        if actual_position is None:
            points = 0
        else:
            diff = abs(actual_position - predicted_position)
            if diff == 0:
                points = 3
            elif diff == 1:
                points = 1
            else:
                points = 0

        breakdown.append(
            {
                "driver_id": driver_id,
                "predicted_position": predicted_position,
                "actual_position": actual_position,
                "points": points,
            }
        )
        total += points

    return {"total": total, "breakdown": breakdown}


def order_dnf_drivers(finishers, dnf_drivers):
    """Build a full race classification from finishers + DNF'd drivers.

    finishers: ordered list of driver_ids, in finishing order (index 0 = P1).
    dnf_drivers: list of {"driver_id": Any, "retired_at": comparable}, where
        a smaller "retired_at" means the driver retired earlier. Drivers who
        retire earlier are ranked lower (closer to last).

    Returns a list of {"position": int, "driver_id": Any, "dnf": bool},
    sorted by position, covering the full field (finishers + DNFs).
    """
    total_positions = len(finishers) + len(dnf_drivers)

    classification = [
        {"position": index, "driver_id": driver_id, "dnf": False}
        for index, driver_id in enumerate(finishers, start=1)
    ]

    sorted_dnfs = sorted(dnf_drivers, key=lambda d: d["retired_at"])
    for order, dnf in enumerate(sorted_dnfs):
        position = total_positions - order
        classification.append({"position": position, "driver_id": dnf["driver_id"], "dnf": True})

    classification.sort(key=lambda entry: entry["position"])
    return classification


def score_bonus_predictions(bonus_predictions, bonus_results):
    """Score race bonus predictions. Each bonus is all-or-nothing.

    bonus_predictions: list of {"bonus_type": str, "driver_id": Any | None,
        "bool_value": bool | None, "int_value": int | None}
    bonus_results: list of the same shape, one entry per bonus_type — the
        actual outcome.
    """
    result_by_type = {r["bonus_type"]: r for r in bonus_results}

    breakdown = []
    total = 0
    for prediction in bonus_predictions:
        bonus_type = prediction["bonus_type"]
        result = result_by_type.get(bonus_type)

        correct = False
        if result is not None:
            if prediction.get("driver_id") is not None:
                correct = prediction.get("driver_id") == result.get("driver_id")
            elif prediction.get("bool_value") is not None:
                correct = prediction.get("bool_value") == result.get("bool_value")
            elif prediction.get("int_value") is not None:
                correct = prediction.get("int_value") == result.get("int_value")

        points = BONUS_POINTS[bonus_type] if correct else 0
        breakdown.append({"bonus_type": bonus_type, "correct": correct, "points": points})
        total += points

    return {"total": total, "breakdown": breakdown}
