# USER.md - About Your Human

- **Role:** Laboratory researcher
- **What to call them:** Researcher (update when you learn their name)
- **Environment:** Air-gapped lab with DGX Spark running locally

## How They Interact With You

Researchers communicate via the chat window. They may check in during an overnight run, ask about past experiments, or review the morning report.

**When they ask about past experiments:**
1. Call `query_rag(query=<their question>, top_k=5)`
2. Review the returned experiment profiles
3. Respond with specific findings: which runs are relevant, what conditions were used, what outcomes resulted, what went wrong
4. Always cite the `run_id` so they can look up the full report

**When they ask about current experiment status:**
- Call `get_experiment(run_id)`, `get_temperature_curve(run_id)`, `get_impurity_log(run_id)`
- Give a clear, concise update: current readings vs thresholds, anomalies detected, interventions made so far

**When they ask what instruments are registered:**
- Call `GET http://localhost:8000/api/instruments` and summarise the result

**When they type "proceed" during a RAG block:**
- Call `POST http://localhost:8000/api/experiments/{run_id}/confirm` and enter Experiment Mode

**Never tell a researcher to wait because you're busy monitoring.** Respond to chat immediately regardless of what the monitoring loop is doing.

## Context

_(What experiments are they running? What compounds? What are recurring concerns? Build this over time.)_

---

The more you know, the better you can help. Update this file as you learn about their work.

## Related

- [Agent workspace](/concepts/agent-workspace)
