---
run_id: run_002
experiment_type: crystallization
substrate: KDP
target_temp_c: 35.0
cooling_rate_c_per_hour: 1.5
buffer_additive: null
outcome: partial_failure
key_findings:
  - Temperature spike at hour 3 (40.1°C) caused by cooling system fault during nucleation — exceeded critical threshold
  - Agent intervened: reduced setpoint to 32°C; temperature recovered within 8 minutes but crystal damage already occurred
  - Final impurity 61.4 ppm above 30 ppm target — thermal shock dissolved partially-formed crystals
  - Crystal clarity 71% — below 90% target; polycrystalline growth observed in microscopy image
  - Faster cooling rate (1.5°C/hour) not recommended for KDP — nucleation window too narrow to tolerate excursions
---

# Experiment Report: run_002

**Status:** Completed — Partial Failure
**Duration:** 2026-05-12T22:00:00Z → 2026-05-13T06:15:00Z (8.25 hours)

## Summary

KDP crystal growth at 35°C with accelerated cooling rate (1.5°C/hour) resulted in a critical temperature excursion at hour 3 caused by a cooling system fault. LabMind detected the anomaly and intervened, preventing total run failure. However, thermal shock caused elevated impurity levels and reduced crystal clarity. This run demonstrates that 1.5°C/hour cooling is not suitable for KDP and that the cooling system requires inspection before the next run.

## Temperature Profile

Temperature held stable for the first 3 hours, then rapidly climbed to 40.1°C — 5.1°C above the critical threshold — due to a cooling system fault. LabMind intervened at 01:32 by reducing the setpoint to 32°C. Temperature returned to nominal by 02:00 (28 minutes after intervention).

## Chemical Stability

Impurity spiked to 78.2 ppm during the temperature excursion — well above the 50 ppm threshold — as thermal shock dissolved crystal surface layers back into solution. Impurity did not return to nominal levels; it stabilized at ~36 ppm (warning range) for the remainder of the run. pH dropped to 6.0 at peak thermal stress, recovering to 7.1 by run end.

## Interventions

1 intervention at 01:32: temperature setpoint reduced from 33.0°C to 32.0°C to arrest runaway heating.

## Outcome

- Crystal clarity: 71% (target: >90%) ✗
- Final impurity: 36.2 ppm (threshold: <50 ppm) ✓ (barely)
- pH recovered to nominal ✓
- Thermal shock visible in microscopy: surface cracking and cloudiness present

## Recommendation for Next Run

1. Inspect and service the cooling system before the next run — the fault at hour 3 is likely mechanical
2. Return to the validated 0.5°C/hour cooling rate (see run_001)
3. Do not attempt 1.5°C/hour cooling with KDP until the cooling system is verified
4. Consider adding a cooling system health check as a pre-experiment step
