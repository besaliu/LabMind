import type { BundleResponse, EventRange, Intervention, MicroscopyRow } from "../types/bundle";
import { CATEGORY_STYLES, narrativeFor } from "../lib/categories";
import { snakeToTitleCase } from "../lib/format";
import { fmtDateTime } from "../lib/time";

export type DetailTarget =
  | { kind: "overview" }
  | { kind: "intervention"; data: Intervention }
  | { kind: "event"; data: EventRange }
  | { kind: "microscopy"; data: MicroscopyRow };

interface Props {
  bundle: BundleResponse;
  target: DetailTarget;
}

export function DetailCard({ bundle, target }: Props) {
  if (target.kind === "intervention") return <InterventionDetail intervention={target.data} />;
  if (target.kind === "event") return <EventDetail range={target.data} />;
  if (target.kind === "microscopy") return <MicroscopyDetail row={target.data} bundle={bundle} />;
  return <OverviewDetail bundle={bundle} />;
}

/* ---------- Default: experiment overview ---------- */
function OverviewDetail({ bundle }: { bundle: BundleResponse }) {
  const m = bundle.metadata;
  const p = m.parameters as Record<string, unknown>;
  const outcome = (m.outcome ?? m.status ?? "—").toString();
  const accent =
    outcome === "success" ? CATEGORY_STYLES.intervention.color :
    outcome === "partial_failure" ? CATEGORY_STYLES.anomaly.color :
    outcome === "failure" ? CATEGORY_STYLES.threshold.color :
    "var(--ink-3)";

  return (
    <aside className="detail" style={{ ["--detail-accent" as never]: accent }}>
      <div className="detail__kind">Experiment overview</div>
      <h2 className="detail__title">{m.experiment_type || "Experiment"}</h2>

      <Row label="Run ID"><code>{m.run_id}</code></Row>
      <Row label="Outcome">{outcome.replace(/_/g, " ")}</Row>
      <Row label="Hypothesis">
        <span className="serif-italic" style={{ fontSize: 15, lineHeight: 1.5, color: "var(--ink-1)" }}>{m.hypothesis}</span>
      </Row>
      {p.substrate ? <Row label="Substrate">{String(p.substrate)}</Row> : null}
      {p.target_temp_c ? <Row label="Target T°">{String(p.target_temp_c)} °C</Row> : null}
      {p.cooling_rate_c_per_hour ? <Row label="Cooling">{String(p.cooling_rate_c_per_hour)} °C/h</Row> : null}
      {m.start_time ? <Row label="Start">{fmtDateTime(m.start_time)}</Row> : null}
      {m.end_time   ? <Row label="End">{fmtDateTime(m.end_time)}</Row> : null}
      <Row label="Interventions">{bundle.interventions.length}</Row>

      {m.key_findings && m.key_findings.length > 0 ? (
        <>
          <Row label="Findings"><span /></Row>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {m.key_findings.map((f, i) => (
              <li key={i} style={{
                fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-2)",
                lineHeight: 1.55, padding: "6px 0 6px 14px",
                borderLeft: "1px solid var(--line-2)", marginBottom: 6,
              }}>
                {f}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <div className="detail__hint">▌ hover an intervention or event band for context. click anywhere outside to return here.</div>
    </aside>
  );
}

/* ---------- Intervention: agent's reasoning + outcome ---------- */
function InterventionDetail({ intervention }: { intervention: Intervention }) {
  const tool = snakeToTitleCase(intervention.action.split("(")[0]);
  return (
    <aside className="detail" style={{ ["--detail-accent" as never]: CATEGORY_STYLES.intervention.color }}>
      <div className="detail__kind">Agent intervention</div>
      <h2 className="detail__title">{tool}</h2>

      <Row label="Time">{fmtDateTime(intervention.timestamp)}</Row>
      <Row label="Call"><code style={{ fontSize: 11 }}>{intervention.action}</code></Row>
      {intervention.instrument_id ? <Row label="Target">{intervention.instrument_id}</Row> : null}

      <div className="detail__kind" style={{ marginTop: 16 }}>Reasoning</div>
      <blockquote className="detail__quote">{intervention.reasoning}</blockquote>

      {intervention.outcome ? (
        <>
          <div className="detail__kind">Outcome</div>
          <blockquote className="detail__quote" style={{ borderLeftColor: "var(--cat-recovery)" }}>
            {intervention.outcome}
          </blockquote>
        </>
      ) : null}
    </aside>
  );
}

/* ---------- Event range: data observation ---------- */
function EventDetail({ range }: { range: EventRange }) {
  const style = CATEGORY_STYLES[range.category];
  return (
    <aside className="detail" style={{ ["--detail-accent" as never]: style.color }}>
      <div className="detail__kind">{style.label}</div>
      <h2 className="detail__title">{snakeToTitleCase(range.tag)}</h2>
      <Row label="Panel">{range.panel}</Row>
      <Row label="Window">
        <span style={{ display: "block" }}>{fmtDateTime(range.start)}</span>
        <span style={{ display: "block", color: "var(--ink-3)" }}>↓</span>
        <span style={{ display: "block" }}>{fmtDateTime(range.end)}</span>
      </Row>
      <blockquote className="detail__quote" style={{ borderLeftColor: style.color }}>
        {narrativeFor(range.tag)}
      </blockquote>
    </aside>
  );
}

/* ---------- Microscopy dot: snapshot detail ---------- */
function MicroscopyDetail({ row, bundle }: { row: MicroscopyRow; bundle: BundleResponse }) {
  const snap = bundle.microscopy_snapshot;
  return (
    <aside className="detail" style={{ ["--detail-accent" as never]: "var(--cat-recovery)" }}>
      <div className="detail__kind">Microscopy snapshot</div>
      <h2 className="detail__title">{fmtDateTime(row.t)}</h2>
      <Row label="Clarity">{row.clarity_pct?.toFixed(1)} %</Row>
      <Row label="Defects">{row.defect_count ?? 0}</Row>
      <Row label="Status">{row.status ?? "—"}</Row>
      {row.event ? (
        <blockquote className="detail__quote">{narrativeFor(row.event)}</blockquote>
      ) : null}
      {snap && Object.keys(snap).length > 0 ? (
        <>
          <div className="detail__kind" style={{ marginTop: 12 }}>End-of-run snapshot</div>
          {Object.entries(snap).map(([k, v]) => (
            <Row key={k} label={k}>{String(v)}</Row>
          ))}
        </>
      ) : null}
    </aside>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="detail__row">
      <span className="detail__row-label">{label}</span>
      <span className="detail__row-value">{children}</span>
    </div>
  );
}
