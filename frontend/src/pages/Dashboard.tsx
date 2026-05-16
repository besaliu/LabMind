import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchBundle } from "../api/dashboard";
import { ChartTooltip } from "../components/ChartTooltip";
import { DetailCard, type DetailTarget } from "../components/DetailCard";
import { FilterBar } from "../components/FilterBar";
import { InterventionPin } from "../components/InterventionPin";
import { SpecHeader } from "../components/SpecHeader";
import { CATEGORY_STYLES } from "../lib/categories";
import { snakeToTitleCase } from "../lib/format";
import { complementWithin } from "../lib/ranges";
import { toMillis } from "../lib/time";
import type {
  BundleResponse,
  EventCategory,
  EventRange,
} from "../types/bundle";

import "../styles/dashboard.css";

const ALL_CATEGORIES: EventCategory[] = ["anomaly", "threshold", "recovery", "intervention"];
const CHART_LEFT = 56;
const CHART_RIGHT = 24;
const PANEL_HEIGHT_MAIN = 200;
const PANEL_HEIGHT_MICRO = 160;
const BRUSH_HEIGHT = 70;

type ChartRow = { tMs: number } & Record<string, unknown>;
type RangeWithMs = EventRange & { startMs: number; endMs: number };
type InterventionWithMs = {
  timestamp: string;
  action: string;
  reasoning: string;
  outcome?: string;
  instrument_id?: string;
  tMs: number;
};

interface ThresholdBlock {
  warning_above?: number;
  critical_above?: number;
  warning_below?: number;
  critical_below?: number;
}

interface TooltipField {
  key: string;
  name: string;
  unit?: string;
  precision?: number;
}

interface PanelProps {
  railLabel: string;
  displayName: string;
  unit: string;
  height: number;
  data: ChartRow[];
  xDomain: [number, number];
  ranges: RangeWithMs[];
  dimRegions: { start: number; end: number }[];
  interventions: InterventionWithMs[];
  activeCats: Set<EventCategory>;
  onPinEnter: (iv: InterventionWithMs) => void;
  onBandEnter: (r: EventRange) => void;
  resolveCategory: (tag: string) => EventCategory | undefined;
  thresholds: ThresholdBlock;
  secondaryThresholds?: ThresholdBlock;
  yPad: [number, number];
  yDomain?: [number, number];
  tooltipFields: TooltipField[];
  children: React.ReactNode;
}

/* ============================================================
   Panel — top-level component with stable identity.
   Defined here (not inside Dashboard) so React reconciles it
   across re-renders instead of unmounting+remounting on every
   state change. memo() prevents work when props are unchanged.
============================================================ */
const Panel = memo(function Panel(props: PanelProps) {
  const interventionMarkers = useMemo(() => {
    const span = props.xDomain[1] - props.xDomain[0] || 1;
    return props.interventions
      .map((iv) => ({ ...iv, fraction: (iv.tMs - props.xDomain[0]) / span }))
      .filter((m) => m.fraction >= 0 && m.fraction <= 1);
  }, [props.interventions, props.xDomain]);

  const visibleBands = useMemo(
    () => props.ranges.filter((r) => props.activeCats.has(r.category)),
    [props.ranges, props.activeCats]
  );

  const yDomain = useMemo(() => {
    if (props.yDomain) return props.yDomain;
    return [
      (min: number) => min - props.yPad[0],
      (max: number) => max + props.yPad[1],
    ] as [(m: number) => number, (m: number) => number];
  }, [props.yDomain, props.yPad]);

  return (
    <div className="panel">
      <div className="panel__rail">{props.railLabel}</div>
      <div style={{ position: "relative" }}>
        <div className="panel__head">
          <span className="panel__name">{props.displayName}</span>
          <span className="panel__unit">{props.unit}</span>
        </div>
        <div className="panel__chart" style={{ position: "relative" }}>
          <ResponsiveContainer width="100%" height={props.height}>
            <LineChart
              data={props.data}
              margin={{ top: 8, right: CHART_RIGHT, left: CHART_LEFT, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="1 4" vertical={false} />
              <XAxis
                dataKey="tMs"
                type="number"
                domain={props.xDomain}
                scale="time"
                tickFormatter={(v: number) => new Date(v).toISOString().substring(11, 16)}
                tickMargin={6}
                allowDataOverflow
                minTickGap={40}
              />
              <YAxis
                yAxisId="left"
                domain={yDomain}
                tickFormatter={(v: number) => v.toFixed(1)}
                width={48}
              />
              {props.secondaryThresholds ? (
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[6.8, 7.5]}
                  tickFormatter={(v: number) => v.toFixed(2)}
                  width={42}
                />
              ) : null}

              {/* Threshold reference lines (faint dashed) */}
              {props.thresholds.warning_above ? (
                <ReferenceLine yAxisId="left" y={props.thresholds.warning_above} stroke="var(--line-3)" strokeDasharray="2 4" strokeOpacity={0.7} />
              ) : null}
              {props.thresholds.critical_above ? (
                <ReferenceLine yAxisId="left" y={props.thresholds.critical_above} stroke="var(--cat-threshold)" strokeDasharray="2 4" strokeOpacity={0.4} />
              ) : null}
              {props.thresholds.warning_below ? (
                <ReferenceLine yAxisId="left" y={props.thresholds.warning_below} stroke="var(--line-3)" strokeDasharray="2 4" strokeOpacity={0.7} />
              ) : null}
              {props.thresholds.critical_below ? (
                <ReferenceLine yAxisId="left" y={props.thresholds.critical_below} stroke="var(--cat-threshold)" strokeDasharray="2 4" strokeOpacity={0.4} />
              ) : null}
              {props.secondaryThresholds?.warning_above ? (
                <ReferenceLine yAxisId="right" y={props.secondaryThresholds.warning_above} stroke="var(--line-3)" strokeDasharray="2 4" strokeOpacity={0.5} />
              ) : null}

              {/* Event tag bands — visible only when their category is active.
                  isAnimationActive disabled so they don't re-fade on every state change. */}
              {visibleBands.map((r, idx) => {
                const style = CATEGORY_STYLES[r.category];
                return (
                  <ReferenceArea
                    key={`band-${idx}-${r.tag}`}
                    yAxisId="left"
                    x1={r.startMs}
                    x2={r.endMs}
                    fill={style.color}
                    fillOpacity={style.fillOpacity}
                    ifOverflow="hidden"
                    isFront={false}
                    isAnimationActive={false}
                    onMouseEnter={() => props.onBandEnter(r)}
                  />
                );
              })}

              {/* Spotlight dim — neutral gray wash over un-selected regions.
                  Tuned for the light theme: dark enough to clearly read as
                  "set aside" without crushing the data line underneath. */}
              {props.dimRegions.map((d, idx) => (
                <ReferenceArea
                  key={`dim-${idx}`}
                  yAxisId="left"
                  x1={d.start}
                  x2={d.end}
                  fill="#1a1814"
                  fillOpacity={0.18}
                  ifOverflow="hidden"
                  isAnimationActive={false}
                />
              ))}

              {/* Intervention vertical lines */}
              {props.activeCats.has("intervention") &&
                interventionMarkers.map((m, idx) => (
                  <ReferenceLine
                    key={`iv-${idx}`}
                    yAxisId="left"
                    x={m.tMs}
                    stroke="var(--accent)"
                    strokeWidth={2}
                    strokeOpacity={0.85}
                    ifOverflow="hidden"
                  />
                ))}

              <Tooltip
                content={
                  <ChartTooltip
                    fields={props.tooltipFields}
                    resolveCategory={props.resolveCategory}
                  />
                }
                cursor={{ stroke: "var(--accent)", strokeWidth: 1, strokeDasharray: "2 3" }}
                isAnimationActive={false}
              />

              {props.children}
            </LineChart>
          </ResponsiveContainer>

          {/* Intervention pins — absolute overlay (DOM, not SVG) */}
          {props.activeCats.has("intervention") &&
            interventionMarkers.map((m, idx) => {
              const tool = snakeToTitleCase(m.action.split("(")[0]);
              return (
                <InterventionPin
                  key={`pin-${idx}`}
                  fraction={m.fraction}
                  label={tool}
                  delayMs={700 + idx * 120}
                  leftMargin={CHART_LEFT}
                  rightMargin={CHART_RIGHT}
                  onEnter={() => props.onPinEnter(m)}
                  onClick={() => props.onPinEnter(m)}
                />
              );
            })}
        </div>
      </div>
    </div>
  );
});

/* ============================================================
   Dashboard — page-level orchestrator
============================================================ */
export function Dashboard() {
  const { runId = "run_005" } = useParams();
  const [bundle, setBundle] = useState<BundleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [activeCats, setActiveCats] = useState<Set<EventCategory>>(new Set(ALL_CATEGORIES));
  const [showImpurity, setShowImpurity] = useState(true);
  const [showPh, setShowPh] = useState(true);
  const [xDomain, setXDomain] = useState<[number, number] | null>(null);
  const [detail, setDetail] = useState<DetailTarget>({ kind: "overview" });

  useEffect(() => {
    let cancelled = false;
    fetchBundle(runId)
      .then((b) => { if (!cancelled) setBundle(b); })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [runId]);

  const toggleCat = useCallback((cat: EventCategory) => {
    setActiveCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }, []);

  /* ---------- Derived data ---------- */
  const prepared = useMemo(() => {
    if (!bundle) return null;
    const temp: ChartRow[] = bundle.series.temp.map((r) => ({ ...r, tMs: toMillis(r.t) }));
    const impurity: ChartRow[] = bundle.series.impurity.map((r) => ({ ...r, tMs: toMillis(r.t) }));
    const micro: ChartRow[] = bundle.series.microscopy.map((r) => ({ ...r, tMs: toMillis(r.t) }));

    const allTimes: number[] = [
      ...temp.map((r) => r.tMs),
      ...impurity.map((r) => r.tMs),
      ...micro.map((r) => r.tMs),
    ];
    const fullDomain: [number, number] = allTimes.length
      ? [Math.min(...allTimes), Math.max(...allTimes)]
      : [0, 1];

    const ranges: RangeWithMs[] = bundle.event_ranges.map((r) => ({
      ...r,
      startMs: toMillis(r.start),
      endMs: toMillis(r.end),
    }));

    const interventions: InterventionWithMs[] = bundle.interventions.map((iv) => ({
      ...iv,
      tMs: toMillis(iv.timestamp),
    }));

    return { temp, impurity, micro, fullDomain, ranges, interventions };
  }, [bundle]);

  const counts = useMemo(() => {
    const c: Record<EventCategory, number> = { anomaly: 0, threshold: 0, recovery: 0, intervention: 0 };
    if (!bundle) return c;
    for (const r of bundle.event_ranges) c[r.category] = (c[r.category] ?? 0) + 1;
    c.intervention = bundle.interventions.length;
    return c;
  }, [bundle]);

  const effectiveDomain = useMemo<[number, number] | null>(() => {
    if (!prepared) return null;
    return xDomain ?? prepared.fullDomain;
  }, [prepared, xDomain]);

  /* Per-panel range slices, memoized so Panel.memo() sees stable refs. */
  const tempRanges = useMemo(
    () => prepared?.ranges.filter((r) => r.panel === "temp") ?? [],
    [prepared]
  );
  const impurityRanges = useMemo(
    () => prepared?.ranges.filter((r) => r.panel === "impurity") ?? [],
    [prepared]
  );
  const microRanges = useMemo(
    () => prepared?.ranges.filter((r) => r.panel === "microscopy") ?? [],
    [prepared]
  );

  /* ---------- Spotlight: complement intervals to dim ---------- */
  const dimRegions = useMemo(() => {
    if (!prepared || !effectiveDomain) return [];
    if (activeCats.size === ALL_CATEGORIES.length) return [];

    const selectedRanges: { start: number; end: number }[] = [];
    for (const r of prepared.ranges) {
      if (activeCats.has(r.category)) {
        selectedRanges.push({ start: r.startMs, end: r.endMs });
      }
    }
    if (activeCats.has("intervention")) {
      const PAD = 2 * 60 * 1000;
      for (const iv of prepared.interventions) {
        selectedRanges.push({ start: iv.tMs - PAD, end: iv.tMs + PAD });
      }
    }
    return complementWithin(effectiveDomain, selectedRanges);
  }, [prepared, effectiveDomain, activeCats]);

  /* Stable callbacks so memo() prevents Panel re-renders on detail changes. */
  const handlePinEnter = useCallback((iv: InterventionWithMs) => {
    setDetail({ kind: "intervention", data: iv });
  }, []);
  const handleBandEnter = useCallback((r: EventRange) => {
    setDetail({ kind: "event", data: r });
  }, []);

  const resolveCategory = useCallback(
    (tag: string): EventCategory | undefined => {
      if (tag.startsWith("agent_intervention")) return "intervention";
      const found = prepared?.ranges.find((r) => r.tag === tag);
      return found?.category;
    },
    [prepared]
  );

  /* Stable tooltip field lists. */
  const tempTooltipFields = useMemo<TooltipField[]>(
    () => [
      { key: "temperature_c", name: "reading", unit: "°C", precision: 1 },
      { key: "setpoint_c", name: "setpoint", unit: "°C", precision: 1 },
    ],
    []
  );
  const impurityTooltipFields = useMemo<TooltipField[]>(
    () => [
      { key: "impurity_ppm", name: "impurity", unit: "ppm", precision: 1 },
      { key: "ph", name: "pH", precision: 2 },
    ],
    []
  );
  const microTooltipFields = useMemo<TooltipField[]>(
    () => [
      { key: "clarity_pct", name: "clarity", unit: "%", precision: 1 },
      { key: "defect_count", name: "defects", precision: 0 },
    ],
    []
  );

  /* ---------- Click outside chrome → reset detail ---------- */
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && t.closest("[data-detail-anchor]")) return;
      setDetail({ kind: "overview" });
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  /* ---------- Render guard states ---------- */
  if (error) {
    return (
      <div className="center">
        <div>
          <div className="center__display">Signal lost.</div>
          <div className="center__hint">{error}</div>
        </div>
      </div>
    );
  }
  if (!bundle || !prepared || !effectiveDomain) {
    return (
      <div className="center">
        <div>
          <div className="center__display">Establishing telemetry…</div>
          <div className="center__hint">▌ Fetching {runId}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="dash">
      <main className="dash__main" data-detail-anchor>
        <SpecHeader bundle={bundle} />

        <FilterBar
          active={activeCats}
          counts={counts}
          onToggle={toggleCat}
          showImpurity={showImpurity}
          showPh={showPh}
          onToggleImpurity={() => setShowImpurity((v) => !v)}
          onTogglePh={() => setShowPh((v) => !v)}
        />

        <div className="panels">
          <Panel
            railLabel="Temperature"
            displayName="Temperature"
            unit="°C"
            height={PANEL_HEIGHT_MAIN}
            data={prepared.temp}
            xDomain={effectiveDomain}
            ranges={tempRanges}
            dimRegions={dimRegions}
            interventions={prepared.interventions}
            activeCats={activeCats}
            onPinEnter={handlePinEnter}
            onBandEnter={handleBandEnter}
            resolveCategory={resolveCategory}
            thresholds={bundle.thresholds.temp}
            yPad={[0.4, 0.4]}
            tooltipFields={tempTooltipFields}
          >
            <Line
              type="monotone"
              yAxisId="left"
              dataKey="temperature_c"
              stroke="var(--ink-1)"
              strokeWidth={1.8}
              dot={false}
              isAnimationActive={false}
              name="reading"
            />
            <Line
              type="monotone"
              yAxisId="left"
              dataKey="setpoint_c"
              stroke="var(--cat-recovery)"
              strokeWidth={1.2}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
              name="setpoint"
            />
          </Panel>

          <Panel
            railLabel="Impurity + pH"
            displayName="Impurity / pH"
            unit="ppm  ·  pH"
            height={PANEL_HEIGHT_MAIN}
            data={prepared.impurity}
            xDomain={effectiveDomain}
            ranges={impurityRanges}
            dimRegions={dimRegions}
            interventions={prepared.interventions}
            activeCats={activeCats}
            onPinEnter={handlePinEnter}
            onBandEnter={handleBandEnter}
            resolveCategory={resolveCategory}
            thresholds={bundle.thresholds.impurity}
            secondaryThresholds={bundle.thresholds.ph}
            yPad={[2, 2]}
            tooltipFields={impurityTooltipFields}
          >
            {showImpurity ? (
              <Line
                type="monotone"
                yAxisId="left"
                dataKey="impurity_ppm"
                stroke="var(--series-impurity)"
                strokeWidth={1.8}
                dot={false}
                isAnimationActive={false}
                name="impurity"
              />
            ) : null}
            {showPh ? (
              <Line
                type="monotone"
                yAxisId="right"
                dataKey="ph"
                stroke="var(--series-ph)"
                strokeWidth={1.6}
                dot={false}
                isAnimationActive={false}
                name="pH"
              />
            ) : null}
          </Panel>

          <Panel
            railLabel="Microscopy"
            displayName="Crystal clarity"
            unit="%"
            height={PANEL_HEIGHT_MICRO}
            data={prepared.micro}
            xDomain={effectiveDomain}
            ranges={microRanges}
            dimRegions={dimRegions}
            interventions={prepared.interventions}
            activeCats={activeCats}
            onPinEnter={handlePinEnter}
            onBandEnter={handleBandEnter}
            resolveCategory={resolveCategory}
            thresholds={{}}
            yPad={[2, 2]}
            yDomain={[80, 100]}
            tooltipFields={microTooltipFields}
          >
            <Line
              type="monotone"
              yAxisId="left"
              dataKey="clarity_pct"
              stroke="var(--ink-3)"
              strokeWidth={1}
              strokeOpacity={0.6}
              dot={{ r: 3.5, fill: "var(--ink-1)", stroke: "var(--surface-1)", strokeWidth: 1.5 }}
              activeDot={{ r: 5.5, fill: "var(--accent)", stroke: "var(--surface-1)", strokeWidth: 2 }}
              isAnimationActive={false}
              name="clarity"
            />
          </Panel>
        </div>

        {/* Brush strip — controls all panels via xDomain */}
        <div className="brush-strip">
          <div className="brush-strip__label">▌ Time selector — drag handles to focus</div>
          <ResponsiveContainer width="100%" height={BRUSH_HEIGHT}>
            <LineChart
              data={prepared.impurity}
              margin={{ top: 4, right: CHART_RIGHT, bottom: 2, left: CHART_LEFT }}
            >
              <XAxis
                dataKey="tMs"
                type="number"
                domain={prepared.fullDomain}
                scale="time"
                tickFormatter={(v: number) => new Date(v).toISOString().substring(11, 16)}
                tick={{ fontSize: 9 }}
              />
              <YAxis hide domain={["auto", "auto"]} />
              <Line
                type="monotone"
                dataKey="impurity_ppm"
                stroke="var(--ink-3)"
                strokeWidth={1}
                dot={false}
                isAnimationActive={false}
              />
              <Brush
                dataKey="tMs"
                height={20}
                stroke="var(--accent)"
                fill="var(--surface-2)"
                travellerWidth={6}
                tickFormatter={(v: number) => new Date(v as number).toISOString().substring(11, 16)}
                onChange={(range) => {
                  const startMs = prepared.impurity[range.startIndex ?? 0]?.tMs;
                  const endMs = prepared.impurity[range.endIndex ?? prepared.impurity.length - 1]?.tMs;
                  if (typeof startMs === "number" && typeof endMs === "number") {
                    if (startMs === prepared.fullDomain[0] && endMs === prepared.fullDomain[1]) {
                      setXDomain(null);
                    } else {
                      setXDomain([startMs, endMs]);
                    }
                  }
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </main>

      <aside className="dash__aside" data-detail-anchor>
        <DetailCard bundle={bundle} target={detail} />
      </aside>
    </div>
  );
}
