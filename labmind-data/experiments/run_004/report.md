# Experiment Report: run_004

**Status:** Completed — Partial Failure
**Duration:** 2026-05-14T22:00:00Z → 2026-05-15T08:12:00Z (10.2 hours)

## Summary

Long-duration KDP crystal growth at 35°C with conservative 0.8°C/hour cooling — designed to be uneventful. Temperature held nominal the entire run. The failure came from an entirely different direction: **the pH probe drifted monotonically from 7.1 to 7.5 over six hours without ever crossing a warning threshold on any individual reading**. By the time pH finally read 7.6 (critical_above) at hour 6:30, partial KDP hydrolysis had already begun — and KDP hydrolysis is irreversible. Buffer addition brought the pH reading back down but could not undo the chemistry damage already done. Final crystal clarity 81%, entirely due to dissolved hydrolysis products in solution.

## Temperature Profile

Uneventful. Temperature held within ±0.2°C of setpoint for the entire 10-hour run. Cooling proceeded at the planned 0.8°C/hour rate from hour 2 to hour 8. No interventions needed.

## Chemical Stability

This is where the run failed, and in a way no prior run had revealed.

- **Hour 0:** pH 7.10, impurity 11.8 ppm. Nominal.
- **Hour 2:** pH 7.18, impurity 14.2 ppm. Nominal. (drift = +0.08)
- **Hour 4:** pH 7.28, impurity 17.6 ppm. Nominal. (drift = +0.18, still below 7.4 warning)
- **Hour 5:** pH 7.34, impurity 19.4 ppm. **Nominal — but pH has risen 0.24 in 5 hours, monotonically.**
- **Hour 6:** pH 7.42. Warning_above (7.4) finally crossed.
- **Hour 6:30:** pH 7.58. **Critical_above (7.6) effectively crossed.** Hydrolysis products detected.
- **Hour 6:35:** Buffer added (5ml). pH begins falling.
- **Hour 7:30:** pH 7.32. Recovered to nominal range.
- **Hour 10:** pH 7.18. Stable, but solution permanently contaminated with hydrolysis products.

Impurity climbed in parallel with pH (because dissolved phosphate is part of the impurity reading), peaking at 38 ppm at hour 6:30. After buffer intervention, impurity declined slowly to 26 ppm by run end — within target, but the crystal had already grown in contaminated solution for part of the critical nucleation window.

## Interventions

One intervention, too late:

**Hour 6:35 — add_buffer(5ml then 3ml)**: pH had crossed 7.6 critical at hour 6:30. Added 5ml buffer, waited 60s, re-read at 7.49, added 3ml more, re-read at 7.41. By hour 7:30 pH was 7.32. The intervention worked mechanically (pH came down), but the underlying issue had been developing for the prior 6 hours and hydrolysis had already begun in the 7.5+ region. The intervention should have happened at hour 5 when the drift trend was already visible (0.24 units in 5 hours, all in one direction). At that point a small (3ml) preemptive buffer addition would have arrested the drift before it reached the danger zone.

## Outcome

- Crystal clarity: 81% (target: >90%) ✗
- Final impurity: 26 ppm (threshold: <50 ppm) ✓
- pH drift: 0.48 over the run (target: <0.3) ✗
- One critical excursion ✗
- Microscopy: surface cloudiness from hydrolysis-derived contamination, no cracking, single-crystal morphology preserved

## Key Lesson — Slow Drifts Evade Thresholds

**A monotonic drift can damage a run without ever tripping a single threshold check.** This is the inverse of run_003's lesson:

- run_003 taught: **fast changes** matter before any threshold trips. Watch rate-of-change.
- run_004 teaches: **slow drifts** matter before any threshold trips. Watch direction and duration.

Together they imply a unified rule the agent should apply to all sensor readings: **threshold breaches are floors, not ceilings. The agent should intervene on:**

1. **Fast rate-of-change** in a leading indicator, even if no threshold is crossed (run_003).
2. **Slow monotonic trends over multi-hour windows**, even if no threshold is crossed (run_004).
3. **Actual threshold breaches** as the final fallback — but by the time these fire, damage may already be underway.

For pH specifically: a drift of >0.3 units over any 4-hour window warrants a preemptive 3ml buffer addition. This is cheap insurance — buffer is reversible (you can always add more, and the solution chemistry tolerates small additions well), while crossing the hydrolysis threshold is permanent.

For temperature: still defer to run_003's faster-response heuristics — impurity rate-of-change is the leading indicator at high cooling rates.

## Recommendation for Next Run

1. **Implement rolling-window trend analysis on pH.** A check every reading: "has pH moved in one direction for the past 4 hours by more than 0.3 units?" If yes, intervene with 3ml buffer regardless of absolute value.
2. **Do not run KDP experiments longer than 6 hours without active pH trend monitoring.** Short runs hide slow drifts; long runs amplify them.
3. **Consider a calibration check at hour 4 of any long run.** Some of the 0.067/hour drift rate may be probe drift rather than solution chemistry; a calibration check would discriminate. Standard probe drift is ~0.05/hour, so observed 0.067 suggests ~25% is real chemistry — small but real.
4. **Update the agent's monitoring policy**: pH and impurity should both be monitored on TWO axes — absolute thresholds (existing) AND rate-of-change / trend-direction (new).
