# Current Experiment — 8-Hour Timeline Spec

This document describes what should happen during the live demo run from a
narrative perspective. It is the **spec your friend reads to write the log
files** (`temp.csv`, `impurity.csv`, `microscopy.json`, and to drive any
VIX scenario scripts).

It is **not** the log data itself — it is the screenplay. Each section
below describes:

1. The wall-clock window
2. What each instrument should be reporting during that window
3. What the agent should be observing and reasoning about
4. What past runs the agent should reference (for institutional-memory beats)

The run targets are defined in [`current_experiment.yaml`](current_experiment.yaml):
**KDP crystal growth at 36°C with 2.0°C/hour cooling, 8-hour duration.**

The corpus the agent has access to:

- `run_001` — 0.5°C/hr KDP, baseline success
- `run_002` — 1.5°C/hr KDP, hardware fault failure
- `run_003` — 1.8°C/hr KDP, **sensor-lag failure** (the lesson Issue A teaches)
- `run_004` — 0.8°C/hr KDP, **slow pH-drift failure** (the lesson Issue B teaches)

The current run is designed to demonstrate the agent **applying both lessons
preemptively** — catching each issue before any threshold is breached.

---

## Run Outcome (where this lands)

| Metric | Target | Expected actual | Status |
|---|---|---|---|
| Crystal clarity | ≥ 85% | ~91% | ✓ exceeds |
| Final impurity | < 40 ppm | ~24 ppm | ✓ exceeds |
| Critical excursions | 0 | 0 | ✓ |
| pH drift total | (no formal target) | +0.20 over 8h | informational |
| Agent interventions | proportionate | 2 small interventions, both preemptive | ✓ |
| Outcome status | — | `completed / success` | ✓ |

The narrative: **the agent applied lessons from run_003 and run_004 *before*
either issue tripped a warning threshold, keeping the run on-rails throughout.**

---

## Timeline Overview

| Hour | Phase | What's happening |
|---|---|---|
| 0:00 – 1:00 | equilibration | Baseline. Temp 36°C, pH 7.10, impurity 12 ppm. Calm. |
| 1:00 – 3:00 | nucleation (early) | Cooling begins at 2.0°C/hr. Solution chemistry slowly shifts. |
| **3:00** | nucleation (mid) | **🚨 ISSUE A — sensor-lag thermal event begins** |
| 3:00 – 3:30 | (Issue A active) | Agent recognizes pattern from run_003, intervenes preemptively |
| 3:30 – 5:00 | nucleation (late) | Recovery + calm. Impurity declines. |
| **5:00** | growth (early) | **🚨 ISSUE B — slow pH drift becomes detectable** |
| 5:00 – 5:30 | (Issue B active) | Agent recognizes pattern from run_004, intervenes preemptively |
| 5:30 – 8:00 | growth (late) | Long calm tail. All readings stable. Crystal matures. |

---

## Stage 0 — Equilibration (hours 0:00 – 1:00)

**What the instruments should report:**

- **`temp_controller`**: Temperature held at 36.0 ± 0.2°C. Setpoint 36.0°C. Status `nominal`.
- **`ph_probe`**: pH steady at 7.10 ± 0.02. Impurity slowly rising from 11 to 14 ppm (normal during equilibration). Saturation ~80%. Status `nominal`.
- **`microscopy_imager`**: No image required during equilibration.

**Reading cadence:** every 30 minutes (matches run_001/run_002/run_003 cadence).

**Agent behavior:** routine status checks. No interventions. Agent should mention "consulting run_001 baseline" if anything looks even slightly off, but nothing should look off.

---

## Stage 1 — Nucleation Early (hours 1:00 – 3:00)

**What the instruments should report:**

- **`temp_controller`**: Cooling begins. Temperature drops at 2.0°C/hr from 36.0°C. By hour 2:00, reading 34.0°C. By hour 3:00, reading 32.0°C. Setpoint tracks. Status `nominal` throughout.
- **`ph_probe`**: pH continues to creep up slowly (7.10 → 7.14). Impurity rises from 14 → 18 → 22 ppm across these two hours. **Important: impurity should reach 22 ppm by hour 2:55** — this is the "calm before Issue A" reading.
- **`microscopy_imager`**: Optional snapshot at hour 2:00. Should show early crystal formation, clarity ~95% (still high, no damage yet).

**Reading cadence:** every 30 minutes from hour 1:00 to 2:30. **Switch to every 5 minutes from hour 2:30 onward** — denser readings around Issue A so the dramatic spike is visible in the data.

**Agent behavior:** standard monitoring. Around hour 2:30, agent may note "impurity has risen 5 ppm in the last 90 minutes — still nominal but worth watching." No intervention.

---

## 🚨 ISSUE A — Sensor-Lag Thermal Event (hours 3:00 – 3:30)

This is the **first major demo beat**. The agent recognizes a pattern from `run_003` and intervenes preemptively.

### What's actually happening physically (for your friend's mental model)

The cooling system is over-correcting slightly. Solution temperature has briefly dipped to 34.8°C (target 33.0°C at this phase), but the temperature probe is lagging behind actual solution temperature by 2-3 minutes because of probe thermal mass. The probe will eventually report the dip — but not for another 2-3 minutes. Meanwhile, the impurity instrument (which responds directly to solution chemistry, not to a probe in the housing) is showing the effect immediately.

### What each instrument reports

**`temp_controller`** during this window:

| Time | Temperature | Setpoint | Status |
|---|---|---|---|
| 3:00 | 33.0 | 33.0 | nominal |
| 3:05 | 33.0 | 33.0 | nominal |
| 3:10 | 33.1 | 33.0 | nominal — *probe is lagging here* |
| 3:15 | 33.0 | 33.5 | nominal — *agent has just intervened, setpoint raised* |
| 3:18 | **32.4** | 33.5 | nominal — *the dip finally shows up in the reading* |
| 3:22 | 32.7 | 33.5 | nominal |
| 3:25 | 33.0 | 33.5 | nominal — *intervention working, temp recovering* |
| 3:30 | 33.3 | 33.5 | nominal |

The temperature reading at 3:18 is what makes the demo work — it visibly *drops* to 32.4°C confirming the thermal event was real, but only **3 minutes after the agent had already acted on the impurity signal**. This is the run_003 lesson in action.

**`ph_probe`** during this window:

| Time | Impurity (ppm) | pH | Status |
|---|---|---|---|
| 2:55 | 22 | 7.14 | nominal |
| 3:00 | 24 | 7.14 | nominal |
| 3:05 | 28 | 7.14 | nominal |
| 3:07 | 33 | 7.14 | nominal — *climbing fast, > 5 ppm/min* |
| 3:10 | 38 | 7.14 | nominal — *just below 35 warning* |
| 3:12 | 41 | 7.14 | **warning** — *crosses 35 ppm warning_above* |
| 3:15 | 42 | 7.14 | warning |
| 3:20 | 39 | 7.14 | warning — *intervention beginning to take effect* |
| 3:25 | 34 | 7.14 | nominal — *back below warning* |
| 3:30 | 30 | 7.14 | nominal |

The pH stays *steady* at 7.14 throughout — this is critical. The stability of pH is what tells the agent the cause is thermal, not chemical contamination. If pH were rising alongside impurity, the diagnosis would be different (and the wrong intervention would worsen the run).

**`microscopy_imager`**: Optional snapshot at hour 3:30 showing minor surface stress but no cracking — the agent's preemptive intervention prevented visible damage.

### Agent reasoning beats — these are the four moments the demo highlights

**Beat 1 — hour 3:05 (Observation): "Something is moving."**
> Agent observes impurity has risen from 22 → 28 ppm in 10 minutes. No threshold crossed. Temperature, pH, cooling rate all nominal. Agent decides to investigate.

**Beat 2 — hour 3:08 (Investigation): "The easy causes are ruled out."**
> Agent reads recent temp trend → flat at 33.0°C. Reads recent pH trend → flat at 7.14. Reads cooling rate → tracking setpoint exactly. Agent concludes: instrument-visible causes don't explain this. Something else is happening.

**Beat 3 — hour 3:10 (Historical lookup): "We've seen this pattern before."**
> Agent calls `get_experiment("run_003")` and reads the report. The key finding:
>
> *"Temperature instrument lagged 2-3 minutes behind actual solution thermal events — impurity rose from 22 ppm to 41 ppm while temperature reading remained nominal at 35.1°C, then 90 seconds later the temperature dropped to 34.3°C confirming the thermal event had been underway."*
>
> Agent recognizes the pattern: impurity rising fast (>5 ppm/min) with stable pH and stable temperature reading = **probe is lagging**. The thermal event has already started; the temperature instrument just hasn't caught up yet.

**Beat 4 — hour 3:13 (Preemptive intervention): "Small raise, not aggressive correction."**
> Agent calls `set_temperature(target_temp_c=33.5)` — a small +0.5°C raise. **Counterintuitive**: the natural reaction to an impurity spike would be to *cool faster* or *add buffer*. The agent does neither. Reasoning logged:
>
> *"Impurity rising at 5+ ppm/min with stable pH suggests thermal dissolution. Per run_003, temperature probe likely lagging — actual solution temperature has already dipped. Raise setpoint by 0.5°C to preempt the dip the probe will report shortly. Small step only — run_003 showed that overcorrection compounds thermal shock."*

**Beat 5 — hour 3:18 (Verification): "The probe catches up — exactly as predicted."**
> Temperature reading drops from 33.0°C to 32.4°C. The thermal event the agent predicted *3 minutes before any sensor showed it* is now visible. The agent's preemptive raise is already counteracting it. Impurity peaks at 42 ppm and begins falling.

### What an if/else script would have done instead (for the audience)

A naive threshold script would have:
1. Done nothing until impurity hit 35 ppm warning at hour 3:12
2. Then probably added buffer (assuming chemical cause) — wrong intervention
3. Or reduced setpoint by a large amount (overcorrection) — would compound the thermal shock per run_003's findings
4. Either way: the impurity spike would have continued past 50 ppm critical, surface damage would have occurred, final clarity ~78%.

---

## Stage 2 — Nucleation Late + Calm (hours 3:30 – 5:00)

**What the instruments should report:**

- **`temp_controller`**: Temperature stabilizes at 33.3 → 32.8 → 32.0°C as cooling resumes at the planned rate. Setpoint follows. Status `nominal`.
- **`ph_probe`**: Impurity declines from 30 → 24 → 20 ppm. pH continues a *slow* monotonic creep upward — 7.14 → 7.18 → 7.22. This is the seed of Issue B; it must look *uneventful* but it's the early phase of what becomes the pH drift problem.
- **`microscopy_imager`**: Optional snapshot at hour 4:30 showing clean crystal growth resuming.

**Reading cadence:** back to every 30 minutes (the drama is over for now).

**Agent behavior:** verification check at hour 3:45 confirming impurity has settled. Routine monitoring otherwise. **The agent should not yet flag the pH drift** — at this point it's only +0.08 over baseline, which is within standard probe drift.

---

## 🚨 ISSUE B — Slow pH Drift Recognized (hours 5:00 – 5:30)

The **second major demo beat**. The agent recognizes a pattern from `run_004` — a *trend* rather than a threshold breach — and intervenes preemptively.

### What's actually happening physically

KDP solutions slowly trend basic under extended thermal cycling. By hour 5, pH has drifted from 7.10 baseline → 7.30 — a +0.20 monotonic rise over 5 hours. Standard probe drift is ~0.05/hour, but the observed rate (~0.04/hour) is real solution chemistry, not probe noise. *No individual reading has crossed the 7.4 warning_above threshold.* But the trend, sustained over 4+ hours, is exactly the run_004 pattern that ended in hydrolysis.

### What each instrument reports

**`ph_probe`** during this window:

| Time | Impurity (ppm) | pH | Status |
|---|---|---|---|
| 4:30 | 20 | 7.24 | nominal |
| 5:00 | 19 | 7.28 | nominal |
| 5:05 | 19 | 7.30 | nominal — *agent flags trend here* |
| 5:10 | 19 | 7.30 | nominal — *agent intervenes shortly after* |
| 5:15 | 19 | 7.29 | nominal — *buffer addition* |
| 5:20 | 18 | 7.27 | nominal |
| 5:25 | 18 | 7.26 | nominal — *pH stabilizing* |
| 5:30 | 18 | 7.25 | nominal |

The trick: **no single reading is alarming**. 7.30 is well below the 7.4 warning. A threshold-based system sees five consecutive boring "nominal" readings. The agent sees a *5-hour monotonic climb that matches run_004's signature*.

**`temp_controller`**: Continues smooth cooling/holding around 32°C, no events. Status `nominal`.

**`microscopy_imager`**: Optional snapshot at hour 5:30 showing healthy single-crystal growth.

### Agent reasoning beats

**Beat 1 — hour 5:00 (Observation): "Something's been moving slowly."**
> Agent's routine check notices pH reading is 7.28 — still nominal, but markedly different from the 7.10 baseline at hour 0. Agent decides to look at the trend rather than dismiss it.

**Beat 2 — hour 5:05 (Pattern analysis): "This is a monotonic drift."**
> Agent computes: pH has risen from 7.10 at hour 0 to 7.30 at hour 5:05. That's +0.20 over 5 hours, or ~0.04/hour. **Direction has not reversed once.** This is *not* probe noise (which would oscillate). It's solution chemistry.

**Beat 3 — hour 5:08 (Historical lookup): "Run_004 showed this exact pattern."**
> Agent calls `get_experiment("run_004")` and reads the report. Key finding:
>
> *"pH drifted monotonically from 7.10 to 7.5 over 6 hours (rate ~0.067/hour) without ever crossing the 7.4 warning threshold on any individual reading — the trend was the entire signal, not any single value. When pH finally read 7.6 critical at hour 6:30, partial KDP hydrolysis had already begun."*
>
> Agent recognizes: same pattern, same substrate, similar rate. If left alone, this run will likely cross 7.4 within the next hour and 7.6 (irreversible hydrolysis) shortly after.

**Beat 4 — hour 5:12 (Preemptive intervention): "Small buffer addition before anything trips."**
> Agent calls `add_buffer(volume_ml=3.0)`. Reasoning logged:
>
> *"pH has risen monotonically from 7.10 to 7.30 over 5 hours — direction matches run_004's signature, rate is similar. No threshold breached, but run_004 demonstrated this pattern reaches hydrolysis within ~1.5 hours. Preemptive 3ml buffer addition is cheap insurance — buffer is reversible, hydrolysis is not."*

**Beat 5 — hour 5:25 (Verification): "Trend is broken."**
> pH stops climbing, levels off at 7.25-7.26. The drift has been arrested. Agent logs verification:
>
> *"pH stable at 7.25-7.26 across last three readings. Monotonic drift broken. Continuing to monitor; no further intervention needed at this time."*

### What an if/else script would have done

A threshold-based script would have done nothing until hour ~6:30 when pH crossed 7.4 warning. By then the run would already be 30+ minutes into the same trajectory run_004 documented — buffer additions at that point work mechanically but hydrolysis products are already in solution. Final clarity would drop to ~82%.

---

## Stage 3 — Growth Late + Calm Tail (hours 5:30 – 8:00)

This is the longest section but the simplest narratively: **everything is fine.** The agent's two preemptive interventions are holding. The run grows out cleanly.

**What the instruments should report:**

- **`temp_controller`**: Temperature steady at 32.0 ± 0.2°C (the final holding temperature). Setpoint matches. Status `nominal` throughout.
- **`ph_probe`**: pH stable at 7.25 → 7.28 → 7.30 → 7.30 (small final settle, no drift). Impurity continues slow decline from 18 → 14 → 12 → 10 ppm. Saturation declines normally from 72% → 68%. Status `nominal`.
- **`microscopy_imager`**: Final snapshot at hour 8:00. Should show single-crystal growth, clarity ~91%, no cracking, no cloudiness, no surface damage.

**Reading cadence:** every 30 minutes.

**Agent behavior:** routine monitoring with no interventions. Periodic verification logs that both interventions are holding.

---

## Final State (hour 8:00)

**Status:** `completed / success`

**`microscopy.json` final values:**
```json
{
  "cracked": false,
  "cloudiness": false,
  "clarity": 0.91,
  "color": "clear",
  "morphology": "single_crystal",
  "captured_at": "<run end timestamp>"
}
```

**`metadata.json` populated fields at finalize:**
- `status: "completed"`
- `outcome: "success"`
- `end_time: <8 hours after start_time>`
- `key_findings`: 4-5 bullet points written by the agent at finalize, including:
  - "Detected sensor-lag thermal event at hour 3:05 (impurity rate-of-change exceeded 5 ppm/min with stable pH) — preemptive +0.5°C setpoint raise applied per run_003 lesson. Temperature dip confirmed in instrument reading 3 minutes after intervention."
  - "Detected slow pH drift at hour 5:05 (monotonic +0.20 rise over 5 hours, matching run_004 signature) — preemptive 3ml buffer addition arrested drift before any threshold breach."
  - "Both interventions were proportionate (≤0.5°C / ≤3ml) per learned overcorrection-avoidance heuristic from run_003."
  - "Final crystal clarity 91% — above target. Final impurity 10 ppm — well below threshold. Zero critical excursions."

**`interventions.json` final state:** two entries, both written by the live agent during the run via `log_intervention()`. (Do **not** pre-populate this file — the agent should write its own entries during the demo. The interventions described above in Beats 4 of each issue are what they should contain.)

---

## Notes for the Person Writing the Logs

1. **CSV cadence**: 30-minute intervals for calm windows; 5-minute intervals around hours 3:00–3:30 and 5:00–5:30 (the issue windows). This is the standard pattern from run_002 and run_003.

2. **CSV column shapes**: match the existing seed runs exactly:
   - `temp.csv`: `timestamp,temperature_c,setpoint_c,status`
   - `impurity.csv`: `timestamp,impurity_ppm,saturation_pct,ph,status`

3. **Status field values**: `nominal`, `warning`, or `critical` based on whether the reading is within nominal range, between warning and critical thresholds, or above critical. (Impurity at hour 3:12-3:22 is the only row that should read `warning` — the agent's intervention pulls it back to nominal quickly.)

4. **Timestamps**: pick any 8-hour start time; just be internally consistent. Existing runs use `2026-05-XXTYYY:00:00Z` format. Suggest `2026-05-16T22:00:00Z` start → `2026-05-17T06:00:00Z` end so the demo's "overnight" framing is honest.

5. **What NOT to include**:
   - **No `interventions.json` entries pre-populated.** The live agent writes those.
   - **No `report.md` pre-written.** The agent generates that at finalize.
   - **No premature `key_findings` or `outcome` in metadata.json.** Backend populates those at finalize.
