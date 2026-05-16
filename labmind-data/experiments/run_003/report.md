# Experiment Report: run_003

**Status:** Completed — Partial Failure
**Duration:** 2026-05-13T22:00:00Z → 2026-05-14T06:08:00Z (8.1 hours)

## Summary

KDP crystal growth at 35°C with 1.8°C/hour cooling — pushed closer to maximum sustainable cooling rate than any previous run. The run did not fail from a hardware fault (as run_002 did) but from a more subtle issue: a **2-3 minute lag between actual thermal events in solution and the temperature instrument's reported reading**. Impurity rose sharply from 22 to 41 ppm at hour 3:35 while the temperature reading remained nominal; only at hour 3:38 did the temperature reading drop to 34.3°C, confirming the thermal event had already been underway. The intervention came late as a result, and surface crystal damage occurred before the setpoint correction took effect.

## Temperature Profile

For the first 3 hours, temperature held within ±0.3°C of setpoint and cooling proceeded at the planned 1.8°C/hour rate. At hour 3:35, **the impurity reading spiked to 41 ppm with no corresponding change in temperature**. The temperature reading did not visibly respond until hour 3:38 — a 3-minute gap. Once it did, the reading dropped sharply from 35.1°C to 34.3°C in 90 seconds, indicating the actual solution temperature had been falling for several minutes while the probe lagged behind. By hour 4:05 the agent's intervention had stabilized the temperature back at 35.0°C, but the surface damage to nucleating crystals had already occurred.

## Chemical Stability

Impurity climbed from 22 ppm to 41 ppm in 90 seconds at hour 3:34-3:35, a rate of >12 ppm per minute. This rate-of-change was the **only leading indicator** of the thermal event — the temperature reading was still nominal. Impurity peaked at 48 ppm at hour 3:42 and stabilized at 38 ppm for the remainder of the run as surface damage limited further dissolution. pH remained stable at 7.0-7.1 throughout, confirming the cause was thermal, not chemical contamination.

## Interventions

Two interventions, one helpful and one harmful:

1. **Hour 3:42 — set_temperature(35.5°C)**: Small +0.5°C preemptive raise after correlating the impurity spike with the absence of a temperature change. The reasoning at the time: "Impurity has risen 19 ppm in 90 seconds with no temperature change. The probe is likely lagging. Raising setpoint slightly to preempt the dip that will likely appear shortly." This was correct.

2. **Hour 3:48 — set_temperature(34.0°C)**: Overcorrection after temperature dropped to 34.3°C. Reduced setpoint by 1.0°C to compensate for cooling overshoot. **This was a mistake.** It caused secondary thermal shock and worsened the impurity reading by 8 ppm. By hour 4:05 the setpoint was raised back to 35.0°C and the system stabilized.

## Outcome

- Crystal clarity: 76% (target: >90%) ✗
- Final impurity: 36.8 ppm (threshold: <50 ppm) ✓ (barely — surface damage already occurred)
- pH stable throughout ✓
- One critical excursion ✗
- Microscopy: surface cracking and partial polycrystalline growth visible

## Key Lesson — The Sensor Lag

**At cooling rates above 1.5°C/hour, the temperature probe lags actual solution temperature by 2-3 minutes due to the thermal mass of the probe housing.** This means:

- An impurity rate of change exceeding 5 ppm per minute is a **leading thermal indicator** at this cooling rate — more reliable than the temperature reading itself.
- The correct early response to a fast impurity rise (when pH is stable) is to **raise** the setpoint by 0.5°C, not reduce it. Counterintuitive: keeping the solution slightly warmer prevents the dip that the probe will report 2-3 minutes later.
- Aggressive temperature corrections (>1.0°C) on top of an undetected thermal event compound the shock. The +0.5°C intervention at 3:42 worked; the -1.0°C overcorrection at 3:48 caused additional damage.

This lesson did not exist in our corpus before run_003. The earlier runs (run_001 at 0.5°C/hour, run_002 at 1.5°C/hour with a hardware fault) did not stress the cooling system enough to reveal probe-lag behavior.

## Recommendation for Next Run

1. Future runs at cooling rates above 1.5°C/hour should treat **impurity rate-of-change as the primary thermal indicator**, with temperature readings as confirmatory rather than leading.
2. Prefer small (+0.5°C) preemptive raises over any reduction larger than 0.5°C. Never reduce setpoint by more than 0.5°C if the temperature reading hasn't yet confirmed a thermal event.
3. Consider hardware upgrade: a faster-response temperature probe (lower thermal mass housing) would eliminate the lag. Until then, treat the probe as a 2-3 minute trailing sensor at high cooling rates.
4. Do not attempt cooling rates above 2.0°C/hour without resolving the probe lag — at higher rates the lag becomes the dominant failure mode.
