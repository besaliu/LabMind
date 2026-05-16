import type { BundleResponse } from "../types/bundle";
import { fmtDateTime } from "../lib/time";

interface Props {
  bundle: BundleResponse;
}

export function SpecHeader({ bundle }: Props) {
  const m = bundle.metadata;
  const p = m.parameters as Record<string, unknown>;
  const outcome = (m.outcome ?? m.status ?? "").toString();
  const outcomeClass =
    outcome === "success" ? "" :
    outcome === "partial_failure" ? "spec__outcome--partial" :
    outcome === "failure" ? "spec__outcome--failure" :
    "";

  return (
    <header className="spec">
      <div className="spec__brand">
        LabMind<sup>/OBS</sup>
      </div>

      <div className="spec__meta">
        <Cell label="Run">{m.run_id}</Cell>
        <Cell label="Type">{m.experiment_type || "—"}</Cell>
        {p.substrate ? <Cell label="Substrate">{String(p.substrate)}</Cell> : null}
        {p.cooling_rate_c_per_hour ? <Cell label="Cooling">{String(p.cooling_rate_c_per_hour)} °C/h</Cell> : null}
        {p.target_temp_c ? <Cell label="Target">{String(p.target_temp_c)} °C</Cell> : null}
        {m.start_time ? <Cell label="Started">{fmtDateTime(m.start_time)}</Cell> : null}
      </div>

      {outcome ? (
        <div className={`spec__outcome ${outcomeClass}`}>{outcome.replace(/_/g, " ")}</div>
      ) : null}

      <p className="spec__hypothesis">“{m.hypothesis}”</p>
    </header>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="spec__cell">
      <span className="spec__cell-label">{label}</span>
      <span className="spec__cell-value">{children}</span>
    </div>
  );
}
