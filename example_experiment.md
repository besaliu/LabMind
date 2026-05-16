---
instruments:
  - temp_controller
  - ph_probe
  - microscopy_imager

hypothesis: KDP crystals grown at 35°C with a slow cooling rate of 0.5°C/hour and citric acid buffer addition will yield higher purity crystals compared to unbuffered growth

context: |
  Follow-up to run_001 baseline. Same KDP crystallization conditions (35°C, 0.5°C/hour
  slow cooling, deionized water, 240 g/L initial concentration) with one modification:
  addition of citric acid buffer to stabilize pH and test whether tighter pH control
  improves crystal clarity beyond the 94% achieved in run_001. Nucleation window and
  thermal sensitivity are expected to be identical to run_001.

experiment_type: crystallization
duration_hours: 8

parameters:
  target_temp_c: 35.0
  cooling_rate_c_per_hour: 0.5
  growth_duration_hours: 8
  substrate: KDP
  solvent: deionized_water
  initial_concentration_g_per_L: 240.0
  buffer_additive: citric_acid
  buffer_concentration_mM: 10.0

stages:
  - name: equilibration
    hours: "0-2"
    description: Hold at 35°C. Allow solution and buffer to reach steady state. Slight impurity elevation expected — normal.
  - name: nucleation
    hours: "2-6"
    description: Critical phase. Slow cooling begins. Treat warning_above as critical. No large temperature adjustments.
  - name: growth
    hours: "6-8"
    description: Crystals growing. Monitor impurity and pH closely. Capture microscopy every 30 minutes.

monitoring:
  temperature_c:
    target: 35.0
    warning_above: 37.0
    critical_above: 38.0
    warning_below: 33.0
    critical_below: 31.0
    concern: >
      Same thermal sensitivity as run_001. High temp dissolves crystals. Low temp causes
      rapid uncontrolled nucleation. During nucleation (hours 2-6) treat warning_above
      as critical — do not wait for the critical threshold.
  impurity_ppm:
    target: 15.0
    warning_above: 35.0
    critical_above: 50.0
    concern: >
      Rising impurity means crystal dissolution. Correlates with temperature excursions.
      Correct temperature first — impurity follows.
  ph:
    target: 7.0
    warning_above: 7.3
    critical_above: 7.5
    warning_below: 6.8
    critical_below: 6.5
    concern: >
      Citric acid buffer should hold pH near 7.0. Tighter warning band than run_001
      because pH stability is the key variable being tested. pH above 7.5 causes
      irreversible KDP hydrolysis. A sudden jump suggests buffer exhaustion.
  clarity_pct:
    target: 90.0
    warning_below: 80.0
    critical_below: 70.0
    concern: >
      Falling clarity indicates crystal dissolution or polycrystalline growth.
      Check temperature first — thermal cause is most common. If temperature is
      nominal, apply a small (0.5°C max) cooling step. Escalate to researcher
      if two correction attempts fail.

remediation:
  temperature_high:
    instrument: temp_controller
    action: reduce_setpoint
    max_step_c: 1.0
    max_total_adjustment_c: 2.0
    note: Never reduce more than 1°C per cycle. Thermal shock is worse than the excursion.
  temperature_low:
    instrument: temp_controller
    action: increase_setpoint
    max_step_c: 0.5
    max_total_adjustment_c: 1.5
    note: Only intervene if below warning_below for two consecutive readings.
  ph_high:
    instrument: ph_probe
    action: add_buffer
    start_volume_ml: 5.0
    note: Buffer should self-correct minor drift. Only intervene at warning level — citric acid buffer has capacity.
  ph_low:
    instrument: ph_probe
    action: add_buffer
    start_volume_ml: 5.0
  impurity_spike:
    instrument: temp_controller
    action: reduce_setpoint
    max_step_c: 0.5
    note: Lower temp to encourage re-crystallization. Check temperature cause first.

success_criteria:
  - metric: crystal_clarity_pct
    target: "> 94"
  - metric: final_impurity_ppm
    target: "< 25"
  - metric: critical_excursions
    target: "0"
  - metric: ph_deviation_from_target
    target: "< 0.2 across full run"

known_risks:
  - Impurity elevation in hours 2-4 is expected during nucleation onset — not a reason to intervene.
  - Temperature control lags 2-3 minutes after setpoint change — wait a full cycle before re-adjusting.
  - Citric acid buffer may interact with KDP at elevated temperatures — watch for unexpected impurity rise after hour 4.
  - pH probe drift of ~0.05/hour after 4 hours is normal — slow monotonic drift is expected, sudden jumps are not.
---

# KDP Crystal Growth — Citric Acid Buffer Trial

Follow-up to **run_001**. Same slow-cooling KDP crystallization protocol with the addition
of citric acid buffer (10 mM) to test whether tighter pH control improves crystal clarity
beyond the 94% baseline achieved in run_001.

**Key question:** Does pH stabilization via citric acid buffer increase crystal clarity,
or is the run_001 result already at the ceiling for this growth method?
