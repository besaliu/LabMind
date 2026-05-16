# Anomaly Detection — Run this loop every 60 seconds while in Experiment Mode.
# Check faster (30s) if an anomaly was recently detected.

## Step 1 — Fetch current readings and experiment context

Call in parallel:
- `get_temperature_curve(run_id)` — focus on the last 3-5 rows
- `get_impurity_log(run_id)` — focus on the last 3-5 rows
- `get_experiment(run_id)` — read `monitoring`, `remediation`, `stages`, and `known_risks`

## Step 2 — Determine current stage

Calculate elapsed hours from `metadata.start_time` to now. Match against `metadata.stages`. Read the stage `description` — it tells you how strictly to apply thresholds in this phase.

## Step 3 — Check readings against thresholds

| Condition | Status | Action |
|-----------|--------|--------|
| Reading within warning bounds | **Nominal** | Log nothing, continue loop |
| Reading outside warning but within critical | **Warning** | Note it, check `known_risks`, re-check next cycle |
| Warning persists 2+ consecutive readings | **Anomaly** | Go to Step 4 |
| Reading at or beyond critical | **Anomaly** | Go to Step 4 immediately |

Before escalating: check `metadata.known_risks`. If the reading matches expected behavior (e.g. "impurity elevation during hours 2-4 is normal"), note it in stream output but do not intervene.

## Step 4 — Root cause analysis

Before acting:
1. **How many instruments are affected?** Multiple simultaneous anomalies = systemic issue. Alert researcher, don't act on individual instruments.
2. **What does `metadata.monitoring.{param}.concern` say?** Explains scientific consequence and correlations.
3. **Drift or spike?** Check last 5 rows. Gradual drift = control issue. Sudden jump = fault or external event.
4. **Compare to history:** Call `compare_runs(run_id, <most_similar_past_run_id>)`.

## Step 5 — Remediate using the experiment's remediation plan

Read `metadata.remediation` for the correct action. Respect:
- `max_step_c` — never exceed in a single cycle
- `max_total_adjustment_c` — cumulative limit across all interventions this run
- `start_volume_ml` — always start here for buffer additions
- `note` — experiment-specific constraints; follow them

Always pair every instrument call with `log_intervention`:
```
log_intervention(
  run_id=<run_id>,
  action="<tool_called>(<params>)",
  reasoning="<2-3 sentences: reading observed, stage context, root cause, why this action>"
)
```

Stream a concise summary to chat: what was observed, current stage, action taken, what to watch next cycle.

## Step 6 — Verify remediation

Next cycle: check whether the parameter returned toward target. If anomaly persists after 2 correction attempts:

```
⚠️ {instrument} remains anomalous after 2 correction attempts.
Current reading: {value}. Stage: {stage_name}. Manual inspection may be required.
```

Then continue monitoring without further automated corrections for that instrument.

## Related

- [Heartbeat config](/gateway/config-agents)
