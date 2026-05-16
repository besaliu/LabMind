"""key_differences computation tests.

These are pure-function tests — no Chroma, no Ollama. They prove the
deterministic diff produces meaningful, ordered output for the cases
the upload UI cares about.
"""
from __future__ import annotations

from rag.diff import compute_key_differences

HIT_META = {
    "substrate": "KDP",
    "target_temp_c": 35.0,
    "cooling_rate_c_per_hour": 0.5,
    "growth_duration_hours": 8.0,
    "instruments": "temp_controller|ph_probe|microscopy_imager",
}
HIT_TEXT = "Microscopy observations: cracked, clarity_high"


def _query(target_temp=35.0, cooling_rate=0.5, duration=8.0, substrate="KDP",
           instruments=("temp_controller", "ph_probe", "microscopy_imager"),
           microscopy="none"):
    return (
        "Hypothesis: test\n"
        f"Instruments: {', '.join(instruments)}\n"
        f"Parameters: target_temp={target_temp}C, cooling_rate={cooling_rate}C/hr, "
        f"growth_duration={duration}h, substrate={substrate}\n"
        f"Microscopy observations: {microscopy}\n"
    )


def test_identical_query_has_no_diffs():
    diffs = compute_key_differences(_query(), HIT_META, HIT_TEXT)
    assert diffs == []


def test_temperature_setpoint_delta():
    diffs = compute_key_differences(_query(target_temp=38.0), HIT_META, HIT_TEXT)
    assert any("temperature setpoint differs by 3.0°C" in d for d in diffs)


def test_substrate_change_is_highest_salience():
    """Substrate diff should come first when multiple diffs exist."""
    diffs = compute_key_differences(
        _query(substrate="KCl", target_temp=38.0, cooling_rate=1.5),
        HIT_META,
        HIT_TEXT,
    )
    assert diffs[0].startswith("different substrate")


def test_cooling_rate_delta_below_tolerance_ignored():
    diffs = compute_key_differences(_query(cooling_rate=0.55), HIT_META, HIT_TEXT)
    assert not any("cooling rate" in d for d in diffs)


def test_duration_shorter_vs_longer():
    short = compute_key_differences(_query(duration=4.0), HIT_META, HIT_TEXT)
    assert any("shorter growth window" in d for d in short)
    long = compute_key_differences(_query(duration=12.0), HIT_META, HIT_TEXT)
    assert any("longer growth window" in d for d in long)


def test_diff_capped_at_max():
    """Even with many differences, output is capped at MAX_DIFFS=3."""
    diffs = compute_key_differences(
        _query(substrate="KCl", target_temp=42.0, cooling_rate=2.0, duration=2.0),
        HIT_META,
        HIT_TEXT,
    )
    assert len(diffs) <= 3


def test_empty_query_text_falls_back_to_hit_description():
    """Empty query is just the limit case of "unparseable" — fallback fires."""
    diffs = compute_key_differences("", HIT_META, HIT_TEXT)
    assert diffs  # non-empty
    assert any("matched run" in d for d in diffs)


def test_unparseable_query_falls_back_to_descriptive_hit_info():
    """If query has no parseable fields, output describes the hit."""
    diffs = compute_key_differences("totally freeform query text", HIT_META, HIT_TEXT)
    # Should still produce something useful from the hit metadata.
    assert any("matched run" in d for d in diffs)
