import pytest

from vix.status import compute_status

T = {
    "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
    "ph":            {"nominal": [6.8, 7.4],   "warning": [6.5, 7.6]},
}


def test_nominal_when_all_inside_nominal() -> None:
    assert compute_status({"temperature_c": 35.0, "ph": 7.0}, T) == "nominal"


def test_warning_when_one_metric_in_warning_band() -> None:
    assert compute_status({"temperature_c": 36.5, "ph": 7.0}, T) == "warning"


def test_critical_when_one_metric_outside_warning() -> None:
    assert compute_status({"temperature_c": 38.5, "ph": 7.0}, T) == "critical"


def test_critical_below_warning_band() -> None:
    assert compute_status({"temperature_c": 30.0, "ph": 7.0}, T) == "critical"


def test_worst_metric_wins() -> None:
    assert compute_status({"temperature_c": 36.5, "ph": 5.0}, T) == "critical"


def test_unknown_metrics_ignored() -> None:
    assert compute_status({"random_metric": 9999, "temperature_c": 35.0}, T) == "nominal"


def test_empty_readings_is_nominal() -> None:
    assert compute_status({}, T) == "nominal"


def test_inclusive_bounds_on_nominal() -> None:
    assert compute_status({"temperature_c": 34.0}, T) == "nominal"
    assert compute_status({"temperature_c": 36.0}, T) == "nominal"


def test_inclusive_bounds_on_warning() -> None:
    assert compute_status({"temperature_c": 33.0}, T) == "warning"
    assert compute_status({"temperature_c": 37.0}, T) == "warning"


def test_non_numeric_reading_ignored() -> None:
    assert compute_status({"image_b64": "AAAA", "temperature_c": 35.0}, T) == "nominal"
