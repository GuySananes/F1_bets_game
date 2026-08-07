from app.scoring import BONUS_POINTS, order_dnf_drivers, score_bonus_predictions, score_position_predictions


# ---------------------------------------------------------------------------
# score_position_predictions
# ---------------------------------------------------------------------------

def test_exact_match_scores_three():
    predictions = [{"position": 3, "driver_id": "HAM"}]
    results = [{"position": 3, "driver_id": "HAM"}]

    outcome = score_position_predictions(predictions, results)

    assert outcome["total"] == 3
    assert outcome["breakdown"][0]["points"] == 3
    assert outcome["breakdown"][0]["actual_position"] == 3


def test_off_by_one_above_scores_one():
    # predicted P3, actually finished P2 (one above)
    predictions = [{"position": 3, "driver_id": "VER"}]
    results = [{"position": 2, "driver_id": "VER"}]

    outcome = score_position_predictions(predictions, results)

    assert outcome["total"] == 1
    assert outcome["breakdown"][0]["points"] == 1


def test_off_by_one_below_scores_one():
    # predicted P3, actually finished P4 (one below)
    predictions = [{"position": 3, "driver_id": "LEC"}]
    results = [{"position": 4, "driver_id": "LEC"}]

    outcome = score_position_predictions(predictions, results)

    assert outcome["total"] == 1
    assert outcome["breakdown"][0]["points"] == 1


def test_no_match_scores_zero():
    predictions = [{"position": 1, "driver_id": "NOR"}]
    results = [{"position": 5, "driver_id": "NOR"}]

    outcome = score_position_predictions(predictions, results)

    assert outcome["total"] == 0
    assert outcome["breakdown"][0]["points"] == 0


def test_driver_missing_from_results_scores_zero():
    # e.g. predicted driver didn't actually take part (no result entry at all)
    predictions = [{"position": 1, "driver_id": "GHOST"}]
    results = [{"position": 1, "driver_id": "PIA"}]

    outcome = score_position_predictions(predictions, results)

    assert outcome["total"] == 0
    assert outcome["breakdown"][0]["actual_position"] is None


def test_empty_predictions_scores_zero():
    outcome = score_position_predictions([], [{"position": 1, "driver_id": "PIA"}])

    assert outcome["total"] == 0
    assert outcome["breakdown"] == []


def test_partial_predictions_only_scores_submitted_positions():
    # e.g. a qualifying prediction only covers top 10, not the full grid
    predictions = [
        {"position": 1, "driver_id": "VER"},
        {"position": 2, "driver_id": "HAM"},
    ]
    results = [
        {"position": 1, "driver_id": "VER"},
        {"position": 2, "driver_id": "LEC"},
        {"position": 3, "driver_id": "HAM"},
    ]

    outcome = score_position_predictions(predictions, results)

    # VER exact (3) + HAM off-by-one, predicted P2 actual P3 (1)
    assert outcome["total"] == 4


# ---------------------------------------------------------------------------
# order_dnf_drivers
# ---------------------------------------------------------------------------

def test_order_dnf_drivers_single_dnf_takes_last_position():
    finishers = ["A", "B", "C"]
    dnfs = [{"driver_id": "D", "retired_at": 10}]

    classification = order_dnf_drivers(finishers, dnfs)

    positions = {c["driver_id"]: c["position"] for c in classification}
    assert positions == {"A": 1, "B": 2, "C": 3, "D": 4}
    assert all(c["dnf"] is False for c in classification if c["driver_id"] != "D")
    assert next(c for c in classification if c["driver_id"] == "D")["dnf"] is True


def test_order_dnf_drivers_multiple_dnfs_ordered_by_retirement_time():
    # matches the spec example: earliest retiree gets the very last position
    finishers = ["F1", "F2", "F3"]
    dnfs = [
        {"driver_id": "LATE", "retired_at": 30},   # retired second -> second-to-last
        {"driver_id": "EARLY", "retired_at": 10},  # retired first -> last
    ]

    classification = order_dnf_drivers(finishers, dnfs)

    positions = {c["driver_id"]: c["position"] for c in classification}
    assert positions["EARLY"] == 5  # last of 5 total positions
    assert positions["LATE"] == 4   # second-to-last
    assert positions["F1"] == 1


def test_order_dnf_drivers_no_finishers_all_dnf():
    finishers = []
    dnfs = [
        {"driver_id": "A", "retired_at": 1},
        {"driver_id": "B", "retired_at": 2},
        {"driver_id": "C", "retired_at": 3},
    ]

    classification = order_dnf_drivers(finishers, dnfs)

    positions = {c["driver_id"]: c["position"] for c in classification}
    # earliest retiree (A) is last overall
    assert positions == {"A": 3, "B": 2, "C": 1}


def test_order_dnf_drivers_feeds_into_position_scoring():
    finishers = ["A", "B", "C"]
    dnfs = [
        {"driver_id": "LATE", "retired_at": 30},
        {"driver_id": "EARLY", "retired_at": 10},
    ]
    classification = order_dnf_drivers(finishers, dnfs)
    results = [{"position": c["position"], "driver_id": c["driver_id"]} for c in classification]

    # predicted EARLY to finish P4 (one off from actual P5) -> 1 point
    predictions = [{"position": 4, "driver_id": "EARLY"}]
    outcome = score_position_predictions(predictions, results)

    assert outcome["total"] == 1


# ---------------------------------------------------------------------------
# score_bonus_predictions
# ---------------------------------------------------------------------------

def test_all_bonus_types_correct_award_full_points():
    bonus_predictions = [
        {"bonus_type": "first_penalty", "driver_id": "VER"},
        {"bonus_type": "first_pit", "driver_id": "HAM"},
        {"bonus_type": "red_flag", "bool_value": True},
        {"bonus_type": "safety_car", "bool_value": False},
        {"bonus_type": "virtual_safety_car", "bool_value": True},
        {"bonus_type": "classified_finishers", "int_value": 18},
        {"bonus_type": "mvp", "driver_id": "NOR"},
        {"bonus_type": "fastest_lap", "driver_id": "LEC"},
    ]
    bonus_results = [
        {"bonus_type": "first_penalty", "driver_id": "VER"},
        {"bonus_type": "first_pit", "driver_id": "HAM"},
        {"bonus_type": "red_flag", "bool_value": True},
        {"bonus_type": "safety_car", "bool_value": False},
        {"bonus_type": "virtual_safety_car", "bool_value": True},
        {"bonus_type": "classified_finishers", "int_value": 18},
        {"bonus_type": "mvp", "driver_id": "NOR"},
        {"bonus_type": "fastest_lap", "driver_id": "LEC"},
    ]

    outcome = score_bonus_predictions(bonus_predictions, bonus_results)

    expected_total = sum(BONUS_POINTS.values())
    assert outcome["total"] == expected_total
    assert all(entry["correct"] for entry in outcome["breakdown"])


def test_all_bonus_types_incorrect_award_zero():
    bonus_predictions = [
        {"bonus_type": "first_penalty", "driver_id": "VER"},
        {"bonus_type": "first_pit", "driver_id": "HAM"},
        {"bonus_type": "red_flag", "bool_value": True},
        {"bonus_type": "safety_car", "bool_value": False},
        {"bonus_type": "virtual_safety_car", "bool_value": True},
        {"bonus_type": "classified_finishers", "int_value": 18},
        {"bonus_type": "mvp", "driver_id": "NOR"},
        {"bonus_type": "fastest_lap", "driver_id": "LEC"},
    ]
    bonus_results = [
        {"bonus_type": "first_penalty", "driver_id": "PIA"},
        {"bonus_type": "first_pit", "driver_id": "LEC"},
        {"bonus_type": "red_flag", "bool_value": False},
        {"bonus_type": "safety_car", "bool_value": True},
        {"bonus_type": "virtual_safety_car", "bool_value": False},
        {"bonus_type": "classified_finishers", "int_value": 17},
        {"bonus_type": "mvp", "driver_id": "VER"},
        {"bonus_type": "fastest_lap", "driver_id": "HAM"},
    ]

    outcome = score_bonus_predictions(bonus_predictions, bonus_results)

    assert outcome["total"] == 0
    assert all(not entry["correct"] for entry in outcome["breakdown"])


def test_classified_finishers_no_partial_credit_for_close_guess():
    bonus_predictions = [{"bonus_type": "classified_finishers", "int_value": 17}]
    bonus_results = [{"bonus_type": "classified_finishers", "int_value": 18}]

    outcome = score_bonus_predictions(bonus_predictions, bonus_results)

    assert outcome["total"] == 0


def test_bonus_prediction_missing_result_scores_zero():
    bonus_predictions = [{"bonus_type": "mvp", "driver_id": "NOR"}]

    outcome = score_bonus_predictions(bonus_predictions, [])

    assert outcome["total"] == 0
    assert outcome["breakdown"][0]["correct"] is False


def test_empty_bonus_predictions_scores_zero():
    outcome = score_bonus_predictions([], [{"bonus_type": "mvp", "driver_id": "NOR"}])

    assert outcome["total"] == 0
    assert outcome["breakdown"] == []
