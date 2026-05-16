import json
import random
from pathlib import Path

import pytest

from vix.scenario import Scenario


@pytest.fixture
def spec_file(tmp_path: Path) -> Path:
    spec = {
        "thresholds": {
            "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
        },
        "baseline": {
            "readings": {
                "temperature_c": {"mean": 35.0, "noise": 0.1},
                "setpoint_c":    {"mean": 35.0, "noise": 0.0},
            },
        },
        "failure": {
            "readings": {
                "temperature_c": {"mean": 38.5, "noise": 0.2},
                "setpoint_c":    {"mean": 35.0, "noise": 0.0},
            },
        },
        "recovery": {
            "readings": {
                "temperature_c": {"mean": 35.5, "noise": 0.1},
                "setpoint_c":    {"mean": 34.0, "noise": 0.0},
            },
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    return p


def test_default_phase_is_baseline(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    assert s.current_phase == "baseline"


def test_thresholds_loaded(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    assert s.thresholds == {
        "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
    }


def test_sample_is_near_phase_mean(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    samples = [s.sample("temperature_c") for _ in range(50)]
    assert all(34.5 < x < 35.5 for x in samples)


def test_set_phase_switches_distribution(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    s.set_phase("failure")
    assert s.current_phase == "failure"
    samples = [s.sample("temperature_c") for _ in range(50)]
    assert all(38.0 < x < 39.0 for x in samples)


def test_zero_noise_is_exact(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    assert s.sample("setpoint_c") == 35.0


def test_unknown_phase_raises(spec_file: Path) -> None:
    s = Scenario(spec_file)
    with pytest.raises(ValueError):
        s.set_phase("explode")


def test_unknown_metric_raises(spec_file: Path) -> None:
    s = Scenario(spec_file)
    with pytest.raises(KeyError):
        s.sample("not_a_metric")


def test_missing_baseline_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"failure": {"readings": {}}}))
    with pytest.raises(ValueError):
        Scenario(bad)
