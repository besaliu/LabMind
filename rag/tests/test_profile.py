"""Profile builder tests against real seed data.

These are the keystone tests: they prove the deterministic template
produces stable, well-shaped output from production-realistic inputs.
"""
from __future__ import annotations

from rag.profile import build_profile


def test_build_profile_run_001(tmp_path, isolated_data_root):
    p = build_profile("run_001", isolated_data_root)
    assert p.run_id == "run_001"

    # Every locked field must appear in the embedded text.
    for prefix in (
        "Hypothesis:",
        "Instruments:",
        "Parameters:",
        "Success criteria:",
        "Status:",
        "Key findings:",
        "Risks:",
        "Temperature:",
        "Impurity:",
        "Microscopy:",
        "Interventions:",
        "Report:",
    ):
        assert prefix in p.text, f"missing line prefix: {prefix}"

    # run_001 has zero interventions — make sure the empty case renders cleanly.
    assert "Interventions: 0 total — none" in p.text

    # Chroma metadata must be flat (str/int/float/bool only).
    for key, value in p.metadata.items():
        assert isinstance(value, (str, int, float, bool)), (
            f"non-flat Chroma metadata at {key!r}: {type(value).__name__}"
        )

    # Substrate + params should match the seed metadata.
    assert p.metadata["substrate"] == "KDP"
    assert p.metadata["target_temp_c"] == 35.0
    assert p.metadata["status"] == "completed"
    assert p.metadata["outcome"] == "success"


def test_build_profile_run_002_has_intervention(isolated_data_root):
    p = build_profile("run_002", isolated_data_root)
    # run_002 had one intervention — make sure it appears in the text.
    assert "Interventions: 1 total — set_temperature" in p.text


def test_build_profile_is_deterministic(isolated_data_root):
    a = build_profile("run_001", isolated_data_root)
    b = build_profile("run_001", isolated_data_root)
    assert a.text == b.text
    assert a.summary == b.summary
    assert a.metadata == b.metadata


def test_build_profile_missing_run_raises(isolated_data_root):
    import pytest
    with pytest.raises(FileNotFoundError):
        build_profile("run_does_not_exist", isolated_data_root)


def test_microscopy_stats_from_csv(isolated_data_root):
    """microscopy.csv stats appear in the profile text."""
    run_dir = isolated_data_root / "experiments" / "run_001"
    micro_csv = run_dir / "microscopy.csv"
    micro_csv.write_text(
        "timestamp,clarity_pct,defect_count\n"
        "2026-05-11T00:00:00Z,92.0,0\n"
        "2026-05-11T00:30:00Z,93.0,1\n"
        "2026-05-11T01:00:00Z,94.0,0\n"
    )

    p = build_profile("run_001", isolated_data_root)
    assert "Microscopy:" in p.text
    assert "clarity_mean=" in p.text
    assert "clarity_min=" in p.text
    assert "peak_defects=" in p.text
    # clarity_min should be 92.0 from the rows above
    assert "clarity_min=92.0%" in p.text
    assert "peak_defects=1" in p.text


def test_microscopy_stats_missing_csv(isolated_data_root):
    """If microscopy.csv is absent the Microscopy line is omitted (no crash)."""
    run_dir = isolated_data_root / "experiments" / "run_001"
    csv_path = run_dir / "microscopy.csv"
    csv_path.unlink(missing_ok=True)

    p = build_profile("run_001", isolated_data_root)
    assert "Microscopy:" not in p.text


def test_temperature_stats_count_violations(isolated_data_root, tmp_path):
    """Out-of-threshold temperatures count toward violations."""
    run_dir = isolated_data_root / "experiments" / "run_001"
    # Append a hot reading that exceeds the 38C threshold.
    temp_path = run_dir / "temp.csv"
    with temp_path.open("a") as f:
        f.write("2026-05-11T06:30:00Z,39.5,35.0,critical\n")

    p = build_profile("run_001", isolated_data_root)
    assert "threshold_violations=1" in p.text
